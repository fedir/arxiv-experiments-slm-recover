# Verification-Gated Redraw and Repair for Local Small Language Models: A Paired Evaluation

Research data accompanying this article, by Fedir Rykhtik, October 2026.

This is a **data-only release**, not the original execution pipeline. It contains
the completed Ornith 1.5 9B / Gemma 4 E4B study: 72 tasks per model (40 HumanEval+,
16 SQL, 16 shell), one sampling block, 144 task/model cells and 226 recorded calls.
Historical experiments, pilot responses, author harness scripts, manuscript files,
model weights and unrelated private material are excluded.

## Layout

```text
benchmarks/
  confirmation-run-v1/
    artifacts/              raw requests/responses, public grades, dispatch states
    cells/                  paired policy attempt lists and selected indices
    grades/                 saved final grades linked to raw-file SHA-256 hashes
    public_manifest.json    prompts, public examples, task IDs and metadata
    private_manifest.json   held-out SQL/shell fixtures and validation controls
    protocol-*.json         frozen settings, budgets and source/checkpoint hashes
    analysis_plan.json      original statistical analysis plan
    analysis.json           task-level outcomes, statistics and recorded costs
    complete-*.json         collection completion records
    integrity-audit.json    author integrity-check result
    reproduction-check.json author replay result and its stated limits
  confirmation-review-v2/
    PLAN.md, PLAN_P1.md     explicitly post-review analysis definitions
    analysis-verifier.json  initial verifier partitions, ceilings and trace rows
    analysis-p1.json        sparse-data sensitivity, costs and configuration
    manifests*/            content-addressed input/code/result provenance
    configuration-evidence/ small checkpoint configs matching pre-run hashes
```

Here **private** means held out from the recovery policy during collection, not
personal data. These fixtures were used only for final grading/assurance. Public
release does not make this a new untouched evaluation cohort.

## Reading the data

- **N:** select the first answer. **R:** after public rejection, take one fresh
  sample. **D:** after public rejection, request one diagnostic repair. First
  answers are shared; a saved first response must not be counted three times.
- `cells/*/*/*.json` contains policy `attempts` paths and a zero-based `selected`
  index. Follow those paths under the same `confirmation-run-v1` directory.
- Each attempt stores the raw API request/response, extracted `answer`, public
  decision, provenance and nullable telemetry. Model-generated code inside JSON
  is experimental data, not a distributed harness script.
- Each saved final grade identifies its `artifact` and `artifact_sha256`.
  Dispatch `*.state.json` files are state records, not extra model responses.
- Questions are the sampling units. Repeated references to a candidate and the
  R/D branches do not create additional independent questions.
- Initial-answer, rejected-task and all-attempt denominators differ. Null means
  unknown, not measured zero. Post-review findings are separate from the frozen
  prespecified comparisons; no new inference was collected for them.

| Model | N /72 | R /72 | D /72 |
|---|---:|---:|---:|
| Ornith | 37 | 43 | 38 |
| Gemma | 40 | 45 | 46 |

None of the four prespecified comparisons passes Holm correction. This does not
establish equivalence or future reliability. Raw and adjusted p-values, paired
outcomes, subgroup counts and descriptive costs are in the JSON analyses.

## Scope of reproducibility

The records support reconstruction of policy selections, inspection of generated
candidates and fixtures, and independent statistical interpretation. The original
collector/evaluator/analysis scripts and full runtime are **not distributed**.
Thus this is not a complete computational replication package or a promise of
identical stochastic trajectories. Hashes of withheld code/metadata identify
retained evidence; not every referenced input is present in this export.

HumanEval final tests/canonical implementations are not bundled. The pinned
upstream component is EvalPlus 0.3.1 / HumanEvalPlus v0.1.10; its original JSONL
SHA-256 is `42526ec0e7d5f3ee0b06d6ced98f8c8bae3d76519151bfb3d36f79010645bd7f`.
Task identities/prompts are in the public manifest. Author replay/audit records
are reported evidence, not independent human review or verification of a proof
kernel. No new benchmark run is necessary to inspect these files.

## License and attribution

Author-contributed research data and annotations are CC BY 4.0 to the extent of
the author's rights; see `LICENSE`. Third-party prompts and dataset material keep
their original terms and notices in `THIRD_PARTY_NOTICES.md`. No exclusive rights
over facts or third-party/model-generated code are asserted. Model weights are
not included. Cite this study and the relevant HumanEval/EvalPlus sources.
