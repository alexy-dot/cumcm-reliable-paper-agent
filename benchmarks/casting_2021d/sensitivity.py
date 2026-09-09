"""Grid refinement, initial phase, and a fixed-target cutting baseline."""
import argparse
from pathlib import Path
from solve import online, recover
from verify import verify_trace, continuous_lower_bound
from engine import read_json, write_json, sha256_file


def assess(run):
    facts=read_json(run/"artifacts/facts.json")
    primary=read_json(run/"artifacts/solution.json")
    records={}
    for name,case in facts["cases"].items():
        events=facts["event_times_min"]
        fine=online(events,case,scale=20)
        fine_trace=verify_trace(fine,events)
        d,lo,hi=[round(case[k]*10) for k in ("target_m","lower_m","upper_m")]
        defects=[(round(t*10)+596,round(t*10)+604) for t in events]
        anchor=0; baseline=[]
        while anchor<defects[-1][1]:
            # Cut positions are completely independent of defects; offline recovery occurs afterward.
            baseline.append(recover(anchor,anchor+d,defects,lo,hi,d))
            anchor+=d
        shifted=online(events,case,scale=20,initial_boundary=-d)
        shifted_trace=verify_trace(shifted,events)
        shifted_bound=continuous_lower_bound(events,case["lower_m"],case["upper_m"],initial=-d/20)
        records[name]={"nominal_waste_m":primary["online"][name]["total_waste_m"],
                       "fixed_target_baseline_waste_m":sum(e["waste"] for e in baseline)/10,
                       "fine_grid":{"step_m":.05,"waste_m":fine["total_waste_m"],
                                    "deviation_m2":fine["total_deviation_m2"],"trace":fine_trace},
                       "half_target_initial_phase":{"initial_boundary_m":-d/20,
                                    "waste_m":shifted["total_waste_m"],"trace":shifted_trace,"lower_bound":shifted_bound},
                       "nominal_deviation_m2":primary["online"][name]["total_deviation_m2"]}
        print(name,records[name],flush=True)
    output={"solution_sha256":sha256_file(run/"artifacts/solution.json"),"cases":records,
            "scope":"grid refinement and one initial-phase alternative; no uniform guarantee over all phases or events"}
    write_json(run/"artifacts/sensitivity.json",output)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run",type=Path)
    assess(parser.parse_args().run)
