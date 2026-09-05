from datetime import timedelta

import pytest
from apps.core.models import AnalysisRun, Job
from apps.core.tasks import execute_job, reconcile
from django.utils import timezone
from providers.base import ProviderError

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def polygon(client, geometry):
    response = client.post("/api/v1/polygons", {"name": "Тестовое поле", "geometry": geometry}, format="json")
    assert response.status_code == 201, response.data
    return response.data


def launch(client, field, key="analysis-1"):
    body = {
        "polygon_id": field["id"],
        "polygon_version": 1,
        "period": {"from": "2024-06-01", "to": "2024-06-10"},
        "sources": ["sentinel2", "era5_land"],
        "options": {"climatology_years": 0},
    }
    return client.post("/api/v1/analyses", body, format="json", HTTP_IDEMPOTENCY_KEY=key)


def test_workspace_isolation_and_csrf(client, client_factory, geometry):
    field = polygon(client, geometry)
    other = client_factory()
    assert other.get(f"/api/v1/polygons/{field['id']}").status_code == 404
    client.credentials()
    assert (
        client.delete(f"/api/v1/polygons/{field['id']}", {"expected_version": 1}, format="json").status_code
        == 403
    )
    assert (
        other.post("/api/v1/session", {}, format="json", HTTP_ORIGIN="https://untrusted.example").status_code
        == 403
    )


def test_geometry_validation_and_versioning(client, geometry):
    invalid = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}
    response = client.post("/api/v1/polygons", {"name": "Плохой контур", "geometry": invalid}, format="json")
    assert response.status_code == 422
    assert response.data["error"]["code"] == "invalid_geometry"
    field = polygon(client, geometry)
    response = client.patch(
        f"/api/v1/polygons/{field['id']}", {"expected_version": 1, "geometry": geometry}, format="json"
    )
    assert response.data["current_version"] == 2
    assert (
        client.patch(
            f"/api/v1/polygons/{field['id']}",
            {"expected_version": 1, "name": "Устаревшая правка"},
            format="json",
        ).status_code
        == 409
    )


def test_full_analysis_idempotency_duplicate_delivery_and_export(
    client, geometry, active_model, providers, no_dispatch
):
    field = polygon(client, geometry)
    created = launch(client, field)
    assert created.status_code == 202, created.data
    repeated = launch(client, field)
    assert repeated.status_code == 200 and repeated.data["reused"]
    assert repeated.data["job_id"] == created.data["job_id"]
    run_id, job_id = created.data["run_id"], created.data["job_id"]
    execute_job(job_id)
    run = client.get(f"/api/v1/analyses/{run_id}").data
    assert run["state"] == "partial"
    assert run["summary"]["observed_days"] == 2
    assert run["summary"]["overall_status"] == "insufficient_data"
    points = client.get(f"/api/v1/analyses/{run_id}/series").data
    assert len(points["items"]) == 10
    assert all(row["prediction_interval"]["method"] == "not_calibrated" for row in points["items"])
    assert all(row["zscore"] is None for row in points["items"])
    assert run["result_version"]
    execute_job(job_id)
    assert AnalysisRun.objects.get(pk=run_id).points.count() == 10
    weekly = client.get(f"/api/v1/analyses/{run_id}/series?resolution=weekly").data
    assert weekly["actual_resolution"] == "weekly"
    assert "observed_primary" not in weekly["items"][0]
    export = client.post(
        "/api/v1/exports", {"run_id": run_id, "format": "csv"}, format="json", HTTP_IDEMPOTENCY_KEY="export-1"
    )
    assert export.status_code == 202
    execute_job(export.data["job_id"])
    downloaded = client.get(f"/api/v1/exports/{export.data['export_id']}/download")
    assert downloaded.status_code == 200
    assert len(b"".join(downloaded.streaming_content).splitlines()) == 11


def test_private_job_export_and_run(client, client_factory, geometry, active_model, no_dispatch):
    created = launch(client, polygon(client, geometry)).data
    other = client_factory()
    for path in [
        f"jobs/{created['job_id']}",
        f"analyses/{created['run_id']}",
        f"analyses/{created['run_id']}/series",
        f"analyses/{created['run_id']}/quality",
    ]:
        assert other.get("/api/v1/" + path).status_code == 404
    assert other.post(f"/api/v1/jobs/{created['job_id']}/cancel", {}, format="json").status_code == 404


def test_cancel_queued_and_retry(client, geometry, active_model, no_dispatch, providers):
    created = launch(client, polygon(client, geometry)).data
    response = client.post(f"/api/v1/jobs/{created['job_id']}/cancel", {}, format="json")
    assert response.status_code == 202 and response.data["state"] == "cancelled"
    execute_job(created["job_id"])
    assert not AnalysisRun.objects.get(pk=created["run_id"]).points.exists()
    retry = client.post(f"/api/v1/jobs/{created['job_id']}/retry", {}, format="json")
    assert retry.status_code == 202
    assert retry.data["parent_job_id"] == created["job_id"]
    execute_job(retry.data["id"])
    assert Job.objects.get(pk=retry.data["id"]).state == "succeeded"


def test_cancel_before_atomic_publication(
    client, geometry, active_model, no_dispatch, providers, monkeypatch
):
    from apps.core import tasks

    real = tasks.calculate
    created = launch(client, polygon(client, geometry)).data

    def cancel_before_result(*args, **kwargs):
        result = real(*args, **kwargs)
        Job.objects.filter(pk=created["job_id"]).update(cancel_requested=True)
        return result

    monkeypatch.setattr(tasks, "calculate", cancel_before_result)
    execute_job(created["job_id"])
    run = AnalysisRun.objects.get(pk=created["run_id"])
    assert run.state == "cancelled" and not run.points.exists()


def test_weather_partial_and_no_satellite_data(
    client, geometry, active_model, no_dispatch, providers, monkeypatch
):
    def no_weather(*args):
        raise ProviderError("provider_timeout", "Нет ответа", provider="open_meteo_era5_land", retryable=True)

    monkeypatch.setattr("apps.core.tasks.fetch_weather", no_weather)
    created = launch(client, polygon(client, geometry)).data
    execute_job(created["job_id"])
    run = AnalysisRun.objects.get(pk=created["run_id"])
    assert run.state == "partial" and run.summary["observed_days"] > 0
    assert any(x["code"] == "provider_timeout" for x in run.warnings)
    from providers.base import snapshot

    monkeypatch.setattr(
        "apps.core.tasks.fetch_satellite",
        lambda *args, **kwargs: ([], snapshot("earth_search", {}, {"observations": []})),
    )
    # refresh_sources обходит ранее записанный реальный кеш.
    second = launch(client, polygon(client, geometry), key="analysis-2").data
    item = AnalysisRun.objects.get(pk=second["run_id"])
    item.config["options"]["refresh_sources"] = True
    item.save()
    execute_job(second["job_id"])
    item.refresh_from_db()
    assert item.state == "no_data"
    assert item.summary["overall_status"] == "insufficient_data"
    assert all(x.data["reconstructed"] is None for x in item.points.all())


def test_idempotency_conflict_and_reconciliation(client, geometry, active_model, no_dispatch):
    created = launch(client, polygon(client, geometry)).data
    other_field = polygon(client, geometry)
    conflict = launch(client, other_field)
    assert conflict.status_code == 409
    Job.objects.filter(pk=created["job_id"]).update(
        state="running", heartbeat_at=timezone.now() - timedelta(minutes=10)
    )
    reconcile()
    job = Job.objects.get(pk=created["job_id"])
    assert job.state == "failed" and job.retryable


@pytest.mark.django_db(transaction=True)
def test_concurrent_posts_create_one_job(client, geometry, active_model, no_dispatch):
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections
    from rest_framework.test import APIClient

    field = polygon(client, geometry)

    def post():
        worker_client = APIClient(enforce_csrf_checks=True)
        worker_client.cookies.update(client.cookies)
        worker_client.credentials(**client._credentials)
        try:
            response = launch(worker_client, field, key="concurrent")
            return response.status_code, response.data
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: post(), range(2)))
    assert sorted(status for status, _ in results) == [200, 202]
    assert len({body["job_id"] for _, body in results}) == 1
    assert Job.objects.count() == 1


def test_discovery_candidates_and_expired_export(
    client, geometry, active_model, providers, no_dispatch, monkeypatch
):
    from apps.core.models import CandidatePolygon, Export
    from providers.base import snapshot

    monkeypatch.setattr(
        "apps.core.tasks.discover",
        lambda bbox: (
            [
                {
                    "geometry": geometry,
                    "name": "Поле из OSM",
                    "source_ref": "https://www.openstreetmap.org/way/542661544",
                }
            ],
            snapshot("overpass", {}, {}),
        ),
    )
    response = client.post(
        "/api/v1/discoveries",
        {"bbox": [13.0, 52.49, 13.01, 52.50], "sources": ["osm"]},
        format="json",
        HTTP_IDEMPOTENCY_KEY="discover-1",
    )
    assert response.status_code == 202
    execute_job(response.data["job_id"])
    discovery = client.get(f"/api/v1/discoveries/{response.data['discovery_id']}").data
    assert discovery["status"] == "completed" and len(discovery["items"]) == 1
    candidate_id = discovery["items"][0]["candidate_id"]
    created = client.post(
        "/api/v1/polygons", {"name": "Кандидат", "candidate_id": candidate_id}, format="json"
    )
    assert created.status_code == 201 and created.data["source"] == "osm"
    CandidatePolygon.objects.filter(pk=candidate_id).update(expires_at=timezone.now() - timedelta(seconds=1))
    assert (
        client.post(
            "/api/v1/polygons", {"name": "Просрочен", "candidate_id": candidate_id}, format="json"
        ).status_code
        == 404
    )
    run = launch(client, created.data).data
    execute_job(run["job_id"])
    export = Export.objects.create(
        workspace_id=created.data["workspace_id"],
        run_id=run["run_id"],
        format="csv",
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    assert client.get(f"/api/v1/exports/{export.id}/download").status_code == 410


@pytest.mark.parametrize(
    "coordinates",
    [
        [[[0, 0], [0.01, 0], [0.01, 0.01], [0, 0.01]]],
        [[[0, 0], [0.01, "0"], [0.01, 0.01], [0, 0]]],
        [[[0, 0], [True, 0], [0.01, 0.01], [0, 0]]],
        [],
    ],
)
def test_malformed_coordinate_structure_returns_domain_error(client, coordinates):
    response = client.post(
        "/api/v1/polygons",
        {
            "name": "Проверка геометрии",
            "geometry": {"type": "Polygon", "coordinates": coordinates},
        },
        format="json",
    )
    assert response.status_code == 422
    assert response.data["error"]["code"] == "invalid_geometry"


def test_discovery_world_bbox_cannot_bypass_area_quota(client, no_dispatch):
    response = client.post(
        "/api/v1/discoveries",
        {"bbox": [-180, -90, 180, 90]},
        format="json",
        HTTP_IDEMPOTENCY_KEY="world-bbox",
    )
    assert response.status_code == 422
    assert response.data["error"]["code"] == "geometry_too_large"


def test_json_payload_limit_returns_contract_error(client, settings):
    settings.DATA_UPLOAD_MAX_MEMORY_SIZE = 100
    response = client.post("/api/v1/polygons", {"name": "X" * 200}, format="json")
    assert response.status_code == 413
    assert response.data["error"]["code"] == "payload_too_large"


def test_crop_history_validation_frozen_run_and_latest_geometry(client, geometry, active_model, no_dispatch):
    seasons = [
        {"season_start": "2023-01-01", "season_end": "2023-12-31", "crop_type": "пшеница"},
        {"season_start": "2024-01-01", "season_end": "2024-12-31", "crop_type": "кукуруза"},
    ]
    response = client.post(
        "/api/v1/polygons",
        {"name": "Севооборот", "geometry": geometry, "crop_seasons": seasons},
        format="json",
    )
    assert response.status_code == 201, response.data
    field = response.data
    assert [season["crop_type"] for season in field["crop_seasons"]] == ["пшеница", "кукуруза"]
    created = launch(client, field).data
    assert client.get(f"/api/v1/polygons/{field['id']}").data["latest_run_id"] == created["run_id"]
    overlap = seasons + [{"season_start": "2024-06-01", "season_end": "2024-06-10", "crop_type": None}]
    invalid = client.patch(
        f"/api/v1/polygons/{field['id']}", {"expected_version": 1, "crop_seasons": overlap}, format="json"
    )
    assert invalid.status_code == 400
    updated = client.patch(
        f"/api/v1/polygons/{field['id']}",
        {"expected_version": 1, "geometry": geometry, "crop_seasons": []},
        format="json",
    )
    assert updated.status_code == 200 and updated.data["latest_run_id"] is None
    run = AnalysisRun.objects.get(pk=created["run_id"])
    assert len(run.config["crop_seasons"]) == 2
    assert run.polygon_version.version == 1


def test_retry_only_latest_attempt_and_enforces_limit(client, geometry, active_model, no_dispatch):
    created = launch(client, polygon(client, geometry)).data
    first_id = created["job_id"]
    current = first_id
    for attempt in range(1, 4):
        assert client.post(f"/api/v1/jobs/{current}/cancel", {}, format="json").status_code == 202
        if attempt > 1:
            assert client.post(f"/api/v1/jobs/{first_id}/retry", {}, format="json").status_code == 409
        retry = client.post(f"/api/v1/jobs/{current}/retry", {}, format="json")
        if attempt == 3:
            assert retry.status_code == 409
        else:
            assert retry.status_code == 202 and retry.data["attempt"] == attempt + 1
            current = retry.data["id"]
            run = AnalysisRun.objects.get(pk=created["run_id"])
            assert run.state == "queued" and run.completed_at is None


def test_duplicate_active_run_reuses_pair_with_new_key(client, geometry, active_model, no_dispatch):
    field = polygon(client, geometry)
    first = launch(client, field)
    repeated = launch(client, field, key="same-body-new-key")
    assert first.status_code == 202 and repeated.status_code == 200
    assert repeated.data["reused"] and repeated.data["run_id"] == first.data["run_id"]


def test_export_manifest_intervals_and_isolation(
    client, client_factory, geometry, active_model, providers, no_dispatch
):
    import csv
    import io

    created = launch(client, polygon(client, geometry)).data
    execute_job(created["job_id"])
    accepted = client.post(
        "/api/v1/exports",
        {"run_id": created["run_id"], "format": "csv"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="manifest-export",
    ).data
    execute_job(accepted["job_id"])
    info = client.get(f"/api/v1/exports/{accepted['export_id']}").data
    manifest = client.get(info["manifest_url"])
    assert manifest.status_code == 200
    assert manifest.data["model_manifest"]["model_id"] == active_model.model_id
    assert manifest.data["artifact_hash"] == info["hash"]
    assert manifest.data["config"]["sources"] == ["era5_land", "sentinel2"]
    assert manifest.data["snapshots"][0]["query_hash"]
    downloaded = client.get(info["download_url"])
    rows = list(csv.DictReader(io.StringIO(b"".join(downloaded.streaming_content).decode())))
    assert {"interval_lower", "interval_upper", "interval_method", "severity", "weather_provider"} <= set(
        rows[0]
    )
    assert rows[0]["interval_method"] == "not_calibrated"
    assert client_factory().get(info["manifest_url"]).status_code == 404


def test_comparison_alignment_keeps_leap_dates_and_rejects_pending(
    client, geometry, active_model, no_dispatch
):
    from datetime import date

    from apps.core.models import DailyEstimate

    created = launch(client, polygon(client, geometry)).data
    body = {"run_ids": [created["run_id"]], "alignment": "day_of_year"}
    assert client.post("/api/v1/comparisons", body, format="json").status_code == 409
    run = AnalysisRun.objects.get(pk=created["run_id"])
    run.state = "partial"
    run.save(update_fields=["state"])
    for day in [date(2024, 2, 28), date(2024, 2, 29), date(2024, 3, 1)]:
        DailyEstimate.objects.create(
            run=run,
            date=day,
            data={
                "date": str(day),
                "reconstructed": 0.4,
                "clean_primary": None,
                "origin": "interpolated",
                "zscore": None,
                "quality_flags": ["insufficient_reference"],
            },
        )
    response = client.post("/api/v1/comparisons", body, format="json")
    assert response.data["axis"] == ["02-28", "02-29", "03-01"]
    assert response.data["aligned_series"][0]["points"][1]["date"] == "2024-02-29"
    body["run_ids"] *= 2
    assert client.post("/api/v1/comparisons", body, format="json").status_code == 400


def test_polygon_delete_cancels_export_and_quota_is_enforced(
    client, geometry, active_model, providers, no_dispatch, settings
):
    settings.MAX_POLYGONS = 1
    field = polygon(client, geometry)
    denied = client.post("/api/v1/polygons", {"name": "Лишнее поле", "geometry": geometry}, format="json")
    assert denied.status_code == 429
    run = launch(client, field).data
    execute_job(run["job_id"])
    exported = client.post(
        "/api/v1/exports",
        {"run_id": run["run_id"], "format": "json"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="delete-export",
    ).data
    response = client.delete(f"/api/v1/polygons/{field['id']}", {"expected_version": 1}, format="json")
    assert response.status_code == 204
    assert Job.objects.get(pk=exported["job_id"]).state == "cancelled"
    assert client.post(f"/api/v1/jobs/{exported['job_id']}/retry", {}, format="json").status_code == 409
