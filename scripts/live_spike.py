"""Реальный ограниченный сбор; запуск из корня: python scripts/live_spike.py."""

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from providers.base import ProviderError
from providers.landsat import fetch_landsat
from providers.stac import fetch_satellite
from providers.weather import fetch_weather
from shapely.geometry import shape
from terralens_ml.io import sha256, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--geometry", default="backend/tests/fixtures/potsdam.geojson")
    parser.add_argument("--from", dest="start", default="2024-06-01")
    parser.add_argument("--to", dest="end", default="2024-06-10")
    parser.add_argument("--output", default="artifacts/spike")
    parser.add_argument(
        "--sources", nargs="+", choices=["sentinel2", "landsat"], default=["sentinel2", "landsat"]
    )
    parser.add_argument("--max-scenes", type=int, default=80)
    parser.add_argument("--history-years", type=int, choices=range(0, 6), default=0)
    parser.add_argument("--resume", action="store_true", help="Продолжить с уже сохранённых точных запросов")
    args = parser.parse_args()
    geometry = shape(json.loads(Path(args.geometry).read_text())["geometry"])
    out = Path(args.output)
    periods = [(args.start, args.end, "current")]
    for delta in range(1, args.history_years + 1):

        def prior(value):
            day = date.fromisoformat(value)
            try:
                return day.replace(year=day.year - delta)
            except ValueError:
                return day.replace(year=day.year - delta, day=28)

        periods.append(
            (
                str(prior(args.start) - timedelta(days=15)),
                str(prior(args.end) + timedelta(days=15)),
                f"history-{delta}",
            )
        )
    evidence_sources, warnings = [], []
    observations, history = [], []
    for start, end, label in periods:
        for sensor in args.sources:
            path = out / f"{label}-{sensor}.json"
            fetch = fetch_satellite if sensor == "sentinel2" else fetch_landsat
            try:
                began = time.monotonic()
                resumed = args.resume and path.is_file()
                if resumed:
                    satellite = json.loads(path.read_text())
                    expected = {
                        "bbox": ",".join(map(str, geometry.bounds)),
                        "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
                        "collections": "sentinel-2-c1-l2a" if sensor == "sentinel2" else "landsat-c2-l2",
                        "limit": min(args.max_scenes + 1, 100),
                    }
                    if any(satellite["query"].get(key) != value for key, value in expected.items()):
                        raise ValueError(f"Snapshot не соответствует запросу: {path}")
                    values = satellite["data"]["observations"]
                    print(f"{label} {sensor}: сохранённый snapshot {satellite['retrieved_at']}", flush=True)
                else:
                    values, satellite = fetch(
                        geometry,
                        start,
                        end,
                        max_scenes=args.max_scenes,
                        progress=lambda i, n: print(f"{label} {sensor}: {i}/{n}", flush=True),
                    )
                    write_json(path, satellite)
                (observations if label == "current" else history).extend(values)
                warnings.extend(satellite["warnings"])
                evidence_sources.append(
                    {
                        "period": {"from": start, "to": end},
                        "label": label,
                        "sensor": sensor,
                        "path": path.name,
                        "sha256": sha256(path),
                        "retrieved_at": satellite["retrieved_at"],
                        "resumed_snapshot": resumed,
                        "duration_seconds": None if resumed else round(time.monotonic() - began, 3),
                        "observations": len(values),
                        "usable_observations": sum(x["usable"] for x in values),
                        "warnings": satellite["warnings"],
                    }
                )
            except ProviderError as exc:
                warnings.append({"code": exc.code, "provider": exc.provider, "period": label})
                print(f"{label} {sensor}: {exc.code}", flush=True)
    weather = []
    try:
        weather, weather_snapshot = fetch_weather(geometry, args.start, args.end)
        write_json(out / "weather_snapshot.json", weather_snapshot)
        weather_hash = sha256(out / "weather_snapshot.json")
        warnings.extend(weather_snapshot["warnings"])
    except ProviderError as exc:
        weather_hash = None
        warnings.append({"code": exc.code, "provider": exc.provider})
    write_json(
        out / "observations.json", {"observations": observations, "history": history, "weather": weather}
    )
    evidence = {
        "geometry_sha256": sha256(args.geometry),
        "geometry": args.geometry,
        "sources": evidence_sources,
        "weather_sha256": weather_hash,
        "observations": len(observations),
        "usable_observations": sum(x["usable"] for x in observations),
        "weather_days": len(weather),
        "history_observations": len(history),
        "history_usable_observations": sum(x["usable"] for x in history),
        "warnings": warnings,
    }
    write_json(out / "evidence.json", evidence)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["usable_observations"] and weather else 1


if __name__ == "__main__":
    raise SystemExit(main())
