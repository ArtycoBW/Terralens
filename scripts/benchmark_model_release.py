"""Alternate legacy baseline, optimized baseline and candidate on the same CPU."""

from __future__ import annotations

import argparse
import platform
import time
from unittest.mock import patch

import numpy as np
from terralens_ml import model as runtime
from terralens_ml.io import read_csv, sha256, write_json
from verify_runtime_optimization import legacy_module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="artifacts/expanded-training/previous-model/manifest.json")
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--inputs", nargs="+", default=["test-dataset.csv", "test_features.csv"])
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    baseline, _ = runtime.load_model(args.baseline)
    candidate, _ = runtime.load_model(args.candidate)
    revision = "31f0d97fdd6d8be3c0cc25e837ee681877526faf"
    legacy_features = legacy_module(revision, "candidates").residual_features
    legacy_intervals = legacy_module(revision, "uncertainty").apply_intervals
    current_features, current_intervals = runtime.residual_features, runtime.apply_intervals
    report = {
        "method": "Alternating warm full reconstruct; imports, read/load and output excluded; two CatBoost threads",
        "limitations": "Local microbenchmark, not production p95 or ingestion latency",
        "platform": platform.platform(),
        "python": platform.python_version(),
        "baseline_manifest_sha256": sha256(args.baseline),
        "candidate_manifest_sha256": sha256(args.candidate),
        "script_sha256": sha256(__file__),
        "inputs": {},
    }
    for path in args.inputs:
        frame = read_csv(path)
        runtime.reconstruct(frame, model=baseline)
        runtime.reconstruct(frame, model=candidate)
        samples = {"legacy_baseline": [], "optimized_baseline": [], "optimized_candidate": []}
        for repeat in range(args.repeats):
            order = list(samples)
            order = order[repeat % 3 :] + order[: repeat % 3]
            for name in order:
                legacy = name == "legacy_baseline"
                with (
                    patch.object(
                        runtime, "residual_features", legacy_features if legacy else current_features
                    ),
                    patch.object(
                        runtime, "apply_intervals", legacy_intervals if legacy else current_intervals
                    ),
                ):
                    start = time.perf_counter()
                    runtime.reconstruct(frame, model=candidate if name == "optimized_candidate" else baseline)
                    samples[name].append(time.perf_counter() - start)
        medians = {name: float(np.median(values)) for name, values in samples.items()}
        report["inputs"][path] = {
            "rows": len(frame),
            "input_sha256": sha256(path),
            "samples_seconds": samples,
            "median_seconds": medians,
            "budget_ratio": medians["optimized_candidate"] / medians["legacy_baseline"],
        }
        print(f"{path}: {medians}", flush=True)
    report["budget_passed"] = all(item["budget_ratio"] <= 1.25 for item in report["inputs"].values())
    write_json(args.output, report)


if __name__ == "__main__":
    main()
