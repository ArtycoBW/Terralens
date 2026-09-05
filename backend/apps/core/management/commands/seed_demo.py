import json
from datetime import timedelta
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from services.geometry import validate_geometry

from apps.core.models import Polygon, PolygonVersion, Workspace


class Command(BaseCommand):
    help = "Загрузить датированный реальный OSM-контур для CLI-демонстрации"

    def handle(self, *args, **options):
        path = Path(__file__).resolve().parents[4] / "tests/fixtures/potsdam.geojson"
        source = json.loads(path.read_text())
        geometry, area, digest = validate_geometry(source["geometry"])
        with transaction.atomic():
            workspace = Workspace.objects.create(expires_at=timezone.now() + timedelta(days=7))
            polygon = Polygon.objects.create(
                workspace=workspace,
                name=source["properties"]["name"],
                source="osm",
                source_ref=source["properties"]["source_ref"],
            )
            PolygonVersion.objects.create(
                polygon=polygon, version=1, geometry=geometry, area_ha=area, geometry_hash=digest
            )
        self.stdout.write(
            json.dumps(
                {
                    "workspace_id": str(workspace.id),
                    "polygon_id": str(polygon.id),
                    "source_ref": polygon.source_ref,
                    "note": "Создан реальный контур; новый спутниковый сбор запускается отдельно",
                },
                ensure_ascii=False,
            )
        )
