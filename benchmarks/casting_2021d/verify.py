"""Independent cell-occupancy network LP, interval checks and a continuous waste bound."""
import argparse
from fractions import Fraction
from pathlib import Path

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix, csr_matrix, vstack

from artifact_io import read_json, write_json, sha256_file


def network_optimum(start, notification, defects, target, lower, upper, scale=10, fixed_end=None):
    """Unit-flow LP on an acyclic graph; edge rewards from a cell scan, not interval recovery."""
    minimum, maximum = int(4.8*scale+.1), int(12.6*scale+.1)
    boundary = fixed_end if fixed_end is not None else max(e for _,e in defects)
    end = boundary if fixed_end is not None else boundary+maximum
    occupied = [any(a<=x<b for a,b in defects) for x in range(start,end)]
    sources, destinations, loss, deviation = [],[],[],[]
    for left in range(start,boundary):
        clean = longest = 0
        for right in range(left+1,min(end,left+maximum)+1):
            clean = 0 if occupied[right-start-1] else clean+1
            longest = max(longest,clean)
            if right-left < minimum or (left==start and right<notification):
                continue
            kept = min(longest,upper) if longest>=lower else 0
            sources.append(left-start); destinations.append(right-start)
            loss.append(right-left-kept)
            deviation.append((kept-target)**2 if kept else 0)
    sink = end-start+1
    terminals = [boundary] if fixed_end is not None else range(boundary,end+1)
    for point in terminals:
        sources.append(point-start); destinations.append(sink); loss.append(0); deviation.append(0)
    columns = np.arange(len(sources))
    matrix = coo_matrix((np.r_[np.ones(len(sources)),-np.ones(len(sources))],
                         (np.r_[sources,destinations],np.r_[columns,columns])),
                        shape=(sink+1,len(sources))).tocsr()
    balance = np.zeros(sink+1); balance[0]=1; balance[sink]=-1
    first = linprog(loss,A_eq=matrix,b_eq=balance,bounds=(0,None),method="highs")
    if not first.success:
        raise ValueError("independent network cannot route material: "+first.message)
    optimum = round(first.fun)
    if abs(first.fun-optimum)>1e-6:
        raise ValueError("nonintegral first objective")
    second = linprog(deviation,A_eq=vstack([matrix,csr_matrix([loss])]),
                     b_eq=np.r_[balance,optimum],bounds=(0,None),method="highs")
    if not second.success or np.max(np.abs(second.x-np.round(second.x)))>1e-6:
        raise ValueError("independent lexicographic network result is not integral")
    return {"loss_tick":optimum,"deviation_tick2":round(second.fun),
            "edges":len(sources),"nodes":sink+1,
            "flow_residual":float(np.max(np.abs(matrix@second.x-balance))),
            "method":"two-stage minimum-cost unit-flow linear program, HiGHS; cell occupancy defines edge recovery"}


def continuous_lower_bound(events, lower, upper, initial=0):
    """Relax transport/cut/causality limits; acceptable products cannot span a defect."""
    f = lambda x:Fraction(str(x))
    intervals = [(f(t)+f(59.6),f(t)+f(60.4)) for t in events]
    merged = []
    for a,b in intervals:
        if merged and a<=merged[-1][1]:
            merged[-1] = (merged[-1][0],max(b,merged[-1][1]))
        else:
            merged.append((a,b))
    cursor = f(initial)
    waste = Fraction(0)
    gaps = []
    for a,b in merged:
        if b<=cursor:
            continue
        if a>cursor:
            length = a-cursor
            count = int(length/f(lower))
            recovered_upper = min(length,count*f(upper))
            gaps.append({"length_m":float(length),"max_products":count,"unavoidable_waste_m":float(length-recovered_upper)})
            waste += length-recovered_upper
        waste += b-max(a,cursor)
        cursor = b
    return {"waste_m":float(waste),"exact_waste":str(waste),"healthy_gaps":gaps,
            "scope":"continuous material bound using the complete realized event sequence, only for retrospective verification; not input to online decisions"}


def verify_trace(record, event_times):
    scale = record["scale"]
    f = lambda x:int(Fraction(str(x))*scale)
    d,lo,hi = [f(record["case"][k]) for k in ("target_m","lower_m","upper_m")]
    all_bad = [(f(t)+f(59.6),f(t)+f(60.4)) for t in event_times]
    cursor = record["initial_boundary"]
    loss = deviation = 0
    for edge in record["executed"]:
        assert edge["start"]==cursor
        assert f(4.8)<=edge["end"]-cursor<=f(12.6)
        assert edge["end"]-cursor>=f(4)  # Cutting + return cycle, in saw-arrival coordinates.
        assert edge["end"]>=edge["planned_at"]
        kept = edge["recovered"]
        recovered = 0
        if kept is not None:
            a,b=kept; recovered=b-a
            assert cursor<=a<b<=edge["end"] and lo<=recovered<=hi
            assert not any(max(a,x)<min(b,y) for x,y in all_bad)
        expected_waste = edge["end"]-cursor-recovered
        expected_deviation = (recovered-d)**2 if recovered else 0
        assert edge["waste"]==expected_waste and edge["deviation"]==expected_deviation
        loss += expected_waste; deviation += expected_deviation
        cursor=edge["end"]
    assert loss/scale==record["total_waste_m"]
    assert deviation/scale**2==record["total_deviation_m2"]
    assert cursor>=max(b for _,b in all_bad)
    # Reconstruct which prior plan decisions became irrevocable before each notification.
    for i,row in enumerate(record["events"]):
        now=f(event_times[i])
        committed=[e for e in record["executed"] if e["end"]<now]
        assert row["committed_piece_count"]==len(committed)
        assert row["locked_boundary"]==(committed[-1]["end"] if committed else record["initial_boundary"])
        assert row["known_events"]==i+1
        expected=[list(x) for x in all_bad[:i+1] if x[1]>row["locked_boundary"]]
        assert row["new_plan"]["defects"]==expected
        assert all(e["end"]>=now for e in row["new_plan"]["pieces"])
        cursor=row["locked_boundary"]; planned_loss=planned_deviation=0
        for piece in row["new_plan"]["pieces"]:
            assert piece["start"]==cursor and f(4.8)<=piece["end"]-cursor<=f(12.6)
            kept=piece["recovered"]; size=0
            if kept:
                a,b=kept;size=b-a
                assert cursor<=a<b<=piece["end"] and lo<=size<=hi
                assert not any(max(a,x)<min(b,y) for x,y in expected)
            assert piece["waste"]==piece["end"]-cursor-size
            assert piece["deviation"]==((size-d)**2 if size else 0)
            planned_loss+=piece["waste"];planned_deviation+=piece["deviation"];cursor=piece["end"]
        assert row["new_plan"]["score"]==[planned_loss,planned_deviation,len(row["new_plan"]["pieces"])]
        assert row["new_plan"]["terminal"]==cursor>=max(b for _,b in expected)
        if i:
            previous=record["events"][i-1]["new_plan"]["pieces"]
            fixed=[e for e in previous if e["end"]<now]
            actual=[e for e in committed if e["start"]>=record["events"][i-1]["locked_boundary"]]
            assert [(e["start"],e["end"],e["recovered"]) for e in fixed]==[(e["start"],e["end"],e["recovered"]) for e in actual[:len(fixed)]]
    return {"passed":True,"pieces":len(record["executed"]),"total_waste_m":loss/scale,
            "checks":["mass balance","primary transport bounds","cut/return spacing","defect-free recovery","target bounds","no retroactive cut","known-event prefix","irrevocable prior cuts"]}


def verify(run):
    if not __debug__:
        raise ValueError("Verification requires Python assertions; do not use -O or PYTHONOPTIMIZE")
    facts=read_json(run/"artifacts/facts.json")
    solution=read_json(run/"artifacts/solution.json")
    if solution["facts_sha256"]!=sha256_file(run/"artifacts/facts.json"):
        raise ValueError("input facts changed")
    report={"solution_sha256":sha256_file(run/"artifacts/solution.json"),"tails":[],"online":{},"passed":True}
    for row in solution["tails"]:
        p=list(map(Fraction,row["exact"]["primary"]))
        r=list(map(Fraction,row["exact"]["recovered"]))
        assert sum(p)==Fraction(str(row["tail_m"]))
        assert all(Fraction("4.8")<=v<=Fraction("12.6") for v in p)
        assert all(v==0 or 9<=v<=10 for v in r)
        assert all(x<=y for x,y in zip(r,p))
        assert sum(p)-sum(r)==Fraction(row["exact"]["waste"])
        assert sum((v-Fraction("9.5"))**2 for v in r if v)==Fraction(row["exact"]["squared_deviation"])
        network=network_optimum(0,0,[],95,90,100,fixed_end=round(row["tail_m"]*10))
        assert abs(network["loss_tick"]/10-row["waste_m"])<1e-8
        report["tails"].append({"tail_m":row["tail_m"],"waste_m":network["loss_tick"]/10,
                                "loss_agreement":True,"network":network,
                                "secondary_scope":"rational allocation checked algebraically; network secondary cost is grid-restricted, not the continuous Q1 objective"})
    for name,record in solution["online"].items():
        checked=verify_trace(record,facts["event_times_min"])
        references=[]
        case=record["case"]
        target,lower,upper=[round(case[k]*10) for k in ("target_m","lower_m","upper_m")]
        for row in record["events"]:
            p=row["new_plan"]
            network=network_optimum(p["start"],p["notification"],p["defects"],target,lower,upper)
            assert network["loss_tick"]==p["score"][0]
            assert network["deviation_tick2"]==p["score"][1]
            references.append({"event":row["event"],"passed":True,**network})
        bound=continuous_lower_bound(facts["event_times_min"],case["lower_m"],case["upper_m"])
        bound["attained"]=Fraction(str(record["total_waste_m"]))==Fraction(bound["exact_waste"])
        report["online"][name]={"trace":checked,"network_comparisons":references,"continuous_lower_bound":bound}
        print(name,"LP matches all 9 event objectives; continuous waste bound",bound["waste_m"],"attained",bound["attained"],flush=True)
    write_json(run/"artifacts/independent.json",report)
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run",type=Path)
    verify(parser.parse_args().run)
