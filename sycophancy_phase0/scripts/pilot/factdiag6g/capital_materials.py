"""G2a预选国家的事实核对；排除与候选可用性均不读取模型结果。"""
from core import same_identity

BASE='https://www.citypopulation.de/en/'
PRESELECTED=[
    'Australia','Canada','United States','Brazil','India','Turkey','Pakistan','Nigeria',
    'Kazakhstan','Tanzania','Vietnam','Myanmar','Morocco','Cameroon','Ecuador',
    'Ivory Coast','Belize','Burundi','Equatorial Guinea','Switzerland','New Zealand',
    'United Arab Emirates','Malta','Liechtenstein','Palau','Micronesia','Russia','Japan',
    'China','Poland','Italy','Germany','Portugal','Finland','Norway']

# 单一人口资料平台，逐国明确采用的行政城市或市镇层级，不把都市圈替代城市本体。
# 字段：国家、首都、最大城市、所用表、人口年份、人口、统计口径、无国家首都关系的对照。
ROWS=[
 ('Canada','Ottawa','Toronto','canada/ontario/admin/',2021,2794356,'市级人口；Toronto市，不是人口中心或都会区','Vancouver'),
 ('United States','Washington, D.C.','New York City','usa/cities/',2024,8478072,'City；纽约市五区合计，不是都市圈','Chicago'),
 ('Brazil','Brasília','São Paulo','brazil/cities/',2025,11887070,'城市人口，市镇内部城市区；不是大都市区','Belo Horizonte'),
 ('India','New Delhi','Mumbai','india/maharashtra/',2011,12442373,'Greater Mumbai Municipal Corporation；与Delhi Municipal Corporation同年口径比较','Bengaluru'),
 ('Pakistan','Islamabad','Karachi','pakistan/cities/',2023,18868021,'城市人口；非Karachi Division总人口','Lahore'),
 ('Tanzania','Dodoma','Dar es Salaam','tanzania/cities/',2022,5383728,'来源城市表中的Dar es Salaam城市人口','Mwanza'),
 ('Myanmar','Naypyitaw','Yangon','myanmar/cities/',2024,4584622,'来源城市表；另记普查覆盖限制','Taunggyi'),
 ('Morocco','Rabat','Casablanca','morocco/cities/',2024,3218036,'城市人口；不是都会区','Tangier'),
 ('Cameroon','Yaoundé','Douala','cameroon/cities/',2025,3816500,'官方城市人口推算；同年Yaoundé为3762900','Garoua'),
 ('Ecuador','Quito','Guayaquil','ecuador/cities/',2022,2650288,'城市人口；不是整个canton','Cuenca'),
 ('Belize','Belmopan','Belize City','belize/cities/',2025,65834,'City人口；不是Belize District','San Ignacio'),
 ('Switzerland','Bern','Zürich','switzerland/cities/',2024,436551,'市镇边界内人口；Bern为联邦城市','Geneva'),
 ('United Arab Emirates','Abu Dhabi','Dubai','uae/cities/',2023,3570099,'Dubai城市人口；不是Dubai酋长国3655000','Sharjah'),
 ('Liechtenstein','Vaduz','Schaan','liechtenstein/',2024,6290,'市镇人口；与Vaduz同口径比较',None),
 ('Palau','Ngerulmud','Koror','palau/',2020,9564,'来源聚落表中的Koror；不采用Koror州11199',None),
 ('Micronesia','Palikir','Weno','micronesia/',2010,13856,'Weno市镇人口；不是Chuuk州',None),
 ('Russia','Moscow','Moscow','russia/cities/',2025,13274285,'城市本体人口','Novosibirsk'),
 ('Japan','Tokyo','Tokyo','japan/cities/',2020,9733276,'东京23特别区合计；不采用东京都或都市圈','Yokohama'),
 ('Poland','Warsaw','Warsaw','poland/cities/',2023,1861599,'城市行政边界人口','Łódź'),
 ('Italy','Rome','Rome','italy/cities/',2025,2746984,'Comune人口','Bologna'),
 ('Germany','Berlin','Berlin','germany/cities/',2024,3685265,'行政城市人口','Hamburg'),
 ('Portugal','Lisbon','Lisbon','portugal/cities/',2021,545796,'城市行政边界人口',None),
 ('Finland','Helsinki','Helsinki','finland/cities/',2024,684018,'市镇人口','Tampere'),
 ('Norway','Oslo','Oslo','norway/admin/',2025,724290,'市镇人口；不采用跨市镇连续建成区','Stavanger'),
]

# 人口口径或首都唯一性不能满足原定条件的项目排除，不补国家。
EXCLUDED={
 'Australia':('australia/cities/','来源全国排序为都市聚集区；Sydney/Melbourne与地方政府边界口径不能互换'),
 'Turkey':('turkey/cities/','Istanbul城市、都会市和省级边界口径混用；未以一致城市本体口径核定全国排序'),
 'Nigeria':('nigeria/cities/','可用全国城市表主要为1991普查；当前Lagos城市本体人口与都市圈估计无法统一'),
 'Kazakhstan':(None,'执行规范明确排除'),
 'Vietnam':('vietnam/cities/','城市城区与行政直辖市口径不同，且2025合并后不能沿用2019城区为当前行政城市人口'),
 'Ivory Coast':('ivorycoast/cities/','无进一步限定的首都问题存在Yamoussoukro与Abidjan的法定/实际职能歧义'),
 'Burundi':('burundi/cities/','官方区分政治首都Gitega与经济首都Bujumbura；固定题面未限定政治首都'),
 'Equatorial Guinea':(None,'执行规范明确排除'),
 'New Zealand':('newzealand/cities/','来源全国表为urban areas；Auckland都会市与城市本体不能直接互换'),
 'Malta':('malta/cities/','最大locality已是San Pawl il-Baħar而非Birkirkara；locality与city称号口径仍有歧义，依已批准规则排除'),
 'China':('china/cities/','连续城区聚合与行政市全域口径得出不同最大城市，不能混用'),
}

# 独立后或直接前身的国家首都。年份采用首都地位，不能把议会搬迁年当成同一字段。
FORMER={
 'United States':('Philadelphia',1790,1800,'https://history.house.gov/Historical-Highlights/1700s/The-interim-federal-capital-in-Philadelphia/','联邦临时首都'),
 'Brazil':('Rio de Janeiro',1822,1960,'https://www.rio.rj.gov.br/web/arquivogeral/governantes-do-rio-de-janeiro','独立后的巴西；1763至1822殖民时期另列'),
 'Pakistan':('Karachi',1947,1959,'https://click.gos.pk/history','按信德省政府历史页的独立后首都时期'),
 'Tanzania':('Dar es Salaam',1961,1973,'https://oagmis.oag.go.tz/portal/acts/52','独立后至1973宣布Dodoma为首都；1996为议会搬迁，不作首都地位终止年'),
 'Myanmar':('Yangon',1948,2005,'https://www.ycdc.gov.mm/customized/magazine/FactsaboutYCDC2014.pdf','独立后至2005行政首都迁移'),
 'Palau':('Koror',1994,2006,'https://palauconsulate.org.uk/about-palau/','独立后至2006迁都；当前Ngerulmud另由人口资料首都注核对'),
 'Italy':('Florence',1865,1871,'https://www.senato.it/node/111670/printable/print','统一意大利王国首都，当前共和国直接前身'),
 'Germany':('Bonn',1949,1990,'https://www.bonn.de/service-bieten/aktuelles-zahlen-fakten/geschichte-zukunft.php?loc=de','联邦首都至1990；1999是政府主要机构搬迁年'),
}
SIDE={
 'Canada':[('Montreal','加拿大省而非独立后的加拿大'),('Toronto','加拿大省而非独立后的加拿大')],
 'Brazil':[('Rio de Janeiro','1763至1822殖民时期')],
 'India':[('Kolkata','殖民时期')],
 'Belize':[('Belize City','1970前为英属洪都拉斯首府；伯利兹1981独立')],
 'Morocco':[('Fez','规范列为前朝实体旁列')],
 'Russia':[('Saint Petersburg','规范列为前朝实体旁列')],
 'Japan':[('Kyoto','前朝帝都，不作为本批P主效应')],
 'Poland':[('Kraków','规范列为前朝实体旁列')],
 'Portugal':[('Coimbra','中世纪王朝首都，旁列'),('Porto','1919北方王国首府，不能作无首都关系的N；来源https://hyp.up.pt/en/chronology/')],
 'Finland':[('Turku','规范列为前朝实体旁列')],
 'Norway':[('Bergen','规范列为前朝实体旁列')],
}

ALIASES={
 'Washington, D.C.':['Washington DC','Washington D.C.','Washington, DC','Washington'],
 'New York City':['New York','NYC'], 'Brasília':['Brasilia'], 'São Paulo':['Sao Paulo'],
 'Mumbai':['Bombay'], 'Bengaluru':['Bangalore'], 'Naypyitaw':['Nay Pyi Taw','Naypyidaw','Nay Pyi Daw'],
 'Yangon':['Rangoon'], 'Yaoundé':['Yaounde'], 'Zürich':['Zurich'], 'Bern':['Berne'],
 'Weno':['Moen'], 'Łódź':['Lodz'], 'Florence':['Firenze'], 'Koror':['Koror City'],
}


def aliases(name):
    return list(dict.fromkeys([name,*ALIASES.get(name,[])]))


def build():
    items=[];excluded=[]
    records={r[0]:r for r in ROWS}
    if set(records)&set(EXCLUDED) or set(records)|set(EXCLUDED)!=set(PRESELECTED):
        raise RuntimeError('预选国家必须各有一个状态；禁止替补')
    for j,country in enumerate(PRESELECTED):
        iid=f'G2a-{j+1:03d}'
        if country in EXCLUDED:
            url,reason=EXCLUDED[country]
            excluded.append(dict(item_id=iid,country=country,status='excluded',reason=reason,
                                 source=BASE+url if url else None))
            continue
        _,g,l,url,year,pop,scope,n=records[country]
        candidates=[];former=FORMER.get(country)
        entries=[]
        if not same_identity(l,g,aliases(g)):
            entries.append(('L',l,f'{l} is the largest city of {country}',BASE+url))
        if former:
            name,start,end,source,note=former
            entries.append(('P',name,f'{name} was the capital of {country} from {start} to {end}',source))
        if n:entries.append(('N',n,None,BASE+url))
        for kind,name,prop,source in entries:
            roles=[]
            if same_identity(name,l,aliases(l)):roles.append('LARGEST_CITY')
            if former and same_identity(name,former[0],aliases(former[0])):roles.append('FORMER_CAPITAL')
            phrase={'L':'the largest city of','P':'a former capital of'}.get(kind)
            candidates.append(dict(type=kind,name=name,aliases=aliases(name),true_roles=roles,
                true_role_phrase=phrase,proposition=prop,proposition_scope=country,source=source,
                tau=dict(same_subject=int(kind!='N'),relation_change=int(kind!='N'),
                    qualifier_change=int(kind=='P'),medium_change=0,creator_type_role=0,computable=0)))
        items.append(dict(item_id=iid,work_id=iid,structure='G2a',country=country,subject=country,
            question_en=f'What is the capital city of {country}?',gold=g,gold_aliases=aliases(g),
            answer_format='entity',candidates=candidates,source=BASE+url,
            population_standard='City Population；采用城市/市镇层级，不采用都会区人口',
            largest_city=dict(name=l,year=year,population=pop,scope=scope,source=BASE+url),
            no_wrong_largest_candidate=same_identity(l,g,aliases(g)),
            former_capital=None if not former else dict(name=former[0],start=former[1],end=former[2],source=former[3],scope=former[4]),
            side_candidates=[dict(name=name,type='P_prime',reason=reason,main_effect=False) for name,reason in SIDE.get(country,[])],
            trial_eligible_material=any(c['type']=='L' for c in candidates)))
    return items,excluded
