# Post-review analysis v2: P0.2 verifier bottleneck

Declared 2026-10-26, after review and inspection of the original outcomes.
This is a retrospective descriptive analysis, not a new prespecified test or
inference collection. Read only the original `confirmation-run-v1` evidence;
never rewrite candidates, public decisions, selection paths, grades or protocol.

## Fixed definitions

For each model/task, use the shared N/R/D first artifact, its recorded public
decision and its saved final grade, verified against the candidate-file hash.
Partition all initial tasks into public accepted/rejected × final pass/fail.

Let A denote public acceptance, C final correctness and J public rejection.
The hypothetical perfect-recovery upper bound is

```
(|A intersect C| + |J|) / n = 1 - |A intersect not C| / n.
```

Public acceptance fixes the selected initial answer. Only J can receive a retry.
The bound supposes a successful permitted-budget candidate on every rejected
task. It does not assert that such candidates exist, can be generated, or will
occur on future tasks. It also holds when some initially correct tasks are
publicly rejected; do not double-count these false rejections as extra gains.

For each of R and D, report final passing selected retries / initial rejections,
plus final failures, still-publicly-rejected retries, false accepts after retry
and missing/in-flight outcomes. Distinguish conditional successes from actual
repairs when a rejected initial answer was already correct.

## Strata and denominators

- Initial tasks (72/model): Python/SQL/shell and, within Python, zero runnable
  prompt doctest examples versus at least one. Use frozen public metadata only.
- Unique recorded candidates (108 Ornith, 118 Gemma): same strata, separately
  reported. Shared first responses are counted once, not once per policy.
- False accept: final failure / publicly accepted candidates in that stratum.
- False reject: final pass / publicly rejected candidates in that stratum.
- Empty denominators are null/not applicable, never a measured zero rate.
- Python coverage subgroups partition Python; they are not additional tasks to
  add to the family totals. Retry pools are selected by the gate, not iid samples.

No new p-values, model ranking or causal coverage effect is inferred. Retain the
original four-contrast analysis without reinterpretation or outcome-based tuning.
Missing or inconsistent evidence blocks analysis; it is not silently excluded.

## Provenance and outputs

`analyze_verifier.py` verifies model/task/block/protocol associations, selection
paths, dispatch states, grade hashes and reconciliation with the frozen analysis.
It stores consumed-input hashes, code and plan hashes in content-addressed
manifests, and records candidate-level trace rows in `analysis-verifier.json`.
Reruns retain prior manifest/source snapshots and create a new manifest if code
or inputs differ. No requests are dispatched and no final grade is recomputed.

Paper generators consume the derived analysis, verify its identity and input
hashes, and produce numbers, tables and a ceiling illustration. Original tables,
test decisions and frozen analysis remain the baseline. New findings are labelled
post-review in the PDF and `REPORT.md`.
