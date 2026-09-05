"""Строгий ввод и атомарная публикация файлов с проверкой контрольных ключей."""

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

KEY = ["anon_polygon_id", "date"]
SENSORS = [
    "s2_ndvi",
    "s2_evi",
    "s2_ndwi",
    "landsat_ndvi",
    "landsat_evi",
    "landsat_ndwi",
    "modis_ndvi",
    "modis_evi",
]
DYNAMIC = SENSORS + [
    "era5_temp_c",
    "era5_precip_mm",
    "year",
    "doy",
    "primary_ndvi",
    "ndvi_climatology_mean",
    "ndvi_climatology_std",
    "n_reference_years",
    "ndvi_zscore",
]
SUBMISSION = KEY + ["primary_ndvi_pred"]


class DataError(ValueError):
    """Понятная пользователю ошибка данных или артефакта."""


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, default=str).encode()
    ).hexdigest()


def atomic_write(path: str | Path, content: str | bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content.encode("utf-8") if isinstance(content, str) else content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_json(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False, default=str) + "\n")


def parse_bool(values: pd.Series) -> pd.Series:
    mapping = {"True": True, "False": False, "1": True, "0": False}
    text = values.astype(str)
    invalid = ~text.isin(mapping)
    if invalid.any():
        raise DataError(
            f"is_synthetic_gap: допустимы только True/False или 1/0; строка {int(np.flatnonzero(invalid)[0]) + 2}"
        )
    return text.map(mapping).astype(bool)


def read_csv(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    try:
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                members = [
                    x for x in archive.namelist() if x.endswith(".csv") and not x.startswith("__MACOSX/")
                ]
                if len(members) != 1:
                    raise DataError("ZIP должен содержать ровно один CSV с данными")
                raw = archive.read(members[0])
        else:
            raw = path.read_bytes()
        frame = pd.read_csv(io.StringIO(raw.decode("utf-8-sig")), dtype=str, keep_default_na=False)
    except (UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError, zipfile.BadZipFile) as exc:
        raise DataError("Ожидается CSV UTF-8 с разделителем-запятой") from exc
    required = set(KEY + ["crop_type", "primary_ndvi"])
    if missing := required - set(frame):
        raise DataError(f"Отсутствуют обязательные столбцы: {', '.join(sorted(missing))}")
    if frame[KEY].eq("").any().any():
        raise DataError("Идентификатор поля и дата не могут быть пустыми")
    if not frame.date.str.fullmatch(r"\d{4}-\d{2}-\d{2}").all():
        raise DataError("Дата должна иметь формат YYYY-MM-DD")
    try:
        pd.to_datetime(frame.date, format="%Y-%m-%d", errors="raise")
    except ValueError as exc:
        raise DataError("Обнаружена несуществующая календарная дата") from exc
    if frame.duplicated(KEY).any():
        raise DataError("Повторяется ключ anon_polygon_id,date")
    for column in set(DYNAMIC) & set(frame):
        try:
            frame[column] = pd.to_numeric(
                frame[column].replace({"": np.nan, "NaN": np.nan, "nan": np.nan}), errors="raise"
            ).astype(float)
        except ValueError as exc:
            raise DataError(f"Столбец {column} должен содержать числа или пропуски") from exc
        if np.isinf(frame[column]).any():
            raise DataError(f"Бесконечное значение в столбце {column}")
    if "is_synthetic_gap" in frame:
        frame["is_synthetic_gap"] = parse_bool(frame.is_synthetic_gap)
    frame["input_row_id"] = np.arange(len(frame))
    return frame


def mask_context(frame: pd.DataFrame, mask) -> pd.DataFrame:
    result = frame.copy(deep=True)
    mask = parse_bool(pd.Series(mask, index=result.index))
    if "is_synthetic_gap" in result:
        result["is_synthetic_gap"] = parse_bool(result.is_synthetic_gap)
    # Скрываем также неизвестные производные признаки: разрешён только статический ключ/культура.
    dynamic = result.columns.difference(KEY + ["crop_type", "input_row_id", "is_synthetic_gap"])
    for column in dynamic:
        result.loc[mask, column] = None if result[column].dtype == object else np.nan
    dates = pd.to_datetime(result.date)
    result["year"] = dates.dt.year
    result["doy"] = dates.dt.dayofyear
    return result


def audit(frame: pd.DataFrame) -> dict:
    mask = frame.get("is_synthetic_gap", pd.Series(False, index=frame.index))
    return {
        "rows": len(frame),
        "polygons": int(frame.anon_polygon_id.nunique()),
        "known_targets": int(frame.primary_ndvi.notna().sum()),
        "control_rows": int(mask.sum()),
        "duplicate_keys": int(frame.duplicated(KEY).sum()),
        "date_min": frame.date.min() if len(frame) else None,
        "date_max": frame.date.max() if len(frame) else None,
        "target_out_of_range": int((frame.primary_ndvi.abs() > 1).sum()),
        "missing": {c: int(frame[c].isna().sum()) for c in DYNAMIC if c in frame},
    }


def validate_submission(test: pd.DataFrame, submission: str | Path | pd.DataFrame) -> dict:
    if "is_synthetic_gap" not in test:
        raise DataError("Во входном test отсутствует is_synthetic_gap")
    if isinstance(submission, pd.DataFrame):
        result = submission.copy()
    else:
        try:
            result = pd.read_csv(submission, dtype={c: str for c in KEY}, encoding="utf-8")
        except (UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
            raise DataError("Некорректный CSV submission") from exc
    if list(result.columns) != SUBMISSION:
        raise DataError(f"Submission должен содержать ровно {','.join(SUBMISSION)}")
    expected = test.loc[parse_bool(test.is_synthetic_gap), KEY]
    if result.duplicated(KEY).any():
        raise DataError("Submission содержит повторяющиеся ключи")
    if len(result) != len(expected) or set(map(tuple, result[KEY].to_numpy())) != set(
        map(tuple, expected.to_numpy())
    ):
        raise DataError(
            f"Submission должен содержать точные контрольные ключи: ожидается {len(expected)}, получено {len(result)}"
        )
    try:
        values = pd.to_numeric(result.primary_ndvi_pred, errors="raise").to_numpy(dtype=float)
    except (ValueError, TypeError) as exc:
        raise DataError("Предсказания должны быть вещественными числами") from exc
    if not np.isfinite(values).all():
        raise DataError("Предсказания содержат NaN или бесконечность")
    return {
        "valid": True,
        "rows": len(result),
        "message": "Контрольных строк нет; записан только заголовок"
        if not len(result)
        else "Submission прошёл проверку",
    }


def write_submission(test, result, path):
    validate_submission(test, result)
    # Повторное чтение проверяется до публикации целевого файла.
    text = result.to_csv(index=False, float_format="%.17g", lineterminator="\n")
    validate_submission(test, pd.read_csv(io.StringIO(text), dtype={c: str for c in KEY}))
    atomic_write(path, text)
    return validate_submission(test, path)
