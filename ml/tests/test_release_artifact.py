"""The checked-out release must survive Windows Git line-ending conversion."""

import json
from hashlib import sha256
from pathlib import Path


def test_committed_model_matches_signed_manifest():
    directory = Path(__file__).resolve().parents[1] / "artifacts" / "final"
    manifest = json.loads((directory / "manifest.json").read_text())
    for filename, digest in manifest["files"].items():
        assert sha256((directory / filename).read_bytes()).hexdigest() == digest
