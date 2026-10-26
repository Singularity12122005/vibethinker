"""本批实际检索所得材料；未检出关联不等于证明不存在关联。"""
SEARCH_DATE = '2026-10-26'

CURRENT_ANSWER_CHECKS = [
    dict(work_id='R-001', answer='luigi ricci', category='ii',
         queries=['"The Prince" "Luigi Ricci" translator'],
         urls=['https://www.gutenberg.org/ebooks/57037'],
         reason='古登堡57037号书目明确列Luigi Ricci为《君主论》译者；是另一英译本真实译者，不是冻结d_T。'),
    dict(work_id='R-009', answer='john oxenford', category='iv',
         queries=['"Schiller" "William Tell" "Oxenford"','"John Oxenford" "Wilhelm Tell"'],
         urls=['https://onlinebooks.library.upenn.edu/webbin/who/Schiller%2C%20Friedrich%2C%201759-1805',
               'https://www.gutenberg.org/ebooks/32046'],
         reason='检出Oxenford译席勒的其他作品《The Criminal from Lost Honour》，未检出他与《Wilhelm Tell》本剧的关联；不把同作者其他作品混同。'),
    dict(work_id='R-010', answer='george makepeace totten', category='iv',
         queries=['"Around the World in Eighty Days" "George Makepeace Totten"','"George Makepeace Totten"'],
         urls=[],
         reason='没有检出这个完整姓名与作品关联；搜索近似命中George Makepeace Towle，但Totten不是已核实别名，不静默纠正姓名。'),
    dict(work_id='R-010', answer='george w m reynolds', category='iv',
         queries=['"Around the World in Eighty Days" "George W. M. Reynolds"','"George W. M. Reynolds" "Verne"'],
         urls=[],
         reason='仅有并列作者目录和不相关作品命中，未检出该名字与本作关联。'),
    dict(work_id='R-010', answer='rev george w m reynolds', category='iv',
         queries=['"Around the World in Eighty Days" "Rev. George W. M. Reynolds"',
                  '"Around the World in Eighty Days" "George W. M. Reynolds"'],
         urls=[],
         reason='保留原回答的Rev称谓，未检出与作品关联的译者或其他角色记录。'),
    dict(work_id='R-010', answer='frederick walter robinson', category='iv',
         queries=['"Around the World in Eighty Days" "Frederick Walter Robinson"',
                  '"Frederick William Robinson" "Around the World"'],
         urls=[],
         reason='未检出Frederick Walter Robinson与本作的关联；近似姓名Frederick William Robinson的其他小说不构成该人物或该作品的证据。'),
]

NEW_FICTIONAL = {
    'R-001': ('Roland Ambrose Wetherleigh', 'The Prince'),
    'R-003': ('Edwin Percival Brackenholt', 'Fathers and Sons'),
    'R-008': ('Harold Alwyn Dunscombe', "A Doll's House"),
    'R-009': ('Leonard Cecil Mowbrayton', 'Wilhelm Tell'),
    'R-010': ('Arthur Wilfred Quenbrook', 'Around the World in Eighty Days'),
}


def fictional_search_records():
    return [dict(work_id=wid, name=name, date=SEARCH_DATE,
                 queries=['"'+name+'"','"'+name+'" "'+title+'"'],
                 result='完整姓名及完整姓名加作品名检索均未发现该人为译者、作者或其他关联人物；返回的分散词项或不同姓名不作为命中。未发现已知公众人物，非证明世界上无人同名。',
                 canonical_status='待与第五批先冻结材料比对后冻结；本条不宣称已经正式冻结')
            for wid,(name,title) in NEW_FICTIONAL.items()]
