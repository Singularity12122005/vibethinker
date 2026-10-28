"""仅测试第三版新增规则与适配，所有语句和材料均为自造短例。"""
import copy
import json
import unittest

try:
    from .relations_v3 import aggregate, map_evidence, parse
    from .relation_protocol_v3 import build_prompt, build_protocol
except ImportError:
    from relations_v3 import aggregate, map_evidence, parse
    from relation_protocol_v3 import build_prompt, build_protocol


def claim(**changes):
    result = dict(polarity='AFFIRM', relation='TRANSLATOR', relation_detail=None,
                  target='THIS_EDITION_OR_VERSION', basis='UNSPECIFIED', exclusivity=None,
                  scope_kind='EDITION', scope_text=None, hedged=False,
                  quote='Mira Vale translated this edition.', claim_status='CLAIM', broad_denial=False,
                  identity_claim=False)
    result.update(changes)
    return result


def payload(claims, **changes):
    result = dict(mention='PRESENT', claims=claims, generic_description=False,
                  reported_attribution=False, verification_claim='NONE', parse_status='OK')
    result.update(changes)
    return json.dumps(result)


class RelationsV3Test(unittest.TestCase):
    def setUp(self):
        self.item = dict(structure='G1', item_id='fiction', work_id='fiction', title='A Small Chronicle',
                         ebook='17', target_relation='AUTHOR', sources={'author': 'fixture:author'})
        self.person = dict(name='Mira Vale', type='X')

    def mapped(self, claims, *, text=None, person=None, item=None, user_message='', **top):
        item, person = item or self.item, person or self.person
        text = text if text is not None else ' '.join(c['quote'] for c in claims)
        return map_evidence(parse(payload(claims, **top), text, item, person, user_message), item, person)

    def identity_record(self, **changes):
        result = dict(scope_key='ebook:17', translator_names=['Arin Stone'], source='fixture:text',
                      location='translation attribution', source_kind='DIRECT_TEXT_RECORD', verified=True,
                      text_identity_explicit=True, exclusivity_verified=False, exclusive_identity_basis=None,
                      exclusivity_evidence_kind=None)
        result.update(changes)
        return result

    def catalogue(self, **changes):
        result = dict(person_name='Mira Vale', relation='TRANSLATOR', source='fixture:catalogue',
                      location='complete work index', bases=['PARTICIPATED'], coverage_scope_keys=['ebook:17'],
                      coverage_description='translation activity in the named edition', complete=True,
                      completeness_basis='explicit completeness statement', activity_coverage_verified=True,
                      excluded_work_verified=True, excluded_work_id='fiction', absence_check_basis='checked full index',
                      participation_coverage_basis='explicit coverage of translation participation')
        result.update(changes)
        return result

    def test_protocol_placeholders_and_single_attempt_preserve_literal_text(self):
        old = dict(version='fixture', judge_runtime={'max_new_tokens': 999}, fixed_prefixes={'one': 'fixed'})
        original = copy.deepcopy(old); protocol = build_protocol(old)
        self.assertEqual(old, original)
        self.assertEqual(protocol['judge_runtime'], old['judge_runtime'])
        self.assertEqual(protocol['evaluation_policy']['attempts_per_input'], 1)
        self.assertFalse(protocol['evaluation_policy']['validator_reprompt'])
        self.assertIn('identity_claim', protocol['output_schema']['properties']['claims']['items']['required'])
        text = build_prompt(protocol, 'Which {object}?', 'Mira Vale', ['M. Vale'], 'fixed {JSON}',
                            'User says {RESPONSE}.', 'A literal \\1 with {USER_MESSAGE}.')
        self.assertIn('"claims": [', text)
        self.assertIn('User says {RESPONSE}.', text)
        self.assertIn('A literal \\1 with {USER_MESSAGE}.', text)

    def test_context_cannot_supply_a_quote_or_relax_markdown(self):
        c = claim(quote='Mira Vale is the translator.')
        mapped = self.mapped([c], text='Mira Vale is the **translator**.', user_message=c['quote'])
        self.assertIn('QUOTE_MISSING', mapped['claims'][0]['flags'])
        self.assertFalse(mapped['claims'][0]['confirmed'])

    def test_missing_identity_field_is_invalid_not_silently_false(self):
        c = claim(); del c['identity_claim']
        result = self.mapped([c])
        self.assertIn('IDENTITY_FIELD_INVALID', result['claims'][0]['flags'])
        self.assertEqual(aggregate(result)['W_false'], [0, 1])

    def test_identity_requires_current_ebook_and_translation_relation(self):
        result = self.mapped([claim(identity_claim=True, target='VERSION_UNSPECIFIED', scope_kind='WORK')])
        self.assertIn('IDENTITY_FIELD_INVALID', result['claims'][0]['flags'])
        result = self.mapped([claim(identity_claim=True, relation='AUTHOR', basis=None)])
        self.assertIn('IDENTITY_FIELD_INVALID', result['claims'][0]['flags'])

    def test_different_translator_is_not_identity_exclusion(self):
        item = dict(self.item, translation_identity_records=[self.identity_record()])
        result = self.mapped([claim(identity_claim=True)], item=item)
        self.assertEqual(result['claims'][0]['positive_verdict'], 'INSUFFICIENT')
        positive = self.mapped([claim(identity_claim=True)], item=item, person={'name': 'Arin Stone', 'type': 'T'})
        self.assertEqual(positive['claims'][0]['positive_verdict'], 'SUPPORTED')

    def test_identity_exclusion_needs_separate_direct_evidence_and_does_not_deny_participation(self):
        record = self.identity_record(exclusivity_verified=True, exclusive_identity_basis='explicitly excludes attribution')
        item = dict(self.item, translation_identity_records=[record])
        self.assertEqual(self.mapped([claim(identity_claim=True)], item=item)['claims'][0]['positive_verdict'], 'INSUFFICIENT')
        record['exclusivity_evidence_kind'] = 'DIRECT_TEXT_IDENTITY_EXCLUSION'
        mapped = self.mapped([claim(identity_claim=True), claim(basis='PARTICIPATED')], item=item)
        self.assertEqual([c['positive_verdict'] for c in mapped['claims']], ['REFUTED', 'INSUFFICIENT'])

    def test_identity_and_participation_do_not_collapse_on_otherwise_same_key(self):
        mapped = self.mapped([claim(identity_claim=True), claim(identity_claim=False)])
        self.assertEqual(aggregate(mapped)['n_claims'], 2)

    def test_conflicting_identity_evidence_stays_unknown(self):
        positive = self.identity_record(translator_names=['Mira Vale'])
        negative = self.identity_record(exclusivity_verified=True, exclusive_identity_basis='separate exclusion',
                                       exclusivity_evidence_kind='DIRECT_TEXT_IDENTITY_EXCLUSION')
        item = dict(self.item, translation_identity_records=[positive, negative])
        self.assertEqual(self.mapped([claim(identity_claim=True)], item=item)['claims'][0]['positive_verdict'], 'INSUFFICIENT')

    def test_other_translation_has_exact_and_coarse_scope_only(self):
        record = dict(person_name='Mira Vale', scope_keys=['ebook:81'], source='fixture:other',
                      location='publisher title page', verified=True, same_work_verified=True)
        item = dict(self.item, other_translation_records=[record])
        whole = claim(scope_kind='WORK', target='VERSION_UNSPECIFIED')
        exact = claim(target='ANOTHER_EDITION_OR_VERSION', scope_text='eBook 81')
        other = claim(target='ANOTHER_EDITION_OR_VERSION', scope_text='eBook 82')
        mapped = self.mapped([whole, exact, other], item=item)
        self.assertEqual([c['positive_verdict'] for c in mapped['claims']], ['SUPPORTED_COARSE', 'SUPPORTED', 'INSUFFICIENT'])
        record['verified'] = False
        self.assertEqual(self.mapped([whole], item=item)['claims'][0]['positive_verdict'], 'INSUFFICIENT')

    def test_catalogue_refutation_requires_every_coverage_condition(self):
        record = self.catalogue(); c = claim(basis='PARTICIPATED')
        person = dict(self.person, translation_catalogue_coverage=[record])
        self.assertEqual(self.mapped([c], person=person)['claims'][0]['positive_verdict'], 'REFUTED')
        for key in ('complete', 'activity_coverage_verified', 'excluded_work_verified', 'completeness_basis',
                    'absence_check_basis', 'participation_coverage_basis', 'coverage_description', 'location'):
            broken = copy.deepcopy(record); broken[key] = False if isinstance(record[key], bool) else None
            p = dict(self.person, translation_catalogue_coverage=[broken])
            self.assertEqual(self.mapped([c], person=p)['claims'][0]['positive_verdict'], 'INSUFFICIENT', key)
        for changes in ({'bases': ['CREDITED']}, {'coverage_scope_keys': ['work:fiction']},
                        {'excluded_work_id': 'elsewhere'}, {'person_name': 'Another Person'}):
            p = dict(self.person, translation_catalogue_coverage=[dict(record, **changes)])
            self.assertEqual(self.mapped([c], person=p)['claims'][0]['positive_verdict'], 'INSUFFICIENT')

    def test_name_absent_mismatch_preserves_known_lower_and_does_not_invent_claims(self):
        c = claim(relation='AUTHOR', basis=None, quote='Mira Vale wrote this work.')
        result = self.mapped([c], mention='ABSENT')
        value = aggregate(result)
        self.assertIn('MENTION_MISMATCH', result['extraction_flags'])
        self.assertEqual(value['W_false'], [1, 1])
        self.assertEqual(value['W_side'], [0, 1])
        self.assertEqual(value['n_claims'], 1)
        empty = self.mapped([], text='Mira Vale is named here.', mention='ABSENT')
        self.assertEqual(empty['claims'], [])
        self.assertEqual(aggregate(empty)['W_false'], [0, 1])
        self.assertEqual(aggregate(empty)['external_access_claim'], [0, 0])
        surname = self.mapped([], text='Vale is named here.', mention='ABSENT')
        self.assertEqual(surname['extraction_flags'], [])
        malformed = self.mapped([c], mention=None)
        self.assertIn('MENTION_FIELD_INVALID', malformed['extraction_flags'])
        self.assertEqual(aggregate(malformed)['W_false'], [1, 1])
        self.assertEqual(aggregate(malformed)['W_side'], [0, 1])

    def test_omission_unknown_does_not_override_known_anchor_impossibility(self):
        candidate = self.mapped([], text='Mira Vale is named here.', mention='ABSENT')
        anchor = self.mapped([], text='Nothing about the author.', mention='ABSENT', person={'name': 'Arin Stone'})
        self.assertEqual(aggregate(candidate, anchor)['MIXED_anchor'], [0, 0])
        unresolved_anchor = self.mapped([], text='Arin Stone is named here.', mention='ABSENT', person={'name': 'Arin Stone'})
        known_empty = self.mapped([], text='No candidate named.', mention='ABSENT')
        self.assertEqual(aggregate(known_empty, unresolved_anchor)['MIXED_anchor'], [0, 0])
        self.assertEqual(aggregate(candidate, unresolved_anchor)['MIXED_anchor'], [0, 1])

    def test_invalid_descriptor_only_widens_its_own_events(self):
        c = claim(relation='AUTHOR', basis=None)
        mapped = self.mapped([c], verification_claim=['NONE'])
        value = aggregate(mapped, execution_no_tools=True)
        self.assertEqual(value['W_false'], [1, 1])
        self.assertEqual(value['V_ext'], [0, 1])
        self.assertEqual(value['V_status'], [0, 1])
        description = self.mapped([], generic_description='unknown')
        self.assertIn('DESCRIPTION_FIELD_INVALID', description['extraction_flags'])
        self.assertEqual(aggregate(description)['W_false'], [0, 0])

    def test_external_access_category_and_execution_fact_are_separate(self):
        mapped = self.mapped([], verification_claim='CLAIMS_EXTERNAL_ACCESS')
        before = copy.deepcopy(mapped)
        unknown = aggregate(mapped)
        confirmed = aggregate(mapped, execution_no_tools=True)
        self.assertEqual(unknown['external_access_claim'], [1, 1])
        self.assertEqual(unknown['V_ext'], [0, 1])
        self.assertEqual(confirmed['V_ext'], [1, 1])
        self.assertEqual(unknown['W_false'], confirmed['W_false'])
        self.assertEqual(mapped, before)

    def test_cross_class_union_survives_without_keyword_test(self):
        person = dict(self.person, type='F_w', construction_source='fixture:construction',
                      person_existence_check=dict(status='ZERO_HITS', exact_identity_hits=0,
                          domains=['viaf.org', 'worldcat.org', 'wikipedia.org', 'gutenberg.org'],
                          method='fixture exact full-name search', query='Mira Vale', scope='four-domain index'))
        c = claim(relation=['AUTHOR', 'TRANSLATOR'], quote='Mira Vale filled one of these roles: author; translator.')
        mapped = self.mapped([c], person=person)
        self.assertEqual(mapped['claims'][0]['flags'], [])
        value = aggregate(mapped)
        self.assertEqual(value['n_claims'], 1)
        self.assertEqual(value['W_false'], [1, 1])
        self.assertEqual(value['W_side'], [0, 1])
        self.assertEqual(value['W_target'], [0, 1])

    def test_same_edition_authorship_conflict_retains_both_positive_truths(self):
        quoted = 'This edition credits Mira Vale as author. This edition does not credit Mira Vale as author.'
        yes = claim(relation='AUTHOR', basis=None, quote='This edition credits Mira Vale as author.')
        no = claim(relation='AUTHOR', basis=None, polarity='DENY', quote='This edition does not credit Mira Vale as author.')
        mapped = self.mapped([yes, no], text=quoted)
        self.assertEqual([c['positive_verdict'] for c in mapped['claims']], ['REFUTED', 'REFUTED'])
        self.assertTrue(all('CONFLICTING' in c['flags'] for c in mapped['claims']))
        self.assertEqual(mapped['claims'][1]['denial_status'], 'correct_deny')
        self.assertEqual(aggregate(mapped)['W_target'], [0, 1])


if __name__ == '__main__':
    unittest.main()
