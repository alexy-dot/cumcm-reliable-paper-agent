"""Closed-form hierarchy and two-component Markov equivalence checks."""
import unittest
from fractions import Fraction as F
from itertools import product
from multistage import leaf,assembly,order_cost,source_tree
from rework import evaluate
from test_production import CASE
from verify_multistage import simulate_tree


class MultistageTest(unittest.TestCase):
    def test_recursion_matches_exact_markov_for_all_16_effective_two_part_policies(self):
        for t1,t2,tf,d in product((0,1),repeat=4):
            with self.subTest(policy=(t1,t2,tf,d)):
                children=[leaf(.1,4,2,t1),leaf(.1,18,3,t2)]
                value=order_cost(children,.1,6,3,5,6,tf,d)
                reference=evaluate(CASE,(t1,t2,1,1,tf,d))
                self.assertEqual(value,F(reference["cost_exact"]))

    def test_known_good_recovery_only_repeats_assembly_and_output_test(self):
        children=[leaf(.1,4,2,True),leaf(.1,18,3,True)]
        output=assembly(children,.1,6,3,5,True,True)
        expected=sum(c["cost"] for c in children)+(F(9)+F(".1")*5)/F(".9")
        self.assertEqual(output["cost"],expected)
        self.assertEqual(output["bad"],0)
        self.assertTrue(output["known"])

    def test_bad_child_repair_is_conditioned_on_failed_parent(self):
        child=leaf(.2,10,2,False)
        output=assembly([child],0,3,1,4,False,True)
        # A failure here proves that the only child was bad, so it must be replaced.
        self.assertEqual(output["bad"],F(".2"))
        self.assertEqual(output["repair_bad"],4+2+F(12)/F(".8")+3+1)

    def test_zero_defects_full_tree_costs_one_purchase_and_each_assembly_once(self):
        tree=source_tree()
        for p in tree["parts"]:p["p"]=0
        for s in tree["semis"]:s["p"]=0
        tree["final"]["p"]=0
        policy={"part_tests":[0]*8,"semi_tests":[0]*3,"semi_dismantle":[1]*3,"final_test":0,"final_dismantle":1}
        result=simulate_tree(tree,policy,20,10)
        self.assertEqual(result["mean_cost"],sum(p["purchase"] for p in tree["parts"])+32)
        self.assertEqual(result["standard_error"],0)
        self.assertEqual(result["mean_customer_returns"],0)

    def test_exact_cost_breakdown_matches_known_good_closed_form(self):
        from figures import breakdown
        tree=source_tree()
        policy={"part_tests":[1]*8,"semi_tests":[1]*3,"semi_dismantle":[1]*3,"final_test":0,"final_dismantle":1,"cost_exact":"1258/9"}
        result=breakdown(tree,policy)
        exact={k:F(v) for k,v in result["exact_components"].items()}
        self.assertEqual(exact["purchase"],F(64)/F(".9"))
        self.assertEqual(exact["part_inspection"],F(11)/F(".9"))
        self.assertEqual(exact["customer_exchange_loss"],F(40)/9)
        self.assertEqual(exact["final_inspection"],0)
        self.assertEqual(sum(exact.values()),F("1258/9"))
        policy.update(final_test=1,cost_exact="142")
        inspected=breakdown(tree,policy)
        self.assertEqual(F(inspected["exact_components"]["customer_exchange_loss"]),0)
        self.assertEqual(F(inspected["exact_components"]["final_inspection"]),F(20)/3)


if __name__=="__main__":unittest.main()
