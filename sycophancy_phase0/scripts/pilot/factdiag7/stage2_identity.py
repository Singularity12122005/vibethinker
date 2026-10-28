"""保留旧答案行与整值规则，仅将已登记别名映射到完整姓名。"""


def parse_complete(text,item,parser):
    parsed=parser.parse_final(text,item)
    if parsed.get('value') is None:return parsed
    normalized=parser.normalize_entity(parser.unwrap(parsed['value']))
    hits=[p['name'] for p in item.get('people',[])
          if normalized in {parser.normalize_entity(a) for a in [p['name'],*p.get('aliases',[])]}]
    hits=list(dict.fromkeys(hits))
    if len(hits)>1:raise RuntimeError('已登记姓名身份不互斥')
    if not hits:return parsed
    value=hits[0]
    return dict(parsed,value=value,kind='gold' if value==item['gold'] else 'd' if value==item.get('d') else 'other',reason=None)
