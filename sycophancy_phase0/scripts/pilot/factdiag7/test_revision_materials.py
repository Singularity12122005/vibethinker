"""第57/58项新增材料与第五批原范围的针对性纯构造测试。"""
from copy import deepcopy
from pathlib import Path
import json
import unittest

from .revision_materials import (build_materials, build_revision_materials, fifth_scope_summary,
                                 validate_identity, validate_catalogue)


def public_materials():
    root = Path(__file__).resolve().parents[4] / 'docs/research/early-stage'
    load = lambda p: json.loads(p.read_text(encoding='utf-8'))
    return (load(root / 'factdiag7/factdiag7_stage2_materials.json'),
            load(root / 'factdiag5/factdiag5_materials.json'))


class RevisionMaterialTests(unittest.TestCase):
    def test_real_coverage_and_old_fields_remain_unchanged(self):
        original, fifth = public_materials()
        before = deepcopy(original)
        updated = build_materials(original, fifth)
        with self.assertRaises(ValueError):
            build_materials(original)
        self.assertEqual(original, before)
        for key in original.keys() - {'items'}:
            self.assertEqual(original[key], updated[key])
        for old, new in zip(original['items'], updated['items']):
            for key in old.keys() - {'people'}:
                self.assertEqual(old[key], new[key])
            for person, revised in zip(old['people'], new['people']):
                for key in person:
                    self.assertEqual(person[key], revised[key])
        totals = updated['revision_materials_coverage']['totals']
        self.assertEqual(totals['direct_identity_sources'], 10)
        self.assertEqual(totals['front_matter_verified'], 8)
        self.assertEqual(totals['other_translations_verified'], 8)
        self.assertEqual(totals['other_translations_unverified'], 2)
        self.assertEqual(totals['identity_exclusions'], 0)
        self.assertEqual(totals['X_complete_catalogues'], 0)
        self.assertEqual(totals['X_absence_refutations'], 0)

    def test_missing_other_signature_not_replaced_by_other_edition_id(self):
        original, fifth = public_materials()
        result = build_revision_materials(original, fifth)
        for item in result['items']:
            if item['work_id'] in ('R-006', 'R-009'):
                self.assertFalse(item['other_translation_records'][0]['verified'])
                self.assertTrue(item['other_translation_records'][0]['scope_keys'])

    def test_distinct_name_and_complete_credit_list_do_not_prove_identity_exclusion(self):
        original, fifth = public_materials()
        result = build_revision_materials(original, fifth)
        item = result['items'][0]
        record = item['translation_identity_records'][0]
        self.assertFalse(record['exclusivity_verified'])
        bad = dict(record, exclusivity_verified=True, exclusive_identity_basis='不同名字且未列在目录')
        with self.assertRaises(ValueError):
            validate_identity(bad, item)
        direct = dict(record, exclusivity_verified=True, exclusive_identity_basis='合成例：明确排除另一文本身份的直接版次说明',
                      exclusivity_evidence_kind='DIRECT_TEXT_IDENTITY_EXCLUSION')
        self.assertTrue(validate_identity(direct, item)['exclusivity_verified'])
        with self.assertRaises(ValueError):
            validate_identity(dict(direct, scope_key='ebook:999999'), item)

    def test_catalogue_requires_completeness_scope_activity_and_absence(self):
        original, fifth = public_materials()
        item = build_revision_materials(original, fifth)['items'][0]
        person = next(p for p in item['people'] if p['type'] == 'X')
        record = person['translation_catalogue_coverage'][0]
        self.assertFalse(record['complete'])
        self.assertFalse(record['excluded_work_verified'])
        with self.assertRaises(ValueError):
            validate_catalogue(dict(record, complete=True), item, person)
        with self.assertRaises(ValueError):
            validate_catalogue(dict(record, excluded_work_verified=True), item, person)
        good = dict(record, complete=True, completeness_basis='合成完整书目说明',
            activity_coverage_verified=True, coverage_scope_keys=['work:'+item['work_id']],
            excluded_work_verified=True, excluded_work_id=item['work_id'], absence_check_basis='合成逐项核对')
        self.assertTrue(validate_catalogue(good, item, person)['complete'])
        with self.assertRaises(ValueError):
            validate_catalogue(dict(good, bases=['PARTICIPATED']), item, person)

    def test_fifth_scope_and_user_message_are_not_expanded_or_rebuilt(self):
        _, fifth = public_materials()
        report = fifth_scope_summary(fifth, deepcopy(fifth['plan']['requests']))
        self.assertEqual(report['total'], 1840)
        self.assertEqual(report['fixed_prefix_rows'], 720)
        self.assertEqual(report['system_record_rows'], 0)
        self.assertTrue(report['actual_rows_checked'])
        changed = deepcopy(fifth['plan']['requests'])
        row = next(r for r in changed if r['cell'] == '5.5')
        row['user_text'] = 'Synthetic changed context'
        with self.assertRaises(ValueError):
            fifth_scope_summary(fifth, changed)
        altered = deepcopy(fifth)
        altered['plan']['requests'] = [r for r in altered['plan']['requests'] if r['cell'] != 'E-false']
        with self.assertRaises(ValueError):
            fifth_scope_summary(altered)


if __name__ == '__main__':
    unittest.main()
