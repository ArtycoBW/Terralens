"""Фиксированный второй этап исследования без повторного использования просмотренного holdout."""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from .io import KEY, DataError, atomic_write, canonical_hash, sha256, write_json
from .model import DEFAULT_CONFIG, fit, save_model
from .uncertainty import calibrate, coverage
from .validation import _score_context, make_mask, metrics, summarize

DEFAULT_ASSESSMENT_STATUS = "Post-selection assessment; these source AOIs appeared in the earlier baseline study, not a new blind holdout"
DEFAULT_ASSESSMENT_LIMITATION = (
    "Remaining AOIs previously appeared in baseline development; assessment is not newly blind data"
)


def _write_results(
    output,
    predictions,
    *,
    selected,
    selected_config,
    selection_metrics,
    timings,
    plan,
    mask_hashes,
    selection_rule,
    selection_guardrail,
    assessment_limitations,
    development_only=False,
    evaluation=None,
    calibration=None,
):
    report = {
        "selected_candidate": selected,
        "selected_algorithm": selected_config.get("algorithm", DEFAULT_CONFIG["algorithm"]),
        "selection_rule": selection_rule,
        "selection_guardrail": selection_guardrail,
        "development_only": development_only,
        "assessment_status": plan["assessment_status"],
        "development": selection_metrics,
        "elapsed_candidate_seconds": timings,
        "scopes": {
            f"{scope}/{candidate}": summarize(part)
            for (scope, candidate), part in predictions.groupby(["scope", "candidate"])
        },
        "interval_assessment": {}
        if evaluation is None
        else {scope: coverage(part, calibration) for scope, part in evaluation.groupby("scope")},
        "calibration": calibration,
        "split_hash": canonical_hash(plan),
        "mask_hashes": mask_hashes,
        "limitations": [
            "Official test labels unavailable; no official RMSE",
            "Previously inspected 8 holdout AOIs excluded entirely",
            *assessment_limitations,
            "Calibration points within AOI and repeated masks are dependent; empirical intervals have no unconditional guarantee",
            "Benchmark has no geography; live regional transfer and agronomic causes remain unvalidated",
            *(
                [
                    "Development-only run: no final fit, calibration, assessment, temporal scoring or model artifact"
                ]
                if development_only
                else []
            ),
        ],
    }
    rows = [
        {"scope": scope, "candidate": candidate, **metrics(part.truth, part.reconstructed)}
        for (scope, candidate), part in predictions.groupby(["scope", "candidate"])
    ]
    atomic_write(output / "predictions.csv", predictions.to_csv(index=False))
    atomic_write(output / "metrics.csv", pd.DataFrame(rows).to_csv(index=False))
    write_json(output / "report.json", report)
    return report


def run_research(frame, config, *, development_only=False):
    baseline = config.get("selection_baseline")
    if baseline is not None and (not isinstance(baseline, str) or baseline not in config["candidates"]):
        raise DataError("selection_baseline должен указывать существующего кандидата")
    assessment_status = config.get("assessment_status", DEFAULT_ASSESSMENT_STATUS)
    if not isinstance(assessment_status, str) or not assessment_status.strip():
        raise DataError("assessment_status должен быть непустой строкой")
    assessment_limitations = config.get(
        "assessment_limitations",
        [
            assessment_status if "assessment_status" in config else DEFAULT_ASSESSMENT_LIMITATION,
        ],
    )
    if not isinstance(assessment_limitations, list) or any(
        not isinstance(item, str) or not item.strip() for item in assessment_limitations
    ):
        raise DataError("assessment_limitations должен быть списком непустых строк")
    output = Path(config["output"])
    old_plan = json.loads(Path(config["prior_split"]).read_text())
    excluded = old_plan["locked_holdout_ids"]
    ids = np.array(sorted(set(frame.anon_polygon_id) - set(excluded)))
    rng = np.random.default_rng(config["seed"])
    rng.shuffle(ids)
    calibration_n, assessment_n = config["calibration_fields"], config["assessment_fields"]
    calibration_ids = sorted(ids[:calibration_n])
    assessment_ids = sorted(ids[calibration_n : calibration_n + assessment_n])
    selection_ids = sorted(ids[calibration_n + assessment_n :])
    if len(selection_ids) < config["folds"]:
        raise DataError("Недостаточно AOI для независимых selection/calibration/assessment")
    final_year = int(pd.to_datetime(frame.date).dt.year.max())
    past = frame.loc[pd.to_datetime(frame.date).dt.year < final_year]
    selection = past.loc[past.anon_polygon_id.isin(selection_ids)]
    folds = []
    for fold, (train, validation) in enumerate(
        GroupKFold(config["folds"]).split(selection, groups=selection.anon_polygon_id)
    ):
        folds.append(
            {
                "fold": fold,
                "train_ids": sorted(selection.iloc[train].anon_polygon_id.unique()),
                "validation_ids": sorted(selection.iloc[validation].anon_polygon_id.unique()),
            }
        )
    plan = {
        "config": config,
        "excluded_previously_inspected_holdout": excluded,
        "selection_ids": selection_ids,
        "calibration_ids": calibration_ids,
        "assessment_ids": assessment_ids,
        "temporal_year": final_year,
        "folds": folds,
        "input_sha256": sha256(config["input"]),
        "assessment_status": assessment_status,
    }
    manifest_path = output / "split_manifest.json"
    if manifest_path.exists() and canonical_hash(json.loads(manifest_path.read_text())) != canonical_hash(
        plan
    ):
        raise DataError("Схема исследования уже зафиксирована; используйте другой output")
    write_json(manifest_path, plan)
    mask_hashes, results, timings = {}, [], {}

    def score(data, model, scope, fold, seed, blocks):
        mask = make_mask(data, seed, config["mask_fraction"], blocks=blocks)
        name = f"{scope}-{fold}-{seed}"
        keys = data.loc[mask, KEY].to_dict("records")
        write_json(output / "masks" / f"{name}.json", keys)
        mask_hashes[name] = canonical_hash(keys)
        scored = _score_context(data, model, mask, scope, fold, seed)
        # Наличие сырых сенсорных значений используется только для срезов отчёта, не как признак.
        sensor = pd.Series("unknown", index=data.index)
        for column in ["modis_ndvi", "landsat_ndvi", "s2_ndvi"]:
            if column in data:
                sensor.loc[data[column].notna()] = column
        scored["sensor"] = sensor.loc[mask]
        return scored

    base = {
        k: v
        for k, v in config.items()
        if k in ["seed", "max_gap_days", "max_edge_days", "season_start_month", "boost_iterations"]
    }
    for fold in folds:
        training = selection.loc[selection.anon_polygon_id.isin(fold["train_ids"])]
        validation = selection.loc[selection.anon_polygon_id.isin(fold["validation_ids"])]
        for candidate, options in config["candidates"].items():
            started = time.monotonic()
            model = fit(training, base | options)
            for seed in config["mask_seeds"]:
                for blocks in [False, True]:
                    scope = "development_blocks" if blocks else "development_points"
                    scored = score(validation, model, scope, fold["fold"], seed, blocks)
                    scored["candidate"] = candidate
                    results.append(scored)
            timings[candidate] = timings.get(candidate, 0) + time.monotonic() - started
            print(f"fold {fold['fold'] + 1}/{len(folds)}: {candidate}", flush=True)
    development = pd.concat(results, ignore_index=True)
    selection_metrics = {
        name: summarize(part)
        for name, part in development.loc[development.scope.eq("development_points")].groupby("candidate")
    }
    eligible = list(selection_metrics)
    selection_rule = "minimum pooled development_points RMSE, all raw masked targets; frozen before calibration and assessment"
    selection_guardrail = None
    if baseline is not None:
        block_rmse = {
            name: metrics(part.truth, part.reconstructed)["rmse"]
            for name, part in development.loc[development.scope.eq("development_blocks")].groupby("candidate")
        }
        limit = block_rmse.get(baseline)
        if limit is None or not np.isfinite(limit):
            raise DataError("У selection_baseline нет конечной development_blocks RMSE")
        eligible = [
            name for name in eligible if block_rmse.get(name) is not None and block_rmse[name] <= limit
        ]
        selection_rule = (
            "minimum pooled development_points RMSE among candidates with pooled development_blocks RMSE "
            "no greater than selection_baseline; frozen before calibration and assessment"
        )
        selection_guardrail = {
            "baseline": baseline,
            "maximum_blocks_rmse": limit,
            "blocks_rmse": block_rmse,
            "eligible_candidates": eligible,
        }
    if not eligible or any(selection_metrics[name]["rmse"] is None for name in eligible):
        raise DataError("Нет кандидата с конечной development RMSE")
    selected = min(eligible, key=lambda name: selection_metrics[name]["rmse"])
    # Модель и параметры фиксируются до прогнозов на calibration и assessment.
    selected_config = base | config["candidates"][selected]
    write_json(output / "selected_config.json", selected_config)
    report_options = {
        "selected": selected,
        "selected_config": selected_config,
        "selection_metrics": selection_metrics,
        "timings": timings,
        "plan": plan,
        "mask_hashes": mask_hashes,
        "selection_rule": selection_rule,
        "selection_guardrail": selection_guardrail,
        "assessment_limitations": assessment_limitations,
    }
    if development_only:
        return _write_results(output, development, development_only=True, **report_options)
    model = fit(selection, selected_config)
    model["training_scope"] = {
        "polygon_ids": selection_ids,
        "years_before": final_year,
        "excluded_previously_inspected_holdout": excluded,
        "calibration_ids": calibration_ids,
        "assessment_ids": assessment_ids,
    }
    calibration = past.loc[past.anon_polygon_id.isin(calibration_ids)]
    calibration_predictions = pd.concat(
        [
            score(
                calibration, model, "calibration_blocks" if blocks else "calibration_points", -1, 991, blocks
            )
            for blocks in [False, True]
        ],
        ignore_index=True,
    )
    model["calibration"] = calibrate(calibration_predictions, level=config["calibration_level"])
    assessment = past.loc[past.anon_polygon_id.isin(assessment_ids)]
    assessment_predictions = [
        score(assessment, model, "assessment_blocks" if blocks else "assessment_points", -1, 2003, blocks)
        for blocks in [False, True]
    ]
    temporal_ids = selection_ids + assessment_ids
    temporal = frame.loc[frame.anon_polygon_id.isin(temporal_ids)]
    temporal_mask = pd.to_datetime(temporal.date).dt.year.eq(final_year)
    # Исторические модели сохраняют прежний видимый контекст; обучение ограничено годами до final_year.
    for blocks in [False, True]:
        mask = make_mask(temporal.loc[temporal_mask], 2003, config["mask_fraction"], blocks=blocks)
        full_mask = mask.reindex(temporal.index, fill_value=False)
        scope = "temporal_blocks" if blocks else "temporal_points"
        keys = temporal.loc[full_mask, KEY].to_dict("records")
        write_json(output / "masks" / f"{scope}.json", keys)
        mask_hashes[scope] = canonical_hash(keys)
        assessment_predictions.append(_score_context(temporal, model, full_mask, scope, -1, 2003))
    evaluation = pd.concat([calibration_predictions, *assessment_predictions], ignore_index=True)
    evaluation["candidate"] = selected
    all_predictions = pd.concat([development, evaluation], ignore_index=True)
    report = _write_results(
        output,
        all_predictions,
        evaluation=evaluation,
        calibration=model["calibration"],
        **report_options,
    )
    save_model(
        model,
        config["artifact_output"],
        input_path=config["input"],
        metrics={
            "development": selection_metrics[selected],
            "assessment": {
                k: v for k, v in report["scopes"].items() if k.startswith(("assessment", "temporal"))
            },
            "interval_assessment": report["interval_assessment"],
        },
        validation_hashes={"split": report["split_hash"], "masks": mask_hashes},
    )
    return report
