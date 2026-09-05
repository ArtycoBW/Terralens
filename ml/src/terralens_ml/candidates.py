"""CPU-модели: все признаки пересчитываются после маскирования контекста."""

from __future__ import annotations

import json
import tempfile
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.interpolate import PchipInterpolator
from scipy.sparse.linalg import spsolve

from .io import SENSORS, DataError, canonical_hash

NDVI_SENSORS = ["s2_ndvi", "landsat_ndvi", "modis_ndvi"]
SENSOR_DYNAMICS = [
    "left_value",
    "left_days",
    "right_value",
    "right_days",
    "slope",
    "primary_bias",
    "paired_count",
    "adjusted_estimate",
]


def field_season_segments(frame, season_start_month):
    """Разделить поле и сезон на непрерывные по времени отрезки одной культуры."""
    dates = pd.to_datetime(frame.date)
    seasons = dates.dt.year - (dates.dt.month < season_start_month).astype(int)
    for _, part in frame.groupby([frame.anon_polygon_id, seasons], sort=False):
        ordered = part.iloc[np.argsort(pd.to_datetime(part.date).to_numpy(), kind="stable")]
        # Возврат к прежней культуре после другой культуры начинает новый отрезок.
        # Все отсутствующие значения культуры имеют один код, отличный от строк.
        crops, _ = pd.factorize(ordered.crop_type, sort=False)
        segments = np.cumsum(np.r_[True, crops[1:] != crops[:-1]])
        for _, segment in ordered.groupby(segments, sort=False):
            yield segment


def robust_smooth(x, y, query, *, strength=20.0, robust=True):
    """Дневное сглаживание Уиттекера по вторым разностям с необязательными весами Хьюбера."""
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
    """Только предыдущие сезоны того же поля и культуры, без текущего сезона."""
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
        # Медиана pandas обрабатывает полностью пустые окна без предупреждений numpy.
        annual.append(pd.DataFrame(values.T).median().to_numpy())
    annual = np.asarray(annual)
    result = pd.DataFrame(annual).median().to_numpy()
    result[np.isfinite(annual).sum(axis=0) < minimum_years] = np.nan
    return result


def residual_features(result, config, *, alignment=None):
    """Календарь, локальный контекст и доступные соседние сенсоры/погода, без ID поля."""
    dates = pd.to_datetime(result.date)
    features = {
        "base": result.reconstructed.to_numpy(),
        "support": result.support_count.to_numpy(),
        "gap": result.gap_days.to_numpy(),
        "sin_doy": np.sin(2 * np.pi * dates.dt.dayofyear.to_numpy() / 366),
        "cos_doy": np.cos(2 * np.pi * dates.dt.dayofyear.to_numpy() / 366),
        "fallback": result.origin.eq("climatology_fallback").to_numpy(dtype=float),
    }
    if config.get("crop_features", False):
        features["crop_type"] = result.crop_type.fillna("<unknown>").astype(str).to_numpy()
    columns = []
    if config.get("use_sensors", True):
        columns += SENSORS
    if config.get("use_weather", True):
        columns += ["era5_temp_c", "era5_precip_mm"]
    for column in columns:
        features[column] = np.full(len(result), np.nan)
        if config.get("context_quality", False):
            features[f"{column}_age"] = np.full(len(result), np.nan)
            features[f"{column}_span"] = np.full(len(result), np.nan)
        if config.get("sensor_dynamics", False) and column in NDVI_SENSORS:
            for name in SENSOR_DYNAMICS:
                features[f"{column}_{name}"] = np.full(len(result), np.nan)
    # Один DataFrame в конце вместо тысяч .loc-присваиваний; индекс результата неизменен.
    for part in field_season_segments(result.reset_index(drop=True), config["season_start_month"]):
        positions = part.index.to_numpy()
        days = pd.to_datetime(part.date).to_numpy(dtype="datetime64[D]").astype(np.int64)
        if config.get("local_features", False):
            local = local_shape_features(
                days,
                part.clean_primary.to_numpy(dtype=float),
                transitions=config.get("transition_features", False),
            )
            for name, values in local.items():
                if name not in features:
                    features[name] = np.full(len(result), np.nan)
                features[name][positions] = values
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
            neighbors = np.searchsorted(days[valid], days)
            left = np.maximum(neighbors - 1, 0)
            right = np.minimum(neighbors, valid.sum() - 1)
            distance = np.minimum(abs(days - days[valid][left]), abs(days[valid][right] - days))
            estimate = np.interp(days, days[valid], values[valid])
            estimate[distance > 14] = np.nan
            features[column][positions] = estimate
            if config.get("context_quality", False):
                features[f"{column}_age"][positions] = distance
                features[f"{column}_span"][positions] = days[valid][right] - days[valid][left]
            if config.get("sensor_dynamics", False) and column in NDVI_SENSORS:
                dynamics = sensor_dynamics_features(
                    days, np.where(valid, values, np.nan), part.clean_primary.to_numpy(dtype=float), estimate
                )
                for name, values in dynamics.items():
                    features[f"{column}_{name}"][positions] = values
        if config.get("sensor_alignment", False):
            if alignment is None:
                raise DataError("Для межсенсорных признаков нужна обученная калибровка")
            aligned = alignment_features(part, days, alignment, config.get("alignment_shrinkage", 8))
            aligned["landsat_as_s2"] = features["landsat_ndvi"][positions] + aligned["s2_landsat_bias"]
            aligned["s2_as_landsat"] = features["s2_ndvi"][positions] - aligned["s2_landsat_bias"]
            for name, values in aligned.items():
                if name not in features:
                    features[name] = np.full(len(result), np.nan)
                features[name][positions] = values
    features = pd.DataFrame(features, index=result.index)
    if config.get("context_quality", False) and config.get("use_sensors", True):
        ndvi = features[["s2_ndvi", "landsat_ndvi", "modis_ndvi"]]
        features["sensor_count"] = ndvi.count(axis=1)
        features["sensor_range"] = ndvi.max(axis=1) - ndvi.min(axis=1)
        features["sensor_std"] = ndvi.std(axis=1, ddof=0)
    # Пропуски в признаках сохраняются: CatBoost обрабатывает их явно.
    return features


def sensor_pairs(frame):
    """Independent co-observations; never compare a sensor to primary made from itself."""
    s2 = frame.get("s2_ndvi", pd.Series(np.nan, index=frame.index))
    landsat = frame.get("landsat_ndvi", pd.Series(np.nan, index=frame.index))
    return (s2 - landsat).where(s2.between(-1, 1) & landsat.between(-1, 1))


def fit_sensor_alignment(frame):
    differences = sensor_pairs(frame)
    medians = differences.groupby(frame.anon_polygon_id).median().dropna()
    return {
        "method": "s2_minus_landsat_field_median_v1",
        "bias": float(medians.median()) if len(medians) else 0.0,
        "paired_days": int(differences.notna().sum()),
        "paired_fields": len(medians),
    }


def alignment_features(part, days, alignment, shrinkage):
    differences = sensor_pairs(part).to_numpy(dtype=float)
    paired = np.isfinite(differences)
    distances = abs(days[:, None] - days[paired][None, :])
    eligible = distances <= 60
    count = eligible.sum(axis=1).astype(float)
    matrix = np.where(eligible, differences[paired][None, :], np.nan)
    local = pd.DataFrame(matrix.T).median().to_numpy()
    mad = pd.DataFrame(abs(matrix - local[:, None]).T).median().to_numpy()
    global_bias = alignment["bias"]
    local = np.where(count > 0, local, global_bias)
    weight = count / (count + shrinkage)
    age = np.min(np.where(eligible, distances, np.inf), axis=1, initial=np.inf)
    age[~np.isfinite(age)] = np.nan
    return {
        "s2_landsat_bias": weight * local + (1 - weight) * global_bias,
        "s2_landsat_pair_count": count,
        "s2_landsat_pair_age": age,
        "s2_landsat_pair_mad": mad,
    }


def sensor_dynamics_features(days, values, primary, estimate):
    """Строгие календарные соседи и парное смещение по видимым данным одного сегмента культуры."""
    valid = np.isfinite(values)
    x, y = days[valid], values[valid]
    result = {}
    for side, positions in [
        ("left", np.searchsorted(x, days, side="left") - 1),
        ("right", np.searchsorted(x, days, side="right")),
    ]:
        available = (positions >= 0) & (positions < len(x))
        value, distance = np.full(len(days), np.nan), np.full(len(days), np.nan)
        value[available] = y[positions[available]]
        distance[available] = abs(days[available] - x[positions[available]])
        result[f"{side}_value"], result[f"{side}_days"] = value, distance
    span = result["left_days"] + result["right_days"]
    result["slope"] = np.divide(
        result["right_value"] - result["left_value"],
        span,
        out=np.full(len(days), np.nan),
        where=span > 0,
    )
    paired = valid & np.isfinite(primary)
    eligible = abs(days[:, None] - days[paired][None, :]) <= 60
    count = eligible.sum(axis=1)
    differences = np.broadcast_to((primary - values)[paired], eligible.shape).copy()
    differences[~eligible] = np.nan
    bias = pd.DataFrame(differences.T).median().to_numpy()
    bias[count < 3] = np.nan
    result["primary_bias"], result["paired_count"] = bias, count.astype(float)
    result["adjusted_estimate"] = estimate + bias
    return result


def local_shape_features(days, values, *, transitions=False):
    """Видимые соседи и окна внутри одного сезона поля с расстояниями в календарных днях."""
    valid = np.isfinite(values)
    x, y = days[valid], values[valid]
    result = {}
    positions = np.searchsorted(x, days)
    for side, offsets in [("left", [-1, -2]), ("right", [0, 1])]:
        for rank, offset in enumerate(offsets, start=1):
            indices = positions + offset
            available = (indices >= 0) & (indices < len(x))
            value, distance = np.full(len(days), np.nan), np.full(len(days), np.nan)
            value[available] = y[indices[available]]
            distance[available] = abs(days[available] - x[indices[available]])
            result[f"{side}_{rank}_value"] = value
            result[f"{side}_{rank}_days"] = distance
        span = result[f"{side}_2_days"] - result[f"{side}_1_days"]
        delta = result[f"{side}_2_value"] - result[f"{side}_1_value"]
        result[f"{side}_slope"] = np.divide(
            delta * (-1 if side == "left" else 1),
            span,
            out=np.full(len(days), np.nan),
            where=span > 0,
        )
    span = result["left_1_days"] + result["right_1_days"]
    fraction = np.divide(result["left_1_days"], span, out=np.full(len(days), np.nan), where=span > 0)
    result["neighbor_fraction"] = fraction
    result["linear_estimate"] = result["left_1_value"] + fraction * (
        result["right_1_value"] - result["left_1_value"]
    )
    if transitions:
        # Форму перехода оцениваем только по видимым опорам текущего сегмента.
        result["left_projected"] = result["left_1_value"] + result["left_slope"] * result["left_1_days"]
        result["right_projected"] = result["right_1_value"] - result["right_slope"] * result["right_1_days"]
        result["projection_gap"] = result["right_projected"] - result["left_projected"]
        result["slope_change"] = result["right_slope"] - result["left_slope"]
        if len(x) >= 2:
            pchip = PchipInterpolator(x, y, extrapolate=False)
            result["pchip_estimate"] = pchip(days)
            result["pchip_curvature"] = pchip(days, nu=2)
        else:
            result["pchip_estimate"] = np.full(len(days), np.nan)
            result["pchip_curvature"] = np.full(len(days), np.nan)
        result["pchip_delta_linear"] = result["pchip_estimate"] - result["linear_estimate"]
    distance = abs(days[:, None] - x[None, :])
    for window in [14, 30, 60]:
        weights = distance <= window
        count = weights.sum(axis=1)
        mean = np.divide(weights @ y, count, out=np.full(len(days), np.nan), where=count > 0)
        second = np.divide(weights @ (y * y), count, out=np.full(len(days), np.nan), where=count > 0)
        result[f"window_{window}_count"] = count
        result[f"window_{window}_mean"] = mean
        result[f"window_{window}_std"] = np.sqrt(np.maximum(0, second - mean * mean))
    return result


def training_masks(frame, valid, config):
    """Воспроизводимые маски самообучения: целями становятся только пригодные известные значения."""
    rng = np.random.default_rng(config["seed"])
    dates = pd.to_datetime(frame.date)
    seasons = dates.dt.year - (dates.dt.month < config["season_start_month"]).astype(int)
    groups = list(frame.loc[valid].groupby([frame.anon_polygon_id, seasons], sort=True))
    partitions = {}
    partition_count = config.get("coverage_partitions", 5)
    for repeat in range(config.get("training_repeats", 1)):
        if config.get("cover_training_targets", False) and repeat % partition_count == 0:
            partitions = {
                key: np.array_split(rng.permutation(part.sort_values("date").index), partition_count)
                for key, part in groups
            }
        for blocks in [False, True] if config.get("training_blocks", False) else [False]:
            if blocks and repeat >= config.get("training_block_repeats", config.get("training_repeats", 1)):
                continue
            mask = pd.Series(False, index=frame.index)
            for key, part in groups:
                if blocks:
                    ordered = part.sort_values("date")
                    days = pd.to_datetime(ordered.date).to_numpy(dtype="datetime64[D]").astype(np.int64)
                    start = days[int(rng.integers(len(days)))]
                    width = int(rng.choice([8, 15, 30, 45, 65]))
                    indices = ordered.index[(days >= start) & (days < start + width)]
                elif config.get("cover_training_targets", False):
                    indices = partitions[key][repeat % partition_count]
                else:
                    indices = rng.choice(part.index, max(1, round(len(part) * 0.2)), replace=False)
                mask.loc[indices] = True
            yield mask


def train_booster(features, residual, config, *, sample_weight=None):
    from catboost import CatBoostRegressor, Pool

    estimator = CatBoostRegressor(
        iterations=config.get("boost_iterations", 160),
        depth=config.get("boost_depth", 4),
        learning_rate=config.get("boost_learning_rate", 0.04),
        l2_leaf_reg=config.get("boost_l2", 10),
        loss_function="RMSE",
        random_seed=config["seed"],
        thread_count=2,
        verbose=False,
        allow_writing_files=False,
    )
    pool = (
        Pool(features, residual, cat_features=["crop_type"], weight=sample_weight)
        if config.get("crop_features")
        else None
    )
    if pool is None:
        estimator.fit(features, residual, sample_weight=sample_weight)
    else:
        estimator.fit(pool)
    with tempfile.TemporaryDirectory(prefix="terralens-model-") as directory:
        path = Path(directory) / "boost.json"
        estimator.save_model(str(path), format="json", pool=pool)
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
    predictions = []
    for member in [model["boosting"], *model.get("boosting_members", [])]:
        payload = json.dumps(member, separators=(",", ":"))
        estimator = _load_booster(canonical_hash(member), payload)
        predictions.append(estimator.predict(features, thread_count=2))
    return np.mean(predictions, axis=0)
