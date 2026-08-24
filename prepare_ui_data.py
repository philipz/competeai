#!/usr/bin/env python
# Copyright (c) 2025
# Licensed under the MIT License.
#
# Preprocesses logs/coke_pepsi into browser-loadable JSON for the
# BeverageTown replay frontend (beverage-ui/).
#
# Output layout (mirrors logs layout, one JSON per run):
#   beverage-ui/public/data/index.json
#   beverage-ui/public/data/{group}/{cell}/seed{s}.json
#
# Each run JSON:
#   {
#     "meta": {group, cell, seed, n_consumers, n_days, rule},
#     "daily": [ {day, price_coke, ..., hhi}, ... ],   # one entry per day
#     "consumers": {                                   # per-consumer info
#       "0": {"solo": true, "group_id": null},
#       ...
#     },
#     "choices": [ [c0d1, c0d2, ...], [c1d1, ...], ... ]  # choice per consumer per day
#   }

import gzip
import glob
import json
import os

ROOT = "logs/coke_pepsi"
OUT = "beverage-ui/public/data"

DAILY_COLS = ["day", "price_coke", "price_pepsi", "quality_coke", "quality_pepsi",
              "marketing_coke", "marketing_pepsi", "sales_coke", "sales_pepsi",
              "optout", "revenue_coke", "revenue_pepsi", "capital_coke",
              "capital_pepsi", "share_coke", "share_pepsi", "hhi"]


def load_daily(path):
    rows = []
    with open(path) as f:
        header = [h.strip() for h in f.readline().strip().split(",")]
        for line in f:
            if not line.strip():
                continue
            vals = line.strip().split(",")
            rec = {}
            for col, val in zip(header, vals):
                if col == "day":
                    rec[col] = int(val)
                elif col == "group":
                    rec[col] = val
                else:
                    rec[col] = float(val)
            rows.append(rec)
    return rows


def load_consumer(path):
    """Returns (n_consumers, n_days, consumers_info, choices_matrix)."""
    with gzip.open(path, "rt") as f:
        header = [h.strip() for h in f.readline().strip().split(",")]
        col_idx = {h: i for i, h in enumerate(header)}
        data = []
        for line in f:
            if not line.strip():
                continue
            parts = line.strip().split(",")
            data.append(parts)
    n_days = max(int(r[col_idx["day"]]) for r in data)
    n_consumers = max(int(r[col_idx["cid"]]) for r in data) + 1
    consumers_info = {}
    choices = [[-1] * n_days for _ in range(n_consumers)]
    for r in data:
        cid = int(r[col_idx["cid"]])
        day = int(r[col_idx["day"]]) - 1  # zero-based
        choice = int(r[col_idx["choice"]])
        choices[cid][day] = choice
        if str(cid) not in consumers_info:
            gid_raw = r[col_idx["group_id"]]
            consumers_info[str(cid)] = {
                "solo": gid_raw == "None" or gid_raw == "",
                "group_id": None if gid_raw in ("None", "") else gid_raw,
            }
    return n_consumers, n_days, consumers_info, choices


def sanitize(obj):
    """Convert NaN/Inf to None (JSON-safe)."""
    if isinstance(obj, float):
        import math
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, list):
        return [sanitize(x) for x in obj]
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    return obj


def main():
    os.makedirs(OUT, exist_ok=True)
    index = {"runs": []}

    for path in sorted(glob.glob(os.path.join(ROOT, "consumer", "*", "*", "*.csv.gz"))):
        parts = path.replace(os.sep, "/").split("/")
        group, cell, fname = parts[-3], parts[-2], parts[-1]
        seed = fname.replace("seed", "").replace(".csv.gz", "")
        rule = "sum" if cell.endswith("_sum") else "majority_explore"

        daily_path = os.path.join(ROOT, "daily", group, cell, f"seed{seed}.csv")
        if not os.path.exists(daily_path):
            print(f"skip (no daily): {group}/{cell}/{seed}")
            continue

        daily = load_daily(daily_path)
        n_consumers, n_days, consumers_info, choices = load_consumer(path)

        out_dir = os.path.join(OUT, group, cell)
        os.makedirs(out_dir, exist_ok=True)
        run_data = {
            "meta": {
                "group": group, "cell": cell, "seed": int(seed),
                "n_consumers": n_consumers, "n_days": n_days, "rule": rule,
            },
            "daily": daily,
            "consumers": consumers_info,
            "choices": choices,
        }
        with open(os.path.join(out_dir, f"seed{seed}.json"), "w") as f:
            json.dump(sanitize(run_data), f, ensure_ascii=False)

        # summary row for the index (last-day snapshot)
        last = daily[-1]
        index["runs"].append({
            "group": group, "cell": cell, "seed": int(seed), "rule": rule,
            "n_consumers": n_consumers, "n_days": n_days,
            "share_coke": last["share_coke"], "share_pepsi": last["share_pepsi"],
            "hhi": last["hhi"],
            "price_coke": last["price_coke"], "price_pepsi": last["price_pepsi"],
        })

    with open(os.path.join(OUT, "index.json"), "w") as f:
        json.dump(sanitize(index), f, ensure_ascii=False)

    print(f"preprocessed {len(index['runs'])} runs -> {OUT}")


if __name__ == "__main__":
    main()
