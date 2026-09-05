import json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from terralens_ml import research
from terralens_ml.io import DataError


@pytest.fixture
def protocol_input(tmp_path):
    frame = pd.DataFrame(
        [
            {"anon_polygon_id": name, "date": day, "crop_type": "unknown", "primary_ndvi": 0.2 + index * 0.03}
            for name in "ABCDEFG"
            for index, day in enumerate(
                [
                    "2023-06-01",
                    "2023-06-03",
                    "2023-06-06",
                    "2023-06-10",
                    "2024-06-01",
                    "2024-06-05",
                ]
            )
        ]
    )
    input_path = tmp_path / "input.csv"
    frame.to_csv(input_path, index=False)
    prior = tmp_path / "prior.json"
    prior.write_text(json.dumps({"locked_holdout_ids": ["G"]}))
    config = {
        "input": str(input_path),
        "output": str(tmp_path / "research"),
        "artifact_output": str(tmp_path / "final"),
        "prior_split": str(prior),
        "seed": 42,
        "folds": 2,
        "mask_seeds": [11],
        "mask_fraction": 0.25,
        "calibration_fields": 1,
        "assessment_fields": 1,
        "calibration_level": 0.9,
        "candidates": {"baseline": {"algorithm": "neighbor_mean"}, "linear": {"algorithm": "linear"}},
    }
    return frame, config


def test_development_only_guards_final_fit_assessment_calibration_and_artifacts(protocol_input, monkeypatch):
    frame, config = protocol_input
    config["assessment_status"] = "Previously inspected assessment: reused diagnostic only"
    config["assessment_limitations"] = ["No unseen assessment data remain"]
    original_fit, original_score = research.fit, research._score_context
    fit_ids, scored_scopes = [], []
    output = Path(config["output"])

    def fit(data, options):
        plan = json.loads((output / "split_manifest.json").read_text())
        ids = set(data.anon_polygon_id)
        assert ids in [set(fold["train_ids"]) for fold in plan["folds"]]
        assert set(pd.to_datetime(data.date).dt.year) == {2023}
        fit_ids.append(ids)
        return original_fit(data, options)

    def score(data, model, mask, scope, fold, seed):
        plan = json.loads((output / "split_manifest.json").read_text())
        assert scope in {"development_points", "development_blocks"}
        assert set(data.anon_polygon_id) == set(plan["folds"][fold]["validation_ids"])
        assert set(pd.to_datetime(data.date).dt.year) == {2023}
        scored_scopes.append(scope)
        return original_score(data, model, mask, scope, fold, seed)

    def forbidden(*args, **kwargs):
        pytest.fail("Development-only must not calibrate, assess intervals, or save a model")

    monkeypatch.setattr(research, "fit", fit)
    monkeypatch.setattr(research, "_score_context", score)
    for name in ["calibrate", "coverage", "save_model"]:
        monkeypatch.setattr(research, name, forbidden)
    report = research.run_research(frame, config, development_only=True)
    assert len(fit_ids) == config["folds"] * len(config["candidates"])
    assert len(scored_scopes) == 2 * len(fit_ids)
    assert report["development_only"] is True
    assert report["calibration"] is None and report["interval_assessment"] == {}
    assert report["assessment_status"] == config["assessment_status"]
    assert config["assessment_limitations"][0] in report["limitations"]
    assert research.DEFAULT_ASSESSMENT_LIMITATION not in report["limitations"]
    assert not Path(config["artifact_output"]).exists()
    assert all(path.name.startswith("development_") for path in (output / "masks").iterdir())
    for name in ["predictions.csv", "metrics.csv"]:
        saved = pd.read_csv(output / name)
        assert set(saved.scope) == {"development_points", "development_blocks"}
    assert json.loads((output / "report.json").read_text()) == report
    assert (
        json.loads((output / "selected_config.json").read_text())["algorithm"] == report["selected_algorithm"]
    )

    # Тот же config разрешает полный запуск: execution flag не изменяет зафиксированный split.
    frozen_plan = (output / "split_manifest.json").read_bytes()

    class FinalFitReached(Exception):
        pass

    def stop_at_final_fit(data, options):
        plan = json.loads(frozen_plan)
        if set(data.anon_polygon_id) == set(plan["selection_ids"]):
            raise FinalFitReached
        return fit(data, options)

    monkeypatch.setattr(research, "fit", stop_at_final_fit)
    with pytest.raises(FinalFitReached):
        research.run_research(frame, config)
    assert (output / "split_manifest.json").read_bytes() == frozen_plan
    assert not Path(config["artifact_output"]).exists()


def test_candidate_can_use_default_algorithm_in_both_execution_modes(protocol_input):
    frame, config = protocol_input
    config["candidates"] = {"default": {}}
    for development_only in [True, False]:
        report = research.run_research(frame, config, development_only=development_only)
        assert report["selected_algorithm"] == "linear"
        assert report["selected_candidate"] == "default"


@pytest.mark.parametrize("guarded, expected", [(True, "balanced"), (False, "points_only")])
def test_selection_guardrail_rejects_regression_on_blocks(protocol_input, monkeypatch, guarded, expected):
    frame, config = protocol_input
    config["candidates"] = {
        "baseline": {"algorithm": "neighbor_mean"},
        "points_only": {"algorithm": "linear"},
        "balanced": {"algorithm": "pchip"},
    }
    if guarded:
        config["selection_baseline"] = "baseline"
    original_score = research._score_context

    def controlled_scores(data, model, mask, scope, fold, seed):
        scored = original_score(data, model, mask, scope, fold, seed)
        point_error, block_error = {
            "neighbor_mean": (0.2, 0.3),
            "linear": (0.01, 0.4),
            "pchip": (0.1, 0.25),
        }[model["config"]["algorithm"]]
        scored["reconstructed"] = scored.truth + (block_error if scope.endswith("blocks") else point_error)
        return scored

    monkeypatch.setattr(research, "_score_context", controlled_scores)
    report = research.run_research(frame, config, development_only=True)
    assert report["selected_candidate"] == expected
    assert report["assessment_status"] == research.DEFAULT_ASSESSMENT_STATUS
    assert research.DEFAULT_ASSESSMENT_LIMITATION in report["limitations"]
    if guarded:
        assert report["selection_guardrail"]["maximum_blocks_rmse"] == pytest.approx(0.3)
        assert set(report["selection_guardrail"]["eligible_candidates"]) == {"baseline", "balanced"}
    else:
        assert report["selection_guardrail"] is None


def test_unknown_selection_baseline_fails_before_fitting(protocol_input, monkeypatch):
    frame, config = protocol_input
    config["selection_baseline"] = "missing"
    monkeypatch.setattr(
        research, "fit", lambda *args: pytest.fail("Unknown baseline must fail before fitting")
    )
    with pytest.raises(DataError, match="selection_baseline"):
        research.run_research(frame, config, development_only=True)
    assert not Path(config["output"]).exists()


def test_cli_passes_development_only_without_mutating_config(protocol_input, tmp_path, monkeypatch):
    from terralens_ml import cli

    frame, config = protocol_input
    path = tmp_path / "research.yaml"
    path.write_text(yaml.safe_dump(config))
    monkeypatch.setattr(cli, "read_csv", lambda *args: frame)
    received = []

    def run(data, actual_config, *, development_only):
        assert actual_config == config and data is frame
        received.append(development_only)
        return {"selected_algorithm": "neighbor_mean", "development": {}}

    monkeypatch.setattr(cli, "run_research", run)
    assert cli.main(["research", "--config", str(path), "--development-only"]) == 0
    assert received == [True]
