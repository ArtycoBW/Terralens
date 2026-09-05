"""Compare the frozen Git runtime with current code, using identical model weights."""

from __future__ import annotations

import argparse
import subprocess
import time
import types
from unittest.mock import patch

import pandas as pd
from terralens_ml import model as runtime
from terralens_ml.io import read_csv, sha256, write_json


def legacy_module(revision, name):
    source = subprocess.check_output(["git", "show", f"{revision}:ml/src/terralens_ml/{name}.py"], text=True)
    module = types.ModuleType(f"terralens_ml._verification_{name}")
    exec(compile(source, f"git:{revision}/{name}.py", "exec"), module.__dict__)
    return module


def verify(inputs, manifest, revision, repeats):
    model, metadata = runtime.load_model(manifest)
    features = legacy_module(revision, "candidates").residual_features
    intervals = legacy_module(revision, "uncertainty").apply_intervals
    result = {}
    for path in inputs:
        frame = read_csv(path)
        current = runtime.reconstruct(frame, model=model)
        with (
            patch.object(runtime, "residual_features", features),
            patch.object(runtime, "apply_intervals", intervals),
        ):
            expected = runtime.reconstruct(frame, model=model)
        pd.testing.assert_frame_equal(expected, current, check_exact=True)
        pd.testing.assert_frame_equal(
            features(expected, model["config"]),
            runtime.residual_features(current, model["config"]),
            check_exact=True,
        )
        samples = {"legacy": [], "optimized": []}
        for repeat in range(repeats):
            for name in list(samples) if repeat % 2 == 0 else list(reversed(samples)):
                with (
                    patch.object(
                        runtime,
                        "residual_features",
                        features if name == "legacy" else runtime.residual_features,
                    ),
                    patch.object(
                        runtime, "apply_intervals", intervals if name == "legacy" else runtime.apply_intervals
                    ),
                ):
                    start = time.perf_counter()
                    actual = runtime.reconstruct(frame, model=model)
                    samples[name].append(time.perf_counter() - start)
                pd.testing.assert_frame_equal(expected, actual, check_exact=True)
        result[path] = {
            "rows": len(frame),
            "sha256": sha256(path),
            "exact_features_and_full_frame": True,
            "samples_seconds": samples,
        }
        print(f"Проверено точное совпадение: {path}", flush=True)
    return {
        "method": "Alternating warm full reconstruct; imports/read/load excluded; same model in both runtimes",
        "baseline_revision": revision,
        "model_id": metadata["model_id"],
        "model_manifest_sha256": sha256(manifest),
        "inputs": result,
        "script_sha256": sha256(__file__),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", nargs="+", default=["test-dataset.csv", "test_features.csv"])
    parser.add_argument("--model", default="artifacts/expanded-training/previous-model/manifest.json")
    parser.add_argument("--revision", default="31f0d97fdd6d8be3c0cc25e837ee681877526faf")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    write_json(args.output, verify(args.inputs, args.model, args.revision, args.repeats))


if __name__ == "__main__":
    main()
