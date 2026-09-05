"""Evaluate a frozen model once against a separate user-provided answer file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from terralens_ml.io import KEY, DataError, read_csv, sha256, write_json, write_submission
from terralens_ml.model import load_model, reconstruct
from terralens_ml.uncertainty import coverage
from terralens_ml.validation import metrics
from train_expanded_model import align_truth, freeze


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="test_features.csv")
    parser.add_argument("--labels", default="private_test_ground_truth.csv")
    parser.add_argument("--model", default="ml/artifacts/final/manifest.json")
    parser.add_argument("--training-input", default="train_dataset.csv")
    parser.add_argument("--allow-seen-fields", action="store_true")
    parser.add_argument("--output", required=True)
    parser.add_argument("--submission", default="deliverables/submission-new-test.csv")
    args = parser.parse_args()
    output = Path(args.output)
    if (output / "assessment.json").exists():
        raise DataError("Эта оценка уже выполнена; используйте сохранённый отчёт")
    frame = read_csv(args.input)
    model, manifest = load_model(args.model)
    training_ids = set(model["training_scope"]["polygon_ids"])
    overlapping_ids = sorted(training_ids & set(frame.anon_polygon_id))
    if overlapping_ids and not args.allow_seen_fields:
        raise DataError("Поля нового теста пересекаются с обучением")
    training = read_csv(args.training_input)
    result = reconstruct(frame, model=model).loc[frame.is_synthetic_gap]
    submission = result[KEY + ["reconstructed"]].rename(columns={"reconstructed": "primary_ndvi_pred"})
    write_submission(frame, submission, args.submission)
    plan = {
        "model_id": manifest["model_id"],
        "model_manifest_sha256": sha256(args.model),
        "input_sha256": sha256(args.input),
        "training_input_sha256": sha256(args.training_input),
        "labels_sha256": sha256(args.labels),
        "submission_sha256": sha256(args.submission),
        "selection": "Keep original weights: both development candidates failed prespecified gates",
        "labels_used_for_training_selection_or_calibration": False,
        "training_field_overlap": overlapping_ids,
        "allow_seen_fields": args.allow_seen_fields,
        "script_sha256": sha256(__file__),
    }
    plan_path = output / "assessment-plan.json"
    if plan_path.exists():
        # После технического сбоя можно исправить evaluator, но не входы, модель или прогноз.
        previous = json.loads(plan_path.read_text())
        plan["script_sha256"] = previous["script_sha256"]
    freeze(plan_path, plan)
    # Только после записи неизменного прогноза читаем ответы по явному разрешению пользователя.
    labels = align_truth(frame, pd.read_csv(args.labels, dtype={key: str for key in KEY}))
    known = training.loc[
        training.primary_ndvi.notna()
        & ~training.get("is_synthetic_gap", pd.Series(False, index=training.index)),
        KEY,
    ]
    if len(labels.merge(known, on=KEY, validate="one_to_one")):
        raise DataError("Ответы теста пересекаются с известными целями train")
    evaluated = result.merge(labels, on=KEY, validate="one_to_one")
    report = plan | {
        "evaluation_script_sha256": sha256(__file__),
        "scope": "Local evaluation on user-provided labels; see field overlap; not an official platform score",
        "labels_overlapping_known_training_targets": 0,
        "n": len(evaluated),
        "aoi_count": evaluated.anon_polygon_id.nunique(),
        "metrics": metrics(evaluated.truth, evaluated.reconstructed),
        "intervals": coverage(evaluated, model["calibration"]),
        "field_groups": {
            name: {"aoi_count": part.anon_polygon_id.nunique(), **metrics(part.truth, part.reconstructed)}
            for name, part in (
                ("seen_in_fit", evaluated.loc[evaluated.anon_polygon_id.isin(training_ids)]),
                ("not_seen_in_fit", evaluated.loc[~evaluated.anon_polygon_id.isin(training_ids)]),
            )
            if len(part)
        },
        "per_aoi": {
            name: metrics(part.truth, part.reconstructed)
            for name, part in evaluated.groupby("anon_polygon_id")
        },
    }
    write_json(output / "assessment.json", report)
    write_json(str(args.submission) + ".manifest.json", plan | {"rows": len(submission)})
    print(report["metrics"])
    print(report["intervals"])


if __name__ == "__main__":
    main()
