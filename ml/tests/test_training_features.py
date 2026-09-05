"""Регрессии обучения residual-модели на скрытом локальном контексте."""

import numpy as np
import pandas as pd
import pytest
from terralens_ml import model as model_module
from terralens_ml.candidates import field_season_segments, residual_features
from terralens_ml.io import mask_context


def sample(values, dates=None):
    return pd.DataFrame(
        {
            "anon_polygon_id": "training-field",
            "date": dates or pd.date_range("2023-06-01", periods=len(values)).strftime("%Y-%m-%d"),
            "crop_type": "озимая пшеница",
            "primary_ndvi": values,
            "s2_ndvi": values,
            "era5_temp_c": 20.0,
            "era5_precip_mm": 1.0,
        }
    )


def test_internal_mask_excludes_labels_from_local_features_and_training_priors(monkeypatch):
    frame = sample([0.9, 0.9, 0.9, 0.9, 0.4, 0.6])
    frame.index = [4, 5, 9, 13, 20, 21]
    mask = pd.Series([True, True, True, True, False, False], index=frame.index)
    captured = []

    monkeypatch.setattr(model_module, "training_masks", lambda *args: iter([mask]))

    def capture(features, labels, config):
        captured.append((features.copy(deep=True), labels.copy(deep=True)))
        return {"test_stub": "zero_correction"}

    monkeypatch.setattr(model_module, "train_booster", capture)
    config = {
        "algorithm": "catboost_residual",
        "local_features": True,
        "masked_training_priors": True,
        "max_edge_days": 0,
    }
    model_module.fit(frame, config)
    changed = frame.copy(deep=True)
    changed.loc[mask, ["primary_ndvi", "s2_ndvi", "era5_temp_c", "era5_precip_mm"]] = 0.1
    model_module.fit(changed, config)

    original_features, original_labels = captured[0]
    changed_features, changed_labels = captured[1]
    pd.testing.assert_frame_equal(original_features, changed_features)
    # Все скрытые строки находятся вне разрешённого края: base берётся из двух видимых целей.
    np.testing.assert_allclose(original_features["base"], 0.5)
    np.testing.assert_allclose(original_labels - changed_labels, 0.8)


@pytest.mark.parametrize("values", [[None, None, None], [None, 0.4, None]])
def test_rich_reconstruction_handles_empty_or_single_observation_context(monkeypatch, values):
    monkeypatch.setattr(model_module, "train_booster", lambda *args: {"test_stub": "zero_correction"})
    monkeypatch.setattr(model_module, "predict_booster", lambda model, features: np.zeros(len(features)))
    model = model_module.fit(
        sample([0.2, 0.4, 0.8]), {"algorithm": "catboost_residual", "local_features": True}
    )
    frame = sample(values).assign(anon_polygon_id="new-field")
    result = model_module.reconstruct(frame, model=model)
    features = residual_features(result, model["config"])

    assert np.isfinite(result.reconstructed.to_numpy()).all()
    assert not np.isinf(features.to_numpy(dtype=float)).any()
    assert features["left_2_value"].isna().all()
    assert features["right_2_value"].isna().all()
    assert (features["window_14_count"] == frame.primary_ndvi.notna().sum()).all()
    observed = frame.primary_ndvi.notna()
    np.testing.assert_array_equal(result.loc[observed, "reconstructed"], frame.loc[observed, "primary_ndvi"])


def test_linear_residual_base_matches_training_and_inference(monkeypatch):
    frame = sample([0.2, 0.4, 0.8], ["2023-06-01", "2023-06-03", "2023-06-09"])
    mask = pd.Series([False, True, False], index=frame.index)
    captured = []
    monkeypatch.setattr(model_module, "training_masks", lambda *args: iter([mask]))

    def capture(features, labels, config):
        captured.append((features.copy(), labels.copy()))
        return {"test_stub": "zero_correction"}

    monkeypatch.setattr(model_module, "train_booster", capture)
    monkeypatch.setattr(model_module, "predict_booster", lambda model, features: np.zeros(len(features)))
    model = model_module.fit(
        frame,
        {
            "algorithm": "catboost_residual",
            "residual_base": "linear",
            "local_features": True,
            "masked_training_priors": True,
        },
    )
    features, labels = captured[0]
    assert features["base"].iloc[0] == pytest.approx(0.35)
    assert features["linear_estimate"].iloc[0] == pytest.approx(0.35)
    assert labels.iloc[0] == pytest.approx(0.05)
    result = model_module.reconstruct(mask_context(frame, mask), model=model)
    np.testing.assert_allclose(result.reconstructed, [0.2, 0.35, 0.8])


def rotation():
    frame = sample([0.2, None, 0.8, None, 0.6, None, 0.9])
    frame["crop_type"] = ["wheat", "wheat", "maize", "maize", "maize", "wheat", "wheat"]
    frame["era5_temp_c"] = [10.0, np.nan, 30.0, np.nan, 30.0, np.nan, 50.0]
    frame.index = [10, 40, 80, 120, 150, 210, 300]
    return frame


@pytest.mark.parametrize(
    "algorithm",
    ["neighbor_mean", "linear", "pchip", "robust_smoother", "history_residual", "catboost_residual"],
)
def test_reconstruction_separates_returning_crop_and_preserves_input_order(monkeypatch, algorithm):
    monkeypatch.setattr(model_module, "train_booster", lambda *args: {"test_stub": "zero_correction"})
    monkeypatch.setattr(model_module, "predict_booster", lambda model, features: np.zeros(len(features)))
    model = model_module.fit(sample([0.3, 0.5, 0.7]), {"algorithm": algorithm, "local_features": True})
    frame = rotation()
    result = model_module.reconstruct(frame, model=model)
    np.testing.assert_allclose(result.reconstructed, [0.2, 0.2, 0.8, 0.7, 0.6, 0.9, 0.9])
    assert result.origin.loc[[40, 120, 210]].tolist() == ["extrapolated", "interpolated", "extrapolated"]
    shuffled = frame.sample(frac=1, random_state=42)
    actual = model_module.reconstruct(shuffled, model=model)
    assert actual.index.tolist() == shuffled.index.tolist()
    pd.testing.assert_frame_equal(result, actual.reindex(result.index))


def test_local_sensor_weather_features_use_only_current_continuous_crop_segment():
    model = model_module.fit(sample([0.3, 0.5, 0.7]), {"local_features": True})
    frame = rotation()
    result = model_module.reconstruct(frame, model=model)
    features = residual_features(result, model["config"])
    np.testing.assert_allclose(features.loc[[40, 120, 210], "s2_ndvi"], [0.2, 0.7, 0.9])
    np.testing.assert_allclose(features.loc[[40, 120, 210], "era5_temp_c"], [10.0, 30.0, 50.0])
    assert features.loc[[40, 120, 210], "window_60_count"].tolist() == [1, 2, 1]
    assert pd.isna(features.loc[40, "right_1_value"])
    assert pd.isna(features.loc[210, "left_1_value"])
    changed = frame.copy()
    changed.loc[changed.index < 210, ["primary_ndvi", "s2_ndvi", "era5_temp_c"]] = 0.1
    changed_features = residual_features(model_module.reconstruct(changed, model=model), model["config"])
    pd.testing.assert_frame_equal(features.loc[[210, 300]], changed_features.loc[[210, 300]])
    shuffled = frame.sample(frac=1, random_state=73)
    actual = residual_features(model_module.reconstruct(shuffled, model=model), model["config"])
    pd.testing.assert_frame_equal(features, actual.reindex(features.index))


def test_crop_segments_respect_custom_season_and_nullable_cultures():
    frame = sample(
        [0.2] * 6,
        ["2022-09-30", "2022-10-01", "2023-01-01", "2023-02-01", "2023-03-01", "2023-04-01"],
    )
    frame["crop_type"] = ["wheat", "wheat", "wheat", None, np.nan, "wheat"]
    frame.index = [50, 10, 30, 80, 20, 90]
    segments = list(field_season_segments(frame.sample(frac=1, random_state=42), 10))
    assert {tuple(segment.index) for segment in segments} == {(50,), (10, 30), (80, 20), (90,)}
    assert all(pd.to_datetime(segment.date).is_monotonic_increasing for segment in segments)


def test_history_residual_keeps_crop_segment_corrections_separate():
    current = rotation()
    expected = [0.2, 0.2, 0.8, 0.7, 0.6, 0.9, 0.9]
    years = []
    for year in [2020, 2021, 2022]:
        history = current.copy()
        history["date"] = history.date.str.replace("2023", str(year))
        history["primary_ndvi"] = expected
        years.append(history)
    context = pd.concat([*years, current], ignore_index=True)
    model = model_module.fit(sample([0.3, 0.5, 0.7]), {"algorithm": "history_residual"})
    result = model_module.reconstruct(context, model=model)
    np.testing.assert_allclose(result.reconstructed.iloc[-len(current) :], expected)
    assert all("aoi_history" in flags for flags in result.quality_flags.iloc[-len(current) :].iloc[[1, 3, 5]])
