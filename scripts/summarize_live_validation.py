"""Проверить hashes live-сбора и рассчитать два реальных ряда тем же адаптером, что и worker."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services.analysis import calculate
from terralens_ml.io import sha256, write_json
from terralens_ml.model import load_model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--inputs",
        nargs="+",
        default=[
            "artifacts/live-validation/potsdam",
            "artifacts/live-validation/seville",
        ],
    )
    parser.add_argument("--model", default="ml/artifacts/final/manifest.json")
    parser.add_argument("--output", default="docs/analysis/live-validation")
    args = parser.parse_args()
    model, _ = load_model(Path(args.model))
    results = []
    for name in args.inputs:
        folder = Path(name)
        evidence = json.loads((folder / "evidence.json").read_text())
        feature = json.loads(Path(evidence["geometry"]).read_text())
        if sha256(evidence["geometry"]) != evidence["geometry_sha256"]:
            raise ValueError("Геометрия изменилась после live-сбора")
        recorded = {"observations": [], "history": []}
        for source in evidence["sources"]:
            if sha256(folder / source["path"]) != source["sha256"]:
                raise ValueError(f"Snapshot изменился: {source['path']}")
            snapshot = json.loads((folder / source["path"]).read_text())
            recorded["observations" if source["label"] == "current" else "history"].extend(
                snapshot["data"]["observations"]
            )
        if (
            evidence["weather_sha256"]
            and sha256(folder / "weather_snapshot.json") != evidence["weather_sha256"]
        ):
            raise ValueError("Snapshot погоды изменился")
        weather_metadata = None
        if evidence["weather_sha256"]:
            weather_snapshot = json.loads((folder / "weather_snapshot.json").read_text())
            weather_metadata = {key: weather_snapshot[key] for key in ["provider", "query", "retrieved_at"]}
        data = json.loads((folder / "observations.json").read_text())
        if any(data[key] != value for key, value in recorded.items()):
            raise ValueError("Сводный ряд отличается от исходных спутниковых snapshots")
        if weather_metadata:
            raw_daily = weather_snapshot["data"]["daily"]
            expected_weather = [
                {
                    "date": day,
                    "temperature_c": temp,
                    "precipitation_mm": rain if rain is None or rain >= 0 else None,
                    "provider": weather_metadata["provider"],
                }
                for day, temp, rain in zip(
                    raw_daily["time"],
                    raw_daily["temperature_2m_mean"],
                    raw_daily["precipitation_sum"],
                    strict=True,
                )
            ]
            if data["weather"] != expected_weather:
                raise ValueError("Сводная погода отличается от исходного snapshot")
        period = next(source["period"] for source in evidence["sources"] if source["label"] == "current")
        daily, events, summary = calculate(
            folder.name,
            None,
            period["from"],
            period["to"],
            data["observations"],
            data["weather"],
            model,
            data["history"],
        )
        report = {
            "kind": "recorded_live_validation",
            "field": folder.name,
            "geometry": feature,
            "period": period,
            "evidence": evidence,
            "model_sha256": sha256(args.model),
            "model_manifest": args.model,
            "weather_source": weather_metadata,
            "summary": summary,
            "daily": daily,
            "events": events,
            "observations": data["observations"],
            "history_observations": data["history"],
            "limitations": [
                "История культур неизвестна; сопоставимость сезонов не подтверждена агрономом",
                "Короткое окно и два региона проверяют сбор и вычисления, а не точность диагноза",
                "Валидация модели на анонимном benchmark не является валидацией переноса на эти поля",
            ],
        }
        write_json(Path(args.output) / f"{folder.name}.json", report)
        results.append(
            {
                "field": folder.name,
                "summary": summary,
                "reference_years": sorted({x["reference_years"] for x in daily}),
            }
        )
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
