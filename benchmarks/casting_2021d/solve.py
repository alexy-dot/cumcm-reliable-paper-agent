"""Exact continuous tail enumeration and causal grid-optimal primary-cut planning."""
import argparse
import csv
from fractions import Fraction
from pathlib import Path
from time import perf_counter

from artifact_io import read_json, write_json, sha256_file


def exact_tail(length, target=9.5, lower=9., upper=10.):
    total, d, lo, hi = map(lambda x: Fraction(str(x)), (length,target,lower,upper))
    a, b = Fraction("4.8"), Fraction("12.6")
    best = None
    for count in range(1, int(total/a)+1):
        for good in range(count+1):
            scrap = count-good
            if not good*lo+scrap*a <= total <= count*b:
                continue
            recovered = min(good*hi, total-scrap*a)
            if recovered < good*lo:
                continue
            deviation = good*(recovered/good-d)**2 if good else Fraction(0)
            score = (total-recovered, deviation, count, scrap)
            if best is None or score < best[0]:
                best = score, good, scrap, recovered
    if best is None:
        raise ValueError("tail cannot be partitioned into transportable primary pieces")
    score, good, scrap, recovered = best
    mean = recovered/good if good else Fraction(0)
    accepted = [mean]*good + [Fraction(0)]*scrap
    primary = [mean]*good + [a]*scrap
    extra = total-sum(primary)
    for i in range(len(primary)):
        addition = min(extra,b-primary[i])
        primary[i] += addition
        extra -= addition
    assert extra == 0 and sum(primary) == total
    return {"tail_m":float(total), "primary_m":list(map(float,primary)),
            "recovered_m":list(map(float,accepted)), "waste_m":float(score[0]),
            "squared_deviation_m2":float(score[1]), "accepted_count":good,
            "exact": {"primary":list(map(str,primary)), "recovered":list(map(str,accepted)),
                      "waste":str(score[0]), "squared_deviation":str(score[1])}}


def recover(left, right, defects, lower, upper, target):
    """At most one accepted product fits: primary max 12.6 < 2*8.0 m."""
    cursor = left
    longest = (left,left)
    for begin,end in defects:
        if end <= left or begin >= right:
            continue
        gap = (cursor,min(begin,right))
        if gap[1]-gap[0] > longest[1]-longest[0]:
            longest = gap
        cursor = max(cursor,min(end,right))
    if right-cursor > longest[1]-longest[0]:
        longest = (cursor,right)
    size = min(upper,longest[1]-longest[0]) if longest[1]-longest[0] >= lower else 0
    kept = [longest[0],longest[0]+size] if size else None
    return {"start":left, "end":right, "recovered":kept,
            "waste":right-left-size, "deviation":(size-target)**2 if size else 0}


def plan(start, notification, defects, target, lower, upper, scale=10):
    """Shortest lexicographic path to the first cut beyond all known defects."""
    a, b = 48*scale//10, 126*scale//10
    last_bad = max(end for _,end in defects)
    limit = last_bad+b
    cost = {start:(0,0,0)}
    predecessor = {}
    evaluated = 0
    for left in range(start,last_bad):
        if left not in cost:
            continue
        for right in range(max(left+a,notification if left==start else left+a), min(left+b,limit)+1):
            edge = recover(left,right,defects,lower,upper,target)
            evaluated += 1
            score = (cost[left][0]+edge["waste"], cost[left][1]+edge["deviation"], cost[left][2]+1)
            if right not in cost or score < cost[right]:
                cost[right] = score
                predecessor[right] = (left,edge)
    terminals = [end for end in cost if end>=last_bad]
    if not terminals:
        raise ValueError("no causal transport-feasible plan")
    finish = min(terminals,key=lambda x:(*cost[x],x))
    edges = []
    cursor = finish
    while cursor != start:
        cursor,edge = predecessor[cursor]
        edges.append(edge)
    edges.reverse()
    return {"start":start, "notification":notification, "defects":[list(x) for x in defects],
            "terminal":finish, "score":list(cost[finish]), "pieces":edges,
            "grid_scale_per_m":scale, "evaluated_edges":evaluated,
            "optimality":"exact lexicographic optimum of the declared finite grid graph; continuous/global online optimality not implied"}


def online(event_times, case, scale=10, initial_boundary=0):
    if scale not in (10,20):
        raise ValueError("this benchmark supports exact 0.1 or 0.05 m grids")
    def ticks(x):
        value=Fraction(str(x))*scale
        if value.denominator!=1:
            raise ValueError("input is not exactly representable on the declared grid")
        return int(value)
    target,lower,upper = [ticks(case[key]) for key in ("target_m","lower_m","upper_m")]
    executed = []
    pending = []
    known = []
    history = []
    anchor = initial_boundary
    for index,time in enumerate(event_times):
        now = ticks(time)
        while pending and pending[0]["end"] < now:
            piece = pending.pop(0)
            executed.append(piece)
            anchor = piece["end"]
        # Healthy continuation after a former finite plan, without future events.
        while not pending and anchor+target < now:
            edge = recover(anchor,anchor+target,known,lower,upper,target)
            edge.update(planned_at=history[-1]["time_tick"] if history else initial_boundary,
                        known_event_count=index)
            executed.append(edge)
            anchor = edge["end"]
        before = [dict(edge) for edge in pending]
        known.append((now+ticks(59.6),now+ticks(60.4)))
        future = [interval for interval in known if interval[1]>anchor]
        started = perf_counter()
        chosen = plan(anchor,now,future,target,lower,upper,scale)
        elapsed = perf_counter()-started
        pending = [dict(edge,planned_at=now,known_event_count=index+1) for edge in chosen["pieces"]]
        history.append({"event":index+1,"time_tick":now,"known_events":index+1,
                        "locked_boundary":anchor,"committed_piece_count":len(executed),
                        "cut_in_progress":anchor<=now<anchor+3*scale,
                        "previous_pending":before,"new_plan":chosen,"planning_seconds":elapsed,
                        "current_next_cut_changed":None if not before else before[0]["end"]!=pending[0]["end"],
                        "committed_waste":sum(edge["waste"] for edge in executed),
                        "projected_total_waste":sum(edge["waste"] for edge in executed)+chosen["score"][0]})
    executed.extend(pending)
    return {"case":case,"scale":scale,"initial_boundary":initial_boundary,
            "events":history,"executed":executed,
            "total_waste_m":sum(edge["waste"] for edge in executed)/scale,
            "total_deviation_m2":sum(edge["deviation"] for edge in executed)/scale**2,
            "last_cut_start_min":executed[-1]["end"]/scale if executed else initial_boundary/scale,
            "last_cut_complete_min":executed[-1]["end"]/scale+3 if executed else initial_boundary/scale+3,
            "scope":"optimal current-known-defect plans on a 0.1/0.05 m grid; realized final record follows causal revisions"}


def solve(run):
    facts_path = run/"artifacts/facts.json"
    facts = read_json(facts_path)
    tails = [exact_tail(value) for value in facts["tail_lengths_m"]]
    result = {"facts_sha256":sha256_file(facts_path), "tails":tails, "online":{}}
    for key,case in facts["cases"].items():
        result["online"][key] = online(facts["event_times_min"],case)
        print(key, {"waste_m":result["online"][key]["total_waste_m"],
                    "event_seconds":[round(row["planning_seconds"],3) for row in result["online"][key]["events"]]},flush=True)
    write_json(run/"artifacts/solution.json",result)
    with (run/"artifacts/event_plans.csv").open("w",encoding="utf-8-sig",newline="") as stream:
        writer=csv.writer(stream)
        writer.writerow(["case","notification_min","plan","primary_start_m","primary_end_m",
                         "sever_cut_start_min","sever_cut_complete_min","machine_return_min",
                         "retained_start_m","retained_end_m","waste_m"])
        for key,record in result["online"].items():
            for row in record["events"]:
                for kind,pieces in [("previous",row["previous_pending"]),("new",row["new_plan"]["pieces"])]:
                    for piece in pieces:
                        kept=piece["recovered"]
                        writer.writerow([key,row["time_tick"]/10,kind,piece["start"]/10,piece["end"]/10,
                                         piece["end"]/10,piece["end"]/10+3,piece["end"]/10+4,
                                         kept[0]/10 if kept else "",kept[1]/10 if kept else "",piece["waste"]/10])
    print("tails",[(r["tail_m"],r["waste_m"]) for r in tails],flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run",type=Path)
    solve(parser.parse_args().run)
