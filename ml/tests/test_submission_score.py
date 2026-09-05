"""Проверки локальной оценки: соответствие ключей важнее совпадения размера."""

import csv
import runpy
import tempfile
import unittest
import zipfile
from pathlib import Path

score = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/score_submission.py"))["score"]


class SubmissionScoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.inputs = self.write(
            "input.csv", ["anon_polygon_id", "date", "is_synthetic_gap"], [["a", "2024-01-01", "True"]]
        )
        self.prediction = self.write(
            "submission.csv", ["anon_polygon_id", "date", "primary_ndvi_pred"], [["a", "2024-01-01", 0.5]]
        )
        self.truth = self.write(
            "truth.csv", ["date", "primary_ndvi_true", "anon_polygon_id"], [["2024-01-01", 0.52, "a"]]
        )

    def write(self, name, header, rows):
        path = self.root / name
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(header)
            writer.writerows(rows)
        return path

    def test_formula_and_zip_truth(self):
        archive = self.root / "truth.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.write(self.truth, "truth.csv")
            output.writestr("__MACOSX/._truth.csv", "metadata")
        result = score(self.inputs, self.prediction, archive)
        self.assertAlmostEqual(result["rmse"], 0.02)
        self.assertEqual(result["gap_score"], 24)

    def test_different_keys_with_same_row_count_are_rejected(self):
        self.truth.write_text(self.truth.read_text().replace("2024-01-01", "2024-01-02"))
        with self.assertRaisesRegex(ValueError, "совпадать полностью"):
            score(self.inputs, self.prediction, self.truth)

    def test_duplicates_and_nonfinite_predictions_are_rejected(self):
        for value in ("nan", "inf", "-inf"):
            self.write(
                "submission.csv",
                ["anon_polygon_id", "date", "primary_ndvi_pred"],
                [["a", "2024-01-01", value]],
            )
            with self.assertRaisesRegex(ValueError, "конечными"):
                score(self.inputs, self.prediction, self.truth)
        with self.prediction.open("a") as stream:
            stream.write("a,2024-01-01,0.5\n")
        with self.assertRaisesRegex(ValueError, "повторяющийся"):
            score(self.inputs, self.prediction, self.truth)
