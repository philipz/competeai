# Copyright (c) 2025
# Licensed under the MIT License.
#
# BeverageTown duopoly engine for the Coke vs Pepsi bidding experiment.
# Standalone engine: brand agents are LLM-driven (DeepSeek), consumers are
# parametric utility-maximizers. No Django dependency; state is held in
# memory and dumped to CSV per run.

import json
import math
import re
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..message import Message
from ..utils.prompt_template import PromptTemplate

# choice codes: 0 = CocaCola, 1 = PepsiCo, 2 = OptOut
N_CHOICES = 3
BRAND_NAMES = ["CocaCola", "PepsiCo"]


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


# ---------------------------------------------------------------- consumer

class Consumer:
    __slots__ = ("cid", "income", "alpha", "beta_coke", "beta_pepsi",
                 "group_id", "solo")

    def __init__(self, cid, income, alpha, beta_coke, beta_pepsi, group_id, solo):
        self.cid = cid
        self.income = income
        self.alpha = alpha          # price sensitivity, inversely ~ income
        self.beta_coke = beta_coke  # intrinsic brand loyalty
        self.beta_pepsi = beta_pepsi
        self.group_id = group_id    # None for solo consumers
        self.solo = solo


class ConsumerParams:
    def __init__(self, cfg: dict):
        c = cfg["consumers"]
        self.n = int(c["n_consumers"])
        self.solo_ratio = float(c["solo_ratio"])
        self.income_min = float(c["income_min"])
        self.income_max = float(c["income_max"])
        self.alpha_scale = float(c["alpha_scale"])
        self.beta_mean = float(c["beta_mean"])
        self.beta_sd = float(c["beta_sd"])
        self.gamma_q = float(c["gamma_q"])
        self.gamma_a = float(c["gamma_a"])
        self.gumbel_scale = float(c["gumbel_scale"])
        self.explore_prob = float(c["explore_prob"])
        self.group_size_values = [int(x) for x in c["group_size_values"]]
        self.group_size_probs = [float(x) for x in c["group_size_probs"]]
        self.sat_w_q = float(c["sat_w_q"])
        self.sat_w_p = float(c["sat_w_p"])
        self.sat_noise = float(c["sat_noise"])
        self.sat_q_anchor = float(c.get("sat_q_anchor", c.get("base_quality", 0.7)))
        self.group_rule = c.get("group_rule", "majority_explore")  # or "sum"


def generate_population(n: int, seed: int, params: ConsumerParams) -> List[Consumer]:
    rng = np.random.default_rng(seed)
    incomes = rng.uniform(params.income_min, params.income_max, n)
    alphas = params.alpha_scale / incomes
    betas_c = rng.normal(params.beta_mean, params.beta_sd, n)
    betas_p = rng.normal(params.beta_mean, params.beta_sd, n)

    n_solo = int(round(n * params.solo_ratio))
    group_ids = [None] * n
    next_gid = 0
    idx = n_solo
    while idx < n:
        size = int(rng.choice(params.group_size_values, p=params.group_size_probs))
        size = min(size, n - idx)
        for k in range(size):
            group_ids[idx + k] = next_gid
        next_gid += 1
        idx += size

    consumers = []
    for i in range(n):
        consumers.append(Consumer(
            cid=i, income=incomes[i], alpha=alphas[i],
            beta_coke=betas_c[i], beta_pepsi=betas_p[i],
            group_id=group_ids[i], solo=(group_ids[i] is None),
        ))
    return consumers


def deterministic_utility(consumer, prices, qualities, ads, gamma_q, gamma_a):
    v_c = (consumer.beta_coke - consumer.alpha * prices[0]
           + gamma_q * qualities[0] + gamma_a * ads[0])
    v_p = (consumer.beta_pepsi - consumer.alpha * prices[1]
           + gamma_q * qualities[1] + gamma_a * ads[1])
    return np.array([v_c, v_p, 0.0])


def sample_choice(v, rng, gumbel_scale):
    if gumbel_scale <= 1e-9:
        return int(np.argmax(v))
    g = rng.gumbel(0.0, gumbel_scale, size=v.shape[0])
    return int(np.argmax(v + g))


def group_decision(v_matrix, rng, params, prev_choice):
    """majority_explore rule: members vote with Gumbel noise, majority wins;
    ties resolved by total deterministic utility; with probability
    explore_prob the group tries a different choice than yesterday."""
    votes = np.array([sample_choice(v, rng, params.gumbel_scale)
                      for v in v_matrix])
    counts = np.bincount(votes, minlength=N_CHOICES)
    majority = int(np.argmax(counts))
    if np.sum(counts == counts.max()) > 1:
        majority = int(np.argmax(v_matrix.sum(axis=0)))
    if (params.explore_prob > 0 and prev_choice is not None
            and rng.random() < params.explore_prob):
        means = v_matrix.mean(axis=0)
        cands = [i for i in range(N_CHOICES) if i != prev_choice]
        majority = max(cands, key=lambda i: means[i])
    return majority


def group_decision_sum(v_matrix):
    """contrast rule 'sum': the group picks the brand maximizing total utility."""
    return int(np.argmax(v_matrix.sum(axis=0)))


def satisfaction_stars(quality, price, base_price, rng, params):
    x = (params.sat_w_q * (quality - params.sat_q_anchor)
         - params.sat_w_p * (price - base_price) / base_price
         + rng.normal(0.0, params.sat_noise))
    s = 1 + 4 * _sigmoid(x)
    return int(_clamp(round(s), 1, 5))


# ---------------------------------------------------------------- comments

POSITIVE_COMMENTS = [
    "「{brand} 的 {slogan}！味道一如既往地出色，價格完全值得。」",
    "「口感順滑、氣泡充足，{brand} 從沒讓我失望，會繼續回購。」",
    "「新配方很驚豔，{brand} 這波升級很有誠意。」",
    "「價格合理、品質穩定，{brand} 是每天的首選。」",
    "「廣告裡的 {slogan} 很打動我，喝起來果然沒讓我失望。」",
]

NEUTRAL_COMMENTS = [
    "「{brand} 表現中規中矩，沒有特別驚喜但也沒有失望。」",
    "「味道還行，但如果價格再低一點會更常買。」",
    "「跟平時差不多，{brand} 的品質還是穩定的。」",
    "「說不上最好，但也挑不出大毛病。」",
]

NEGATIVE_COMMENTS = [
    "「{brand} 漲價太多了，這個價格配不上這個品質。」",
    "「最近 {brand} 的味道變差了，有點失望。」",
    "「廣告說得很好聽，但實際喝起來差強人意。」",
    "「同樣的價格我會去試別家，{brand} 不再划算。」",
]


def sample_comments(brand, slogan, stars, rng):
    n_pos = max(1, sum(1 for s in stars if s >= 4))
    n_neg = max(1, sum(1 for s in stars if s <= 2))
    n_neu = max(1, sum(1 for s in stars if s == 3))
    pools = ([rng.choice(POSITIVE_COMMENTS) for _ in range(min(n_pos, 3))]
             + [rng.choice(NEUTRAL_COMMENTS) for _ in range(min(n_neu, 2))]
             + [rng.choice(NEGATIVE_COMMENTS) for _ in range(min(n_neg, 2))])
    rng.shuffle(pools)
    return [c.format(brand=brand, slogan=slogan) for c in pools[:5]]


# ---------------------------------------------------------------- brand agent

class BrandAgent:
    SYSTEM_PROMPT = None

    def __init__(self, name, role_desc, backend, cfg):
        m = cfg["market"]
        self.name = name
        self.role_desc = role_desc
        self.backend = backend
        if BrandAgent.SYSTEM_PROMPT is None:
            tpl = PromptTemplate(["beverage", "brand_system"])
            if tpl.content is None:
                raise RuntimeError("beverage/brand_system.txt prompt template missing")
            BrandAgent.SYSTEM_PROMPT = tpl.content
        self.system_prompt = BrandAgent.SYSTEM_PROMPT
        self.base_price = float(m["base_price"])
        self.base_quality = float(m["base_quality"])
        self.capital = float(m["start_capital"])
        self.fixed_cost = float(m["daily_fixed_cost"])
        self.recipe_cost_per_01 = float(m["recipe_cost_per_01"])
        self.base_unit_cost = float(m["base_unit_cost"])
        self.price = self.base_price
        self.quality = self.base_quality
        self.marketing = 0.0
        self.slogan = ""
        self.alive = True
        self.last_decision = {"price": self.base_price,
                              "marketing_budget": 0.0,
                              "recipe_change": 0.0,
                              "slogan": ""}
        self.total_profit = 0.0
        self.last_units = 0
        self.cum_units = 0

    def unit_cost(self):
        return (self.base_unit_cost
                + self.recipe_cost_per_01 * 10.0
                * max(0.0, self.quality - self.base_quality))

    def apply_recipe(self, delta):
        self.quality = _clamp(self.quality + _clamp(float(delta), -0.3, 0.3),
                              0.4, 1.5)

    def ad_exposure(self):
        return 1.0 - math.exp(-self.marketing / 300.0)

    def decide(self, day, daybook_str, rival_str, comments_str):
        tpl = PromptTemplate(["beverage", "daybook"])
        if tpl.content is None:
            raise RuntimeError("beverage/daybook.txt prompt template missing")
        prompt = tpl.render([day, daybook_str, rival_str, comments_str])
        msg = Message(agent_name="System", content=prompt, turn=0,
                      visible_to=self.name)
        decision = self._query([msg], first_try=True)
        self._apply(decision)
        return decision

    def _query(self, messages, first_try):
        try:
            raw = self.backend.query(
                agent_name=self.name, agent_type="boss",
                role_desc=self.role_desc, history_messages=messages,
                global_prompt=self.system_prompt, request_msg=None)
        except Exception:
            return dict(self.last_decision)
        parsed = _parse_decision_json(raw)
        if parsed is None:
            if first_try:
                retry = Message(agent_name="System",
                                content="你的回覆格式錯誤。請只輸出一個 JSON 物件，包含 price、marketing_budget、recipe_change、slogan 四個欄位。",
                                turn=1, visible_to=self.name)
                return self._query(messages + [retry], first_try=False)
            return dict(self.last_decision)
        return parsed

    def _apply(self, decision):
        price = float(decision.get("price", self.base_price))
        budget = float(decision.get("marketing_budget", 0.0))
        recipe = float(decision.get("recipe_change", 0.0))
        slogan = str(decision.get("slogan", ""))[:60]
        self.price = _clamp(price, 0.5, 5.0)
        self.marketing = _clamp(budget, 0.0, 2000.0)
        self.apply_recipe(recipe)
        if slogan:
            self.slogan = slogan
        self.last_decision = {"price": self.price,
                              "marketing_budget": self.marketing,
                              "recipe_change": recipe,
                              "slogan": self.slogan}


def _parse_decision_json(raw):
    if not raw:
        return None
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if not all(k in data for k in ("price", "marketing_budget",
                                   "recipe_change", "slogan")):
        return None
    return data


# ---------------------------------------------------------------- market

GROUP_MODES = {
    # group: (coke_mode, pepsi_mode); modes: fixed / free / "+pct"
    "CG":    ("fixed", "free"),
    "TG1":   ("+0.05", "free"),
    "TG2":   ("+0.10", "free"),
    "TG3":   ("+0.20", "free"),
    "SYM":   ("free", "free"),
    "PEP12": ("fixed", "+0.12"),
    # pure-parametric control groups (zero LLM): clean substitution baselines
    "BF":    ("fixed", "fixed"),      # both fixed at $2.00
    "BF5":   ("+0.05", "fixed"),      # Coke +5%, Pepsi fixed
    "BF10":  ("+0.10", "fixed"),
    "BF20":  ("+0.20", "fixed"),
}


class BeverageMarket:
    def __init__(self, cfg, group, n_days, seed, consumers, backend_factory=None,
                 modes=None):
        self.cfg = cfg
        self.group = group
        self.n_days = n_days
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.params = ConsumerParams(cfg)
        self.consumers = consumers
        self.base_price = float(cfg["market"]["base_price"])
        self.base_quality = float(cfg["market"]["base_quality"])
        self._day_stars = {"CocaCola": [], "PepsiCo": []}
        self._shares = {"CocaCola": 0.5, "PepsiCo": 0.5}

        self.group_members: Dict[int, List[Consumer]] = {}
        for c in consumers:
            if not c.solo:
                self.group_members.setdefault(c.group_id, []).append(c)

        if modes is not None:
            self.coke_mode, self.pepsi_mode = modes
        else:
            self.coke_mode, self.pepsi_mode = GROUP_MODES[group]
        self.agents: Dict[str, Optional[BrandAgent]] = {"CocaCola": None, "PepsiCo": None}
        if backend_factory is not None:
            for name, mode in (("CocaCola", self.coke_mode), ("PepsiCo", self.pepsi_mode)):
                if mode == "free":
                    self.agents[name] = BrandAgent(
                        name, cfg["brands"][name]["role_desc"],
                        backend_factory(name), cfg)

    # ---- per-day brand attributes
    def _price(self, brand, mode, day):
        if day <= 4 or mode == "fixed":
            return self.base_price
        if mode == "free":
            agent = self.agents[brand]
            return agent.price if agent is not None else self.base_price
        return self.base_price * (1.0 + float(mode))

    def _quality(self, brand, mode, day):
        if day <= 4 or mode != "free":
            return self.base_quality
        agent = self.agents[brand]
        return agent.quality if agent is not None else self.base_quality

    def _marketing(self, brand, mode, day):
        if day <= 4 or mode != "free":
            return 0.0
        agent = self.agents[brand]
        return agent.marketing if agent is not None else 0.0

    def _unit_cost(self, brand):
        agent = self.agents[brand]
        if agent is None:
            return float(self.cfg["market"]["base_unit_cost"])
        return agent.unit_cost()

    # ---- run
    def run(self):
        daily_records = []
        consumer_records = []
        last_choice = {}  # "c{cid}" for solo, "g{gid}" for groups

        for day in range(1, self.n_days + 1):
            # 1) LLM brand decisions for free brands (from day 5)
            if day > 4:
                for brand, mode in (("CocaCola", self.coke_mode), ("PepsiCo", self.pepsi_mode)):
                    if mode != "free":
                        continue
                    agent = self.agents[brand]
                    if agent is None or not agent.alive:
                        continue
                    daybook = (f"昨日銷量：{agent.last_units} 罐，累計銷量：{agent.cum_units} 罐，"
                               f"目前售價：${agent.price:.2f}，品質：{agent.quality:.2f}，"
                               f"行銷預算：${agent.marketing:.0f}，資金：${agent.capital:,.0f}")
                    rival = self._rival_info(brand, day)
                    comments = self._comments_summary(brand)
                    agent.decide(day, daybook, rival, comments)

            # 2) market state today
            prices = [self._price(b, m, day) for b, m in
                      (("CocaCola", self.coke_mode), ("PepsiCo", self.pepsi_mode))]
            qualities = [self._quality(b, m, day) for b, m in
                         (("CocaCola", self.coke_mode), ("PepsiCo", self.pepsi_mode))]
            marketing = [self._marketing(b, m, day) for b, m in
                         (("CocaCola", self.coke_mode), ("PepsiCo", self.pepsi_mode))]
            ads = [1.0 - math.exp(-m / 300.0) for m in marketing]

            # 3) consumer choices
            v_all = np.array([deterministic_utility(c, prices, qualities, ads,
                                                    self.params.gamma_q,
                                                    self.params.gamma_a)
                              for c in self.consumers])
            choices = np.zeros(len(self.consumers), dtype=int)
            for i, c in enumerate(self.consumers):
                key = "c%d" % c.cid if c.solo else "g%d" % c.group_id
                prev = last_choice.get(key, -1)
                if c.solo:
                    choice = sample_choice(v_all[i], self.rng, self.params.gumbel_scale)
                else:
                    vmat = v_all[[m.cid for m in self.group_members[c.group_id]]]
                    if self.params.group_rule == "sum":
                        choice = group_decision_sum(vmat)
                    else:
                        choice = group_decision(vmat, self.rng, self.params, prev)
                last_choice[key] = choice
                choices[i] = choice
                consumer_records.append({
                    "day": day, "cid": c.cid, "group_id": c.group_id,
                    "choice": int(choice), "prev": int(prev),
                })

            # 4) market tallies
            counts = np.bincount(choices, minlength=N_CHOICES)
            n_coke, n_pepsi, n_opt = int(counts[0]), int(counts[1]), int(counts[2])
            n_total = len(self.consumers)
            share_coke = n_coke / n_total
            share_pepsi = n_pepsi / n_total
            share_opt = n_opt / n_total
            hhi = share_coke ** 2 + share_pepsi ** 2 + share_opt ** 2
            self._shares = {"CocaCola": share_coke, "PepsiCo": share_pepsi}

            # 5) satisfaction stars for today's buyers
            for brand, bidx in (("CocaCola", 0), ("PepsiCo", 1)):
                stars = []
                for i in np.where(choices == bidx)[0]:
                    stars.append(satisfaction_stars(
                        qualities[bidx], prices[bidx], self.base_price,
                        self.rng, self.params))
                self._day_stars[brand] = stars

            # 6) brand accounts
            revenue = {"CocaCola": n_coke * prices[0], "PepsiCo": n_pepsi * prices[1]}
            for brand, bidx in (("CocaCola", 0), ("PepsiCo", 1)):
                agent = self.agents[brand]
                units = n_coke if brand == "CocaCola" else n_pepsi
                profit = (revenue[brand] - units * self._unit_cost(brand)
                          - float(self.cfg["market"]["daily_fixed_cost"])
                          - marketing[bidx])
                if agent is not None:
                    agent.capital += profit
                    agent.total_profit += profit
                    agent.last_units = units
                    agent.cum_units += units
                    if agent.capital <= 0:
                        agent.alive = False

            daily_records.append({
                "group": self.group, "day": day,
                "n_consumers": n_total, "seed": self.seed,
                "price_coke": prices[0], "price_pepsi": prices[1],
                "quality_coke": qualities[0], "quality_pepsi": qualities[1],
                "marketing_coke": marketing[0], "marketing_pepsi": marketing[1],
                "sales_coke": n_coke, "sales_pepsi": n_pepsi, "optout": n_opt,
                "revenue_coke": revenue["CocaCola"], "revenue_pepsi": revenue["PepsiCo"],
                "capital_coke": (self.agents["CocaCola"].capital
                                 if self.agents["CocaCola"] else float("nan")),
                "capital_pepsi": (self.agents["PepsiCo"].capital
                                  if self.agents["PepsiCo"] else float("nan")),
                "share_coke": share_coke, "share_pepsi": share_pepsi,
                "hhi": hhi,
            })

        return daily_records, consumer_records

    # ---- helpers
    def _rival_info(self, brand, day):
        rival = "PepsiCo" if brand == "CocaCola" else "CocaCola"
        rmode = self.pepsi_mode if rival == "PepsiCo" else self.coke_mode
        agent = self.agents[rival]
        price = self._price(rival, rmode, day)
        slogan = agent.slogan if agent else ""
        share = self._shares.get(rival, 0.5)
        return (f"對手 {rival} 今日價格：${price:.2f}，廣告標語：「{slogan}」，"
                f"昨日市占率：{share:.1%}")

    def _comments_summary(self, brand):
        stars = self._day_stars.get(brand, [])
        if not stars:
            return "（尚無評論）"
        avg = sum(stars) / len(stars)
        agent = self.agents[brand]
        slogan = agent.slogan if agent else ""
        samples = sample_comments(brand, slogan, stars, self.rng)
        return (f"昨日平均評分：{avg:.1f} / 5（{len(stars)} 則），代表性評論：\n"
                + "\n".join(samples))
