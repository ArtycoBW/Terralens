"""Локальная оценка готового submission без обучения и изменения прогнозов."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import zipfile
from pathlib import Path

KEY = ("anon_polygon_id", "date")


def read_table(path: Path):
    raw = path.read_bytes()
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = [n for n in archive.namelist() if n.endswith(".csv") and not n.startswith("__MACOSX/")]
            if len(names) != 1:
                raise ValueError("ZIP должен содержать ровно один CSV")
            raw = archive.read(names[0])
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    rows = list(reader)
    if not rows or not set(KEY).issubset(reader.fieldnames or []):
        raise ValueError("Нужна непустая таблица с anon_polygon_id,date")
    indexed = {}
    for row in rows:
        key = tuple(row[c] for c in KEY)
        if not all(key) or key in indexed:
            raise ValueError("Пустой или повторяющийся ключ")
        indexed[key] = row
    return indexed


def score(input_path: Path, submission_path: Path, truth_path: Path):
    inputs, submission, truth = [read_table(p) for p in (input_path, submission_path, truth_path)]
    if any(row.get("is_synthetic_gap") not in ("True", "False", "1", "0") for row in inputs.values()):
        raise ValueError("Во входе нужен корректный is_synthetic_gap")
    expected = {k for k, row in inputs.items() if row["is_synthetic_gap"] in ("True", "1")}
    if not expected or expected != set(submission) or expected != set(truth):
        raise ValueError("Контрольные ключи input, submission и ground truth должны совпадать полностью")
    if any(set(row) != {*KEY, "primary_ndvi_pred"} for row in submission.values()):
        raise ValueError("Submission должен содержать только ключи и primary_ndvi_pred")
    errors = []
    for key in sorted(expected):
        actual = float(truth[key]["primary_ndvi_true"])
        predicted = float(submission[key]["primary_ndvi_pred"])
        if not math.isfinite(actual) or not math.isfinite(predicted):
            raise ValueError("Цели и прогнозы должны быть конечными числами")
        errors.append(predicted - actual)
    # Истинные значения не обрезаем: формула кейса оценивает все контрольные точки.
    rmse = math.sqrt(math.fsum(e * e for e in errors) / len(errors))
    return {
        "evaluation": "local_provided_ground_truth_not_platform_score",
        "n": len(errors),
        "polygons": len({k[0] for k in expected}),
        "rmse": rmse,
        "mae": math.fsum(abs(e) for e in errors) / len(errors),
        "gap_score": round(30 * max(0, 1 - rmse / 0.10), 2),
        "exact_key_match": True,
        "sha256": {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in (
                ("input", input_path),
                ("submission", submission_path),
                ("ground_truth", truth_path),
            )
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = score(args.input, args.submission, args.ground_truth)
    except (ValueError, KeyError, OSError, zipfile.BadZipFile) as exc:
        parser.exit(2, f"Ошибка оценки: {exc}\n")
    text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
