"""Offline-only frozen collector utilities; no dispatch or serving code."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
HERE = Path(__file__).resolve().parent
SCHEMA_VERSION = 1
POLICIES = ("N", "R", "D")

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def sha256(value):
    if not isinstance(value, bytes):
        value = canonical(value).encode()
    return hashlib.sha256(value).hexdigest()


def artifact_key(value):
    """Return a case-safe key; the original identifier remains in the artifact."""
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=path.name + ".", delete=False
    ) as output:
        json.dump(value, output, indent=2)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
        temporary = Path(output.name)
    temporary.replace(path)


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_manifest(manifest):
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported public manifest schema")
    if manifest.get("visibility") != "public":
        raise ValueError("collector requires a visibility=public manifest")
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("public manifest requires at least one task")
    ids = set()
    for task in tasks:
        if set(task) - {
            "task_id",
            "prompt",
            "entry_point",
            "prompt_sha256",
            "category",
            "public_metadata",
        }:
            raise ValueError("public manifest task has non-public or unknown fields")
        if not isinstance(task.get("task_id"), str) or not task["task_id"]:
            raise ValueError("task_id must be a non-empty string")
        if not isinstance(task.get("prompt"), str):
            raise ValueError("task prompt must be a string")
        if task["task_id"] in ids:
            raise ValueError("duplicate task_id in public manifest")
        ids.add(task["task_id"])


def validate_protocol(protocol, manifest):
    if protocol.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported protocol schema")
    if protocol.get("frozen") is not True or not protocol.get("frozen_at"):
        raise ValueError("collection requires a timestamped frozen protocol")
    if protocol.get("public_manifest_sha256") != sha256(manifest):
        raise ValueError("protocol does not freeze this public manifest")
    if protocol.get("policies") != list(POLICIES):
        raise ValueError("protocol policies must be exactly N/R/D")
    if not isinstance(protocol.get("model_id"), str) or not protocol["model_id"]:
        raise ValueError("protocol requires model_id")
    if not isinstance(protocol.get("endpoint"), str) or not protocol["endpoint"]:
        raise ValueError("protocol requires a frozen endpoint")
    if not isinstance(protocol.get("request_parameters"), dict):
        raise ValueError("protocol requires frozen request_parameters")
    if not isinstance(protocol.get("blocks"), list) or not protocol["blocks"]:
        raise ValueError("protocol requires at least one sampling block")
    if len(set(protocol["blocks"])) != len(protocol["blocks"]):
        raise ValueError("protocol blocks must be unique")
    if not isinstance(protocol.get("system_prompt"), str):
        raise ValueError("protocol requires system_prompt")
    cap = protocol["request_parameters"].get("max_tokens")
    if not isinstance(cap, int) or cap <= 0:
        raise ValueError("positive max_tokens cap required")
    # The inference/orchestration sources are intentionally not exported.
    # Check their retained identities; the entry point separately checks exported bytes.
    expected = load_json(HERE / "source-identities.json")
    if protocol.get("source_sha256") != expected:
        raise ValueError("protocol frozen source identities differ")
