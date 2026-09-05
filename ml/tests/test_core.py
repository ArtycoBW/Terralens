import json

import numpy as np
import pandas as pd
import pytest
from terralens_ml.io import (
    DataError,
    mask_context,
    parse_bool,
    read_csv,
    validate_submission,
    write_submission,
)
from terralens_ml.model import fit, load_model, predict_submission, reconstruct, save_model
from terralens_ml.validation import make_mask, metrics


def series(values, dates=None, polygon="A"):
    return pd.DataFrame(
        {
            "anon_polygon_id": polygon,
            "date": dates or [f"2024-06-{i + 1:02}" for i in range(len(values))],
            "crop_type": "пшеница",
            "primary_ndvi": values,
        }
    )


@pytest.fixture
def model():
    return fit(series([0.2, 0.4, 0.8]))


def test_calendar_interpolation_and_m0(model):
    frame = series([0.2, None, 0.8], ["2024-06-01", "2024-06-03", "2024-06-09"])
    assert reconstruct(frame, model=model).reconstructed.tolist() == pytest.approx([0.2, 0.35, 0.8])
    assert reconstruct(frame, {"algorithm": "neighbor_mean"}, model).reconstructed.iloc[1] == 0.5


def test_mask_invariance_hides_all_dynamic_columns(model):
    frame = series([0.2, 0.4, 0.8])
    frame["is_synthetic_gap"] = [False, True, False]
    frame["s2_ndvi"] = frame.primary_ndvi
    frame["era5_temp_c"] = 20.0
    frame["rolling_secret"] = 0.3
    expected = reconstruct(frame, model=model)
    changed = frame.copy()
    changed.loc[1, ["primary_ndvi", "s2_ndvi", "era5_temp_c", "rolling_secret"]] = 999
    actual = reconstruct(changed, model=model)
    pd.testing.assert_frame_equal(expected, actual)
    assert actual.loc[1, "observed_primary"] is np.nan or pd.isna(actual.loc[1, "observed_primary"])


def test_no_cross_aoi_or_season_and_shuffle(model):
    a = series([0.2, None, 0.8])
    b = series([0.9, 0.9, 0.9], polygon="B")
    combined = pd.concat([a, b], ignore_index=True)
    pd.testing.assert_series_equal(
        reconstruct(a, model=model).reconstructed, reconstruct(combined, model=model).reconstructed.iloc[:3]
    )
    shuffled = combined.sample(frac=1, random_state=42)
    pd.testing.assert_series_equal(
        reconstruct(combined, model=model).reconstructed,
        reconstruct(shuffled, model=model).reconstructed.sort_index(),
    )
    boundary = series([0.2, None], ["2023-12-31", "2024-01-01"])
    assert reconstruct(boundary, model=model).origin.iloc[1] == "climatology_fallback"


def test_edge_empty_context_and_long_gap(model):
    assert reconstruct(series([None, 0.8]), model=model).origin.iloc[0] == "extrapolated"
    empty = reconstruct(series([None, None]), model=model)
    assert np.isfinite(empty.reconstructed).all()
    long = reconstruct(series([0.2, None, 0.8], ["2024-01-01", "2024-06-01", "2024-10-01"]), model=model)
    assert long.origin.iloc[1] == "climatology_fallback"
    assert "long_gap" in long.quality_flags.iloc[1]


def test_rejected_observation_preserves_raw(model):
    result = reconstruct(series([0.2, 1.8, 0.8]), model=model)
    assert result.observed_primary.iloc[1] == 1.8
    assert pd.isna(result.clean_primary.iloc[1])
    assert "invalid_value" in result.quality_flags.iloc[1]


@pytest.mark.parametrize("algorithm", ["linear", "neighbor_mean", "pchip"])
def test_leap_dates(algorithm, model):
    frame = series([0.2, None, 0.8], ["2024-02-28", "2024-02-29", "2024-03-01"])
    assert reconstruct(frame, {"algorithm": algorithm}, model).reconstructed.iloc[1] == pytest.approx(0.5)


def test_artifact_integrity(tmp_path, model):
    save_model(model, tmp_path)
    loaded, manifest = load_model(tmp_path / "manifest.json")
    assert loaded == model
    assert manifest["dependency_lock_sha256"]
    (tmp_path / "model.json").write_text(json.dumps(model | {"global_median": 0}))
    with pytest.raises(DataError, match="сумма"):
        load_model(tmp_path / "manifest.json")


def test_submission_mask_order_and_atomicity(tmp_path, model):
    frame = series([0.2, None, None, 0.8])
    frame["is_synthetic_gap"] = [False, True, False, False]
    result, origins = predict_submission(frame, model)
    path = tmp_path / "submission.csv"
    assert write_submission(frame, result, path)["rows"] == 1
    assert sum(origins.values()) == 1
    before = path.read_bytes()
    result.loc[:, "primary_ndvi_pred"] = np.nan
    with pytest.raises(DataError):
        write_submission(frame, result, path)
    assert path.read_bytes() == before
    with pytest.raises(DataError):
        validate_submission(frame, pd.concat([pd.read_csv(path)] * 2))
    frame["is_synthetic_gap"] = False
    result, _ = predict_submission(frame, model)
    assert write_submission(frame, result, path)["rows"] == 0
    assert len(path.read_text().splitlines()) == 1


def test_bool_and_input_validation(tmp_path):
    assert parse_bool(pd.Series(["False", "True", "0", "1"])).tolist() == [False, True, False, True]
    with pytest.raises(DataError):
        parse_bool(pd.Series(["false", "", None]))
    path = tmp_path / "input.csv"
    frame = series([0.2, 0.8])
    frame.loc[1, "date"] = "2024-02-30"
    frame.to_csv(path, index=False)
    with pytest.raises(DataError, match="календарная"):
        read_csv(path)
    frame.loc[1, "date"] = frame.date.iloc[0]
    frame.to_csv(path, index=False)
    with pytest.raises(DataError, match="Повторяется"):
        read_csv(path)


def test_python_api_parses_false_as_false(model):
    frame = series([0.2, None, 0.8])
    frame["is_synthetic_gap"] = ["False", "True", "False"]
    prediction, _ = predict_submission(frame, model)
    assert len(prediction) == 1 and prediction.date.iloc[0] == "2024-06-02"


def test_metrics_keep_raw_targets_and_mask_deterministic():
    frame = series([-0.2, 0.1, 1.8])
    mask = make_mask(frame, 42, 0.5)
    assert mask.equals(make_mask(frame, 42, 0.5))
    assert mask_context(frame, mask).primary_ndvi.loc[mask].isna().all()
    assert metrics([1.8], [0.8])["rmse"] == 1
    for error, score in [(0, 30), (0.02, 24), (0.05, 15), (0.08, 6), (0.10, 0)]:
        assert metrics([0], [error])["gap_score"] == score


def test_realtime_rejected(model):
    with pytest.raises(DataError, match="retrospective"):
        reconstruct(series([0.2]), {"mode": "realtime"}, model)
