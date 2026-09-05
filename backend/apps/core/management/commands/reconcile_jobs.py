from django.core.management.base import BaseCommand

from apps.core.tasks import reconcile


class Command(BaseCommand):
    help = "Восстановить доставку задач и завершить зависшие запуски"

    def handle(self, *args, **options):
        reconcile()
        self.stdout.write("Проверка очереди завершена")
