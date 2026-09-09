"""Read exported official templates and independently reconcile every submitted cell."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from openpyxl import load_workbook
from prepare import write


def check(run):
    p=json.loads((run/"artifacts/plans.json").read_text());reports=[]
    for tag in "AB":
        original=next((run/"sources").glob("*附件"+tag+"*"))
        name=original.name[original.name.index("附件"):]
        result=run/"artifacts/submission"/name
        source=load_workbook(original,data_only=False);out=load_workbook(result,data_only=False)
        assert source.sheetnames==out.sheetnames
        for q,(before,after) in enumerate(zip(source,out),2):
            width=24 if tag=="A" else 192
            expected=np.array(p["Q"+str(q)]["orders"]).T if tag=="A" else np.array(p["Q"+str(q)]["shipments"]).transpose(1,0,2).reshape(402,192)
            actual=np.zeros_like(expected);bad_type=[];changed=[]
            for row in after.iter_rows(min_row=7,max_row=408,min_col=2,max_col=width+1):
                for c in row:
                    if c.value is not None:
                        if c.data_type!="n":bad_type.append(c.coordinate)
                        actual[c.row-7,c.column-2]=float(c.value)
            for row in before.iter_rows():
                for c in row:
                    if 7<=c.row<=408 and 2<=c.column<=width+1:continue
                    v=after.cell(c.row,c.column).value
                    # Export may normalize formula casing; formulas remain formulas.
                    if v!=c.value:changed.append({"cell":c.coordinate,"before":c.value,"after":v})
            merges_ok=sorted(map(str,before.merged_cells.ranges))==sorted(map(str,after.merged_cells.ranges))
            record={"workbook":name,"sheet":after.title,"numeric_cells":int(np.count_nonzero(actual)),
                    "max_numeric_error":float(np.max(np.abs(expected-actual))),"non_numeric_output_cells":bad_type,
                    "changed_existing_information":changed,"merged_ranges_preserved":merges_ok,
                    "blank_zero_outputs":all(after.cell(i+7,j+2).value is None for i,j in zip(*np.nonzero(expected<=1e-8)))}
            record["passed"]=record["max_numeric_error"]<1e-7 and not bad_type and not changed and merges_ok and record["blank_zero_outputs"]
            reports.append(record)
        source.close();out.close()
    report={"passed":all(r["passed"] for r in reports),"sheets":reports,
            "workbook_sha256":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (run/"artifacts/submission").glob("*.xlsx")},
            "plans_sha256":hashlib.sha256((run/"artifacts/plans.json").read_bytes()).hexdigest()}
    write(run/"artifacts/workbook-verification.json",report)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if not report["passed"]:raise ValueError("exported templates differ from verified plan or source information")


if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("run",type=Path);check(ap.parse_args().run)
