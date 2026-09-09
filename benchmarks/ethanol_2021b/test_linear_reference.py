"""Independent fit checks on known solutions, degenerate designs and corrupted predictions."""
import unittest
from copy import deepcopy
import numpy as np
from prepare import PROJECT  # Adds Skill scripts to import path.
from polynomial_reference import expand,predict_reference
from grouped_regression import evaluate_grouped
from verify_linear_models import compare_models


class LinearReferenceTest(unittest.TestCase):
    def test_closed_form_ridge_has_unpenalized_intercept(self):
        x=np.array([[-1.],[1.]])
        prediction,_=predict_reference(x,[8.,12.],[[-1.],[0.],[1.]],alpha=2.)
        np.testing.assert_allclose(prediction,[9.,10.,11.],atol=1e-12)

    def test_explicit_polynomial_expansion_includes_all_cross_terms(self):
        np.testing.assert_array_equal(expand([[2.,3.]],2),[[2.,3.,4.,6.,9.]])

    def test_rank_deficiency_constant_columns_and_training_only_scaling(self):
        x=np.array([[t,2*t,4.] for t in range(6)])
        y=3+2*x[:,0]
        prediction,info=predict_reference(x,y,[[6.,12.,4.]],alpha=0.)
        np.testing.assert_allclose(prediction,[15.],atol=1e-10)
        self.assertEqual(info["constant_columns"],1)
        combined,_=predict_reference(x,y,[[6.,12.,4.],[1000.,2000.,4.]],alpha=0.)
        np.testing.assert_allclose(combined[:1],prediction,atol=1e-10)

    def test_reproduces_training_pipeline_and_catches_tampered_raw_predictions(self):
        groups=np.repeat(np.arange(6),3)
        x=np.array([[t,group%2] for group in range(6) for t in (250.,300.,350.)])
        y=20+.02*(x[:,0]-280)+3*x[:,1]
        families={"temperature_only":[{"name":"t","kind":"polynomial","degree":2,"columns":[0]}],
                  "ridge":[{"name":"r","kind":"polynomial","degree":2,"alpha":10.,"columns":[0,1]}]}
        output=evaluate_grouped(x,y,groups,families,outer_folds=3,bounds=(0,100))
        rows=[{"group":str(g),"t":a,"mode":b,**{k:v for k in ("conversion_pct","selectivity_pct","yield_pct")}}
              for (a,b),g,v in zip(x,groups,y)]
        observations={"rows":rows,"features":["t","mode"]}
        result={"targets":{k:deepcopy(output) for k in ("conversion_pct","selectivity_pct","yield_pct")}}
        self.assertTrue(all(c["passed"] for c in compare_models(observations,result)))
        result["targets"]["conversion_pct"]["models"]["ridge"]["raw_prediction"][0]+=1.
        self.assertFalse(all(c["passed"] for c in compare_models(observations,result)))

    def test_invalid_penalty_or_nonfinite_input_is_rejected(self):
        for alpha in (-1.,float("nan")):
            with self.assertRaises(ValueError):predict_reference([[0.],[1.]],[1.,2.],[[2.]],alpha=alpha)
        with self.assertRaises(ValueError):expand([[float("inf")]],2)


if __name__=="__main__":unittest.main()
