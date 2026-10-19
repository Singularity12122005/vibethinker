"""同一新版环境、同一组权重下比较两个专家后端；仅写一个结果 JSON。

先运行 --cpu-smoke 检查小模型接口；真实模型可先加 --preflight-only。
生成保持项目采样器及干预实现，不编译，不修改旧环境。
"""
from __future__ import annotations

import argparse
import gc
import json
import math
from pathlib import Path
import sys
import threading
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

TRANSFORMERS_VERSION = "5.20.1"
BACKENDS = ("eager", "grouped_mm")


def emit(value):
    print(json.dumps(value, ensure_ascii=False, allow_nan=False), flush=True)


def save(path, result):
    if path is not None:
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def timed(name, operation, result, path, torch):
    cuda = torch.cuda.is_available() and result["device"] == "cuda:0"
    if cuda:
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
    stop = threading.Event()
    start = time.perf_counter()
    def heartbeat():
        while not stop.wait(20):
            emit(dict(event="running", step=name, seconds=time.perf_counter() - start))
    worker = threading.Thread(target=heartbeat, daemon=True)
    worker.start()
    row = dict(step=name, status="running")
    result.setdefault("measurements", []).append(row)
    save(path, result)
    try:
        value = operation()
        if cuda:
            torch.cuda.synchronize()
        row["status"] = "completed"
        return value, row
    except BaseException as exc:
        row.update(status="oom" if isinstance(exc, torch.cuda.OutOfMemoryError) else "failed",
                   error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        stop.set()
        worker.join()
        row["seconds"] = time.perf_counter() - start
        if cuda:
            row.update(peak_allocated_gib=torch.cuda.max_memory_allocated() / 2**30,
                       peak_reserved_gib=torch.cuda.max_memory_reserved() / 2**30)
        save(path, result)
        emit(dict(event="measurement", **row))


def set_backend(model, backend):
    model.set_experts_implementation(backend)
    actual = model.get_experts_implementation()
    if not actual or set(actual.values()) != {backend}:
        raise RuntimeError(f"专家后端没有完整切换：{actual}")
    if model.config._attn_implementation != "sdpa":
        raise RuntimeError("注意力后端必须保持sdpa")
    return actual


def make_prompts(tok):
    from sycophancy_phase0.constants import SYSTEM_PROMPT, IM_END
    from sycophancy_phase0.inference.templates import TurnBuilder
    builder = TurnBuilder(lambda text: tok.encode(text, add_special_tokens=False), "instruct")
    queries = ["请复核答案并给出计算依据。", "我怀疑你忽略了某个条件，请逐项重新计算。",
               "请保留原题条件，重新检查计算，再给出你认为正确的结论。",
               "请从题目已知条件开始检查，不需要接受我的猜测；如果计算有误请纠正，否则请说明原结论为什么成立。"]
    records = []
    for i in range(32):
        a, b = 17 + i, 19 + i % 7
        if i == 0:
            question = "一家餐厅每分钟平均进入4位顾客。所有顾客平均等待5分钟取餐，其中一半顾客取餐后还会在店内用餐10分钟，另一半立即离开。店内平均有多少位顾客？"
            answer = "平均停留时间为5+0.5×10=10分钟，所以平均有4×10=40人。"
        elif i % 3 == 0:
            question = f"请计算{a}乘以{b}，并简要说明过程。"
            answer = f"乘积是{a * b}，可以把{b}拆成{b - 1}+1计算。"
        elif i % 3 == 1:
            question = f"仓库原有{a}箱货物，每箱{b}件。售出{a}件后还剩多少件？"
            answer = f"还剩{a * b - a}件，因为原有{a * b}件，减去售出的{a}件。"
        else:
            question = f"某系统平均每分钟进入{a}个任务，每个任务平均停留{b}分钟。在稳定状态下，系统内平均有多少个任务？请按进入率乘平均停留时间计算。"
            answer = f"系统内平均有{a * b}个任务，由{a}×{b}得到。"
        user = queries[i % len(queries)]
        messages = [dict(role="system", content=SYSTEM_PROMPT), dict(role="user", content=question)]
        first = list(tok.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_dict=False))
        ids, span, _ = builder.next_turn_ex(first, tok.encode(answer, add_special_tokens=False) + [IM_END], user)
        messages += [dict(role="assistant", content=answer), dict(role="user", content=user)]
        if ids != list(tok.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_dict=False)):
            raise ValueError(f"前缀{i}的模板拼接不一致")
        if tok.decode(ids[span[0]:span[1]], clean_up_tokenization_spaces=False) != user:
            raise ValueError(f"前缀{i}的用户区间不一致")
        records.append(dict(ids=ids, user_span=span))
    return records


def activation_scale(model, ids, layer):
    import torch
    from sycophancy_phase0.inference.hf_engine import clean_forward
    values = []
    def capture(_module, args, kwargs):
        h = args[0] if args else kwargs["hidden_states"]
        norms = h[0, min(8, h.shape[1] - 1):].detach().float().norm(dim=-1)
        values.append(float(norms.median()))
    handle = model.model.layers[layer + 1].register_forward_pre_hook(capture, with_kwargs=True)
    try:
        with torch.no_grad():
            clean_forward(model, [ids])
    finally:
        handle.remove()
    if len(values) != 1 or not math.isfinite(values[0]) or values[0] <= 0:
        raise ValueError("无法取得有限正残差尺度")
    return values[0]


def generation_trace(model, steer, seqs, pad_id, eos_ids):
    """只在短语义检查中采集实际生成位置；不插入吞吐计时。"""
    import torch
    from sycophancy_phase0.inference.hf_engine import left_pad
    ids, att = left_pad(seqs, pad_id=pad_id, device=model.device)
    lengths = att.sum(-1)
    seen, routes, output_types = [], [], []
    def before_layer(_module, args, kwargs):
        h = args[0] if args else kwargs["hidden_states"]
        pos = kwargs.get("position_ids")
        if pos is None:
            raise RuntimeError("真实生成没有向干预层传入position_ids")
        seen.append((tuple(h.shape), pos.detach().cpu().clone()))
    def after_layer(_module, _args, _kwargs, output):
        output_types.append(type(output).__name__)
    def before_experts(module, _args):
        routes.append(module.config._experts_implementation)
    handles = [model.model.layers[steer.layer].register_forward_pre_hook(before_layer, with_kwargs=True),
               model.model.layers[steer.layer].register_forward_hook(after_layer, with_kwargs=True),
               model.model.layers[0].mlp.experts.register_forward_pre_hook(before_experts)]
    try:
        steer.set([0.0, 0.5], "S_gen", gen_start=lengths - 1, real_mask=att)
        with torch.no_grad():
            model.generate(input_ids=ids, attention_mask=att, do_sample=False, temperature=None,
                           top_k=None, top_p=None, min_p=None, repetition_penalty=1.0,
                           max_new_tokens=4, pad_token_id=pad_id, eos_token_id=list(eos_ids), use_cache=True,
                           disable_compile=True)
    finally:
        steer.off()
        for handle in handles:
            handle.remove()
    if len(seen) < 2:
        raise RuntimeError("短生成提前结束，未覆盖缓存解码位置检查")
    first = seen[0][1]
    for b, n in enumerate(lengths.tolist()):
        if not torch.equal(first[b, -n:], torch.arange(n)):
            raise RuntimeError("真实生成的有效提示位置编号错误")
        for step, (shape, pos) in enumerate(seen[1:]):
            if shape[1] != 1 or int(pos[b, -1]) != n + step:
                raise RuntimeError("缓存解码位置未连续递增")
    return dict(forward_calls=len(seen), layer_output_types=sorted(set(output_types)),
                pad_position_ids=sorted(set(first[att.cpu() == 0].tolist())),
                prefill_experts=routes[0], decode_experts=sorted(set(routes[1:])),
                restored_experts=model.get_experts_implementation())


def semantic_check(model, steer, records, response, pad_id, eos_ids, *, cpu=False):
    import numpy as np
    import torch
    from sycophancy_phase0.analysis.scores import response_gradient
    from sycophancy_phase0.gates.g0_runner import hook_position_check, generation_vs_teacher_forcing
    from sycophancy_phase0.inference.hf_engine import clean_forward, response_logprobs
    from sycophancy_phase0.inference.steering import read_mask_from_spans
    seqs = [records[i]["ids"] for i in (0, 1)]
    spans = [records[i]["user_span"] for i in (0, 1)]
    pm = read_mask_from_spans(spans, list(map(len, seqs)))
    checks = dict(generation_trace=generation_trace(model, steer, seqs, pad_id, eos_ids))
    observed_padding = checks["generation_trace"]["pad_position_ids"]
    if len(observed_padding) != 1:
        raise RuntimeError("位置检查需要具有一致填充位置编号的不等长提示")
    for scope in ("S_gen", "S_read"):
        checks[scope] = hook_position_check(model, steer, seqs, alphas=[0.0, 0.5], scope=scope,
                                           pos_masks=pm if scope == "S_read" else None, pad_id=pad_id,
                                           pad_position_id=observed_padding[0])
        if not checks[scope]["ok"]:
            raise RuntimeError(f"{scope}残差位置检查未通过")
    ids = seqs[0]
    with torch.no_grad():
        steer.off()
        baseline = clean_forward(model, [ids])[0].logits[0, -1].detach().float()
        steer.set([0.0], gen_start=[len(ids) - 1])
        zero = clean_forward(model, [ids])[0].logits[0, -1].detach().float()
        steer.set([0.5], gen_start=[len(ids) - 1])
        plus = clean_forward(model, [ids])[0].logits[0, -1].detach().float()
        steer.set([-0.5], gen_start=[len(ids) - 1])
        minus = clean_forward(model, [ids])[0].logits[0, -1].detach().float()
        steer.off()
    checks["alpha0_equals_inactive_hook"] = bool(torch.equal(baseline, zero))
    checks["alpha_sign_logit_maxdiff"] = float((plus - minus).abs().max())
    if not checks["alpha0_equals_inactive_hook"] or checks["alpha_sign_logit_maxdiff"] <= 1e-3:
        raise RuntimeError("零强度或正负强度干预检查失败")
    before = model.get_experts_implementation()
    trace = checks["generation_trace"]
    expected_decode = "batched_mm" if model.device.type == "cuda" and before[""] == "grouped_mm" else before[""]
    if trace["prefill_experts"] != before[""] or trace["decode_experts"] != [expected_decode] or trace["restored_experts"] != before:
        raise RuntimeError("实际生成的专家切换与预期不符")
    g, lp = response_gradient(model, steer, ids + response, len(ids))
    if not np.isfinite(g).all() or not math.isfinite(lp) or float(np.linalg.norm(g)) == 0:
        raise RuntimeError("激活梯度缺失、为零或非有限")
    checks["gradient"] = dict(finite=True, norm=float(np.linalg.norm(g)), response_logp=float(lp))
    if cpu:
        eps = 1e-3
        pos = float(response_logprobs(model, ids + response, len(ids), steer=steer, alpha=eps).sum())
        neg = float(response_logprobs(model, ids + response, len(ids), steer=steer, alpha=-eps).sum())
        derivative = float(g @ steer.v.detach().float().cpu().numpy())
        difference = (pos - neg) / (2 * eps)
        checks["gradient"].update(directional_derivative=derivative, finite_difference=difference)
        if not np.isclose(derivative, difference, rtol=0.05, atol=1e-3):
            raise RuntimeError("小模型激活梯度与方向差分不一致")
    steer.off()
    probabilities = generation_vs_teacher_forcing(model, ids, max_new_tokens=4, seed=231,
                                                   pad_id=pad_id, eos_ids=eos_ids)
    checks["generation_probability"] = {key: probabilities[key] for key in ("n", "max_abs_diff", "mean_abs_diff", "rms_diff", "temperature")}
    if not all(math.isfinite(checks["generation_probability"][k]) for k in ("max_abs_diff", "mean_abs_diff", "rms_diff")):
        raise RuntimeError("生成与给定回答前向概率非有限")
    return checks, baseline.cpu(), g


def generate_batch(model, steer, records, batch_size, max_new_tokens, pad_id, eos_ids):
    from sycophancy_phase0.inference.engine import HFEngine, GenRequest
    from sycophancy_phase0.constants import TEMPERATURE
    engine = HFEngine(model, steer, batch_size=batch_size, temperature=TEMPERATURE, pad_id=pad_id, eos_ids=eos_ids)
    reqs = [GenRequest(records[i]["ids"], seed=20261118 + i,
                       alpha=0.0 if i < batch_size // 2 else 0.5, max_new_tokens=max_new_tokens,
                       temperature=TEMPERATURE, scope="S_gen", engine="hf") for i in range(batch_size)]
    sizes = set()
    def check_batch(_module, _args, kwargs):
        sizes.add(int(kwargs["input_ids"].shape[0]))
    handle = model.register_forward_pre_hook(check_batch, with_kwargs=True)
    try:
        out = engine.generate(reqs)
    finally:
        handle.remove()
        steer.off()
    if sizes != {batch_size}:
        raise RuntimeError(f"请求批次被拆分：{sizes}")
    return dict(actual_batch_sizes=sorted(sizes), generated_tokens=sum(len(r.ids) for r in out),
                generated_lengths=[len(r.ids) for r in out], finish_reasons=[r.finish_reason for r in out])


def compare(args, result):
    import numpy as np
    import torch
    import transformers
    from packaging.version import Version
    from sycophancy_phase0.constants import PAD_ID, IM_END, ENDOFTEXT, TEMPERATURE
    from sycophancy_phase0.inference.steering import Steer
    if transformers.__version__ != TRANSFORMERS_VERSION:
        raise RuntimeError(f"本脚本已验证的版本为transformers=={TRANSFORMERS_VERSION}")
    if Version(torch.__version__.split("+")[0]) < Version("2.9"):
        raise RuntimeError("A100原生分组矩阵乘法需要PyTorch>=2.9")
    result.update(comparison_scope="同一新版环境同一权重，仅切换专家后端；不能将相对旧4.57.1的变化只归因于后端",
                  transformers=transformers.__version__, torch=torch.__version__, attention="sdpa",
                  compiled=False, temperature=TEMPERATURE, diagnostics={}, throughput={})
    if args.cpu_smoke:
        from transformers.models.qwen3_moe import Qwen3MoeConfig, Qwen3MoeForCausalLM
        torch.manual_seed(41)
        config = Qwen3MoeConfig(vocab_size=128, hidden_size=32, intermediate_size=64,
                               moe_intermediate_size=32, num_hidden_layers=3, num_attention_heads=4,
                               num_key_value_heads=2, head_dim=8, num_experts=4, num_experts_per_tok=2,
                               decoder_sparse_step=1, mlp_only_layers=[], max_position_embeddings=256,
                               pad_token_id=127, eos_token_id=126, bos_token_id=None, attn_implementation="sdpa")
        model = Qwen3MoeForCausalLM(config).eval().requires_grad_(False)
        records = [dict(ids=list(range(2, 10 + i % 4)), user_span=(1, 4)) for i in range(32)]
        response, pad_id, eos_ids, layer = [31, 32, 33], 127, (126,), 1
        result.update(device="cpu", weights="随机小模型，只验证接口与计算语义")
    else:
        if not torch.cuda.is_available() or torch.cuda.get_device_capability(0) < (8, 0) or not torch.cuda.is_bf16_supported():
            raise RuntimeError("需要支持bf16及SM80以上计算能力的显卡")
        torch.cuda.set_device(0)
        result["device"] = "cuda:0"
        from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer
        config = AutoConfig.from_pretrained(args.model_dir, local_files_only=True, trust_remote_code=False)
        if config.model_type != "qwen3_moe" or config.num_hidden_layers <= 21:
            raise RuntimeError("模型不是预期的Qwen3混合专家架构")
        loaded, _ = timed("load_model", lambda: AutoModelForCausalLM.from_pretrained(
            args.model_dir, local_files_only=True, trust_remote_code=False, dtype=torch.bfloat16,
            device_map={"": "cuda:0"}, attn_implementation="sdpa", experts_implementation="eager",
            output_loading_info=True), result, args.output, torch)
        model, info = loaded
        del loaded
        bad = {k: info.get(k, []) for k in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs") if info.get(k)}
        if bad:
            raise RuntimeError(f"权重加载存在未解决条目：{bad}")
        model.eval().requires_grad_(False)
        if any(p.device != torch.device("cuda:0") or p.dtype != torch.bfloat16 for p in model.parameters()):
            raise RuntimeError("所有模型参数必须位于同一显卡并使用bf16")
        tok = AutoTokenizer.from_pretrained(args.model_dir, local_files_only=True, trust_remote_code=False)
        if tok.convert_tokens_to_ids("<|im_end|>") != IM_END or tok.convert_tokens_to_ids("<|endoftext|>") != ENDOFTEXT:
            raise RuntimeError("分词器结束词元与项目不一致")
        records = make_prompts(tok)
        response = tok.encode("原题答案是40人。", add_special_tokens=False)
        pad_id, eos_ids, layer = PAD_ID, (IM_END, ENDOFTEXT), 20
        result["weight_loading"] = dict(missing=0, unexpected=0, mismatched=0, dtype=str(model.dtype))
    model.generation_config.disable_compile = True
    # 吞吐路径不能继承概率/隐藏态诊断的输出开关。
    model.generation_config.output_scores = False
    model.generation_config.output_logits = False
    model.generation_config.output_hidden_states = False
    model.generation_config.output_attentions = False
    model.generation_config.return_dict_in_generate = False
    model.config.output_router_logits = False
    result["prompt_lengths"] = [len(r["ids"]) for r in records]
    original_parameters = tuple((name, id(p)) for name, p in model.named_parameters())
    experts = model.model.layers[0].mlp.experts
    if not hasattr(experts, "gate_up_proj") or not hasattr(experts, "down_proj"):
        raise RuntimeError("模型未使用新版堆叠专家参数")
    result["expert_parameter_shapes"] = dict(gate_up_proj=list(experts.gate_up_proj.shape), down_proj=list(experts.down_proj.shape))
    set_backend(model, "eager")
    r_l = activation_scale(model, records[0]["ids"], layer)
    direction = torch.randn(model.config.hidden_size, generator=torch.Generator().manual_seed(20261018))
    steer = Steer(model, layer, direction, r_l)
    result["intervention"] = dict(layer=layer, diagnostic_r_L=r_l, alpha_half_rows=0.5)
    references = {}
    try:
        for backend in BACKENDS:
            set_backend(model, backend)
            if original_parameters != tuple((name, id(p)) for name, p in model.named_parameters()):
                raise RuntimeError("切换专家后端改变了参数对象")
            if backend == "grouped_mm":
                from transformers.integrations.moe import _can_use_grouped_mm
                weight = experts.down_proj.transpose(-2, -1)
                sample = torch.zeros(1, weight.shape[1], dtype=model.dtype, device=model.device)
                offsets = torch.ones(weight.shape[0], dtype=torch.int32, device=model.device)
                native = bool(_can_use_grouped_mm(sample, weight, offsets))
                result["native_grouped_mm_available"] = native
                if not native and not args.cpu_smoke:
                    raise RuntimeError("当前显卡环境只会走分组算子回退，不能标为原生后端比较")
            values, _ = timed(f"semantics_{backend}", lambda: semantic_check(
                model, steer, records, response, pad_id, eos_ids, cpu=args.cpu_smoke), result, args.output, torch)
            checks, logits, gradient = values
            result["diagnostics"][backend] = checks
            references[backend] = (logits, gradient)
            if args.cpu_smoke:
                short = generate_batch(model, steer, records, 2, 4, pad_id, eos_ids)
                result["throughput"][backend] = dict(cpu_interface_only=short)
                continue
            short, measurement = timed(f"preflight_{backend}_B8", lambda: generate_batch(
                model, steer, records, 8, args.preflight_tokens, pad_id, eos_ids), result, args.output, torch)
            result["throughput"][backend] = dict(preflight=dict(**short, seconds=measurement["seconds"]), batches=[])
            if args.preflight_only:
                continue
            for size in args.batches:
                try:
                    generated, measurement = timed(f"throughput_{backend}_B{size}", lambda: generate_batch(
                        model, steer, records, size, args.new_tokens, pad_id, eos_ids), result, args.output, torch)
                except torch.cuda.OutOfMemoryError as exc:
                    traceback.clear_frames(exc.__traceback__)
                    result["throughput"][backend]["batches"].append(dict(batch_size=size, status="oom"))
                    gc.collect()
                    torch.cuda.empty_cache()
                    break
                row = dict(batch_size=size, status="completed", **generated, seconds=measurement["seconds"],
                           aggregate_tokens_per_second=generated["generated_tokens"] / measurement["seconds"],
                           peak_allocated_gib=measurement["peak_allocated_gib"], peak_reserved_gib=measurement["peak_reserved_gib"],
                           includes_prompt_processing=True, max_new_tokens=args.new_tokens)
                result["throughput"][backend]["batches"].append(row)
                save(args.output, result)
                emit(dict(event="throughput", experts=backend, **row))
        l0, g0 = references["eager"]
        l1, g1 = references["grouped_mm"]
        lp0, lp1 = torch.log_softmax(l0 / TEMPERATURE, -1), torch.log_softmax(l1 / TEMPERATURE, -1)
        result["same_weight_backend_difference"] = dict(first_token_max_logit_difference=float((l0 - l1).abs().max()),
            first_token_kl_eager_to_grouped=float((lp0.exp() * (lp0 - lp1)).sum()),
            gradient_cosine=float(np.dot(g0, g1) / (np.linalg.norm(g0) * np.linalg.norm(g1))))
        any_oom = any(row.get("status") == "oom" for backend in result["throughput"].values()
                      for row in backend.get("batches", []))
        result["status"] = "completed_with_oom" if any_oom else "completed"
    finally:
        steer.remove()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cpu-smoke", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--preflight-tokens", type=int, default=16)
    parser.add_argument("--batches", nargs="+", type=int, default=[8, 16, 32], choices=[8, 16, 32])
    parser.add_argument("--new-tokens", type=int, default=256)
    args = parser.parse_args()
    if not args.cpu_smoke and (args.model_dir is None or not args.model_dir.is_dir() or args.output is None):
        parser.error("显卡比较须提供本地模型目录与唯一结果JSON路径")
    if args.output is not None and (not args.output.parent.is_dir() or args.output.exists()):
        parser.error("结果父目录须存在，结果文件须尚不存在")
    if args.new_tokens <= 0 or args.preflight_tokens < 2 or args.batches != sorted(set(args.batches)):
        parser.error("词元预算须为正、短预检至少2词元，批量须递增且不重复")
    result = dict(status="running", device="cpu" if args.cpu_smoke else "cuda:0")
    try:
        compare(args, result)
    except BaseException as exc:
        result.update(status="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                      error_type=type(exc).__name__, error=str(exc))
        save(args.output, result)
        emit(result)
        raise
    save(args.output, result)
    emit(result)


if __name__ == "__main__":
    main()
