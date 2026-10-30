"""Public-fixture verification and formatting-only extraction. No private imports."""

import ast
import doctest
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run as base


def candidate_source(task, answer):
    blocks = base.code_blocks(answer)
    code = blocks[0] if blocks else answer
    try:
        tree = ast.parse(code)
        if any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == task["entry_point"]
            for node in tree.body
        ):
            return code
    except SyntaxError:
        pass
    # Preserve body completions exactly, including indentation. Never fill code.
    return task["prompt"] + code


def execute(files, command, *, stdin=None, timeout=5):
    """Bounded, isolated process with exact stdout/exit status; kill descendants."""
    with tempfile.TemporaryDirectory() as directory:
        for name, content in files.items():
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise ValueError("fixture path escapes sandbox")
            path = Path(directory) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        real = str(Path(directory).resolve())
        if sys.platform == "darwin" and shutil.which("sandbox-exec"):
            profile = (
                "(version 1) (deny default) (allow process*) (allow sysctl-read) "
                '(allow file-read*) (deny file-read* (subpath "/Users")) '
                f'(allow file-read* (subpath "{directory}")) '
                f'(allow file-read* (subpath "{real}")) '
                f'(allow file-write* (subpath "{directory}")) '
                f'(allow file-write* (subpath "{real}"))'
            )
            command = ["sandbox-exec", "-p", profile, *command]
        elif shutil.which("bwrap"):
            command = [
                "bwrap",
                "--unshare-all",
                "--ro-bind",
                "/",
                "/",
                "--tmpfs",
                "/home",
                "--tmpfs",
                "/Users",
                "--tmpfs",
                "/tmp",
                "--dev",
                "/dev",
                "--proc",
                "/proc",
                "--bind",
                directory,
                "/work",
                "--chdir",
                "/work",
                *command,
            ]
        else:
            raise RuntimeError("execution requires sandbox-exec or bubblewrap")
        process = subprocess.Popen(
            command,
            cwd=directory,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "HOME": directory},
        )
        try:
            stdout, stderr = process.communicate(stdin, timeout=timeout)
            return process.returncode, stdout, stderr
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            return None, b"", b"execution timed out"


def fixture_grade(kind, fixtures, answer):
    for fixture in fixtures:
        if kind == "sql":
            ok, detail = base.sql_check(
                fixture["setup"],
                fixture["expected"],
                fixture.get("ordered", True),
                answer,
            )
        else:
            blocks = base.code_blocks(answer)
            command = (blocks[0] if blocks else answer).strip()
            status, stdout, stderr = execute(
                fixture["files"], ["/bin/bash", "-c", command]
            )
            expected = fixture["expected"].encode()
            ok = status == 0 and stdout == expected
            detail = (
                "exact output and exit status match"
                if ok
                else f"exit={status}, stdout={stdout[:500]!r}, expected={expected[:500]!r}, stderr={stderr[:200]!r}"
            )
        if not ok:
            return False, detail
    return True, "all public fixtures match"


WORKER = r"""
import ast, doctest, json, sys
data = json.load(sys.stdin)
namespace = {"__name__": "candidate"}
exec(compile(data["source"], "candidate.py", "exec"), namespace)
if not callable(namespace.get(data["entry_point"])):
    raise AssertionError("missing callable entry point")
class LiteralChecker(doctest.OutputChecker):
    def check_output(self, want, got, flags):
        try:
            return ast.literal_eval(want.strip()) == ast.literal_eval(got.strip())
        except (ValueError, SyntaxError):
            return super().check_output(want, got, flags)
runner = doctest.DocTestRunner(verbose=False, checker=LiteralChecker())
test = doctest.DocTestParser().get_doctest(data["prompt"], namespace, "public", "prompt", 0)
for example in test.examples:
    tree = ast.parse(example.source)
    if not example.want.strip() and len(tree.body) == 1 and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Compare):
        example.want = "True\n"
result = runner.run(test)
if result.failed:
    raise AssertionError("public prompt examples failed")
"""


def prompt_examples(task):
    tree = ast.parse(task["prompt"])
    for node in tree.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == task["entry_point"]
        ):
            return ast.get_docstring(node) or ""
    return ""


def grade(task, answer):
    if task.get("category") in ("sql", "shell"):
        return fixture_grade(
            task["category"], task["public_metadata"]["fixtures"], answer
        )
    source = candidate_source(task, answer)
    try:
        compile(source, "candidate.py", "exec")
    except (SyntaxError, ValueError) as error:
        return False, f"invalid Python: {error}"
    payload = json.dumps(
        {
            "source": source,
            "entry_point": task["entry_point"],
            "prompt": prompt_examples(task),
        }
    ).encode()
    status, stdout, stderr = execute(
        {}, [str(Path(sys.executable).resolve()), "-I", "-c", WORKER], stdin=payload
    )
    examples = len(doctest.DocTestParser().get_examples(prompt_examples(task)))
    return (
        status == 0,
        f"{examples} public prompt examples; exit={status}; "
        + (stdout + stderr).decode(errors="replace")[-1500:],
    )
