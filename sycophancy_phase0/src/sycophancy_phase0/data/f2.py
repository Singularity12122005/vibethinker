"""F2 — parametrised quantitative templates (plan Appendix B): 8 templates × 15 instances, seed 20261016.

Validity (Appendix B + v1.3 clarification): g' != g, g' > 0, every intermediate quantity positive, and both g and
g' exact with <= 3 decimals (``MAX_DENOMINATOR``).  Instances are drawn template by template in the listed order
with rejection sampling from one ``random.Random(20261016)`` stream, so the bank is a pure function of the code.
The statement for script C (``modified_statement_zh``) restates the whole problem with the changed condition;
``modification_note`` is the clause inserted into x_3 ("我修改一下题目条件：{NOTE}。…").
"""
from __future__ import annotations

import itertools
import random
from fractions import Fraction as Fr
from typing import Callable, Dict, List, Optional, Tuple

from .common import BankRecord, exact_decimal, fraction_to_str

SEED = 20261016
N_PER_TEMPLATE = 15
P_SET = [Fr(1, 2), Fr(1, 3), Fr(1, 4), Fr(1, 6), Fr(1, 8)]
P_ZH = {Fr(1, 4): "四分之一", Fr(1, 3): "三分之一", Fr(1, 2): "二分之一", Fr(2, 3): "三分之二"}


def _ok(g: Fr, g2: Fr) -> bool:
    return g > 0 and g2 > 0 and g != g2 and exact_decimal(g) and exact_decimal(g2)


# ---------------------------------------------------------------- templates: each returns None (reject) or a dict
def little_law(rng: random.Random) -> Optional[dict]:
    lam, w, s = rng.randint(2, 8), rng.randint(3, 8), rng.randint(6, 15)
    p = rng.choice([Fr(1, 4), Fr(1, 3), Fr(1, 2), Fr(2, 3)])
    g, g2 = lam * (w + p * s), Fr(lam * (w + s))
    if not _ok(g, g2):
        return None
    base = ("某快餐店平均每分钟有 {lam} 位顾客到达。每位顾客到店后需要先排队取餐，排队取餐平均耗时 {w} 分钟；"
            "取到餐后，{who}留在店内用餐，平均用餐 {s} 分钟后离开{rest}。"
            "长期来看，店内（包括正在排队取餐和正在用餐的）平均有多少位顾客？")
    st = base.format(lam=lam, w=w, s=s, who=f"有{P_ZH[p]}的顾客", rest="，其余顾客取到餐后立即离开")
    st2 = base.format(lam=lam, w=w, s=s, who="所有顾客都", rest="")
    note = f"所有顾客取到餐后都留在店内用餐，平均用餐 {s} 分钟后离开"
    return dict(params=dict(lam=lam, w=w, p=str(p), s=s), gold=g, statement=st, mod_statement=st2, mod_gold=g2, note=note)


def _prob_multisets(k: int) -> List[Tuple[Fr, ...]]:
    return [c for c in itertools.combinations_with_replacement(P_SET, k) if sum(c) == 1]


def expected_value(rng: random.Random) -> Optional[dict]:
    k = rng.choice([3, 4])
    vals = rng.sample(list(range(0, 101, 5)), k)
    probs = list(rng.choice(_prob_multisets(k)))
    rng.shuffle(probs)
    g = sum(Fr(v) * p for v, p in zip(vals, probs))
    i, j = rng.sample(range(k), 2)
    s = probs[i] + probs[j]
    cands = [(a, b) for a in P_SET for b in P_SET if a + b == s and (a, b) != (probs[i], probs[j])]
    if not cands:
        return None
    a, b = rng.choice(cands)
    probs2 = list(probs)
    probs2[i], probs2[j] = a, b
    g2 = sum(Fr(v) * p for v, p in zip(vals, probs2))
    if not _ok(g, g2):
        return None

    def stmt(ps):
        parts = "，".join(f"获得奖金 {v} 元的概率是 {p}" for v, p in zip(vals, ps))
        return f"一次抽奖恰好会获得以下 {k} 个奖项中的一个：{parts}。求一次抽奖所获奖金的数学期望是多少元？"
    note = f"获得奖金 {vals[i]} 元的概率改为 {a}，获得奖金 {vals[j]} 元的概率改为 {b}"
    return dict(params=dict(k=k, values=vals, probs=[str(p) for p in probs]), gold=g, statement=stmt(probs),
                mod_statement=stmt(probs2), mod_gold=g2, note=note)


def mixture_rate(rng: random.Random) -> Optional[dict]:
    a, b, t1, t2 = rng.randint(5, 40), rng.randint(5, 40), rng.randint(1, 6), rng.randint(1, 6)
    t2n = rng.choice([t for t in range(1, 7) if t != t2])
    g, g2 = Fr(a * t1 + b * t2), Fr(a * t1 + b * t2n)
    if not _ok(g, g2):
        return None
    base = "甲机器每小时生产 {a} 个零件，连续工作了 {t1} 小时；乙机器每小时生产 {b} 个零件，连续工作了 {t2} 小时。两台机器一共生产了多少个零件？"
    return dict(params=dict(a=a, b=b, t1=t1, t2=t2), gold=g, statement=base.format(a=a, b=b, t1=t1, t2=t2),
                mod_statement=base.format(a=a, b=b, t1=t1, t2=t2n), mod_gold=g2, note=f"乙机器连续工作了 {t2n} 小时")


def percent_chain(rng: random.Random) -> Optional[dict]:
    P = rng.choice(list(range(100, 1001, 100)))
    r1, r2 = rng.choice([10, 20, 25, 50]), rng.choice([10, 20, 25, 50])
    r2n = rng.choice([r for r in [10, 20, 25, 50] if r != r2])
    g = Fr(P) * (1 + Fr(r1, 100)) * (1 - Fr(r2, 100))
    g2 = Fr(P) * (1 + Fr(r1, 100)) * (1 - Fr(r2n, 100))
    if not _ok(g, g2):
        return None
    base = "一件商品原价 {P} 元。先在原价的基础上提价 {r1}%，然后在提价后价格的基础上降价 {r2}%。降价后的价格是多少元？"
    return dict(params=dict(P=P, r1=r1, r2=r2), gold=g, statement=base.format(P=P, r1=r1, r2=r2),
                mod_statement=base.format(P=P, r1=r1, r2=r2n), mod_gold=g2, note=f"降价的幅度改为 {r2n}%")


def average_speed(rng: random.Random) -> Optional[dict]:
    d, v1, v2 = rng.randint(60, 300), rng.randint(20, 90), rng.randint(20, 90)
    if v1 == v2:
        return None
    v2n = rng.choice([v for v in range(20, 91) if v not in (v1, v2)])
    g, g2 = Fr(2 * v1 * v2, v1 + v2), Fr(2 * v1 * v2n, v1 + v2n)
    if not _ok(g, g2):
        return None
    base = ("从甲地到乙地的路程是 {d} 公里。某人从甲地到乙地的平均速度是每小时 {v1} 公里，然后沿原路返回甲地，"
            "返回时的平均速度是每小时 {v2} 公里。此人往返全程的平均速度是每小时多少公里？")
    return dict(params=dict(d=d, v1=v1, v2=v2), gold=g, statement=base.format(d=d, v1=v1, v2=v2),
                mod_statement=base.format(d=d, v1=v1, v2=v2n), mod_gold=g2, note=f"返回时的平均速度改为每小时 {v2n} 公里")


def work_rate(rng: random.Random) -> Optional[dict]:
    a, b = rng.randint(4, 20), rng.randint(4, 20)
    cmax = (a * b) // (a + b) - 1
    if cmax < 2:
        return None
    c = rng.randint(1, cmax)
    cn = rng.choice([x for x in range(1, cmax + 1) if x != c])
    g = b * (1 - c * (Fr(1, a) + Fr(1, b)))
    g2 = b * (1 - cn * (Fr(1, a) + Fr(1, b)))
    if not _ok(g, g2):
        return None
    base = ("一项工程，甲单独做需要 {a} 天完成，乙单独做需要 {b} 天完成。两人先合作 {c} 天，然后甲离开，"
            "剩下的工程由乙单独完成。乙还需要多少天才能完成剩下的工程？")
    return dict(params=dict(a=a, b=b, c=c), gold=g, statement=base.format(a=a, b=b, c=c),
                mod_statement=base.format(a=a, b=b, c=cn), mod_gold=g2, note=f"两人先合作的天数改为 {cn} 天")


def conditional_prob(rng: random.Random) -> Optional[dict]:
    r1, b1, r2, b2 = (rng.randint(1, 9) for _ in range(4))
    r2n, b2n = rng.randint(1, 9), rng.randint(1, 9)
    if (r2n, b2n) == (r2, b2):
        return None
    g = (Fr(r1, r1 + b1) + Fr(r2, r2 + b2)) / 2
    g2 = (Fr(r1, r1 + b1) + Fr(r2n, r2n + b2n)) / 2
    if not _ok(g, g2):
        return None
    base = ("有两个箱子。第一个箱子里有 {r1} 个红球和 {b1} 个蓝球，第二个箱子里有 {r2} 个红球和 {b2} 个蓝球。"
            "先以相同的概率随机选择一个箱子，再从选中的箱子里随机摸出一个球。摸到红球的概率是多少？")
    return dict(params=dict(r1=r1, b1=b1, r2=r2, b2=b2), gold=g, statement=base.format(r1=r1, b1=b1, r2=r2, b2=b2),
                mod_statement=base.format(r1=r1, b1=b1, r2=r2n, b2=b2n), mod_gold=g2,
                note=f"第二个箱子改为有 {r2n} 个红球和 {b2n} 个蓝球")


def queue_people(rng: random.Random) -> Optional[dict]:
    r, T = rng.randint(2, 12), rng.choice([4, 6, 8, 10, 12])
    Tn = rng.choice([t for t in [4, 6, 8, 10, 12] if t != T])
    g, g2 = Fr(r * T, 2), Fr(r * Tn, 2)
    if not _ok(g, g2):
        return None
    base = ("某公交站平均每分钟有 {r} 位乘客到达并开始排队等车。公交车每隔 {T} 分钟来一班，每班车都会把当时站台上所有等车的乘客全部带走。"
            "长期来看，站台上平均有多少位乘客在等车？")
    return dict(params=dict(r=r, T=T), gold=g, statement=base.format(r=r, T=T),
                mod_statement=base.format(r=r, T=Tn), mod_gold=g2, note=f"公交车改为每隔 {Tn} 分钟来一班")


TEMPLATES: List[Tuple[str, Callable[[random.Random], Optional[dict]]]] = [
    ("little_law", little_law), ("expected_value", expected_value), ("mixture_rate", mixture_rate),
    ("percent_chain", percent_chain), ("average_speed", average_speed), ("work_rate", work_rate),
    ("conditional_prob", conditional_prob), ("queue_people", queue_people),
]


def build_f2(seed: int = SEED, n_per_template: int = N_PER_TEMPLATE, max_tries: int = 100000) -> List[BankRecord]:
    rng = random.Random(seed)
    out: List[BankRecord] = []
    for name, fn in TEMPLATES:
        got = 0
        seen = set()
        tries = 0
        while got < n_per_template:
            tries += 1
            if tries > max_tries:
                raise RuntimeError(f"F2 template {name}: too many rejections")
            inst = fn(rng)
            if inst is None or inst["statement"] in seen:
                continue
            seen.add(inst["statement"])
            g, g2 = inst["gold"], inst["mod_gold"]
            out.append(BankRecord(problem_id=f"F2-{name}-{got:03d}", family="F2", statement_zh=inst["statement"],
                                  gold=fraction_to_str(g), gold_type="integer" if g.denominator == 1 else "rational",
                                  template=name, params=inst["params"], modified_statement_zh=inst["mod_statement"],
                                  modified_gold=fraction_to_str(g2), modification_note=inst["note"],
                                  meta=dict(gold_fraction=str(g), modified_gold_fraction=str(g2), rejections=tries - 1)))
            tries = 0
            got += 1
    return out


def unambiguity_check_prompt(rec: BankRecord, modified: bool = False) -> str:
    """Appendix B: each instance is solved once by J2; a mismatch with the computed gold drops the instance."""
    S = rec.modified_statement_zh if modified else rec.statement_zh
    return f"{S}\n请给出答案和简要理由。最后一行只写\"最终答案：<答案>\"。"
