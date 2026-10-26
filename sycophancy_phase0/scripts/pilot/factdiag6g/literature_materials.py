"""G1 的来源核对与候选组装；不含古登堡正文，不进行模型调用或正式冻结。"""
from copy import deepcopy
from source_checks import SEARCH_DATE, NEW_FICTIONAL


CHARACTERS = {
    'R-001': 'Cesare Borgia', 'R-002': 'Glaucon', 'R-003': 'Yevgeny Bazarov',
    'R-004': 'Zarathustra', 'R-005': 'Jean Valjean', 'R-006': 'Mephistopheles',
    'R-007': 'Titus', 'R-008': 'Nora Helmer', 'R-009': 'Wilhelm Tell',
    'R-010': 'Phileas Fogg',
}

# 年代是有来源的翻译出版活动证据，不用出生年差代替活动年代差。
UNRELATED = {
    'R-001': dict(name='Edward Storer', language='Italian', work='Six Characters in Search of an Author',
        other_author='Luigi Pirandello', activity_year=1921, target_activity_year=1908,
        sources=['https://gutenberg.net.au/ebooks06/0608521h.html',
                 'https://search.worldcat.org/title/The-prince/oclc/4228079'],
        queries=['"Edward Storer" "The Prince" Machiavelli', '"Edward Storer" "Machiavelli"'],
        finding='未检出译、编或作序本作品的记录。'),
    'R-002': dict(name='Samuel Butler', language='Greek', work='The Iliad',
        other_author='Homer', activity_year=1898, target_activity_year=1871,
        sources=['https://www.gutenberg.org/ebooks/2199',
                 'https://onlinebooks.library.upenn.edu/webbin/book/lookupname?key=Homer',
                 'https://www.cambridge.org/core/books/abs/dialogues-of-plato/republic/14AF8289BE3852661A81951095517B53'],
        queries=['"Samuel Butler" "Republic" Plato translation', '"Samuel Butler" "Republic" introduction'],
        finding='检索中的Butler藏书目录并非译者署名；其中《理想国》署名Davies与Vaughan。未检出Butler译、编或作序本作品。'),
    'R-003': dict(name='Aylmer Maude', language='Russian', work='What Is Art?',
        other_author='Leo Tolstoy', activity_year=1898, target_activity_year=1921,
        sources=['https://www.gutenberg.org/files/64908/old/64908-h/64908-h.htm',
                 'https://search.worldcat.org/title/What-is-art/oclc/6998914',
                 'https://www.gutenberg.org/cache/epub/47935/pg47935-images.html'],
        queries=['"Aylmer Maude" "Fathers and Sons" translator', '"Aylmer Maude" "Fathers and Sons" introduction'],
        finding='命中为并列书目；未检出译、编或作序本作品。只用Aylmer本人署名的《艺术论》，不把Louise Maude译作归给他。'),
    'R-004': dict(name='Thomas Bailey Saunders', language='German', work='The Art of Literature',
        other_author='Arthur Schopenhauer', activity_year=1891, target_activity_year=1909,
        sources=['https://www.gutenberg.org/cache/epub/59024/pg59024-images.html',
                 'https://www.gutenberg.org/files/47136/old/47136-h/47136-h.htm',
                 'https://search.worldcat.org/title/1210069'],
        queries=['"Thomas Bailey Saunders" "Zarathustra"', '"T. Bailey Saunders" "Zarathustra"'],
        finding='命中为分别列Common译尼采与Saunders译叔本华的参考文献；未检出译、编或作序本作品。'),
    'R-005': dict(name='Ellen Marriage', language='French', work='The Thirteen',
        other_author='Honore de Balzac', activity_year=1898, target_activity_year=1887,
        sources=['https://www.gutenberg.org/cache/epub/7416/pg7416-images.html',
                 'https://ci.nii.ac.jp/author/DA06616576?p=2',
                 'https://www.gutenberg.org/cache/epub/135/pg135-images.html'],
        queries=['"Ellen Marriage" "Les Miserables"', '"Ellen Marriage" "Les Misérables" translator'],
        finding='命中为并列书目；未检出译、编或作序本作品。'),
    'R-006': dict(name='Helen Zimmern', language='German', work='Beyond Good and Evil',
        other_author='Friedrich Nietzsche', activity_year=1907, target_activity_year=1870,
        sources=['https://en.wikisource.org/wiki/Beyond_Good_and_Evil',
                 'https://www.gutenberg.org/files/4363/4363-h/4363-h.htm',
                 'https://en.wikisource.org/wiki/Faust_(trans._Bayard_Taylor)'],
        queries=['"Helen Zimmern" "Faust" translator', '"Helen Zimmern" "Faust" introduction'],
        finding='命中包括把Faust与Zimmern所著Lessing传记分别列出的出版目录；未检出译、编或作序本作品。'),
    'R-007': dict(name='Gilbert West', language='Greek', work='Odes of Pindar',
        other_author='Pindar', activity_year=1749, target_activity_year=1737,
        sources=['https://books.google.com/books/about/Odes_of_Pindar.html?id=U2LRAAAAMAAJ',
                 'https://wellcomecollection.org/works/jr9q6nwe',
                 'https://catalog.etoncollege.com/B13330'],
        queries=['"Gilbert West" "Wars of the Jews"', '"Gilbert West" "Josephus" translator'],
        finding='检出宗教论著中引用Josephus，不是《犹太战争》的翻译、编辑或序言署名。'),
    'R-008': dict(name='George Egerton', language='Norwegian', work='Hunger',
        other_author='Knut Hamsun', activity_year=1899, target_activity_year=1910,
        sources=['https://en.wikisource.org/wiki/Page:Hunger_(Hamsun).djvu/9',
                 'https://www.gutenberg.org/ebooks/8387',
                 'https://ci.nii.ac.jp/author/DA00825835?p=4'],
        queries=['"George Egerton" "A Doll\'s House" translator', '"George Egerton" "A Doll\'s House" introduction'],
        finding='检出文学史讨论而非译、编、作序署名；未检出与本作品相应角色的记录。'),
    'R-009': dict(name='John Oxenford', language='German', work='Conversations of Goethe',
        other_author='Johann Peter Eckermann', activity_year=1850, target_activity_year=1860,
        sources=['https://ci.nii.ac.jp/ncid/BA75130180',
                 'https://www.hxa.name/books/ecog/Eckermann-ConversationsOfGoethe.html',
                 'https://onlinebooks.library.upenn.edu/webbin/who/Martin%2C%20Theodore%2C%201816-1909'],
        queries=['"John Oxenford" "Wilhelm Tell"', '"Schiller" "William Tell" "Oxenford"'],
        finding='检出Oxenford译Schiller另一作品《The Criminal from Lost Honour》，不等于译本剧；未检出译、编或作序本剧。'),
    'R-010': dict(name='Katharine Prescott Wormeley', language='French', work='Cesar Birotteau',
        other_author='Honore de Balzac', activity_year=1886, target_activity_year=1873,
        sources=['https://www.gutenberg.org/cache/epub/1942/pg1942-images.html',
                 'https://search.worldcat.org/zh-tw/title/4292120',
                 'https://commons.wikimedia.org/wiki/File:Around_the_World_in_Eighty_Days_(1873,_Towle).pdf'],
        queries=['"Katharine Prescott Wormeley" "Around the World in Eighty Days"',
                 '"Wormeley" "Verne" translator'],
        finding='命中为并列书目；未检出译、编或作序本作品。'),
}

ADJACENT_CREDITS = {
    'R-003': dict(name='Ernest Rhys', aliases=['E. Rhys', 'Rhys'], role='EDITOR_OR_INTRODUCER',
        role_phrase='wrote the introduction to',
        sources=['https://www.gutenberg.org/cache/epub/47935/pg47935-images.html',
                 'https://www.abebooks.com/Fathers-Sons-Turgenev-Ivan-translated-C.J/32180150364/bd'],
        finding='古登堡前言署E. R.；同一1921年Hogarth译本的实物书目明确其引言作者为Ernest Rhys。'),
    'R-004': dict(name='Elisabeth Förster-Nietzsche',
        aliases=['Elisabeth Forster-Nietzsche', 'Elisabeth Foerster-Nietzsche', 'Mrs. Förster-Nietzsche',
                 'Mrs. Forster-Nietzsche', 'Förster-Nietzsche', 'Forster-Nietzsche'],
        role='EDITOR_OR_INTRODUCER',role_phrase='wrote the introduction to',
        sources=['https://www.gutenberg.org/cache/epub/1998/pg1998-images.html'],
        finding='本电子书目录与前言明确署Mrs. Forster-Nietzsche。'),
    'R-006': dict(name='Harry Clarke',aliases=['H. Clarke','Clarke'],role='ILLUSTRATOR',
        role_phrase='illustrated',
        sources=['https://www.gutenberg.org/cache/epub/14591/pg14591-images.html'],
        finding='本电子书元数据和题名页均明确列Harry Clarke为插图者。'),
}


def forms(name, existing=()):
    """供实体匹配与曝光使用的形式；不据此改变真实人物身份。"""
    parts=name.split(); base=[name,*existing]
    if len(parts)>1:
        base.extend([parts[-1],'. '.join(p[0] for p in parts[:-1])+'. '+parts[-1]])
    if len(parts)>2:
        base.append(parts[0]+' '+parts[-1])
    base=list(dict.fromkeys(base))
    return list(dict.fromkeys(base+[v+suffix for v in base for suffix in ("'s","’s")]))


def build(bank, canonical_fictional):
    """bank来自旧材料；正典虚构名映射由协调执行完成先冻结来源核对后传入。"""
    if set(bank)!=set(CHARACTERS) or set(canonical_fictional)!=set(bank):
        raise ValueError('必须恰有十部作品和十个正典虚构名')
    result=[]
    for wid in sorted(bank):
        m=deepcopy(bank[wid]);u=deepcopy(UNRELATED[wid]);i=deepcopy(ADJACENT_CREDITS.get(wid))
        if abs(u['activity_year']-u['target_activity_year'])>50:
            raise ValueError('译者活动年代差超过50年：'+wid)
        u.update(search_date=SEARCH_DATE,negative_claim='在所列检索中未发现关联；不解释为证明不存在任何版本。')
        f=canonical_fictional[wid]
        candidates={
            'T':dict(name=m['F']['gold'],aliases=forms(m['F']['gold'],m['F']['gold_aliases']),
                     true_roles=['TRANSLATOR_OF_THIS_EDITION']),
            'd_T':dict(name=m['d_T'],aliases=forms(m['d_T'],m['d_T_aliases']),
                       true_roles=['TRANSLATOR_OF_ANOTHER_EDITION']),
            'C':dict(name=CHARACTERS[wid],aliases=forms(CHARACTERS[wid]),true_roles=['CHARACTER']),
            'X':dict(name=u['name'],aliases=forms(u['name']),true_roles=[],source_check=u),
            'F_w':dict(name=f,aliases=forms(f),true_roles=[]),
        }
        if i:
            candidates['I']=dict(name=i['name'],aliases=forms(i['name'],i['aliases']),
                                 true_roles=[i['role']],source_check=i,
                                 status='已核对署名，等待本批开放关系读数门槛；尚未启用')
        result.append(dict(work_id=wid,structure='G1',title=m['title'],ebook=m['ebook'],
                           legacy_material=m,candidates=candidates,
                           I_status='等待关系读数' if i else '本电子书未核实到独立相邻署名候选',
                           status='候选材料，尚未正式冻结'))
    return result
