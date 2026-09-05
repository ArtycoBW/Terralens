from datetime import timedelta

import pytest
from apps.core.models import AnalysisRun, Export, Job, SourceSnapshot, Workspace
from apps.core.tasks import execute_job
from django.utils import timezone
from services.retention import cleanup_retention

from .test_api import launch, polygon

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_retention_removes_expired_workspace_but_keeps_shared_snapshot(
    client,
    client_factory,
    geometry,
    active_model,
    providers,
    no_dispatch,
    django_capture_on_commit_callbacks,
    settings,
):
    first = launch(client, polygon(client, geometry)).data
    execute_job(first["job_id"])
    other = client_factory()
    accepted = launch(other, polygon(other, geometry)).data
    execute_job(accepted["job_id"])
    first_run = AnalysisRun.objects.get(pk=first["run_id"])
    shared = list(first_run.snapshots.values_list("id", flat=True))
    # Операторский импорт может явно разделить immutable snapshot между runs.
    AnalysisRun.objects.get(pk=accepted["run_id"]).snapshots.add(*shared)
    SourceSnapshot.objects.filter(pk__in=shared).update(created_at=timezone.now() - timedelta(days=90))
    Workspace.objects.filter(pk=first_run.workspace_id).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    with django_capture_on_commit_callbacks(execute=True):
        result = cleanup_retention()
    assert result["workspaces"] == 1
    assert not AnalysisRun.objects.filter(pk=first_run.pk).exists()
    assert SourceSnapshot.objects.filter(pk__in=shared).count() == len(shared)
    assert all(
        (settings.ARTIFACT_ROOT / snapshot.artifact_path).is_file()
        for snapshot in SourceSnapshot.objects.filter(pk__in=shared)
    )


def test_retention_waits_for_running_worker_and_expires_export(
    client,
    geometry,
    active_model,
    providers,
    no_dispatch,
    django_capture_on_commit_callbacks,
    settings,
):
    field = polygon(client, geometry)
    first = launch(client, field).data
    execute_job(first["job_id"])
    created = client.post(
        "/api/v1/exports",
        {"run_id": first["run_id"], "format": "csv"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="retention-export",
    ).data
    execute_job(created["job_id"])
    exported = Export.objects.get(pk=created["export_id"])
    path = settings.ARTIFACT_ROOT / exported.artifact_path
    exported.expires_at = timezone.now() - timedelta(seconds=1)
    exported.save(update_fields=["expires_at"])
    with django_capture_on_commit_callbacks(execute=True):
        cleanup_retention()
    assert not path.exists()
    assert client.get(f"/api/v1/exports/{exported.id}/download").status_code == 410
    running = launch(client, field, key="retention-running").data
    Job.objects.filter(pk=running["job_id"]).update(state="running", heartbeat_at=timezone.now())
    Workspace.objects.filter(pk=field["workspace_id"]).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    cleanup_retention()
    assert Workspace.objects.filter(pk=field["workspace_id"]).exists()
    assert Job.objects.get(pk=running["job_id"]).cancel_requested
    assert client.get("/api/v1/polygons").status_code == 401


def test_retention_deletes_unreferenced_snapshots_without_following_external_path(
    tmp_path,
    settings,
    django_capture_on_commit_callbacks,
):
    settings.ARTIFACT_ROOT = tmp_path / "artifacts"
    root = settings.ARTIFACT_ROOT
    (root / "snapshots").mkdir(parents=True)
    local = root / "snapshots" / "orphan.json"
    local.write_text("{}")
    outside = tmp_path / "must-stay.json"
    outside.write_text("{}")
    for path in ["snapshots/orphan.json", str(outside)]:
        snapshot = SourceSnapshot.objects.create(
            provider="fixture",
            query_hash="q",
            geometry_hash="g",
            status="completed",
            artifact_path=path,
            checksum="c",
            metadata={},
        )
        SourceSnapshot.objects.filter(pk=snapshot.pk).update(created_at=timezone.now() - timedelta(days=90))
    with django_capture_on_commit_callbacks(execute=True):
        result = cleanup_retention()
    assert result["snapshots"] == 2
    assert not local.exists() and outside.exists()
