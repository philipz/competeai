#!/usr/bin/env python
# Copyright (c) 2025
# Licensed under the MIT License.
#
# Analysis for the Coke vs Pepsi bidding experiment.
# Reads logs/coke_pepsi/daily/** and consumer/**, computes:
#   - XED / PED via log-log regression and arc elasticity (Q10a/b)
#   - 2022 Pepsi +12% external validity check (Q10c)
#   - market share / HHI time series, switching matrices, strategy
#     classification (share harvesting vs margin matching), quality evolution
#   - solo vs group XED moderation, majority vs sum group-rule contrast (Q11)
# Writes figures to logs/coke_pepsi/fig/ and a summary JSON.

import glob
import json
import math
import os

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    plt.style.use("science")
except Exception:
    pass

FIG_DIR = "logs/coke_pepsi/fig"
SUMMARY_PATH = "logs/coke_pepsi/summary.json"


def load_daily(root="logs/coke_pepsi/daily", include_sum=False):
    frames = []
    for path in glob.glob(os.path.join(root, "*", "*", "*.csv")):
        if not include_sum and "_sum" in path:
            continue
        frame = pd.read_csv(path)
        cell = os.path.basename(os.path.dirname(path))
        frame["cell"] = cell
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def load_consumer(root="logs/coke_pepsi/consumer", include_sum=False):
    frames = []
    for path in glob.glob(os.path.join(root, "*", "*", "*.csv.gz")):
        if not include_sum and "_sum" in path:
            continue
        frame = pd.read_csv(path)
        parts = path.replace(os.sep, "/").split("/")
        frame["group"] = parts[-3]
        frame["cell"] = parts[-2]
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def loglog_regression(df, group_sel=("CG", "TG1", "TG2", "TG3")):
    """Estimate PED(coke), PED(pepsi), XED(coke->pepsi) with a log-log demand
    panel: ln Q = b0 + b_pc ln P_coke + b_pp ln P_pepsi + (quality/marketing
    controls) + seed fixed effects. Post-baseline days only.

    Identification note: Coke's price is exogenous and constant within group,
    so PED/XED wrt P_coke are identified from BETWEEN-group price variation;
    we therefore do NOT include group fixed effects (they are collinear with
    P_coke). Pepsi's price varies day to day (LLM decisions), giving within
    variation for PED_pepsi."""
    d = df[df["group"].isin(group_sel) & (df["day"] > 4)].copy()
    d["lnQ_coke"] = np.log(d["sales_coke"] + 1e-6)
    d["lnQ_pepsi"] = np.log(d["sales_pepsi"] + 1e-6)
    d["lnP_coke"] = np.log(d["price_coke"])
    d["lnP_pepsi"] = np.log(d["price_pepsi"])
    # In Phase A, Coke's quality/marketing are constant (fixed treatment), so
    # we control only for Pepsi's time-varying quality/marketing.
    d["lnQ_quality_pepsi"] = np.log(d["quality_pepsi"])
    d["lnM_pepsi"] = np.log(d["marketing_pepsi"] + 1.0)
    d["fe"] = d["seed"].astype(str)

    fe_dummies = pd.get_dummies(d["fe"], drop_first=True).astype(float)
    X = pd.concat([d[["lnP_coke", "lnP_pepsi", "lnQ_quality_pepsi", "lnM_pepsi"]],
                   fe_dummies], axis=1)
    X.insert(0, "const", 1.0)

    def ols(y, X):
        X = X.values.astype(float)
        y = y.values.astype(float)
        XtX = X.T @ X
        try:
            XtX_inv = np.linalg.inv(XtX)
        except np.linalg.LinAlgError:
            XtX_inv = np.linalg.pinv(XtX)
        beta = XtX_inv @ (X.T @ y)
        resid = y - X @ beta
        n, k = X.shape
        sigma2 = (resid @ resid) / (n - k)
        se = np.sqrt(np.diag(XtX_inv * sigma2))
        return beta, se

    b_coke, se_coke = ols(d["lnQ_coke"], X)
    b_pepsi, se_pepsi = ols(d["lnQ_pepsi"], X)

    return {
        "ped_coke": float(b_coke[1]), "ped_coke_se": float(se_coke[1]),
        "xed_pepsi_to_coke": float(b_coke[2]), "xed_pepsi_to_coke_se": float(se_coke[2]),
        "xed_coke_to_pepsi": float(b_pepsi[1]), "xed_coke_to_pepsi_se": float(se_pepsi[1]),
        "ped_pepsi": float(b_pepsi[2]), "ped_pepsi_se": float(se_pepsi[2]),
        "n_obs": int(len(d)),
    }


def arc_elasticity(df):
    """Arc XED: compare CG vs each TG in post-baseline window, share-weighted,
    pooled over seeds. XED = (dQ_pepsi/Q_pepsi) / (dP_coke/P_coke)."""
    d = df[df["day"] > 4]
    out = {}
    base = d[d["group"] == "CG"]
    for tg in ("TG1", "TG2", "TG3"):
        treat = d[d["group"] == tg]
        # aggregate over seeds/cells: mean shares per group
        q_p_base = base["share_pepsi"].mean()
        p_c_base = base["price_coke"].mean()
        q_p_treat = treat["share_pepsi"].mean()
        p_c_treat = treat["price_coke"].mean()
        dq = (q_p_treat - q_p_base) / ((q_p_base + q_p_treat) / 2)
        dp = (p_c_treat - p_c_base) / ((p_c_base + p_c_treat) / 2)
        out[tg] = {"arc_xed": float(dq / dp),
                   "coke_price": float(p_c_treat),
                   "pepsi_share_base": float(q_p_base),
                   "pepsi_share_treat": float(q_p_treat)}
    return out


def arc_elasticity_parametric(df):
    """Clean XED on pure-parametric groups (BF/BF5/BF10/BF20): Pepsi price is
    fixed at $2.00 so the measured substitution is uncontaminated by LLM
    responses — the doc's XED anchors (e.g. +0.63) apply to this design."""
    d = df[df["day"] > 4]
    out = {}
    base = d[d["group"] == "BF"]
    for tg, pct in (("BF5", 0.05), ("BF10", 0.10), ("BF20", 0.20)):
        treat = d[d["group"] == tg]
        q_p_base = base["share_pepsi"].mean()
        p_c_base = base["price_coke"].mean()
        q_p_treat = treat["share_pepsi"].mean()
        p_c_treat = treat["price_coke"].mean()
        dq = (q_p_treat - q_p_base) / ((q_p_base + q_p_treat) / 2)
        dp = (p_c_treat - p_c_base) / ((p_c_base + p_c_treat) / 2)
        out[tg] = {"arc_xed": float(dq / dp) if dp != 0 else float("nan"),
                   "coke_price": float(p_c_treat),
                   "pepsi_share_base": float(q_p_base),
                   "pepsi_share_treat": float(q_p_treat),
                   "shock_pct": pct}
    return out


def external_validity(df):
    """2022 case: Pepsi +12% (PEP12 group) while Coke stays at $2.00.
    Baseline is BF (both fixed at $2.00, pure parametric) — CG cannot be the
    baseline because Pepsi is an LLM agent there and cuts price, which is not
    the 2022 counterfactual. Expected: Coke gains ~2pp share."""
    d = df[df["day"] > 4]
    bf = d[d["group"] == "BF"].groupby(["n_consumers"])["share_coke"].mean()
    p12 = d[d["group"] == "PEP12"].groupby(["n_consumers"])["share_coke"].mean()
    out = {}
    for n in bf.index:
        delta_pp = (p12.get(n, np.nan) - bf[n]) * 100
        out[int(n)] = {"coke_share_bf": float(bf[n]),
                       "coke_share_pep12": float(p12.get(n, np.nan)),
                       "delta_pp": float(delta_pp)}
    return out


def hhi_series(df):
    return df.groupby(["group", "day"])["hhi"].mean().reset_index()


def switching_matrix(consumer, max_consumers=200):
    """Markov transition among {Coke, Pepsi, OptOut} from per-consumer daily
    trajectories. Optional cap for memory."""
    if consumer.empty:
        return {}
    c = consumer[consumer["cid"] < max_consumers].copy()
    c = c[(c["prev"] >= 0)]
    counts = pd.crosstab(c["prev"], c["choice"])
    counts = counts.reindex(index=[0, 1, 2], columns=[0, 1, 2], fill_value=0)
    mat = counts.div(counts.sum(axis=1), axis=0).fillna(0.0)
    return {f"from_{int(i)}": {f"to_{int(j)}": float(mat.loc[i, j])
                               for j in range(3)} for i in range(3)}


def classify_strategy(df):
    """For TG groups: classify Pepsi's response to Coke's shock relative to the
    baseline period (day 4, pre-shock).
    Share harvesting: Pepsi holds/lowers price AND invests in marketing.
    Margin matching: Pepsi raises price within a few days of the shock."""
    d = df[df["day"] > 4].copy()
    rows = []
    for (group, n_cons, seed), g in d.groupby(["group", "n_consumers", "seed"]):
        if group not in ("TG1", "TG2", "TG3"):
            continue
        g = g.sort_values("day")
        # pre-shock baseline (day 4)
        base_row = df[(df["group"] == group) & (df["n_consumers"] == n_cons)
                      & (df["seed"] == seed) & (df["day"] == 4)]
        p_base = base_row["price_pepsi"].mean() if len(base_row) else 2.0
        window = g[g["day"] <= 8]  # shock days 5-8
        price_rise = window["price_pepsi"].mean() - p_base
        mkt_engaged = window["marketing_pepsi"].mean() > 100.0
        if price_rise > 0.03:
            strat = "margin_matching"
        elif mkt_engaged and price_rise <= 0.03:
            strat = "share_harvesting"
        else:
            strat = "other"
        rows.append({"group": group, "n_consumers": n_cons, "seed": seed,
                     "strategy": strat, "price_rise": price_rise,
                     "mkt_engaged": mkt_engaged})
    return pd.DataFrame(rows)


def quality_evolution(df):
    d = df[df["day"] > 4]
    return (d.groupby(["group", "day"])[["quality_coke", "quality_pepsi"]]
            .mean().reset_index())


def solo_vs_group_xed(df, consumer):
    """XED moderation: compare share response for solo vs group consumers.
    Uses the pure-parametric BF series (Pepsi fixed at $2.00) so the effect is
    not contaminated by LLM price responses."""
    if consumer.empty:
        return {}
    c = consumer.copy()
    c = c[c["group"].isin(["BF", "BF5", "BF10", "BF20"])]
    if c.empty:
        return {}
    c["is_solo"] = c["group_id"].isna()
    c["is_pepsi"] = (c["choice"] == 1).astype(int)
    agg = (c.groupby(["group", "day", "is_solo"])
           [["is_pepsi"]].mean().reset_index())
    out = {}
    for solo in (True, False):
        a = agg[agg["is_solo"] == solo]
        base = a[a["group"] == "BF"].groupby("day")["is_pepsi"].mean()
        for tg, pct in (("BF5", 0.05), ("BF10", 0.10), ("BF20", 0.20)):
            treat = a[a["group"] == tg].groupby("day")["is_pepsi"].mean()
            dq = (treat.mean() - base.mean()) / ((base.mean() + treat.mean()) / 2)
            dp = math.log(1.0 + pct)
            out[f"solo={solo}|{tg}"] = {"xed": float(dq / dp),
                                        "pepsi_share_base": float(base.mean()),
                                        "pepsi_share_treat": float(treat.mean())}
    return out


def group_rule_contrast():
    """Q11: compare arc XED under majority_explore vs sum group rules on the
    anchor cell (n100_w4). Reads the *_sum directories for the sum rule."""
    out = {}
    for rule, include_sum in (("majority_explore", False), ("sum", True)):
        df = load_daily(include_sum=include_sum)
        cell = "n100_w4_sum" if include_sum else "n100_w4"
        # restrict to anchor cell n100_w4 only
        d = df[(df["cell"] == cell) & (df["day"] > 4)]
        base = d[d["group"] == "CG"]
        row = {}
        for tg in ("TG1", "TG2", "TG3"):
            treat = d[d["group"] == tg]
            q_p_base = base["share_pepsi"].mean()
            p_c_base = base["price_coke"].mean()
            q_p_treat = treat["share_pepsi"].mean()
            p_c_treat = treat["price_coke"].mean()
            dq = (q_p_treat - q_p_base) / ((q_p_base + q_p_treat) / 2)
            dp = (p_c_treat - p_c_base) / ((p_c_base + p_c_treat) / 2)
            row[tg] = float(dq / dp) if dp != 0 else float("nan")
        out[rule] = row
    return out


def plot_series(df, out_prefix):
    os.makedirs(FIG_DIR, exist_ok=True)
    hhi = hhi_series(df)
    fig, ax = plt.subplots(figsize=(7, 4))
    for g in hhi["group"].unique():
        s = hhi[hhi["group"] == g]
        ax.plot(s["day"], s["hhi"], label=g, marker="o", ms=3)
    ax.set_xlabel("day"); ax.set_ylabel("HHI"); ax.set_title("HHI time series")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(os.path.join(FIG_DIR, f"{out_prefix}_hhi.png"), dpi=150)
    plt.close(fig)

    q = quality_evolution(df)
    fig, ax = plt.subplots(figsize=(7, 4))
    for g in q["group"].unique():
        s = q[q["group"] == g]
        ax.plot(s["day"], s["quality_coke"], "--", label=f"{g} Coke", alpha=0.7)
        ax.plot(s["day"], s["quality_pepsi"], "-", label=f"{g} Pepsi", alpha=0.7)
    ax.set_xlabel("day"); ax.set_ylabel("quality"); ax.set_title("Quality evolution")
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout(); fig.savefig(os.path.join(FIG_DIR, f"{out_prefix}_quality.png"), dpi=150)
    plt.close(fig)

    # share time series (CG vs TG3 vs SYM)
    fig, ax = plt.subplots(figsize=(7, 4))
    for g in ("CG", "TG3", "SYM"):
        s = df[df["group"] == g].groupby("day")[["share_coke", "share_pepsi"]].mean()
        ax.plot(s.index, s["share_coke"], label=f"{g} Coke", marker=".", ms=3)
        ax.plot(s.index, s["share_pepsi"], "--", label=f"{g} Pepsi", marker=".", ms=3)
    ax.set_xlabel("day"); ax.set_ylabel("market share"); ax.set_title("Market share dynamics")
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout(); fig.savefig(os.path.join(FIG_DIR, f"{out_prefix}_shares.png"), dpi=150)
    plt.close(fig)

    # Pepsi price response to Coke shock (RQ2)
    fig, ax = plt.subplots(figsize=(7, 4))
    for g in ("CG", "TG1", "TG2", "TG3"):
        s = df[df["group"] == g].groupby("day")["price_pepsi"].mean()
        ax.plot(s.index, s, label=f"Pepsi in {g}", marker=".", ms=3)
    ax.axvline(4.5, color="k", ls=":", lw=1, label="shock day")
    ax.set_xlabel("day"); ax.set_ylabel("Pepsi price ($)"); ax.set_title("Pepsi price response")
    ax.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(os.path.join(FIG_DIR, f"{out_prefix}_pepsi_price.png"), dpi=150)
    plt.close(fig)


def main():
    df = load_daily()
    consumer = load_consumer()
    print(f"daily rows: {len(df)}, consumer rows: {len(consumer)}")

    os.makedirs(FIG_DIR, exist_ok=True)
    summary = {}

    # Q10a: log-log regression
    reg = loglog_regression(df)
    summary["loglog"] = reg
    print("loglog:", {k: round(v, 3) if isinstance(v, float) else v for k, v in reg.items()})

    # Q10b: arc elasticity
    arc = arc_elasticity(df)
    summary["arc_xed"] = arc
    print("arc XED:", {k: round(v["arc_xed"], 3) for k, v in arc.items()})

    # Q10b clean: arc elasticity on pure-parametric BF series
    arcp = arc_elasticity_parametric(df)
    summary["arc_xed_parametric"] = arcp
    print("parametric arc XED:", {k: round(v["arc_xed"], 3) for k, v in arcp.items()})

    # Q10c: external validity
    ext = external_validity(df)
    summary["external_validity_2022"] = ext
    print("2022 external validity:", {k: round(v["delta_pp"], 3) for k, v in ext.items()})

    # switching matrix
    sw = switching_matrix(consumer)
    summary["switching_matrix"] = sw

    # strategy classification
    strat = classify_strategy(df)
    if not strat.empty:
        frac = strat["strategy"].value_counts(normalize=True).to_dict()
        summary["strategy_fractions"] = frac
        summary["strategy_by_group"] = (strat.groupby(["group", "strategy"]).size()
                                        .unstack(fill_value=0).to_dict("index"))
        print("strategy fractions:", {k: round(v, 3) for k, v in frac.items()})

    # solo vs group XED
    svg = solo_vs_group_xed(df, consumer)
    summary["solo_vs_group_xed"] = svg
    print("solo/group XED:", {k: round(v["xed"], 3) for k, v in svg.items()})

    # Q11: group-rule contrast (requires *_sum dirs present)
    grc = group_rule_contrast()
    summary["group_rule_contrast"] = grc
    print("group-rule contrast:", grc)

    plot_series(df, "coke_pepsi")

    with open(SUMMARY_PATH, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print("summary written:", SUMMARY_PATH)


if __name__ == "__main__":
    main()
