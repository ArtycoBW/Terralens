import pytest
from apps.core import tasks
from apps.core.models import AnalysisRun, Job
from providers.base import ProviderError, snapshot

from .test_analysis import observation
from .test_api import polygon


@pytest.mark.django_db
@pytest.mark.parametrize("mode", ["observations", "empty", "partial_failure"])
@pytest.mark.parametrize("period", ["2024-02-29", "2017-02-28"])
def test_progress_covers_all_seasons_and_cache_without_restarting(
    client, geometry, active_model, no_dispatch, providers, monkeypatch, mode, period
):
    samples, calls = [], []
    original_checkpoint = tasks.checkpoint

    def checkpoint(job_id, stage, progress=None):
        original_checkpoint(job_id, stage, progress)
        samples.append((stage, Job.objects.get(pk=job_id).progress))

    def fetch(geometry, start, end, *, max_scenes, progress):
        calls.append((start, end))
        progress(0, 0)
        if mode == "partial_failure" and start.year < 2020:
            progress(1, 2)
            raise ProviderError("provider_timeout", "Fixture timeout", provider="earth_search")
        records = [] if mode == "empty" else [observation(str(start), 0.6, "sentinel2")]
        progress(1, 2)
        progress(2, 2)
        return records, snapshot("earth_search", {}, {"observations": records})

    monkeypatch.setattr(tasks, "checkpoint", checkpoint)
    monkeypatch.setattr(tasks, "fetch_satellite", fetch)
    monkeypatch.setattr(tasks, "fetch_landsat", fetch)
    for repeat in range(2):
        samples.clear()
        field = polygon(client, geometry)
        response = client.post(
            "/api/v1/analyses",
            {
                "polygon_id": field["id"],
                "polygon_version": 1,
                "period": {"from": period, "to": period},
                "sources": ["sentinel2", "landsat", "era5_land"],
                "options": {"climatology_years": 3},
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=f"progress-{repeat}",
        )
        assert response.status_code == 202, response.data
        calls_before = len(calls)
        tasks.execute_job(response.data["job_id"])
        job = Job.objects.get(pk=response.data["job_id"])
        assert job.state == "succeeded" and job.progress == 1 and job.attempt == 1
        values = [value for _, value in samples]
        assert values and all(value is not None and 0 <= value < 1 for value in values)
        assert values == sorted(values), samples
        assert "fetching_reference" in {stage for stage, _ in samples}
        assert any(0 < value < 0.8 for stage, value in samples if stage == "fetching_reference")
        if repeat and mode != "partial_failure":
            assert len(calls) == calls_before, "Cached batches must also advance overall progress"
        if period.startswith("2017"):
            run = AnalysisRun.objects.get(pk=response.data["run_id"])
            assert any(w["code"] == "insufficient_reference" for w in run.warnings)
        if period.startswith("2024"):
            assert any(str(start) == "2023-02-13" for start, _ in calls)


@pytest.mark.django_db
def test_cancel_during_scene_progress_does_not_complete_next_batch(
    client, geometry, active_model, no_dispatch, monkeypatch
):
    from .test_api import launch

    created = launch(client, polygon(client, geometry)).data

    def fetch(*args, progress, **kwargs):
        progress(1, 2)
        Job.objects.filter(pk=created["job_id"]).update(cancel_requested=True)
        progress(2, 2)
        pytest.fail("Cancellation must interrupt collection")

    monkeypatch.setattr(tasks, "fetch_satellite", fetch)
    tasks.execute_job(created["job_id"])
    job = Job.objects.get(pk=created["job_id"])
    assert job.state == "cancelled" and job.progress == 0.4
    assert not AnalysisRun.objects.get(pk=created["run_id"]).points.exists()
