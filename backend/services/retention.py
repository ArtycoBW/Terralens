"""Очистка истёкших гостевых данных с сохранением общих и активных снимков."""

from datetime import timedelta
from pathlib import Path

from apps.core.models import AnalysisRun, CandidatePolygon, Export, Job, SourceSnapshot, Workspace
from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone

from services.jobs import cancel


def remove_artifact(relative):
    root = settings.ARTIFACT_ROOT.resolve()
    path = (root / relative).resolve()
    if path.is_relative_to(root) and path.is_file():
        path.unlink(missing_ok=True)


def export_files(exports):
    return [
        path
        for export in exports
        for path in [export.artifact_path, f"exports/{export.id}.manifest.json"]
        if path
    ]


def cleanup_retention(now=None):
    now = now or timezone.now()
    removed = {"workspaces": 0, "exports": 0, "snapshots": 0, "orphan_files": 0}
    for workspace_id in Workspace.objects.filter(expires_at__lte=now).values_list("id", flat=True):
        with transaction.atomic():
            workspace = (
                Workspace.objects.select_for_update().filter(pk=workspace_id, expires_at__lte=now).first()
            )
            if workspace is None:
                continue
            for job in Job.objects.select_for_update().filter(
                workspace=workspace, state__in=["queued", "running"]
            ):
                cancel(job)
            # Worker должен подтвердить отмену до удаления строк, которыми он владеет.
            if Job.objects.filter(workspace=workspace, state="running").exists():
                continue
            files = export_files(Export.objects.filter(workspace=workspace))
            # PROTECT на старых версиях геометрии требует сначала удалить runs.
            AnalysisRun.objects.filter(workspace=workspace).delete()
            workspace.delete()
            for path in files:
                transaction.on_commit(lambda path=path: remove_artifact(path))
            removed["workspaces"] += 1
    for export_id in Export.objects.filter(expires_at__lte=now).values_list("id", flat=True):
        with transaction.atomic():
            # Совпадает с порядком публикации worker: сначала job, затем export.
            jobs = list(
                Job.objects.select_for_update().filter(export_id=export_id, state__in=["queued", "running"])
            )
            export = Export.objects.select_for_update().filter(pk=export_id).first()
            if export is None:
                continue
            for job in jobs:
                cancel(job)
            if export.jobs.filter(state="running").exists():
                continue
            paths = export_files([export])
            # Оставляем запись истёкшего экспорта, чтобы download продолжал отвечать 410.
            export.artifact_path, export.checksum, export.manifest_checksum = "", "", ""
            export.save(update_fields=["artifact_path", "checksum", "manifest_checksum"])
            for path in paths:
                transaction.on_commit(lambda path=path: remove_artifact(path))
            removed["exports"] += 1
    CandidatePolygon.objects.filter(expires_at__lte=now).delete()
    Session.objects.filter(expire_date__lte=now).delete()
    # Защищаем суточный кеш и снимки незавершённого анализа, ещё не привязанные к run.
    cutoff = now - timedelta(days=max(2, settings.SNAPSHOT_RETENTION_DAYS))
    for snapshot_id in SourceSnapshot.objects.filter(
        created_at__lt=cutoff, analysisrun__isnull=True
    ).values_list("id", flat=True):
        with transaction.atomic():
            snapshot = (
                SourceSnapshot.objects.select_for_update(of=("self",))
                .filter(pk=snapshot_id, analysisrun__isnull=True)
                .first()
            )
            if snapshot is None:
                continue
            relative = snapshot.artifact_path
            snapshot.delete()
            transaction.on_commit(lambda relative=relative: remove_artifact(relative))
            removed["snapshots"] += 1
    referenced = set(SourceSnapshot.objects.values_list("artifact_path", flat=True))
    for export in Export.objects.all().only("id", "artifact_path"):
        referenced.update(export_files([export]))
    orphan_before = (now - timedelta(hours=settings.ARTIFACT_ORPHAN_GRACE_HOURS)).timestamp()
    for directory in ["snapshots", "exports"]:
        for path in (settings.ARTIFACT_ROOT / directory).glob("*"):
            relative = str(Path(directory) / path.name)
            if path.is_file() and relative not in referenced and path.stat().st_mtime < orphan_before:
                remove_artifact(relative)
                removed["orphan_files"] += 1
    return removed
