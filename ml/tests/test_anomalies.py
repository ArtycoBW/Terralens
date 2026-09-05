import pandas as pd
from terralens_ml.anomalies import add_reference, detect_anomalies, severity


def frame(z, origins):
    return pd.DataFrame(
        {
            "anon_polygon_id": "A",
            "date": pd.date_range("2024-06-01", periods=len(z)).strftime("%Y-%m-%d"),
            "zscore": z,
            "origin": origins,
            "reconstructed": 0.3,
            "climatology_mean": 0.6,
            "quality_flags": [[] for _ in z],
        }
    )


def test_thresholds_and_evidence():
    assert severity(-1) == "normal"
    assert severity(-2) == "stress"
    assert severity(-2.01) == "critical"
    assert severity(None) == "insufficient_data"
    assert not detect_anomalies(frame([-3] * 10, ["interpolated"] * 10))
    event = detect_anomalies(frame([-3], ["observed"]))[0]
    assert event["event_kind"] == "single_observation_alert" and event["confidence"] == "low"
    event = detect_anomalies(frame([-3, -2.5], ["observed", "observed"]))[0]
    assert event["event_kind"] == "persistent_period" and event["observed_evidence_count"] == 2


def test_reference_excludes_current_year_and_zero_std():
    result = frame([None], ["observed"])
    result["clean_primary"] = 0.3
    history = pd.DataFrame(
        {
            "anon_polygon_id": "A",
            "date": ["2021-06-01", "2022-06-01", "2023-06-01", "2024-06-01"],
            "primary_ndvi": [0.5, 0.5, 0.5, 0.9],
        }
    )
    actual = add_reference(result, history)
    assert actual.reference_years.iloc[0] == 3
    assert pd.isna(actual.zscore.iloc[0])
    assert "degenerate_reference" in actual.quality_flags.iloc[0]
    short = add_reference(result, history.iloc[:2])
    assert "insufficient_reference" in short.quality_flags.iloc[0]


def test_robust_reference_masks_hidden_history_and_matches_crop():
    result = frame([None], ["observed"])
    result["clean_primary"], result["crop_type"] = 0.3, "wheat"
    history = pd.DataFrame(
        {
            "anon_polygon_id": "A",
            "date": [f"{year}-06-01" for year in range(2018, 2024)],
            "primary_ndvi": [0.4, 0.5, 0.6, 0.99, 0.1, 0.99],
            "crop_type": ["wheat"] * 4 + ["maize", "wheat"],
            "is_synthetic_gap": [False] * 5 + [True],
        }
    )
    actual = add_reference(result, history)
    assert actual.reference_years.iloc[0] == 4
    assert actual.climatology_mean.iloc[0] == 0.55
    assert abs(actual.climatology_std.iloc[0] - 0.14826) < 1e-6
    assert "robust_reference" in actual.quality_flags.iloc[0]


def test_long_gap_evidence_and_weather_coverage_lower_confidence():
    data = frame([-3] * 9, ["observed"] * 3 + ["interpolated"] * 6)
    data["quality_flags"] = [["long_gap"] for _ in range(9)]
    event = detect_anomalies(data)[0]
    assert event["confidence"] == "medium"
    assert event["weather_coverage_ratio"] == 0
    assert "weather_missing" in event["quality_flags"]
