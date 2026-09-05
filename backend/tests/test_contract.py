import json
from pathlib import Path

import pytest
from apps.core.serializers import (
    DailyPointResponse,
    DailySeries,
    ErrorDetail,
    JobResponse,
    PolygonResponse,
    RunResponse,
)
from apps.core.tasks import execute_job
from drf_spectacular.generators import SchemaGenerator

from .test_api import launch, polygon


def test_committed_schema_matches_implementation():
    root = Path(__file__).resolve().parents[2]
    schema = SchemaGenerator().get_schema(request=None, public=True)
    checked_in = json.loads((root / "docs/openapi.json").read_text())
    # JSON-нормализация учитывает OrderedDict и tuple в генераторе.
    assert json.loads(json.dumps(schema)) == checked_in
    assert len(schema["paths"]) >= 24
    fields = schema["components"]["schemas"]["DailyPointResponse"]["properties"]
    assert fields["reconstructed"]["nullable"] is True


def test_synthetic_fixtures_obey_contract():
    root = Path(__file__).resolve().parents[2]
    for path in (root / "docs/fixtures").glob("*.json"):
        fixture = json.loads(path.read_text())
        assert fixture["metadata"]["synthetic_example"] is True
        for field, serializer in [("series", DailySeries), ("job", JobResponse), ("error", ErrorDetail)]:
            if field in fixture:
                checked = serializer(data=fixture[field])
                assert checked.is_valid(), (path, checked.errors)


@pytest.mark.django_db
def test_actual_responses_obey_contract(client, geometry, active_model, providers, no_dispatch):
    field = polygon(client, geometry)
    checked = PolygonResponse(data=field)
    assert checked.is_valid(), checked.errors
    created = launch(client, field).data
    execute_job(created["job_id"])
    run = client.get(f"/api/v1/analyses/{created['run_id']}").data
    checked = RunResponse(data=run)
    assert checked.is_valid(), checked.errors
    points = client.get(f"/api/v1/analyses/{created['run_id']}/series").data["items"]
    checked = DailyPointResponse(data=points, many=True)
    assert checked.is_valid(), checked.errors
