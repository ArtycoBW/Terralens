from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from terralens_ml.io import DataError, atomic_write, sha256
from terralens_ml.model import load_model

from apps.core.models import ModelVersion


class Command(BaseCommand):
    help = "Проверить и активировать локальный ML-артефакт"

    def add_arguments(self, parser):
        parser.add_argument("--manifest", default=str(settings.ACTIVE_MODEL_MANIFEST))

    def handle(self, *args, **options):
        path = Path(options["manifest"]).resolve()
        try:
            _, manifest = load_model(path)
        except DataError as exc:
            raise CommandError(str(exc)) from exc
        digest = sha256(path)
        destination = settings.ARTIFACT_ROOT / "models" / digest
        # В registry сохраняется собственная неизменяемая копия, а не путь к рабочему checkpoint.
        for filename in ["model.json", "manifest.json"]:
            source = path if filename == "manifest.json" else path.parent / filename
            target = destination / filename
            if not target.exists():
                atomic_write(target, source.read_bytes())
        load_model(destination / "manifest.json")
        if sha256(destination / "manifest.json") != digest:
            raise CommandError("Контрольная сумма сохранённого manifest не совпадает")
        with transaction.atomic():
            # Сериализуем переключение, в том числе когда registry ещё пуст.
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [1414286674])
            existing = ModelVersion.objects.filter(model_id=manifest["model_id"]).first()
            if existing and existing.artifact_hash != digest:
                raise CommandError(
                    "Этот model_id уже зарегистрирован с другим manifest; создайте новую версию"
                )
            ModelVersion.objects.filter(active=True).update(active=False)
            model, _ = ModelVersion.objects.update_or_create(
                model_id=manifest["model_id"],
                defaults={
                    "artifact_hash": digest,
                    "manifest_path": str(destination / "manifest.json"),
                    "manifest": manifest,
                    "active": True,
                },
            )
        self.stdout.write(f"Активная модель: {model.model_id}")
