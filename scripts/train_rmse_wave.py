"""Run a bounded development wave without reading supplied test answers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd
import yaml
from compare_reconstruction import assert_same_context, compare, read_development
from terralens_ml import model as runtime
from terralens_ml.io import DataError, canonical_hash, read_csv, sha256, write_json
from terralens_ml.uncertainty import calibrate
from train_expanded_model import freeze, score


def feature_cache(directory, original, source_hash):
    """Cache exact numeric columns, labels and source indices; no pickle."""
    directory.mkdir(parents=True, exist_ok=True)
    booster_options = {
        "boost_iterations",
        "boost_depth",
        "boost_learning_rate",
        "boost_l2",
        "normalize_target_weights",
        "ensemble_seeds",
    }

    def cached(frame, valid, config, model):
        identity = {
            "source": source_hash,
            "frame": hashlib.sha256(
                pd.util.hash_pandas_object(frame, index=True).to_numpy().tobytes()
            ).hexdigest(),
            "valid": hashlib.sha256(valid.to_numpy().tobytes()).hexdigest(),
            "config": {key: value for key, value in config.items() if key not in booster_options},
        }
        key = canonical_hash(identity)
        path, metadata_path = directory / f"{key}.npz", directory / f"{key}.json"
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text())
            if metadata["identity"] != identity or sha256(path) != metadata["sha256"]:
                raise DataError("Повреждён или изменён feature cache")
            with np.load(path, allow_pickle=False) as arrays:
                features = pd.DataFrame({name: arrays[f"f{i}"] for i, name in enumerate(metadata["columns"])})
                return features, pd.Series(arrays["residuals"]), arrays["target_indices"]
        features, residuals, indices = original(frame, valid, config, model)
        arrays = {f"f{i}": features[name].to_numpy() for i, name in enumerate(features.columns)}
        arrays |= {"residuals": residuals.to_numpy(), "target_indices": indices}
        if any(array.dtype.hasobject for array in arrays.values()):
            raise DataError("Этот исследовательский cache принимает только числовые признаки")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, delete=False) as stream:
                temporary = Path(stream.name)
                np.savez(stream, **arrays)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        write_json(
            metadata_path,
            {"identity": identity, "columns": features.columns.tolist(), "sha256": sha256(path)},
        )
        return features, residuals, indices

    return cached


def prepare(config):
    baseline, manifest = runtime.load_model(config["baseline_model"])
    prior = json.loads(Path(config["prior_split"]).read_text())
    source = {path.name: sha256(path) for path in sorted(Path(runtime.__file__).parent.glob("*.py"))}
    source["train_rmse_wave.py"] = sha256(__file__)
    plan = {
        "config": config,
        "baseline_model_id": manifest["model_id"],
        "model_config": baseline["config"],
        "source_hashes": source,
        "source_hash": canonical_hash(source),
        "selection_ids": prior["selection_ids"],
        "calibration_ids": prior["calibration_ids"],
        "assessment_ids": prior["assessment_ids"],
        "excluded_previously_inspected_holdout": prior["excluded_previously_inspected_holdout"],
        "temporal_year": prior["temporal_year"],
        "folds": prior["folds"],
        "input_hashes": {
            name: sha256(config[name])
            for name in ["input", "baseline_model", "baseline_predictions", "prior_split"]
        },
        "protocol_sha256": sha256(Path(config["evidence"]) / "PROTOCOL.md"),
        "test_labels_used_for_selection": False,
        "assessment_status": "Previously inspected data; no new independent labels; development selection only",
    }
    freeze(Path(config["evidence"]) / "plan.json", plan)
    frame = read_csv(config["input"])
    return frame.loc[pd.to_datetime(frame.date).dt.year.lt(plan["temporal_year"])], plan


def verify_baseline(config, frame, plan):
    evidence, output = Path(config["evidence"]), Path(config["output"])
    if (evidence / "baseline-reproduction.json").exists():
        return
    fold = plan["folds"][0]
    training = frame.loc[frame.anon_polygon_id.isin(fold["train_ids"])]
    validation = frame.loc[frame.anon_polygon_id.isin(fold["validation_ids"])]
    start = time.perf_counter()
    model = runtime.fit(training, plan["model_config"])
    results = score(
        validation, model, "development", fold["fold"], config["mask_seeds"], config["mask_fraction"]
    )
    results["candidate"] = "reproduced"
    path = output / "baseline-fold-0.csv"
    results.to_csv(path, index=False)
    expected = read_development(config["baseline_predictions"], config["baseline_candidate"])
    expected = expected.loc[expected.index.get_level_values("fold") == fold["fold"]]
    actual = read_development(path, "reproduced")
    assert_same_context(expected, actual, "baseline reproduction")
    difference = np.max(abs(actual.reconstructed - expected.reconstructed))
    if difference > 1e-12:
        raise DataError(f"Baseline не воспроизведён: max diff={difference}")
    write_json(
        evidence / "baseline-reproduction.json",
        {
            "fold": 0,
            "rows": len(actual),
            "max_absolute_difference": float(difference),
            "tolerance": 1e-12,
            "seconds": time.perf_counter() - start,
            "predictions_sha256": sha256(path),
            "plan_sha256": sha256(evidence / "plan.json"),
        },
    )
    print(f"Baseline fold 0 reproduced; max difference {difference:.3g}", flush=True)


def run_candidate(name, overrides, config, frame, plan):
    evidence = Path(config["evidence"]) / name
    output = Path(config["output"]) / name
    output.mkdir(parents=True, exist_ok=True)
    freeze(evidence / "config.json", plan["model_config"] | overrides)
    if (evidence / "decision.json").exists():
        return json.loads((evidence / "decision.json").read_text())
    frames = []
    for fold in plan["folds"]:
        path = output / f"fold-{fold['fold']}.csv"
        if not path.exists():
            start = time.perf_counter()
            training = frame.loc[frame.anon_polygon_id.isin(fold["train_ids"])]
            validation = frame.loc[frame.anon_polygon_id.isin(fold["validation_ids"])]
            model = runtime.fit(training, plan["model_config"] | overrides)
            result = score(
                validation, model, "development", fold["fold"], config["mask_seeds"], config["mask_fraction"]
            )
            result["candidate"] = name
            result.to_csv(path, index=False)
            write_json(
                evidence / f"training-fold-{fold['fold']}.json",
                {
                    "train_ids": fold["train_ids"],
                    "validation_ids": fold["validation_ids"],
                    "training_rows": model["training_rows"],
                    "training_examples": model["training_examples"],
                    "feature_count": len(model["feature_names"]),
                    "seconds": time.perf_counter() - start,
                    "predictions_sha256": sha256(path),
                },
            )
        frames.append(pd.read_csv(path))
        print(f"{name}: fold {fold['fold'] + 1}/5 complete", flush=True)
    predictions = output / "predictions.csv"
    pd.concat(frames, ignore_index=True).to_csv(predictions, index=False)
    report = compare(
        SimpleNamespace(
            baseline=Path(config["baseline_predictions"]),
            baseline_candidate=config["baseline_candidate"],
            candidate=predictions,
            candidate_name=name,
            secondary=None,
            output=evidence,
            bootstrap=3000,
            seed=42,
        )
    )
    point = report["scopes"]["development_points"]["comparisons"]["candidate_vs_baseline"]
    block = report["scopes"]["development_blocks"]["comparisons"]["candidate_vs_baseline"]
    improved = sum(
        fold["scopes"]["development_points"]["candidate"]["rmse"]
        < fold["scopes"]["development_points"]["baseline"]["rmse"]
        for fold in report["folds"].values()
    )
    decision = {
        "candidate": name,
        "overrides": overrides,
        "accepted": point["relative_rmse_reduction"] >= config["minimum_relative_gain"]
        and block["gain_rmse"] >= 0
        and improved >= config["minimum_improved_folds"]
        and point["gain_rmse_95_aoi_bootstrap"][0] > 0,
        "point_rmse": report["scopes"]["development_points"]["metrics"]["candidate"]["rmse"],
        "block_rmse": report["scopes"]["development_blocks"]["metrics"]["candidate"]["rmse"],
        "point_comparison": point,
        "block_comparison": block,
        "improved_point_folds": improved,
        "predictions_sha256": sha256(predictions),
        "plan_sha256": sha256(Path(config["evidence"]) / "plan.json"),
    }
    write_json(evidence / "decision.json", decision)
    print(
        f"{name}: points {decision['point_rmse']:.6f}, blocks {decision['block_rmse']:.6f}, gain {point['relative_rmse_reduction']:.2%}, improved {improved}/5, accepted={decision['accepted']}",
        flush=True,
    )
    return decision


def develop(config, frame, plan):
    verify_baseline(config, frame, plan)
    decisions = [
        run_candidate(name, overrides, config, frame, plan)
        for name, overrides in config["candidates"].items()
    ]
    accepted = [decision for decision in decisions if decision["accepted"]]
    tuning = [
        decision
        for decision in accepted
        if decision["candidate"] in ["longer_boosting", "deeper_regularized"]
    ]
    independent = [decision for decision in accepted if decision not in tuning]
    if tuning:
        independent.append(min(tuning, key=lambda decision: (decision["point_rmse"], decision["candidate"])))
    if len(independent) >= 2:
        combined = {}
        for decision in independent:
            combined |= decision["overrides"]
        decisions.append(run_candidate("combined", combined, config, frame, plan))
    eligible = [decision for decision in decisions if decision["accepted"]]
    winner = (
        min(eligible, key=lambda decision: (decision["point_rmse"], decision["candidate"]))
        if eligible
        else None
    )
    write_json(
        Path(config["evidence"]) / "selection.json",
        {
            "selected": winner,
            "candidates": decisions,
            "plan_sha256": sha256(Path(config["evidence"]) / "plan.json"),
            "independent_assessment_available": False,
        },
    )
    print(f"Selection: {winner['candidate'] if winner else 'retain current weights'}", flush=True)


def final_fit(config, frame, plan):
    evidence, output = Path(config["evidence"]), Path(config["output"])
    selected = json.loads((evidence / "selection.json").read_text())["selected"]
    if not selected or not selected["accepted"]:
        raise DataError("Ни один кандидат не прошёл условия development")
    if (evidence / "final-fit.json").exists():
        raise DataError("Final fit уже выполнен; используйте сохранённый артефакт")
    training = frame.loc[frame.anon_polygon_id.isin(plan["selection_ids"])]
    model = runtime.fit(training, plan["model_config"] | selected["overrides"])
    model["training_scope"] = {
        "polygon_ids": plan["selection_ids"],
        "years_before": plan["temporal_year"],
        "calibration_ids": plan["calibration_ids"],
        "assessment_ids": plan["assessment_ids"],
        "excluded_previously_inspected_holdout": plan["excluded_previously_inspected_holdout"],
    }
    calibration = frame.loc[frame.anon_polygon_id.isin(plan["calibration_ids"])]
    predictions = score(
        calibration, model, "calibration", -1, [config["calibration_seed"]], config["mask_fraction"]
    )
    model["calibration"] = calibrate(predictions, level=config["calibration_level"])
    predictions.to_csv(output / "calibration-predictions.csv", index=False)
    manifest = runtime.save_model(
        model,
        output / "model",
        input_path=config["input"],
        metrics={
            "selection": {
                decision["candidate"]: {"rmse": decision["point_rmse"]}
                for decision in json.loads((evidence / "selection.json").read_text())["candidates"]
            },
            "selected": selected["candidate"],
            "development_points": {"rmse": selected["point_rmse"]},
            "development_blocks": {"rmse": selected["block_rmse"]},
            "assessment_status": plan["assessment_status"],
        },
        validation_hashes={
            "plan": sha256(evidence / "plan.json"),
            "selection": sha256(evidence / "selection.json"),
        },
    )
    write_json(
        evidence / "final-fit.json",
        {
            "model_id": manifest["model_id"],
            "manifest_sha256": sha256(output / "model/manifest.json"),
            "training_scope": model["training_scope"],
            "calibration": model["calibration"],
            "test_labels_read": False,
        },
    )
    print(f"Final model ready: {manifest['model_id']}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="ml/configs/rmse-wave.yaml")
    parser.add_argument("--stage", choices=["develop", "final", "benchmark"], required=True)
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text())
    frame, plan = prepare(config)
    original = runtime.booster_training_data
    cached = feature_cache(Path(config["output"]) / "feature-cache", original, plan["source_hash"])
    with patch.object(runtime, "booster_training_data", cached):
        {"develop": develop, "final": final_fit, "benchmark": benchmark}[args.stage](config, frame, plan)


def benchmark(config, frame, plan):
    evidence, output = Path(config["evidence"]), Path(config["output"])
    final = json.loads((evidence / "final-fit.json").read_text())
    candidate_path = output / "model/manifest.json"
    if sha256(candidate_path) != final["manifest_sha256"]:
        raise DataError("Модель изменилась после final fit")
    if (evidence / "inference-timing.json").exists():
        raise DataError("Замер уже выполнен; используйте сохранённые samples")
    baseline, _ = runtime.load_model(config["baseline_model"])
    candidate, _ = runtime.load_model(candidate_path)
    report = {
        "method": "Ten alternating warm full reconstruct calls per model/input; imports/read/load/write excluded",
        "baseline": "Current optimized runtime with original weights",
        "platform": platform.platform(),
        "python": platform.python_version(),
        "baseline_manifest_sha256": sha256(config["baseline_model"]),
        "candidate_manifest_sha256": sha256(candidate_path),
        "inputs": {},
    }
    for path in ["test-dataset.csv", "test_features.csv"]:
        context = read_csv(path)
        for model in [baseline, candidate]:
            runtime.reconstruct(context, model=model)
        samples = {"baseline": [], "candidate": []}
        for repeat in range(10):
            order = [("baseline", baseline), ("candidate", candidate)]
            for name, model in order if repeat % 2 == 0 else reversed(order):
                start = time.perf_counter()
                runtime.reconstruct(context, model=model)
                samples[name].append(time.perf_counter() - start)
        medians = {name: float(np.median(values)) for name, values in samples.items()}
        report["inputs"][path] = {
            "input_sha256": sha256(path),
            "rows": len(context),
            "samples_seconds": samples,
            "median_seconds": medians,
            "latency_ratio": medians["candidate"] / medians["baseline"],
        }
        print(f"Timing {path}: {medians}", flush=True)
    report["budget_passed"] = all(
        value["latency_ratio"] <= config["maximum_latency_ratio"] for value in report["inputs"].values()
    )
    write_json(evidence / "inference-timing.json", report)


if __name__ == "__main__":
    main()
