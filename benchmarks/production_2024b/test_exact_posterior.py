"""Exact moments tested against independent tensor quadrature and divergent-variance cases."""
import unittest
from itertools import product
from fractions import Fraction as F
import numpy as np
from scipy.special import roots_jacobi
from exact_posterior import leaf_moments,assembly_moments,finish_cost,evaluate,shapes
from sampled_rates import case_tree,evaluate as conditional_cost
from multistage import source_tree
from verify_sampled_rates import posterior_costs,all_tested_expectation
from test_production import CASE


class ExactPosteriorTest(unittest.TestCase):
    def test_all_two_part_policies_match_independent_beta_quadrature(self):
        params=[(F(3),F(19)),(F(5),F(17)),(F(2),F(20))];tree=case_tree(CASE)
        for row in posterior_costs(tree,np.array(params,float),32):
            self.assertAlmostEqual(float(evaluate(tree,row["policy"],params)),row["posterior_mean_cost"],places=9)

    def test_finite_mean_with_infinite_variance_is_computable_exactly(self):
        shape=shapes([{"n":1,"k":0,"basis":"random_supply"}],["random_supply"],{"alpha":1,"beta":1})[0]
        item=leaf_moments(shape,10,2,True)
        self.assertEqual(item["C"],24)
        self.assertEqual(item["w"],0)
        with self.assertRaises(ValueError):leaf_moments((F(2),F(1)),10,2,True)

    def test_all_upstream_tested_matches_separate_analytic_expression(self):
        tree=source_tree();params=[(F(3),F(19))]*12
        for test in (0,1):
            policy={"part_tests":[1]*8,"semi_tests":[1]*3,"semi_dismantle":[1]*3,"final_test":test,"final_dismantle":1}
            self.assertAlmostEqual(float(evaluate(tree,policy,params)),all_tested_expectation(tree,np.array(params,float),test),places=10)

    def test_two_layer_mixed_policies_match_four_dimensional_quadrature(self):
        tree={"parts":[{"purchase":4,"test":2},{"purchase":18,"test":3}],
              "semis":[{"children":[0,1],"assembly":6,"test":3,"dismantle":5}],
              "final":{"assembly":8,"test":6,"dismantle":10,"exchange_loss":40,"price":100}}
        params=[(F(3),F(19)),(F(4),F(18)),(F(2),F(20)),(F(5),F(17))]
        axes=[];weights=[]
        for a,b in params:
            x,w=roots_jacobi(12,float(b-1),float(a-1));axes.append((x+1)/2);weights.append(w/w.sum())
        grid=np.stack(np.meshgrid(*axes,indexing="ij"),axis=-1).reshape(-1,4)
        weight=np.prod(np.stack(np.meshgrid(*weights,indexing="ij"),axis=-1),axis=-1).ravel()
        for flags in ((0,0,0,1,0,1),(1,0,0,0,1,0),(0,1,1,1,0,1),(0,0,1,0,1,1)):
            a,b,s,sd,f,fd=flags
            policy={"part_tests":[a,b],"semi_tests":[s],"semi_dismantle":[sd],"final_test":f,"final_dismantle":fd}
            quadrature=float(weight@conditional_cost(tree,policy,grid))
            self.assertAlmostEqual(float(evaluate(tree,policy,params)),quadrature,places=7)


if __name__=="__main__":unittest.main()
