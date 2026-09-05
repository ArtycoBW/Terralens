"""Проверить два batch-инференса при запрещённой сети в отдельном ML-окружении."""

import argparse
import importlib.metadata
import importlib.util
import os
import socket
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from terralens_ml.cli import main as cli
from terralens_ml.io import read_csv, sha256, validate_submission, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="test-dataset.csv")
    parser.add_argument("--model", default="ml/artifacts/final/manifest.json")
    parser.add_argument("--output", default="artifacts/offline-release")
    parser.add_argument("--require-standalone", action="store_true")
    args = parser.parse_args()
    absent = {name: importlib.util.find_spec(name) is None for name in ["django", "celery", "redis"]}
    if args.require_standalone and not all(absent.values()):
        raise RuntimeError("Запустите в отдельном окружении с установленным только ./ml")
    for name in ["DJANGO_SETTINGS_MODULE", "DATABASE_URL", "REDIS_URL", "DJANGO_SECRET_KEY"]:
        os.environ.pop(name, None)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    hashes = []
    with (
        patch.object(socket.socket, "connect", side_effect=RuntimeError("Сеть запрещена")),
        patch.object(socket.socket, "connect_ex", side_effect=RuntimeError("Сеть запрещена")),
        patch.object(socket, "create_connection", side_effect=RuntimeError("Сеть запрещена")),
    ):
        for number in [1, 2]:
            path = output / f"submission-{number}.csv"
            code = cli(["predict", "--input", args.input, "--model", args.model, "--output", str(path)])
            if code:
                raise RuntimeError(f"Инференс завершился с кодом {code}")
            validation = validate_submission(read_csv(args.input), path)
            hashes.append(sha256(path))
    if hashes[0] != hashes[1]:
        raise RuntimeError("Повторные предсказания отличаются")
    write_json(
        output / "evidence.json",
        {
            "checked_at": datetime.now(UTC).isoformat(),
            "network_disabled": True,
            "missing_modules": absent,
            "input_sha256": sha256(args.input),
            "model_manifest_sha256": sha256(args.model),
            "submission_sha256": hashes[0],
            "identical_runs": 2,
            "validation": validation,
            "dependencies": {
                name: importlib.metadata.version(name)
                for name in ["terralens-ml", "numpy", "pandas", "scipy", "scikit-learn", "catboost"]
            },
        },
    )


if __name__ == "__main__":
    main()
