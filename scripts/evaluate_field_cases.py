"""Оценить неизменённую модель на скрытых наблюдаемых датах реальных полей."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services.analysis import calculate, daily_observations
from terralens_ml.io import sha256, write_json
from terralens_ml.model import load_model


def masks_for_dates(dates):
    """Каждая дата скрывается один раз; блоки состоят из непересекающихся пар."""
    ordered = sorted(set(dates))
    return {
        "points": [[day] for day in ordered],
        "blocks": [ordered[i : i + 2] for i in range(0, len(ordered) - 1, 2)],
    }


def remove_dates(observations, hidden):
    """Удалить все сцены всех сенсоров, чтобы второй сенсор не раскрывал цель."""
    hidden = set(hidden)
    return [row for row in observations if row["date"] not in hidden]


def metrics(rows):
    valid = [row for row in rows if row["prediction"] is not None and math.isfinite(row["prediction"])]
    errors = [row["prediction"] - row["truth"] for row in valid]
    intervals = [row for row in valid if row.get("interval_contains_truth") is not None]
    return {
        "targets": len(rows),
        "predicted": len(valid),
        "unavailable": len(rows) - len(valid),
        "rmse": math.sqrt(math.fsum(e * e for e in errors) / len(errors)) if errors else None,
        "mae": math.fsum(abs(e) for e in errors) / len(errors) if errors else None,
        "interval_n": len(intervals),
        "interval_coverage": (
            sum(row["interval_contains_truth"] for row in intervals) / len(intervals) if intervals else None
        ),
    }


def verified_input(folder):
    evidence = json.loads((folder / "evidence.json").read_text(encoding="utf-8"))
    geometry_path = Path(evidence["geometry"])
    if sha256(geometry_path) != evidence["geometry_sha256"]:
        raise ValueError("Геометрия изменилась после сбора")
    recorded = {"observations": [], "history": []}
    for source in evidence["sources"]:
        path = folder / source["path"]
        if sha256(path) != source["sha256"]:
            raise ValueError(f"Изменился snapshot: {path}")
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        recorded["observations" if source["label"] == "current" else "history"].extend(
            snapshot["data"]["observations"]
        )
    data = json.loads((folder / "observations.json").read_text(encoding="utf-8"))
    if any(data[key] != value for key, value in recorded.items()):
        raise ValueError("Сводные наблюдения отличаются от snapshots")
    if evidence["weather_sha256"]:
        weather_path = folder / "weather_snapshot.json"
        if sha256(weather_path) != evidence["weather_sha256"]:
            raise ValueError("Изменился snapshot погоды")
        snapshot = json.loads(weather_path.read_text(encoding="utf-8"))
        raw = snapshot["data"]["daily"]
        expected = [
            {
                "date": day,
                "temperature_c": temp,
                "precipitation_mm": rain if rain is None or rain >= 0 else None,
                "provider": snapshot["provider"],
            }
            for day, temp, rain in zip(
                raw["time"], raw["temperature_2m_mean"], raw["precipitation_sum"], strict=True
            )
        ]
        if data["weather"] != expected:
            raise ValueError("Сводная погода отличается от snapshot")
    elif data["weather"]:
        raise ValueError("Погода есть, но её snapshot отсутствует")
    return evidence, json.loads(geometry_path.read_text(encoding="utf-8")), data


def evaluate(folder, models):
    evidence, geometry, data = verified_input(folder)
    period = next(source["period"] for source in evidence["sources"] if source["label"] == "current")
    by_day = daily_observations(data["observations"])
    truth = {day: choices[0] for day, choices in by_day.items() if choices[0]["usable"]}

    def run(model, observations):
        return calculate(
            folder.name,
            None,
            period["from"],
            period["to"],
            observations,
            data["weather"],
            model,
            data["history"],
        )

    daily, events, summary = run(models["final"], data["observations"])
    predictions = []
    if len(truth) >= 6:
        for scenario, masks in masks_for_dates(truth).items():
            for number, hidden in enumerate(masks):
                observations = remove_dates(data["observations"], hidden)
                for name, model in models.items():
                    masked_daily, _, _ = run(model, observations)
                    indexed = {row["date"]: row for row in masked_daily}
                    for day in hidden:
                        row = indexed[day]
                        interval = row["prediction_interval"]
                        lower, upper = interval.get("lower"), interval.get("upper")
                        value = truth[day]["ndvi"]
                        predictions.append(
                            {
                                "field": folder.name,
                                "scenario": scenario,
                                "mask": number,
                                "model": name,
                                "date": day,
                                "sensor": truth[day]["sensor"],
                                "truth": value,
                                "prediction": row["reconstructed"],
                                "origin": row["origin"],
                                "gap_days": row["gap_days"],
                                "interval_contains_truth": lower <= value <= upper
                                if lower is not None and upper is not None
                                else None,
                            }
                        )
                print(f"{folder.name} {scenario}: {number + 1}/{len(masks)}", flush=True)
    groups = {
        scenario: {
            name: metrics([p for p in predictions if p["scenario"] == scenario and p["model"] == name])
            for name in models
        }
        for scenario in ("points", "blocks")
    }
    return {
        "field": folder.name,
        "geometry": geometry,
        "period": period,
        "summary": summary,
        "daily": daily,
        "events": events,
        "observations": data["observations"],
        "history": data["history"],
        "weather": data["weather"],
        "evidence": evidence,
        "predictions": predictions,
        "metrics": groups,
        "evaluation_status": "evaluated" if len(truth) >= 6 else "insufficient_observed_dates",
        "agronomic_ground_truth": False,
        "limitations": [
            "Культура и история севооборота не подтверждены",
            "Причины негативных отклонений остаются гипотезами",
            "Маски внутри поля зависимы; число точек не равно числу независимых полей",
            "Три выбранных поля не представляют все регионы",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", nargs="+", required=True)
    parser.add_argument("--output", default="docs/analysis/field-cases")
    args = parser.parse_args()
    manifests = {
        "final": "ml/artifacts/final/manifest.json",
        "baseline": "ml/artifacts/baseline/manifest.json",
    }
    models = {name: load_model(Path(path))[0] for name, path in manifests.items()}
    reports = []
    for folder in args.inputs:
        report = evaluate(Path(folder), models)
        write_json(Path(args.output) / f"{report['field']}.json", report)
        reports.append(report)
    predictions = [p for report in reports for p in report["predictions"]]
    write_json(
        Path(args.output) / "summary.json",
        {
            "evaluated_at": datetime.now(UTC).isoformat(),
            "model_manifests": {
                name: {"path": path, "sha256": sha256(path)} for name, path in manifests.items()
            },
            "protocol_sha256": sha256("docs/analysis/field-cases/PROTOCOL.md"),
            "fields": [
                {k: r[k] for k in ("field", "period", "summary", "metrics", "evaluation_status")}
                for r in reports
            ],
            "pooled": {
                scenario: {
                    name: metrics(
                        [p for p in predictions if p["scenario"] == scenario and p["model"] == name]
                    )
                    for name in models
                }
                for scenario in ("points", "blocks")
            },
            "fit_or_selection_performed": False,
        },
    )


if __name__ == "__main__":
    main()
