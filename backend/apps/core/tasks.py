import json
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from providers.base import ProviderError
from providers.landsat import fetch_landsat
from providers.osm import discover
from providers.stac import fetch_satellite
from providers.weather import fetch_weather
from services.analysis import calculate, worker_model
from services.geometry import validate_geometry
from shapely.geometry import shape
from terralens_ml.io import DataError, atomic_write, canonical_hash, sha256, write_json

from .errors import DomainError
from .models import AnalysisRun, AnomalyPeriod, CandidatePolygon, DailyEstimate, Job, SourceSnapshot

logger = logging.getLogger(__name__)


class Cancelled(Exception):
    pass


def checkpoint(job_id, stage, progress=None):
    updated = Job.objects.filter(pk=job_id, state="running", cancel_requested=False).update(
        stage=stage, progress=progress, heartbeat_at=timezone.now()
    )
    if not updated:
        raise Cancelled()


def source_snapshot(run, provider, start, end, fetch):
    key = canonical_hash(
        {
            "geometry": run.polygon_version.geometry_hash,
            "provider": provider,
            "period": [str(start), str(end)],
            "aggregation": run.config["aggregation"],
            "max_scenes": run.config.get("max_scenes", settings.MAX_SCENES),
            "source_revisions": run.config.get("source_revisions", {}),
            "workspace": str(run.workspace_id),
        }
    )
    if not run.config["options"].get("refresh_sources"):
        cached = (
            SourceSnapshot.objects.filter(query_hash=key, created_at__gt=timezone.now() - timedelta(days=1))
            .order_by("-created_at")
            .first()
        )
        if cached:
            path = (settings.ARTIFACT_ROOT / cached.artifact_path).resolve()
            if (
                path.is_relative_to(settings.ARTIFACT_ROOT)
                and path.is_file()
                and sha256(path) == cached.checksum
            ):
                data = json.loads(path.read_text())
                records = data.get("records", data.get("data", {}).get("observations", []))
                return records, cached
    records, data = fetch()
    data["records"] = records
    snapshot = SourceSnapshot(
        provider=provider,
        query_hash=key,
        geometry_hash=run.polygon_version.geometry_hash,
        status="partial" if data["warnings"] else "completed",
        metadata={k: v for k, v in data.items() if k not in ["data", "records"]},
    )
    relative = f"snapshots/{snapshot.id}.json"
    path = settings.ARTIFACT_ROOT / relative
    write_json(path, data)
    snapshot.artifact_path, snapshot.checksum = relative, sha256(path)
    snapshot.save()
    return records, snapshot


def analyze(job):
    run = job.run
    geometry = shape(json.loads(run.polygon_version.geometry.geojson))
    warnings, snapshots, observations, weather, history = [], [], [], [], []
    sources = {
        "sentinel2": ("earth_search", fetch_satellite, 2017),
        "landsat": ("planetary_computer_landsat", fetch_landsat, 2013),
    }
    max_scenes = run.config.get("max_scenes", settings.MAX_SCENES)

    # Plan all sensor/season requests before reporting progress. Provider callbacks
    # count scenes within one request, not within the complete analysis.
    batches = []

    def collect(provider, fetch, start, end, report):
        report(0, 1)
        records, source = source_snapshot(
            run,
            provider,
            start,
            end,
            lambda: fetch(
                geometry,
                start,
                end,
                max_scenes=max_scenes,
                progress=report,
            ),
        )
        snapshots.append(source)
        for warning in source.metadata["warnings"]:
            warnings.append(
                {
                    **warning,
                    "provider": provider,
                    "affected_period": {"from": str(start), "to": str(end)},
                }
            )
        return records

    def warn_failure(exc, start, end):
        warnings.append(
            {
                "code": exc.code,
                "provider": exc.provider,
                "affected_period": {"from": str(start), "to": str(end)},
                "retryable": exc.retryable,
            }
        )

    for sensor in run.config["sources"]:
        if sensor not in sources:
            continue
        provider, fetch, first_year = sources[sensor]
        batches.append((provider, fetch, run.period_from, run.period_to, observations))
        for delta in range(1, run.config["options"].get("climatology_years", 3) + 1):

            def prior_date(day):
                try:
                    return day.replace(year=day.year - delta)
                except ValueError:
                    return day.replace(year=day.year - delta, day=28)

            start, end = prior_date(run.period_from), prior_date(run.period_to)
            if start.year < first_year:
                warnings.append(
                    {
                        "code": "insufficient_reference",
                        "provider": provider,
                        "affected_period": {"from": str(start), "to": str(end)},
                    }
                )
                continue
            # Окно нормы требует контекста по обе стороны даты прошлого сезона.
            start, end = start - timedelta(days=15), end + timedelta(days=15)
            batches.append((provider, fetch, start, end, history))

    has_weather = "era5_land" in run.config["sources"]
    satellite_share = 0.8 if has_weather else 0.9
    for index, (provider, fetch, start, end, target) in enumerate(batches):
        stage = "fetching_reference" if target is history else "fetching_satellite"
        fraction = 0.0

        def report(i, n):
            nonlocal fraction
            fraction = max(fraction, min(1.0, max(0.0, i / n if n else 0.0)))
            checkpoint(job.id, stage, satellite_share * (index + fraction) / len(batches))

        try:
            target.extend(collect(provider, fetch, start, end, report))
        except ProviderError as exc:
            warn_failure(exc, start, end)
        # Cached, empty and failed requests also finish their part of the plan.
        # Cancellation propagates before this checkpoint and never publishes success.
        report(1, 1)
    if has_weather:
        checkpoint(job.id, "fetching_weather", satellite_share)
        try:
            weather, source = source_snapshot(
                run,
                "open_meteo_era5_seamless",
                run.period_from,
                run.period_to,
                lambda: fetch_weather(geometry, run.period_from, run.period_to),
            )
            snapshots.append(source)
            warnings.extend(source.metadata["warnings"])
        except ProviderError as exc:
            warnings.append({"code": exc.code, "provider": exc.provider, "affected_fields": ["weather"]})
    checkpoint(job.id, "reconstructing", 0.9)
    model = worker_model(run.model_version.manifest_path, run.model_version.artifact_hash)
    daily, events, summary = calculate(
        run.polygon_version.polygon_id,
        run.config.get("crop_type"),
        run.period_from,
        run.period_to,
        observations,
        weather,
        model,
        history,
        crop_seasons=run.config.get("crop_seasons", []),
    )
    checkpoint(job.id, "detecting", 0.97)
    if not any(x["reference_years"] >= 3 for x in daily):
        warnings.append(
            {"code": "insufficient_reference", "message": "Не набрано три сопоставимых исторических сезона"}
        )
    if not run.config.get("crop_seasons") and history:
        warnings.append(
            {
                "code": "crop_history_unknown",
                "message": "История культуры неизвестна; сопоставимость сезонов требует проверки",
            }
        )
    state = "no_data" if summary["observed_days"] == 0 else "partial" if warnings else "completed"
    with transaction.atomic():
        locked = Job.objects.select_for_update().get(pk=job.id)
        if locked.cancel_requested or locked.state != "running":
            raise Cancelled()
        DailyEstimate.objects.filter(run=run).delete()
        AnomalyPeriod.objects.filter(run=run).delete()
        DailyEstimate.objects.bulk_create([DailyEstimate(run=run, date=x["date"], data=x) for x in daily])
        AnomalyPeriod.objects.bulk_create(
            [
                AnomalyPeriod(
                    run=run,
                    start_date=x["start_date"],
                    end_date=x["end_date"],
                    severity=x["severity"],
                    data=x,
                )
                for x in events
            ]
        )
        run.snapshots.set(snapshots)
        run.summary, run.warnings, run.state = summary, warnings, state
        run.result_version = canonical_hash(
            {"daily": daily, "events": events, "model": run.model_version.model_id}
        )
        run.completed_at = timezone.now()
        run.save()
        finish(locked, "succeeded")


def discover_fields(job):
    checkpoint(job.id, "discovering")
    records, snapshot = discover(job.discovery.bbox)
    candidates = []
    for record in records:
        try:
            geometry, area, _ = validate_geometry(record["geometry"])
        except DomainError:
            continue
        candidates.append(
            CandidatePolygon(
                discovery=job.discovery,
                geometry=geometry,
                area_ha=area,
                source_ref=record["source_ref"],
                name=record["name"],
                expires_at=timezone.now() + timedelta(days=1),
            )
        )
    with transaction.atomic():
        locked = Job.objects.select_for_update().get(pk=job.id)
        if locked.cancel_requested or locked.state != "running":
            raise Cancelled()
        job.discovery.candidates.all().delete()
        CandidatePolygon.objects.bulk_create(candidates)
        job.discovery.status = "completed"
        job.discovery.source_status = {
            "osm": {
                "status": "completed",
                "count": len(candidates),
                "retrieved_at": snapshot["retrieved_at"],
                "warnings": snapshot["warnings"],
                "attribution": "© OpenStreetMap contributors, ODbL",
            }
        }
        job.discovery.save()
        finish(locked, "succeeded")


def export_result(job):
    from services.exports import build_export

    checkpoint(job.id, "exporting")
    export = job.export
    text, manifest = build_export(export)
    relative = f"exports/{export.id}.{export.format}"
    artifact = settings.ARTIFACT_ROOT / relative
    manifest_path = settings.ARTIFACT_ROOT / f"exports/{export.id}.manifest.json"
    atomic_write(artifact, text)
    checksum = sha256(artifact)
    write_json(manifest_path, manifest | {"artifact_hash": checksum})
    with transaction.atomic():
        locked = Job.objects.select_for_update().get(pk=job.id)
        if locked.cancel_requested or locked.state != "running":
            raise Cancelled()
        export.artifact_path, export.checksum = relative, checksum
        export.manifest_checksum = sha256(manifest_path)
        export.state = "completed"
        export.save()
        finish(locked, "succeeded")


def finish(job, state, error=None, retryable=False):
    job.state, job.error, job.retryable = state, error, retryable
    job.finished_at, job.heartbeat_at = timezone.now(), timezone.now()
    job.progress = 1 if state == "succeeded" else job.progress
    job.save()


@shared_task
def execute_job(job_id):
    from services.jobs import cancel, heartbeat

    with transaction.atomic():
        job = Job.objects.select_for_update().filter(pk=job_id).first()
        if job is None or job.state != "queued":
            return
        if job.cancel_requested or job.workspace.expires_at <= timezone.now():
            cancel(job)
            return
        job.state, job.started_at, job.heartbeat_at = "running", timezone.now(), timezone.now()
        job.save()
        if job.run_id:
            job.run.state = "running"
            job.run.save(update_fields=["state"])
        if job.discovery_id:
            job.discovery.status = "running"
            job.discovery.save(update_fields=["status"])
        if job.export_id:
            job.export.state = "running"
            job.export.save(update_fields=["state"])
    try:
        with heartbeat(job.id):
            {"analysis": analyze, "discovery": discover_fields, "export": export_result}[job.kind](job)
    except Exception as exc:
        cancelled = isinstance(exc, Cancelled)
        error = (
            None
            if cancelled
            else {
                "code": getattr(exc, "code", "analysis_failed"),
                "message": str(exc)
                if isinstance(exc, (ProviderError, DataError))
                else "Не удалось завершить расчёт",
                "provider": getattr(exc, "provider", None),
            }
        )
        retryable = cancelled or getattr(exc, "retryable", False)
        if not cancelled:
            logger.exception(
                "job_failed", extra={"job_id": str(job.id), "run_id": str(job.run_id) if job.run_id else None}
            )
        with transaction.atomic():
            locked = Job.objects.select_for_update().get(pk=job_id)
            if locked.state != "running":
                return
            state = "cancelled" if cancelled or locked.cancel_requested else "failed"
            finish(locked, state, None if state == "cancelled" else error, retryable or state == "cancelled")
            if locked.run_id:
                locked.run.state, locked.run.completed_at = state, timezone.now()
                locked.run.save(update_fields=["state", "completed_at"])
            if locked.discovery_id:
                locked.discovery.status, locked.discovery.source_status = state, {"error": error}
                locked.discovery.save()
            if locked.export_id:
                locked.export.state = state
                locked.export.save(update_fields=["state"])


@shared_task
def reconcile():
    from services.jobs import dispatch

    stale = timezone.now() - timedelta(minutes=5)
    for job_id in Job.objects.filter(state="running", heartbeat_at__lt=stale).values_list("id", flat=True):
        with transaction.atomic():
            job = Job.objects.select_for_update().get(pk=job_id)
            if job.state == "running" and job.heartbeat_at < stale:
                finish(
                    job,
                    "failed",
                    {"code": "worker_lost", "message": "Worker перестал отвечать; доступен повтор"},
                    True,
                )
                if job.run_id:
                    AnalysisRun.objects.filter(pk=job.run_id).update(
                        state="failed", completed_at=timezone.now()
                    )
                if job.discovery_id:
                    job.discovery.status = "failed"
                    job.discovery.save(update_fields=["status"])
                if job.export_id:
                    job.export.state = "failed"
                    job.export.save(update_fields=["state"])
    for job_id in (
        Job.objects.filter(state="queued")
        .filter(Q(dispatched_at__isnull=True) | Q(dispatched_at__lt=timezone.now() - timedelta(minutes=1)))
        .values_list("id", flat=True)[:100]
    ):
        dispatch(job_id)


@shared_task
def cleanup_retention():
    from services.retention import cleanup_retention as clean

    return clean()
