import importlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from terralens_ml.io import DataError


@pytest.fixture
def experiment(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    return importlib.import_module("train_expanded_model")


def test_expanded_partition_excludes_all_years_of_calibration_and_validation(experiment):
    frame = pd.DataFrame(
        {
            "anon_polygon_id": ["train", "train", "calibration", "calibration", "validation", "validation"],
            "date": ["2023-06-01", "2024-06-01"] * 3,
        }
    )
    selected = experiment.partitions(frame, {"calibration_ids": ["calibration"]}, ["validation"])
    assert selected.anon_polygon_id.tolist() == ["train", "train"]
    assert selected.date.tolist() == ["2023-06-01", "2024-06-01"]


def test_external_truth_requires_exact_keys_and_finite_answers(experiment):
    test = pd.DataFrame(
        {
            "anon_polygon_id": ["new"] * 3,
            "date": ["2024-06-01", "2024-06-02", "2024-06-03"],
            "is_synthetic_gap": [True, False, True],
        }
    )
    labels = pd.DataFrame(
        {
            "date": ["2024-06-03", "2024-06-01"],
            "primary_ndvi_true": [0.3, 0.5],
            "anon_polygon_id": ["new", "new"],
        }
    )
    assert experiment.align_truth(test, labels).truth.tolist() == [0.3, 0.5]
    for changed in [
        labels.iloc[:1],
        pd.concat([labels, labels.iloc[:1]]),
        labels.assign(primary_ndvi_true=np.nan),
        labels.assign(anon_polygon_id="old"),
    ]:
        with pytest.raises(DataError):
            experiment.align_truth(test, changed)


def test_frozen_plan_rejects_later_input_or_parameter_changes(experiment, tmp_path):
    path = tmp_path / "plan.json"
    plan = {"model_config": {"boost_depth": 5}, "labels_sha256": "original"}
    experiment.freeze(path, plan)
    experiment.freeze(path, plan)
    with pytest.raises(DataError, match="План уже зафиксирован"):
        experiment.freeze(path, plan | {"labels_sha256": "changed"})
    with pytest.raises(DataError, match="План уже зафиксирован"):
        experiment.freeze(path, plan | {"model_config": {"boost_depth": 6}})
