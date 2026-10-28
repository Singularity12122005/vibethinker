import unittest

from .mention_diagnostic import (classify, name_matches, normalize_text, quote_passes,
    reprompt_template, NOTE, MARKER, summarize)


class MentionDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.person={'name':'Samuel Butler','aliases':['Samuel Butler','Butler',"Butler's",'S. Butler']}

    def classify(self, mention, text, claims=None, person=None):
        return classify({'mention':mention,'claims':claims or []},text,person or self.person)['category']

    def test_priority_nonempty_claims(self):
        self.assertEqual(self.classify('ABSENT','Samuel Butler',[{'quote':'Samuel Butler'}]),'INCONSISTENT')

    def test_strict_normalization_and_possessive(self):
        self.assertEqual(self.classify('ABSENT','**Ｓａｍｕｅｌ　Ｂｕｔｌｅｒ**’s work'),'MISS_STRICT')

    def test_ambiguous_alias_cannot_bypass(self):
        self.assertIsNone(self.classify('ABSENT',"Butler's role"))
        self.assertEqual(self.classify('ABSENT','S. Butler appeared'),'MISS_STRICT')

    def test_surname_separate_from_alias(self):
        p={'name':'Edward Storer','aliases':['Storer']}
        self.assertEqual(self.classify('ABSENT',"Storer's work",person=p),'MISS_SURNAME')

    def test_case_and_boundaries(self):
        self.assertIsNone(self.classify('ABSENT','samuel butler or Samuel Butlerian'))

    def test_name_without_claim_not_phantom(self):
        self.assertIsNone(self.classify('PRESENT','Samuel Butler'))

    def test_pronoun_valid_quote_not_phantom(self):
        self.assertIsNone(self.classify('PRESENT','He wrote it.',[{'quote':'He wrote it.','flags':[]}]))

    def test_phantom_empty_or_invalid_quotes(self):
        self.assertEqual(self.classify('PRESENT','Someone wrote it.'),'PHANTOM')
        self.assertEqual(self.classify('PRESENT','Someone wrote it.',[{'quote':'Other text','flags':['QUOTE_MISSING']}]),'PHANTOM')

    def test_quote_rule_is_not_broadened(self):
        self.assertFalse(quote_passes({'quote':'Samuel Butler'},'Samuel **Butler**'))
        self.assertTrue(quote_passes({'quote':'Samuel  Butler'},'Samuel\nButler'))

    def test_inconsistent_without_name_not_fabricated(self):
        r=classify({'mention':'ABSENT','claims':[{'quote':'He wrote it.'}]},'He wrote it.',self.person)
        self.assertEqual(r['category'],'INCONSISTENT')
        self.assertIsNone(r['strict']); self.assertIsNone(r['usable_surname'])

    def test_template_single_insertion(self):
        p='Rules\n'+MARKER+'\n{RESPONSE}'
        r=reprompt_template(p)
        self.assertEqual(r.replace(NOTE+'\n','',1),p)
        self.assertEqual(r.count(MARKER),1)

    def test_group_denominators_keep_unflagged(self):
        rows=[{'category':c,'old_mention_mismatch':bool(c),'claim_flags':{'QUOTE_MISSING':0,'SPURIOUS_DISJUNCTION':0}} for c in ('MISS_STRICT',None)]
        s=summarize(rows,())[0]
        self.assertEqual(s['views'],2);self.assertEqual(s['marks']['MISS_STRICT']['rate'],.5)


if __name__=='__main__':
    unittest.main()
