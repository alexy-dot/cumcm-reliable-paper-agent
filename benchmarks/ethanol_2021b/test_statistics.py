"""Behavioral counterexamples for grouped prediction and dependent descriptors."""
import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"skill/cumcm-reliable-paper/scripts"))
from grouped_regression import evaluate_grouped,group_splits,validate_splits,permute_group_descriptors
from prepare import parse_formula


class GroupedStatisticsTest(unittest.TestCase):
    def test_mean_baseline_never_reads_heldout_targets(self):
        groups=np.repeat(np.arange(6),2);x=np.arange(12.)[:,None];y=np.repeat([0.,2,4,6,8,100],2)
        splits=group_splits(groups,3)
        families={"mean":[{"name":"mean","kind":"mean"}]}
        result=evaluate_grouped(x,y,groups,families,splits=splits)
        predicted=np.array(result["models"]["mean"]["prediction"])
        for train,test in splits:np.testing.assert_allclose(predicted[test],y[train].mean())
        self.assertFalse(np.allclose(predicted,y.mean()))

    def test_changing_outer_test_outcomes_does_not_change_that_fold_selection(self):
        groups=np.repeat(np.arange(8),3);x=np.linspace(-2,2,24)[:,None];y=2+x[:,0]**2
        specs=[{"name":str(a),"kind":"polynomial","degree":2,"alpha":a,"columns":[0]} for a in (1.,100.)]
        splits=group_splits(groups,4)
        one=evaluate_grouped(x,y,groups,{"ridge":specs},splits=splits,inner_folds=3)
        altered=y.copy();test=splits[0][1];altered[test]+=1000
        two=evaluate_grouped(x,altered,groups,{"ridge":specs},splits=splits,inner_folds=3)
        self.assertEqual(one["models"]["ridge"]["selection"][0],two["models"]["ridge"]["selection"][0])
        np.testing.assert_array_equal(np.array(one["models"]["ridge"]["prediction"])[test],np.array(two["models"]["ridge"]["prediction"])[test])

    def test_group_leakage_and_incomplete_coverage_are_rejected(self):
        with self.assertRaisesRegex(ValueError,"same independent group"):
            validate_splits(np.array(["a","a","b","b"]),[(np.array([0,2]),np.array([1,3])),(np.array([1,3]),np.array([0,2]))])
        with self.assertRaisesRegex(ValueError,"exactly once"):
            validate_splits(np.array(["a","b","c"]),[(np.array([0,1]),np.array([2]))])
        with self.assertRaisesRegex(ValueError,"integers"):
            validate_splits(np.array(["a","b"]),[(np.array([0.5]),np.array([1.]))])
        with self.assertRaisesRegex(ValueError,"present and finite"):
            group_splits(["a",None,"b"],2)

    def test_group_descriptor_exchange_preserves_mass_and_ratio(self):
        groups=np.repeat(["a","b","c"],2)
        x=np.array([[t,a,b,a+b,a/(a+b)] for a,b in [(1.,2.),(3.,1.),(2.,5.)] for t in (250,300)])
        out,mapping=permute_group_descriptors(x,groups,[1,2,3,4],19)
        np.testing.assert_array_equal(out[:,0],x[:,0])
        np.testing.assert_allclose(out[:,1]+out[:,2],out[:,3])
        np.testing.assert_allclose(out[:,1]/out[:,3],out[:,4])
        for g in np.unique(groups):
            np.testing.assert_array_equal(out[groups==g,1:],x[groups==mapping[g],1:])
        with self.assertRaisesRegex(ValueError,"group-constant"):
            permute_group_descriptors(x,groups,[0,1],19)

    def test_explicit_no_hap_and_quartz_are_not_lost(self):
        row=parse_formula("50mg1wt%Co/SiO2+90mg石英砂-乙醇浓度1.68ml/min，无HAP")
        self.assertEqual(row["hap_mass_mg"],0)
        self.assertEqual(row["quartz_mass_mg"],90)
        with self.assertRaises(ValueError):parse_formula("50mg1wt%Co/SiO2-乙醇浓度1.68ml/min")

    def test_strict_temperature_limit_has_supremum_not_fake_grid_maximum(self):
        from decision import polynomial_maximum
        result=polynomial_maximum([1.,0.],0,1,250,350,True)
        self.assertEqual(result["kind"],"supremum_not_attained")
        self.assertEqual(result["temperature_c"],350)
        self.assertFalse(result["attained"])
        interior=polynomial_maximum([-1.,650.,0.],0,1,250,350,True)
        self.assertTrue(interior["attained"])
        self.assertAlmostEqual(interior["temperature_c"],325)
        constant=polynomial_maximum([0.,3.],0,1,250,350,True)
        self.assertTrue(constant["attained"])
        self.assertEqual(constant["temperature_c"],250)


if __name__=="__main__":unittest.main()
