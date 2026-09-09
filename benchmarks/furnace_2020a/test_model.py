"""Numerical invariants independent of the fitted answers. Requires scientific extras."""
import unittest
from unittest.mock import patch
import numpy as np
from model import LENGTH, temperature_curve, curve_metrics, crossing


class FurnaceNumericsTest(unittest.TestCase):
    def test_geometry_and_uniform_room_temperature(self):
        self.assertEqual(LENGTH, 435.5)
        parameters = [50, 70, 40, 45, 24, 30, 99]
        time, temperature = temperature_curve([25, 25, 25, 25], 78, parameters)
        self.assertAlmostEqual(time[-1], 335)
        np.testing.assert_array_equal(temperature, np.full(len(time), 25.))

    def test_area_stops_at_peak_and_duration_includes_both_sides(self):
        t = np.array([0., 10., 20.])
        y = np.array([200., 240., 200.])
        with patch("model.temperature_curve", return_value=(t, y)):
            m = curve_metrics([175, 195, 235, 255], 70, [50, 5, 55])
        self.assertAlmostEqual(m["t217_up"], 4.25)
        self.assertAlmostEqual(m["t217_down"], 15.75)
        self.assertAlmostEqual(m["time_above_217"], 11.5)
        self.assertAlmostEqual(m["area_rising_above_217"], 66.125)
        self.assertAlmostEqual(m["symmetry"], 0.)

    def test_ascending_and_descending_crossings_are_distinct(self):
        t = np.array([0., 1., 2., 3., 4.])
        y = np.array([25., 150., 190., 150., 25.])
        self.assertEqual(crossing(t, y, 150, True), 1.)
        self.assertEqual(crossing(t, y, 150, False), 3.)

    def test_frozen_model_superposition_for_multiple_heater_settings(self):
        from structural_evidence import affine_basis
        parameters = [50, 70, 40, 45, 24, 30, 99]
        _, ambient, basis = affine_basis(81., parameters, dx=.25)
        for settings in [[165,185,225,245], [185,205,245,265], [173,198,230,257]]:
            _, actual = temperature_curve(settings,81.,parameters,dx=.25)
            np.testing.assert_allclose(ambient+(np.array(settings)-25)@basis, actual, atol=1e-8, rtol=0)

    def test_positive_filter_identity_matches_independent_continuous_ode(self):
        from structural_evidence import check_speed_identity
        result = check_speed_identity([182,203,237,254], [50,70,40,45,24,30,99])
        self.assertTrue(result["passed"],result)

    def test_tradeoff_envelope_cannot_choose_infeasible_or_worse_candidate(self):
        from decision_evidence import select_incumbent
        metrics={"max_rise":2.,"max_cooling":2.,"soak_150_190":80.,"time_above_217":60.,
                 "peak":245.,"symmetry":.04,"area_rising_above_217":400.}
        good={"settings":[175,195,235,255],"speed_cm_min":80.,"metrics":metrics}
        bad={**good,"metrics":{**metrics,"peak":239.,"symmetry":.01}}
        worse={**good,"metrics":{**metrics,"symmetry":.05}}
        over_cap={**good,"metrics":{**metrics,"area_rising_above_217":450.,"symmetry":.02}}
        self.assertIs(select_incumbent([good,bad,worse,over_cap],420),good)
        self.assertIs(select_incumbent([good,over_cap],460),over_cap)
        with self.assertRaises(ValueError): select_incumbent([good],390)

    def test_joint_design_respects_asymmetric_entry_bound(self):
        from decision_evidence import joint_parameters
        base=np.array([50,70,40,45,24,30.5,99.])
        p=joint_parameters(base,np.array([[0.]*7,[1.]*7]))
        np.testing.assert_allclose(p[0],.98*base)
        self.assertEqual(p[1,5],base[5])
        np.testing.assert_allclose(p[1,[0,1,2,3,4,6]],1.02*base[[0,1,2,3,4,6]])
        with self.assertRaises(ValueError): joint_parameters(base,np.array([[2.]*7]))


if __name__ == "__main__":
    unittest.main()
