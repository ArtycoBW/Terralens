import numpy as np
import pandas as pd
import pytest
from terralens_ml.uncertainty import apply_intervals


@pytest.mark.parametrize("shifted", [False, True])
def test_interval_groups_nulls_and_flags_with_nonstandard_index(shifted):
    frame = pd.DataFrame(
        {
            "origin": [
                "observed",
                "unavailable",
                "interpolated",
                "interpolated",
                "extrapolated",
                "climatology_fallback",
                "interpolated",
            ],
            "gap_days": [0, 10, 30, 31, 10, 100, 10],
            "reconstructed": [0.5, np.nan, 0.5, 0.5, 0.5, 0.5, np.inf],
            "quality_flags": [["existing"] for _ in range(7)],
        },
        index=[20, 3, 100, 60, 80, 90, 30],
    )
    original_flags = frame.quality_flags.to_list()
    calibration = {
        "method": "empirical_residual",
        "domain": "anonymous_benchmark",
        "level": 0.9,
        "pooled_radius": 0.4,
        "groups": {"short": {"radius": 0.1}, "long": {"radius": 0.2}, "prior": {"radius": 0.3}},
    }
    result = apply_intervals(
        frame, {"calibration": calibration}, {"interval_domain": "live"} if shifted else {}
    )
    assert result.index.tolist() == [20, 3, 100, 60, 80, 90, 30]
    for position, radius in enumerate([None, None, 0.1, 0.2, 0.4, 0.3, None]):
        interval = result.prediction_interval.iloc[position]
        if radius is None:
            assert interval == {"lower": None, "upper": None, "level": None, "method": "not_calibrated"}
        else:
            assert interval == {
                "lower": 0.5 - radius,
                "upper": 0.5 + radius,
                "level": 0.9,
                "method": "empirical_residual" + ("_domain_shift" if shifted else ""),
            }
        assert result.quality_flags.iloc[position] == ["existing"] + (
            ["domain_shift"] if shifted and radius is not None else []
        )
    assert original_flags == [["existing"] for _ in range(7)]


def test_empty_uncalibrated_intervals_need_no_data_columns():
    frame = pd.DataFrame(index=[5, 10])
    result = apply_intervals(frame, {}, {})
    assert all(value["lower"] is None for value in result.prediction_interval)
    result.prediction_interval.iloc[0]["lower"] = 0.3
    assert result.prediction_interval.iloc[1]["lower"] is None
    assert apply_intervals(pd.DataFrame(), {}, {}).empty
    assert apply_intervals(pd.DataFrame(), {"calibration": {"level": 0.9}}, {}).empty
