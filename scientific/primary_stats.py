"""Exact original statistical functions, without grader imports."""
from collections import defaultdict
import math
import random
import statistics

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
