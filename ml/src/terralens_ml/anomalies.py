"""Историческая норма, границы z и объяснения из проверяемых фактов."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .io import DataError, mask_context


def add_reference(
    result,
    history=None,
    *,
    minimum_years=3,
    window_days=15,
    method="median_mad",
    minimum_std=0.01,
    season_start_month=1,
):
    if method not in ["median_mad", "mean_std"] or minimum_years < 3 or not 1 <= season_start_month <= 12:
        raise DataError("Некорректная политика исторической нормы")
    frame = result.copy(deep=True)
    frame["climatology_mean"], frame["climatology_std"], frame["zscore"] = np.nan, np.nan, np.nan
    frame["reference_years"] = 0
    if history is None:
        history = frame
    history = mask_context(history, history.get("is_synthetic_gap", pd.Series(False, index=history.index)))
    history["_date"] = pd.to_datetime(history.date)
    history["_year"] = history._date.dt.year - (history._date.dt.month < season_start_month).astype(int)
    history["_day"] = pd.to_datetime("2000-" + history._date.dt.strftime("%m-%d")).dt.dayofyear
    target_column = "clean_primary" if "clean_primary" in history else "primary_ndvi"
    history = history.loc[history[target_column].between(-1, 1)]
    for i, row in frame.iterrows():
        date = pd.Timestamp(row.date)
        day = pd.Timestamp(f"2000-{date:%m-%d}").dayofyear
        season = date.year - int(date.month < season_start_month)
        prior = history.loc[(history.anon_polygon_id == row.anon_polygon_id) & (history._year < season)]
        if "crop_type" in prior and pd.notna(row.get("crop_type")):
            prior = prior.loc[prior.crop_type == row.crop_type]
        distance = abs(prior._day - day)
        prior = prior.loc[np.minimum(distance, 366 - distance) <= window_days]
        annual = prior.groupby("_year")[target_column].median()
        count = len(annual)
        flags = list(row.quality_flags)
        frame.at[i, "reference_years"] = count
        if count < minimum_years:
            flags.append("insufficient_reference")
        else:
            if method == "median_mad":
                mean = float(annual.median())
                std = float(1.4826 * (annual - mean).abs().median())
                flags.append("robust_reference")
            else:
                mean, std = float(annual.mean()), float(annual.std(ddof=1))
            frame.at[i, "climatology_mean"], frame.at[i, "climatology_std"] = mean, std
            if std < minimum_std:
                flags.append("degenerate_reference")
            elif pd.notna(row.reconstructed):
                frame.at[i, "zscore"] = (row.reconstructed - mean) / std
        frame.at[i, "quality_flags"] = flags
    return frame


def severity(z):
    if z is None or not np.isfinite(z):
        return "insufficient_data"
    return "critical" if z < -2 else "stress" if z < -1 else "normal"


def detect_anomalies(result, weather=None, config=None):
    config = config or {}
    events = []
    weather = {x["date"]: x for x in (weather or [])}
    for _, part in result.groupby("anon_polygon_id"):
        part = part.sort_values("date").copy()
        negative = part.loc[part.zscore < -1]
        if negative.empty:
            continue
        groups = pd.to_datetime(negative.date).diff().dt.days.ne(1).cumsum()
        for _, group in negative.groupby(groups):
            observed = group.loc[group.origin.eq("observed")]
            count = len(observed)
            if count == 0:
                continue
            duration = (pd.Timestamp(group.date.iloc[-1]) - pd.Timestamp(group.date.iloc[0])).days + 1
            persistent = count >= 2 or duration >= config.get("minimum_period_days", 7)
            if not persistent and not (observed.zscore < -2).any():
                continue
            peak = group.loc[group.zscore.idxmin()]
            confidence = (
                "high"
                if count >= 3 and len(observed) / len(group) >= 0.5
                else "medium"
                if count >= 2
                else "low"
            )
            flags = sorted(set(flag for row_flags in group.quality_flags for flag in row_flags))
            if set(flags) & {"long_gap", "low_support", "domain_shift", "crop_history_unknown"}:
                confidence = "low" if count < 3 else "medium"
            evidence = [
                {
                    "metric": "minimum_z",
                    "value": float(peak.zscore),
                    "unit": "std",
                    "period": {"from": group.date.iloc[0], "to": group.date.iloc[-1]},
                    "source": "historical_aoi_reference",
                }
            ]
            causes = [
                {
                    "code": "uncertain",
                    "label": "Причина требует проверки",
                    "confidence": "low",
                    "evidence": evidence,
                    "counter_evidence": [],
                }
            ]
            available_weather = [weather[date] for date in group.date if date in weather]
            complete = [
                x
                for x in available_weather
                if x.get("temperature_c") is not None
                and x.get("precipitation_mm") is not None
                and np.isfinite(x["temperature_c"])
                and np.isfinite(x["precipitation_mm"])
            ]
            weather_coverage = len(complete) / duration
            if weather_coverage < 0.8:
                flags.append("weather_missing")
            if len(complete) >= 7:
                temperature = float(np.mean([x["temperature_c"] for x in complete]))
                precipitation = float(np.sum([x["precipitation_mm"] for x in complete]))
                if temperature >= 28 and precipitation / len(complete) < 1:
                    causes = [
                        {
                            "code": "weather_stress",
                            "label": "Возможен погодный стресс",
                            "confidence": "low",
                            "evidence": evidence
                            + [
                                {
                                    "metric": "mean_temperature",
                                    "value": temperature,
                                    "unit": "°C",
                                    "period": evidence[0]["period"],
                                    "source": complete[0]["provider"],
                                },
                                {
                                    "metric": "total_precipitation",
                                    "value": precipitation,
                                    "unit": "mm",
                                    "period": evidence[0]["period"],
                                    "source": complete[0]["provider"],
                                },
                            ],
                            "counter_evidence": ["Низкие осадки и жара не устанавливают причину отклонения"],
                        }
                    ]
            events.append(
                {
                    "start_date": group.date.iloc[0],
                    "end_date": group.date.iloc[-1],
                    "peak_date": peak.date,
                    "severity": severity(float(peak.zscore)),
                    "confidence": confidence,
                    "event_kind": "persistent_period" if persistent else "single_observation_alert",
                    "min_z": float(peak.zscore),
                    "integrated_deficit": float(
                        (group.climatology_mean - group.reconstructed).clip(lower=0).sum()
                    ),
                    "observed_evidence_count": count,
                    "reconstructed_fraction": 1 - count / len(group),
                    "weather_coverage_ratio": weather_coverage,
                    "quality_flags": flags,
                    "causes": causes,
                    "explanation": {
                        "title": "Устойчивое снижение растительности"
                        if persistent
                        else "Одиночное критическое наблюдение",
                        "summary": f"Отклонение от исторической нормы достигает {float(peak.zscore):.2f} σ; пригодных наблюдений: {count}.",
                        "observations": [f"Период: {group.date.iloc[0]} — {group.date.iloc[-1]}"],
                        "possible_causes": [x["label"] for x in causes]
                        + [
                            "Возможна фенологическая фаза или уборка",
                            "Возможен артефакт спутникового наблюдения",
                        ],
                        "recommended_checks": [
                            "Сверить культуру, сроки уборки и историю поля",
                            "Проверить исходные снимки и полевые наблюдения",
                        ],
                        "limitations": [
                            "Причины не подтверждены независимой агрономической разметкой",
                            "Погодное правило — начальная эвристика, а не диагноз",
                        ],
                    },
                    "review_status": "unreviewed",
                }
            )
    return events
