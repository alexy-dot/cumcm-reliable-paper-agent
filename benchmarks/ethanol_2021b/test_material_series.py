"""Joint mass changes must not be mistaken for a single unconstrained material effect."""
import unittest
from copy import deepcopy
from types import SimpleNamespace
from decision import material_series
from verify import verify_material_series


def observations(group,co,hap,temperatures=(250,350),feed=1.68,quartz=0):
    return [{"group":group,"co_mass_mg":co,"hap_mass_mg":hap,"quartz_mass_mg":quartz,
             "co_loading_pct":1.,"feed_ml_min":feed,"mode_II":0,"source_row":i+2,
             "temperature_c":t,"conversion_pct":10.,"selectivity_pct":20.,"yield_pct":2.}
            for i,t in enumerate(temperatures)]


class MaterialSeriesTest(unittest.TestCase):
    def test_equal_ratio_mass_series_and_equal_total_ratio_series(self):
        rows=observations("A",50,50)+observations("B",200,200)+observations("C",33,67)
        result=material_series(rows)
        mass=next(r for r in result if r["factor"]=="total_mass_mg")
        ratio=next(r for r in result if r["factor"]=="co_mass_fraction")
        self.assertEqual([p["group"] for p in mass["points"]],["A","B"])
        self.assertEqual(mass["fixed_exact"],"1/2")
        self.assertEqual([p["group"] for p in ratio["points"]],["C","A"])
        self.assertEqual(ratio["fixed_value"],100)

    def test_feed_and_quartz_changes_are_not_controlled_mass_effects(self):
        rows=observations("A",50,50)+observations("B",200,200,feed=.9)+observations("C",100,100,quartz=10)
        self.assertEqual(material_series(rows),[])

    def test_only_common_measured_temperatures_are_used(self):
        rows=observations("A",50,50,(250,300,350))+observations("B",200,200,(250,325,350))
        result=material_series(rows)[0]
        self.assertEqual(result["common_temperatures"],[250,350])
        self.assertTrue(all(len(p["observations"])==2 for p in result["points"]))

    def test_no_hap_and_changing_group_formulation_are_not_silently_matched(self):
        self.assertEqual(material_series(observations("A",50,0)+observations("B",100,0)),[])
        rows=observations("A",50,50)+observations("B",200,200)
        rows[1]["hap_mass_mg"]=51
        with self.assertRaises(ValueError):material_series(rows)

    def test_independent_source_check_rejects_omission_and_wrong_response(self):
        rows=[]
        for group,co,hap,feed,mode in [("A1",50,50,1.68,0),("A2",200,200,1.68,0),
                ("A3",33,67,1.68,0),("A4",50,50,.9,0),("A5",200,200,.9,0),
                ("B1",10,10,1.68,1),("B2",50,50,1.68,1)]:
            for row in observations(group,co,hap,feed=feed):
                row["mode_II"]=mode;row["source_row"]=len(rows)+2;rows.append(row)
        raw=[(r["group"],f"{r['co_mass_mg']}mg1wt%Co/SiO2-{r['hap_mass_mg']}mgHAP-乙醇浓度{r['feed_ml_min']}ml/min",
              r["temperature_c"],r["conversion_pct"],0,r["selectivity_pct"]) for r in rows]
        workbook={"性能数据表":SimpleNamespace(iter_rows=lambda **kw:iter(raw))}
        series=material_series(rows)
        self.assertEqual(len(series),4)
        self.assertTrue(verify_material_series(workbook,series)["passed"])
        broken=deepcopy(series);broken[0]["points"].pop()
        with self.assertRaises(ValueError):verify_material_series(workbook,broken)
        broken=deepcopy(series);broken[0]["points"][0]["observations"][0]["yield_pct"]+=.1
        with self.assertRaises(ValueError):verify_material_series(workbook,broken)


if __name__=="__main__":unittest.main()
