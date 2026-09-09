import unittest
from itertools import combinations

from verify import greedy_capacity
from verify_contingency import bound_for_count


class SupplierCountBoundTest(unittest.TestCase):
    def test_type_count_upper_bound_matches_all_supplier_subsets(self):
        f={"ids":["A1","A2","B1","B2","C1"],"kinds":["A","A","B","B","C"],
           "supply_cap":[12000,8000,16000,4000,20000],"carrier_mean_loss":[.01,.02,.03,.04,.05,.06,.07,.08]}
        for count in (1,2,3):
            expected=max(greedy_capacity([f["supply_cap"][i] if i in indices else 0 for i in range(5)],
                                         [.6,.6,.66,.66,.72],f["carrier_mean_loss"])[0]
                         for indices in combinations([0,1,2,4],count))
            self.assertAlmostEqual(bound_for_count(f,"B2",count)["maximum_product_output"],expected,places=7)


if __name__=="__main__":unittest.main()
