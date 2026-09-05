"""Артефакт релиза сохраняет контрольные суммы после checkout на Windows."""

import json
from hashlib import sha256
from pathlib import Path


def test_committed_model_matches_signed_manifest():
    directory = Path(__file__).resolve().parents[1] / "artifacts" / "final"
    manifest = json.loads((directory / "manifest.json").read_text())
    for filename, digest in manifest["files"].items():
        assert sha256((directory / filename).read_bytes()).hexdigest() == digest


def test_save_model_without_git_binary(tmp_path, monkeypatch):
    import pandas as pd
    from terralens_ml.model import fit, load_model, save_model

    def missing_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr("terralens_ml.model.subprocess.run", missing_git)
    frame = pd.DataFrame(
        {"anon_polygon_id": ["A"], "date": ["2024-06-01"], "crop_type": ["unknown"], "primary_ndvi": [0.5]}
    )
    manifest = save_model(fit(frame), tmp_path)
    assert manifest["git_revision"] == "unknown"
    assert load_model(tmp_path / "manifest.json")[1]["model_id"] == manifest["model_id"]
