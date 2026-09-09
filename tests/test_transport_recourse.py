import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"skill/cumcm-reliable-paper/scripts"))
try:
    from transport_recourse import reallocate, inventory_step
except ImportError:
    reallocate=None


@unittest.skipIf(reallocate is None,"optional NumPy/SciPy unavailable")
class RecourseTest(unittest.TestCase):
    def test_overdelivery_moves_to_spare_carrier_and_preserves_all_goods(self):
        r=reallocate([12],[10,10],[0,.1],[1],required_receipt=10,reference=[[12,0]])
        self.assertEqual(r["status"],"FEASIBLE")
        self.assertAlmostEqual(r["shipments"][0][0],10)
        self.assertAlmostEqual(r["shipments"][0][1],2)
        self.assertAlmostEqual(r["raw_loss"],.2)
        self.assertAlmostEqual(r["changed_raw_quantity"],2)

    def test_product_shortfall_is_not_hidden_by_all_raw_goods_dispatched(self):
        r=reallocate([4,4],[4,4],[0,.5],[.5,1],required_receipt=11)
        self.assertEqual(r["status"],"TARGET_SHORTFALL")
        self.assertTrue(r["all_supply_dispatched"])
        self.assertAlmostEqual(r["maximum_product_receipt"],10)
        self.assertAlmostEqual(r["receipt_shortfall"],1,delta=1.1*r["objective_tolerance"])

    def test_insufficient_total_capacity_does_not_discard_or_invent_transport(self):
        r=reallocate([13],[5,5],[0,0],[1],required_receipt=10)
        self.assertEqual(r["status"],"TRANSPORT_CAPACITY_SHORTFALL")
        self.assertIsNone(r["shipments"])
        self.assertEqual(r["minimum_extra_raw_capacity"],3)
        self.assertEqual(r["purchased_raw_quantity"],13)

    def test_equal_optima_keep_feasible_reference(self):
        reference=[[3,2],[1,4]]
        r=reallocate([5,5],[6,6],[.1,.1],[1,1],reference=reference)
        self.assertAlmostEqual(r["changed_raw_quantity"],0)

    def test_stock_cannot_be_negative_and_unmet_demand_is_explicit(self):
        self.assertEqual(inventory_step(2,3,8,4),{"produced":5,"unmet_production":3,"ending_inventory":0,"reserve_shortfall":4})

    def test_zero_supply_and_invalid_loss_units(self):
        self.assertEqual(reallocate([0],[10],[0],[1],required_receipt=1)["receipt_shortfall"],1)
        with self.assertRaises(ValueError):reallocate([1],[10],[5],[1])
