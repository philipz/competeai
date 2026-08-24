#!/usr/bin/env python
# Copyright (c) 2025
# Licensed under the MIT License.
#
# Consumer parameter calibration for the Coke vs Pepsi experiment (Q14c).
# Searches consumer parameters so that a fixed-price parametric market yields
#   PED(coke) in [-4, -2]  and  XED(coke->pepsi) close to +0.63,
# matching the empirical anchors cited in docs/CompeteAI_Coke_vs_Pepsi.md.
# Outputs logs/coke_pepsi/calibrated_params.json consumed by run_beverage.py.

import itertools
import json
import math
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from competeai.scene.beverage import (  # noqa: E402
    BeverageMarket, ConsumerParams, generate_population,
)


def load_env(path=".env"):
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def shares_at(cfg, coke_price_override, n_days=30, n_consumers=300, seed=42):
    """Average post-baseline market shares with Coke price fixed at an override
    (None -> base price) and Pepsi fixed at base price. No LLM involved."""
    cfg = json.loads(json.dumps(cfg))  # deep copy
    cfg["consumers"]["n_consumers"] = n_consumers
    params = ConsumerParams(cfg)
    consumers = generate_population(n_consumers, seed, params)
    if coke_price_override is None:
        modes = ("fixed", "fixed")
    else:
        pct = coke_price_override / cfg["market"]["base_price"] - 1.0
        modes = ("+%.6f" % pct, "fixed")
    market = BeverageMarket(cfg, "CAL", n_days, seed, consumers, modes=modes)
    daily, _ = market.run()
    post = [d for d in daily if d["day"] > 4]
    n = len(post)
    s_c = sum(d["share_coke"] for d in post) / n
    s_p = sum(d["share_pepsi"] for d in post) / n
    return s_c, s_p


def elasticities(cfg, params_override, seeds=(42, 7, 123)):
    """Average PED/XED over several consumer-population seeds to damp noise."""
    cfg = json.loads(json.dumps(cfg))
    cfg["consumers"].update(params_override)
    base = cfg["market"]["base_price"]
    dlp = math.log(1.10)
    peds, xeds, shares = [], [], []
    for seed in seeds:
        s_c0, s_p0 = shares_at(cfg, None, seed=seed)
        s_c1, s_p1 = shares_at(cfg, base * 1.10, seed=seed)
        peds.append(math.log(s_c1 / s_c0) / dlp)
        xeds.append(math.log(s_p1 / s_p0) / dlp)
        shares.append((s_c0, s_p0))
    return (sum(peds) / len(peds), sum(xeds) / len(xeds),
            tuple(sum(s[i] for s in shares) / len(shares) for i in (0, 1)))


def score(ped, xed, optout_share):
    # target: ped in [-4,-2] (center -3), xed ~ +0.63, opt-out not dominant
    ped_pen = 0.0
    if ped < -4:
        ped_pen += (-4 - ped) * 10
    elif ped > -2:
        ped_pen += (ped + 2) * 10
    else:
        ped_pen += abs(ped + 3.0)
    opt_pen = max(0.0, optout_share - 0.35) * 5.0  # prefer opt-out < 35%
    return abs(xed - 0.63) * 2.0 + ped_pen + opt_pen


def main():
    load_env()
    with open("competeai/examples/beverage.yaml") as f:
        cfg = yaml.safe_load(f)

    best = None
    # coarse grid: include loyalty heterogeneity (beta_sd) to damp XED
    grid = itertools.product(
        [20000, 25000, 30000],          # alpha_scale
        [5.0, 6.5, 8.0],                # beta_mean
        [2.0, 3.0],                     # beta_sd
        [1.2, 1.6, 2.0],                # gumbel_scale
    )
    results = []
    for alpha, beta, betasd, gumbel in grid:
        ov = {"alpha_scale": alpha, "beta_mean": beta, "beta_sd": betasd,
              "gumbel_scale": gumbel}
        try:
            ped, xed, shares = elasticities(cfg, ov)
        except Exception as e:
            print("fail", ov, e)
            continue
        sc = score(ped, xed, 1 - shares[0] - shares[1])
        results.append((sc, ov, ped, xed, shares))
        print(f"alpha={alpha:6.0f} beta={beta:.1f} betasd={betasd:.1f} gumbel={gumbel:.1f} "
              f"-> PED={ped:+.2f} XED={xed:+.2f} shares={shares[0]:.3f}/{shares[1]:.3f} score={sc:.3f}")

    results.sort(key=lambda r: r[0])
    sc, ov, ped, xed, shares = results[0]
    print("\nBEST (coarse):", ov, f"PED={ped:+.3f}", f"XED={xed:+.3f}",
          f"shares={shares[0]:.3f}/{shares[1]:.3f}")

    # fine grid around the coarse best
    fine = itertools.product(
        [alpha for alpha in (ov["alpha_scale"] - 3000, ov["alpha_scale"],
                             ov["alpha_scale"] + 3000)],
        [beta for beta in (ov["beta_mean"] - 0.5, ov["beta_mean"],
                           ov["beta_mean"] + 0.5)],
        [ov["beta_sd"]],
        [g for g in (ov["gumbel_scale"] - 0.2, ov["gumbel_scale"],
                     ov["gumbel_scale"] + 0.2)],
    )
    fine_results = []
    for alpha, beta, betasd, gumbel in fine:
        ovf = {"alpha_scale": alpha, "beta_mean": beta, "beta_sd": betasd,
               "gumbel_scale": gumbel}
        ped, xed, shares = elasticities(cfg, ovf)
        scf = score(ped, xed, 1 - shares[0] - shares[1])
        fine_results.append((scf, ovf, ped, xed, shares))
        print(f"FINE alpha={alpha:6.0f} beta={beta:.1f} gumbel={gumbel:.1f} "
              f"-> PED={ped:+.2f} XED={xed:+.2f} score={scf:.3f}")
    fine_results.sort(key=lambda r: r[0])
    sc, ov, ped, xed, shares = fine_results[0]
    print("\nBEST (fine):", ov, f"PED={ped:+.3f}", f"XED={xed:+.3f}",
          f"shares={shares[0]:.3f}/{shares[1]:.3f}")

    out = {"consumers": ov, "measured": {"ped": ped, "xed": xed,
                                         "share_coke_base": shares[0],
                                         "share_pepsi_base": shares[1]}}
    os.makedirs("logs/coke_pepsi", exist_ok=True)
    with open("logs/coke_pepsi/calibrated_params.json", "w") as f:
        json.dump(out, f, indent=2)
    print("saved logs/coke_pepsi/calibrated_params.json")


if __name__ == "__main__":
    main()
