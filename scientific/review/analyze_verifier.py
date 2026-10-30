#!/usr/bin/env python3
"""Read-only reconstruction of verifier gates from original candidate evidence."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1] / "benchmarks/confirmation-run-v1"
GROUPS = ("all", "python", "sql", "shell", "python_no_examples", "python_examples")


def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(value).hexdigest()


def key(value):
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def coverage(task):
    if task["category"] != "python":
        return None
    count = task["public_metadata"]["public_example_count"]
    if not isinstance(count, int) or count < 0:
        raise ValueError("invalid frozen example count")
    return "python_examples" if count else "python_no_examples"


def partition(candidates):
    counts = Counter(
        ("accepted_" if candidate["public_pass"] else "rejected_")
        + ("correct" if candidate["final_pass"] else "incorrect")
        for candidate in candidates
    )
    result = {
        name: counts[name]
        for name in (
            "accepted_correct",
            "accepted_incorrect",
            "rejected_correct",
            "rejected_incorrect",
        )
    }
    result.update(
        total=len(candidates),
        accepted=counts["accepted_correct"] + counts["accepted_incorrect"],
        rejected=counts["rejected_correct"] + counts["rejected_incorrect"],
    )
    result["false_accept_rate"] = ratio(
        result["accepted_incorrect"], result["accepted"]
    )
    result["false_reject_rate"] = ratio(result["rejected_correct"], result["rejected"])
    return result


def stratify(candidates):
    return {
        group: partition(
            [
                candidate
                for candidate in candidates
                if group == "all"
                or candidate["category"] == group
                or candidate.get("coverage") == group
            ]
        )
        for group in GROUPS
    }


def summarize(rows, candidates):
    firsts = [row["first"] for row in rows]
    initial = partition(firsts)
    rejected = [row for row in rows if not row["first"]["public_pass"]]
    ceiling = initial["accepted_correct"] + initial["rejected"]
    assert ceiling == len(rows) - initial["accepted_incorrect"]
    recovery = {}
    for policy in ("R", "D"):
        selected = [row["selected"][policy] for row in rejected]
        passing = sum(candidate["final_pass"] for candidate in selected)
        recovery[policy] = {
            "eligible": len(rejected),
            "attempted": len(selected),
            "selected_final_pass": passing,
            "selected_final_fail": len(selected) - passing,
            "conditional_success_rate": ratio(passing, len(rejected)),
            "repairs": sum(
                not row["first"]["final_pass"] and row["selected"][policy]["final_pass"]
                for row in rejected
            ),
            "regressions": sum(
                row["first"]["final_pass"] and not row["selected"][policy]["final_pass"]
                for row in rejected
            ),
            "still_publicly_rejected": sum(
                not candidate["public_pass"] for candidate in selected
            ),
            "false_accepts_after_retry": sum(
                candidate["public_pass"] and not candidate["final_pass"]
                for candidate in selected
            ),
            "missing_outcomes": 0,
            "in_flight_dispatches": 0,
        }
        assert (
            sum(row["selected"][policy]["final_pass"] for row in rows)
            == initial["accepted_correct"] + passing
        )
    return {
        "initial": initial,
        "ceiling": {
            "max_successes": ceiling,
            "tasks": len(rows),
            "rate": ratio(ceiling, len(rows)),
            "blocked_initial_failures": initial["accepted_incorrect"],
        },
        "conditional_recovery": recovery,
        "initial_strata": stratify(firsts),
        "all_candidate_strata": stratify(candidates),
        "selected_passed": {
            p: sum(row["selected"][p]["final_pass"] for row in rows)
            for p in ("N", "R", "D")
        },
        "rows": rows,
    }


class Evidence:
    def __init__(self, source):
        self.source = source.resolve()
        self.inputs = {}

    def read(self, relative):
        path = (self.source / relative).resolve()
        if not path.is_relative_to(self.source):
            raise ValueError("evidence path escapes source root")
        raw = path.read_bytes()
        self.inputs[str(path.relative_to(self.source))] = digest(raw)
        return json.loads(raw)

    def candidate(self, relative, grade, task, protocol, block, policy, attempt):
        record = self.read(relative)
        if (
            grade["artifact"] != relative
            or grade["artifact_sha256"] != self.inputs[relative]
        ):
            raise ValueError("candidate grade hash/association mismatch")
        expected = {
            "task_id": task["task_id"],
            "task_sha256": digest(task),
            "model_id": protocol["model_id"],
            "block": block,
            "policy": policy,
            "attempt": attempt,
            "protocol_sha256": digest(protocol),
        }
        if any(record["association"].get(k) != v for k, v in expected.items()):
            raise ValueError("candidate task/model/protocol association mismatch")
        state = self.read(relative.replace(".json", ".state.json"))
        if (
            state["status"] != "recorded"
            or state["association"] != record["association"]
        ):
            raise ValueError("unresolved or mismatched dispatch state")
        public = record["public_grade"]["passed"]
        final = grade["final_grade"]["passed"]
        if type(public) is not bool or type(final) is not bool:
            raise ValueError("candidate verdict is not boolean")
        return {
            "artifact": relative,
            "artifact_sha256": self.inputs[relative],
            "task_id": task["task_id"],
            "category": task["category"],
            "coverage": coverage(task),
            "public_pass": public,
            "final_pass": final,
        }


def analyze(source=SOURCE):
    evidence = Evidence(source)
    public = evidence.read("public_manifest.json")
    baseline = evidence.read("analysis.json")
    output = {
        "schema_version": 1,
        "scope": "post-review descriptive verifier analysis; no new inference",
        "source_cohort": source.name,
        "models": {},
    }
    for model in ("ornith", "gemma"):
        protocol = evidence.read(f"protocol-{model}.json")
        assert protocol["public_manifest_sha256"] == digest(public)
        assert len(protocol["blocks"]) == 1
        block = protocol["blocks"][0]
        completed = evidence.read(f"complete-{protocol['model_id']}.json")
        assert completed["protocol_sha256"] == digest(protocol)
        grade_index = {}
        for path in sorted((source / "grades" / model).glob("*.json")):
            grade = evidence.read(str(path.relative_to(source)))
            if grade["artifact"] in grade_index:
                raise ValueError("duplicate candidate grade")
            grade_index[grade["artifact"]] = grade
        rows, unique = [], {}
        for task in public["tasks"]:
            task_id = task["task_id"]
            cell_path = (
                f"cells/{key(protocol['model_id'])}/{key(block)}/{key(task_id)}.json"
            )
            cell = evidence.read(cell_path)
            expected = {
                "task_id": task_id,
                "task_sha256": digest(task),
                "model_id": protocol["model_id"],
                "block": block,
                "policy": "cell",
                "protocol_sha256": digest(protocol),
            }
            assert all(cell["association"][k] == v for k, v in expected.items())
            first_paths = [cell["policies"][p]["attempts"][0] for p in ("N", "R", "D")]
            assert len(set(first_paths)) == 1
            first_path = first_paths[0]
            first = evidence.candidate(
                first_path, grade_index[first_path], task, protocol, block, "first", 0
            )
            unique[first_path] = first
            selections = {}
            for policy in ("N", "R", "D"):
                arm = cell["policies"][policy]
                expected_attempts = 1 if policy == "N" or first["public_pass"] else 2
                assert len(arm["attempts"]) == expected_attempts
                assert arm["selected"] == expected_attempts - 1
                if expected_attempts == 1:
                    selected = first
                else:
                    relative = arm["attempts"][1]
                    assert relative != first_path and relative not in unique
                    selected = evidence.candidate(
                        relative,
                        grade_index[relative],
                        task,
                        protocol,
                        block,
                        policy,
                        1,
                    )
                    unique[relative] = selected
                selections[policy] = selected
            rows.append({"task_id": task_id, "first": first, "selected": selections})
        assert len(rows) == 72 and len({row["task_id"] for row in rows}) == 72
        recorded = {
            str(p.relative_to(source))
            for p in (source / "artifacts" / key(protocol["model_id"])).glob(
                "**/*.json"
            )
            if not p.name.endswith(".state.json")
        }
        assert recorded == set(unique) == set(grade_index)
        counts = summarize(rows, list(unique.values()))
        original = baseline["models"][model]
        assert counts["selected_passed"] == original["passed"]
        assert len(unique) == original["recorded_requests"]
        assert (
            counts["all_candidate_strata"]["all"]["accepted_incorrect"]
            == original["false_accepts"]
        )
        assert (
            counts["all_candidate_strata"]["all"]["rejected_correct"]
            == original["false_rejects"]
        )
        for scope in ("initial_strata", "all_candidate_strata"):
            strata = counts[scope]
            for field in (
                "total",
                "accepted",
                "rejected",
                "accepted_correct",
                "accepted_incorrect",
                "rejected_correct",
                "rejected_incorrect",
            ):
                assert (
                    sum(strata[c][field] for c in ("python", "sql", "shell"))
                    == strata["all"][field]
                )
                assert (
                    sum(
                        strata[c][field]
                        for c in ("python_no_examples", "python_examples")
                    )
                    == strata["python"][field]
                )
        output["models"][model] = counts
    manifest = {
        "schema_version": 1,
        "declared_date": "2026-10-26",
        "status": "post-review; original outcomes already known",
        "source_cohort": source.name,
        "input_sha256": evidence.inputs,
        "analysis_code_sha256": digest(Path(__file__).read_bytes()),
        "plan_sha256": digest((HERE / "PLAN.md").read_bytes()),
        "model_calls": 0,
        "grading": "reuse original grades with raw-file hashes; no new grades or online feedback",
    }
    manifest["result_sha256"] = digest(output)
    output["manifest_sha256"] = digest(manifest)
    return output, manifest
