"""Q4 sample provenance, conditional-rate semantics and vector/rational agreement."""
import unittest
from itertools import product
import numpy as np
from sampled_rates import counts_parameters,case_tree,evaluate,search
from multistage import source_tree,leaf,assembly,order_cost
from rework import evaluate as markov
from test_production import CASE
from verify_sampled_rates import quadrature,all_tested_expectation


class SampledRatesTest(unittest.TestCase):
    def test_posterior_uses_counts_not_just_nominal_fraction(self):
        small=counts_parameters([{"n":20,"k":2,"basis":"random_supply"}],["random_supply"],{"alpha":1,"beta":1})
        large=counts_parameters([{"n":200,"k":20,"basis":"random_supply"}],["random_supply"],{"alpha":1,"beta":1})
        np.testing.assert_array_equal(small,[[3,19]])
        np.testing.assert_array_equal(large,[[21,181]])

    def test_mixed_input_assembly_samples_and_infinite_mean_are_rejected(self):
        with self.assertRaises(ValueError):counts_parameters([{"n":20,"k":2,"basis":"random_supply"}],["good_inputs"],{"alpha":1,"beta":1})
        with self.assertRaises(ValueError):counts_parameters([{"n":20,"k":20,"basis":"good_inputs"}],["good_inputs"],{"alpha":1,"beta":1})

    def test_vector_cost_matches_rational_markov_across_policies_and_rates(self):
        tree=case_tree(CASE);rates=np.array([[.1,.1,.1],[.2,.05,.15]])
        for t1,t2,tf,d in product((0,1),repeat=4):
            policy={"part_tests":[t1,t2],"semi_tests":[],"semi_dismantle":[],"final_test":tf,"final_dismantle":d}
            actual=evaluate(tree,policy,rates)
            expected=[markov({**CASE,"p1":p1,"p2":p2,"assembly_defect":pf},(t1,t2,1,1,tf,d))["expected_cost"] for p1,p2,pf in rates]
            np.testing.assert_allclose(actual,expected,atol=1e-10,rtol=0)

    def test_multistage_vector_preserves_conditional_repair_cost(self):
        tree=source_tree();rng=np.random.default_rng(31)
        for _ in range(12):
            flags=rng.integers(0,2,16).tolist();rates=rng.uniform(.03,.25,(1,12))
            policy={"part_tests":flags[:8],"semi_tests":flags[8:11],"semi_dismantle":flags[11:14],"final_test":flags[14],"final_dismantle":flags[15]}
            parts=[leaf(float(rates[0,i]),p["purchase"],p["test"],flags[i]) for i,p in enumerate(tree["parts"])]
            semis=[assembly([parts[j] for j in n["children"]],float(rates[0,8+i]),n["assembly"],n["test"],n["dismantle"],flags[8+i],flags[11+i]) for i,n in enumerate(tree["semis"])]
            expected=order_cost(semis,float(rates[0,-1]),8,6,10,40,flags[14],flags[15])
            self.assertAlmostEqual(evaluate(tree,policy,rates)[0],float(expected),places=8)

    def test_beta_quadrature_normalization_mean_and_inverse_good_rate(self):
        parameters=np.array([[3,19],[5,17],[2,20]],float);rates,weights=quadrature(parameters,16)
        self.assertAlmostEqual(weights.sum(),1)
        np.testing.assert_allclose(weights@rates,parameters[:,0]/parameters.sum(axis=1),atol=1e-12)
        np.testing.assert_allclose(weights@(1/(1-rates)),(parameters.sum(axis=1)-1)/(parameters[:,1]-1),atol=1e-10)
        self.assertAlmostEqual(all_tested_expectation(source_tree(),np.tile([3.,19.],(12,1)),0),150+1/6)


if __name__=="__main__":unittest.main()
