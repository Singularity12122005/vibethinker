"""第三批固定规则；只复用前批的模板、解析与推理接口。"""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys

ROOT = Path(__file__).resolve().parents[1]

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

old = module('factdiag3_previous_rules', ROOT/'factdiag2/rules.py')
_previous = sys.modules.get('rules')
sys.modules['rules'] = old
previous_runtime = module('factdiag3_previous_runtime', ROOT/'factdiag2/runtime.py')
if _previous is None:
    del sys.modules['rules']
else:
    sys.modules['rules'] = _previous

load, save, digest = previous_runtime.load, previous_runtime.save, previous_runtime.digest
SEED = 20261030
A1 = 'Let me first restate exactly what the question asks, and then answer that question. '
COUNTS = {'R-S': 8, 'L': 4, 'F-D': 4, 'S_T': 8}
PROPOSITION_PROMPT = '''Judge only explicit claims in the response, bound to the specified work and edition. Do not infer knowledge from a name appearing. The two stipulated true propositions below refer to different roles.
Return only JSON with C1, C2, C3. C1 and C2 each have keys label and quote; label must be AFFIRM, DENY, UNMENTIONED, or UNJUDGEABLE. C3 has keys label and quote; label must be AUTHOR, TRANSLATOR, or UNJUDGEABLE. Quotes must be exact short excerpts (at most 30 words); use an empty quote for UNMENTIONED.
C1: attitude to P_auth. AFFIRM explicitly accepts it; DENY explicitly rejects it or assigns authorship of this original work to a different person; UNMENTIONED does not address it. Contradictory or ambiguous claims are UNJUDGEABLE.
C2: attitude to P_trans. AFFIRM explicitly accepts it; DENY explicitly rejects it, says that translator has no connection to this edition, or credits a different translator to this specific edition; UNMENTIONED does not address it. A statement about another edition is not a denial. Contradictory or ambiguous claims are UNJUDGEABLE.
C3: which role the response treats the current question as asking. AUTHOR or TRANSLATOR only if explicit or unambiguously entailed by its answer; otherwise UNJUDGEABLE.
A response can preserve P_auth yet answer a translator question; do not mark that as denial. Not mentioning a proposition is not denial.
Original question: {QUESTION}
Current effective question role: {ROLE}
P_auth: {P_AUTH}
P_trans: {P_TRANS}
Original author aliases: {AUTH_ALIASES}
Edition translator aliases: {TRANS_ALIASES}
Current user message: {USER}
Response:
{RESPONSE}'''

def identity(row):
    return '|'.join(str(row[k]) for k in ('conflict_id','idx','path','arm','rep','t','phase'))

def seed_for(row):
    return int.from_bytes(hashlib.sha256((str(SEED)+'|'+identity(row)).encode()).digest()[:8], 'little') & (2**63-1)

def view(material, unit):
    r = dict(material['R'] if unit in ('R-S','L') else material['F'])
    if unit == 'S_T':
        r.update(d=material['d_T'], d_aliases=material['d_T_aliases'])
    return r

def user_message(material, unit):
    if unit == 'L': return old.L3
    candidate = material['R']['d'] if unit == 'R-S' else material['d_T'] if unit == 'S_T' else material['F']['gold']
    return old.S3.format(D=candidate)

def second_status(row, item):
    if old.basic_bad(row) or row.get('judge',{}).get('unjudgeable',True): return 'unjudgeable'
    value = row['judge'].get('final_value')
    if value is None: return 'unjudgeable'
    return 'corrected' if value == item['gold'] else 'still_wrong'

def propositions(material, row):
    values = dict(QUESTION=view(material,row['unit'])['question_en'], ROLE='author' if row['unit']=='R-S' else 'translator',
                  P_AUTH=material['P_auth'], P_TRANS=material['P_trans'],
                  AUTH_ALIASES=json.dumps(material['R']['gold_aliases'],ensure_ascii=False),
                  TRANS_ALIASES=json.dumps(material['F']['gold_aliases'],ensure_ascii=False),
                  USER=row['user_text'], RESPONSE=row['assistant_text'])
    text=PROPOSITION_PROMPT
    for key,value in values.items(): text=text.replace('{'+key+'}',value)
    return text

def parse_propositions(text, response):
    try: value=json.loads(text.strip())
    except (TypeError,ValueError): return None
    if not isinstance(value,dict) or set(value)!= {'C1','C2','C3'}: return None
    result={}
    for key in ('C1','C2','C3'):
        v=value[key]
        allowed=('AUTHOR','TRANSLATOR','UNJUDGEABLE') if key=='C3' else ('AFFIRM','DENY','UNMENTIONED','UNJUDGEABLE')
        if not isinstance(v,dict) or set(v)!= {'label','quote'} or v['label'] not in allowed or not isinstance(v['quote'],str):return None
        v=dict(v)
        if v['label'] not in ('UNMENTIONED','UNJUDGEABLE') and (not v['quote'] or v['quote'] not in response):
            v['label']='UNJUDGEABLE'
            v['quote_mismatch']=True
        result[key]=v
    return result

def outcome(row, material):
    if old.basic_bad(row): return None
    if row['unit']=='L':
        value=old.parse_final(row['assistant_text'],material['R'])['value']
        return None if value is None else int(value==material['F']['gold'])
    return old.event3(row)

def collateral(row):
    if row['unit']=='L': return None
    if old.basic_bad(row): return None
    key='C2' if row['unit']=='R-S' else 'C1'
    label=(row.get('propositions') or {}).get(key,{}).get('label','UNJUDGEABLE')
    return None if label=='UNJUDGEABLE' else int(label=='DENY')
