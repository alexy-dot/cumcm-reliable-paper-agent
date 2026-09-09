"""Freeze the original problem and the explicitly scoped Q1/Q2 evaluation protocol."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"skill/cumcm-reliable-paper/scripts"))
from engine import initialize_run,read_json,write_json,sha256_file

SOURCE_HASH="f54529dd15d729b046e248ea41033b4f66ef68333be2bee912b0c54eafd227ab"


def prepare(source,output):
    if sha256_file(source)!=SOURCE_HASH:raise ValueError("source differs from the reviewed two-page problem")
    initialize_run(output,source,[],"2024 B 生产决策：概率与返工研究","production-2024b")
    # Table 1, original page 1; defect rates at assembly are conditional on good inputs.
    raw=[(.1,2,.1,3,.1,3,6,5),(.2,2,.2,3,.2,3,6,5),(.1,2,.1,3,.1,3,30,5),
         (.2,1,.2,1,.2,2,30,5),(.1,8,.2,1,.1,2,10,5),(.05,2,.05,3,.05,3,10,40)]
    cases=[{"case":i+1,"p1":r[0],"inspect1":r[1],"p2":r[2],"inspect2":r[3],"assembly_defect":r[4],
            "inspect_final":r[5],"replacement_loss":r[6],"disassembly":r[7],"purchase1":4,"purchase2":18,"assembly":6,"price":56} for i,r in enumerate(raw)]
    facts={"source_sha256":SOURCE_HASH,"cases":cases,"sampling":{"nominal_rate":.1,"reject_error":.05,"accept_error":.1,"cap":300},
           "interpretations":["independent Bernoulli purchase defects, large lot; inspections perfect and do not damage good items",
             "assembly failures are independent per attempt conditional on all inputs good, exactly as original appendix defines",
             "quality of reused components is persistent; perfect prior inspection knowledge is retained",
             "one customer pays price once; replacement until a good product arrives is free, with additional loss for each delivered defective product",
             "compare stationary policies: fresh component inspections, recovered unknown-component inspections, final inspection, and disassembly; known-good components need not be re-tested",
             "no holding, time, capacity, salvage or inspection damage costs supplied; expected profit per fulfilled order is the chosen objective"],
           "scope":"Q1/Q2 development only; Q3 multi-stage production and Q4 sampled-rate propagation are not yet solved; previously studied historical topic, not a blind trial"}
    write_json(output/"artifacts/facts.json",facts)
    write_json(output/"artifacts/protocol.json",{"facts_sha256":sha256_file(output/"artifacts/facts.json"),
        "sampling":"directional uniform-mixture likelihood-ratio martingales; stop at E_reject>=20 or E_accept>=10; unresolved at 300 remains unresolved",
        "policy_bits":["inspect_fresh_1","inspect_fresh_2","inspect_recovered_1","inspect_recovered_2","inspect_final","disassemble"],
        "verification":{"simulation_orders_per_case":50000,"simulation_seed":20240906,"cost_agreement":"absolute mean error <= 6*sample_standard_error + 0.02 yuan; numerical check, not inference of real process risk"},
        "scope":facts["scope"]})
    print({"run":str(output),"source_sha256":SOURCE_HASH},flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    args=p.parse_args();prepare(args.source,args.output)
