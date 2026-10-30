"""Exact retrospective interval/cost/configuration functions."""
from collections import Counter
from functools import lru_cache
import math
CATEGORIES = ("python", "sql", "shell")
CONTRASTS = (("R", "N"), ("D", "R"))
ALPHA = 0.05
FAMILY_SIZE = 4

def binomial_tail(k, n, p, *, upper):
    indices = range(k, n + 1) if upper else range(k + 1)
    return math.fsum(math.comb(n, j) * p**j * (1 - p) ** (n - j) for j in indices)


@lru_cache(maxsize=None)
def clopper_pearson(k, n, alpha):
    if (
        type(n) is not int
        or type(k) is not int
        or n < 1
        or not 0 <= k <= n
        or not 0 < alpha < 1
    ):
        raise ValueError("invalid binomial count/confidence")
    tail = alpha / 2
    low = 0.0
    if k:
        a, b = 0.0, 1.0
        for _ in range(80):
            mid = (a + b) / 2
            if binomial_tail(k, n, mid, upper=True) < tail:
                a = mid
            else:
                b = mid
        low = (a + b) / 2
    high = 1.0
    if k < n:
        a, b = 0.0, 1.0
        for _ in range(80):
            mid = (a + b) / 2
            if binomial_tail(k, n, mid, upper=False) > tail:
                a = mid
            else:
                b = mid
        high = (a + b) / 2
    return low, high


def simultaneous_interval(rows, left, right, *, alpha=ALPHA, family_size=FAMILY_SIZE):
    groups = {
        category: [r for r in rows if r["category"] == category]
        for category in CATEGORIES
    }
    if not rows or any(not values for values in groups.values()):
        raise ValueError("all three declared task families are required")
    component_alpha = alpha / (family_size * len(groups) * 2)
    lower, upper, strata = 0.0, 0.0, {}
    for category, values in groups.items():
        improved = sum(r[left] > r[right] for r in values)
        worsened = sum(r[left] < r[right] for r in values)
        b_bounds = clopper_pearson(improved, len(values), component_alpha)
        c_bounds = clopper_pearson(worsened, len(values), component_alpha)
        weight = len(values) / len(rows)
        lower += weight * (b_bounds[0] - c_bounds[1])
        upper += weight * (b_bounds[1] - c_bounds[0])
        strata[category] = {
            "n": len(values),
            "improved": improved,
            "worsened": worsened,
            "improved_probability_bounds": b_bounds,
            "worsened_probability_bounds": c_bounds,
        }
    return {
        "contrast": f"{left}-{right}",
        "bounds_pp": [100 * lower, 100 * upper],
        "component_alpha": component_alpha,
        "components": family_size * len(groups) * 2,
        "nominal_familywise_confidence": 1 - alpha,
        "strata": strata,
        "contains_zero": lower <= 0 <= upper,
        "contains_plus_10pp": lower <= 0.10 <= upper,
        "contains_minus_10pp": lower <= -0.10 <= upper,
    }


def cost_contrast(rows, policy, baseline="N"):
    gain = sum(r["scores"][policy] - r["scores"][baseline] for r in rows)
    result = {
        "contrast": f"{policy}-{baseline}",
        "tasks": len(rows),
        "net_additional_passes": gain,
        "repairs": sum(r["scores"][policy] and not r["scores"][baseline] for r in rows),
        "regressions": sum(
            r["scores"][baseline] and not r["scores"][policy] for r in rows
        ),
        "delta": {},
        "per_net_additional_pass": {},
    }
    for metric in ("prompt_tokens", "completion_tokens", "full_loop_seconds"):
        pairs = [
            (r["costs"][policy][metric], r["costs"][baseline][metric]) for r in rows
        ]
        if any(a is None or b is None for a, b in pairs):
            delta = None
        else:
            if any(not math.isfinite(v) or v < 0 for pair in pairs for v in pair):
                raise ValueError("invalid recorded cost")
            delta = math.fsum(a - b for a, b in pairs)
        result["delta"][metric] = delta
        result["per_net_additional_pass"][metric] = (
            delta / gain if gain > 0 and delta is not None else None
        )
    return result


def quantization_summary(config):
    if (
        "quantization" in config
        and "quantization_config" in config
        and config["quantization"] != config["quantization_config"]
    ):
        raise ValueError("conflicting checkpoint quantization declarations")
    quantization = config.get("quantization", config.get("quantization_config", {}))
    overrides = {
        name: value for name, value in quantization.items() if isinstance(value, dict)
    }
    counts = Counter(str(value.get("bits", "unknown")) for value in overrides.values())
    return {
        "default": {
            key: quantization.get(key) for key in ("bits", "group_size", "mode")
        },
        "layer_override_count": len(overrides),
        "override_bits_counts": dict(sorted(counts.items())),
        "overrides": overrides,
    }
