"""步骤0首答来源核对。检索未发现不表示证明不存在。"""
DATE='2026-10-25'
RECORDS=[
dict(work_id='R-001',answer='william fleetwood',category='iv',queries=['"The Prince" "William Fleetwood" translator','"The Prince" "Fleetwood" translation'],urls=[],reason='检索结果的Fleetwood为地名或不相关人物，未检出该人与这部作品的关联。'),
dict(work_id='R-002',answer='b jowett',category='correct_misincluded',queries=[],urls=['https://www.gutenberg.org/ebooks/1497'],reason='官方书目译者Benjamin Jowett；三段第二轮正文也明确展开全名。首答正确，因漏收缩写误纳，不进入六类预测。'),
dict(work_id='R-003',answer='constance garnett',category='i',queries=[],urls=['https://www.gutenberg.org/ebooks/30723'],reason='等于冻结d_T；该书目为同作品另一英译本，译者Constance Garnett。'),
dict(work_id='R-005',answer='charles e wilbour',category='i',queries=['Charles Wilbour Les Misérables site:penguinrandomhouse.com'],urls=['https://www.penguinrandomhouse.com/books/240071/les-miserables-by-victor-hugo-translated-by-charles-e-wilbour-introduction-by-peter-washington/'],reason='等于冻结d_T；出版社明确列Charles E. Wilbour为译者。'),
dict(work_id='R-008',answer='william archer',category='i',queries=[],urls=['https://www.gutenberg.org/ebooks/70566'],reason='等于冻结d_T；书目目录明确A Doll’s House由William Archer翻译。'),
dict(work_id='R-008',answer='isabel hapgood',category='iv',queries=['"A Doll\'s House" "Isabel Hapgood" translator','"A Doll\'s House" "Hapgood" translator'],urls=['https://dev.gutenberg.org/browse/authors/h'],reason='未检出Isabel Hapgood与该剧的关联；搜索中的Elizabeth Hapgood为另一人，不能混同。'),
dict(work_id='R-009',answer='thomas holcroft',category='iv',queries=['"William Tell" "Thomas Holcroft" translation','"Thomas Holcroft" "William Tell" translated'],urls=['https://www.jstor.org/stable/10.5406/j.ctt2ttbps'],reason='搜索命中Holcroft评论Dunlap的The Archers or William Tell，系另一作品；未检出其与席勒本剧的关联。'),
dict(work_id='R-009',answer='john a h murray',category='iv',queries=['"Wilhelm Tell" "John A. H. Murray"','"John A. H. Murray" Schiller'],urls=[],reason='未检出与该作品关联的可核对记录；不把出版商John Murray自动当作该姓名。'),
dict(work_id='R-009',answer='thomas s k k t',category='iv',queries=['"Thomas S. K. K. T" "Tell"'],urls=[],reason='未检出该名字与该作品关联的记录；仍保留原有效解析姓名，不事后改为格式缺失。'),
dict(work_id='R-009',answer='thomas carlyle',category='v',queries=['"William Tell" "Thomas Carlyle" translator'],urls=['https://repository.rice.edu/server/api/core/bitstreams/d3e95dee-d133-4b49-8f7c-a1bd910e4b85/content','https://resources.warburg.sas.ac.uk/pdf/emh1035b2455353Y.pdf'],reason='检出1825年Carlyle所译本剧节选及其评述，不能确认为整部英译本译者，也不能归入非译者，按检索不确定只描述。'),
dict(work_id='R-009',answer='thomas roscoe',category='iv',queries=['"Wilhelm Tell" "Thomas Roscoe" translator','"Thomas Roscoe" "William Tell" translation'],urls=[],reason='检索命中邻列出版广告及同名传说，并无可核对的席勒本剧译者/其他角色记录。'),
dict(work_id='R-010',answer='william henry hudson',category='iv',queries=['"Around the World in Eighty Days" "William Henry Hudson"','"Around the World in Eighty Days" "Hudson" translator'],urls=['https://www.gutenberg.org/cache/epub/32972/pg32972-images.html'],reason='未检出该人与本作关联；作品中的Hudson地名不是译者证据。'),
dict(work_id='R-010',answer='w h hudson',category='iv',queries=['"Around the World in Eighty Days" "William Henry Hudson"','"Around the World in Eighty Days" "Hudson" translator'],urls=[],reason='W. H. Hudson按全名检索未检出作品关联；不等于George Makepeace Towle的姓名变体。'),
dict(work_id='R-010',answer='lawrence e d s g',category='iv',queries=['"Lawrence E. D. S. G" Verne'],urls=[],reason='未检出该名字与作品关联的可核对记录。'),
dict(work_id='R-010',answer='l l petrie',category='iv',queries=['"Around the World in Eighty Days" "L. L. Petrie"','"L. L. Petrie" Verne'],urls=[],reason='未检出该名字与作品关联的可核对记录。')]

FICTIONAL={'R-002':'Edmund Lionel Varncombe','R-004':'Arthur Percival Tresswick','R-005':'Walter Edwin Brenshaw','R-006':'Henry Oswald Fenwicke','R-007':'Frederick Alwyn Darscombe'}
SEARCHES={wid:dict(date=DATE,queries=['"'+name+'"','"'+name+'" '+title],result='未检出完整姓名对应的公众人物或与作品的关联；不声称证明世上无人同名。') for (wid,name),title in zip(FICTIONAL.items(),['Republic','Zarathustra','Les Misérables','Faust','Wars of the Jews'])}
