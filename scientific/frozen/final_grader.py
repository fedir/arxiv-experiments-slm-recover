#!/usr/bin/env python3
"""Final-only HumanEval+ grading boundary.

This module is intentionally not imported by ``collect.py``. Candidates are
completion text appended to the pinned public prompt; no result from this
adapter may be used for collection, selection, diagnostics, or routing.
"""

import hashlib
import json
import os
import platform
import sys
from functools import lru_cache
from pathlib import Path

from evalplus import __version__ as EVALPLUS_VERSION
from evalplus.data.humaneval import HUMANEVAL_PLUS_VERSION, get_human_eval_plus
from evalplus.data.utils import get_dataset_metadata
from evalplus.evaluate import check_correctness, get_groundtruth


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from public_checks import candidate_source

MANIFEST = ROOT / "humaneval_manifest.json"
EVALPLUS_PIN = "0.3.1"

# EvalPlus 0.3.1's default 4 GiB address-space cap cannot be installed by its
# macOS worker when the inherited hard limit is lower.  -1 is EvalPlus's own
# documented no-cap value; its execution guards remain enabled.
if platform.system() == "Darwin":
    os.environ.setdefault("EVALPLUS_MAX_MEMORY_BYTES", "-1")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_verified_tasks() -> tuple[dict, dict]:
    """Return selected source tasks only after checking every pinned identity."""
    if EVALPLUS_VERSION != EVALPLUS_PIN:
        raise RuntimeError(
            f"expected evalplus {EVALPLUS_PIN}, found {EVALPLUS_VERSION}"
        )
    manifest = _manifest()
    source = manifest.get("source", {})
    if source.get("evaluator_version") != EVALPLUS_PIN:
        raise RuntimeError("manifest does not pin evalplus 0.3.1")
    if (
        source.get("dataset") != "HumanEvalPlus"
        or source.get("dataset_version") != HUMANEVAL_PLUS_VERSION
    ):
        raise RuntimeError("manifest dataset identity does not match EvalPlus")
    _, source_path = get_dataset_metadata(
        "HumanEvalPlus", HUMANEVAL_PLUS_VERSION, mini=False
    )
    if sha256_bytes(Path(source_path).read_bytes()) != source.get("source_sha256"):
        raise RuntimeError("installed HumanEval+ source hash does not match manifest")
    all_tasks = get_human_eval_plus()
    selected = {}
    for pinned in manifest.get("tasks", []):
        task_id = pinned.get("task_id")
        task = all_tasks.get(task_id)
        if task is None:
            raise RuntimeError(f"pinned task missing from source: {task_id}")
        if task["entry_point"] != pinned.get("entry_point"):
            raise RuntimeError(f"entry point mismatch for {task_id}")
        if sha256_bytes(task["prompt"].encode()) != pinned.get("prompt_sha256"):
            raise RuntimeError(f"prompt mismatch for {task_id}")
        selected[task_id] = task
    if len(selected) != 40:
        raise RuntimeError("manifest must contain exactly 40 unique HumanEval+ tasks")
    return manifest, selected


def grade(task_id: str, completion: str) -> dict:
    """Grade one completion on base and HumanEval+ tests using EvalPlus semantics."""
    if not isinstance(completion, str):
        raise TypeError("completion must be a string")
    _, tasks = load_verified_tasks()
    if task_id not in tasks:
        raise ValueError(
            f"task is not in the pinned 40-task confirmation subset: {task_id}"
        )
    task = tasks[task_id]
    # EvalPlus computes expected outputs from the official canonical solution,
    # then executes this supplied completion in its isolated checker.
    expected = expected_outputs()
    result = check_correctness(
        "humaneval",
        0,
        task,
        candidate_source(task, completion),
        expected[task_id],
        base_only=False,
        fast_check=True,
        identifier=task_id,
    )
    return {
        "task_id": task_id,
        "base_status": result["base"][0],
        "plus_status": result["plus"][0],
        "passed": result["base"][0] == "pass" and result["plus"][0] == "pass",
    }


@lru_cache(maxsize=1)
def expected_outputs() -> dict:
    """Use EvalPlus's task hash for its cached official expected outputs."""
    from evalplus.data.humaneval import get_human_eval_plus_hash

    # EvalPlus's cache key represents the full source, so its corresponding
    # full task mapping must be used. A cold cache therefore computes official
    # outputs for all HumanEval+ tasks before grading the requested candidate.
    return get_groundtruth(get_human_eval_plus(), get_human_eval_plus_hash(), [])
