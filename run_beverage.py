#!/usr/bin/env python
# Copyright (c) 2025
# Licensed under the MIT License.
#
# Grid runner for the Coke vs Pepsi bidding experiment.
# Cells: consumers {100,200,300} x weeks {2,4,6}; groups CG/TG1/TG2/TG3/SYM/PEP12;
# 5 seeds each. Brand LLM decisions via DeepSeek; consumers parametric.
# Outputs: logs/coke_pepsi/daily/{group}/{cell}/seed{seed}.csv
#          logs/coke_pepsi/consumer/{group}/{cell}/seed{seed}.csv.gz

import argparse
import gzip
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def load_env(path=".env"):
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


def make_cfg(consumers=None):
    with open("competeai/examples/beverage.yaml") as f:
        cfg = yaml.safe_load(f)
    # merge calibrated parameters if present
    calib = "logs/coke_pepsi/calibrated_params.json"
    if os.path.exists(calib):
        with open(calib) as f:
            cal = json.load(f)
        cfg["consumers"].update(cal["consumers"])
    if consumers is not None:
        cfg["consumers"]["n_consumers"] = consumers
    return cfg


def run_one(cfg, group, n_days, n_consumers, seed, log_root, save_consumer,
            group_rule="majority_explore"):
    from competeai.scene.beverage import (
        BeverageMarket, ConsumerParams, generate_population,
    )
    from competeai.agent.backends.deepseek import DeepSeekChat

    cfg = json.loads(json.dumps(cfg))
    cfg["consumers"]["n_consumers"] = n_consumers
    if group_rule:
        cfg["consumers"]["group_rule"] = group_rule
    params = ConsumerParams(cfg)
    consumers = generate_population(n_consumers, seed, params)

    backend_cfg = cfg["backends"]["default_backend"]

    def factory(name):
        return DeepSeekChat(
            temperature=backend_cfg["temperature"],
            max_tokens=backend_cfg["max_tokens"],
            model=backend_cfg["model"],
        )

    market = BeverageMarket(cfg, group, n_days, seed, consumers,
                            backend_factory=factory)
    daily, consumer = market.run()

    cell = f"n{n_consumers}_w{n_days // 7}"
    rule_tag = ("_sum" if group_rule == "sum" else "")
    daily_dir = os.path.join(log_root, "daily", group, cell + rule_tag)
    os.makedirs(daily_dir, exist_ok=True)
    with open(os.path.join(daily_dir, f"seed{seed}.csv"), "w") as f:
        cols = list(daily[0].keys())
        f.write(",".join(cols) + "\n")
        for row in daily:
            f.write(",".join(str(row[c]) for c in cols) + "\n")

    if save_consumer:
        cons_dir = os.path.join(log_root, "consumer", group, cell + rule_tag)
        os.makedirs(cons_dir, exist_ok=True)
        with gzip.open(os.path.join(cons_dir, f"seed{seed}.csv.gz"), "wt") as f:
            cols = list(consumer[0].keys())
            f.write(",".join(cols) + "\n")
            for row in consumer:
                f.write(",".join(str(row[c]) for c in cols) + "\n")

    return group, cell, seed, len(daily)


def main():
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--consumers", default="100,200,300")
    ap.add_argument("--weeks", default="2,4,6")
    ap.add_argument("--groups", default="CG,TG1,TG2,TG3,SYM,PEP12")
    ap.add_argument("--seeds", default="0,1,2,3,4")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--save-consumer", action="store_true",
                    help="also dump per-consumer choice trajectories")
    ap.add_argument("--group-rule", default="",
                    help="override consumer group rule (majority_explore / sum); "
                         "empty keeps yaml value")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the run matrix without executing")
    args = ap.parse_args()

    consumer_counts = [int(x) for x in args.consumers.split(",")]
    weeks = [int(x) for x in args.weeks.split(",")]
    groups = args.groups.split(",")
    seeds = [int(x) for x in args.seeds.split(",")]
    baseline = 4

    cfg = make_cfg()
    log_root = cfg["experiment"]["log_root"]
    os.makedirs(log_root, exist_ok=True)

    tasks = []
    for n_consumers in consumer_counts:
        for w in weeks:
            n_days = w * 7
            cell = f"n{n_consumers}_w{w}"
            for group in groups:
                for seed in seeds:
                    tasks.append((group, n_days, n_consumers, seed))

    print(f"run matrix: {len(tasks)} runs "
          f"({len(consumer_counts)}x{len(weeks)} cells x {len(groups)} groups "
          f"x {len(seeds)} seeds)")
    if args.dry_run:
        for t in tasks:
            print(t)
        return

    ok = 0
    failed = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {
            ex.submit(run_one, cfg, group, n_days, n, seed, log_root,
                      args.save_consumer, args.group_rule): (group, n_days, n, seed)
            for group, n_days, n, seed in tasks
        }
        for fut in as_completed(futures):
            group, n_days, n, seed = futures[fut]
            try:
                res = fut.result()
                ok += 1
                print(f"[{ok}/{len(tasks)}] done {res[0]} {res[1]} seed{res[2]} "
                      f"({res[3]} days)  elapsed={time.time()-t0:.0f}s", flush=True)
            except Exception as e:
                failed += 1
                print(f"FAILED group={group} n={n} w={n_days//7} seed={seed}: {e}",
                      flush=True)

    print(f"\nfinished: ok={ok} failed={failed} elapsed={time.time()-t0:.0f}s")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
