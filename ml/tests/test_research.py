import json

import numpy as np
import pandas as pd
import pytest
from terralens_ml.candidates import local_shape_features, residual_features, training_masks
from terralens_ml.io import DataError, mask_context
from terralens_ml.model import checked_config, fit, load_model, predict_submission, reconstruct, save_model
from terralens_ml.uncertainty import calibrate, coverage


def seasonal_series():
    dates = pd.date_range("2019-05-01", "2023-07-31")
    dates = dates[(dates.month >= 5) & (dates.month <= 7)][::3]
    values = 0.5 + 0.2 * np.sin(dates.dayofyear / 30)
    return pd.DataFrame(
        {
            "anon_polygon_id": "A",
            "date": dates.strftime("%Y-%m-%d"),
            "crop_type": "wheat",
            "primary_ndvi": values,
            "s2_ndvi": values,
            "era5_temp_c": 20 + np.sin(dates.dayofyear),
            "era5_precip_mm": 2.0,
        }
    )


@pytest.mark.parametrize(
    "config",
    [
        {"boost_iterations": 0},
        {"boost_iterations": True},
        {"seed": -1},
        {"seed": "42"},
        {"max_gap_days": np.nan},
        {"max_edge_days": None},
        {"training_repeats": 11},
        {"season_start_month": False},
        {"smoothing_strength": "20"},
    ],
)
def test_invalid_numeric_configuration_fails_before_training(config):
    with pytest.raises(DataError):
        checked_config(config)


@pytest.mark.parametrize(
    "config",
    [
        {"algorithm": "robust_smoother"},
        {"algorithm": "history_residual"},
        {"algorithm": "catboost_residual"},
        {
            "algorithm": "catboost_residual",
            "local_features": True,
            "training_repeats": 2,
            "training_blocks": True,
            "masked_training_priors": True,
            "residual_base": "linear",
        },
    ],
)
def test_candidates_ignore_hidden_values_and_other_fields(config):
    frame = seasonal_series()
    model = fit(frame.assign(anon_polygon_id="training"), config | {"boost_iterations": 10})
    frame["is_synthetic_gap"] = np.arange(len(frame)) % 7 == 0
    expected = reconstruct(frame, model=model)
    changed = frame.copy()
    changed.loc[changed.is_synthetic_gap, ["primary_ndvi", "s2_ndvi", "era5_temp_c"]] = 0.987
    actual = reconstruct(changed, model=model)
    pd.testing.assert_frame_equal(expected, actual)
    combined = pd.concat(
        [frame, frame.assign(anon_polygon_id="unrelated", primary_ndvi=0.99)], ignore_index=True
    )
    np.testing.assert_allclose(
        reconstruct(combined, model=model).reconstructed.iloc[: len(frame)], expected.reconstructed
    )
    visible = ~frame.is_synthetic_gap
    np.testing.assert_array_equal(expected.loc[visible, "reconstructed"], frame.loc[visible, "primary_ndvi"])


def test_local_shape_uses_calendar_distances_and_keeps_absent_support_missing():
    features = local_shape_features(np.array([1, 3, 7, 11, 21]), np.array([0.1, 0.2, np.nan, 0.6, 0.9]))
    assert features["left_1_days"][2] == 4
    assert features["right_1_days"][2] == 4
    assert features["left_slope"][2] == pytest.approx(0.05)
    assert features["right_slope"][2] == pytest.approx(0.03)
    assert features["linear_estimate"][2] == pytest.approx(0.4)
    assert features["window_14_count"][2] == 4
    assert features["window_14_mean"][2] == pytest.approx(0.45)
    empty = local_shape_features(np.array([1, 3]), np.array([np.nan, np.nan]))
    assert np.isnan(empty["left_1_value"]).all()
    assert np.isnan(empty["window_14_mean"]).all()
    assert (empty["window_14_count"] == 0).all()


def test_new_features_respect_noncalendar_season_and_input_order():
    frame = seasonal_series().iloc[:5].copy()
    frame["date"] = ["2023-09-29", "2023-09-30", "2023-10-01", "2023-10-02", "2023-10-04"]
    frame["primary_ndvi"] = [0.1, np.nan, np.nan, np.nan, 0.7]
    config = {"local_features": True, "season_start_month": 10}
    model = fit(seasonal_series(), config)
    features = residual_features(reconstruct(frame, model=model), model["config"])
    assert np.isnan(features.loc[1, "right_1_value"])
    assert np.isnan(features.loc[2, "left_1_value"])
    assert features.loc[2, "right_1_days"] == 3
    shuffled = frame.sample(frac=1, random_state=73)
    expected = reconstruct(frame, model=model).sort_index()
    pd.testing.assert_frame_equal(expected, reconstruct(shuffled, model=model).sort_index())


def test_training_masks_repeat_deterministically_without_using_invalid_targets():
    frame = seasonal_series()
    frame.loc[::5, "primary_ndvi"] = np.nan
    valid = frame.primary_ndvi.notna()
    config = {"seed": 42, "training_repeats": 3, "training_blocks": True, "season_start_month": 10}
    first = list(training_masks(frame, valid, config))
    second = list(training_masks(frame, valid, config))
    assert len(first) == 6
    for mask, repeated in zip(first, second, strict=True):
        assert mask.any()
        assert not (mask & ~valid).any()
        pd.testing.assert_series_equal(mask, repeated)
    assert not first[0].equals(first[2])


def test_weather_sensor_features_respect_masks_calendar_and_season():
    frame = seasonal_series().iloc[:3].copy()
    frame["date"] = ["2023-12-01", "2023-12-25", "2024-01-01"]
    frame.loc[1:, ["primary_ndvi", "s2_ndvi", "era5_temp_c", "era5_precip_mm"]] = np.nan
    model = fit(seasonal_series())
    result = reconstruct(frame, model=model)
    features = residual_features(result, model["config"])
    assert features.loc[1:, ["s2_ndvi", "era5_temp_c"]].isna().all().all()
    assert not any("polygon" in column or "climatology" in column for column in features)


def test_catboost_native_json_round_trip(tmp_path):
    frame = seasonal_series()
    model = fit(frame, {"algorithm": "catboost_residual", "boost_iterations": 10})
    frame = mask_context(frame, pd.Series(np.arange(len(frame)) % 5 == 0))
    expected = reconstruct(frame, model=model)
    save_model(model, tmp_path)
    loaded, _ = load_model(tmp_path / "manifest.json")
    pd.testing.assert_frame_equal(expected, reconstruct(frame, model=loaded))
    assert "oblivious_trees" in json.loads((tmp_path / "model.json").read_text())["boosting"]


def test_explicit_reference_history_preserves_synthetic_mask():
    training = seasonal_series()
    model = fit(training)
    test = training.iloc[1:2].copy()
    test["is_synthetic_gap"] = True
    history = training.iloc[[0, 2]].copy()
    history["is_synthetic_gap"] = [True, False]
    before, _ = predict_submission(test, model, history)
    history.iloc[0, history.columns.get_loc("primary_ndvi")] = 0.99
    after, _ = predict_submission(test, model, history)
    pd.testing.assert_frame_equal(before, after)


def test_empirical_intervals_separate_residuals_and_domain():
    predictions = pd.DataFrame(
        {
            "truth": [0.1, 0.2, 0.4, 0.7],
            "reconstructed": [0.2] * 4,
            "gap_days": [8, 8, 40, 100],
            "origin": ["interpolated", "interpolated", "interpolated", "climatology_fallback"],
        }
    )
    calibration = calibrate(predictions, level=0.75, minimum_group=2)
    assert calibration["groups"]["prior"]["pooled_fallback"]
    assert coverage(predictions, calibration)["coverage"] >= 0.75
    model = fit(seasonal_series())
    model["calibration"] = calibration
    frame = seasonal_series().iloc[:3].copy()
    frame.loc[1, "primary_ndvi"] = np.nan
    result = reconstruct(frame, {"interval_domain": "live"}, model)
    assert result.prediction_interval.iloc[0]["method"] == "not_calibrated"
    assert result.prediction_interval.iloc[1]["method"] == "empirical_residual_domain_shift"
    assert "domain_shift" in result.quality_flags.iloc[1]
    assert result.prediction_interval.iloc[1]["upper"] > result.prediction_interval.iloc[1]["lower"]
    with pytest.raises(DataError):
        calibrate(predictions.iloc[:0])


def test_checked_final_split_and_artifact_exclude_inspected_holdout():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    manifest = root / "ml/artifacts/final/manifest.json"
    if not manifest.exists():
        pytest.skip("Final research artifact has not been generated")
    model, _ = load_model(manifest)
    scope = model["training_scope"]
    groups = [
        set(scope[name])
        for name in [
            "polygon_ids",
            "calibration_ids",
            "assessment_ids",
            "excluded_previously_inspected_holdout",
        ]
    ]
    for i, group in enumerate(groups):
        assert all(not group & other for other in groups[i + 1 :])
