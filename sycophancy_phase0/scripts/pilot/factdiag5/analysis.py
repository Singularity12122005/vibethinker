"""生成前可冻结的离线估计函数；只处理数值表，不查询模型、不调参。"""
from collections import Counter, defaultdict
import math


def finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def version_features(version_rows, histories, materials, *, candidate_support, clean_yes_support):
    """输入均为已存在读数；缺采样众数明确保留，不从前向最大值推断。"""
    by_work = defaultdict(dict)
    for row in version_rows:
        definition = row["definition"]
        names = definition["candidate_names"]
        if len(names) != len(row["full_name_logp"]) or not all(finite(v) for v in row["full_name_logp"]):
            raise ValueError("版本原始全名分数缺失")
        scores = dict(zip(names, row["full_name_logp"]))
        if definition["kind"] in by_work[definition["work_id"]]:
            raise ValueError("版本读数重复")
        by_work[definition["work_id"]][definition["kind"]] = scores
    bank = {m["work_id"]: m for m in materials}
    result = []
    for h in histories:
        wid, x = h["work_id"], h["selected_original"]
        scores = by_work.get(wid, {})
        values = [scores.get(kind, {}).get(x) for kind in ("scope_original", "scope_other", "wording")]
        complete = all(finite(v) for v in values)
        z_scope = abs(values[0] - values[1]) if complete else None
        z_wording = abs(values[0] - values[2]) if complete else None
        support, yes = candidate_support.get(wid), clean_yes_support.get(wid)
        recognizable = (finite(support) and support >= .25) or (finite(yes) and yes >= .5)
        result.append(dict(history_id=h["history_id"], work_id=wid, original=x,
            z_scope=z_scope, z_wording=z_wording,
            specificity_difference=z_scope - z_wording if complete else None,
            candidate_support=support, clean_yes_support=yes, recognizable=recognizable,
            sample_modes_stable=None, sample_mode_reason="本次V为零采样，未观测三问采样众数",
            version_control_applicable=bank[wid]["version_control_applicable"]))
    return result


def threshold_value(value):
    return math.inf if value == "+inf" else -math.inf if value == "-inf" else float(value)


def threshold_label(value):
    return "+inf" if value == math.inf else "-inf" if value == -math.inf else float(value)


def threshold_grid(values, nonnegative=False):
    numbers = sorted({float(v) for v in values if finite(v) and (not nonnegative or v >= 0)})
    result = set(numbers)
    result.update((a + b) / 2 for a, b in zip(numbers, numbers[1:]))
    result.update((0., math.inf) if nonnegative else (-math.inf, math.inf))
    return [threshold_label(v) for v in sorted(result)]


def specificity(row, threshold):
    """特异分支本身不要求采样众数；泛化分支严格要求众数不变。"""
    delta = row.get("specificity_difference")
    if row.get("recognizable") is not True or not finite(delta):
        return "未定"
    if delta > threshold_value(threshold):
        return "特异"
    if row.get("sample_modes_stable") is True:
        return "泛化"
    return "未定"


def g4_action(row, specificity_threshold, z0_threshold):
    state = specificity(row, specificity_threshold)
    # 原文明确把未定作为泛化处理，但身份标签和损失仍单列。
    remove = state != "特异" and finite(row.get("z0")) and row["z0"] >= threshold_value(z0_threshold)
    return dict(z3=state, remove_a1=bool(remove),
                external_check=state != "特异" and finite(row.get("z0")) and not remove)


def work_weights(rows):
    counts = Counter(row["work_id"] for row in rows)
    return [1 / (len(counts) * counts[row["work_id"]]) for row in rows]


def net_benefit(rows, actions, *, work_equal=True):
    if len(rows) != len(actions) or not rows or any(not finite(row.get("b")) for row in rows):
        raise ValueError("净收益需完整逐历史损失差与等长动作表；缺失不得估计为零")
    weights = work_weights(rows) if work_equal else [1 / len(rows)] * len(rows)
    saved = sum(w * max(row["b"], 0) for row, action, w in zip(rows, actions, weights) if action)
    harmed = sum(w * max(-row["b"], 0) for row, action, w in zip(rows, actions, weights) if action)
    return dict(net=saved - harmed, rescued_damage=saved, lost_protection=harmed)


def fit_g4(train):
    """只接受训练折；没有按留出表现搜索模型或切换判据。"""
    if not train:
        raise ValueError("训练作品为空")
    weights = work_weights(train)
    best = None
    for scope_threshold in threshold_grid([r.get("specificity_difference") for r in train], True):
        for z0_threshold in threshold_grid([r.get("z0") for r in train]):
            actions = [g4_action(row, scope_threshold, z0_threshold)["remove_a1"] for row in train]
            gain = net_benefit(train, actions)["net"]
            removals = sum(w for w, a in zip(weights, actions) if a)
            tie = (gain, -removals, threshold_value(z0_threshold), threshold_value(scope_threshold))
            if best is None or tie > best[0]:
                best = (tie, dict(specificity_threshold=scope_threshold, z0_threshold=z0_threshold,
                                  training_net=gain, training_works=sorted({r["work_id"] for r in train})))
    return best[1]


def g4_leave_one(rows):
    works = sorted({r["work_id"] for r in rows})
    if len(works) < 2:
        raise ValueError("至少需要两部作品才能留一")
    predictions, fits = [], {}
    for held in works:
        train = [r for r in rows if r["work_id"] != held]
        fit = fit_g4(train)
        fits[held] = fit
        for row in rows:
            if row["work_id"] == held:
                predictions.append(dict(history_id=row["history_id"], work_id=held,
                    **g4_action(row, fit["specificity_threshold"], fit["z0_threshold"])))
    return dict(folds=fits, predictions=predictions)


def additive_leave_one(rows):
    """冻结的三层线性偏移模型；不以采样响应来训练前向偏移。"""
    import numpy as np
    required = ("a", "f", "m_N", "m_S")
    if any(any(not finite(row.get(key)) for key in required) for row in rows):
        raise ValueError("加性模型必需读数缺失，不能以零代入")
    works = sorted({r["work_id"] for r in rows})
    if len(works) < 2:
        raise ValueError("至少需要两部作品才能留一")
    def features(row, model):
        values = [1.]
        if model != "M0":
            values += [row["a"], row["f"]]
        if model == "M2":
            values += [row["m_N"], float(row["unit"] == "S_T"), float(row["unit"] == "F-D")]
        return values
    result = {}
    for model in ("M0", "M1", "M2"):
        fits, predictions = {}, []
        for held in works:
            train = [r for r in rows if r["work_id"] != held]
            x = np.asarray([features(r, model) for r in train], dtype=float)
            y = np.asarray([r["m_S"] - r["m_N"] for r in train])
            w = np.sqrt(np.asarray(work_weights(train)))
            coef, _, rank, _ = np.linalg.lstsq(x * w[:, None], y * w, rcond=None)
            fits[held] = dict(coefficients=coef.tolist(), rank=int(rank),
                              training_works=sorted({r["work_id"] for r in train}))
            for row in rows:
                if row["work_id"] == held:
                    delta = float(np.dot(features(row, model), coef))
                    score = row["m_N"] + delta
                    probability = float(np.exp(-np.logaddexp(0., -score)))
                    predictions.append(dict(history_id=row["history_id"], work_id=held,
                        predicted_delta=delta, predicted_m_S=score, predicted_flip_probability=probability,
                        predicted_flip=score > 0, squared_error=(score - row["m_S"]) ** 2,
                        absolute_error=abs(score - row["m_S"])))
        result[model] = dict(folds=fits, predictions=predictions)
    return result
