import json
import uuid
from pathlib import Path

import pandas as pd
import pytest
from apps.core.models import ModelVersion
from rest_framework.test import APIClient
from terralens_ml.io import sha256
from terralens_ml.model import fit, save_model


@pytest.fixture
def recorded():
    return json.loads((Path(__file__).parent / "fixtures" / "potsdam_observations.json").read_text())


@pytest.fixture
def geometry():
    return json.loads((Path(__file__).parent / "fixtures" / "potsdam.geojson").read_text())["geometry"]


@pytest.fixture
def client_factory():
    def create():
        client = APIClient(enforce_csrf_checks=True)
        client.defaults["REMOTE_ADDR"] = str(uuid.uuid4())
        response = client.post("/api/v1/session", {}, format="json", HTTP_ORIGIN="http://testserver")
        assert response.status_code == 200, response.data
        client.credentials(HTTP_X_CSRFTOKEN=response.data["csrf_token"])
        return client

    return create


@pytest.fixture
def client(client_factory):
    return client_factory()


@pytest.fixture
def active_model(tmp_path, settings):
    settings.ARTIFACT_ROOT = tmp_path
    frame = pd.DataFrame(
        {
            "anon_polygon_id": ["A", "A"],
            "date": ["2024-06-01", "2024-06-10"],
            "crop_type": ["unknown", "unknown"],
            "primary_ndvi": [0.2, 0.8],
        }
    )
    manifest = save_model(fit(frame), tmp_path / "model")
    path = tmp_path / "model" / "manifest.json"
    return ModelVersion.objects.create(
        model_id=manifest["model_id"],
        manifest=manifest,
        manifest_path=str(path),
        artifact_hash=sha256(path),
        active=True,
    )


@pytest.fixture
def no_dispatch(monkeypatch):
    monkeypatch.setattr("services.jobs.dispatch", lambda *args: None)


@pytest.fixture
def providers(monkeypatch, recorded):
    from providers.base import snapshot

    monkeypatch.setattr(
        "apps.core.tasks.fetch_satellite",
        lambda *args, **kwargs: (
            recorded["observations"],
            snapshot("earth_search", {"fixture": True}, {"observations": recorded["observations"]}),
        ),
    )
    monkeypatch.setattr(
        "apps.core.tasks.fetch_weather",
        lambda *args: (recorded["weather"], snapshot("open_meteo_era5_land", {"fixture": True}, {})),
    )
