"""Geometry, terminal transport, lexicographic and causal counterexamples."""
import unittest
from copy import deepcopy
from fractions import Fraction

from solve import exact_tail, recover, plan, online
from verify import network_optimum, continuous_lower_bound, verify_trace

CASE={"target_m":9.5,"lower_m":9.,"upper_m":10.}


class CastingTest(unittest.TestCase):
    def test_short_tail_has_no_unstated_transport_exception(self):
        row=exact_tail(13.7)
        self.assertEqual(row["waste_m"],13.7)
        self.assertEqual(row["accepted_count"],0)
        row=exact_tail(14.5)
        self.assertEqual(row["waste_m"],4.8)
        self.assertEqual(row["recovered_m"],[9.7,0.])
        with self.assertRaises(ValueError): exact_tail(4.7)

    def test_continuous_tail_balances_lengths_exactly(self):
        row=exact_tail(109)
        self.assertEqual(row["waste_m"],0)
        self.assertEqual(row["accepted_count"],11)
        lengths=list(map(Fraction,row["exact"]["recovered"]))
        self.assertEqual(sum(lengths),109)
        self.assertEqual(len(set(lengths)),1)

    def test_offline_trim_can_be_shorter_than_transport_minimum(self):
        row=exact_tail(22.7)
        self.assertEqual(row["waste_m"],2.7)
        self.assertEqual(row["recovered_m"],[10.,10.])
        self.assertTrue(any(0<p-r<4.8 for p,r in zip(row["primary_m"],row["recovered_m"])))

    def test_defect_cannot_be_bridged_by_an_accepted_product(self):
        # Total clean length 10 m, but neither connected side reaches the 9 m minimum.
        edge=recover(0,108,[(50,58)],90,100,95)
        self.assertIsNone(edge["recovered"])
        self.assertEqual(edge["waste"],108)
        edge=recover(0,103,[(95,103)],90,100,95)
        self.assertEqual(edge["recovered"],[0,95])
        self.assertEqual(edge["waste"],8)

    def test_lp_matches_dynamic_program_for_both_lexicographic_objectives(self):
        defects=[(90,98),(137,145)]
        result=plan(0,10,defects,95,90,100)
        reference=network_optimum(0,10,defects,95,90,100)
        self.assertEqual(result["score"][:2],[reference["loss_tick"],reference["deviation_tick2"]])

    def test_future_events_do_not_change_prior_decisions(self):
        prefix=online([0,10],CASE)
        full=online([0,10,20,23],CASE)
        changed=online([0,10,40,100],CASE)
        for index in range(2):
            self.assertEqual(prefix["events"][index]["new_plan"],full["events"][index]["new_plan"])
            self.assertEqual(prefix["events"][index]["new_plan"],changed["events"][index]["new_plan"])

    def test_same_time_notification_precedes_new_cut(self):
        first=online([0],CASE)
        next_cut=first["events"][0]["new_plan"]["pieces"][0]["end"]
        result=online([0,next_cut/10],CASE)
        self.assertEqual(result["events"][1]["locked_boundary"],0)
        self.assertGreaterEqual(result["events"][1]["new_plan"]["pieces"][0]["end"],next_cut)

    def test_input_grid_is_explicit_and_never_silently_rounded(self):
        with self.assertRaises(ValueError): online([0,10.15],CASE,scale=10)
        self.assertEqual(len(online([0,10.15],CASE,scale=20)["events"]),2)

    def test_trace_verifier_rejects_cut_in_defect_and_backdated_execution(self):
        result=online([0,10],CASE)
        self.assertTrue(verify_trace(result,[0,10])["passed"])
        broken=deepcopy(result)
        broken["executed"][0]["planned_at"]=broken["executed"][0]["end"]+1
        with self.assertRaises(AssertionError): verify_trace(broken,[0,10])
        broken=deepcopy(result)
        broken["executed"][0]["recovered"]=[596,691]
        with self.assertRaises(AssertionError): verify_trace(broken,[0,10])
        broken=deepcopy(result)
        broken["events"][0]["new_plan"]["pieces"][-1]["waste"]+=1
        with self.assertRaises(AssertionError): verify_trace(broken,[0,10])

    def test_lower_bound_counts_short_clean_gap_between_defects(self):
        bound=continuous_lower_bound([0,4.7],9,10)
        self.assertEqual(bound["waste_m"],5.5)
        self.assertEqual(bound["healthy_gaps"][-1]["unavoidable_waste_m"],3.9)


if __name__=="__main__":
    unittest.main()
