import logging
import threading
from contextlib import contextmanager

from apps.core.errors import DomainError
from apps.core.models import IdempotencyRecord, Job, Workspace
from django.db import close_old_connections, connections, transaction
from django.utils import timezone
from terralens_ml.io import canonical_hash

logger = logging.getLogger(__name__)


@contextmanager
def heartbeat(job_id):
    stopped = threading.Event()

    def update():
        try:
            while not stopped.wait(30):
                close_old_connections()
                if not Job.objects.filter(pk=job_id, state="running").update(heartbeat_at=timezone.now()):
                    return
        except Exception:
            logger.exception("job_heartbeat_failed", extra={"job_id": str(job_id)})
        finally:
            connections.close_all()

    worker = threading.Thread(target=update, name=f"heartbeat-{job_id}", daemon=True)
    worker.start()
    try:
        yield
    finally:
        stopped.set()
        worker.join(timeout=2)


def dispatch(job_id):
    from apps.core.tasks import execute_job

    try:
        execute_job.apply_async(args=[str(job_id)], task_id=str(job_id), retry=False)
        Job.objects.filter(pk=job_id, state="queued").update(dispatched_at=timezone.now())
    except Exception:
        # Job остаётся в БД: периодический reconciler повторит отправку из outbox.
        logger.exception("job_dispatch_failed job_id=%s", job_id)


def idempotent(request, create):
    key = request.headers.get("Idempotency-Key", "")
    if not 1 <= len(key) <= 128 or not key.isascii():
        raise DomainError("idempotency_conflict", "Укажите Idempotency-Key длиной 1–128 ASCII-символов", 400)
    fingerprint = canonical_hash({"path": request.path, "body": request.data})
    with transaction.atomic():
        # Один короткий lock сериализует квоты и ключи внутри гостевого пространства.
        Workspace.objects.select_for_update().get(pk=request.workspace.pk)
        prior = IdempotencyRecord.objects.filter(workspace=request.workspace, key=key).first()
        if prior:
            if prior.request_hash != fingerprint:
                raise DomainError("idempotency_conflict", "Этот ключ уже использован с другим запросом", 409)
            return prior.response | {"reused": True}, 200
        response = create()
        IdempotencyRecord.objects.create(
            workspace=request.workspace, key=key, request_hash=fingerprint, response=response
        )
        return response, 200 if response.get("reused") else 202


def enqueue(workspace, kind, **refs):
    from django.conf import settings

    if (
        Job.objects.filter(workspace=workspace, state__in=["queued", "running"]).count()
        >= settings.MAX_ACTIVE_JOBS
    ):
        raise DomainError("quota_exceeded", "Достигнут лимит активных задач", 429)
    job = Job.objects.create(workspace=workspace, kind=kind, **refs)
    transaction.on_commit(lambda: dispatch(job.id))
    return job


def cancel(job):
    if job.state in ["succeeded", "failed", "cancelled"]:
        return 200
    job.cancel_requested = True
    if job.state == "queued":
        job.state, job.finished_at = "cancelled", timezone.now()
        job.retryable = True
        if job.run_id:
            job.run.state, job.run.completed_at = "cancelled", timezone.now()
            job.run.save(update_fields=["state", "completed_at"])
        if job.discovery_id:
            job.discovery.status = "cancelled"
            job.discovery.save(update_fields=["status"])
        if job.export_id:
            job.export.state = "cancelled"
            job.export.save(update_fields=["state"])
    job.save()
    return 202
