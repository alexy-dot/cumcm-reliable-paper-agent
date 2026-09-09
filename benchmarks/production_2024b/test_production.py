"""Probability normalization, immutable bad parts, known quality and one-time revenue."""
import math
import unittest
from fractions import Fraction
from itertools import product
from rework import evaluate,gaussian
from sampling import boundaries,operating_characteristic,log_evidence

CASE={"p1":.1,"p2":.1,"inspect1":2,"inspect2":3,"purchase1":4,"purchase2":18,
      "assembly_defect":.1,"assembly":6,"inspect_final":3,"replacement_loss":6,"disassembly":5,"price":56}


class ProductionTest(unittest.TestCase):
    def test_bad_reused_parts_are_not_fresh_random_draws(self):
        self.assertFalse(evaluate(CASE,(0,0,0,0,0,1))["proper"])
        self.assertTrue(evaluate(CASE,(0,0,1,1,0,1))["proper"])

    def test_scrap_replacement_matches_geometric_closed_form(self):
        result=evaluate(CASE,(0,0,0,0,0,0))
        success=.9**3
        expected=(22+6+6*(1-success))/success
        self.assertAlmostEqual(result["expected_cost"],expected)
        self.assertAlmostEqual(result["profit"],56-expected)
        self.assertAlmostEqual(result["expected_assemblies"],1/success)

    def test_known_good_components_do_not_pay_repeat_inspection(self):
        result=evaluate(CASE,(1,1,1,1,1,1))
        expected=(4+2)/.9+(18+3)/.9+(6+3+.1*5)/.9
        self.assertAlmostEqual(result["expected_cost"],expected)
        self.assertEqual(result["expected_customer_returns"],0)

    def test_no_defects_reduces_to_one_purchase_and_one_assembly(self):
        result=evaluate({**CASE,"p1":0,"p2":0,"assembly_defect":0},(0,0,0,0,0,1))
        self.assertTrue(result["proper"])
        self.assertEqual(result["expected_cost"],28)

    def test_rational_solver_detects_a_closed_failure_class(self):
        with self.assertRaises(ValueError):gaussian([[Fraction(0)]],[Fraction(1)])

    def test_initial_evidence_is_one_in_both_directions(self):
        evidence=log_evidence(0,0)
        self.assertAlmostEqual(evidence["accept"],0)
        self.assertAlmostEqual(evidence["reject"],0)

    def test_path_enumeration_agrees_with_sampling_dynamic_program(self):
        table=boundaries(12,.1,.05,.1);p=.2
        totals={"accept":0.,"reject":0.,"unresolved":0.};expected=0.
        for path in product((0,1),repeat=12):
            probability=p**sum(path)*(1-p)**(12-sum(path));k=0;verdict="unresolved";used=12
            for n,defect in enumerate(path,1):
                k+=defect;row=table[n-1]
                if row["accept_at_most"] is not None and k<=row["accept_at_most"]:verdict="accept";used=n;break
                if row["reject_at_least"] is not None and k>=row["reject_at_least"]:verdict="reject";used=n;break
            totals[verdict]+=probability;expected+=used*probability
        actual=operating_characteristic(table,p)
        for key,value in totals.items():self.assertAlmostEqual(actual[key+"_probability"],value)
        self.assertAlmostEqual(actual["expected_tests_up_to_cap"],expected)


if __name__=="__main__":unittest.main()
