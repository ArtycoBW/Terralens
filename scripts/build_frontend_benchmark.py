"""Publish only anonymous submission points and verified aggregate metadata for UI."""

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    submission = ROOT / "deliverables/submission.csv"
    grouped = defaultdict(list)
    with submission.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            grouped[row["anon_polygon_id"]].append(
                {"date": row["date"], "value": float(row["primary_ndvi_pred"])}
            )
    output = {
        "source": "deliverables/submission.csv",
        "sha256": hashlib.sha256(submission.read_bytes()).hexdigest(),
        "rows": sum(map(len, grouped.values())),
        "model_id": json.loads((ROOT / "ml/artifacts/final/manifest.json").read_text())["model_id"],
        "official_score": None,
        "polygons": [
            {"id": key, "points": sorted(points, key=lambda p: p["date"])}
            for key, points in sorted(grouped.items())
        ],
    }
    destination = ROOT / "frontend/src/data/benchmark.json"
    destination.parent.mkdir(exist_ok=True, parents=True)
    destination.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Published {output['rows']} anonymous target predictions")


if __name__ == "__main__":
    main()
