"""Collect initial DART equity filing candidates for the July–December 2025 stratum."""

import argparse
import math
from concurrent.futures import ThreadPoolExecutor

from scripts import official_enrollment as dart
from scripts.current_b import OUT, dump
from scripts.current_live import load
from scripts.screen_a1_first_filings import CACHE, TITLE

INTERVALS = {"2025H2": (("20250701", "20250930"), ("20251001", "20251231")),
             "2024Q3": (("20240701", "20240930"),),
             "2023H1": (("20230101", "20230331"), ("20230401", "20230630"))}


def inventory(window, destination):
    target = destination / "inventory.json"
    if target.exists():
        return load(target)
    pages = []
    intervals = INTERVALS[window]
    for start, end in intervals:
        dart.PARAMS.update(startDate=start, endDate=end)
        first = dart.listing(1)
        count = math.ceil(first["reported_total"] / 100)
        with ThreadPoolExecutor(max_workers=3) as pool:
            group = [first, *pool.map(dart.listing, range(2, count + 1))]
        if sum(len(p["records"]) for p in group) != first["reported_total"]:
            raise ValueError("Incomplete DART listing")
        pages.extend(group)
    records = sorted((r for p in pages for r in p["records"]), key=lambda r: r["receipt"])
    if len({r["receipt"] for r in records}) != len(records):
        raise ValueError("DART listing overlap")
    names, receipts, codes = dart.prior_roster()
    prior = load(OUT / "official/enrollment/screened_all.json")["rows"]
    codes.update(r["corp_code"] for r in prior)
    for r in records:
        if r["title"] != TITLE:
            status = "other_title"
        elif r["corp_code"] in codes or dart.key(r["issuer"]) in names or r["receipt"] in receipts:
            status = "prior_corporation"
        elif any(s in dart.key(r["issuer"]) for s in ("스팩", "기업인수목적", "spac")):
            status = "spac"
        elif r["withdrawal_notice"]:
            status = "withdrawn"
        else:
            status = "initial_candidate"
        r["inventory_status"] = status
    result = {"window": [intervals[0][0], intervals[-1][1]], "records": records,
              "pages": [{k: v for k, v in p.items() if k != "records"} for p in pages]}
    dump(target, result)
    return result


def inspect(row, destination):
    target = destination / "locator" / (row["receipt"] + ".json")
    if target.exists() and load(target).get("download_status") == "공식 PDF 확인":
        return
    value = dart.inspect(row)
    dump(target, value)
    print(row["receipt"], row["issuer"], value.get("screen_status"), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--window", choices=INTERVALS, default="2025H2")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--stop", type=int, required=True)
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    destination = OUT / "official/enrollment_expansion" / args.window
    rows = [r for r in inventory(args.window, destination)["records"] if r["inventory_status"] == "initial_candidate"]
    print(len(rows), "candidates", flush=True)
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(lambda r: inspect(r, destination), rows[args.start:args.stop]))
