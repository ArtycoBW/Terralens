"""Research-only interval implementation; verify full output parity before timing."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
from profile_reconstruction import summary
from terralens_ml import model as runtime
from terralens_ml.io import read_csv, sha256, write_json


def array_intervals(frame, model, config):
    intervals = [
        {"lower": None, "upper": None, "level": None, "method": "not_calibrated"} for _ in range(len(frame))
    ]
    calibration = model.get("calibration")
    if not calibration:
        frame["prediction_interval"] = intervals
        return frame
    values = frame.reconstructed.to_numpy()
    origins = frame.origin.to_numpy()
    groups = np.where(
        origins == "climatology_fallback",
        "prior",
        np.where(
            origins == "extrapolated", "edge", np.where(frame.gap_days.to_numpy() <= 30, "short", "long")
        ),
    )
    usable = ~np.isin(origins, ["observed", "unavailable"]) & np.isfinite(values)
    shifted = config.get("interval_domain", "anonymous_benchmark") != calibration["domain"]
    method = calibration["method"] + ("_domain_shift" if shifted else "")
    flags = frame.quality_flags.to_list()
    for position in np.flatnonzero(usable):
        radius = calibration["groups"].get(groups[position], {}).get("radius", calibration["pooled_radius"])
        intervals[position] = {
            "lower": float(values[position] - radius),
            "upper": float(values[position] + radius),
            "level": calibration["level"],
            "method": method,
        }
        if shifted:
            flags[position] = list(flags[position]) + ["domain_shift"]
    frame["prediction_interval"] = intervals
    if shifted:
        frame["quality_flags"] = flags
    return frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="test-dataset.csv")
    parser.add_argument("--model", default="ml/artifacts/final/manifest.json")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    frame = read_csv(args.input)
    model, manifest = runtime.load_model(args.model)
    reference = runtime.reconstruct(frame, model=model)
    original = runtime.apply_intervals
    for config, calibration_model in [({}, model), ({"interval_domain": "live"}, model), ({}, {})]:
        expected = original(reference.copy(deep=True), calibration_model, config)
        actual = array_intervals(reference.copy(deep=True), calibration_model, config)
        pd.testing.assert_frame_equal(expected, actual, check_exact=True)
    # Check unavailable, nonfinite, unknown groups and nonstandard indices explicitly.
    fixture = pd.DataFrame(
        {
            "origin": ["observed", "unavailable", "extrapolated", "climatology_fallback", "interpolated"] * 2,
            "gap_days": [0, 15, 14, 65, 31] * 2,
            "reconstructed": [0.2, np.nan, 0.4, 0.5, 0.6, 0.2, np.inf, np.nan, -0.1, 0.7],
            "quality_flags": [["existing"] for _ in range(10)],
        },
        index=np.arange(10) * 3 + 7,
    )
    for config in [{}, {"interval_domain": "live"}]:
        pd.testing.assert_frame_equal(
            original(fixture.copy(deep=True), model, config),
            array_intervals(fixture.copy(deep=True), model, config),
            check_exact=True,
        )
    samples = {"current": [], "array_intervals_probe": []}
    try:
        for repetition in range(3):
            order = list(samples) if repetition % 2 == 0 else list(reversed(samples))
            for name in order:
                runtime.apply_intervals = original if name == "current" else array_intervals
                started = time.perf_counter()
                actual = runtime.reconstruct(frame, model=model)
                samples[name].append(time.perf_counter() - started)
                pd.testing.assert_frame_equal(reference, actual, check_exact=True)
    finally:
        runtime.apply_intervals = original
    output = Path(args.output)
    write_json(
        output,
        {
            "method": "3 alternating warm full-reconstruct runs per variant; imports/read/load excluded",
            "scope": "Research-only monkeypatch; no production source or model changes",
            "full_frame_parity": True,
            "checked_rows": len(reference),
            "additional_parity": [
                "live domain shift",
                "no calibration",
                "unavailable/nonfinite",
                "custom index",
            ],
            "model_id": manifest["model_id"],
            "input_sha256": sha256(args.input),
            "manifest_sha256": sha256(args.model),
            "script_sha256": sha256(__file__),
            "timings": {name: summary(values) for name, values in samples.items()},
            "limitations": "Local microbenchmark; no production p95, network, DB or retraining",
        },
    )
    print(output.read_text())


if __name__ == "__main__":
    main()
