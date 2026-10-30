# Offline scientific reproduction

These commands reproduce the retained experiment, without model inference or
weights. Run from the repository root using Python 3.12, without `-O`.

## 1. Evidence and statistical reconstruction (standard library only)

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scientific/reproduce.py verify --output /tmp/slm-verify
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scientific/tests
```

Choose a **new** output directory for each run. The entry point refuses existing
outputs and directories overlapping `benchmarks/` or `scientific/`. It verifies
package SHA-256 identities and raw-record/grade associations, reconstructs all
144 task/model selections and 226 raw candidate texts, and compares original
bootstrap intervals, exact/Holm tests, retrospective verifier partitions/ceilings,
simultaneous bounds and recorded cost summaries against the saved results.
It also recomputes the hash-matched checkpoint quantization summaries.

Outputs include `candidates.json`, `paired-outcomes.csv`, `primary.json`,
`verifier.json`, `verifier-manifest.json`, `precision-cost.json` and a check report.
Verification uses saved grades; it does not execute candidate programs.

## 2. Candidate regrading

Prerequisites: macOS with `sandbox-exec`, or Linux with working bubblewrap (`bwrap`),
`/bin/bash`, standard command-line utilities and Python's SQLite. Linux portability
is implemented by the original verifier but has not been validated in this release.
The recorded evaluation used macOS; environment/tool differences can affect shell
results and failure diagnostic strings. EvalPlus execution guards are retained;
this is bounded execution, not a formally verified isolation kernel.

Create an evaluator environment and obtain the pinned upstream dataset once:

```sh
python3.12 -m venv /tmp/slm-evaluator
/tmp/slm-evaluator/bin/python -m pip install -r scientific/requirements-lock.txt
SSL_CERT_FILE="$(/tmp/slm-evaluator/bin/python -m certifi)" /tmp/slm-evaluator/bin/python -c 'from evalplus.data import get_human_eval_plus; get_human_eval_plus()'
```

Dependency installation and first dataset acquisition require network access.
The preparation command uses the installed certifi CA bundle, including on Python
installations without a configured default certificate store; TLS checks remain enabled.
The dataset is HumanEvalPlus v0.1.10, obtained by EvalPlus 0.3.1 from:
https://github.com/evalplus/humanevalplus_release/releases/download/v0.1.10/HumanEvalPlus.jsonl.gz

The unchanged final grader checks the uncompressed JSONL SHA-256:
`42526ec0e7d5f3ee0b06d6ced98f8c8bae3d76519151bfb3d36f79010645bd7f`,
all 40 selected task identities, entry points and prompt hashes. Do not use
`HUMANEVAL_OVERRIDE_PATH`: the original grader checks EvalPlus's normal cache path.
EvalPlus may compute official expected outputs for the full upstream dataset on
a cold cache. Those reference implementations are used only by final grading,
never to construct or select model answers.

Then replay offline:

```sh
PYTHONDONTWRITEBYTECODE=1 /tmp/slm-evaluator/bin/python scientific/reproduce.py regrade --output /tmp/slm-regrade
```

This first runs verification, then copies evidence to the output directory and
executes the frozen final grader and full original analysis there. It requires
all 226 regenerated grade records (including raw hashes and diagnostic details)
and the full original `analysis.json` to match. Failure leaves `regrading.log` and
copied outputs for inspection; no reference grade is overwritten.

`requirements-lock.txt` records the fresh macOS/Python 3.12 validation environment,
not collection-time dependencies or a universally portable lock. EvalPlus brings
optional model-client packages as transitive dependencies; these commands do not
use them or require API credentials. `requirements.txt` states the evaluator pin.

## Provenance and limits

`PROVENANCE.json` distinguishes byte-identical frozen modules, exact function
excerpts and portability adaptations. Final grading, formatting/SQL helpers and
all original numerical functions are unchanged. The offline `collect.py` utility
subset replaces a check of withheld collector/orchestrator source files with
their retained identities; `MANIFEST.json` separately checks exported file bytes.
Only the unused author-local dataset path is removed from the benchmark manifest.
The retrospective verifier's location/default path changes its new manifest hash;
its complete model-level output must equal the original. Original manifests remain
unchanged and are not represented as newly recreated identities.

The original collector, model serving, private preflight/pilot logs, historical
experiments, article builders, TeX/PDF sources and weights are excluded. Raw request
records retain prompts, settings and responses. Public offline replay does not
reconstruct withheld hardware/preflight evidence or regenerate identical stochastic
responses. One sampling block and unknown effective seed/cache settings remain
limitations. This author-performed replay is not independent human review.

Author code here is MIT (`LICENSE`); author data remain CC BY 4.0 at repository
root. Third-party material retains its terms (`../THIRD_PARTY_NOTICES.md`).
