import pytest
from apps.core.models import Job, SourceSnapshot
from apps.core.tasks import execute_job
from providers.base import ProviderError, snapshot

from .test_analysis import observation
from .test_api import polygon


@pytest.mark.django_db
def test_failed_sentinel_uses_landsat_and_cached_snapshot_without_new_fetch(
    client,
    geometry,
    active_model,
    no_dispatch,
    providers,
    monkeypatch,
):
    def failed(*args, **kwargs):
        raise ProviderError("provider_timeout", "Нет ответа S2", provider="earth_search", retryable=True)

    calls = []

    def landsat(*args, **kwargs):
        calls.append(args)
        records = [observation("2024-06-01", 0.7, "landsat"), observation("2024-06-10", 0.5, "landsat")]
        return records, snapshot("planetary_computer_landsat", {}, {"observations": records})

    monkeypatch.setattr("apps.core.tasks.fetch_satellite", failed)
    monkeypatch.setattr("apps.core.tasks.fetch_landsat", landsat)
    for index in range(2):
        field = polygon(client, geometry)
        created = client.post(
            "/api/v1/analyses",
            {
                "polygon_id": field["id"],
                "polygon_version": 1,
                "period": {"from": "2024-06-01", "to": "2024-06-10"},
                "sources": ["sentinel2", "landsat", "era5_land"],
                "options": {"climatology_years": 0},
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=f"multi-{index}",
        )
        assert created.status_code == 202
        execute_job(created.data["job_id"])
        assert Job.objects.get(pk=created.data["job_id"]).state == "succeeded"
        run = client.get(f"/api/v1/analyses/{created.data['run_id']}").data
        assert run["state"] == "partial"
        assert run["summary"]["observed_days"] == 2
        assert any(x["provider"] == "earth_search" for x in run["warnings"] if "provider" in x)
        points = client.get(f"/api/v1/analyses/{created.data['run_id']}/series").data["items"]
        assert points[0]["source_sensor"] == "landsat"
        assert points[0]["sensors"]["sentinel2"] is None
    assert len(calls) == 1
    assert SourceSnapshot.objects.filter(provider="planetary_computer_landsat").count() == 1
