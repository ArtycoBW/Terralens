from pathlib import Path

import pandas as pd
import pytest
from apps.core.models import ModelVersion
from django.core.management import call_command
from terralens_ml.model import fit, load_model, save_model


@pytest.mark.django_db
def test_retraining_does_not_replace_registered_version(active_model):
    source = Path(active_model.manifest_path)
    call_command("register_model", manifest=str(source))
    old = ModelVersion.objects.get(active=True)
    old_model, _ = load_model(old.manifest_path)
    changed = pd.DataFrame(
        {
            "anon_polygon_id": ["A", "A"],
            "date": ["2024-06-01", "2024-06-10"],
            "crop_type": ["unknown", "unknown"],
            "primary_ndvi": [0.7, 0.9],
        }
    )
    save_model(fit(changed), source.parent)
    call_command("register_model", manifest=str(source))
    old.refresh_from_db()
    assert old.active is False
    assert load_model(old.manifest_path)[0] == old_model
    active = ModelVersion.objects.get(active=True)
    assert active.model_id != old.model_id
    assert load_model(active.manifest_path)[0]["global_median"] == 0.8


@pytest.mark.django_db
def test_registry_rejects_replacing_existing_model_id(active_model):
    import json

    from django.core.management.base import CommandError

    source = Path(active_model.manifest_path)
    call_command("register_model", manifest=str(source))
    registered = ModelVersion.objects.get(active=True)
    original_path = registered.manifest_path
    manifest = json.loads(source.read_text())
    manifest["metrics"] = {"tampered": 123}
    source.write_text(json.dumps(manifest))
    with pytest.raises(CommandError, match="другим manifest"):
        call_command("register_model", manifest=str(source))
    registered.refresh_from_db()
    assert registered.active and registered.manifest_path == original_path
    assert registered.manifest.get("metrics") != {"tampered": 123}
