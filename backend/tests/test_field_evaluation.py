"""Проверки маскирования независимой оценки на реальных наблюдениях."""

import runpy
from pathlib import Path

evaluation = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/evaluate_field_cases.py"))


def test_mask_hides_all_sensors_and_duplicate_scenes_without_mutation():
    observations = [
        {"date": "2024-06-01", "sensor": "sentinel2", "scene": "a"},
        {"date": "2024-06-01", "sensor": "sentinel2", "scene": "b"},
        {"date": "2024-06-01", "sensor": "landsat", "scene": "c"},
        {"date": "2024-06-10", "sensor": "landsat", "scene": "d"},
    ]
    visible = evaluation["remove_dates"](observations, ["2024-06-01"])
    assert visible == [observations[-1]]
    assert len(observations) == 4


def test_masks_are_chronological_disjoint_and_do_not_duplicate_odd_last_day():
    masks = evaluation["masks_for_dates"](["2024-06-20", "2024-06-01", "2024-06-10", "2024-06-01"])
    assert masks["points"] == [["2024-06-01"], ["2024-06-10"], ["2024-06-20"]]
    assert masks["blocks"] == [["2024-06-01", "2024-06-10"]]


def test_metrics_keep_unavailable_predictions_in_denominator_report():
    result = evaluation["metrics"](
        [
            {"truth": 0.5, "prediction": 0.6, "interval_contains_truth": True},
            {"truth": 0.5, "prediction": None},
        ]
    )
    assert result["targets"] == 2
    assert result["predicted"] == 1
    assert result["unavailable"] == 1
    assert abs(result["rmse"] - 0.1) < 1e-12
    assert result["interval_n"] == 1
