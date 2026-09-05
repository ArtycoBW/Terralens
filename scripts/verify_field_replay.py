"""Повторить расчёт опубликованных полевых примеров без сети и проверить сводные метрики."""

import argparse
import json
import math
import socket
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from evaluate_field_cases import metrics
from services.analysis import calculate
from terralens_ml.io import sha256, write_json
from terralens_ml.model import load_model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", default="docs/analysis/field-cases")
    parser.add_argument("--output", default="artifacts/field-replay.json")
    parser.add_argument("--refresh-summary", action="store_true")
    args = parser.parse_args()
    folder = Path(args.reports)
    manifest_path = Path("ml/artifacts/final/manifest.json")
    model, manifest = load_model(manifest_path)
    combined = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    if sha256(manifest_path) != combined["model_manifests"]["final"]["sha256"]:
        raise ValueError("Модель отличается от использованной при оценке")
    results = []
    with patch.object(socket.socket, "connect", side_effect=RuntimeError("Сеть запрещена")):
        for field in combined["fields"]:
            path = folder / f"{field['field']}.json"
            report = json.loads(path.read_text(encoding="utf-8"))
            daily, events, summary = calculate(
                report["field"],
                None,
                report["period"]["from"],
                report["period"]["to"],
                report["observations"],
                report["weather"],
                model,
                report["history"],
            )
            if daily != report["daily"] or events != report["events"]:
                raise ValueError(f"Ряд или события не воспроизвелись: {path}")
            if args.refresh_summary:
                report["summary"] = summary
                field["summary"] = summary
                write_json(path, report)
            elif summary != report["summary"]:
                raise ValueError(f"Сводный статус не воспроизвёлся: {path}")
            for scenario in ("points", "blocks"):
                for name in ("final", "baseline"):
                    subset = [
                        p for p in report["predictions"] if p["scenario"] == scenario and p["model"] == name
                    ]
                    actual = metrics(subset)
                    if any(
                        not math.isclose(value, report["metrics"][scenario][name][key], rel_tol=1e-12)
                        if isinstance(value, float)
                        else value != report["metrics"][scenario][name][key]
                        for key, value in actual.items()
                    ):
                        raise ValueError(f"Метрики отличаются от таблицы предсказаний: {path}")
            results.append(
                {
                    "field": report["field"],
                    "daily_equal": True,
                    "events_equal": True,
                    "summary_equal": True,
                    "metrics_recomputed": True,
                    "observed_days": summary["observed_days"],
                }
            )
    if args.refresh_summary:
        combined["summary_rule_update"] = {
            "rule": "event-max-else-two-clean-days-and-half-period-reference-v3",
            "reason": "Оценка нормы на нескольких датах не характеризует весь период",
            "reconstruction_and_events_unchanged": True,
            "metrics_unchanged": True,
        }
        write_json(folder / "summary.json", combined)
    write_json(args.output, {"network_disabled": True, "model_id": manifest["model_id"], "fields": results})
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
