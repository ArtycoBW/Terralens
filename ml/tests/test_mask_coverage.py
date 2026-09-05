import numpy as np
import pandas as pd
import pytest
from terralens_ml.candidates import residual_features, training_masks
from terralens_ml.io import DataError
from terralens_ml.model import checked_config, fit, load_model, reconstruct, save_model


def context():
    dates = pd.date_range("2023-04-01", periods=45, freq="3D")
    values = 0.4 + 0.2 * np.sin(np.arange(len(dates)) / 7)
    frame = pd.DataFrame(
        {
            "anon_polygon_id": "A",
            "date": dates.strftime("%Y-%m-%d"),
            "crop_type": "wheat",
            "primary_ndvi": values,
            "s2_ndvi": values,
            "landsat_ndvi": values + 0.05,
        }
    )
    frame.index = np.arange(len(frame)) * 7 + 10
    return frame


def test_cover_masks_hide_each_target_once_per_cycle_and_never_invalid_targets():
    frame = context()
    frame.loc[frame.index[::7], "primary_ndvi"] = np.nan
    frame = pd.concat([frame, frame.assign(anon_polygon_id="B").set_axis(frame.index + 1000)])
    config = checked_config({"cover_training_targets": True, "training_repeats": 10, "training_blocks": True})
    valid = frame.primary_ndvi.notna()
    masks = list(training_masks(frame, valid, config))
    assert len(masks) == 20
    for cycle in [masks[:10:2], masks[10::2]]:
        np.testing.assert_array_equal(sum(cycle), valid.astype(int))
    for first, second in zip(masks, training_masks(frame, valid, config), strict=True):
        pd.testing.assert_series_equal(first, second)
        assert not (first & ~valid).any()
    other_seed = list(training_masks(frame, valid, config | {"seed": 107}))
    assert not masks[0].equals(other_seed[0])


def test_sensor_quality_features_use_masked_context_and_survive_json_roundtrip(tmp_path):
    frame = context()
    config = {
        "algorithm": "catboost_residual",
        "local_features": True,
        "context_quality": True,
        "cover_training_targets": True,
        "training_repeats": 5,
        "training_blocks": True,
        "masked_training_priors": True,
        "boost_iterations": 10,
        "boost_depth": 5,
        "boost_l2": 20,
    }
    model = fit(frame.assign(anon_polygon_id="training"), config)
    assert model["training_unique_targets"] == len(frame)
    frame["is_synthetic_gap"] = np.arange(len(frame)) % 5 == 2
    expected = reconstruct(frame, model=model)
    features = residual_features(expected, model["config"])
    hidden = frame.is_synthetic_gap
    assert (features.loc[hidden, "s2_ndvi_age"] == 3).all()
    np.testing.assert_allclose(features.loc[hidden, "sensor_range"], 0.05)
    assert (features.loc[hidden, "sensor_count"] == 2).all()
    assert features.modis_ndvi_age.isna().all()
    changed = frame.copy()
    changed.loc[hidden, ["primary_ndvi", "s2_ndvi", "landsat_ndvi"]] = 0.99
    pd.testing.assert_frame_equal(expected, reconstruct(changed, model=model))
    actual = reconstruct(frame.sample(frac=1, random_state=4), model=model).reindex(frame.index)
    pd.testing.assert_frame_equal(expected, actual)
    save_model(model, tmp_path)
    restored, _ = load_model(tmp_path / "manifest.json")
    pd.testing.assert_frame_equal(expected, reconstruct(frame, model=restored))


def test_seed_ensemble_averages_independent_predictions_and_validates_members(tmp_path):
    frame = context()
    config = {
        "algorithm": "catboost_residual",
        "local_features": True,
        "context_quality": True,
        "cover_training_targets": True,
        "training_repeats": 5,
        "training_blocks": True,
        "masked_training_priors": True,
        "boost_iterations": 8,
    }
    ensemble = fit(frame, config | {"ensemble_seeds": [42, 107]})
    single = [fit(frame, config | {"seed": seed}) for seed in [42, 107]]
    assert ensemble["training_examples"] == sum(m["training_examples"] for m in single)
    frame["is_synthetic_gap"] = np.arange(len(frame)) % 4 == 1
    actual = reconstruct(frame, model=ensemble)
    expected = np.mean([reconstruct(frame, model=m).reconstructed for m in single], axis=0)
    np.testing.assert_allclose(actual.reconstructed, expected, atol=1e-14, rtol=0)
    manifest = save_model(ensemble, tmp_path)
    assert ensemble["schema_version"] == manifest["schema_version"] == 2
    restored, _ = load_model(tmp_path / "manifest.json")
    pd.testing.assert_frame_equal(actual, reconstruct(frame, model=restored))
    ensemble["schema_version"] = 1
    save_model(ensemble, tmp_path)
    with pytest.raises(DataError, match="версия артефакта 2"):
        load_model(tmp_path / "manifest.json")
    ensemble["schema_version"] = 2
    ensemble["boosting_members"] = []
    save_model(ensemble, tmp_path)
    with pytest.raises(DataError, match="ансамбля"):
        load_model(tmp_path / "manifest.json")


@pytest.mark.parametrize(
    "config",
    [
        {"cover_training_targets": True, "training_repeats": 4},
        {"cover_training_targets": "true"},
        {"context_quality": 1},
        {"boost_depth": 0},
        {"boost_depth": True},
        {"boost_l2": np.nan},
        {"boost_l2": -1},
        {"ensemble_seeds": [42]},
        {"ensemble_seeds": [42, 42]},
        {"ensemble_seeds": [42, True]},
        {"ensemble_seeds": "42,107"},
    ],
)
def test_invalid_coverage_and_booster_parameters_fail_cleanly(config):
    with pytest.raises(DataError):
        checked_config(config)
