import json
import unittest

from quote_repair import reparsed, supported


class QuoteRepairTests(unittest.TestCase):
    def test_display_variations(self):
        for quote, response in [
            ('the original author remains Ada', 'The original author remains Ada.'),
            ('list Ben as the translator', 'list **Ben** as the translator'),
            ("The key word is 'original author'", 'The key word is "original author"'),
            ('Ada is the author', 'Ada  is\n the author'),
        ]:
            with self.subTest(quote=quote):
                self.assertTrue(supported(quote, response))

    def test_words_and_boundaries_remain_material(self):
        for quote, response in [
            ('Ada is the author', 'Ada is not the author'),
            ('Ben is the author', 'Ada is the author'),
            ('Ada is the author', 'Ada is the authorship claimant'),
            ("Ada doesnt write it", "Ada doesn't write it"),
            ('Hogarths edition', "Hogarth's edition"),
        ]:
            with self.subTest(quote=quote, response=response):
                self.assertFalse(supported(quote, response))

    def test_apostrophe_style_preserves_word_spelling(self):
        self.assertTrue(supported("Hogarth's edition", 'Hogarth’s edition'))

    def test_reparse_preserves_raw_claim_and_genuine_mismatch(self):
        raw = dict(C1=dict(label='AFFIRM', quote='ada wrote it'),
                   C2=dict(label='DENY', quote='Ben translated it'),
                   C3=dict(label='AUTHOR', quote='Ada wrote it'))
        result = reparsed(json.dumps(raw), 'Ada wrote it. Ben did not translate it.')
        self.assertEqual(result['C1']['label'], 'AFFIRM')
        self.assertEqual(result['C1']['quote'], raw['C1']['quote'])
        self.assertTrue(result['C1']['quote_format_normalized'])
        self.assertEqual(result['C2']['label'], 'UNJUDGEABLE')
        self.assertTrue(result['C2']['quote_mismatch'])
        self.assertEqual(result['C3'], raw['C3'])


if __name__ == '__main__':
    unittest.main()
