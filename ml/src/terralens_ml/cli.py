from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from .io import DataError, audit, read_csv, sha256, validate_submission, write_json, write_submission
from .model import fit, load_model, predict_submission, save_model
from .research import run_research
from .validation import evaluate


def main(argv=None):
    parser = argparse.ArgumentParser(description="TerraLens: автономное восстановление NDVI")
    commands = parser.add_subparsers(dest="command", required=True)
    audit_parser = commands.add_parser("audit")
    audit_parser.add_argument("--input", required=True)
    audit_parser.add_argument("--output")
    for command in ["train", "evaluate", "research"]:
        sub = commands.add_parser(command)
        sub.add_argument("--config", required=True)
        if command == "research":
            sub.add_argument(
                "--development-only",
                action="store_true",
                help="Только development folds и выбор; без финальной модели и assessment",
            )
    predict = commands.add_parser("predict")
    predict.add_argument("--input", required=True)
    predict.add_argument("--output", required=True)
    predict.add_argument("--model", required=True)
    predict.add_argument("--reference-history")
    validate = commands.add_parser("validate-submission")
    validate.add_argument("--input", required=True)
    validate.add_argument("--submission", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command in ["train", "evaluate", "research"]:
            config = yaml.safe_load(Path(args.config).read_text())
            if not isinstance(config, dict) or not {"input", "output"} <= config.keys():
                raise DataError("Конфигурация должна задавать input и output")
            frame = read_csv(config["input"])
            if args.command == "train":
                result = save_model(fit(frame, config), config["output"], input_path=config["input"])
            else:
                report = (
                    run_research(frame, config, development_only=args.development_only)
                    if args.command == "research"
                    else evaluate(frame, config)
                )
                result = {
                    "selected_algorithm": report["selected_algorithm"],
                    "development": {
                        k: {x: v[x] for x in ["n", "rmse", "mae", "gap_score"]}
                        for k, v in report["development"].items()
                    },
                    "report": str(Path(config["output"]) / "report.json"),
                }
        else:
            frame = read_csv(args.input)
            if args.command == "audit":
                result = audit(frame)
                if args.output:
                    write_json(args.output, result)
            elif args.command == "validate-submission":
                result = validate_submission(frame, args.submission)
            else:
                model, manifest = load_model(args.model)
                history = read_csv(args.reference_history) if args.reference_history else None
                prediction, origins = predict_submission(frame, model, history)
                result = write_submission(frame, prediction, args.output)
                write_json(
                    str(args.output) + ".manifest.json",
                    {
                        "input_sha256": sha256(args.input),
                        "model_manifest_sha256": sha256(args.model),
                        "model_id": manifest["model_id"],
                        "reference_history_sha256": sha256(args.reference_history)
                        if args.reference_history
                        else None,
                        "output_sha256": sha256(args.output),
                        "rows": len(prediction),
                        "origins": origins,
                    },
                )
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (DataError, OSError, yaml.YAMLError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2
