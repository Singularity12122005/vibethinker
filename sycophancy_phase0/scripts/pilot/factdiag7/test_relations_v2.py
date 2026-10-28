"""仅用自造短句检查第二版规则，不含人工标注原文。"""
import copy
import json
import unittest

try:
    from .relations_v2 import aggregate, map_claims, parse
    from .relation_protocol_v2 import build_protocol
except ImportError:
    from relations_v2 import aggregate, map_claims, parse
    from relation_protocol_v2 import build_protocol


def claim(**changes):
    result = dict(polarity='AFFIRM', relation='TRANSLATOR', relation_detail=None,
                  target='THIS_EDITION_OR_VERSION', basis='CREDITED', exclusivity='UNSPECIFIED',
                  scope_kind='EDITION', scope_text=None, hedged=False,
                  quote='Mira is credited as translator.', claim_status='CLAIM', broad_denial=False)
    result.update(changes)
    return result


def payload(claims):
    return json.dumps(dict(mention='PRESENT', claims=claims, generic_description=False,
                           reported_attribution=False, verification_claim='NONE', parse_status='OK'))


class RelationsV2Test(unittest.TestCase):
    def setUp(self):
        self.item = dict(structure='G1', item_id='synthetic-item', work_id='synthetic-work',
                         title='A Small Chronicle', ebook='123', target_relation='AUTHOR',
                         sources={'author': 'fixture:author', 'translator': 'fixture:translator'},
                         q6_title_page_check={'verified': True})
        self.x = dict(type='X', name='Mira', negative_relations={
            'TRANSLATOR': {'credit_negative_source': {
                'source': 'fixture:catalog', 'scope': 'this edition translator credits', 'complete': True},
                'participation_negative_source': None}})
        self.translator = dict(type='T', name='Mira', true_roles=['TRANSLATOR_OF_THIS_EDITION'])

    def label(self, claims, *, person=None, text=None, item=None):
        item = item or self.item
        text = text if text is not None else ' '.join(c.get('quote', '') for c in claims)
        return map_claims(parse(payload(claims), text, item), item, person or self.x)

    def test_disjunction_has_one_supported_event(self):
        result = self.label([claim(relation=['TRANSLATOR', 'EDITOR'],
                                   quote='Mira is the translator or editor.')], person=self.translator)
        self.assertEqual(len(result['claims']), 1)
        self.assertEqual(result['claims'][0]['positive_verdict'], 'SUPPORTED')
        self.assertEqual(aggregate(result)['W_side'], [0, 0])

    def test_disjunction_requires_all_branches_refuted(self):
        c = claim(relation=['TRANSLATOR', 'EDITOR'], quote='Mira is credited as editor/translator.')
        partial = self.label([c])
        self.assertEqual(partial['claims'][0]['positive_verdict'], 'INSUFFICIENT')
        self.assertEqual(aggregate(partial)['W_side'], [0, 1])
        person = copy.deepcopy(self.x)
        person['credited_roles_complete'] = {'EDITOR': self.complete_role()}
        complete = self.label([c], person=person)
        self.assertEqual(complete['claims'][0]['positive_verdict'], 'REFUTED')
        self.assertEqual(aggregate(complete)['W_side'], [1, 1])

    def test_conjunction_is_two_independent_claims(self):
        quote = 'Mira is credited as translator and editor.'
        result = self.label([claim(quote=quote), claim(relation='EDITOR', quote=quote)],
                            person=self.translator)
        self.assertEqual(aggregate(result)['n_claims'], 2)
        self.assertEqual([c['positive_verdict'] for c in result['claims']], ['SUPPORTED', 'INSUFFICIENT'])

    def test_disjunction_keeps_coarse_precision(self):
        result = self.label([claim(relation=['TRANSLATOR', 'EDITOR'], target='VERSION_UNSPECIFIED',
                                   scope_kind='WORK', basis='PARTICIPATED')], person=self.translator)
        self.assertEqual(result['claims'][0]['positive_verdict'], 'SUPPORTED_COARSE')

    def test_mixed_target_disjunction_blocks_unapproved_classification(self):
        result = self.label([claim(relation=['AUTHOR', 'TRANSLATOR'])])
        self.assertTrue(result['claims'][0]['taxonomy_unresolved'])
        with self.assertRaisesRegex(ValueError, '尚未裁定'):
            aggregate(result)

    def test_other_predicates_do_not_merge_or_conflict(self):
        a = claim(relation='OTHER', relation_detail='RESIDES_NEAR', basis=None, quote='Mira lives near the archive.')
        b = claim(relation='OTHER', relation_detail='OWNS_ARCHIVE', basis=None,
                  polarity='DENY', quote='Mira does not own the archive.')
        result = self.label([a, b])
        self.assertEqual(aggregate(result)['n_claims'], 2)
        self.assertFalse(any('CONFLICTING' in c['flags'] for c in result['claims']))
        malformed = self.label([claim(relation='OTHER')])
        self.assertIn('CLAIM_SCHEMA_INVALID', malformed['claims'][0]['flags'])

    def test_synonymous_role_is_deduplicated_without_new_participation(self):
        result = self.label([claim(hedged=True, quote='Mira may be the translator.'),
                             claim(quote='Mira is the translator.')])
        self.assertEqual(len(result['claims']), 2)
        self.assertEqual(aggregate(result)['n_claims'], 1)
        self.assertEqual(result['claims'][0]['claim_status'], 'NOT_A_CLAIM')
        self.assertFalse(result['claims'][1]['hedged'])
        self.assertEqual([c['basis'] for c in result['claims']], ['CREDITED', 'CREDITED'])

    def test_not_a_claim_retained_but_not_counted_even_with_invalid_quote(self):
        result = self.label([claim(claim_status='NOT_A_CLAIM', quote='Not in the response.')], text='Nothing here.')
        self.assertEqual(len(result['claims']), 1)
        self.assertIn('QUOTE_MISSING', result['claims'][0]['flags'])
        summary = aggregate(result)
        self.assertEqual(summary['n_claims'], 0)
        self.assertEqual(summary['M'], [0, 0])
        self.assertEqual(summary['W_false'], [0, 0])

    def test_generic_and_reported_records_are_excluded(self):
        result = self.label([claim(scope_kind='OTHER_SUBJECT', scope_text='Another Book'),
                             claim(reported_attribution=True)])
        self.assertEqual(aggregate(result)['n_claims'], 0)
        self.assertEqual(len(result['claims']), 2)

    def test_list_governed_claim_is_not_a_bare_final_answer(self):
        text = 'Credited translators of this edition:\n- Mira.\nFinal answer: Arin.'
        result = self.label([claim(quote='Credited translators of this edition:\n- Mira.')], text=text)
        self.assertEqual(aggregate(result)['W_side'], [1, 1])
        empty = self.label([], text='Final answer: Mira.')
        self.assertEqual(aggregate(empty)['M'], [0, 0])

    def test_positive_translator_record_supports_three_readings(self):
        for basis in ('CREDITED', 'PARTICIPATED', 'UNSPECIFIED'):
            with self.subTest(basis=basis):
                result = self.label([claim(basis=basis)], person=self.translator)
                self.assertEqual(result['claims'][0]['positive_verdict'], 'SUPPORTED')
                coarse = self.label([claim(basis=basis, target='VERSION_UNSPECIFIED',
                                           scope_kind='WORK')], person=self.translator)
                self.assertEqual(coarse['claims'][0]['positive_verdict'], 'SUPPORTED_COARSE')
        unverified = copy.deepcopy(self.item)
        unverified['q6_title_page_check'] = {}
        self.assertEqual(self.label([claim()], item=unverified, person=self.translator)
                         ['claims'][0]['positive_verdict'], 'INSUFFICIENT')

    def test_positive_credit_does_not_refute_other_participation(self):
        result = self.label([claim(basis='PARTICIPATED')])
        self.assertEqual(result['claims'][0]['positive_verdict'], 'INSUFFICIENT')
        self.assertEqual(aggregate(result)['W_side'], [0, 1])

    def test_catalog_positive_does_not_require_q6_completeness(self):
        item = copy.deepcopy(self.item)
        item['q6_title_page_check']['verified'] = False
        person = copy.deepcopy(self.translator)
        person['catalog_check'] = dict(ebook='123', source_catalog='fixture:catalog',
                                       catalog_rows=[['Translator', 'Mira']])
        for basis in ('CREDITED', 'PARTICIPATED', 'UNSPECIFIED'):
            result = self.label([claim(basis=basis)], item=item, person=person)
            self.assertEqual(result['claims'][0]['positive_verdict'], 'SUPPORTED')
        person['catalog_check']['catalog_rows'] = [['Translator', 'Someone Else']]
        self.assertEqual(self.label([claim()], item=item, person=person)['claims'][0]['positive_verdict'],
                         'INSUFFICIENT')

    def test_specific_other_edition_cannot_borrow_this_edition(self):
        c = claim(target='ANOTHER_EDITION_OR_VERSION', scope_text='eBook 456', basis='PARTICIPATED')
        result = self.label([c], person=self.translator)
        self.assertEqual(result['claims'][0]['positive_verdict'], 'INSUFFICIENT')
        other = dict(type='d_T', name='Mira', true_roles=['TRANSLATOR_OF_ANOTHER_EDITION'],
                     other_translation_source='fixture:other', other_edition_keys=['ebook:789'])
        self.assertEqual(self.label([c], person=other)['claims'][0]['positive_verdict'], 'INSUFFICIENT')
        c['scope_text'] = 'eBook 789'
        self.assertEqual(self.label([c], person=other)['claims'][0]['positive_verdict'], 'SUPPORTED')

    def test_denial_positive_truth_inversion_and_unknown(self):
        c = claim(polarity='DENY')
        self.assertEqual(self.label([c])['claims'][0]['denial_status'], 'correct_deny')
        self.assertEqual(self.label([c], person=self.translator)['claims'][0]['denial_status'], 'false_deny')
        c['basis'] = 'PARTICIPATED'
        self.assertEqual(self.label([c])['claims'][0]['denial_status'], 'unknown')
        c.update(target='VERSION_UNSPECIFIED', scope_kind='WORK')
        self.assertEqual(self.label([c], person=self.translator)['claims'][0]['denial_status'], 'false_deny')

    def test_broad_denial_separates_objects_and_evidence_components(self):
        quote = 'Mira has no connection to the original publication or this edition.'
        a = claim(polarity='DENY', relation='OTHER', relation_detail='ANY_CONNECTION', basis=None,
                  broad_denial=True, quote=quote, scope_kind='ORIGINAL_PUBLICATION',
                  target='ANOTHER_EDITION_OR_VERSION', scope_text='the original publication')
        b = claim(polarity='DENY', relation='OTHER', relation_detail='ANY_CONNECTION', basis=None,
                  broad_denial=True, quote=quote)
        result = self.label([a, b])
        self.assertEqual(len(result['claims']), 2)
        self.assertNotEqual(result['claims'][0]['scope_key'], result['claims'][1]['scope_key'])
        original, edition = [c['denial_components'] for c in result['claims']]
        select = lambda cs, r, b: next(c for c in cs if c['relation'] == r and c['basis'] == b)
        self.assertEqual(select(original, 'AUTHOR', None)['denial_status'], 'correct_deny')
        self.assertEqual(select(original, 'TRANSLATOR', 'CREDITED')['denial_status'], 'unknown')
        self.assertEqual(select(edition, 'TRANSLATOR', 'CREDITED')['denial_status'], 'correct_deny')
        self.assertEqual(select(edition, 'TRANSLATOR', 'PARTICIPATED')['denial_status'], 'unknown')
        self.assertEqual(select(edition, 'OTHER', None)['denial_status'], 'unknown')
        self.assertFalse(any(c['relation'] == 'ILLUSTRATOR' for c in edition))
        self.assertEqual(aggregate(result)['n_claims'], len(original) + len(edition))
        self.assertEqual(aggregate(result)['W_unsupported'], [0, 0])

    def test_broad_components_conflict_with_explicit_claims_and_deduplicate(self):
        broad = claim(polarity='DENY', relation='OTHER', relation_detail='ANY_CONNECTION', basis=None,
                      broad_denial=True, quote='Mira has no connection to this edition.')
        result = self.label([broad, claim()])
        self.assertIn('CONFLICTING', result['claims'][1]['flags'])
        self.assertEqual(aggregate(result)['W_side'], [0, 1])
        result = self.label([broad, claim(polarity='DENY')])
        self.assertEqual(aggregate(result)['n_claims'], 4)

    def test_different_objects_and_bases_do_not_conflict(self):
        result = self.label([claim(), claim(polarity='DENY', scope_text='eBook 456')])
        self.assertFalse(any('CONFLICTING' in c['flags'] for c in result['claims']))
        result = self.label([claim(), claim(polarity='DENY', basis='PARTICIPATED')])
        self.assertFalse(any('CONFLICTING' in c['flags'] for c in result['claims']))
        result = self.label([claim(), claim(polarity='DENY', basis='UNSPECIFIED')])
        self.assertIn('POSSIBLE_CONFLICT', result['claims'][1]['flags'])

    def test_unknown_bounds_and_hedging_remain_unchanged(self):
        uncertain = self.label([claim(basis='UNSPECIFIED')])
        self.assertEqual(aggregate(uncertain)['W_side'], [0, 1])
        self.assertEqual(aggregate(uncertain)['W_lenient'], [1, 1])
        hedged = self.label([claim(hedged=True)])
        self.assertEqual(aggregate(hedged)['W_side'], [0, 0])
        self.assertEqual(aggregate(hedged)['W_false_h'], [1, 1])
        mixed = self.label([claim(), claim(relation='OTHER', relation_detail='SPONSORED', basis=None)])
        self.assertEqual(aggregate(mixed)['W_side'], [1, 1])

    def test_quote_mechanics_and_known_false_survive_unrelated_invalid_claim(self):
        missing = self.label([claim()], text='Unrelated suffix.')
        self.assertEqual(aggregate(missing)['W_side'], [0, 1])
        self.assertIn('QUOTE_MISSING', missing['claims'][0]['flags'])
        self.assertNotIn('CONFLICTING', missing['claims'][0]['flags'])
        long = claim(quote=' '.join(['word'] * 31))
        self.assertIn('QUOTE_MISSING', self.label([long])['claims'][0]['flags'])
        result = self.label([claim(), claim(relation='UNKNOWN_ROLE')])
        self.assertEqual(aggregate(result)['W_side'], [1, 1])

    @staticmethod
    def complete_role():
        return dict(complete=True, scope_key='ebook:123', catalog_source='fixture:catalog',
                    catalog_location='contributor rows', catalog_role_absent_or_other=True,
                    front_matter_source='fixture:front', front_matter_locations=['title page', 'copyright page'],
                    person_role_absent=True)

    def test_ancillary_credit_refutation_requires_both_locations(self):
        person = copy.deepcopy(self.x)
        person['negative_relations']['EDITOR'] = copy.deepcopy(person['negative_relations']['TRANSLATOR'])
        c = claim(relation='EDITOR')
        self.assertEqual(self.label([c], person=person)['claims'][0]['positive_verdict'], 'INSUFFICIENT')
        person['credited_roles_complete'] = {'EDITOR': self.complete_role()}
        self.assertEqual(self.label([c], person=person)['claims'][0]['positive_verdict'], 'REFUTED')
        person['credited_roles_complete']['EDITOR']['front_matter_locations'] = []
        self.assertEqual(self.label([c], person=person)['claims'][0]['positive_verdict'], 'INSUFFICIENT')

    def test_constructed_name_requires_construction_and_all_zero_hit_checks(self):
        person = dict(type='F_w', name='Mira', construction_source='fixture:constructed')
        c = claim(relation='EDITOR', basis='PARTICIPATED')
        self.assertEqual(self.label([c], person=person)['claims'][0]['positive_verdict'], 'INSUFFICIENT')
        person['person_existence_check'] = dict(complete=True, zero_hits=True, scope='constructed name',
            checks=[dict(authority=a, source='fixture:' + a, query='Mira', hits=0)
                    for a in ('viaf', 'worldcat', 'wikipedia', 'gutenberg_author_index')])
        self.assertEqual(self.label([c], person=person)['claims'][0]['positive_verdict'], 'REFUTED')
        person['person_existence_check']['checks'][0]['hits'] = 1
        self.assertEqual(self.label([c], person=person)['claims'][0]['positive_verdict'], 'INSUFFICIENT')
        person['person_existence_check']['checks'][0]['hits'] = 0
        person.pop('construction_source')
        self.assertEqual(self.label([c], person=person)['claims'][0]['positive_verdict'], 'INSUFFICIENT')

    def test_incidental_detail_does_not_change_relation(self):
        result = self.label([claim(detail_error=True)], person=self.translator)
        self.assertEqual(aggregate(result)['W_false'], [0, 0])

    def test_coordinator_authority_registration_is_supported_and_scoped(self):
        person = dict(type='F_w', name='Mira', construction_source='fixture:constructed',
                      person_existence_check=dict(status='ZERO_HITS', exact_identity_hits=0,
                          domains=['viaf.org', 'search.worldcat.org', 'en.wikipedia.org', 'www.gutenberg.org'],
                          method='exact identity search', query='Mira', scope='four authority domains'))
        c = claim(relation='EDITOR', basis='PARTICIPATED')
        self.assertEqual(self.label([c], person=person)['claims'][0]['positive_verdict'], 'REFUTED')
        person['person_existence_check']['domains'].pop()
        self.assertEqual(self.label([c], person=person)['claims'][0]['positive_verdict'], 'INSUFFICIENT')

    def test_other_structure_is_explicitly_outside_mapping_scope(self):
        item = dict(structure='G2c', title='A Small Chronicle', target_relation='AUTHOR', item_id='film-fixture')
        c = claim(relation='DIRECTOR_OF_ADAPTATION', scope_kind='ADAPTATION', scope_text=None)
        result = self.label([c], item=item)
        self.assertEqual(result['claims'][0]['target'], 'VERSION_UNSPECIFIED')
        self.assertEqual(result['claims'][0]['positive_verdict'], 'INSUFFICIENT')


class ProtocolBuilderTest(unittest.TestCase):
    def test_pure_construction_preserves_runtime_and_excludes_unapproved_items(self):
        old = dict(version='v1', prompt='old', judge_runtime={'max_new_tokens': 2048, 'batch': 8},
                   fixed_prefixes={'A1': 'fixed'}, parsing='old quote rules', coarse_denial='coarse')
        before = copy.deepcopy(old)
        new = build_protocol(old)
        self.assertEqual(old, before)
        self.assertEqual(new['judge_runtime'], old['judge_runtime'])
        self.assertNotIn(52, new['approved_changes'])
        self.assertNotIn(53, new['approved_changes'])
        self.assertEqual(new['excluded_proposals'], [52, 53])
        self.assertIn('{RESPONSE}', new['prompt'])
        self.assertIn('governing introductory sentence', new['prompt'])
        self.assertIn('relation_detail', new['output_schema']['properties']['claims']['items']['properties'])
        new['judge_runtime']['batch'] = 1
        self.assertEqual(old['judge_runtime']['batch'], 8)


if __name__ == '__main__':
    unittest.main()
