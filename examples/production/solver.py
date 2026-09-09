"""Standalone reproducible synthetic production model; standard library only."""
import argparse
import csv
import itertools
import json
from functools import lru_cache
from pathlib import Path


def enumerate_plans(products, hours, material):
    bounds = [min(hours // p["hours"], material // p["material"]) for p in products]
    best = -1
    optima = []
    feasible = 0
    for quantities in itertools.product(*(range(bound + 1) for bound in bounds)):
        used_h = sum(q * p["hours"] for q, p in zip(quantities, products))
        used_m = sum(q * p["material"] for q, p in zip(quantities, products))
        if used_h > hours or used_m > material:
            continue
        feasible += 1
        profit = sum(q * p["profit"] for q, p in zip(quantities, products))
        if profit > best:
            best, optima = profit, [list(quantities)]
        elif profit == best:
            optima.append(list(quantities))
    quantities = optima[0]
    return {"profit": best, "quantities": quantities, "optima": optima,
            "feasible_plans": feasible,
            "hours_slack": hours - sum(q * p["hours"] for q, p in zip(quantities, products)),
            "material_slack": material - sum(q * p["material"] for q, p in zip(quantities, products))}


def dynamic_profit(products, hours, material):
    # Independent state recurrence; no use of enumeration bounds or chosen plan.
    @lru_cache(None)
    def value(h, m):
        options = [0]
        for product in products:
            if h >= product["hours"] and m >= product["material"]:
                options.append(product["profit"] + value(h - product["hours"], m - product["material"]))
        return max(options)
    return value(hours, material)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(__file__).with_name("products.csv"))
    parser.add_argument("--output", type=Path, default=Path("reproduced.json"))
    args = parser.parse_args()
    with args.data.open(encoding="utf-8", newline="") as stream:
        products = [{"product": row["product"], **{key: int(row[key]) for key in ("hours","material","profit")}} for row in csv.DictReader(stream)]
    if not products or any(row["hours"] <= 0 or row["material"] <= 0 for row in products):
        raise ValueError("This example requires positive resource consumption.")
    result = enumerate_plans(products,40,48)
    independent = dynamic_profit(products,40,48)
    if result["profit"] != independent:
        raise RuntimeError("Independent methods disagree.")
    result["independent_profit"] = independent
    args.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(result)
