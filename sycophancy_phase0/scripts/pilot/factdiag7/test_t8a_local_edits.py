import unittest

from .t8a_local_edits import edit, MARKER, verification_quotes


class LocalEditTest(unittest.TestCase):
    def test_cross_sentence_minimum_cover_and_final_protection(self):
        text = 'A correct reason. A false sentence! Another false sentence? Safe ending.\nFinal answer: A\n'
        revised, log, _ = edit(text, ['false sentence! Another false'], 'DELETE')
        self.assertEqual(revised, 'A correct reason. Safe ending.\nFinal answer: A\n')
        self.assertEqual(log['deleted_sentence_count'], 2)
        self.assertTrue(log['endline_unchanged'])

    def test_only_marker_added_and_shared_sentence_once(self):
        text = 'An uncertain claim and another uncertain claim.\n\nFinal answer: A\n'
        revised, log, _ = edit(text, ['An uncertain', 'another uncertain'], 'ANNOTATE')
        self.assertEqual(revised, 'An uncertain claim and another uncertain claim.' + MARKER + '\n\nFinal answer: A\n')
        self.assertEqual(log['affected_sentence_count'], 1)

    def test_ambiguous_quote_is_not_guessed(self):
        text = 'Same claim. Same claim.\nFinal answer: A'
        revised, log, _ = edit(text, ['Same claim'], 'DELETE')
        self.assertEqual(revised, text)
        self.assertEqual(log['issues'][0]['reason'], 'ambiguous_quote')

    def test_missing_and_final_conflicts_preserved(self):
        text = 'Safe reason.\n**Final answer: A**\n'
        revised, log, _ = edit(text, ['Missing quote', 'Final answer: A'], 'DELETE')
        self.assertEqual(revised, text)
        self.assertEqual([i['reason'] for i in log['issues']], ['quote_not_found', 'endline_conflict'])

    def test_verification_only_from_explicit_human_quote(self):
        row = {'核对说明': "verification_claim=CLAIMS_EXTERNAL_ACCESS\n说明：V_ext：'I re-checked Gutenberg's entry' → CLAIMS_EXTERNAL_ACCESS（P6）。"}
        quotes, marked = verification_quotes(row)
        self.assertEqual(quotes, ["I re-checked Gutenberg's entry"])
        self.assertTrue(marked)
        text = "I re-checked Gutenberg's entry and conclude A. Another reason.\nFinal answer: A"
        revised, log, _ = edit(text, [], 'DELETE', quotes, marked)
        self.assertEqual(revised, ' Another reason.\nFinal answer: A')
        self.assertEqual(log['deleted_sentence_count'], 1)

    def test_unlocated_verification_cannot_be_silently_completed(self):
        revised, log, _ = edit('A.\nFinal answer: A', [], 'DELETE', [], True)
        self.assertEqual(log['issues'][0]['reason'], 'no_exact_human_quote')

    def test_registered_ellipsis_unique_fragments_with_whitespace(self):
        text = 'I checked  the entry with relevant details and confirmed A. Safe reason.\nFinal answer: A'
        revised, log, private = edit(text, [], 'DELETE', ['I checked the entry (…) and confirmed A'], True, allow_ellipsis=True)
        self.assertEqual(revised, ' Safe reason.\nFinal answer: A')
        self.assertEqual(log['deleted_sentence_count'], 1)
        self.assertEqual(private['locations'][0]['method'], 'registered_ellipsis_fragments')

    def test_registered_ellipsis_ambiguity_is_not_guessed(self):
        text = 'I checked A. I checked B. Safe reason.\nFinal answer: A'
        revised, log, _ = edit(text, [], 'DELETE', ['I checked ...'], True, allow_ellipsis=True)
        self.assertEqual(revised, text)
        self.assertEqual(log['issues'][0]['reason'], 'ambiguous_ellipsis_sentence_set')

    def test_registered_ellipsis_no_match_and_case_is_preserved(self):
        text = 'I checked A.\nFinal answer: A'
        revised, log, _ = edit(text, [], 'DELETE', ['i checked … A'], True, allow_ellipsis=True)
        self.assertEqual(revised, text)
        self.assertEqual(log['issues'][0]['reason'], 'ellipsis_fragments_not_found')

    def test_registered_ellipsis_cannot_touch_endline_or_other_claims(self):
        text = 'I checked A.\nFinal answer: A'
        revised, log, _ = edit(text, [], 'DELETE', ['I checked … Final answer: A'], True, allow_ellipsis=True)
        self.assertEqual(revised, text)
        self.assertEqual(log['issues'][0]['reason'], 'endline_conflict')
        revised, log, _ = edit(text, ['I checked … A'], 'DELETE', allow_ellipsis=True)
        self.assertEqual(revised, text)
        self.assertEqual(log['issues'][0]['reason'], 'quote_not_found')


if __name__ == '__main__':
    unittest.main()
