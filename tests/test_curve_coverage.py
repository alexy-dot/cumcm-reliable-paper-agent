import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill/cumcm-reliable-paper/scripts"))
try:
    from curve_coverage import directed_coverage, compare_curves
except ImportError:
    directed_coverage = None


@unittest.skipIf(directed_coverage is None, "optional NumPy/SciPy unavailable")
class CurveCoverageTest(unittest.TestCase):
    def test_small_shared_segment_does_not_certify_full_coverage(self):
        result = directed_coverage([[0, 0], [10, 0]], [[0, 0], [3, 0]], tolerance=.05, step=.01)
        self.assertLess(result["best_20_percent_midpoint_rms"], .01)
        self.assertLess(result["covered_fraction_upper"], .31)
        self.assertLessEqual(result["maximum_distance_lower"], 7)
        self.assertGreaterEqual(result["maximum_distance_upper"], 7)
        self.assertTrue(result["definitely_uncovered_arc_intervals"])

    def test_parallel_curves_have_analytic_directed_distance(self):
        result = compare_curves([[0, 0], [10, 0]], [[0, 2], [10, 2]], tolerance=2.1, step=.02)
        for report in result.values():
            self.assertEqual(report["covered_fraction_lower"], 1)
            self.assertLessEqual(report["maximum_distance_lower"], 2)
            self.assertGreaterEqual(report["maximum_distance_upper"], 2)

    def test_sampling_density_and_repeated_points_do_not_reweight_length(self):
        a = directed_coverage([[0, 0], [10, 0]], [[0, 0], [3, 0]], tolerance=.05, step=.02)
        b = directed_coverage([[0, 0], [0, 0], [.01, 0], [.02, 0], [10, 0]], [[0, 0], [3, 0]], tolerance=.05, step=.02)
        self.assertEqual(a["covered_fraction_upper"], b["covered_fraction_upper"])

    def test_corner_vertices_are_preserved(self):
        r = directed_coverage([[0, 0], [1, 0], [1, 1]], [[0, 0], [1, 0], [1, 1]], tolerance=.1, step=.04)
        self.assertEqual(r["covered_fraction_lower"], 1)
        self.assertLess(r["maximum_distance_upper"], .1)

    def test_invalid_geometry_and_impractical_resolution_are_rejected(self):
        for source, step in (([[0, 0], [0, 0]], .1), ([[0, 0], [1, float("nan")]], .1), ([[0, 0], [1, 0]], 1e-10)):
            with self.assertRaises(ValueError):
                directed_coverage(source, [[0, 0], [1, 0]], tolerance=.1, step=step)


if __name__ == "__main__":
    unittest.main()
