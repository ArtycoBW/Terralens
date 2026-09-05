"""CPU candidates; every feature is rebuilt from the masked inference context."""

from __future__ import annotations

import json
import tempfile
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.linalg import spsolve

from .io import SENSORS, canonical_hash


def robust_smooth(x, y, query, *, strength=20.0, robust=True):
    """Daily Whittaker second differences, with optional Huber reweighting."""
    days = np.arange(int(x[0]), int(x[-1]) + 1)
    positions = (x - days[0]).astype(int)
    values = np.zeros(len(days))
    values[positions] = y
    weights = np.zeros(len(days))
    weights[positions] = 1
    if len(days) < 3:
        return np.interp(query, x, y)
    differences = sparse.diags(
        [np.ones(len(days) - 2), -2 * np.ones(len(days) - 2), np.ones(len(days) - 2)],
        [0, 1, 2],
        shape=(len(days) - 2, len(days)),
    )
    penalty = strength * (differences.T @ differences)
    for _ in range(4 if robust else 1):
        smooth = spsolve((sparse.diags(weights) + penalty).tocsc(), weights * values)
        residual = y - smooth[positions]
        scale = max(0.01, 1.4826 * np.median(abs(residual - np.median(residual))))
        weights[positions] = np.minimum(1, 1.5 * scale / np.maximum(abs(residual), 1e-12))
    return np.interp(query, days, smooth)


def seasonal_history(frame, part, *, minimum_years=3, window=15):
    """Only earlier seasons of this field and crop; never the current season."""
    history = frame.loc[
        (frame.anon_polygon_id == part.anon_polygon_id.iloc[0])
        & (frame._season < part._season.iloc[0])
        & frame.clean_primary.notna()
    ]
    crop = part.crop_type.iloc[0]
    history = history.loc[history.crop_type.eq(crop)]
    if history._season.nunique() < minimum_years:
        return None
    query = pd.to_datetime("2000-" + pd.to_datetime(part.date).dt.strftime("%m-%d")).dt.dayofyear.to_numpy()
    history_day = pd.to_datetime("2000-" + pd.to_datetime(history.date).dt.strftime("%m-%d")).dt.dayofyear
    annual = []
    for _, year in history.groupby("_season"):
        distances = abs(query[:, None] - history_day.loc[year.index].to_numpy()[None, :])
        eligible = np.minimum(distances, 366 - distances) <= window
        values = np.broadcast_to(year.clean_primary.to_numpy(), eligible.shape).copy()
        values[~eligible] = np.nan
        # pandas median handles entirely missing windows without numpy warnings.
        annual.append(pd.DataFrame(values.T).median().to_numpy())
    annual = np.asarray(annual)
    result = pd.DataFrame(annual).median().to_numpy()
    result[np.isfinite(annual).sum(axis=0) < minimum_years] = np.nan
    return result


def residual_features(result, config):
    """Calendar/local support and adjacent available sensors/weather, with no AOI ID."""
    dates = pd.to_datetime(result.date)
    features = pd.DataFrame(index=result.index)
    features["base"] = result.reconstructed
    features["support"] = result.support_count
    features["gap"] = result.gap_days
    features["sin_doy"] = np.sin(2 * np.pi * dates.dt.dayofyear / 366)
    features["cos_doy"] = np.cos(2 * np.pi * dates.dt.dayofyear / 366)
    features["fallback"] = result.origin.eq("climatology_fallback").astype(float)
    columns = []
    if config.get("use_sensors", True):
        columns += SENSORS
    if config.get("use_weather", True):
        columns += ["era5_temp_c", "era5_precip_mm"]
    season = dates.dt.year - (dates.dt.month < config["season_start_month"]).astype(int)
    for column in columns:
        features[column] = np.nan
    for _, part in result.groupby([result.anon_polygon_id, season], sort=False):
        part = part.sort_values("date")
        days = pd.to_datetime(part.date).to_numpy(dtype="datetime64[D]").astype(np.int64)
        for column in columns:
            if column not in part:
                continue
            values = pd.to_numeric(part[column], errors="coerce").to_numpy(dtype=float)
            valid = np.isfinite(values)
            if column.endswith("ndvi") or column.endswith("ndwi"):
                valid &= abs(values) <= 1
            elif column.endswith("evi"):
                valid &= abs(values) <= 2  # bounded clean feature; raw inputs are preserved
            if not valid.any():
                continue
            positions = np.searchsorted(days[valid], days)
            left = np.maximum(positions - 1, 0)
            right = np.minimum(positions, valid.sum() - 1)
            distance = np.minimum(abs(days - days[valid][left]), abs(days[valid][right] - days))
            estimate = np.interp(days, days[valid], values[valid])
            estimate[distance > 14] = np.nan
            features.loc[part.index, column] = estimate
    # Missing features stay missing: CatBoost handles them explicitly.
    return features


def train_booster(features, residual, config):
    from catboost import CatBoostRegressor

    estimator = CatBoostRegressor(
        iterations=config.get("boost_iterations", 160),
        depth=4,
        learning_rate=0.04,
        l2_leaf_reg=10,
        loss_function="RMSE",
        random_seed=config["seed"],
        thread_count=2,
        verbose=False,
        allow_writing_files=False,
    )
    estimator.fit(features, residual)
    with tempfile.TemporaryDirectory(prefix="terralens-model-") as directory:
        path = Path(directory) / "boost.json"
        estimator.save_model(str(path), format="json")
        return json.loads(path.read_text())


@lru_cache(maxsize=8)
def _load_booster(key, payload):
    from catboost import CatBoostRegressor

    estimator = CatBoostRegressor(thread_count=2)
    with tempfile.TemporaryDirectory(prefix="terralens-model-") as directory:
        path = Path(directory) / "boost.json"
        path.write_text(payload)
        estimator.load_model(str(path), format="json")
    return estimator


def predict_booster(model, features):
    payload = json.dumps(model["boosting"], separators=(",", ":"))
    estimator = _load_booster(canonical_hash(model["boosting"]), payload)
    return estimator.predict(features, thread_count=2)
