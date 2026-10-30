"""Independent small-sample and accounting controls for P1 sensitivity."""

import copy
from fractions import Fraction
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "review"))
import analyze_precision_cost as analysis


def cost_row(n_score, r_score, n_cost, r_cost):
    return {
        "scores": {"N": n_score, "R": r_score},
        "costs": {
            "N": dict(
                zip(("prompt_tokens", "completion_tokens", "full_loop_seconds"), n_cost)
            ),
            "R": dict(
                zip(("prompt_tokens", "completion_tokens", "full_loop_seconds"), r_cost)
            ),
        },
    }


class PrecisionCostControls(unittest.TestCase):
    def test_clopper_pearson_boundaries_and_reference(self):
        alpha = 0.05
        self.assertEqual(0.0, analysis.clopper_pearson(0, 10, alpha)[0])
        self.assertAlmostEqual(
            1 - (alpha / 2) ** (1 / 10),
            analysis.clopper_pearson(0, 10, alpha)[1],
            places=13,
        )
        self.assertAlmostEqual(
            (alpha / 2) ** (1 / 10),
            analysis.clopper_pearson(10, 10, alpha)[0],
            places=13,
        )
        self.assertEqual(1.0, analysis.clopper_pearson(10, 10, alpha)[1])
        # Standard exact 95% binomial reference for 3 successes in 10 trials.
        low, high = analysis.clopper_pearson(3, 10, alpha)
        self.assertAlmostEqual(0.0667395111777345, low, places=12)
        self.assertAlmostEqual(0.6524528500599972, high, places=12)

    def test_rational_probability_enumeration_component_coverage(self):
        alpha = 0.05 / 24
        probabilities = [
            Fraction(v, 1000)
            for v in (0, 1, 10, 50, 100, 250, 500, 750, 900, 950, 990, 999, 1000)
        ]
        for n in range(1, 9):
            intervals = [analysis.clopper_pearson(k, n, alpha) for k in range(n + 1)]
            for p in probabilities:
                covered = sum(
                    Fraction(math.comb(n, k)) * p**k * (1 - p) ** (n - k)
                    for k, (low, high) in enumerate(intervals)
                    if low - 1e-14 <= float(p) <= high + 1e-14
                )
                self.assertGreaterEqual(float(covered) + 1e-12, 1 - alpha, (n, p))

    def test_zero_discordance_and_direction_symmetry(self):
        rows = [
            {"category": category, "R": 0, "N": 0}
            for category in analysis.CATEGORIES
            for _ in range(4)
        ]
        zero = analysis.simultaneous_interval(rows, "R", "N")
        self.assertLess(zero["bounds_pp"][0], 0.0)
        self.assertGreater(zero["bounds_pp"][1], 0.0)
        self.assertEqual(24, zero["components"])
        rows[0]["R"] = 1
        positive = analysis.simultaneous_interval(rows, "R", "N")
        negative = analysis.simultaneous_interval(rows, "N", "R")
        self.assertAlmostEqual(positive["bounds_pp"][0], -negative["bounds_pp"][1])
        self.assertAlmostEqual(positive["bounds_pp"][1], -negative["bounds_pp"][0])

    def test_matched_multinomial_coverage_small_samples(self):
        # Independently enumerate paired +1/-1/0 outcomes; no independence
        # between the two discordant-cell counts is assumed.
        n = 4
        alpha = 0.05 / 24
        for p, q in (
            (Fraction(0), Fraction(0)),
            (Fraction(1, 5), Fraction(1, 5)),
            (Fraction(1, 2), Fraction(0)),
            (Fraction(1, 4), Fraction(1, 2)),
        ):
            covered = Fraction(0)
            for b in range(n + 1):
                for c in range(n - b + 1):
                    remaining = n - b - c
                    bl, bu = analysis.clopper_pearson(b, n, alpha)
                    cl, cu = analysis.clopper_pearson(c, n, alpha)
                    probability = (
                        Fraction(
                            math.factorial(n),
                            math.factorial(b)
                            * math.factorial(c)
                            * math.factorial(remaining),
                        )
                        * p**b
                        * q**c
                        * (1 - p - q) ** remaining
                    )
                    if bl - cu - 1e-14 <= float(p - q) <= bu - cl + 1e-14:
                        covered += probability
            self.assertGreaterEqual(float(covered) + 1e-12, 1 - 2 * alpha)

    def test_cost_uses_unrounded_sum_and_net_gain(self):
        rows = [
            cost_row(0, 1, (10, 3, 1.0), (15, 6, 3.0)),
            cost_row(0, 0, (20, 4, 4.0), (30, 5, 8.0)),
        ]
        result = analysis.cost_contrast(rows, "R")
        self.assertEqual(1, result["net_additional_passes"])
        self.assertEqual(
            {"prompt_tokens": 15.0, "completion_tokens": 4.0, "full_loop_seconds": 6.0},
            result["per_net_additional_pass"],
        )

    def test_zero_negative_gain_and_unknown_tokens(self):
        rows = [
            cost_row(0, 1, (10, 3, 1.0), (15, 6, 3.0)),
            cost_row(1, 0, (20, 4, 4.0), (30, 5, 8.0)),
        ]
        result = analysis.cost_contrast(rows, "R")
        self.assertEqual((1, 1), (result["repairs"], result["regressions"]))
        self.assertTrue(
            all(v is None for v in result["per_net_additional_pass"].values())
        )
        rows[0]["scores"] = {"N": 1, "R": 0}
        self.assertLess(analysis.cost_contrast(rows, "R")["net_additional_passes"], 0)
        missing = copy.deepcopy(rows[:1])
        missing[0]["scores"] = {"N": 0, "R": 1}
        missing[0]["costs"]["R"]["prompt_tokens"] = None
        self.assertIsNone(
            analysis.cost_contrast(missing, "R")["delta"]["prompt_tokens"]
        )

    def test_mixed_quantization_metadata_is_not_flattened(self):
        result = analysis.quantization_summary(
            {
                "quantization": {
                    "bits": 4,
                    "group_size": 64,
                    "mode": "affine",
                    "layer": {"bits": 8, "group_size": 64},
                }
            }
        )
        self.assertEqual(4, result["default"]["bits"])
        self.assertEqual({"8": 1}, result["override_bits_counts"])
        self.assertEqual(1, result["layer_override_count"])
        with self.assertRaisesRegex(ValueError, "conflicting"):
            analysis.quantization_summary(
                {"quantization": {"bits": 4}, "quantization_config": {"bits": 8}}
            )

    def test_invalid_counts_and_missing_strata_fail_closed(self):
        for args in ((-1, 5, 0.05), (6, 5, 0.05), (0, 0, 0.05), (1, 5, 0)):
            with self.assertRaises(ValueError):
                analysis.clopper_pearson(*args)
        with self.assertRaises(ValueError):
            analysis.simultaneous_interval(
                [{"category": "python", "R": 0, "N": 0}], "R", "N"
            )


if __name__ == "__main__":
    unittest.main()
