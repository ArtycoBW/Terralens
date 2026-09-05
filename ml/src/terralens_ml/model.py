"""Базовые ретроспективные модели и проверяемые JSON-артефакты."""

from __future__ import annotations

import json
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator

from .candidates import predict_booster, residual_features, robust_smooth, seasonal_history, train_booster
from .io import KEY, DataError, canonical_hash, mask_context, parse_bool, sha256, write_json
from .uncertainty import apply_intervals

DEFAULT_CONFIG = {
    "algorithm": "linear",
    "max_gap_days": 60,
    "max_edge_days": 14,
    "season_start_month": 1,
    "clip": False,
    "seed": 42,
    "quality_filter": True,
    "smoothing_strength": 20.0,
    "robust": True,
    "use_history": True,
    "use_weather": True,
    "use_sensors": True,
}
ALGORITHMS = ("neighbor_mean", "linear", "pchip", "robust_smoother", "history_residual", "catboost_residual")


def checked_config(config=None):
    result = DEFAULT_CONFIG | (config or {})
    if result["algorithm"] not in ALGORITHMS:
        raise DataError(f"Неизвестная модель: {result['algorithm']}")
    if (
        not isinstance(result["season_start_month"], int)
        or not 1 <= result["season_start_month"] <= 12
        or result["max_gap_days"] < 1
        or result["max_edge_days"] < 0
        or not np.isfinite(result["smoothing_strength"])
        or result["smoothing_strength"] <= 0
    ):
        raise DataError("Некорректные параметры сезона или длины пропуска")
    for name in ["clip", "quality_filter", "robust", "use_history", "use_sensors", "use_weather"]:
        if not isinstance(result[name], bool):
            raise DataError(f"{name} должен быть boolean")
    return result


def fit(training_context: pd.DataFrame, config=None) -> dict:
    config = checked_config(config)
    training_context = mask_context(
        training_context,
        training_context.get("is_synthetic_gap", pd.Series(False, index=training_context.index)),
    )
    valid = (
        training_context.primary_ndvi.between(-1, 1)
        if config["quality_filter"]
        else np.isfinite(training_context.primary_ndvi)
    )
    frame = training_context.loc[valid].copy()
    if frame.empty:
        raise DataError("В train нет пригодных известных целей для обучения prior")
    frame["month"] = pd.to_datetime(frame.date).dt.month
    model = {
        "schema_version": 1,
        "config": config,
        "global_median": float(frame.primary_ndvi.median()),
        "monthly": {str(k): float(v) for k, v in frame.groupby("month").primary_ndvi.median().items()},
        "crop_monthly": {
            f"{crop}|{month}": float(v)
            for (crop, month), v in frame.groupby(["crop_type", "month"]).primary_ndvi.median().items()
        },
        "training_rows": int(valid.sum()),
        "excluded_targets": int(training_context.primary_ndvi.notna().sum() - valid.sum()),
        "supported_modes": ["retrospective"],
    }
    if config["algorithm"] == "catboost_residual":
        rng = np.random.default_rng(config["seed"])
        mask = pd.Series(False, index=training_context.index)
        for _, part in training_context.loc[valid].groupby(
            ["anon_polygon_id", pd.to_datetime(training_context.loc[valid].date).dt.year], sort=True
        ):
            indices = rng.choice(part.index, max(1, round(len(part) * 0.2)), replace=False)
            mask.loc[indices] = True
        context = mask_context(training_context, mask)
        base = reconstruct(context, {"algorithm": "neighbor_mean"}, model)
        features = residual_features(base, config)
        model["boosting"] = train_booster(
            features.loc[mask],
            training_context.loc[mask, "primary_ndvi"] - base.loc[mask, "reconstructed"],
            config,
        )
        model["feature_names"] = features.columns.tolist()
    return model


def save_model(model, directory, *, input_path=None, metrics=None, validation_hashes=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / "model.json", model)
    revision = (
        subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        or "unknown"
    )
    locks = [Path.cwd() / "uv.lock", Path(__file__).resolve().parents[3] / "uv.lock"]
    lock = next((path for path in locks if path.is_file()), locks[0])
    manifest = {
        "schema_version": 1,
        "model_id": canonical_hash(model)[:16],
        "version": "0.1.0",
        "created_at": datetime.now(UTC).isoformat(),
        "git_revision": revision,
        "source_sha256": canonical_hash(
            {
                str(path.relative_to(Path(__file__).parent)): sha256(path)
                for path in sorted(Path(__file__).parent.glob("*.py"))
            }
        ),
        "python": platform.python_version(),
        "dependency_lock_sha256": sha256(lock) if lock.exists() else None,
        "input_sha256": sha256(input_path) if input_path else None,
        "files": {"model.json": sha256(directory / "model.json")},
        "config": model["config"],
        "feature_schema": model.get("feature_names", "neighbors-calendar-crop-v2"),
        "target_filter": "fit finite NDVI in [-1,1]; evaluate unchanged targets"
        if model["config"].get("quality_filter", True)
        else "fit all finite raw targets; evaluate unchanged targets",
        "training_scope": model.get("training_scope"),
        "postprocessing": {"clip": model["config"]["clip"], "preserve_clean_observations": True},
        "supported_modes": model["supported_modes"],
        "metrics": metrics,
        "validation_hashes": validation_hashes,
        "calibration": model.get("calibration", "not_calibrated"),
        "external_datasets": [],
        "external_models": [],
    }
    # Новый manifest — отдельная версия, даже если веса совпали; история run остаётся точной.
    manifest["model_id"] = canonical_hash(manifest)[:16]
    write_json(directory / "manifest.json", manifest)
    return manifest


def load_model(manifest_path):
    manifest_path = Path(manifest_path)
    try:
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("schema_version") != 1 or set(manifest.get("files", {})) != {"model.json"}:
            raise DataError("Несовместимая схема артефакта модели")
        path = manifest_path.parent / "model.json"
        if path.is_symlink() or sha256(path) != manifest["files"]["model.json"]:
            raise DataError("Контрольная сумма модели не совпадает")
        model = json.loads(path.read_text())
        if model["schema_version"] != 1 or not np.isfinite(model["global_median"]):
            raise DataError("Некорректная модель")
        checked_config(model["config"])
        for name in ["monthly", "crop_monthly"]:
            if not isinstance(model[name], dict) or not all(
                np.isfinite(value) for value in model[name].values()
            ):
                raise DataError("Некорректные сезонные priors модели")
        if model["config"]["algorithm"] == "catboost_residual" and not model.get("boosting"):
            raise DataError("В артефакте отсутствует CatBoost модель")
        calibration = model.get("calibration")
        if calibration:
            radii = [calibration["pooled_radius"]] + [
                group["radius"] for group in calibration["groups"].values()
            ]
            if not 0 < calibration["level"] < 1 or not all(np.isfinite(x) and x >= 0 for x in radii):
                raise DataError("Некорректная калибровка модели")
        return model, manifest
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise DataError(f"Не удалось загрузить артефакт: {manifest_path}") from exc


def reconstruct(series: pd.DataFrame, config=None, model=None) -> pd.DataFrame:
    if model is None:
        raise DataError("Модель отсутствует; передайте проверенный артефакт")
    config = checked_config(model["config"] | (config or {}))
    if config.get("mode", "retrospective") != "retrospective":
        raise DataError("Модель поддерживает только retrospective")
    if series.duplicated(KEY).any():
        raise DataError("Повторяется ключ ряда")
    frame = mask_context(
        series, series.get("is_synthetic_gap", pd.Series(False, index=series.index))
    ).reset_index(drop=True)
    dates = pd.to_datetime(frame.date)
    frame["_day"] = dates.to_numpy(dtype="datetime64[D]").astype(np.int64)
    frame["_season"] = dates.dt.year - (dates.dt.month < config["season_start_month"]).astype(int)
    frame["observed_primary"] = frame.primary_ndvi
    valid = frame.primary_ndvi.between(-1, 1) if config["quality_filter"] else np.isfinite(frame.primary_ndvi)
    frame["clean_primary"] = frame.primary_ndvi.where(valid)
    values = np.full(len(frame), np.nan)
    origins = np.full(len(frame), "unavailable", dtype=object)
    supports = np.zeros(len(frame), dtype=int)
    gaps = np.zeros(len(frame), dtype=int)
    flags = [[] for _ in range(len(frame))]
    for _, part in frame.groupby(["anon_polygon_id", "_season"], sort=False):
        part = part.sort_values("_day")
        index = part.index.to_numpy()
        query = part._day.to_numpy()
        visible = part.loc[part.clean_primary.notna()]
        x, y = visible._day.to_numpy(), visible.clean_primary.to_numpy()
        months = pd.to_datetime(part.date).dt.month
        estimate = np.array(
            [
                model["crop_monthly"].get(
                    f"{crop}|{month}", model["monthly"].get(str(month), model["global_median"])
                )
                for crop, month in zip(part.crop_type, months, strict=True)
            ]
        )
        origin = np.full(len(part), "climatology_fallback", dtype=object)
        support = np.zeros(len(part), dtype=int)
        gap = np.zeros(len(part), dtype=int)
        if len(x):
            pos = np.searchsorted(x, query)
            left, right = np.maximum(pos - 1, 0), np.minimum(pos, len(x) - 1)
            has_left, has_right = pos > 0, pos < len(x)
            dl, dr = np.where(has_left, query - x[left], 0), np.where(has_right, x[right] - query, 0)
            gap = dl + dr
            support = has_left.astype(int) + has_right.astype(int)
            inside = has_left & has_right & (gap <= config["max_gap_days"])
            edge = (support == 1) & (gap <= config["max_edge_days"])
            if config["algorithm"] in ["neighbor_mean", "catboost_residual"]:
                estimate[inside] = (y[left[inside]] + y[right[inside]]) / 2
            elif config["algorithm"] == "pchip" and len(x) >= 2:
                estimate[inside] = PchipInterpolator(x, y, extrapolate=False)(query[inside])
            elif config["algorithm"] == "robust_smoother" and len(x) >= 3:
                estimate[inside] = robust_smooth(
                    x, y, query[inside], strength=config["smoothing_strength"], robust=config["robust"]
                )
            else:
                estimate[inside] = np.interp(query[inside], x, y)
            estimate[edge] = np.interp(query[edge], x, y)
            origin[inside], origin[edge] = "interpolated", "extrapolated"
        if config["algorithm"] == "history_residual" and config["use_history"]:
            history = seasonal_history(frame, part)
            if history is not None:
                available = np.isfinite(history)
                residual_valid = part.clean_primary.notna().to_numpy() & available
                residual = part.clean_primary.to_numpy() - history
                if residual_valid.any():
                    correction = np.interp(query, query[residual_valid], residual[residual_valid])
                    estimate[available] = history[available] + correction[available]
                else:
                    estimate[available] = history[available]
                # Public origin remains stable; provenance is recorded in quality_flags below.
        observed = part.clean_primary.notna().to_numpy()
        if config["clip"]:
            estimate[~observed] = np.clip(estimate[~observed], -1, 1)
        estimate[observed] = part.clean_primary.to_numpy()[observed]
        origin[observed], support[observed], gap[observed] = "observed", 1, 0
        values[index], origins[index], supports[index], gaps[index] = estimate, origin, support, gap
        raw = part.observed_primary.to_numpy()
        synthetic = part.get("is_synthetic_gap", pd.Series(False, index=part.index)).to_numpy()
        for position, i in enumerate(index):
            if observed[position]:
                continue
            current = ["invalid_value" if pd.notna(raw[position]) else "input_nan"]
            if synthetic[position]:
                current.append("synthetic_mask")
            if support[position] < 2:
                current.append("edge_gap")
            if gap[position] > config["max_gap_days"]:
                current.append("long_gap")
            if origin[position] in ["climatology_fallback", "history_fallback"]:
                current.append("low_support")
            if config["algorithm"] == "history_residual" and config["use_history"] and history is not None:
                if np.isfinite(history[position]):
                    current.append("aoi_history")
            flags[i] = current
    frame["reconstructed"], frame["origin"] = values, origins
    frame["support_count"], frame["gap_days"], frame["quality_flags"] = supports, gaps, flags
    if config["algorithm"] == "catboost_residual" and "boosting" in model and len(frame):
        features = residual_features(frame, config)
        correction = predict_booster(model, features[model["feature_names"]])
        missing = frame.origin.ne("observed")
        frame.loc[missing, "reconstructed"] += correction[missing]
        if config["clip"]:
            frame.loc[missing, "reconstructed"] = frame.loc[missing, "reconstructed"].clip(-1, 1)
    frame = apply_intervals(frame, model, config)
    return frame.drop(columns=["_day", "_season"]).set_axis(series.index)


def predict_submission(test, model, optional_reference_history=None):
    if "is_synthetic_gap" not in test:
        raise DataError("Для submission требуется is_synthetic_gap")
    context = test.copy()
    if optional_reference_history is not None:
        if len(test[KEY].merge(optional_reference_history[KEY], on=KEY)):
            raise DataError("Reference history пересекается с test по ключам")
        history = optional_reference_history.copy()
        history["is_synthetic_gap"] = history.get("is_synthetic_gap", pd.Series(False, index=history.index))
        context = pd.concat([context, history], ignore_index=True)
    result = reconstruct(context, model=model).iloc[: len(test)]
    mask = parse_bool(test.is_synthetic_gap).to_numpy()
    submission = result.loc[mask, KEY + ["reconstructed"]].rename(
        columns={"reconstructed": "primary_ndvi_pred"}
    )
    return submission, result.loc[mask, "origin"].value_counts().to_dict()
