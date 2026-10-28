"""V前向读数的另一版本材料；只保留书目信息，不保存原文。"""
from copy import deepcopy


VERSION_RECORDS = {
    "R-001": dict(E_prime="University of Chicago Press, second edition, 1998",
        other_translator="Harvey C. Mansfield", other_translator_verified=True,
        source="https://press.uchicago.edu/ucp/books/book/chicago/P/bo3615120.html",
        location="版本标题、译者署名、版权年份",
        finding="出版社列第二版、1998年及该译者。"),
    "R-002": dict(E_prime="Loeb Classical Library, Harvard University Press and W. Heinemann, 1935",
        other_translator="Paul Shorey", other_translator_verified=True,
        source="https://catalog.perseus.org/catalog/urn:cts:greekLit:tlg0059.tlg030.perseus-eng1",
        location="译者、丛书、出版社、出版年份字段",
        finding="大学项目目录独立列明译者及1935年丛书版。"),
    "R-003": dict(E_prime="Project Gutenberg eBook 30723",
        other_translator="Constance Garnett", other_translator_verified=True,
        source="https://www.gutenberg.org/ebooks/30723", location="Translator贡献者字段",
        finding="目录直接列明该译者，标题别名包含同一作品。"),
    "R-004": dict(E_prime="the 1896 edition",
        other_translator="Alexander Tille", other_translator_verified=True,
        source="https://en.wikisource.org/wiki/Index:Thus_Spake_Zarathustra_-_Alexander_Tille_-_1896.djvu",
        location="既有扫描本索引的译者与年份字段",
        finding="沿用既有来源的1896年版本与译者登记；标识不含译者姓名。"),
    "R-005": dict(E_prime="Everyman's Library, 1998",
        other_translator="Charles E. Wilbour", other_translator_verified=True,
        source="https://www.penguinrandomhouse.com/books/240071/les-miserables-by-victor-hugo-translated-by-charles-e-wilbour-introduction-by-peter-washington/",
        location="产品信息与译者署名，ISBN 9780375403170",
        finding="第四批source_audit已有的出版社来源列1998年3月31日、丛书及翻译署名；原爱尔兰国家图书馆链接本次返回403。"),
    "R-006": dict(E_prime="Project Gutenberg eBook 3023",
        other_translator="Anna Swanwick", other_translator_verified=False,
        source="https://www.gutenberg.org/ebooks/3023",
        additional_source="https://www.gutenberg.org/ebooks/3023.txt.utf-8",
        location="目录与远端全文的署名检索",
        finding="目录没有译者字段；本次在A100检索全文未检出Swanwick。不能据此确认该电子书的翻译署名，也不推断其译者一定不是此人。"),
    "R-007": dict(E_prime="Penguin Classics, 1959",
        other_translator="G. A. Williamson", other_translator_verified=True,
        source="https://www.penguinrandomhouse.com/authors/233220/g-a-williamson/",
        location="出版社译者简介",
        finding="出版社明确说明其1959年为该丛书翻译本作品。"),
    "R-008": dict(E_prime="Project Gutenberg eBook 70566",
        other_translator="William Archer", other_translator_verified=True,
        source="https://www.gutenberg.org/ebooks/70566", location="Contents内容字段",
        finding="贡献者角色为编者，不能挪用为译者；内容字段独立明确本卷中的该剧由此人翻译。"),
    "R-009": dict(E_prime="the third edition published by A. Gebhardt and Williams & Norgate in 1873",
        other_translator="William Peter", other_translator_verified=False,
        source="https://findingaids.library.upenn.edu/records/UPENN_RBML_PUSP.PRINTCOLL.79",
        location="第三箱第三十文件夹的1873年第三版记录",
        finding="既有档案目录核实版次、出版社和年份，但明确署名是注释与插图；没有把该条记录自行扩写成翻译署名。"),
    "R-010": dict(E_prime="Penguin Classics, 2004",
        other_translator="Michael Glencross", other_translator_verified=True,
        source="https://www.penguinrandomhouse.com/books/294033/around-the-world-in-eighty-days-by-jules-verne-translated-with-notes-by-michael-glencross-introduction-by-brian-aldiss-cover-illustrated-by-coralie-bickford-smith/",
        original_source="https://penguinrandomhousesecondaryeducation.com/book/?isbn=9780140449068",
        location="出版社平装出版日期、丛书与翻译署名",
        finding="同一出版社页面列2004年5月4日平装版及该翻译署名。"),
}


def attach_version_materials(materials):
    result = []
    for original in materials:
        m = deepcopy(original)
        record = deepcopy(VERSION_RECORDS[m["work_id"]])
        if record["other_translator"] != m["d_T"]:
            raise ValueError("另一版本译者与冻结候选材料不一致：" + m["work_id"])
        if any(name.casefold() in record["E_prime"].casefold() for name in (m["F"]["gold"], m["d_T"])):
            raise ValueError("版本标识不得泄露候选译者姓名")
        gate = m.get("evidence_gate", {})
        current_verified = ((gate.get("catalog_contributors_checked") is True and
            m["F"]["gold"] in gate.get("catalog_translator_names", [])) or
            (gate.get("title_page_credits_checked") is True and
             m["F"]["gold"] in gate.get("title_page_translator_names", [])))
        distinct = m["F"]["gold"] != m["d_T"]
        m.update(E_prime=record["E_prime"], version_control_applicable=bool(
            current_verified and record["other_translator_verified"] and distinct),
            version_check=dict(record, current_translator_verified=current_verified,
                               distinct_translators=distinct,
                               interpretation="不适用作品仅用于限定变化读数，不解释为版本辨别。"))
        result.append(m)
    return result
