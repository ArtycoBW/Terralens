import json
import math
from datetime import date, timedelta

from django.conf import settings
from django.core import signing
from django.db import connection, transaction
from django.db.models import Q
from django.http import FileResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema
from providers.base import ProviderError
from providers.osm import search_regions
from redis import Redis
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView
from services.geometry import validate_geometry
from services.jobs import cancel, enqueue, idempotent
from terralens_ml.io import canonical_hash, sha256
from terralens_ml.model import load_model

from .errors import DomainError
from .models import (
    AnalysisRun,
    CandidatePolygon,
    CropSeason,
    Discovery,
    Export,
    Job,
    ModelVersion,
    Polygon,
    PolygonVersion,
    Region,
    Workspace,
)
from .presentation import candidate_data, job_data, polygon_data, region_data, run_data
from .serializers import (
    AnalysisInput,
    ComparisonInput,
    DiscoveryInput,
    ExportInput,
    JobResponse,
    PolygonInput,
    PolygonPatch,
    VersionInput,
)


def validated(serializer, request):
    value = serializer(data=request.data)
    value.is_valid(raise_exception=True)
    return value.validated_data


def accessible(model, request, id, **filters):
    return get_object_or_404(model, pk=id, workspace=request.workspace, **filters)


def page(items, request, mapper=lambda x: x):
    try:
        limit = int(request.query_params.get("limit", 50))
        offset = (
            signing.loads(request.query_params["cursor"], salt="pagination", max_age=86400)
            if request.query_params.get("cursor")
            else 0
        )
        if not 1 <= limit <= 200 or not isinstance(offset, int) or offset < 0:
            raise ValueError()
    except (ValueError, signing.BadSignature) as exc:
        raise DomainError("invalid_pagination", "Некорректный cursor или limit", 400) from exc
    selected = list(items[offset : offset + limit + 1])
    return {
        "items": [mapper(x) for x in selected[:limit]],
        "next_cursor": signing.dumps(offset + limit, salt="pagination") if len(selected) > limit else None,
        "total": None,
    }


def bbox_value(value):
    if len(value) != 4 or not all(math.isfinite(x) for x in value):
        raise DomainError("invalid_geometry", "Некорректный bbox")
    west, south, east, north = value
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise DomainError("invalid_geometry", "Некорректный bbox")
    # Площадь между параллелями не обнуляется для bbox шириной 360° или у полюсов.
    area = (
        6371.0088**2
        * math.radians(east - west)
        * (math.sin(math.radians(north)) - math.sin(math.radians(south)))
    )
    if area > 2500:
        raise DomainError(
            "geometry_too_large", "Область поиска превышает 2500 км²", details={"value": area, "limit": 2500}
        )
    return value


class LiveView(APIView):
    permission_classes = []

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response({"status": "ok"})


class ReadyView(LiveView):
    def get(self, request):
        checks = {}
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            checks["database"] = True
        except Exception:
            checks["database"] = False
        try:
            checks["queue"] = bool(
                Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1).ping()
            )
        except Exception:
            checks["queue"] = False
        try:
            active = ModelVersion.objects.get(active=True)
            load_model(active.manifest_path)
            checks["model"] = True
        except Exception:
            checks["model"] = False
        return Response(
            {"status": "ready" if all(checks.values()) else "not_ready", "checks": checks},
            status=200 if all(checks.values()) else 503,
        )


class SessionView(APIView):
    permission_classes = []

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        origin = request.headers.get("Origin")
        allowed = {f"{request.scheme}://{request.get_host()}", *settings.CSRF_TRUSTED_ORIGINS}
        if origin not in allowed:
            raise DomainError("forbidden", "Для создания сессии требуется разрешённый Origin", 403)
        redis = Redis.from_url(settings.REDIS_URL)
        rate_key = "terralens:bootstrap:" + canonical_hash(request.META.get("REMOTE_ADDR", "unknown"))
        with redis.pipeline() as pipe:
            pipe.incr(rate_key)
            pipe.expire(rate_key, 60)
            count, _ = pipe.execute()
        if count > 20:
            raise DomainError("quota_exceeded", "Слишком много запросов создания сессии", 429)
        workspace = (
            Workspace.objects.filter(
                pk=request.session.get("workspace_id"), expires_at__gt=timezone.now()
            ).first()
            if request.session.get("workspace_id")
            else None
        )
        if workspace is None:
            workspace = Workspace.objects.create(
                expires_at=timezone.now() + timedelta(days=settings.WORKSPACE_DAYS)
            )
            request.session.cycle_key()
            request.session["workspace_id"] = str(workspace.id)
            request.session.set_expiry(settings.SESSION_COOKIE_AGE)
        return Response(
            {
                "workspace_id": str(workspace.id),
                "role": "guest",
                "expires_at": workspace.expires_at,
                "csrf_token": get_token(request),
            }
        )

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        workspace_id = request.session.get("workspace_id")
        workspace = (
            Workspace.objects.filter(pk=workspace_id, expires_at__gt=timezone.now()).first()
            if workspace_id
            else None
        )
        if workspace is None:
            raise DomainError("session_expired", "Сессия отсутствует или истекла", 401)
        return Response(
            {
                "workspace_id": str(workspace.id),
                "role": "guest",
                "expires_at": workspace.expires_at,
                "csrf_token": get_token(request),
            }
        )

    @extend_schema(responses={204: None})
    def delete(self, request):
        SessionAuthentication().enforce_csrf(request)
        request.session.flush()
        return Response(status=204)


class CapabilitiesView(LiveView):
    def get(self, request):
        active = ModelVersion.objects.filter(active=True).first()
        return Response(
            {
                "limits": {
                    "max_polygon_area_ha": settings.MAX_POLYGON_AREA_HA,
                    "max_vertices": settings.MAX_VERTICES,
                    "max_active_jobs": settings.MAX_ACTIVE_JOBS,
                    "max_polygons": settings.MAX_POLYGONS,
                    "max_period_days": settings.MAX_PERIOD_DAYS,
                    "max_discovery_area_km2": 2500,
                    "max_scenes": settings.MAX_SCENES,
                },
                "providers": [
                    {"id": "sentinel2", "provider": "earth_search", "collection": "sentinel-2-c1-l2a"},
                    {
                        "id": "landsat",
                        "provider": "planetary_computer_landsat",
                        "collection": "landsat-c2-l2",
                    },
                    {
                        "id": "era5_land",
                        "provider": "open_meteo_era5_seamless",
                        "aggregation": "centroid",
                        "temperature_source": "era5_land",
                        "precipitation_source": "era5",
                    },
                    {"id": "osm", "provider": "overpass"},
                ],
                "supported_modes": ["retrospective"],
                "active_model": active.model_id if active else None,
                "feature_flags": {
                    "export": True,
                    "comparison": True,
                    "realtime": False,
                    "calibrated_intervals": bool(
                        active and isinstance(active.manifest.get("calibration"), dict)
                    ),
                    "crop_seasons": True,
                },
                "retention": {"workspace_days": settings.WORKSPACE_DAYS, "export_days": settings.EXPORT_DAYS},
                "supported_period": {"from": "2017-01-01", "to": str(date.today() - timedelta(days=5))},
            }
        )


class RegionsView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        query = request.query_params.get("q", "").strip()
        country = request.query_params.get("country")
        if not 2 <= len(query) <= 150 or (country and (len(country) != 2 or not country.isalpha())):
            raise DomainError(
                "invalid_query",
                "Укажите поисковый запрос длиной 2–150 символов и код страны из двух букв",
                400,
            )
        try:
            raw = search_regions(query, country)
        except ProviderError as exc:
            raise DomainError(exc.code, str(exc), 503, {"provider": exc.provider}, exc.retryable) from exc
        items = []
        for row in raw:
            south, north, west, east = map(float, row["boundingbox"])
            region, _ = Region.objects.update_or_create(
                provider="nominatim",
                external_id=f"{row['osm_type']}:{row['osm_id']}",
                defaults={
                    "name": row["display_name"],
                    "country_code": row.get("address", {}).get("country_code", "").upper(),
                    "bbox": [west, south, east, north],
                },
            )
            items.append(region_data(region))
        return Response({"items": items, "next_cursor": None, "total": len(items)})


class RegionView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, id):
        return Response(region_data(get_object_or_404(Region, pk=id)))


class PolygonsView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        query = Polygon.objects.filter(workspace=request.workspace, deleted_at__isnull=True).order_by(
            "-created_at", "id"
        )
        if "bbox" in request.query_params:
            from django.contrib.gis.geos import Polygon as GEOSPolygon
            from django.db.models import F

            try:
                bounds = bbox_value([float(x) for x in request.query_params["bbox"].split(",")])
            except ValueError as exc:
                raise DomainError("invalid_geometry", "Некорректный bbox") from exc
            query = query.filter(
                versions__version=F("current_version"),
                versions__geometry__intersects=GEOSPolygon.from_bbox(bounds),
            )
        response = page(query, request, polygon_data)
        if request.query_params.get("lightweight") == "true":
            for item in response["items"]:
                item.pop("geometry")
        return Response(response)

    @extend_schema(request=PolygonInput, responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        data = validated(PolygonInput, request)
        source, source_ref = "user", ""
        if "candidate_id" in data:
            candidate = get_object_or_404(
                CandidatePolygon,
                pk=data["candidate_id"],
                discovery__workspace=request.workspace,
                expires_at__gt=timezone.now(),
            )
            data["geometry"] = json.loads(candidate.geometry.geojson)
            source, source_ref = "osm", candidate.source_ref
        geometry, area, digest = validate_geometry(data["geometry"])
        with transaction.atomic():
            Workspace.objects.select_for_update().get(pk=request.workspace.pk)
            if (
                Polygon.objects.filter(workspace=request.workspace, deleted_at__isnull=True).count()
                >= settings.MAX_POLYGONS
            ):
                raise DomainError("quota_exceeded", "Достигнут лимит сохранённых полей", 429)
            polygon = Polygon.objects.create(
                workspace=request.workspace,
                name=data["name"],
                crop_type=data.get("crop_type"),
                source=source,
                source_ref=source_ref,
                region=candidate.discovery.region if "candidate_id" in data else None,
            )
            PolygonVersion.objects.create(
                polygon=polygon, version=1, geometry=geometry, geometry_hash=digest, area_ha=area
            )
            CropSeason.objects.bulk_create(
                [CropSeason(polygon=polygon, **season) for season in data.get("crop_seasons", [])]
            )
        return Response(polygon_data(polygon), status=201)


class PolygonView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, id):
        return Response(polygon_data(accessible(Polygon, request, id, deleted_at__isnull=True)))

    @extend_schema(request=PolygonPatch, responses=OpenApiTypes.OBJECT)
    def patch(self, request, id):
        data = validated(PolygonPatch, request)
        geometry = validate_geometry(data["geometry"]) if "geometry" in data else None
        with transaction.atomic():
            Workspace.objects.select_for_update().get(pk=request.workspace.pk)
            polygon = get_object_or_404(
                Polygon.objects.select_for_update(),
                pk=id,
                workspace=request.workspace,
                deleted_at__isnull=True,
            )
            if polygon.current_version != data["expected_version"]:
                raise DomainError("version_conflict", "Контур уже изменён; обновите данные", 409)
            if geometry:
                polygon.current_version += 1
                PolygonVersion.objects.create(
                    polygon=polygon,
                    version=polygon.current_version,
                    geometry=geometry[0],
                    area_ha=geometry[1],
                    geometry_hash=geometry[2],
                )
            for key in ["name", "crop_type"]:
                if key in data:
                    setattr(polygon, key, data[key])
            if "crop_seasons" in data:
                polygon.cropseason_set.all().delete()
                CropSeason.objects.bulk_create(
                    [CropSeason(polygon=polygon, **season) for season in data["crop_seasons"]]
                )
            polygon.save()
        return Response(polygon_data(polygon))

    @extend_schema(request=VersionInput, responses={204: None})
    def delete(self, request, id):
        data = validated(VersionInput, request)
        with transaction.atomic():
            Workspace.objects.select_for_update().get(pk=request.workspace.pk)
            polygon = get_object_or_404(
                Polygon.objects.select_for_update(),
                pk=id,
                workspace=request.workspace,
                deleted_at__isnull=True,
            )
            if polygon.current_version != data["expected_version"]:
                raise DomainError("version_conflict", "Контур уже изменён", 409)
            polygon.deleted_at = timezone.now()
            polygon.save()
            for job in Job.objects.select_for_update(of=("self",)).filter(
                Q(run__polygon_version__polygon=polygon) | Q(export__run__polygon_version__polygon=polygon),
                state__in=["queued", "running"],
            ):
                cancel(job)
        return Response(status=204)


class AnalysesView(APIView):
    @extend_schema(request=AnalysisInput, responses={202: OpenApiTypes.OBJECT, 200: OpenApiTypes.OBJECT})
    def post(self, request):
        data = validated(AnalysisInput, request)

        def create():
            polygon = get_object_or_404(
                Polygon.objects.select_for_update(),
                pk=data["polygon_id"],
                workspace=request.workspace,
                deleted_at__isnull=True,
            )
            if polygon.current_version != data["polygon_version"]:
                raise DomainError("version_conflict", "Версия геометрии изменилась", 409)
            start, end = data["period"]["from"], data["period"]["to"]
            if (
                start > end
                or (end - start).days >= settings.MAX_PERIOD_DAYS
                or end > date.today() - timedelta(days=5)
                or start < date(2017, 1, 1)
            ):
                raise DomainError(
                    "unsupported_period",
                    f"Выберите период до {settings.MAX_PERIOD_DAYS} дней начиная с 2017 года, заканчивающийся не позднее пяти дней назад",
                )
            active = ModelVersion.objects.filter(active=True).first()
            if active is None:
                raise DomainError("model_unavailable", "Активная модель не зарегистрирована", 503)
            version = polygon.versions.get(version=polygon.current_version)
            config = {
                "sources": sorted(set(data["sources"])),
                "options": data.get("options", {"climatology_years": 3, "refresh_sources": False}),
                "crop_type": polygon.crop_type,
                "max_scenes": settings.MAX_SCENES,
                "source_revisions": {
                    "sentinel2": "sentinel-2-c1-l2a:full-aoi-qa-v3",
                    "landsat": "landsat-c2-l2:full-aoi-qa-v2",
                    "era5_land": "open-meteo-era5-seamless:utc-v2",
                },
                "crop_seasons": [
                    {
                        "season_start": str(season.season_start),
                        "season_end": str(season.season_end),
                        "crop_type": season.crop_type,
                        "origin": season.origin,
                    }
                    for season in polygon.cropseason_set.order_by("season_start")
                ],
                "aggregation": "multi-optical-median-full-aoi-v3",
                "reference_method": "median_mad",
            }
            fingerprint = canonical_hash(
                {
                    "version": str(version.id),
                    "period": [str(start), str(end)],
                    "model": active.model_id,
                    "config": config,
                }
            )
            existing = AnalysisRun.objects.filter(
                workspace=request.workspace, fingerprint=fingerprint, state__in=["queued", "running"]
            ).first()
            if existing:
                return {
                    "run_id": str(existing.id),
                    "job_id": str(existing.jobs.latest("created_at").id),
                    "state": existing.state,
                    "reused": True,
                }
            run = AnalysisRun.objects.create(
                workspace=request.workspace,
                polygon_version=version,
                model_version=active,
                period_from=start,
                period_to=end,
                mode=data["mode"],
                config=config,
                fingerprint=fingerprint,
            )
            job = enqueue(request.workspace, "analysis", run=run)
            return {"run_id": str(run.id), "job_id": str(job.id), "state": "queued", "reused": False}

        response, status = idempotent(request, create)
        return Response(response, status=status)


class AnalysisView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, id):
        return Response(run_data(accessible(AnalysisRun, request, id)))


class PolygonAnalysesView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, id):
        polygon = accessible(Polygon, request, id, deleted_at__isnull=True)
        return Response(
            page(
                AnalysisRun.objects.filter(polygon_version__polygon=polygon).order_by("-created_at", "id"),
                request,
                run_data,
            )
        )


class SeriesView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, id):
        run = accessible(AnalysisRun, request, id)
        points = run.points.all()
        for param, lookup in [("from", "date__gte"), ("to", "date__lte")]:
            if request.query_params.get(param):
                try:
                    value = date.fromisoformat(request.query_params[param])
                except ValueError as exc:
                    raise DomainError("unsupported_period", "Некорректная дата", 400) from exc
                points = points.filter(**{lookup: value})
        resolution = request.query_params.get("resolution", "daily")
        if resolution == "daily":
            return Response(page(points, request, lambda x: x.data) | {"actual_resolution": resolution})
        if resolution not in ["weekly", "monthly"]:
            raise DomainError("unsupported_resolution", "Допустимы daily, weekly, monthly", 400)
        groups = {}
        for point in points:
            start = (
                point.date - timedelta(days=point.date.weekday())
                if resolution == "weekly"
                else point.date.replace(day=1)
            )
            groups.setdefault(start, []).append(point.data)
        items = []
        for start, rows in groups.items():
            values = [x["reconstructed"] for x in rows if x["reconstructed"] is not None]
            z = [x["zscore"] for x in rows if x["zscore"] is not None]
            items.append(
                {
                    "bucket_start": str(start),
                    "bucket_end": rows[-1]["date"],
                    "estimate_mean": sum(values) / len(values) if values else None,
                    "estimate_min": min(values) if values else None,
                    "estimate_max": max(values) if values else None,
                    "observed_count": sum(x["clean_primary"] is not None for x in rows),
                    "available_day_count": len(values),
                    "total_day_count": len(rows),
                    "minimum_z": min(z) if z else None,
                    "quality_flags": sorted(set(f for x in rows for f in x["quality_flags"])),
                }
            )
        return Response(page(items, request) | {"actual_resolution": resolution})


class AnomaliesView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, id):
        run = accessible(AnalysisRun, request, id)
        events = run.anomalies.order_by("start_date", "id")
        if "severity" in request.query_params:
            if request.query_params["severity"] not in ["stress", "critical"]:
                raise DomainError("invalid_severity", "Допустимы stress или critical", 400)
            events = events.filter(severity=request.query_params["severity"])
        return Response(page(events, request, lambda x: x.data | {"id": str(x.id), "run_id": str(run.id)}))


class QualityView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, id):
        run = accessible(AnalysisRun, request, id)
        counts = {}
        for point in run.points.all():
            for flag in point.data["quality_flags"]:
                counts[flag] = counts.get(flag, 0) + 1
        return Response(
            {
                "summary": run.summary,
                "exclusions": counts,
                "warnings": run.warnings,
                "model": run.model_version.manifest,
                "reference": {
                    "method": "prior-seasons-same-aoi-crop-and-sensor-window-15-days-annual-median",
                    "center_and_scale": run.config.get(
                        "reference_method", "median_mad" if "robust_reference" in counts else "mean_std"
                    ),
                    "robust_scale_definition": "1.4826 * median(abs(annual_median - median(annual_medians)))",
                    "window_days": 15,
                    "minimum_years": 3,
                },
                "observed_days_definition": "Число дат с пригодным спутниковым наблюдением после QA и проверки NDVI",
            }
        )


class JobView(APIView):
    @extend_schema(responses=JobResponse)
    def get(self, request, id):
        return Response(job_data(accessible(Job, request, id)))


class CancelView(APIView):
    @extend_schema(request=None, responses={200: JobResponse, 202: JobResponse})
    def post(self, request, id):
        with transaction.atomic():
            job = get_object_or_404(Job.objects.select_for_update(), pk=id, workspace=request.workspace)
            status = cancel(job)
        return Response(job_data(job), status=status)


class RetryView(APIView):
    @extend_schema(request=None, responses={202: JobResponse})
    def post(self, request, id):
        with transaction.atomic():
            Workspace.objects.select_for_update().get(pk=request.workspace.pk)
            prior = get_object_or_404(Job.objects.select_for_update(), pk=id, workspace=request.workspace)
            if prior.state not in ["failed", "cancelled"] or not prior.retryable or prior.attempt >= 3:
                raise DomainError("retry_unavailable", "Повтор этой задачи недоступен", 409)
            references = {
                "run_id": prior.run_id,
                "discovery_id": prior.discovery_id,
                "export_id": prior.export_id,
            }
            if Job.objects.filter(**references, state__in=["queued", "running"]).exists():
                raise DomainError("retry_unavailable", "Повтор уже запущен", 409)
            latest = (
                Job.objects.filter(**references, workspace=request.workspace)
                .order_by("-created_at", "-id")
                .first()
            )
            if latest.id != prior.id:
                raise DomainError(
                    "retry_unavailable", "Повтор доступен только для последней попытки задачи", 409
                )
            if prior.run_id:
                if prior.run.polygon_version.polygon.deleted_at:
                    raise DomainError("retry_unavailable", "Поле удалено", 409)
                if prior.run.jobs.filter(state__in=["queued", "running"]).exists():
                    raise DomainError("retry_unavailable", "Повтор уже запущен", 409)
                if AnalysisRun.objects.filter(
                    workspace=request.workspace,
                    fingerprint=prior.run.fingerprint,
                    state__in=["queued", "running"],
                ).exists():
                    raise DomainError("retry_unavailable", "Уже запущен эквивалентный анализ", 409)
                prior.run.state, prior.run.completed_at = "queued", None
                prior.run.save(update_fields=["state", "completed_at"])
            if prior.discovery_id:
                prior.discovery.status = "queued"
                prior.discovery.source_status = {}
                prior.discovery.save(update_fields=["status", "source_status"])
            if prior.export_id:
                if (
                    prior.export.expires_at <= timezone.now()
                    or prior.export.run.polygon_version.polygon.deleted_at
                ):
                    raise DomainError(
                        "retry_unavailable", "Экспорт истёк или поле удалено; повтор недоступен", 409
                    )
                prior.export.state = "queued"
                prior.export.save(update_fields=["state"])
            job = enqueue(
                request.workspace,
                prior.kind,
                run=prior.run,
                discovery=prior.discovery,
                export=prior.export,
                parent_job=prior,
                attempt=prior.attempt + 1,
            )
        return Response(job_data(job), status=202)


class DiscoveriesView(APIView):
    @extend_schema(request=DiscoveryInput, responses={202: OpenApiTypes.OBJECT})
    def post(self, request):
        data = validated(DiscoveryInput, request)
        bounds = bbox_value(data["bbox"])

        def create():
            region = get_object_or_404(Region, pk=data["region_id"]) if data.get("region_id") else None
            discovery = Discovery.objects.create(workspace=request.workspace, region=region, bbox=bounds)
            job = enqueue(request.workspace, "discovery", discovery=discovery)
            return {
                "discovery_id": str(discovery.id),
                "job_id": str(job.id),
                "state": "queued",
                "reused": False,
            }

        response, status = idempotent(request, create)
        return Response(response, status=status)


class DiscoveryView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, id):
        discovery = accessible(Discovery, request, id)
        return Response(
            page(
                discovery.candidates.filter(expires_at__gt=timezone.now()).order_by("id"),
                request,
                candidate_data,
            )
            | {
                "status": discovery.status,
                "source_status": discovery.source_status,
                "coverage": {"bbox": discovery.bbox, "boundary_kind": "mapped_landuse"},
            }
        )


class ExportsView(APIView):
    @extend_schema(request=ExportInput, responses={202: OpenApiTypes.OBJECT})
    def post(self, request):
        data = validated(ExportInput, request)

        def create():
            run = accessible(AnalysisRun, request, data["run_id"])
            if run.state not in ["completed", "partial", "no_data"]:
                raise DomainError("result_unavailable", "Расчёт ещё не завершён", 409)
            export = Export.objects.create(
                workspace=request.workspace,
                run=run,
                format=data["format"],
                expires_at=timezone.now() + timedelta(days=settings.EXPORT_DAYS),
            )
            job = enqueue(request.workspace, "export", export=export)
            return {"export_id": str(export.id), "job_id": str(job.id), "state": "queued", "reused": False}

        response, status = idempotent(request, create)
        return Response(response, status=status)


class ExportView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, id):
        export = accessible(Export, request, id)
        available = export.state == "completed" and export.expires_at > timezone.now()
        return Response(
            {
                "id": str(export.id),
                "status": export.state,
                "filename": f"terralens-{export.id}.{export.format}",
                "hash": export.checksum or None,
                "expires_at": export.expires_at,
                "download_url": f"/api/v1/exports/{export.id}/download" if available else None,
                "manifest_url": f"/api/v1/exports/{export.id}/manifest"
                if available and export.manifest_checksum
                else None,
            }
        )


class DownloadView(APIView):
    @extend_schema(responses=OpenApiTypes.BINARY)
    def get(self, request, id):
        export = accessible(Export, request, id)
        if export.expires_at <= timezone.now():
            raise DomainError("artifact_expired", "Срок хранения экспорта истёк", 410)
        path = (settings.ARTIFACT_ROOT / export.artifact_path).resolve()
        if (
            export.state != "completed"
            or not path.is_relative_to(settings.ARTIFACT_ROOT)
            or not path.is_file()
        ):
            raise DomainError("result_unavailable", "Экспорт ещё не доступен", 409)
        if sha256(path) != export.checksum:
            raise DomainError("artifact_invalid", "Контрольная сумма экспорта не совпала", 503)
        return FileResponse(
            path.open("rb"), as_attachment=True, filename=f"terralens-{export.id}.{export.format}"
        )


class ExportManifestView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, id):
        export = accessible(Export, request, id)
        if export.expires_at <= timezone.now():
            raise DomainError("artifact_expired", "Срок хранения экспорта истёк", 410)
        path = (settings.ARTIFACT_ROOT / "exports" / f"{export.id}.manifest.json").resolve()
        if (
            export.state != "completed"
            or not path.is_relative_to(settings.ARTIFACT_ROOT)
            or not path.is_file()
        ):
            raise DomainError("result_unavailable", "Manifest экспорта ещё не доступен", 409)
        if sha256(path) != export.manifest_checksum:
            raise DomainError("artifact_invalid", "Контрольная сумма manifest не совпала", 503)
        return Response(json.loads(path.read_text()))


class ModelsView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(
            page(
                ModelVersion.objects.order_by("-created_at", "id"),
                request,
                lambda x: {
                    "id": x.model_id,
                    "active": x.active,
                    "artifact_hash": x.artifact_hash,
                    "metrics": x.manifest.get("metrics"),
                    "supported_modes": x.manifest["supported_modes"],
                    "created_at": x.created_at,
                },
            )
        )


class ComparisonsView(APIView):
    @extend_schema(request=ComparisonInput, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        data = validated(ComparisonInput, request)
        runs = [accessible(AnalysisRun, request, id) for id in data["run_ids"]]
        if any(run.state not in ["completed", "partial", "no_data"] for run in runs):
            raise DomainError("result_unavailable", "Для сравнения дождитесь завершения всех анализов", 409)
        axis, aligned = set(), []
        for run in runs:
            points = []
            for point in run.points.all():
                # Общий високосный календарь сохраняет месяц и день после 29 февраля.
                key = str(point.date) if data["alignment"] == "calendar" else point.date.strftime("%m-%d")
                axis.add(key)
                points.append(
                    {
                        "alignment_key": key,
                        "date": str(point.date),
                        **{
                            name: point.data[name]
                            for name in [
                                "reconstructed",
                                "origin",
                                "zscore",
                                "clean_primary",
                                "quality_flags",
                            ]
                        },
                    }
                )
            aligned.append({"run_id": str(run.id), "points": points})
        return Response(
            {
                "alignment": data["alignment"],
                "items": [
                    {"run": run_data(run), "series_url": f"/api/v1/analyses/{run.id}/series"} for run in runs
                ],
                "axis": sorted(axis),
                "aligned_series": aligned,
                "alignment_rule": "iso-date"
                if data["alignment"] == "calendar"
                else "month-day-leap-preserving",
                "warnings": ["Сравнивайте культуры, сезоны и качество наблюдений"],
            }
        )
