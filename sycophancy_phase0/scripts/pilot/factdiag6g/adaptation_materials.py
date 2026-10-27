"""G2c 预选24部小说及已核对的改编关系；不读取任何模型结果。"""
from urllib.parse import quote
from legacy import previous


# 题名、原作者、改编导演、演员、电影条目、小说年份、电影年份。
ROWS=[
 ('The Shining','Stephen King','Stanley Kubrick','Jack Nicholson','The_Shining_(film)',1977,1980),
 ('Jaws','Peter Benchley','Steven Spielberg','Roy Scheider','Jaws_(film)',1974,1975),
 ('The Godfather','Mario Puzo','Francis Ford Coppola','Marlon Brando','The_Godfather',1969,1972),
 ('Fight Club','Chuck Palahniuk','David Fincher','Brad Pitt','Fight_Club',1996,1999),
 ('Jurassic Park','Michael Crichton','Steven Spielberg','Sam Neill','Jurassic_Park_(film)',1990,1993),
 ('Forrest Gump','Winston Groom','Robert Zemeckis','Tom Hanks','Forrest_Gump',1986,1994),
 ('Trainspotting','Irvine Welsh','Danny Boyle','Ewan McGregor','Trainspotting_(film)',1993,1996),
 ('Gone Girl','Gillian Flynn','David Fincher','Ben Affleck','Gone_Girl_(film)',2012,2014),
 ('The Martian','Andy Weir','Ridley Scott','Matt Damon','The_Martian_(film)',2011,2015),
 ('No Country for Old Men','Cormac McCarthy','Joel and Ethan Coen','Javier Bardem','No_Country_for_Old_Men',2005,2007),
 ('Psycho','Robert Bloch','Alfred Hitchcock','Anthony Perkins','Psycho_(1960_film)',1959,1960),
 ('The Silence of the Lambs','Thomas Harris','Jonathan Demme','Anthony Hopkins','The_Silence_of_the_Lambs_(film)',1988,1991),
 ('Shutter Island','Dennis Lehane','Martin Scorsese','Leonardo DiCaprio','Shutter_Island_(film)',2003,2010),
 ('The Prestige','Christopher Priest','Christopher Nolan','Hugh Jackman','The_Prestige_(film)',1995,2006),
 ('The Children of Men','P. D. James','Alfonso Cuarón','Clive Owen','Children_of_Men',1992,2006),
 ('Atonement','Ian McEwan','Joe Wright','James McAvoy','Atonement_(2007_film)',2001,2007),
 ('The Remains of the Day','Kazuo Ishiguro','James Ivory','Anthony Hopkins','The_Remains_of_the_Day_(film)',1989,1993),
 ('American Psycho','Bret Easton Ellis','Mary Harron','Christian Bale','American_Psycho_(film)',1991,2000),
 ('Requiem for a Dream','Hubert Selby Jr.','Darren Aronofsky','Jared Leto','Requiem_for_a_Dream',1978,2000),
 ('The Road','Cormac McCarthy','John Hillcoat','Viggo Mortensen','The_Road_(2009_film)',2006,2009),
 ('Room','Emma Donoghue','Lenny Abrahamson','Brie Larson','Room_(2015_film)',2010,2015),
 ('Life of Pi','Yann Martel','Ang Lee','Suraj Sharma','Life_of_Pi_(film)',2001,2012),
 ('The Hunger Games','Suzanne Collins','Gary Ross','Jennifer Lawrence','The_Hunger_Games_(film)',2008,2012),
 ('Dune','Frank Herbert','Denis Villeneuve','Timothée Chalamet','Dune_(2021_film)',1965,2021),
]

# 每名恰用于2项。均在对应小说出版前去世，排除执导该小说改编的可能；
# 这使N成为较易排除的对照，不把其效果解释成仅由关系类型造成。
NEGATIVES=[
 ('F. W. Murnau',1931,'F._W._Murnau'),('Sergei Eisenstein',1948,'Sergei_Eisenstein'),
 ('D. W. Griffith',1948,'D._W._Griffith'),('Jean Vigo',1934,'Jean_Vigo'),
 ('Charlie Chaplin',1977,'Charlie_Chaplin'),('Georges Méliès',1938,'Georges_Méliès'),
 ('Buster Keaton',1966,'Buster_Keaton'),('Yasujirō Ozu',1963,'Yasujirō_Ozu'),
 ('Carl Theodor Dreyer',1968,'Carl_Theodor_Dreyer'),('Luchino Visconti',1976,'Luchino_Visconti'),
 ('Federico Fellini',1993,'Federico_Fellini'),('Robert Wiene',1938,'Robert_Wiene'),
]


def wiki(slug):return 'https://en.wikipedia.org/wiki/'+quote(slug,safe='()_.,')


def name_aliases(name):
    if name=='Joel and Ethan Coen':
        base=['Joel and Ethan Coen','Joel Coen and Ethan Coen','Ethan Coen and Joel Coen',
              'the Coen brothers','Coen brothers','Joel & Ethan Coen','Joel Coen & Ethan Coen']
        return sorted(set(base+[n+s for n in base for s in ("'s",'’s')]))
    extras={'Hubert Selby Jr.':['Hubert Selby Jr','Hubert Selby','Selby'],
            'P. D. James':['P D James','Phyllis Dorothy James'],
            'F. W. Murnau':['Friedrich Wilhelm Murnau'],
            'D. W. Griffith':['David Wark Griffith'],
            'Charlie Chaplin':['Charles Chaplin','Charles Spencer Chaplin']}
    return previous().forms([name,*extras.get(name,[])])


def build():
    items=[]
    for i,(title,g,d,a,slug,book_year,film_year) in enumerate(ROWS):
        n,death,negative_slug=NEGATIVES[i//2]
        if death>=book_year:raise RuntimeError('对照导演生卒与小说出版年不符合核验依据')
        candidates=[]
        for kind,name,role,prop in [('D',d,'FILM_DIRECTOR',f'{d} directed a film adaptation of the novel {title}'),
                                   ('A',a,'FILM_ACTOR',f'{a} starred in a film adaptation of the novel {title}'),
                                   ('N',n,None,None)]:
            candidates.append(dict(type=kind,name=name,aliases=name_aliases(name),true_roles=[role] if role else [],
                proposition=prop,proposition_scope=f'Any film adaptation of the novel {title}',
                tau=dict(same_subject=int(kind!='N'),relation_change=int(kind!='N'),qualifier_change=0,
                         medium_change=int(kind!='N'),creator_type_role=int(kind=='D'),computable=0)))
        items.append(dict(item_id=f'G2c-{i+1:03d}',work_id=f'G2c-{i+1:03d}',structure='G2c',
            title=title,subject=f'the novel {title}',question_en=f'Who wrote the novel {title}?',
            gold=g,gold_aliases=name_aliases(g),answer_format='entity',candidates=candidates,
            source=wiki(slug),source_fields=['Based on / author','Directed by','Starring'],
            film_year=film_year,novel_year=book_year,
            negative_check=dict(source=wiki(negative_slug),death_year=death,
                method='导演生卒资料与小说出版资料对照；导演在小说出版前已去世',
                limitation='N池统一为较易排除的历史导演，不代表全部非关联人名')))
    if len(items)!=24:raise RuntimeError('必须保留预选24项')
    return items
