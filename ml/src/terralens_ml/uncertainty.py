"""Empirical residual intervals; separated spatial calibration and explicit scope."""

from __future__ import annotations

import numpy as np

from .io import DataError


def interval_group(gap, origin):
    if origin == "climatology_fallback":
        return "prior"
    if origin == "extrapolated":
        return "edge"
    return "short" if gap <= 30 else "long"


def calibrate(predictions, *, level=0.9, minimum_group=100):
    if not 0 < level < 1 or predictions.empty:
        raise DataError("Калибровка требует непустую выборку и уровень между 0 и 1")
    errors = abs(predictions.truth.to_numpy() - predictions.reconstructed.to_numpy())
    if not np.isfinite(errors).all():
        raise DataError("Калибровка требует конечных residuals")

    def quantile(values):
        rank = min(len(values), int(np.ceil((len(values) + 1) * level)))
        return float(np.sort(values)[rank - 1])

    result = {
        "method": "empirical_residual",
        "level": level,
        "pooled_radius": quantile(errors),
        "n": len(errors),
        "minimum_group": minimum_group,
        "groups": {},
        "domain": "anonymous_benchmark",
        "unit": "masked_observation",
        "limitations": "Repeated observations within AOI are dependent; no unconditional coverage guarantee",
    }
    groups = [
        interval_group(gap, origin)
        for gap, origin in zip(predictions.gap_days, predictions.origin, strict=True)
    ]
    for group in sorted(set(groups)):
        selected = errors[np.asarray(groups) == group]
        result["groups"][group] = {
            "n": len(selected),
            "radius": quantile(selected) if len(selected) >= minimum_group else result["pooled_radius"],
            "pooled_fallback": len(selected) < minimum_group,
        }
    # Sparse/long context never receives a narrower band than short interpolation.
    short = result["groups"].get("short", {}).get("radius", result["pooled_radius"])
    for group in ["long", "edge", "prior"]:
        if group in result["groups"]:
            result["groups"][group]["radius"] = max(short, result["groups"][group]["radius"])
    return result


def apply_intervals(frame, model, config):
    frame["prediction_interval"] = [
        {"lower": None, "upper": None, "level": None, "method": "not_calibrated"} for _ in range(len(frame))
    ]
    calibration = model.get("calibration")
    if not calibration:
        return frame
    for i, row in frame.iterrows():
        if row.origin in ["observed", "unavailable"] or not np.isfinite(row.reconstructed):
            continue
        group = interval_group(row.gap_days, row.origin)
        radius = calibration["groups"].get(group, {}).get("radius", calibration["pooled_radius"])
        shifted = config.get("interval_domain", "anonymous_benchmark") != calibration["domain"]
        method = calibration["method"] + ("_domain_shift" if shifted else "")
        frame.at[i, "prediction_interval"] = {
            "lower": float(row.reconstructed - radius),
            "upper": float(row.reconstructed + radius),
            "level": calibration["level"],
            "method": method,
        }
        if shifted:
            frame.at[i, "quality_flags"] = list(row.quality_flags) + ["domain_shift"]
    return frame


def coverage(predictions, calibration):
    selected = predictions.copy()
    selected["quality_flags"] = [[] for _ in range(len(selected))]
    selected = apply_intervals(selected, {"calibration": calibration}, {})
    lower = np.array([x["lower"] for x in selected.prediction_interval])
    upper = np.array([x["upper"] for x in selected.prediction_interval])
    truth = selected.truth.to_numpy()
    return {
        "n": len(selected),
        "coverage": float(np.mean((truth >= lower) & (truth <= upper))),
        "mean_width": float(np.mean(upper - lower)),
        "nominal_level": calibration["level"],
    }
