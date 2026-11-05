"""新材料的独立中性评分与至多 64 条真实首答。"""
import argparse
import copy
import json
from pathlib import Path
import sys

from program_update_first_answers import RUNS, MODEL, collect
from program_semantic_materials import material_rows, first_prompts, probe

STAGE = 'internal8_program_semantic_v124'


def score(directory, rows):
    import torch
    from transformers import AutoTokenizer
    sys.path.insert(0, str(RUNS / 'internal8_P0_w17'))
    from w17_core import Engine, write
    torch.set_num_threads(2)
    path = directory / 'neutral_scores.json'
    if path.exists():
        raise RuntimeError('中性评分已存在，不静默覆盖或重复执行。')
    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    engine = Engine()
    result = {'rows': [], 'temperature': .7, 'generated_tokens': 0,
              'definition': 'same neutral truth-evaluation prompt; normalized Yes/No joint likelihood including IM_END'}
    with torch.inference_mode():
        for row in rows:
            values = {}
            for label, outcome in [('theta', row['gold']), ('alpha', row['candidate'])]:
                prefix = tokenizer.apply_chat_template(probe(row, outcome), tokenize=False, add_generation_prompt=True)
                ids = tokenizer.encode(prefix, add_special_tokens=False)
                initial = engine.call(ids, None, 'neutral_prompt')
                likelihoods = []
                for answer in ['Yes', 'No']:
                    all_ids = tokenizer.encode(prefix + answer + '<|im_end|>', add_special_tokens=False)
                    assert all_ids[:len(ids)] == ids
                    answer_ids = all_ids[len(ids):]
                    first = (initial.logits[0, -1].float() / .7).log_softmax(-1)[answer_ids[0]]
                    rest = engine.call(answer_ids[:-1], copy.deepcopy(initial.past_key_values), 'forced_answer', True)
                    lp = (rest.logits[0].float() / .7).log_softmax(-1)
                    tail = lp[torch.arange(len(answer_ids)-1, device='cuda'), torch.tensor(answer_ids[1:], device='cuda')].sum()
                    likelihoods.append(float(first+tail))
                values[label] = {'yes_logp': likelihoods[0], 'no_logp': likelihoods[1],
                                 'yes_relative_probability': float(torch.tensor(likelihoods).softmax(0)[0])}
            result['rows'].append({'id': row['id'], 'family': row['family'], **values})
            result['calls'] = dict(engine.counter)
            write(path, result)
            print(json.dumps({'scored':len(result['rows']),'total':32}), flush=True)
    for family in ['numeric','text','iterator','library']:
        members = sorted([r for r in result['rows'] if r['family']==family],
                         key=lambda r:(r['alpha']['yes_relative_probability'],r['id']))
        for i,r in enumerate(members):
            r['stratum'] = 'lower_within_family' if i < 4 else 'higher_within_family'
    result['complete'] = True
    write(path,result)


def main():
    args = argparse.ArgumentParser()
    args.add_argument('action', choices=['materials','score','sample'])
    action = args.parse_args().action
    rows = material_rows()
    directory = RUNS / STAGE
    directory.mkdir(exist_ok=True)
    if action == 'materials':
        p = directory / 'materials.json'
        if p.exists():
            assert json.loads(p.read_text()) == rows
        else:
            p.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
        print('MATERIALS_VALIDATED_32', flush=True)
    elif action == 'score':
        assert json.loads((directory/'materials.json').read_text()) == rows
        score(directory,rows)
    else:
        neutral = json.loads((directory/'neutral_scores.json').read_text())
        assert neutral['complete'] and len(neutral['rows']) == 32
        collect(directory, first_prompts(rows), STAGE, complete=True, repeats=2, max_new_tokens=16384)


if __name__ == '__main__':
    main()
