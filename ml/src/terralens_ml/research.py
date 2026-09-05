"""Frozen second-stage research without reusing the already inspected holdout."""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from .io import KEY, DataError, atomic_write, canonical_hash, sha256, write_json
from .model import fit, save_model
from .uncertainty import calibrate, coverage
from .validation import _score_context, make_mask, metrics, summarize


def run_research(frame, config):
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
        "assessment_status": "Post-selection assessment; these source AOIs appeared in the earlier baseline study, not a new blind holdout",
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
        # Raw sensor availability is used only for report stratification, never as a feature.
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
    selected = min(selection_metrics, key=lambda name: selection_metrics[name]["rmse"])
    # The model and hyperparameters are frozen before any calibration/assessment predictions.
    selected_config = base | config["candidates"][selected]
    write_json(output / "selected_config.json", selected_config)
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
    # Earlier visible context is retained for history models; global fitting remains before final_year.
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
    report = {
        "selected_candidate": selected,
        "selected_algorithm": model["config"]["algorithm"],
        "selection_rule": "minimum pooled development_points RMSE, all raw masked targets; frozen before calibration and assessment",
        "development": selection_metrics,
        "elapsed_candidate_seconds": timings,
        "scopes": {
            f"{scope}/{candidate}": summarize(part)
            for (scope, candidate), part in all_predictions.groupby(["scope", "candidate"])
        },
        "interval_assessment": {
            scope: coverage(part, model["calibration"]) for scope, part in evaluation.groupby("scope")
        },
        "calibration": model["calibration"],
        "split_hash": canonical_hash(plan),
        "mask_hashes": mask_hashes,
        "limitations": [
            "Official test labels unavailable; no official RMSE",
            "Previously inspected 8 holdout AOIs excluded entirely",
            "Remaining AOIs previously appeared in baseline development; assessment is not newly blind data",
            "Calibration points within AOI and repeated masks are dependent; empirical intervals have no unconditional guarantee",
            "Benchmark has no geography; live regional transfer and agronomic causes remain unvalidated",
        ],
    }
    rows = [
        {"scope": scope, "candidate": candidate, **metrics(part.truth, part.reconstructed)}
        for (scope, candidate), part in all_predictions.groupby(["scope", "candidate"])
    ]
    atomic_write(output / "predictions.csv", all_predictions.to_csv(index=False))
    atomic_write(output / "metrics.csv", pd.DataFrame(rows).to_csv(index=False))
    write_json(output / "report.json", report)
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
