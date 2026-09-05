"""Describe public missingness and existing development errors without fitting models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from terralens_ml.io import read_csv, sha256, write_json
from terralens_ml.model import load_model, reconstruct


def distribution(values):
    return pd.Series(values).value_counts().sort_index().to_dict()


def buckets(values):
    return pd.cut(values, [-1, 8, 30, 60, np.inf], labels=["0-8", "9-30", "31-60", ">60"]).astype(str)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", default="train-dataset.zip")
    parser.add_argument("--test", default="test-dataset.csv")
    parser.add_argument("--model", default="ml/artifacts/final/manifest.json")
    parser.add_argument("--split", default="docs/analysis/crop-dynamics/selection_split.json")
    parser.add_argument("--predictions", default="artifacts/crop-dynamics/predictions.csv")
    parser.add_argument("--candidate", default="dynamics")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    train, test = read_csv(args.train), read_csv(args.test)
    model, _ = load_model(args.model)
    result = reconstruct(test, config={"algorithm": "neighbor_mean"}, model=model)
    mask = test.is_synthetic_gap
    plan = json.loads(Path(args.split).read_text())
    predictions = pd.read_csv(args.predictions)
    predictions = predictions.loc[
        predictions.candidate.eq(args.candidate)
        & predictions.scope.isin(["development_points", "development_blocks"])
    ]
    if predictions.empty:
        raise ValueError("Нет development-прогнозов выбранного кандидата")
    report = {
        "public_test": {
            "rows": len(test),
            "aoi": test.anon_polygon_id.nunique(),
            "queries": int(mask.sum()),
            "visible_primary": int(test.primary_ndvi.notna().sum()),
            "mask_fraction_of_pre_mask_known": float(
                mask.sum() / (mask.sum() + test.primary_ndvi.notna().sum())
            ),
            "query_years": distribution(pd.to_datetime(test.loc[mask, "date"]).dt.year),
            "query_gaps": distribution(buckets(result.loc[mask, "gap_days"])),
            "query_origins": distribution(result.loc[mask, "origin"]),
            "query_aoi_in_fitted_selection": int(
                test.loc[mask, "anon_polygon_id"].isin(plan["selection_ids"]).sum()
            ),
            "query_aoi_in_raw_train": int(
                test.loc[mask, "anon_polygon_id"].isin(train.anon_polygon_id).sum()
            ),
            "query_crops": distribution(test.loc[mask, "crop_type"]),
        },
        "development": {},
        "available_calendar_months": {
            "train": sorted(train.date.str[5:7].unique().tolist()),
            "test": sorted(test.date.str[5:7].unique().tolist()),
        },
        "inputs": {
            "train_sha256": sha256(args.train),
            "test_sha256": sha256(args.test),
            "predictions_path": args.predictions,
            "predictions_sha256": sha256(args.predictions),
            "manifest_sha256": sha256(args.model),
            "split_sha256": sha256(args.split),
            "script_sha256": sha256(__file__),
        },
        "limitations": "Development diagnostics, no new quality experiment or official test labels",
    }
    for scope, part in predictions.groupby("scope"):
        error = part.reconstructed - part.truth
        n_top = int(np.ceil(len(part) * 0.01))
        report["development"][scope] = {
            "n": len(part),
            "gap_distribution": distribution(buckets(part.gap_days)),
            "bias": float(error.mean()),
            "rmse": float(np.sqrt(np.mean(error**2))),
            "top_1pct_count": n_top,
            "top_1pct_squared_error_share": float((error**2).nlargest(n_top).sum() / (error**2).sum()),
            "per_gap": {
                bucket: {
                    "n": len(group),
                    "rmse": float(np.sqrt(np.mean((group.reconstructed - group.truth) ** 2))),
                    "bias": float((group.reconstructed - group.truth).mean()),
                }
                for bucket, group in part.groupby(buckets(part.gap_days))
            },
        }
    write_json(args.output, report)
    print(args.output)


if __name__ == "__main__":
    main()
