"""Фиксированные пространственные folds, закрытый holdout и временная проверка."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from .io import KEY, DataError, atomic_write, canonical_hash, mask_context, write_json
from .model import fit, reconstruct


def metrics(truth, prediction):
    truth, prediction = np.asarray(truth, dtype=float), np.asarray(prediction, dtype=float)
    if len(truth) == 0:
        return {
            "n": 0,
            "rmse": None,
            "mae": None,
            "bias": None,
            "p95_absolute_error": None,
            "gap_score": None,
        }
    if not np.isfinite(truth).all() or not np.isfinite(prediction).all():
        raise DataError("Метрика требует конечных значений цели и предсказания")
    error = prediction - truth
    rmse = float(np.sqrt(np.mean(error**2)))
    return {
        "n": len(error),
        "rmse": rmse,
        "mae": float(np.mean(np.abs(error))),
        "bias": float(np.mean(error)),
        "p95_absolute_error": float(np.quantile(np.abs(error), 0.95)),
        "gap_score": round(30 * max(0, 1 - rmse / 0.10), 2),
    }


def make_mask(frame, seed, fraction=0.15, *, blocks=False):
    rng = np.random.default_rng(seed)
    result = pd.Series(False, index=frame.index)
    for _, part in frame.groupby(["anon_polygon_id", pd.to_datetime(frame.date).dt.year], sort=True):
        known = part.loc[part.primary_ndvi.notna()].sort_values("date")
        if known.empty:
            continue
        if blocks:
            # Целые календарные окна, включая длинные и краевые разрывы.
            days = pd.to_datetime(known.date).to_numpy(dtype="datetime64[D]").astype(np.int64)
            start = days[int(rng.integers(len(days)))]
            width = int(rng.choice([8, 15, 30, 45, 65]))
            selected = known.index[(days >= start) & (days < start + width)]
        else:
            selected = rng.choice(
                known.index.to_numpy(), size=max(1, round(len(known) * fraction)), replace=False
            )
        result.loc[selected] = True
    return result


def _score_context(frame, model, mask, scope, fold, seed):
    context = mask_context(frame, mask)
    result = reconstruct(context, model=model)
    selected = result.loc[mask, KEY + ["crop_type", "reconstructed", "origin", "gap_days"]].copy()
    selected["truth"] = frame.loc[mask, "primary_ndvi"]
    selected["algorithm"] = model["config"]["algorithm"]
    selected["scope"], selected["fold"], selected["mask_seed"] = scope, fold, seed
    selected["year"] = pd.to_datetime(selected.date).dt.year
    selected["gap_bucket"] = pd.cut(
        selected.gap_days, [-1, 8, 30, 60, np.inf], labels=["0-8", "9-30", "31-60", ">60"]
    ).astype(str)
    return selected


def summarize(frame):
    summary = metrics(frame.truth, frame.reconstructed)
    summary["fallback_rate"] = float(frame.origin.eq("climatology_fallback").mean()) if len(frame) else None
    summary["slices"] = {
        column: {
            str(key): metrics(part.truth, part.reconstructed)
            for key, part in frame.groupby(column, observed=True)
        }
        for column in ["crop_type", "year", "gap_bucket", "origin", "anon_polygon_id", "sensor"]
        if column in frame
    }
    aoi_metrics = [x["rmse"] for x in summary["slices"]["anon_polygon_id"].values()]
    summary["median_aoi_rmse"] = float(np.median(aoi_metrics)) if aoi_metrics else None
    summary["p90_aoi_rmse"] = float(np.quantile(aoi_metrics, 0.9)) if aoi_metrics else None
    # Resample whole AOIs, preserving the dependence between repeated masks and seasons.
    groups = [
        (float(np.square(part.reconstructed - part.truth).sum()), len(part))
        for _, part in frame.groupby("anon_polygon_id")
    ]
    if groups:
        rng = np.random.default_rng(42)
        totals = np.asarray(groups)
        sampled = totals[rng.integers(len(groups), size=(1000, len(groups)))].sum(axis=1)
        bounds = np.quantile(np.sqrt(sampled[:, 0] / sampled[:, 1]), [0.025, 0.975])
        summary["rmse_bootstrap_aoi_95"] = bounds.tolist()
    for column in summary["slices"]:
        for key, part in frame.groupby(column, observed=True):
            summary["slices"][column][str(key)]["fallback_rate"] = float(
                part.origin.eq("climatology_fallback").mean()
            )
            summary["slices"][column][str(key)]["unavailable_rate"] = float(
                part.origin.eq("unavailable").mean()
            )
    return summary


def evaluate(frame, config):
    output = Path(config["output"])
    ids = np.array(sorted(frame.anon_polygon_id.unique()))
    if len(ids) < config.get("folds", 5) + 2:
        raise DataError("Недостаточно полей для пространственных folds и закрытого holdout")
    rng = np.random.default_rng(config.get("seed", 42))
    rng.shuffle(ids)
    holdout_n = max(1, round(len(ids) * config.get("holdout_fraction", 0.2)))
    locked_ids, development_ids = sorted(ids[:holdout_n]), sorted(ids[holdout_n:])
    development = frame.loc[frame.anon_polygon_id.isin(development_ids)]
    splitter = GroupKFold(n_splits=config.get("folds", 5))
    folds = []
    for fold, (train_index, val_index) in enumerate(
        splitter.split(development, groups=development.anon_polygon_id)
    ):
        folds.append(
            {
                "fold": fold,
                "train_ids": sorted(development.iloc[train_index].anon_polygon_id.unique()),
                "validation_ids": sorted(development.iloc[val_index].anon_polygon_id.unique()),
            }
        )
    plan = {
        "seed": config.get("seed", 42),
        "locked_holdout_ids": locked_ids,
        "folds": folds,
        "mask_seeds": config.get("mask_seeds", [42, 137]),
        "config": config,
    }
    # Публикуем split до расчёта/выбора кандидатов. Повтор с иной схемой требует нового output.
    plan_path = output / "split_manifest.json"
    if plan_path.exists():
        import json

        if canonical_hash(json.loads(plan_path.read_text())) != canonical_hash(plan):
            raise DataError("В каталоге уже зафиксирован другой split; выберите новый output")
    write_json(plan_path, plan)
    results, mask_hashes = [], {}
    for fold in folds:
        training = development.loc[development.anon_polygon_id.isin(fold["train_ids"])]
        validation = development.loc[development.anon_polygon_id.isin(fold["validation_ids"])]
        for seed in plan["mask_seeds"]:
            for blocks in [False, True]:
                scope = "development_blocks" if blocks else "development_points"
                mask = make_mask(validation, seed, config.get("mask_fraction", 0.15), blocks=blocks)
                name = f"{scope}-{fold['fold']}-{seed}"
                keys = validation.loc[mask, KEY].to_dict("records")
                write_json(output / "masks" / f"{name}.json", keys)
                mask_hashes[name] = canonical_hash(keys)
                for algorithm in config.get("algorithms", ["neighbor_mean", "linear", "pchip"]):
                    model = fit(training, config | {"algorithm": algorithm})
                    results.append(_score_context(validation, model, mask, scope, fold["fold"], seed))
        print(f"Проверен development fold {fold['fold'] + 1}/{len(folds)}", flush=True)
    predictions = pd.concat(results, ignore_index=True)
    development_metrics = {
        algorithm: summarize(part)
        for algorithm, part in predictions.loc[predictions.scope.eq("development_points")].groupby(
            "algorithm"
        )
    }
    selected = min(development_metrics, key=lambda x: development_metrics[x]["rmse"])
    # Holdout запускается только для выбранного на development кандидата.
    locked = frame.loc[frame.anon_polygon_id.isin(locked_ids)]
    model = fit(development, config | {"algorithm": selected})
    for blocks in [False, True]:
        mask = make_mask(locked, 991, config.get("mask_fraction", 0.15), blocks=blocks)
        scope = "locked_blocks" if blocks else "locked_points"
        keys = locked.loc[mask, KEY].to_dict("records")
        write_json(output / "masks" / f"{scope}.json", keys)
        mask_hashes[scope] = canonical_hash(keys)
        results.append(_score_context(locked, model, mask, scope, -1, 991))
    years = pd.to_datetime(frame.date).dt.year
    final_year = int(years.max())
    temporal_train, temporal_test = frame.loc[years < final_year], frame.loc[years == final_year]
    temporal_model = fit(temporal_train, config | {"algorithm": selected})
    mask = make_mask(temporal_test, 991, config.get("mask_fraction", 0.15))
    keys = temporal_test.loc[mask, KEY].to_dict("records")
    write_json(output / "masks" / "temporal.json", keys)
    mask_hashes["temporal"] = canonical_hash(keys)
    results.append(_score_context(temporal_test, temporal_model, mask, "temporal", -1, 991))
    predictions = pd.concat(results, ignore_index=True)
    report = {
        "selected_algorithm": selected,
        "selection_rule": "minimum pooled development_points RMSE; unchanged raw targets",
        "development": development_metrics,
        "scopes": {
            f"{scope}/{algorithm}": summarize(part)
            for (scope, algorithm), part in predictions.groupby(["scope", "algorithm"])
        },
        "split_hash": canonical_hash(plan),
        "mask_hashes": mask_hashes,
        "limitations": [
            "Локальная оценка; private test ground truth недоступен",
            "Повторные маски одного поля зависимы",
            "Региональный перенос по анонимным CSV не измерен",
            "Интервалы восстановления пока не откалиброваны",
        ],
    }
    atomic_write(output / "predictions.csv", predictions.to_csv(index=False))
    write_json(output / "report.json", report)
    write_json(output / "selected_config.json", config | {"algorithm": selected, "output": "artifacts/model"})
    rows = [
        {"scope": scope, "algorithm": algorithm, **metrics(part.truth, part.reconstructed)}
        for (scope, algorithm), part in predictions.groupby(["scope", "algorithm"])
    ]
    atomic_write(output / "metrics.csv", pd.DataFrame(rows).to_csv(index=False))
    return report
