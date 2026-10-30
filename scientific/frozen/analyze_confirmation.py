#!/usr/bin/env python3
"""Post-collection grading and the prospectively declared analysis. No inference."""

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import random
import statistics

import collect
import final_grader
from public_checks import fixture_grade


def interval(values):
    values = sorted(values)
    return [
        values[int(0.025 * (len(values) - 1))],
        values[int(0.975 * (len(values) - 1))],
    ]


def paired_stats(rows, left, right, plan):
    differences = [r[left] - r[right] for r in rows]
    positive = sum(d > 0 for d in differences)
    negative = sum(d < 0 for d in differences)
    discordant = positive + negative
    pvalue = (
        min(
            1.0,
            2
            * sum(math.comb(discordant, k) for k in range(min(positive, negative) + 1))
            / 2**discordant,
        )
        if discordant
        else 1.0
    )
    strata = defaultdict(list)
    clusters = defaultdict(lambda: defaultdict(list))
    for row, difference in zip(rows, differences):
        strata[row["category"]].append(difference)
        clusters[row["category"]][row["template_cluster"]].append(difference)
    rng = random.Random(plan["bootstrap_seed"])
    ordinary, clustered = [], []
    for _ in range(plan["bootstrap_draws"]):
        ordinary.append(
            sum(sum(rng.choices(values, k=len(values))) for values in strata.values())
            / len(rows)
            * 100
        )
        aggregate = 0.0
        for category, groups in clusters.items():
            values = list(groups.values())
            sample = [d for group in rng.choices(values, k=len(values)) for d in group]
            aggregate += statistics.mean(sample) * len(strata[category]) / len(rows)
        clustered.append(100 * aggregate)
    return {
        "contrast": f"{left}-{right}",
        "effect_pp": 100 * statistics.mean(differences),
        "ci95_pp": interval(ordinary),
        "template_ci95_pp": interval(clustered),
        "discordant_improved": positive,
        "discordant_worsened": negative,
        "p_exact": pvalue,
    }


def holm(effects):
    ordered = sorted(effects, key=lambda item: item["p_exact"])
    previous = 0.0
    for rank, item in enumerate(ordered):
        previous = max(previous, min(1.0, (len(ordered) - rank) * item["p_exact"]))
        item["p_holm"] = previous


def analyze(root):
    public = collect.load_json(root / "public_manifest.json")
    private = collect.load_json(root / "private_manifest.json")
    plan = collect.load_json(root / "analysis_plan.json")
    private_tasks = {t["id"]: t for t in private["tasks"]}
    protocols = {
        name: collect.load_json(root / f"protocol-{name}.json")
        for name in ("ornith", "gemma")
    }
    for protocol in protocols.values():
        collect.validate_protocol(protocol, public)
        assert protocol["private_manifest_sha256"] == collect.sha256(private)
        assert protocol["analysis_plan_sha256"] == collect.sha256(plan)
        completion = collect.load_json(
            root / ("complete-" + protocol["model_id"] + ".json")
        )
        assert completion["protocol_sha256"] == collect.sha256(protocol)
    result = {
        "root": root.name,
        "scope": "72-task one-block two-model confirmation",
        "analysis_plan": plan,
        "models": {},
    }
    effects = []
    for name, protocol in protocols.items():
        cache = {}

        def grade_record(relative):
            path = root / relative
            if relative not in cache:
                record = collect.load_json(path)
                task_id = record["association"]["task_id"]
                if task_id.startswith("HumanEval/"):
                    grade = final_grader.grade(task_id, record["answer"])
                else:
                    task = private_tasks[task_id]
                    passed, detail = fixture_grade(
                        task["type"], task["final"], record["answer"]
                    )
                    grade = {"passed": passed, "detail": detail}
                if record["telemetry"].get("finish_reason") == "http_error":
                    grade["passed"] = False
                cache[relative] = {"record": record, "grade": grade}
                key = collect.sha256(relative.encode())
                collect.atomic_json(
                    root / "grades" / name / (key + ".json"),
                    {
                        "artifact": relative,
                        "artifact_sha256": collect.sha256(path.read_bytes()),
                        "final_grade": grade,
                    },
                )
            return cache[relative]

        rows = []
        policy_costs = {policy: [] for policy in collect.POLICIES}
        for task in public["tasks"]:
            path = (
                root
                / "cells"
                / collect.artifact_key(protocol["model_id"])
                / collect.artifact_key("block-1")
                / (collect.artifact_key(task["task_id"]) + ".json")
            )
            cell = collect.load_json(path)
            row = {
                "task_id": task["task_id"],
                "category": task["category"],
                "template_cluster": task["public_metadata"]["template_cluster"],
            }
            for policy in collect.POLICIES:
                selection = cell["policies"][policy]
                candidates = [
                    grade_record(relative) for relative in selection["attempts"]
                ]
                row[policy] = int(candidates[selection["selected"]]["grade"]["passed"])
                row[policy + "_available"] = int(
                    any(c["grade"]["passed"] for c in candidates)
                )
                cost = {"full_loop_seconds": selection["full_loop_seconds"]}
                for field in ("prompt_tokens", "completion_tokens", "reasoning_tokens"):
                    values = [c["record"]["telemetry"].get(field) for c in candidates]
                    cost[field] = (
                        sum(values) if all(v is not None for v in values) else None
                    )
                cost["verification_seconds"] = sum(
                    c["record"]["public_grade"]["seconds"] for c in candidates
                )
                policy_costs[policy].append(cost)
            rows.append(row)
        model_effects = [
            paired_stats(rows, "R", "N", plan),
            paired_stats(rows, "D", "R", plan),
        ]
        for effect in model_effects:
            effect["model"] = name
        effects.extend(model_effects)
        false_accept = sum(
            c["record"]["public_grade"]["passed"] and not c["grade"]["passed"]
            for c in cache.values()
        )
        false_reject = sum(
            not c["record"]["public_grade"]["passed"] and c["grade"]["passed"]
            for c in cache.values()
        )
        result["models"][name] = {
            "tasks": len(rows),
            "rows": rows,
            "passed": {p: sum(r[p] for r in rows) for p in collect.POLICIES},
            "available": {
                p: sum(r[p + "_available"] for r in rows) for p in collect.POLICIES
            },
            "category": {
                cat: {
                    p: sum(r[p] for r in rows if r["category"] == cat)
                    for p in collect.POLICIES
                }
                for cat in ("python", "sql", "shell")
            },
            "effects": model_effects,
            "recorded_requests": len(cache),
            "false_accepts": false_accept,
            "false_rejects": false_reject,
            "policy_cost_mean": {
                p: {
                    field: (
                        statistics.mean(c[field] for c in costs)
                        if all(c[field] is not None for c in costs)
                        else None
                    )
                    for field in costs[0]
                }
                for p, costs in policy_costs.items()
            },
            "truncations": sum(
                c["record"]["telemetry"].get("finish_reason") == "length"
                or (c["record"]["telemetry"].get("completion_tokens") or -1) >= 1024
                for c in cache.values()
            ),
            "http_errors": sum(
                c["record"]["telemetry"].get("finish_reason") == "http_error"
                for c in cache.values()
            ),
        }
    holm(effects)
    collect.atomic_json(root / "analysis.json", result)
    print(
        json.dumps(
            {
                name: {"passed": v["passed"], "effects": v["effects"]}
                for name, v in result["models"].items()
            },
            indent=2,
        )
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    analyze(args.root.resolve())
