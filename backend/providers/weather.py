import math
from datetime import date

from .base import ProviderError, get_json, snapshot

PROVIDER = "open_meteo_era5_seamless"


def fetch_weather(geometry, start, end):
    # В MVP это выборка сеточной модели в центроиде, не полевая метеостанция.
    center = geometry.centroid
    params = {
        "latitude": center.y,
        "longitude": center.x,
        "start_date": str(start),
        "end_date": str(end),
        "daily": "temperature_2m_mean,precipitation_sum",
        "timezone": "UTC",
        "models": "era5_seamless",
        "temperature_unit": "celsius",
        "precipitation_unit": "mm",
        "cell_selection": "land",
    }
    raw = get_json("https://archive-api.open-meteo.com/v1/archive", params=params, provider=PROVIDER)
    try:
        if not isinstance(raw, dict):
            raise ValueError("weather object")
        units = raw.get("daily_units", {})
        if not isinstance(units, dict):
            raise ValueError("weather units object")
        if units.get("temperature_2m_mean", "°C") != "°C" or units.get("precipitation_sum", "mm") != "mm":
            raise ValueError("weather units")
        daily = raw["daily"]
        dates, temps, rain = daily["time"], daily["temperature_2m_mean"], daily["precipitation_sum"]
        if not len(dates) == len(temps) == len(rain):
            raise ValueError("length")
        if len(set(dates)) != len(dates):
            raise ValueError("duplicate dates")
        for day in dates:
            if not str(start) <= date.fromisoformat(day).isoformat() <= str(end):
                raise ValueError("date outside query")
        if any(
            value is not None and (isinstance(value, bool) or not math.isfinite(value))
            for value in temps + rain
        ):
            raise ValueError("nonfinite weather")
        records = [
            {
                "date": day,
                "temperature_c": temp,
                "precipitation_mm": value if value is None or value >= 0 else None,
                "provider": PROVIDER,
            }
            for day, temp, value in zip(dates, temps, rain, strict=True)
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderError(
            "provider_schema_changed", "Неожиданная схема погодных данных", provider=PROVIDER
        ) from exc
    expected_days = (date.fromisoformat(str(end)) - date.fromisoformat(str(start))).days + 1
    missing_days = expected_days - len(records)
    incomplete_days = sum(x["temperature_c"] is None or x["precipitation_mm"] is None for x in records)
    warnings = []
    if missing_days or incomplete_days:
        warnings.append(
            {
                "code": "weather_missing",
                "provider": PROVIDER,
                "affected_period": {"from": str(start), "to": str(end)},
                "missing_days": missing_days,
                "incomplete_days": incomplete_days,
            }
        )
    return records, snapshot(
        PROVIDER,
        params
        | {
            "aggregation": "centroid_grid_sampling_utc_daily_v2",
            "field_sources": {"temperature_c": "era5_land", "precipitation_mm": "era5"},
        },
        raw,
        warnings,
    )
