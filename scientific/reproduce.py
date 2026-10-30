#!/usr/bin/env python3
"""Offline evidence reconstruction/regrading; never queries or serves a model."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE / "review"))
import analyze_verifier as verifier
import analyze_precision_cost as precision
import primary_stats


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_files(root):
    manifest = load(HERE / "MANIFEST.json")
    for relative, expected in manifest["sha256"].items():
        path = (root / relative).resolve()
        require(path.is_relative_to(root), "manifest path escapes package")
        require(
            hashlib.sha256(path.read_bytes()).hexdigest() == expected,
            f"package hash differs: {relative}",
        )
    return len(manifest["sha256"])


def output_directory(root, output):
    output = output.resolve()
    evidence = root / "benchmarks"
    code = root / "scientific"
    for retained in (evidence, code):
        require(
            not output.is_relative_to(retained) and not retained.is_relative_to(output),
            "output must be separate from retained evidence and scientific code",
        )
    require(not output.exists(), "output already exists; choose a new directory")
    output.mkdir(parents=True)
    return output


def verify(root, output):
    checked = verify_files(root)
    cohort = root / "benchmarks/confirmation-run-v1"
    review = root / "benchmarks/confirmation-review-v2"
    gates, gate_manifest = verifier.analyze(cohort)
    reference_gates = load(review / "analysis-verifier.json")
    require(
        gates["models"] == reference_gates["models"], "verifier reconstruction differs"
    )
    baseline = load(cohort / "analysis.json")
    public = load(cohort / "public_manifest.json")
    private = load(cohort / "private_manifest.json")
    plan = load(cohort / "analysis_plan.json")
    for name in ("ornith", "gemma"):
        protocol = load(cohort / f"protocol-{name}.json")
        require(
            protocol["private_manifest_sha256"] == verifier.digest(private),
            "private fixtures differ",
        )
        require(
            protocol["analysis_plan_sha256"] == verifier.digest(plan),
            "analysis plan differs",
        )
    p1_reference = load(review / "analysis-p1.json")
    effects = []
    reconstructed = {}
    p1 = {}
    extracted = []
    for name in ("ornith", "gemma"):
        model = gates["models"][name]
        rows = []
        for task, row in zip(public["tasks"], model["rows"]):
            require(task["task_id"] == row["task_id"], "task order differs")
            scores = {p: int(row["selected"][p]["final_pass"]) for p in ("N", "R", "D")}
            rows.append(
                {
                    "task_id": task["task_id"],
                    "category": task["category"],
                    "template_cluster": task["public_metadata"]["template_cluster"],
                    **scores,
                }
            )
        original_rows = baseline["models"][name]["rows"]
        for row, original in zip(rows, original_rows):
            require(
                all(original[k] == v for k, v in row.items()), "paired outcome differs"
            )
        current = [
            primary_stats.paired_stats(rows, a, b, plan)
            for a, b in (("R", "N"), ("D", "R"))
        ]
        for effect in current:
            effect["model"] = name
        effects.extend(current)
        reconstructed[name] = {
            "rows": rows,
            "effects": current,
            "passed": model["selected_passed"],
        }
        protocol = load(cohort / f"protocol-{name}.json")
        costs = []
        seen = set()
        for row in rows:
            cell = load(
                cohort
                / "cells"
                / verifier.key(protocol["model_id"])
                / verifier.key(protocol["blocks"][0])
                / (verifier.key(row["task_id"]) + ".json")
            )
            cost = {
                "task_id": row["task_id"],
                "scores": {p: row[p] for p in ("N", "R", "D")},
                "costs": {},
            }
            for policy in ("N", "R", "D"):
                arm = cell["policies"][policy]
                records = [load(cohort / relative) for relative in arm["attempts"]]
                values = {"full_loop_seconds": arm["full_loop_seconds"]}
                for metric in ("prompt_tokens", "completion_tokens"):
                    tokens = [record["telemetry"].get(metric) for record in records]
                    values[metric] = (
                        sum(tokens) if all(v is not None for v in tokens) else None
                    )
                cost["costs"][policy] = values
                for relative, record in zip(arm["attempts"], records):
                    if relative not in seen:
                        seen.add(relative)
                        # Formatting-only extraction already stored in the raw record;
                        # verify association with the native/OpenAI response text.
                        response = record["response"]
                        if "output" in response:
                            answer = "\n".join(
                                item.get("content", "")
                                for item in response["output"]
                                if item.get("type") == "message"
                            )
                        else:
                            answer = (
                                response["choices"][0]["message"].get("content") or ""
                            )
                        require(
                            answer == record["answer"],
                            "recorded answer differs from raw response",
                        )
                        extracted.append(
                            {
                                "model": name,
                                "task_id": row["task_id"],
                                "artifact": relative,
                                "answer": answer,
                            }
                        )
            costs.append(cost)
        intervals = []
        for effect, (left, right) in zip(current, (("R", "N"), ("D", "R"))):
            interval = precision.simultaneous_interval(rows, left, right)
            interval.update({k: effect[k] for k in ("effect_pp", "p_exact", "ci95_pp")})
            intervals.append(interval)
        p1[name] = {
            "intervals": intervals,
            "cost_contrasts": [precision.cost_contrast(costs, p) for p in ("R", "D")],
            "task_cost_rows": costs,
        }
        for config in (review / "configuration-evidence").glob(name + "-*.json"):
            require(
                hashlib.sha256(config.read_bytes()).hexdigest()
                == protocol["model_files_sha256"]["config.json"],
                "checkpoint config hash differs",
            )
            require(
                precision.quantization_summary(load(config))
                == p1_reference["configuration"][name][
                    "quantization_checkpoint_config"
                ],
                "quantization summary differs",
            )
    primary_stats.holm(effects)
    for name in ("ornith", "gemma"):
        require(
            reconstructed[name]["effects"] == baseline["models"][name]["effects"],
            "original paired statistics differ",
        )
        for interval, effect in zip(
            p1[name]["intervals"], reconstructed[name]["effects"]
        ):
            interval["p_holm"] = effect["p_holm"]
        require(
            json.loads(json.dumps(p1[name])) == p1_reference["models"][name],
            "retrospective intervals/costs differ",
        )
    require(len(extracted) == 226, "candidate count differs")
    save(output / "candidates.json", extracted)
    save(output / "primary.json", reconstructed)
    save(output / "verifier.json", gates)
    save(output / "verifier-manifest.json", gate_manifest)
    save(output / "precision-cost.json", p1)
    with (output / "paired-outcomes.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "model",
                "task_id",
                "category",
                "template_cluster",
                "N",
                "R",
                "D",
            ),
        )
        writer.writeheader()
        for name, model in reconstructed.items():
            writer.writerows({"model": name, **row} for row in model["rows"])
    result = {
        "status": "pass",
        "package_files_checked": checked,
        "evidence_files_consumed": len(gate_manifest["input_sha256"]),
        "candidates": len(extracted),
        "task_model_cells": 144,
        "original_paired_statistics": "identical",
        "retrospective_model_statistics_costs": "identical",
        "grading": "saved grades checked against raw hashes; not executed by verify",
        "configuration": "checkpoint summaries recomputed; withheld preflight/pilot telemetry not re-audited",
        "model_calls": 0,
        "python": platform.python_version(),
    }
    save(output / "verification.json", result)
    return result


def regrade(root, output):
    cohort = root / "benchmarks/confirmation-run-v1"
    # Retain the exact root basename because the frozen analysis records it.
    target = output / "regraded/confirmation-run-v1"
    shutil.copytree(cohort, target)
    command = [
        sys.executable,
        str(HERE / "frozen/analyze_confirmation.py"),
        "--root",
        str(target),
    ]
    completed = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=1800,
    )
    (output / "regrading.log").write_text(completed.stdout)
    require(completed.returncode == 0, "regrading failed; inspect regrading.log")
    require(
        load(target / "analysis.json") == load(cohort / "analysis.json"),
        "regraded full original analysis differs",
    )
    old = {
        str(p.relative_to(cohort / "grades")): load(p)
        for p in (cohort / "grades").glob("**/*.json")
    }
    new = {
        str(p.relative_to(target / "grades")): load(p)
        for p in (target / "grades").glob("**/*.json")
    }
    require(len(new) == 226 and old == new, "regraded candidate records differ")
    result = {
        "status": "pass",
        "candidate_grades": 226,
        "full_original_analysis": "identical",
        "grade_records": "identical including final detail and raw-file hash",
        "model_calls": 0,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "limits": "offline artifact replay, not independent human review or stochastic generation replay",
    }
    save(output / "regrading.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify", "regrade"))
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="new output directory outside benchmarks/ and scientific/",
    )
    args = parser.parse_args()
    require(
        sys.flags.optimize == 0,
        "run without -O: frozen provenance checks use assertions",
    )
    root = ROOT.resolve()
    output = output_directory(root, args.output)
    result = verify(root, output)
    if args.command == "regrade":
        result = regrade(root, output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
