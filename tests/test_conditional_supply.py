import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill/cumcm-reliable-paper/scripts"))
try:
    import numpy as np
    from conditional_supply import METHODS, fit_response, predict_response
except ImportError:
    np = None


@unittest.skipIf(np is None, "optional NumPy unavailable")
class ConditionalSupplyTest(unittest.TestCase):
    def test_failed_orders_enter_the_mean_and_new_orders_do_not_refit(self):
        model = fit_response([[10, 10, 0]], [[10, 0, 0]])
        before = repr(model)
        y, support = predict_response(model, [[0, 10, 100]])
        np.testing.assert_array_equal(y, [[0, 5, 50]])
        self.assertTrue(support["outside_fitted_order_range"][0, 2])
        self.assertEqual(repr(model), before)

    def test_no_order_is_zero_under_all_methods(self):
        for method in METHODS:
            y, _ = predict_response(fit_response([[1, 2, 10, 20]], [[0, 3, 7, 12]], method), [[0, 0]])
            np.testing.assert_array_equal(y, [[0, 0]])

    def test_recent_response_adapts_without_reading_future_supply(self):
        o = np.ones((1, 96))*10
        s = np.r_[np.ones(48)*10, np.zeros(48)][None, :]
        y, _ = predict_response(fit_response(o, s, "ratio_48"), [[10]])
        self.assertEqual(y[0, 0], 0)
        y, _ = predict_response(fit_response(o, s, "ratio_all"), [[10]])
        self.assertEqual(y[0, 0], 5)

    def test_cold_start_uses_training_pooled_rate_but_remains_flagged(self):
        model = fit_response([[0, 0], [10, 10]], [[0, 0], [5, 5]])
        y, flags = predict_response(model, [[20], [10]])
        self.assertEqual(y[0, 0], 10)
        self.assertTrue(flags["cold_start"][0, 0])

    def test_internal_data_gap_is_not_mislabeled_as_range_extrapolation(self):
        model = fit_response([[1, 2, 1000, 1000]], [[1, 2, 500, 900]])
        _, flags = predict_response(model, [[100, 1000]])
        self.assertFalse(flags["outside_fitted_order_range"][0, 0])
        self.assertTrue(flags["no_nearby_orders"][0, 0])
        self.assertEqual(flags["nearby_order_count"][0, 1], 2)

    def test_backlog_or_invalid_inputs_are_explicitly_unsupported(self):
        for o, s in (([[0]], [[1]]), ([[1]], [[float("nan")]]), ([[-1]], [[0]])):
            with self.assertRaises(ValueError):
                fit_response(o, s)
