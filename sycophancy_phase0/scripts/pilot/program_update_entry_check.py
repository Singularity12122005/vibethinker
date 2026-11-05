"""程序迁移三问核查：固定社会证明上下文；不生成新词元。"""
import copy
import json
from pathlib import Path
import sys

from program_update_paired import families, context, messages
from program_update_first_answers import RUNS, MODEL, HEADS


def main():
    import torch
    from transformers import AutoTokenizer
    sys.path.insert(0, str(RUNS / 'internal8_P0_w17'))
    from w17_core import Engine, cap, metric, write
    import g1_runtime_main as legacy
    torch.set_num_threads(2)
    directory = RUNS / 'internal8_program_paired_v121'
    target = directory / 'entry_check_v124.json'
    if target.exists():
        raise RuntimeError('已有入口核查结果；先读取，禁止静默重跑。')
    selected = json.loads((directory / 'selected_histories.json').read_text())
    easy = json.loads((directory / 'first_answers.json').read_text())
    hard = json.loads((RUNS / 'internal8_program_hard_v120/first_answers.json').read_text())
    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    builder = legacy.TurnBuilder(lambda s: tokenizer.encode(s, add_special_tokens=False), 'instruct')
    pairs = families()
    cases = []
    for entry in selected:
        name, side, key = entry['family'], entry['side'], entry['key']
        first = (easy if side == 'E' else hard)[key]
        ctx = context(tokenizer, builder, pairs[name], side, first, '加社交压力')
        cases.append((f'{name}-{side}-{key}', ctx))
    assert len(cases) == 16
    config = json.loads((RUNS / 'internal8_P0_w17/allfit_done.json').read_text())
    assert config['heads'] == HEADS and config['k'] == 1
    bases = torch.load(RUNS / 'internal8_P0_w17/pooled_directions.pt', map_location='cpu', weights_only=True)
    selection = {}
    for head in HEADS:
        selection.setdefault(head // 32, torch.zeros(32, device='cuda'))[head % 32] = 1.
    projection = {}
    for layer in selection:
        vector = bases[layer][0].to(device='cuda', dtype=torch.float32)
        assert vector.shape == (2048,) and abs(vector.norm().item()-1.) < 1e-5
        projection[layer] = lambda d, v=vector: (d @ v).unsqueeze(-1) * v
    zero = {layer: (lambda d: torch.zeros_like(d)) for layer in selection}
    engine = Engine()
    report = {'condition': '加社交压力', 'generated_tokens': 0, 'rows': []}
    with torch.inference_mode():
        for key, x in cases:
            prefix = engine.prefix(x)
            header = x['ids'][x['bounds'][2]:]
            capture = cap()
            scores = {}
            # 原生调用与无编辑的采集调用并列，检测采集接口自身偏移。
            native = engine.call(header, copy.deepcopy(prefix), 'native').logits[0, -1].float()
            scores['N'] = native
            with engine.edit(x, 'N', selection={}, capture=capture):
                scores['capture'] = engine.call(header, copy.deepcopy(prefix), 'capture').logits[0, -1].float()
            with engine.ref(x, x['bounds'][2], 'O'):
                scores['O'] = engine.call(header, copy.deepcopy(prefix), 'blocked').logits[0, -1].float()
            with engine.edit(x, 'N', selection=selection, projection=projection):
                scores['L'] = engine.call(header, copy.deepcopy(prefix), 'rank_one_remove').logits[0, -1].float()
            with engine.edit(x, 'N', selection=selection, projection=zero):
                scores['zero'] = engine.call(header, copy.deepcopy(prefix), 'zero_projection').logits[0, -1].float()
            probabilities = {k: (v / .7).softmax(-1) for k, v in scores.items()}
            q = {k: float(v[2610]) for k, v in probabilities.items()}
            tv = {k: float((v-probabilities['N']).abs().sum()/2) for k,v in probabilities.items()}
            span = {str(h): float(capture['span'][h // 32][-1, h % 32]) for h in HEADS}
            report['rows'].append({'key': key, 'q_You': q, 'total_variation_from_N': tv,
                'selected_head_span_attention_last_query': span,
                'opening_text': tokenizer.decode(x['ids'][x['opening_span'][0]:x['opening_span'][1]]),
                'distance_from_opening_end_to_generation': len(x['ids'])-x['opening_span'][1],
                'remove_probability_effect': q['N']-q['L'],
                'block_probability_effect': q['N']-q['O'],
                'rank_one_numeric_floor': 3*abs(q['N']-q['zero'])})
            report['calls'] = dict(engine.counter)
            write(target, report)
            print(json.dumps({'finished': len(report['rows']), 'total': 16}, ensure_ascii=False), flush=True)
            del prefix, capture, scores, probabilities
    assert sum(engine.counter.values()) == 128
    report['complete'] = True
    write(target, report)
    print('ENTRY_CHECK_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
