"""Frozen expanded-training experiment; external labels are read only by assess."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import yaml
from compare_reconstruction import compare, paired_bootstrap
from terralens_ml.io import (
    KEY,
    DataError,
    read_csv,
    sha256,
    validate_submission,
    write_json,
    write_submission,
)
from terralens_ml.model import fit, load_model, reconstruct, save_model
from terralens_ml.uncertainty import calibrate, coverage
from terralens_ml.validation import _score_context, make_mask, metrics


def freeze(path, data):
    if path.exists() and json.loads(path.read_text()) != data:
        raise DataError(f"План уже зафиксирован и отличается: {path}")
    write_json(path, data)


def partitions(frame, plan, validation_ids=()):
    excluded = set(plan["calibration_ids"]) | set(validation_ids)
    return frame.loc[~frame.anon_polygon_id.isin(excluded)]


def prepare(config):
    frame, test = read_csv(config["input"]), read_csv(config["test"])
    if set(frame.anon_polygon_id) & set(test.anon_polygon_id):
        raise DataError("Новые assessment AOI пересекаются с train")
    baseline, manifest = load_model(config["baseline_model"])
    prior = json.loads(Path(config["prior_split"]).read_text())
    plan = {
        "config": config,
        "baseline_model_id": manifest["model_id"],
        "model_config": baseline["config"] | config.get("model_overrides", {}),
        "calibration_ids": prior["calibration_ids"],
        "training_ids": sorted(set(frame.anon_polygon_id) - set(prior["calibration_ids"])),
        "external_assessment_ids": sorted(test.anon_polygon_id.unique()),
        "validation_years_before": prior["temporal_year"],
        "folds": prior["folds"],
        "hashes": {
            key: sha256(config[key])
            for key in [
                "input",
                "test",
                "assessment_labels",
                "baseline_model",
                "baseline_predictions",
                "prior_split",
            ]
        },
        "protocol_sha256": sha256(Path(config["evidence"]) / "PROTOCOL.md"),
        "private_labels_used_for_training_or_selection": False,
    }
    freeze(Path(config["evidence"]) / "plan.json", plan)
    return frame, test, baseline, plan


def score(frame, model, scope, fold, seeds, fraction):
    output = []
    for seed in seeds:
        for blocks in [False, True]:
            mask = make_mask(frame, seed, fraction, blocks=blocks)
            output.append(
                _score_context(frame, model, mask, f"{scope}_{'blocks' if blocks else 'points'}", fold, seed)
            )
    return pd.concat(output, ignore_index=True)


def develop(config, frame, plan):
    output, evidence = Path(config["output"]), Path(config["evidence"])
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for fold in plan["folds"]:
        path = output / f"development-fold-{fold['fold']}.csv"
        if not path.exists():
            training = partitions(frame, plan, fold["validation_ids"])
            validation = frame.loc[
                frame.anon_polygon_id.isin(fold["validation_ids"])
                & pd.to_datetime(frame.date).dt.year.lt(plan["validation_years_before"])
            ]
            model = fit(training, plan["model_config"])
            result = score(
                validation, model, "development", fold["fold"], config["mask_seeds"], config["mask_fraction"]
            )
            result["candidate"] = "expanded"
            result.to_csv(path, index=False)
            write_json(
                output / f"training-fold-{fold['fold']}.json",
                {
                    "ids": sorted(training.anon_polygon_id.unique()),
                    "rows": len(training),
                    "valid_targets": model["training_rows"],
                },
            )
        results.append(pd.read_csv(path))
        print(f"Development fold {fold['fold'] + 1}/5 готов", flush=True)
    path = output / "development-predictions.csv"
    pd.concat(results, ignore_index=True).to_csv(path, index=False)
    comparison = compare(
        SimpleNamespace(
            baseline=Path(config["baseline_predictions"]),
            baseline_candidate=config["baseline_candidate"],
            candidate=path,
            candidate_name="expanded",
            secondary=None,
            output=evidence,
            bootstrap=3000,
            seed=42,
        )
    )
    point = comparison["scopes"]["development_points"]["comparisons"]["candidate_vs_baseline"]
    block = comparison["scopes"]["development_blocks"]["comparisons"]["candidate_vs_baseline"]
    improved = sum(
        fold["scopes"]["development_points"]["candidate"]["rmse"]
        < fold["scopes"]["development_points"]["baseline"]["rmse"]
        for fold in comparison["folds"].values()
    )
    accepted = (
        point["relative_rmse_reduction"] >= config["minimum_relative_gain"]
        and block["gain_rmse"] >= 0
        and improved >= config["minimum_improved_folds"]
        and point["gain_rmse_95_aoi_bootstrap"][0] > 0
    )
    write_json(
        evidence / "development-decision.json",
        {
            "accepted": accepted,
            "point_comparison": point,
            "block_comparison": block,
            "improved_point_folds": improved,
            "plan_sha256": sha256(evidence / "plan.json"),
            "predictions_sha256": sha256(path),
        },
    )


def final_fit(config, frame, plan):
    output, evidence = Path(config["output"]), Path(config["evidence"])
    decision = json.loads((evidence / "development-decision.json").read_text())
    if not decision["accepted"]:
        raise DataError("Development-кандидат не прошёл условия публикации")
    if (output / "model/manifest.json").exists():
        raise DataError("Final fit уже существует; не переобучать после оценки")
    training = partitions(frame, plan)
    model = fit(training, plan["model_config"])
    model["training_scope"] = {
        "polygon_ids": plan["training_ids"],
        "years_through": int(pd.to_datetime(training.date).dt.year.max()),
        "calibration_ids": plan["calibration_ids"],
        "assessment_ids": plan["external_assessment_ids"],
        "excluded_previously_inspected_holdout": [],
        "previous_holdout_policy": "Previously inspected old holdout/assessment admitted to training; external assessment fields remain excluded",
    }
    calibration = score(
        frame.loc[frame.anon_polygon_id.isin(plan["calibration_ids"])],
        model,
        "calibration",
        -1,
        [config["calibration_seed"]],
        config["mask_fraction"],
    )
    model["calibration"] = calibrate(calibration, level=config["calibration_level"])
    calibration.to_csv(output / "calibration-predictions.csv", index=False)
    development = json.loads((evidence / "comparison.json").read_text())
    manifest = save_model(
        model,
        output / "model",
        input_path=config["input"],
        metrics={
            "development": {
                scope: info["metrics"]["candidate"] for scope, info in development["scopes"].items()
            },
            "calibration": {
                scope: coverage(part, model["calibration"]) for scope, part in calibration.groupby("scope")
            },
            "assessment": "External assessment pending; former diagnostic scopes are now training data",
        },
        validation_hashes={
            "plan": sha256(evidence / "plan.json"),
            "development_predictions": decision["predictions_sha256"],
            "calibration_predictions": sha256(output / "calibration-predictions.csv"),
        },
    )
    write_json(
        evidence / "final-fit.json",
        {
            "model_id": manifest["model_id"],
            "training_rows": model["training_rows"],
            "training_examples": model["training_examples"],
            "training_unique_targets": model["training_unique_targets"],
            "training_scope": model["training_scope"],
            "calibration": model["calibration"],
            "manifest_sha256": sha256(output / "model/manifest.json"),
        },
    )
    print(f"Final model {manifest['model_id']} готов; private labels ещё не прочитаны", flush=True)


def align_truth(test, labels):
    if list(labels.columns) != ["date", "primary_ndvi_true", "anon_polygon_id"]:
        raise DataError("Неожиданная схема assessment labels")
    submission = labels[KEY + ["primary_ndvi_true"]].rename(
        columns={"primary_ndvi_true": "primary_ndvi_pred"}
    )
    validate_submission(test, submission)
    return submission.rename(columns={"primary_ndvi_pred": "truth"})


def assess(config, test, baseline, plan):
    output, evidence = Path(config["output"]), Path(config["evidence"])
    model_path = output / "model/manifest.json"
    model, manifest = load_model(model_path)
    fitted = json.loads((evidence / "final-fit.json").read_text())
    if sha256(model_path) != fitted["manifest_sha256"]:
        raise DataError("Final artifact изменился после обучения")
    if set(model["training_scope"]["polygon_ids"]) & set(test.anon_polygon_id):
        raise DataError("Assessment fields entered final fit")
    if (evidence / "external-assessment.json").exists():
        raise DataError("External assessment уже выполнена; повторное использование не нужно")
    frames = {}
    for name, candidate in [("baseline", baseline), ("expanded", model)]:
        reconstructed = reconstruct(test, model=candidate)
        selected = reconstructed.loc[test.is_synthetic_gap].copy()
        submission = selected[KEY + ["reconstructed"]].rename(columns={"reconstructed": "primary_ndvi_pred"})
        write_submission(test, submission, output / f"external-{name}.csv")
        frames[name] = selected
    # Прогнозы и модель зафиксированы до первого чтения истинных значений.
    freeze(
        evidence / "assessment-plan.json",
        {
            "plan_sha256": sha256(evidence / "plan.json"),
            "model_manifest_sha256": sha256(model_path),
            "predictions": {name: sha256(output / f"external-{name}.csv") for name in frames},
            "labels_sha256": plan["hashes"]["assessment_labels"],
        },
    )
    labels = align_truth(test, pd.read_csv(config["assessment_labels"], dtype={key: str for key in KEY}))
    joined = labels.merge(
        frames["baseline"][KEY + ["reconstructed"]].rename(columns={"reconstructed": "baseline"}),
        on=KEY,
        validate="one_to_one",
    ).merge(frames["expanded"][KEY + ["reconstructed", "gap_days", "origin"]], on=KEY, validate="one_to_one")
    scores = {
        name: metrics(joined.truth, joined[column])
        for name, column in [("baseline", "baseline"), ("expanded", "reconstructed")]
    }
    report = {
        "scope": "Local evaluation on user-provided previously unseen test labels; not platform official score",
        "model_id": manifest["model_id"],
        "model_manifest_sha256": sha256(model_path),
        "n": len(joined),
        "aoi_count": joined.anon_polygon_id.nunique(),
        "metrics": scores,
        "bootstrap": paired_bootstrap(joined, joined.baseline, joined.reconstructed),
        "intervals": coverage(joined, model["calibration"]),
        "per_aoi": {
            aoi: {
                "n": len(part),
                "baseline_rmse": metrics(part.truth, part.baseline)["rmse"],
                "expanded_rmse": metrics(part.truth, part.reconstructed)["rmse"],
            }
            for aoi, part in joined.groupby("anon_polygon_id")
        },
        "quality_gate_passed": scores["expanded"]["rmse"] <= scores["baseline"]["rmse"],
        "labels_used_for_fit_selection_or_calibration": False,
    }
    write_json(evidence / "external-assessment.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def publish(config):
    output, evidence = Path(config["output"]), Path(config["evidence"])
    assessment = json.loads((evidence / "external-assessment.json").read_text())
    timing = json.loads((evidence / "inference-timing.json").read_text())
    decision = json.loads((evidence / "development-decision.json").read_text())
    source = output / "model/manifest.json"
    if not (assessment["quality_gate_passed"] and timing["budget_passed"] and decision["accepted"]):
        raise DataError("Не выполнены условия качества или скорости")
    if (
        sha256(source) != assessment["model_manifest_sha256"]
        or sha256(source) != timing["candidate_manifest_sha256"]
    ):
        raise DataError("Проверенная модель отличается от публикуемой")
    if (evidence / "publication.json").exists():
        raise DataError("Публикация уже зафиксирована")
    model, manifest = load_model(source)
    reported_metrics = manifest["metrics"] | {
        "assessment": {"external_user_provided_test": assessment["metrics"]["expanded"]},
        "assessment_status": assessment["scope"],
        "external_interval_assessment": assessment["intervals"],
    }
    published = save_model(
        model,
        "ml/artifacts/final",
        input_path=config["input"],
        metrics=reported_metrics,
        validation_hashes=manifest["validation_hashes"]
        | {"external_assessment": sha256(evidence / "external-assessment.json")},
    )
    if sha256("ml/artifacts/final/model.json") != sha256(output / "model/model.json"):
        raise DataError("При обновлении метаданных изменились веса модели")
    write_json(
        evidence / "publication.json",
        {
            "model_id": published["model_id"],
            "manifest_sha256": sha256("ml/artifacts/final/manifest.json"),
            "evaluated_manifest_sha256": sha256(source),
            "weights_sha256": sha256("ml/artifacts/final/model.json"),
            "weights_unchanged_since_assessment": True,
            "metadata_change": "Attach external assessment metrics without refitting or changing predictions",
        },
    )
    print(f"Опубликован артефакт {published['model_id']}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="ml/configs/expanded-training.yaml")
    parser.add_argument("--stage", choices=["develop", "final", "assess", "publish"], required=True)
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text())
    frame, test, baseline, plan = prepare(config)
    if args.stage == "develop":
        develop(config, frame, plan)
    elif args.stage == "final":
        final_fit(config, frame, plan)
    elif args.stage == "assess":
        assess(config, test, baseline, plan)
    else:
        publish(config)


if __name__ == "__main__":
    main()
