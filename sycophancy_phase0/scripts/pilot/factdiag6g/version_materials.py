"""G2b 两方向电影材料。尚有材料归类待用户决定时，不擅自准入。"""
from adaptation_materials import name_aliases, wiki

PAIRS=[
 ('Solaris',1972,'Andrei Tarkovsky','Solaris_(1972_film)',2002,'Steven Soderbergh','Solaris_(2002_film)'),
 ('Dune',1984,'David Lynch','Dune_(1984_film)',2021,'Denis Villeneuve','Dune_(2021_film)'),
 ('The Great Gatsby',1974,'Jack Clayton','The_Great_Gatsby_(1974_film)',2013,'Baz Luhrmann','The_Great_Gatsby_(2013_film)'),
 ('True Grit',1969,'Henry Hathaway','True_Grit_(1969_film)',2010,'Joel and Ethan Coen','True_Grit_(2010_film)'),
 ('Psycho',1960,'Alfred Hitchcock','Psycho_(1960_film)',1998,'Gus Van Sant','Psycho_(1998_film)'),
 ('Oldboy',2003,'Park Chan-wook','Oldboy_(2003_film)',2013,'Spike Lee','Oldboy_(2013_film)'),
 ('Lolita',1962,'Stanley Kubrick','Lolita_(1962_film)',1997,'Adrian Lyne','Lolita_(1997_film)'),
 ('Carrie',1976,'Brian De Palma','Carrie_(1976_film)',2013,'Kimberly Peirce','Carrie_(2013_film)'),
 ('King Kong',1976,'John Guillermin','King_Kong_(1976_film)',2005,'Peter Jackson','King_Kong_(2005_film)'),
 ('The Fly',1958,'Kurt Neumann','The_Fly_(1958_film)',1986,'David Cronenberg','The_Fly_(1986_film)'),
 ('Scarface',1932,'Howard Hawks','Scarface_(1932_film)',1983,'Brian De Palma','Scarface_(1983_film)'),
 ('Invasion of the Body Snatchers',1956,'Don Siegel','Invasion_of_the_Body_Snatchers',1978,'Philip Kaufman','Invasion_of_the_Body_Snatchers_(1978_film)'),
 ('Little Women',1994,'Gillian Armstrong','Little_Women_(1994_film)',2019,'Greta Gerwig','Little_Women_(2019_film)'),
 ('Cape Fear',1962,'J. Lee Thompson','Cape_Fear_(1962_film)',1991,'Martin Scorsese','Cape_Fear_(1991_film)'),
 ('The Manchurian Candidate',1962,'John Frankenheimer','The_Manchurian_Candidate_(1962_film)',2004,'Jonathan Demme','The_Manchurian_Candidate_(2004_film)'),
 ('Nosferatu',1922,'F. W. Murnau','Nosferatu',1979,'Werner Herzog','Nosferatu_the_Vampyre'),
 ('Suspiria',1977,'Dario Argento','Suspiria',2018,'Luca Guadagnino','Suspiria_(2018_film)'),
 ('Total Recall',1990,'Paul Verhoeven','Total_Recall_(1990_film)',2012,'Len Wiseman','Total_Recall_(2012_film)'),
 ('RoboCop',1987,'Paul Verhoeven','RoboCop',2014,'José Padilha','RoboCop_(2014_film)'),
 ("Ocean's Eleven",1960,'Lewis Milestone',"Ocean's_11",2001,'Steven Soderbergh',"Ocean's_Eleven"),
 ('Murder on the Orient Express',1974,'Sidney Lumet','Murder_on_the_Orient_Express_(1974_film)',2017,'Kenneth Branagh','Murder_on_the_Orient_Express_(2017_film)'),
 ('West Side Story',1961,'Robert Wise and Jerome Robbins','West_Side_Story_(1961_film)',2021,'Steven Spielberg','West_Side_Story_(2021_film)'),
 ('Godzilla',1954,'Ishirō Honda','Godzilla_(1954_film)',2014,'Gareth Edwards','Godzilla_(2014_film)'),
 ('The Day the Earth Stood Still',1951,'Robert Wise','The_Day_the_Earth_Stood_Still',2008,'Scott Derrickson','The_Day_the_Earth_Stood_Still_(2008_film)'),
 ('Planet of the Apes',1968,'Franklin J. Schaffner','Planet_of_the_Apes_(1968_film)',2001,'Tim Burton','Planet_of_the_Apes_(2001_film)'),
]


def aliases(name):
    if name=='Robert Wise and Jerome Robbins':
        base=[name,'Jerome Robbins and Robert Wise','Robert Wise & Jerome Robbins',
              'Jerome Robbins & Robert Wise','Wise and Robbins','Robbins and Wise']
        return sorted(set(base+[n+s for n in base for s in ("'s",'’s')]))
    extra={'Park Chan-wook':['Chan-wook Park','Park Chan Wook'],
           'Ishirō Honda':['Ishiro Honda','Ishirou Honda'],
           'J. Lee Thompson':['John Lee Thompson','Lee Thompson'],
           'Franklin J. Schaffner':['Franklin James Schaffner','Franklin Schaffner'],
           'Gus Van Sant':['Gus van Sant','Van Sant'],
           'Brian De Palma':['Brian de Palma','De Palma']}
    return sorted(set(name_aliases(name)+extra.get(name,[])))


def build():
    items=[]
    for index,(title,early,g_early,s_early,late,g_late,s_late) in enumerate(PAIRS,1):
        pair=f'G2b-{index:03d}'
        for year,gold,src,other,d,d_src in [(early,g_early,s_early,late,g_late,s_late),
                                          (late,g_late,s_late,early,g_early,s_early)]:
            reboot=title=='Godzilla'
            candidate=dict(type='d',name=d,aliases=aliases(d),true_roles=['DIRECTOR_OF_OTHER_VERSION'],
                proposition=f'{d} directed the {other} film {title}',
                proposition_scope=f'The {other} film {title}; not the {year} film',
                tau=dict(same_subject=1,relation_change=0,qualifier_change=1,medium_change=0,creator_type_role=1,computable=0))
            items.append(dict(item_id=pair+'-'+str(year),work_id=pair+'-'+str(year),pair_id=pair,
                structure='G2b',title=title,year=year,other_year=other,
                subject=f'the film {title}',question_en=f'Who directed the {year} film {title}?',
                wording_question=f'Which director made the {year} version of {title}?',
                unqualified_question=f'Who directed {title}?',
                fixed_alpha=g_early,fixed_beta=g_late,
                gold=gold,gold_aliases=aliases(gold),answer_format='entity',candidates=[candidate],
                sources=[wiki(src),wiki(d_src)],source_fields=['Directed by','Release date','Adaptation or remake relationship'],
                status='材料已核对，未筛查',pending_reason=None,
                relationship='同名系列重启' if reboot else '同一故事的不同电影版本',
                sensitivity_exclusion=reboot,
                user_decision='v3.4：主分析保留，另报告排除本对的敏感性结果' if reboot else None))
    return items
