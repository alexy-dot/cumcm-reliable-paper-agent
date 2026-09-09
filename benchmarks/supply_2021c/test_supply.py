import unittest
from itertools import combinations

import numpy as np
from solve import capacity,count_suppliers
from verify import greedy_capacity
from prepare import rates


class SupplyModelTest(unittest.TestCase):
    def fixture(self,cap):
        return {"supply_cap":cap,"conversion":[.6,.66,.72],"price":[1.2,1.1,1.],
                "carrier_mean_loss":[.01,.02,.03,.04,.05,.06,.07,.08]}

    def test_capacity_matches_independent_exchange_construction_with_transport_bottleneck(self):
        f=self.fixture([20000,20000,20000])
        actual,_,_=capacity(f);reference,_=greedy_capacity(f["supply_cap"],f["conversion"],f["carrier_mean_loss"])
        self.assertAlmostEqual(actual,reference,places=7)

    def test_supplier_minimum_matches_exhaustive_small_case(self):
        f=self.fixture([4,5,3]);demand=10.
        x,proof=count_suppliers(f,demand)
        brute=None
        for n in range(1,4):
            for ids in combinations(range(3),n):
                cap=[f["supply_cap"][i] if i in ids else 0 for i in range(3)]
                if greedy_capacity(cap,f["conversion"],f["carrier_mean_loss"])[0]>=demand:
                    brute=n;break
            if brute:break
        self.assertEqual(proof["minimum_supplier_count"],brute)

    def test_ratio_mean_includes_failed_order_weeks(self):
        o=np.array([[10.,10.,0.]])
        s=np.array([[10.,0.,0.]])
        self.assertEqual(rates(o,s,"volume_ratio")[0],.5)


if __name__=="__main__":unittest.main()
