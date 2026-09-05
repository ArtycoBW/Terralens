from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from services.analysis import calculate
from terralens_ml.model import fit, load_model, reconstruct


def observation(day, value, sensor="sentinel2", usable=True, coverage=0.8):
    return {
        "date": day,
        "ndvi": value,
        "sensor": sensor,
        "usable": usable,
        "valid_pixel_fraction": coverage,
        "quality_flags": [] if usable else ["low_pixel_coverage"],
    }


def baseline():
    return fit(
        pd.DataFrame(
            {
                "anon_polygon_id": ["training", "training"],
                "date": ["2023-06-01", "2023-06-10"],
                "crop_type": ["unknown", "unknown"],
                "primary_ndvi": [0.2, 0.8],
            }
        )
    )


def test_sensor_priority_and_fallback_preserve_individual_measurements():
    daily, _, _ = calculate(
        "field",
        None,
        date(2024, 6, 1),
        date(2024, 6, 2),
        [
            observation("2024-06-01", 0.4),
            observation("2024-06-01", 0.8, "landsat", coverage=1.0),
            observation("2024-06-02", 0.1, usable=False),
            observation("2024-06-02", 0.7, "landsat"),
        ],
        [],
        baseline(),
    )
    assert daily[0]["clean_primary"] == 0.4
    assert daily[0]["sensors"] == {"sentinel2": 0.4, "landsat": 0.8, "modis": None}
    assert daily[1]["source_sensor"] == "landsat"
    assert daily[1]["clean_primary"] == 0.7
    assert daily[1]["sensors"]["sentinel2"] == 0.1


def test_static_crop_does_not_invent_historical_crop_seasons():
    observations = [observation("2024-06-01", 0.5)]
    history = [observation(f"{year}-06-01", value) for year, value in [(2021, 0.5), (2022, 0.6), (2023, 0.8)]]
    args = ("field", "wheat", date(2024, 6, 1), date(2024, 6, 1), observations, [], baseline(), history)
    unknown, _, _ = calculate(*args)
    assert unknown[0]["reference_years"] == 0
    seasons = [
        {"season_start": f"{year}-01-01", "season_end": f"{year}-12-31", "crop_type": "wheat"}
        for year in range(2021, 2025)
    ]
    known, _, _ = calculate(*args, crop_seasons=seasons)
    assert known[0]["reference_years"] == 3
    assert known[0]["climatology_mean"] is not None


def test_history_alone_does_not_create_live_observations_or_health():
    daily, events, summary = calculate(
        "field",
        None,
        date(2024, 6, 1),
        date(2024, 6, 3),
        [],
        [],
        baseline(),
        [observation("2023-06-01", 0.6)],
    )
    assert events == []
    assert summary["overall_status"] == "insufficient_data"
    assert summary["unavailable_days"] == 3
    assert all(x["reconstructed"] is None and x["origin"] == "unavailable" for x in daily)
    assert all(x["prediction_interval"]["lower"] is None for x in daily)


def test_worker_matches_batch_core_on_same_calendar_and_context():
    model = baseline()
    dates = pd.date_range("2024-06-01", "2024-06-10").strftime("%Y-%m-%d")
    observations = [observation("2024-06-01", 0.3), observation("2024-06-10", 0.8)]
    frame = pd.DataFrame(
        {
            "anon_polygon_id": "field",
            "date": dates,
            "crop_type": "unknown",
            "primary_ndvi": [0.3] + [float("nan")] * 8 + [0.8],
        }
    )
    expected = reconstruct(frame, model=model)
    daily, _, _ = calculate("field", None, date(2024, 6, 1), date(2024, 6, 10), observations, [], model)
    assert [x["reconstructed"] for x in daily] == expected.reconstructed.tolist()


def test_final_model_worker_parity_and_live_interval_scope():
    path = Path(__file__).resolve().parents[2] / "ml/artifacts/final/manifest.json"
    model, _ = load_model(path)
    dates = pd.date_range("2024-06-01", "2024-06-10").strftime("%Y-%m-%d")
    values = [0.3] + [float("nan")] * 8 + [0.8]
    frame = pd.DataFrame(
        {
            "anon_polygon_id": "field",
            "date": dates,
            "crop_type": "unknown",
            "primary_ndvi": values,
            "s2_ndvi": values,
        }
    )
    expected = reconstruct(frame, model=model)
    observations = [observation("2024-06-01", 0.3), observation("2024-06-10", 0.8)]
    daily, _, _ = calculate("field", None, date(2024, 6, 1), date(2024, 6, 10), observations, [], model)
    np.testing.assert_allclose([x["reconstructed"] for x in daily], expected.reconstructed, atol=1e-8)
    assert daily[0]["prediction_interval"]["lower"] is None
    assert daily[1]["prediction_interval"]["method"] == "empirical_residual_domain_shift"
    assert "domain_shift" in daily[1]["quality_flags"]


def test_unknown_crop_reduces_event_confidence_before_detection():
    daily, events, _ = calculate(
        "field",
        None,
        date(2024, 6, 1),
        date(2024, 6, 3),
        [observation(f"2024-06-0{day}", 0.1) for day in range(1, 4)],
        [],
        baseline(),
        [observation(f"{year}-06-01", value) for year, value in [(2021, 0.5), (2022, 0.6), (2023, 0.7)]],
    )
    assert events and events[0]["confidence"] != "high"
    assert "crop_history_unknown" in events[0]["quality_flags"]
    assert "crop_history_unknown" in daily[0]["quality_flags"]


def test_reference_includes_earlier_season_inside_selected_period():
    daily, _, _ = calculate(
        "field",
        None,
        date(2023, 6, 1),
        date(2024, 5, 31),
        [observation("2023-06-01", 0.7), observation("2024-05-31", 0.5)],
        [],
        baseline(),
        [observation("2021-05-31", 0.5), observation("2022-05-31", 0.6)],
    )
    assert daily[-1]["reference_years"] == 3
    assert daily[-1]["climatology_mean"] is not None


def test_reference_does_not_mix_unharmonized_sensors():
    daily, _, _ = calculate(
        "field",
        None,
        date(2024, 6, 1),
        date(2024, 6, 1),
        [observation("2024-06-01", 0.5, "landsat")],
        [],
        baseline(),
        [observation(f"{year}-06-01", 0.6) for year in [2021, 2022, 2023]],
    )
    assert daily[0]["reference_years"] == 0
    assert daily[0]["zscore"] is None
    assert "reference_sensor_landsat" in daily[0]["quality_flags"]
    mixed = [
        observation(f"{year}-06-01", value, sensor)
        for year, value in [(2021, 0.5), (2022, 0.6), (2023, 0.7)]
        for sensor in ["sentinel2", "landsat"]
    ]
    compatible, _, _ = calculate(
        "field",
        None,
        date(2024, 6, 1),
        date(2024, 6, 1),
        [observation("2024-06-01", 0.5, "landsat")],
        [],
        baseline(),
        mixed,
    )
    assert compatible[0]["reference_years"] == 3


def test_one_observed_day_with_reference_does_not_imply_normal_period():
    history = [observation(f"{year}-06-05", 0.6) for year in [2022, 2023]] + [
        observation(f"{year}-06-05", value, "landsat")
        for year, value in [(2021, 0.3), (2022, 0.5), (2023, 0.7)]
    ]
    daily, events, summary = calculate(
        "field",
        None,
        date(2024, 6, 1),
        date(2024, 6, 10),
        [observation("2024-06-01", 0.5), observation("2024-06-10", 0.5, "landsat")],
        [],
        baseline(),
        history,
    )
    assert events == []
    assert summary["observed_days"] == 2
    assert sum(x["clean_primary"] is not None and x["zscore"] is not None for x in daily) == 1
    assert summary["overall_status"] == "insufficient_data"


def test_two_referenced_days_do_not_mark_a_mostly_unassessed_period_normal():
    history = [
        observation(f"{year}-06-05", value, "landsat")
        for year, value in [(2021, 0.3), (2022, 0.5), (2023, 0.7)]
    ]
    observations = [
        observation("2024-06-01", 0.5),
        observation("2024-06-04", 0.5, "landsat"),
        observation("2024-06-07", 0.5),
        observation("2024-06-10", 0.5, "landsat"),
    ]
    daily, events, summary = calculate(
        "field", None, date(2024, 6, 1), date(2024, 6, 10), observations, [], baseline(), history
    )
    assert sum(row["zscore"] is not None for row in daily) == 2
    assert events == []
    assert summary["overall_status"] == "insufficient_data"

    all_same_sensor = [dict(row, sensor="landsat") for row in observations]
    _, events, complete = calculate(
        "field", None, date(2024, 6, 1), date(2024, 6, 10), all_same_sensor, [], baseline(), history
    )
    assert events == []
    assert complete["overall_status"] == "normal"


def test_negative_observed_signal_remains_visible_with_sparse_reference():
    history = [
        observation(f"{year}-06-05", value, "landsat")
        for year, value in [(2021, 0.5), (2022, 0.6), (2023, 0.7)]
    ]
    _, events, summary = calculate(
        "field",
        None,
        date(2024, 6, 1),
        date(2024, 6, 10),
        [
            observation("2024-06-01", 0.5),
            observation("2024-06-04", 0.1, "landsat"),
            observation("2024-06-07", 0.5),
            observation("2024-06-10", 0.1, "landsat"),
        ],
        [],
        baseline(),
        history,
    )
    assert events
    assert summary["overall_status"] == "critical"
