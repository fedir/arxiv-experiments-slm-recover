"""Controls for portable output preservation and retained grading boundaries."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import reproduce

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "frozen"))
import public_checks


class ReleaseControls(unittest.TestCase):
    def test_outputs_cannot_overlap_evidence_or_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for output in (
                root,
                root / "benchmarks",
                root / "benchmarks/new",
                root / "scientific/new",
            ):
                with self.assertRaisesRegex(ValueError, "separate"):
                    reproduce.output_directory(root, output)
            output = reproduce.output_directory(root, root / "results")
            with self.assertRaisesRegex(ValueError, "exists"):
                reproduce.output_directory(root, output)

    def test_manifest_rejects_corruption_and_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            manifest = root / "MANIFEST.json"
            (root / "record.json").write_text("changed")
            manifest.write_text(json.dumps({"sha256": {"record.json": "0" * 64}}))
            with patch.object(reproduce, "HERE", root):
                with self.assertRaisesRegex(ValueError, "hash differs"):
                    reproduce.verify_files(root)
                manifest.write_text(json.dumps({"sha256": {"../outside": "0" * 64}}))
                with self.assertRaisesRegex(ValueError, "escapes"):
                    reproduce.verify_files(root)

    def test_original_sql_readonly_and_python_extraction(self):
        setup = "CREATE TABLE t(x); INSERT INTO t VALUES(1);"
        self.assertTrue(
            public_checks.fixture_grade(
                "sql", [{"setup": setup, "expected": [[1]]}], "SELECT x FROM t;"
            )[0]
        )
        self.assertFalse(
            public_checks.fixture_grade(
                "sql", [{"setup": setup, "expected": []}], "DELETE FROM t;"
            )[0]
        )
        task = {"entry_point": "f", "prompt": "def f(x):\n"}
        self.assertEqual(
            "def f(x):\n    return x",
            public_checks.candidate_source(
                task, "```python\ndef f(x):\n    return x\n```"
            ),
        )
        self.assertEqual(
            "def f(x):\n    return x",
            public_checks.candidate_source(task, "    return x"),
        )


if __name__ == "__main__":
    unittest.main()
