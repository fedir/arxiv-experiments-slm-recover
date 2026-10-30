# P1 post-review precision, configuration and cost analysis

Declared 2026-10-26 before implementing/computing these additional intervals and
cost ratios. Original task outcomes and corrected decisions are already known.
This is post-review sensitivity/reporting, not a new prespecified analysis, data
collection, replacement grading or policy tuning. P0.3 publication is deferred.

## P1.1: conservative simultaneous paired risk-difference bounds

Retain original exact McNemar tests, their four-contrast Holm correction and the
original stratified percentile-bootstrap intervals. Publish raw and adjusted
p-values side by side. Do not choose an interval according to significance.

Respect the original fixed Python/SQL/shell allocation. For each of four contrasts
and each of three families, count improved (b) and worsened (c) paired outcomes.
Their marginal probabilities have Clopper-Pearson binomial intervals. There are
4 * 3 * 2 = 24 component intervals. At familywise alpha = 0.05, each component
has two-sided alpha 0.05/24, with alpha/48 in each tail. Form family-specific
risk-difference bounds [L(b)-U(c), U(b)-L(c)] and weight them by n_family/72.

By a union bound, simultaneous coverage across the four risk differences is at
least 95% **under a working model of independent, identically distributed task
pairs within each task family**. Independence between discordant cells or between
contrasts is not required. Template dependence, nonexchangeable custom tasks and
a single stochastic trajectory limit that interpretation. The method is deliberately
conservative; it is not cluster-robust and does not estimate repeated-block noise.
It does not invert the conditional McNemar test. Use it as post-review sensitivity,
not as a newly chosen confirmatory decision rule or proof of equivalence.

Compute binomial tails directly using integer combinatorial coefficients and
floating-point summation, then invert by bounded bisection. Validate against
closed-form boundary cases, a known nonboundary reference interval, and independent
finite-sample binomial/multinomial probability enumeration on small samples.
Zero discordances must not produce an unjustified zero-width interval.

Discuss both zero and the predeclared +10/-10 percentage-point meaningful effects
without retrospectively calling the study powered for those effects.

## P1.2: evidence-backed configuration

Use frozen model protocols, the two primary preflights and the frozen preparation
source for checkpoint directory/repository identities. A same-session pilot's
environment-start record contains a chip name not separately captured at the
primary preflights: identify that provenance explicitly rather than upgrading it
to a direct primary measurement. Confirm matching memory/OS fields where recorded.
Do not query the current machine or installation to backfill collection settings.

Record model weight hashes already in the PDF and add tokenizer/config/index
hashes. Repository names do not attest upstream revisions. Label LM Studio app
version, underlying library versions, sampler/cache effectiveness, actual thermal
trajectory and background-load control unknown where not attested. Report actual
power/swap snapshots and fixed model/task/arm order; make no hardware speed claim.

Small local checkpoint configuration files may be inspected after collection only
when their exact SHA-256 matches the pre-collection digest. Preserve those exact
bytes in post-review evidence, report nominal defaults and mixed-bit overrides,
and distinguish static checkpoint configuration from runtime attestation. This
does not backfill a current application's settings or versions.

## P1.3: incremental cost per net additional final-test pass

For p in R,D, compute G_p = sum_t(Y_p,t - Y_N,t). For each cost field, compute
Delta_p = sum_t(cost_p,t - cost_N,t) from unrounded task-level values, then
Delta_p/G_p only when G_p > 0. Report delta and undefined ratios for zero/negative
gain. Unknown token counts propagate to null; they are not measured zero.

Use saved policy full-loop seconds and sum actual prompt/completion tokens from
the selected policy's attempt list, charging the shared first answer once within
each policy. Physical collection still counts that shared request once overall.
This is descriptive policy accounting, excluding loading/final grading; no monetary
price, deployment-efficiency guarantee or cross-model hardware ranking follows.
Small net gains make these ratios unstable, and corrected significance of gain
is not established. Validate R-N against about 7.77 s/net pass (Ornith) and
35.89 s/net pass (Gemma); include D under the same definition.

## Provenance

Write `analysis-p1.json` plus content-addressed `manifests-p1/` and source snapshots.
Reference unchanged P0.2 evidence and add hashes for newly consumed preflights,
configuration-source bytes and the qualified pilot metadata. All 72 tasks per
model remain included; no model calls or new final grades are made. Preserve
original protocols, grades, analysis, bootstrap intervals and P0.2 outputs.
