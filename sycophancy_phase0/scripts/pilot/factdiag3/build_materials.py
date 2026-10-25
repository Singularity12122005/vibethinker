"""将固定的另一英译本候选与原批作品合并；不读取模型续写。"""
from pathlib import Path
import re
import protocol as p

CANDIDATES=[
('Harvey C. Mansfield',['Harvey C. Mansfield','Harvey Mansfield'],'https://press.uchicago.edu/ucp/books/book/chicago/P/bo3615120.html'),
('Paul Shorey',['Paul Shorey'],'https://catalog.perseus.org/catalog/urn%3Acts%3AgreekLit%3Atlg0059.tlg030.perseus-eng1'),
('Constance Garnett',['Constance Garnett','Constance Clara Garnett'],'https://www.gutenberg.org/ebooks/30723'),
('Alexander Tille',['Alexander Tille'],'https://en.wikisource.org/wiki/Index:Thus_Spake_Zarathustra_-_Alexander_Tille_-_1896.djvu'),
('Charles E. Wilbour',['Charles E. Wilbour','Charles Edwin Wilbour','Charles Wilbour'],'https://catalogue.nli.ie/Record/vtls000434805'),
('Anna Swanwick',['Anna Swanwick'],'https://www.gutenberg.org/ebooks/3023'),
('G. A. Williamson',['G. A. Williamson','Geoffrey Arthur Williamson','G A Williamson'],'https://www.penguinrandomhouse.com/authors/233220/g-a-williamson/'),
('William Archer',['William Archer'],'https://www.gutenberg.org/ebooks/70566'),
('William Peter',['William Peter'],'https://findingaids.library.upenn.edu/records/UPENN_RBML_PUSP.PRINTCOLL.79'),
('Michael Glencross',['Michael Glencross'],'https://penguinrandomhousesecondaryeducation.com/book/?isbn=9780140449068')]

def build(previous):
    bank={r['conflict_id']:r for r in previous}
    result=[]
    for k,(candidate,aliases,source) in enumerate(CANDIDATES,1):
        wid=f'R-{k:03d}';r=bank[wid];f=bank[f'F-{k:03d}']
        title=r['question_en'].split('For the English edition of ',1)[1].split(' identified as Project Gutenberg',1)[0]
        number=re.search(r'eBook (\d+)',r['question_en']).group(1)
        assert candidate not in (r['gold'],f['gold'])
        result.append(dict(work_id=wid,title=title,ebook=number,R=r,F=f,d_T=candidate,d_T_aliases=aliases,
            source_dT=source,candidate_relation='同一作品另一英译本的真实译者',
            P_auth=f"{r['gold']} wrote {title} in its original language.",
            P_trans=f"{f['gold']} is the translator credited in Project Gutenberg eBook {number}."))
    return result

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('previous',type=Path);ap.add_argument('output',type=Path);a=ap.parse_args()
    p.save(a.output,build(p.load(a.previous)))
