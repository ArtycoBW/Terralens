"""Воспроизводимый аудит исходных файлов. Не изменяет данные и не обучает модель."""

from __future__ import annotations

import hashlib
import json
import math
import struct
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "analysis"
KEY = ["anon_polygon_id", "date"]


def serializable(value):
    if isinstance(value, dict):
        return {str(k): serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serializable(v) for v in value]
    if isinstance(value, np.generic):
        return serializable(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is pd.NA:
        return None
    return value


def write_json(name, value):
    (OUT / name).write_text(
        json.dumps(serializable(value), ensure_ascii=False, indent=2, default=str, allow_nan=False),
        encoding="utf-8",
    )


def profile(df):
    dates = pd.to_datetime(df.date, errors="raise")
    reference = df.s2_ndvi.combine_first(df.landsat_ndvi).combine_first(df.modis_ndvi)
    known = df.primary_ndvi.notna()
    return {
        "rows": len(df),
        "columns": list(df.columns),
        "dtypes": df.dtypes.astype(str).to_dict(),
        "missing": df.isna().sum().to_dict(),
        "nunique": df.nunique().to_dict(),
        "duplicate_keys": int(df.duplicated(KEY).sum()),
        "date_min": str(dates.min().date()),
        "date_max": str(dates.max().date()),
        "rows_by_year": dates.dt.year.value_counts().sort_index().to_dict(),
        "crop_rows": df.crop_type.value_counts().to_dict(),
        "crop_polygons": df.groupby("crop_type").anon_polygon_id.nunique().to_dict(),
        "primary_known": int(known.sum()),
        "priority_matches": int(np.isclose(df.loc[known, "primary_ndvi"], reference[known]).sum()),
        "primary_out_of_range": int((df.primary_ndvi.abs() > 1).sum()),
        "s2_evi_abs_gt_2": int((df.s2_evi.abs() > 2).sum()),
        "landsat_ndwi_abs_gt_1": int((df.landsat_ndwi.abs() > 1).sum()),
        "negative_precip": int((df.era5_precip_mm < 0).sum()),
        "year_inconsistent": int((df.year.notna() & (df.year != dates.dt.year)).sum()),
        "doy_inconsistent": int((df.doy.notna() & (df.doy != dates.dt.dayofyear)).sum()),
        "nonfinite_numeric": {c: int(np.isinf(df[c].dropna()).sum()) for c in df.select_dtypes("number")},
        "status": df.status.value_counts(dropna=False).to_dict() if "status" in df else None,
        "describe": df.describe(include="all").to_dict(),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for file in sorted(ROOT.iterdir()):
        if file.suffix not in {".pdf", ".csv", ".zip"}:
            continue
        item = {
            "file": file.name,
            "bytes": file.stat().st_size,
            "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
        }
        if file.suffix == ".zip":
            with zipfile.ZipFile(file) as archive:
                item["members"] = [
                    {"path": entry.filename, "bytes": entry.file_size} for entry in archive.infolist()
                ]
                item["crc_error"] = archive.testzip()
        manifest.append(item)
    write_json("input-manifest.json", manifest)
    with zipfile.ZipFile(ROOT / "train-dataset.zip") as archive:
        with archive.open("train_dataset.csv") as stream:
            train = pd.read_csv(stream)
    test = pd.read_csv(ROOT / "test-dataset.csv")
    write_json("dataset-profile.json", {"train": profile(train), "test": profile(test)})
    gaps = test.loc[test.is_synthetic_gap]
    gap_context = []
    # Контекст разрешён только из открытых значений; скрытые цели не восстанавливаются для аудита.
    for polygon, part in test.groupby("anon_polygon_id"):
        available = pd.to_datetime(part.loc[part.primary_ndvi.notna(), "date"]).sort_values()
        for row in part.loc[part.is_synthetic_gap].itertuples():
            date = pd.Timestamp(row.date)
            previous = available[available < date]
            following = available[available > date]
            gap_context.append(
                {
                    "id": polygon,
                    "date": row.date,
                    "before_days": int((date - previous.iloc[-1]).days) if len(previous) else None,
                    "after_days": int((following.iloc[0] - date).days) if len(following) else None,
                }
            )
    context = pd.DataFrame(gap_context)
    checks = {
        "overlap_ids": sorted(set(train.anon_polygon_id) & set(test.anon_polygon_id)),
        "overlap_keys": len(train[KEY].merge(test[KEY], on=KEY)),
        "gap_rows": len(gaps),
        "gap_years": pd.to_datetime(gaps.date).dt.year.value_counts().sort_index().to_dict(),
        "gap_mask_nonnull": gaps.drop(columns=KEY + ["crop_type", "is_synthetic_gap"])
        .notna()
        .sum()
        .to_dict(),
        "gap_context_test_only": context[["before_days", "after_days"]].describe().to_dict(),
        "gap_without_left_test_only": int(context.before_days.isna().sum()),
        "gap_without_right_test_only": int(context.after_days.isna().sum()),
    }
    write_json("dataset-checks.json", checks)
    scene = {}
    with zipfile.ZipFile(ROOT / "ascend.zip") as archive:
        for name in archive.namelist():
            if not name.endswith(".glb"):
                continue
            content = archive.read(name)
            magic, version, size = struct.unpack_from("<4sII", content)
            chunk_size, chunk_type = struct.unpack_from("<II", content, 12)
            assert magic == b"glTF" and size == len(content) and chunk_type == 0x4E4F534A
            info = json.loads(content[20 : 20 + chunk_size])
            scene[name] = {
                "version": version,
                "bytes": size,
                "asset": info.get("asset"),
                "meshes": len(info.get("meshes", [])),
                "images": len(info.get("images", [])),
                "extensionsRequired": info.get("extensionsRequired", []),
                "external_uris": [
                    x["uri"] for group in ("images", "buffers") for x in info.get(group, []) if "uri" in x
                ],
            }
        lock = json.loads(archive.read("ascend/package-lock.json"))
        scene["lock_dependencies"] = {
            name: data.get("version")
            for name, data in lock["packages"].items()
            if name
            in {
                "node_modules/react",
                "node_modules/react-dom",
                "node_modules/three",
                "node_modules/vite",
                "node_modules/lenis",
            }
        }
    write_json("ascend-assets.json", scene)
    print(
        json.dumps(
            {"train_rows": len(train), "test_rows": len(test), "control_rows": len(gaps), "output": str(OUT)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
