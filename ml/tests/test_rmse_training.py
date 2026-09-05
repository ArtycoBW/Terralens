import numpy as np
import pandas as pd
import pytest
from terralens_ml.candidates import alignment_features, fit_sensor_alignment, training_masks
from terralens_ml.io import DataError
from terralens_ml.model import (
    checked_config,
    fit,
    load_model,
    reconstruct,
    save_model,
    target_example_weights,
)
from test_mask_coverage import context


def test_seven_point_partitions_cover_targets_without_changing_five_block_masks():
    frame = context()
    valid = frame.primary_ndvi.notna()
    base = checked_config({"cover_training_targets": True, "training_repeats": 5, "training_blocks": True})
    old = list(training_masks(frame, valid, base))
    new = list(
        training_masks(
            frame,
            valid,
            base | {"coverage_partitions": 7, "training_repeats": 7, "training_block_repeats": 5},
        )
    )
    points = new[:10:2] + new[10:]
    assert len(new) == 12
    np.testing.assert_array_equal(sum(points), valid.astype(int))
    assert max(mask.sum() for mask in points) <= np.ceil(valid.sum() / 7)
    for original, changed in zip(old[1::2], new[1:10:2], strict=True):
        pd.testing.assert_series_equal(original, changed)


def test_target_weights_equalize_total_contribution_and_preserve_average_weight():
    ids = np.array([7, 7, 8, 9, 9, 9])
    weights = target_example_weights(ids)
    assert weights.mean() == pytest.approx(1)
    assert pd.Series(weights).groupby(ids).sum().tolist() == pytest.approx([2, 2, 2])


def test_alignment_uses_independent_sensor_pairs_and_shrinks_sparse_estimates():
    frame = pd.DataFrame(
        {
            "anon_polygon_id": ["A"] * 3 + ["B"],
            "s2_ndvi": [0.6] * 4,
            "landsat_ndvi": [0.5] * 3 + [0.3],
            "primary_ndvi": [0.6] * 4,
        }
    )
    alignment = fit_sensor_alignment(frame)
    assert alignment["bias"] == pytest.approx(0.2)  # Equal field weight, not three A votes.
    assert alignment["paired_fields"] == 2
    assert fit_sensor_alignment(frame.assign(primary_ndvi=-0.9)) == alignment
    local = alignment_features(frame.iloc[:3], np.array([0, 1, 80]), alignment, 8)
    assert local["s2_landsat_pair_count"].tolist() == [2, 2, 1]
    assert local["s2_landsat_bias"][0] == pytest.approx(0.18)
    missing = alignment_features(
        frame.iloc[:3].assign(landsat_ndvi=np.nan), np.array([0, 1, 80]), alignment, 8
    )
    assert missing["s2_landsat_pair_count"].tolist() == [0, 0, 0]
    np.testing.assert_allclose(missing["s2_landsat_bias"], 0.2)
    assert np.isnan(missing["s2_landsat_pair_age"]).all()
    assert np.isnan(missing["s2_landsat_pair_mad"]).all()


def test_alignment_training_masks_shuffle_observations_and_schema_roundtrip(tmp_path):
    frame = context()
    config = {
        "algorithm": "catboost_residual",
        "use_weather": False,
        "local_features": True,
        "context_quality": True,
        "sensor_dynamics": True,
        "sensor_alignment": True,
        "normalize_target_weights": True,
        "masked_training_priors": True,
        "boost_iterations": 12,
        "training_repeats": 1,
    }
    model = fit(frame.assign(anon_polygon_id="train"), config)
    assert model["schema_version"] == 5
    assert len(model["feature_names"]) == 84
    query = frame.assign(is_synthetic_gap=np.arange(len(frame)) % 5 == 2)
    expected = reconstruct(query, model=model)
    changed = query.copy()
    changed.loc[changed.is_synthetic_gap, ["primary_ndvi", "s2_ndvi", "landsat_ndvi"]] = -0.9
    pd.testing.assert_frame_equal(expected, reconstruct(changed, model=model))
    shuffled = reconstruct(query.sample(frac=1, random_state=5), model=model).reindex(query.index)
    pd.testing.assert_frame_equal(expected, shuffled)
    observed = ~query.is_synthetic_gap
    np.testing.assert_array_equal(
        expected.loc[observed, "reconstructed"], query.loc[observed, "primary_ndvi"]
    )
    other = query.assign(anon_polygon_id="other", landsat_ndvi=-0.8).set_axis(query.index + 1000)
    isolated = reconstruct(pd.concat([query, other]), model=model).loc[query.index]
    pd.testing.assert_frame_equal(expected, isolated)
    save_model(model, tmp_path)
    loaded, _ = load_model(tmp_path / "manifest.json")
    pd.testing.assert_frame_equal(expected, reconstruct(query, model=loaded))
    model["schema_version"] = 4
    save_model(model, tmp_path)
    with pytest.raises(DataError, match="версия артефакта 5"):
        load_model(tmp_path / "manifest.json")
    model["schema_version"] = 5
    model["sensor_alignment"]["bias"] = 3
    save_model(model, tmp_path)
    with pytest.raises(DataError, match="межсенсорная"):
        load_model(tmp_path / "manifest.json")


@pytest.mark.parametrize(
    "config",
    [
        {"normalize_target_weights": 1},
        {"sensor_alignment": "true"},
        {"sensor_alignment": True, "use_sensors": False},
        {"coverage_partitions": True},
        {"coverage_partitions": 7, "cover_training_targets": True, "training_repeats": 5},
        {"training_repeats": 5, "training_block_repeats": 6},
        {"boost_learning_rate": 0},
        {"boost_learning_rate": np.nan},
        {"alignment_shrinkage": -1},
    ],
)
def test_invalid_training_and_alignment_parameters_fail(config):
    with pytest.raises(DataError):
        checked_config(config)


def test_training_cache_is_exact_reuses_only_booster_changes_and_checks_integrity(tmp_path, monkeypatch):
    import importlib
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    wave = importlib.import_module("train_rmse_wave")
    frame = context()
    valid = frame.primary_ndvi.notna()
    calls = []

    def build(*args):
        calls.append(True)
        return (
            pd.DataFrame({"integer": [1, 2], "missing": [np.nan, 0.5]}),
            pd.Series([0.1, -0.2]),
            np.array([10, 17]),
        )

    cached = wave.feature_cache(tmp_path, build, "source-a")
    first = cached(frame, valid, {"seed": 42, "boost_iterations": 400}, {})
    second = cached(frame, valid, {"seed": 42, "boost_iterations": 800, "normalize_target_weights": True}, {})
    pd.testing.assert_frame_equal(first[0], second[0], check_exact=True)
    pd.testing.assert_series_equal(first[1], second[1], check_exact=True)
    np.testing.assert_array_equal(first[2], second[2])
    assert len(calls) == 1
    cached(frame, valid, {"seed": 42, "sensor_alignment": True}, {})
    assert len(calls) == 2
    for path in tmp_path.glob("*.npz"):
        path.write_bytes(b"corrupt")
    with pytest.raises(DataError, match="cache"):
        cached(frame, valid, {"seed": 42, "boost_iterations": 400}, {})
