"""诊断实例：隐藏成员只在构造与精确枚举时存在。"""
from dataclasses import asdict, dataclass
from fractions import Fraction
from itertools import combinations
from math import comb
import random

SEED = 20261027
BOX_PROTOCOL = (
    "The prize is placed uniformly at random in one of the {n} boxes. "
    "You initially choose box {initial}. The host, who knows where the prize is, opens one "
    "of the other boxes that is empty (choosing uniformly at random if more than one is empty). "
    "You have observed that the host opened box {opened} "
    "and it was empty. What is the conditional probability of winning if you switch "
    "to box {switch}? Give the answer as a fraction in lowest terms, like 3/8."
)


def canonical(value):
    value = Fraction(value)
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


@dataclass
class Instance:
    instance_id: str
    family: str
    level: int
    spec_public: dict
    question_en: str
    gold: str
    trap: str
    trap_name: str

    def public(self):
        return asdict(self)

    @property
    def spec(self):
        return dict(family=self.family,level=self.level,**self.spec_public)


def _solve_formula(family, level, s):
    if family == "F1":
        if level == 1:
            return s["population"] - s["A"] - s["B"] + s["AB"]
        pairs = s["AB"] + s["AC"] + s["BC"]
        if level == 2:
            return s["A"] + s["B"] + s["C"] - 2 * pairs + 3 * s["ABC"]
        return Fraction(3 * s["at_least_two"] - pairs, 2)
    if family == "F2":
        if level in (1, 2):
            counts = s["color_counts"]
            n = sum(counts.values())
            if level == 1:
                return Fraction(sum(comb(c, 2) for c in counts.values()), comb(n, 2))
            r = counts["red"]
            return Fraction(comb(r, 2), comb(n, 2) - comb(n-r, 2))
        return Fraction(s["n"]-1, s["n"] * (s["n"]-2))
    return s["groups"] * s["per_group"] + s["added"] - s["removed"]


def _solve_enumerate(family, level, s):
    if family == "F1":
        answers=set()
        if level == 1:
            for both in range(min(s["A"],s["B"])+1):
                cells=[both,s["A"]-both,s["B"]-both,s["population"]-s["A"]-s["B"]+both]
                if both==s["AB"] and min(cells)>=0:
                    answers.add(cells[-1])
        else:
            # 独立枚举三交自由整数；逐一检验全部公开约束及八个互斥Venn单元。
            for triple in range(min(s["AB"],s["AC"],s["BC"])+1):
                ab,ac,bc=s["AB"]-triple,s["AC"]-triple,s["BC"]-triple
                a,b,c=s["A"]-ab-ac-triple,s["B"]-ab-bc-triple,s["C"]-ac-bc-triple
                outside=s["population"]-sum((a,b,c,ab,ac,bc,triple))
                if min(a,b,c,ab,ac,bc,triple,outside)<0:
                    continue
                if level==2 and triple==s["ABC"]:
                    answers.add(a+b+c)
                if level==3 and ab+ac+bc+triple==s["at_least_two"]:
                    answers.add(ab+ac+bc)
        if len(answers)!=1:
            raise ValueError("公开约束不能确定唯一可行目标")
        return answers.pop()
    if family == "F2" and level in (1, 2):
        balls = [color for color, n in s["color_counts"].items() for _ in range(n)]
        pairs = list(combinations(range(len(balls)), 2))
        if level == 2:
            pairs = [(a,b) for a,b in pairs if balls[a] == "red" or balls[b] == "red"]
        return Fraction(sum(balls[a] == balls[b] and (level == 1 or balls[a] == "red")
                            for a,b in pairs), len(pairs))
    if family == "F2":
        denominator, numerator = Fraction(0), Fraction(0)
        for prize in range(1, s["n"]+1):
            eligible = [b for b in range(1, s["n"]+1) if b != s["initial"] and b != prize]
            for opened in eligible:
                if opened == s["opened"]:
                    weight = Fraction(1, s["n"] * len(eligible))
                    denominator += weight
                    if prize == s["switch"]:
                        numerator += weight
        return numerator / denominator
    objects = [1 for _ in range(s["groups"]) for _ in range(s["per_group"])]
    objects.extend([1] * s["added"])
    for _ in range(s["removed"]):
        objects.pop()
    return len(objects)


def _trap_solution(family, level, s):
    if family == "F1":
        if level == 1:
            return s["population"] - s["A"] - s["B"]
        if level == 2:
            return s["A"]+s["B"]+s["C"] - 2*(s["AB"]+s["AC"]+s["BC"]) + s["ABC"]
        return s["at_least_two"]
    if family == "F2":
        if level == 3:
            return Fraction(1, s["n"]-1)
        counts = s["color_counts"]
        n = sum(counts.values())
        if level == 1:
            return sum((Fraction(c, n)**2 for c in counts.values()), Fraction(0))
        return Fraction(counts["red"]-1, n-1)
    return s["groups"] * s["per_group"] + s["added"]


def _render(family, level, s):
    if family == "F1":
        text = f"In a group of {s['population']} students, exactly {s['A']} play chess, exactly {s['B']} play go, "
        if level == 1:
            return text + (f"and exactly {s['AB']} play both chess and go. "
                           "How many students play neither? Give the answer as an integer.")
        text += (f"and exactly {s['C']} play checkers. Exactly {s['AB']} play both chess and go, "
                 f"exactly {s['AC']} play both chess and checkers, and exactly {s['BC']} play both go and checkers. "
                 "Each pairwise count includes students who play all three games. ")
        if level == 2:
            return text + (f"Exactly {s['ABC']} play all three games. How many students play exactly one of these games? "
                           "Give the answer as an integer.")
        return text + (f"Exactly {s['at_least_two']} play at least two of these games. "
                       "How many students play exactly two of these games? Give the answer as an integer.")
    if family == "F2":
        if level == 3:
            return BOX_PROTOCOL.format(**s)
        colors = ", ".join(f"{n} {color}" for color,n in s["color_counts"].items())
        text = (f"A bag contains {colors} balls and no others. One ball is drawn uniformly at random; "
                "without putting it back, a second ball is drawn uniformly at random from the remaining balls. ")
        if level == 1:
            return text + "What is the probability that the two balls have the same color? Give the answer as a fraction in lowest terms, like 3/8."
        return text + ("Given that at least one of the two balls is red, what is the probability that both are red? "
                       "Give the answer as a fraction in lowest terms, like 3/8.")
    return (f"A store has {s['groups']} boxes with {s['per_group']} notebooks in each box. "
            f"It then receives {s['added']} more notebooks and afterwards sells {s['removed']} notebooks. "
            "How many notebooks remain? Give the answer as an integer.")


def generate(family, level, seed):
    rng = random.Random(seed)
    members = None
    if family == "F1":
        n = rng.randint(20, 60)
        k = 2 if level == 1 else 3
        # 独立成员关系；轻度稀疏使非负的指定错误答案有足够可用实例。
        members = [sum((1 << j) for j in range(k) if rng.random() < .35) for _ in range(n)]
        s = dict(population=n, A=sum(bool(m&1) for m in members), B=sum(bool(m&2) for m in members),
                 AB=sum(m&3 == 3 for m in members))
        if k == 3:
            s.update(C=sum(bool(m&4) for m in members), AC=sum(m&5 == 5 for m in members),
                     BC=sum(m&6 == 6 for m in members), pairwise_includes_triple=True)
            if level == 2:
                s["ABC"] = sum(m == 7 for m in members)
            else:
                s["at_least_two"] = sum(m.bit_count() >= 2 for m in members)
        s["target"] = {1: "neither_A_nor_B", 2: "exactly_one", 3: "exactly_two"}[level]
        name = {1: "forget_intersection", 2: "triple_once", 3: "atleast_as_exactly"}[level]
    elif family == "F2":
        if level < 3:
            n, k = rng.randint(6,12), rng.choice([2,3])
            cuts = sorted(rng.sample(range(1,n), k-1))
            counts = [b-a for a,b in zip([0]+cuts, cuts+[n])]
            s = dict(color_counts=dict(zip(["red","blue","green"], counts)), replacement=False,
                     draws=2, target="same_color" if level == 1 else "both_red",
                     condition="none" if level == 1 else "at_least_one_red")
        else:
            n = rng.choice([3,4])
            initial, opened, switch = rng.sample(range(1,n+1),3)
            s = dict(n=n, initial=initial, opened=opened, switch=switch, prize_uniform=True,
                     host_knows_prize=True, host_opens_one_other_empty=True,
                     host_uniform_among_eligible=True, observed_opened_empty=True,
                     target="switch_to_specified_box")
        name = {1: "as_with_replacement", 2: "condition_on_first_red", 3: "naive_uniform"}[level]
    else:
        s = dict(groups=rng.randint(3,12), per_group=rng.randint(4,15), added=rng.randint(3,30),
                 removed=rng.randint(1,10), target="remaining_notebooks")
        name = "skip_last_step"
    spec=dict(family=family,level=level,**s)
    gold, enumerated, trap = (canonical(solve_formula(spec)),
        canonical(solve_enumerate(spec)), canonical(trap_solution(spec)))
    if members is not None and int(Fraction(gold)) != sum(m.bit_count()=={1:0,2:1,3:2}[level] for m in members):
        raise ValueError("隐藏成员直接计数与公开规格求解不符")
    if gold != enumerated or gold == trap or (family == "F1" and Fraction(trap)<0):
        raise ValueError("公式、枚举或不同且非负错误答案条件未通过")
    return Instance(f"{family}-L{level}-{seed:06d}",family,level,s,render(spec),gold,trap,name)


def solve_formula(spec):
    return canonical(_solve_formula(spec["family"],spec["level"],spec))


def solve_enumerate(spec):
    return canonical(_solve_enumerate(spec["family"],spec["level"],spec))


def trap_solution(spec):
    return canonical(_trap_solution(spec["family"],spec["level"],spec))


def render(spec):
    return _render(spec["family"],spec["level"],spec)


GROUPS = [(f,l,20) for f in ("F1","F2") for l in (1,2,3)] + [("R1",1,10)]


def schema_public(spec):
    """仅公开键名与类型；反译时绝不传入该实例字段值。"""
    return {key: schema_public(value) if isinstance(value,dict) else
            "boolean" if isinstance(value,bool) else "integer" if isinstance(value,int) else "string"
            for key,value in spec.items()}
