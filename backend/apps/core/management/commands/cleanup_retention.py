import json

from django.core.management.base import BaseCommand
from services.retention import cleanup_retention


class Command(BaseCommand):
    help = "Удалить истёкшие гостевые данные и непривязанные старые артефакты"

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(cleanup_retention(), ensure_ascii=False))
