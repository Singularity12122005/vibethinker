"""唯一一轮修订的固定输入与冻结校验；原回答只在A100构造，不导出。"""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import re
import sys

# 既有处理器模块采用同目录绝对导入；仅补导入路径，不修改冻结模块。
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

try:
    from .stage2_plan import baseline_records, identity, load, digest
except ImportError:
    from stage2_plan import baseline_records, identity, load, digest

VERSION = 'stage2-relations-v3'
COUNTS = {'baseline': 1200, 'Q2': 2880, 'batch5': 1840}
ORDER = tuple(COUNTS)
PROTOCOL_FILE = 'factdiag7_stage2_revision_protocol.json'
MATERIAL_FILE = 'factdiag7_stage2_revision_materials.json'
PREREG_FILE = 'factdiag7_stage2_revision_prereg.json'
INDEX_FILE = 'stage2_revision_input_index.json'
OUTPUT_FILES = {phase: f'stage2_revision_{phase}_extractions.json' for phase in ORDER}
RS_EVIDENCE = {'M-wrong', 'M-right', 'E-inapp', 'E-false'}
PLACEHOLDERS = r'\{(QUESTION|CANDIDATE|ALIASES|PREFIX|USER_MESSAGE|RESPONSE)\}'


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_new(path, value):
    """冻结材料可重复读取相同内容；已有不同内容不得覆盖。"""
    path = Path(path)
    if path.exists():
        if load(path) != value:
            raise RuntimeError('已有不同修订冻结文件：' + path.name)
        return
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def render_prompt(protocol, item, person, prefix, user_message, response):
    values = dict(QUESTION=item['question_en'], CANDIDATE=person['name'],
                  ALIASES='; '.join(person['aliases']), PREFIX=prefix,
                  USER_MESSAGE=user_message, RESPONSE=response)
    if any('{' + key + '}' not in protocol['prompt'] for key in values):
        raise ValueError('修订协议缺少正式输入段')
    return re.sub(PLACEHOLDERS, lambda match: values[match[1]], protocol['prompt'])


def make_input(phase, prior_id, row, item, person, kind, protocol, *, prefix=None):
    forced = row.get('forced_prefix', '')
    text = row['assistant_text']
    if forced and not text.startswith(forced):
        raise ValueError('生成正文与固定前缀边界不符')
    response = text[len(forced):]
    user_message = row['user_text']
    context = forced if prefix is None else prefix
    prompt = render_prompt(protocol, item, person, context, user_message, response)
    record = dict(id=phase + '|' + prior_id, prior_id=prior_id, phase=phase, kind=kind,
                  response_id=identity(row) if phase != 'batch5' else row['request_id'],
                  work_id=item['work_id'], arm=row['arm'], prompt=prompt, response=response,
                  user_message=user_message, fixed_context=context, item=item, person=person,
                  technical_failure=bool(row.get('truncated') or row.get('looped')))
    record['prompt_sha256'] = hashlib.sha256(prompt.encode()).hexdigest()
    record['input_sha256'] = digest({k: v for k, v in record.items() if k != 'prompt_sha256'})
    return record


def construct_inputs(protocol, materials, baseline, q2, batch5_rows, batch5_material):
    """只转换已经生成的回答；人物对象与旧范围一一对应。"""
    bank = {m['item_id']: m for m in materials['items']}
    queues = {phase: [] for phase in ORDER}
    for phase, rows in (('baseline', baseline), ('Q2', q2)):
        for row in rows:
            item = bank[row['conflict_id']]
            kinds = [row['candidate_type'], 'GOLD'] + (['T'] if phase == 'Q2' else [])
            for kind in kinds:
                person = next(p for p in item['people'] if p['type'] == kind)
                queues[phase].append(make_input(phase, identity(row) + '|' + kind,
                                                row, item, person, kind, protocol))
    items_by_work = {m['work_id']: m for m in materials['items']}
    fifth_bank = {m['work_id']: m for m in batch5_material['materials']}
    for row in batch5_rows:
        selected = (row['unit'] == 'R-S' and row['cell'] in RS_EVIDENCE) or row['cell'] == '5.5'
        if not selected:
            continue
        m = fifth_bank[row['work_id']]
        item = deepcopy(items_by_work[row['work_id']])
        person = next(p for p in item['people'] if p['type'] == 'T')
        if person['name'] != m['F']['gold']:
            raise ValueError('第五批提取对象偏离已核实的真译者')
        role = 'R' if row['unit'] == 'R-S' else 'F'
        item.update(question_en=m[role]['question_en'],
                    target_relation='AUTHOR' if role == 'R' else 'TRANSLATOR',
                    review_target_gold=m[role]['gold'])
        context = 'Fixed assistant prefix:\n' + row.get('forced_prefix', '')
        if row.get('system_record'):
            context += '\nSystem reference record (context only, not generated text):\n' + row['system_record']
        prior_id = row['request_id'] + '|F5_REVIEW|relations_v2'
        q = make_input('batch5', prior_id, row, item, person, 'T', protocol, prefix=context)
        q.update(cell=row['cell'], unit=row['unit'])
        queues['batch5'].append(q)
    return queues


def validate_counts(queues):
    for phase, n in COUNTS.items():
        rows = queues[phase]
        if len(rows) != n or len({q['id'] for q in rows}) != n:
            raise ValueError('修订输入规模或唯一性错误：' + phase)
    fifth = Counter('5.5' if q['cell'] == '5.5' else 'R-S证据' for q in queues['batch5'])
    if fifth != Counter({'R-S证据': 1440, '5.5': 400}):
        raise ValueError('第五批修订范围发生变化')


def build_inputs(pilot, protocol=None, materials=None):
    pilot = Path(pilot); out = pilot / 'factdiag7_20261112'; fifth = pilot / 'factdiag5_20261112'
    protocol = protocol or load(out / PROTOCOL_FILE)
    materials = materials or load(out / MATERIAL_FILE)
    if protocol['version'] != VERSION:
        raise ValueError('修订协议版本不符')
    queues = construct_inputs(protocol, materials,
        baseline_records(pilot / 'factdiag6g_20261111'), load(out / 'stage2_Q2_generations.json'),
        load(fifth / 'core_generations.json'), load(fifth / 'factdiag5_materials.json'))
    validate_counts(queues)
    # 原输入集合一一对应；此校验不重跑原分词、历史绑定或模型评审。
    old = {'baseline': load(out / 'stage2_baseline_extractions.json'),
           'Q2': load(out / 'stage2_Q2_extractions.json')}
    for phase in old:
        if {q['prior_id'] for q in queues[phase]} != set(old[phase]):
            raise ValueError('阶段二修订人物对象发生变化：' + phase)
    return queues


def input_index(queues):
    return {phase: [{k: q[k] for k in ('id', 'prior_id', 'response_id', 'work_id', 'kind',
                                      'input_sha256', 'prompt_sha256')}
                    for q in queues[phase]] for phase in ORDER}


def validate_freeze(pilot, *, queue_check=True):
    pilot = Path(pilot); out = pilot / 'factdiag7_20261112'
    reg = load(out / PREREG_FILE)
    if reg['version'] != VERSION or reg['counts'] != COUNTS:
        raise ValueError('修订预注册范围不符')
    for name, expected in reg['frozen_files'].items():
        if sha_file(out / name) != expected:
            raise RuntimeError('修订冻结材料变化：' + name)
    for relative, expected in reg['code_sha256'].items():
        if sha_file(pilot / relative) != expected:
            raise RuntimeError('修订冻结代码变化：' + relative)
    for relative, expected in reg['source_sha256'].items():
        if sha_file(pilot / relative) != expected:
            raise RuntimeError('既有源材料变化：' + relative)
    if queue_check:
        queues = build_inputs(pilot)
        if input_index(queues) != load(out / INDEX_FILE):
            raise RuntimeError('修订输入与冻结清单不符')
        return reg, queues
    return reg
