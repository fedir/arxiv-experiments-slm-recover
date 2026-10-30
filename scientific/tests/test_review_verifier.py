"""Post-review ceiling and provenance controls; no model calls or new grades."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "review"))
import analyze_verifier as review


def candidate(public, final):
    return {
        "public_pass": public,
        "final_pass": final,
        "category": "python",
        "coverage": "python_no_examples",
    }


def row(first, redraw=None, repair=None):
    return {
        "first": first,
        "selected": {"N": first, "R": redraw or first, "D": repair or first},
    }


class ReviewVerifierControls(unittest.TestCase):
    def test_ceiling_does_not_double_count_initial_false_rejections(self):
        correct = candidate(True, True)
        blocked = candidate(True, False)
        falsely_rejected = candidate(False, True)
        rows = [
            row(correct),
            row(blocked),
            row(falsely_rejected, candidate(False, False), candidate(True, True)),
        ]
        result = review.summarize(rows, [correct, blocked, falsely_rejected])
        self.assertEqual(2, result["ceiling"]["max_successes"])
        self.assertEqual(1, result["initial"]["rejected_correct"])
        self.assertEqual(1, result["conditional_recovery"]["R"]["regressions"])
        self.assertEqual(1, result["conditional_recovery"]["D"]["selected_final_pass"])
        self.assertEqual(0, result["conditional_recovery"]["D"]["repairs"])

    def test_empty_denominators_are_unknown_not_zero(self):
        correct = candidate(True, True)
        result = review.summarize([row(correct)], [correct])
        self.assertIsNone(result["initial"]["false_reject_rate"])
        self.assertIsNone(
            result["conditional_recovery"]["R"]["conditional_success_rate"]
        )
        self.assertIsNone(result["initial_strata"]["sql"]["false_accept_rate"])

    def test_python_coverage_strata_partition_python_not_all_tasks(self):
        zero = candidate(True, False)
        examples = {**candidate(False, False), "coverage": "python_examples"}
        sql = {**candidate(True, True), "category": "sql", "coverage": None}
        strata = review.stratify([zero, examples, sql])
        self.assertEqual(3, strata["all"]["total"])
        self.assertEqual(2, strata["python"]["total"])
        self.assertEqual(1, strata["python_no_examples"]["accepted_incorrect"])
        self.assertEqual(1, strata["python_examples"]["rejected_incorrect"])

    def test_grade_hash_and_uncertain_dispatch_are_rejected(self):
        task = {"task_id": "test", "category": "sql"}
        protocol = {"model_id": "model"}
        association = {
            "task_id": "test",
            "task_sha256": review.digest(task),
            "model_id": "model",
            "block": "one",
            "policy": "first",
            "attempt": 0,
            "protocol_sha256": review.digest(protocol),
        }
        record = {"association": association, "public_grade": {"passed": False}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = json.dumps(record).encode()
            (root / "record.json").write_bytes(raw)
            state = {"association": association, "status": "in_flight"}
            (root / "record.state.json").write_text(json.dumps(state))
            grade = {
                "artifact": "record.json",
                "artifact_sha256": review.digest(raw),
                "final_grade": {"passed": False},
            }
            evidence = review.Evidence(root)
            with self.assertRaisesRegex(ValueError, "dispatch"):
                evidence.candidate(
                    "record.json", grade, task, protocol, "one", "first", 0
                )
            bad = copy.deepcopy(grade)
            bad["artifact_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "grade hash"):
                evidence.candidate(
                    "record.json", bad, task, protocol, "one", "first", 0
                )
            with self.assertRaisesRegex(ValueError, "escapes"):
                evidence.read("../outside.json")

    def test_frozen_cohort_reconstruction(self):
        result, manifest = review.analyze()
        self.assertEqual(0, manifest["model_calls"])
        for name, ceiling, eligible, redraw, repair in (
            ("ornith", 55, 18, 6, 1),
            ("gemma", 63, 23, 5, 6),
        ):
            with self.subTest(model=name):
                model = result["models"][name]
                self.assertEqual(72, model["initial"]["total"])
                self.assertEqual(ceiling, model["ceiling"]["max_successes"])
                for policy, passed in (("R", redraw), ("D", repair)):
                    observed = model["conditional_recovery"][policy]
                    self.assertEqual(eligible, observed["eligible"])
                    self.assertEqual(passed, observed["selected_final_pass"])
                    self.assertEqual(0, observed["missing_outcomes"])
                    self.assertEqual(
                        eligible,
                        passed
                        + observed["still_publicly_rejected"]
                        + observed["false_accepts_after_retry"],
                    )


if __name__ == "__main__":
    unittest.main()
