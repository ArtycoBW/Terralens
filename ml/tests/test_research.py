import json

import numpy as np
import pandas as pd
import pytest
from terralens_ml.candidates import residual_features
from terralens_ml.io import DataError, mask_context
from terralens_ml.model import fit, load_model, predict_submission, reconstruct, save_model
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


@pytest.mark.parametrize("algorithm", ["robust_smoother", "history_residual", "catboost_residual"])
def test_candidates_ignore_hidden_values_and_other_fields(algorithm):
    frame = seasonal_series()
    model = fit(frame.assign(anon_polygon_id="training"), {"algorithm": algorithm, "boost_iterations": 10})
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
