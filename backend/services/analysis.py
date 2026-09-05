from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from terralens_ml.anomalies import add_reference, detect_anomalies
from terralens_ml.io import DataError, sha256
from terralens_ml.model import load_model, reconstruct


@lru_cache(maxsize=4)
def worker_model(path, checksum):
    if sha256(path) != checksum:
        raise DataError("Контрольная сумма manifest изменилась после запуска анализа")
    return load_model(Path(path))[0]


SENSOR_PRIORITY = {"sentinel2": 0, "landsat": 1, "modis": 2}


def daily_observations(observations):
    """Сначала качество, затем S2 → Landsat → MODIS; сцены не становятся новыми днями."""
    grouped = {}
    for item in observations:
        grouped.setdefault(item["date"], []).append(item)
    return {
        day: sorted(
            items,
            key=lambda x: (
                not x["usable"],
                SENSOR_PRIORITY.get(x["sensor"], 99),
                -x["valid_pixel_fraction"],
                x.get("scene_id", ""),
            ),
        )
        for day, items in grouped.items()
    }


def calculate(
    polygon_id,
    crop,
    start,
    end,
    observations,
    weather,
    model,
    reference_observations=None,
    crop_seasons=None,
):
    dates = pd.date_range(start, end).strftime("%Y-%m-%d")
    by_day = daily_observations(observations)
    weather_by_day = {x["date"]: x for x in weather}
    seasons = crop_seasons or []

    def crop_for(day, *, historical=False):
        for season in seasons:
            if season["season_start"] <= day <= season["season_end"]:
                return season["crop_type"] or "unknown"
        # Статическая метка относится к выбранному периоду, а не ко всем прошлым годам.
        return "unknown" if historical else crop or "unknown"

    def ml_row(day, choices, *, historical=False):
        observation = choices[0] if choices else None
        row = {
            "anon_polygon_id": str(polygon_id),
            "date": day,
            "crop_type": crop_for(day, historical=historical),
            "primary_ndvi": observation["ndvi"] if observation and observation["usable"] else np.nan,
            "reference_sensor": observation["sensor"] if observation and observation["usable"] else None,
        }
        for sensor, prefix in [("sentinel2", "s2"), ("landsat", "landsat"), ("modis", "modis")]:
            source = next((x for x in choices if x["sensor"] == sensor and x["usable"]), {})
            for index in ("ndvi", "evi"):
                row[f"{prefix}_{index}"] = source.get(index, np.nan)
            # Формула NDWI benchmark неизвестна: не переносим live NIR/SWIR в этот признак.
        meteo = weather_by_day.get(day, {})
        row["era5_temp_c"] = meteo.get("temperature_c", np.nan)
        row["era5_precip_mm"] = meteo.get("precipitation_mm", np.nan)
        return row

    frame = pd.DataFrame([ml_row(day, by_day.get(day, [])) for day in dates])
    historical = daily_observations(reference_observations or [])
    # Один независимый primary на дату; история не должна перекрывать текущий сезон.
    history_rows = [
        ml_row(day, choices, historical=True)
        for day, choices in historical.items()
        if day < str(start) and choices[0]["usable"]
    ]
    history = pd.DataFrame(history_rows) if history_rows else None
    context = pd.concat([frame, history], ignore_index=True) if history is not None else frame
    result = reconstruct(context, model=model, config={"interval_domain": "live"}).iloc[: len(frame)].copy()
    has_observations = frame.primary_ndvi.notna().any()
    if not has_observations:
        # Непроверенный перенос benchmark prior не заменяет наблюдения реального поля.
        result["reconstructed"] = np.nan
        result["origin"] = "unavailable"
        for column in ("lower", "upper"):
            if column in result:
                result[column] = np.nan
    # Выбранный диапазон может пересекать границу сезона. Его ранние clean-наблюдения
    # тоже доступны будущему сезону; add_reference исключает сезон каждой target-даты.
    reference_rows = []
    for day, choices in (historical | by_day).items():
        if day > str(end):
            continue
        for sensor in SENSOR_PRIORITY:
            source = next((x for x in choices if x["sensor"] == sensor and x["usable"]), None)
            if source:
                reference_rows.append(ml_row(day, [source], historical=day < str(start)))
    reference = pd.DataFrame(reference_rows, columns=frame.columns)
    reference["clean_primary"] = reference.primary_ndvi.where(reference.primary_ndvi.between(-1, 1))
    counts = frame.reference_sensor.value_counts()
    dominant_sensor = counts.index[0] if len(counts) else None
    result["reference_sensor"] = result.reference_sensor.fillna(dominant_sensor or "unavailable")
    referenced = []
    for sensor, part in result.groupby("reference_sensor", sort=False):
        # Смещения S2/Landsat ещё не откалиброваны: норма каждой точки использует
        # только тот же сенсор. На gap-днях берём преобладающий сенсор текущего поля.
        comparable = reference.loc[reference.reference_sensor.eq(sensor)]
        referenced.append(
            add_reference(
                part,
                comparable,
                season_start_month=model["config"].get("season_start_month", 1),
            )
        )
    result = pd.concat(referenced).sort_index()
    for i, row in result.iterrows():
        if row.crop_type == "unknown" and row.reference_years:
            result.at[i, "quality_flags"] = list(row.quality_flags) + ["crop_history_unknown"]
    daily = []

    def finite(value):
        return float(value) if value is not None and np.isfinite(value) else None

    for _, row in result.iterrows():
        choices = by_day.get(row.date, [])
        observation = choices[0] if choices else None
        meteo = weather_by_day.get(
            row.date, {"temperature_c": None, "precipitation_mm": None, "provider": None}
        )
        flags = list(row.quality_flags)
        flags.append(f"reference_sensor_{row.reference_sensor}")
        if meteo["temperature_c"] is None or meteo["precipitation_mm"] is None:
            flags.append("weather_missing")
        if observation:
            flags.extend(observation["quality_flags"])
        if row.origin == "climatology_fallback":
            flags.append("domain_shift")
        daily.append(
            {
                "date": row.date,
                "observed_primary": observation["ndvi"] if observation else None,
                "clean_primary": finite(row.clean_primary),
                "reconstructed": finite(row.reconstructed),
                "origin": row.origin,
                "source_sensor": observation["sensor"] if observation else None,
                "sensors": {
                    sensor: next((x["ndvi"] for x in choices if x["sensor"] == sensor), None)
                    for sensor in SENSOR_PRIORITY
                },
                "climatology_mean": finite(row.climatology_mean),
                "climatology_std": finite(row.climatology_std),
                "zscore": finite(row.zscore),
                "prediction_interval": row.get(
                    "prediction_interval",
                    {
                        "lower": None,
                        "upper": None,
                        "level": None,
                        "method": "not_calibrated",
                    },
                )
                if has_observations
                else {
                    "lower": None,
                    "upper": None,
                    "level": None,
                    "method": "not_calibrated",
                },
                "weather": {k: meteo[k] for k in ["temperature_c", "precipitation_mm", "provider"]},
                "support_count": int(row.support_count),
                "gap_days": int(row.gap_days),
                "quality_flags": sorted(set(flags)),
                "reference_years": int(row.reference_years),
            }
        )
    events = detect_anomalies(result, weather)
    observed = sum(x["clean_primary"] is not None for x in daily)
    reconstructed = sum(x["reconstructed"] is not None and x["origin"] != "observed" for x in daily)
    unavailable = sum(x["reconstructed"] is None for x in daily)
    longest, current = 0, 0
    for row in daily:
        current = current + 1 if row["clean_primary"] is None else 0
        longest = max(longest, current)
    latest = next((x for x in reversed(daily) if x["reconstructed"] is not None), None)
    # Два пригодных дня не характеризуют весь период, если почти вся норма отсутствует.
    # Отрицательные события сохраняют приоритет; «норма» требует покрытия хотя бы половины дат.
    referenced_days = sum(x["zscore"] is not None for x in daily)
    enough = sum(
        x["clean_primary"] is not None and x["zscore"] is not None for x in daily
    ) >= 2 and referenced_days * 2 >= len(daily)
    overall = (
        "critical"
        if any(x["severity"] == "critical" for x in events)
        else "stress"
        if events
        else "normal"
        if enough
        else "insufficient_data"
    )
    summary = {
        "observed_days": observed,
        "total_days": len(daily),
        "observed_coverage_ratio": observed / len(daily) if daily else 0,
        "reconstructed_days": reconstructed,
        "unavailable_days": unavailable,
        "longest_gap_days": longest,
        "anomaly_period_count": len(events),
        "overall_status": overall,
        "summary_rule": "event-max-else-two-clean-days-and-half-period-reference-v3",
        "latest_estimate": {
            "date": latest["date"],
            "value": latest["reconstructed"],
            "origin": latest["origin"],
        }
        if latest
        else None,
    }
    return daily, events, summary
