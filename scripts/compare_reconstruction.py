"""Compare fixed reconstruction candidates using development predictions only.

The optional secondary model always uses the preselected rule:
50% candidate + 50% secondary where gap_days > 30, otherwise candidate.
This script does not fit or select models, thresholds, or blend weights.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

SCOPES = ("development_points", "development_blocks")
KEYS = ("scope", "fold", "mask_seed", "anon_polygon_id", "date")
REQUIRED = {*KEYS, "candidate", "truth", "reconstructed", "gap_days"}


def read_development(path, candidate):
    header = pd.read_csv(path, nrows=0)
    if missing := REQUIRED - set(header.columns):
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    frame = pd.read_csv(
        path,
        usecols=lambda column: column in REQUIRED,
        dtype={"anon_polygon_id": str, "date": str, "scope": str, "candidate": str},
    )
    # Assessment, temporal and calibration labels never enter comparisons or selection.
    frame = frame.loc[frame.scope.isin(SCOPES) & frame.candidate.eq(candidate)].copy()
    if set(frame.scope) != set(SCOPES):
        raise ValueError(f"{path}: candidate {candidate!r} must contain both development scopes")
    if frame[list(KEYS)].isna().any().any() or frame.duplicated(list(KEYS)).any():
        raise ValueError(f"{path}: null or duplicated comparison keys")
    for column in ["truth", "reconstructed", "gap_days", "fold", "mask_seed"]:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
        if not np.isfinite(frame[column]).all():
            raise ValueError(f"{path}: non-finite {column}")
    if frame.groupby("anon_polygon_id").fold.nunique().gt(1).any():
        raise ValueError(f"{path}: an AOI belongs to more than one fold")
    return frame.set_index(list(KEYS)).sort_index()


def assert_same_context(reference, candidate, label):
    if not reference.index.equals(candidate.index):
        missing = reference.index.difference(candidate.index).tolist()[:3]
        extra = candidate.index.difference(reference.index).tolist()[:3]
        raise ValueError(f"{label}: comparison keys differ; missing={missing}, extra={extra}")
    for column in ["truth", "gap_days"]:
        if not np.array_equal(reference[column], candidate[column]):
            raise ValueError(f"{label}: {column} differs on the matched comparison keys")


def metrics(truth, prediction):
    error = np.asarray(prediction) - np.asarray(truth)
    return {
        "n": len(error),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "mae": float(np.mean(abs(error))),
        "bias": float(np.mean(error)),
        "p95_absolute_error": float(np.quantile(abs(error), 0.95)),
    }


def paired_bootstrap(frame, reference, candidate, *, repetitions=3000, seed=42):
    values = pd.DataFrame(
        {
            "aoi": frame.anon_polygon_id.to_numpy(),
            "reference_sse": np.square(np.asarray(reference) - frame.truth.to_numpy()),
            "candidate_sse": np.square(np.asarray(candidate) - frame.truth.to_numpy()),
            "n": 1,
        }
    )
    grouped = values.groupby("aoi")[["reference_sse", "candidate_sse", "n"]].sum().to_numpy()
    rng = np.random.default_rng(seed)
    resampled = grouped[rng.integers(len(grouped), size=(repetitions, len(grouped)))].sum(axis=1)
    gains = np.sqrt(resampled[:, 0] / resampled[:, 2]) - np.sqrt(resampled[:, 1] / resampled[:, 2])
    return {
        "aoi_n": len(grouped),
        "repetitions": repetitions,
        "seed": seed,
        "gain_rmse_95_aoi_bootstrap": np.quantile(gains, [0.025, 0.975]).tolist(),
        "bootstrap_fraction_gain_positive": float(np.mean(gains > 0)),
    }


def compare(args):
    baseline = read_development(args.baseline, args.baseline_candidate)
    candidate = read_development(args.candidate, args.candidate_name)
    assert_same_context(baseline, candidate, "candidate")
    aligned = baseline.reset_index()
    predictions = {
        "baseline": baseline.reconstructed.to_numpy(),
        "candidate": candidate.reconstructed.to_numpy(),
    }
    inputs = {
        "baseline": {"path": str(args.baseline), "candidate": args.baseline_candidate},
        "candidate": {"path": str(args.candidate), "candidate": args.candidate_name},
    }
    if args.secondary:
        secondary = read_development(args.secondary, args.secondary_candidate)
        assert_same_context(baseline, secondary, "secondary")
        routed = aligned.gap_days.gt(30).to_numpy()
        predictions["fixed_history_route"] = np.where(
            routed,
            0.5 * predictions["candidate"] + 0.5 * secondary.reconstructed.to_numpy(),
            predictions["candidate"],
        )
        inputs["secondary"] = {"path": str(args.secondary), "candidate": args.secondary_candidate}
    for details in inputs.values():
        details["sha256"] = hashlib.sha256(Path(details["path"]).read_bytes()).hexdigest()
    report = {
        "inputs": inputs,
        "allowed_scopes": SCOPES,
        "comparison_keys": KEYS,
        "matched_rows": len(aligned),
        "truth_and_gap_days_identical": True,
        "routing_rule": "gap_days > 30: 0.5*candidate + 0.5*secondary; otherwise candidate"
        if args.secondary
        else None,
        "selection": "No fitting, threshold search, weight search or model selection performed",
        "scopes": {},
        "folds": {},
        "gap_slices": {},
    }
    rows = []
    for scope, part in aligned.groupby("scope"):
        indices = part.index.to_numpy()
        scores = {name: metrics(part.truth, prediction[indices]) for name, prediction in predictions.items()}
        comparisons = {}
        for name in list(predictions)[1:]:
            comparison = paired_bootstrap(
                part,
                predictions["baseline"][indices],
                predictions[name][indices],
                repetitions=args.bootstrap,
                seed=args.seed,
            )
            comparison["gain_rmse"] = scores["baseline"]["rmse"] - scores[name]["rmse"]
            comparison["relative_rmse_reduction"] = comparison["gain_rmse"] / scores["baseline"]["rmse"]
            comparisons[name + "_vs_baseline"] = comparison
        if args.secondary:
            comparison = paired_bootstrap(
                part,
                predictions["candidate"][indices],
                predictions["fixed_history_route"][indices],
                repetitions=args.bootstrap,
                seed=args.seed,
            )
            comparison["gain_rmse"] = scores["candidate"]["rmse"] - scores["fixed_history_route"]["rmse"]
            comparisons["fixed_history_route_vs_candidate"] = comparison
        report["scopes"][scope] = {"metrics": scores, "comparisons": comparisons}
        rows.extend({"scope": scope, "variant": name, **score} for name, score in scores.items())
    for fold, validation in aligned.groupby("fold"):
        report["folds"][str(fold)] = {"aoi_ids": sorted(validation.anon_polygon_id.unique()), "scopes": {}}
        for scope, part in validation.groupby("scope"):
            result = {
                name: metrics(part.truth, prediction[part.index]) for name, prediction in predictions.items()
            }
            report["folds"][str(fold)]["scopes"][scope] = result
    bins = pd.cut(aligned.gap_days, [-1, 8, 30, 60, np.inf], labels=["0-8", "9-30", "31-60", ">60"])
    for (scope, bucket), part in aligned.groupby([aligned.scope, bins], observed=True):
        report["gap_slices"][str(scope) + "/" + str(bucket)] = {
            name: metrics(part.truth, prediction[part.index]) for name, prediction in predictions.items()
        }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    pd.DataFrame(rows).to_csv(args.output / "metrics.csv", index=False)
    print(pd.DataFrame(rows).pivot(index="variant", columns="scope", values="rmse").round(6).to_string())
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--baseline-candidate", default="m5_without_weather")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-name", required=True)
    parser.add_argument("--secondary", type=Path)
    parser.add_argument("--secondary-candidate", default="m4")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.bootstrap < 100:
        parser.error("--bootstrap must be at least 100")
    try:
        compare(args)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Comparison failed: {exc}\n")


if __name__ == "__main__":
    main()
