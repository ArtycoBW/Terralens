"""Profile the frozen model and an in-memory cache probe; never change model files.

Run from the repository root. Imports, process startup and output writing are
excluded from timed scopes. The probe only bypasses repeated JSON serialization
of already loaded CatBoost estimators; it does not change features or trees.
"""

from __future__ import annotations

import argparse
import cProfile
import io
import json
import os
import platform
import pstats
import subprocess
import time
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd
from terralens_ml import candidates
from terralens_ml import model as runtime
from terralens_ml.io import canonical_hash, read_csv, sha256, write_json


def summary(values):
    return {
        "n": len(values),
        "median_seconds": float(np.median(values)),
        "min_seconds": float(min(values)),
        "max_seconds": float(max(values)),
        "samples_seconds": values,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="test-dataset.csv")
    parser.add_argument("--model", default="ml/artifacts/final/manifest.json")
    parser.add_argument("--output", required=True)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if args.repeats < 3:
        parser.error("Нужно не менее трёх повторов")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    frame = read_csv(args.input)
    read_seconds = time.perf_counter() - started
    started = time.perf_counter()
    model, manifest = runtime.load_model(args.model)
    load_seconds = time.perf_counter() - started
    started = time.perf_counter()
    reference, origins = runtime.predict_submission(frame, model)
    first_predict_seconds = time.perf_counter() - started
    print("Первый инференс выполнен; измерить повторные запуски", flush=True)

    original_features = runtime.residual_features
    original_predict = runtime.predict_booster
    original_intervals = runtime.apply_intervals
    stages = {}

    def timed(name, function):
        def wrapped(*positional, **keywords):
            tick = time.perf_counter()
            value = function(*positional, **keywords)
            stages.setdefault(name, []).append(time.perf_counter() - tick)
            return value

        return wrapped

    runtime.residual_features = timed("features", original_features)
    runtime.predict_booster = timed("boosters_including_serialization", original_predict)
    runtime.apply_intervals = timed("intervals", original_intervals)
    warm = []
    try:
        for _ in range(args.repeats):
            tick = time.perf_counter()
            result, _ = runtime.predict_submission(frame, model)
            warm.append(time.perf_counter() - tick)
            pd.testing.assert_frame_equal(reference, result, check_exact=True)
    finally:
        runtime.residual_features = original_features
        runtime.predict_booster = original_predict
        runtime.apply_intervals = original_intervals

    estimators = [
        candidates._load_booster(canonical_hash(member), json.dumps(member, separators=(",", ":")))
        for member in [model["boosting"], *model.get("boosting_members", [])]
    ]

    def cached_predict(_model, features):
        return np.mean([estimator.predict(features, thread_count=2) for estimator in estimators], axis=0)

    paired = {"current": [], "preloaded_estimators_probe": []}
    try:
        for repetition in range(args.repeats):
            order = list(paired) if repetition % 2 == 0 else list(reversed(paired))
            for name in order:
                runtime.predict_booster = original_predict if name == "current" else cached_predict
                tick = time.perf_counter()
                result, _ = runtime.predict_submission(frame, model)
                paired[name].append(time.perf_counter() - tick)
                pd.testing.assert_frame_equal(reference, result, check_exact=True)
    finally:
        runtime.predict_booster = original_predict
    print("Парные замеры завершены; выполнить отдельный cProfile", flush=True)
    profiler = cProfile.Profile()
    profiler.runcall(runtime.predict_submission, frame, model)
    stream = io.StringIO()
    pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats("cumulative").print_stats(45)
    (output / "cprofile.txt").write_text(stream.getvalue())
    evidence = {
        "method": "Single process; imports/startup/output excluded; warm model and OS cache; no training",
        "limitations": "Local microbenchmark; 5 repeats do not establish production p95; no network or DB",
        "created_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "git_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "logical_cpus": os.cpu_count(),
        "python": platform.python_version(),
        "dependencies": {name: version(name) for name in ["numpy", "pandas", "scipy", "catboost"]},
        "input_sha256": sha256(args.input),
        "manifest_sha256": sha256(args.model),
        "model_id": manifest["model_id"],
        "input_rows": len(frame),
        "submission_rows": len(reference),
        "polygons": frame.anon_polygon_id.nunique(),
        "origins": origins,
        "first_run": {
            "read_seconds": read_seconds,
            "load_seconds": load_seconds,
            "predict_seconds": first_predict_seconds,
            "total_seconds": read_seconds + load_seconds + first_predict_seconds,
        },
        "warm_predict": summary(warm),
        "stages": {name: summary(values) for name, values in stages.items()},
        "paired_probe": {name: summary(values) for name, values in paired.items()},
        "probe_submission_identical": True,
        "probe_scope": "Research script only; production runtime and model artifact unchanged",
        "script_sha256": sha256(__file__),
    }
    write_json(output / "profiling.json", evidence)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
