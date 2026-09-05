import numpy as np
import pandas as pd
import pytest
from terralens_ml.candidates import residual_features, sensor_dynamics_features
from terralens_ml.io import DYNAMIC, DataError
from terralens_ml.model import checked_config, fit, load_model, reconstruct, save_model


def context():
    dates = pd.date_range("2023-04-01", periods=36, freq="3D")
    frames = []
    for i, crop in enumerate(["пшеница", "подсолнечник", "пастбище", "зерновые"]):
        values = 0.3 + i * 0.07 + 0.1 * np.sin(np.arange(len(dates)) / 6)
        frames.append(
            pd.DataFrame(
                {
                    "anon_polygon_id": f"A{i}",
                    "date": dates.strftime("%Y-%m-%d"),
                    "crop_type": crop,
                    "primary_ndvi": values,
                    "s2_ndvi": values - 0.02,
                    "landsat_ndvi": values + 0.05,
                }
            )
        )
    frame = pd.concat(frames, ignore_index=True)
    for column in DYNAMIC:
        if column not in frame:
            frame[column] = np.nan
    frame.index = frame.index * 7 + 10
    return frame


def test_sensor_neighbors_are_directional_and_use_calendar_distances():
    days = np.array([0, 2, 5, 9, 40, 100])
    values = np.array([0.2, 0.3, np.nan, 0.6, 0.7, 0.8])
    primary = values + 0.1
    result = sensor_dynamics_features(days, values, primary, np.full(6, 0.4))
    assert result["left_days"][2] == 3
    assert result["right_days"][2] == 4
    assert result["left_value"][2] == 0.3
    assert result["right_value"][2] == 0.6
    assert result["slope"][2] == pytest.approx(0.3 / 7)
    assert result["primary_bias"][2] == pytest.approx(0.1)
    assert result["paired_count"][2] == 4
    assert result["adjusted_estimate"][2] == pytest.approx(0.5)
    assert np.isnan(result["left_value"][0])
    assert np.isnan(result["right_value"][-1])
    assert np.isnan(result["primary_bias"][-1])  # Only two visible pairs in ±60 days.
    assert np.isnan(result["slope"][-1])
    empty = sensor_dynamics_features(days, np.full(6, np.nan), primary, np.full(6, np.nan))
    assert (empty["paired_count"] == 0).all()
    assert np.isnan(empty["adjusted_estimate"]).all()


@pytest.mark.parametrize(
    "crop,dynamics,transitions,feature_count",
    [(True, False, False, 55), (False, True, False, 78), (True, True, False, 79), (False, True, True, 85)],
)
def test_new_features_are_mask_invariant_and_support_unseen_crops_and_json(
    tmp_path, crop, dynamics, transitions, feature_count
):
    frame = context()
    config = {
        "algorithm": "catboost_residual",
        "use_weather": False,
        "local_features": True,
        "context_quality": True,
        "crop_features": crop,
        "sensor_dynamics": dynamics,
        "transition_features": transitions,
        "boost_iterations": 12,
        "training_repeats": 1,
        "masked_training_priors": True,
        "ensemble_seeds": [42, 107],
    }
    model = fit(frame, config)
    assert len(model["feature_names"]) == feature_count
    assert model["schema_version"] == (4 if transitions else 3)
    if crop:
        assert model["boosting"]["features_info"]["categorical_features"][0]["feature_id"] == "crop_type"
    query = frame.copy()
    query["is_synthetic_gap"] = np.arange(len(frame)) % 4 == 1
    expected = reconstruct(query, model=model)
    changed = query.copy()
    changed.loc[query.is_synthetic_gap, DYNAMIC] = 999.0
    pd.testing.assert_frame_equal(expected, reconstruct(changed, model=model))
    shuffled = reconstruct(query.sample(frac=1, random_state=3), model=model).reindex(query.index)
    pd.testing.assert_frame_equal(expected, shuffled)
    save_model(model, tmp_path)
    restored, _ = load_model(tmp_path / "manifest.json")
    pd.testing.assert_frame_equal(expected, reconstruct(query, model=restored))
    for category in [None, "неизвестная новая культура"]:
        unseen = query.assign(crop_type=category)
        actual = reconstruct(unseen, model=restored)
        assert np.isfinite(actual.reconstructed).all()
        observed = ~query.is_synthetic_gap
        np.testing.assert_array_equal(
            actual.loc[observed, "reconstructed"], query.loc[observed, "primary_ndvi"]
        )
    model["schema_version"] = 3 if transitions else 2
    save_model(model, tmp_path)
    with pytest.raises(DataError, match=f"версия артефакта {4 if transitions else 3}"):
        load_model(tmp_path / "manifest.json")


def test_sensor_features_do_not_cross_fields_seasons_or_crop_changes():
    frame = context().iloc[:12].copy()
    frame.loc[frame.index[7:], "crop_type"] = "barley"
    frame["is_synthetic_gap"] = False
    frame.loc[frame.index[6], "is_synthetic_gap"] = True
    config = checked_config({"algorithm": "neighbor_mean", "sensor_dynamics": True, "use_weather": False})
    model = fit(frame, config)
    expected = residual_features(reconstruct(frame, model=model), config).iloc[:7]
    assert np.isnan(expected.iloc[-1].s2_ndvi_right_value)
    changed = frame.copy()
    changed.loc[changed.index[7:], ["primary_ndvi", "s2_ndvi", "landsat_ndvi"]] = -0.9
    others = pd.concat(
        [
            changed.assign(anon_polygon_id="another-field").set_axis(changed.index + 10000),
            changed.assign(date=pd.to_datetime(changed.date) + pd.DateOffset(years=1)).set_axis(
                changed.index + 20000
            ),
        ]
    )
    actual = residual_features(reconstruct(pd.concat([changed, others]), model=model), config).iloc[:7]
    pd.testing.assert_frame_equal(expected, actual)


@pytest.mark.parametrize(
    "config",
    [
        {"crop_features": 1},
        {"sensor_dynamics": "true"},
        {"sensor_dynamics": True, "use_sensors": False},
        {"transition_features": "true"},
        {"transition_features": True, "local_features": False},
    ],
)
def test_invalid_feature_flags_fail_cleanly(config):
    with pytest.raises(DataError):
        checked_config(config)


def test_transition_projections_and_pchip_do_not_extrapolate():
    from terralens_ml.candidates import local_shape_features

    features = local_shape_features(
        np.array([0, 1, 3, 7, 11, 21, 25]),
        np.array([np.nan, 0.1, 0.2, np.nan, 0.6, 0.9, np.nan]),
        transitions=True,
    )
    assert features["left_projected"][3] == pytest.approx(0.4)
    assert features["right_projected"][3] == pytest.approx(0.48)
    assert features["projection_gap"][3] == pytest.approx(0.08)
    assert features["slope_change"][3] == pytest.approx(-0.02)
    assert 0.2 <= features["pchip_estimate"][3] <= 0.6
    assert np.isnan(features["pchip_estimate"][[0, -1]]).all()
    empty = local_shape_features(np.array([1, 2]), np.array([0.3, np.nan]), transitions=True)
    assert np.isnan(empty["pchip_estimate"]).all()
