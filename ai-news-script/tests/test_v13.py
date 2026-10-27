"""Fictional completed tasks exercise enum compatibility and evidence boundaries."""
import copy
import unittest
from test_v11 import practical_fixture
from validate_records import validate_bundle
from render_output import render


def completed_demo(domain='daily_life'):
    b=practical_fixture()
    s=b['stories']['stories'][0]
    s['value_brief'].update(domain=domain,application_context='demonstration',
        demonstration_evidence=dict(input_claim_ids=['claim_001'],output_claim_ids=['demo_output'],
                                    scope_limit='Fictional public task example; no real-world time saving measured.'))
    b['fact_cards']['claims'][0]['statement']='Fictional source supplies two recipes as the input.'
    out=copy.deepcopy(b['fact_cards']['claims'][0])
    out.update(claim_id='demo_output',statement='Fictional source shows the completed combined grocery list.')
    b['fact_cards']['claims'].append(out)
    return b


class V13TaskContractTests(unittest.TestCase):
    def test_completed_public_daily_task_can_validate_and_render(self):
        b=completed_demo()
        self.assertEqual(validate_bundle(b,final=True),[])
        self.assertIn('demonstration',render(b)['sources'])

    def test_daily_learning_creation_and_light_work_domains_are_readable(self):
        for domain in ('daily_life','learning','personal_creation','light_work'):
            with self.subTest(domain=domain):
                self.assertEqual(validate_bundle(completed_demo(domain),final=True),[])

    def test_demo_without_completed_output_references_is_rejected(self):
        b=completed_demo();b['stories']['stories'][0]['value_brief']['demonstration_evidence']['output_claim_ids']=[]
        self.assertTrue(validate_bundle(b,final=True))

    def test_missing_or_invented_demo_input_references_are_rejected(self):
        for ids in ([],['absent']):
            b=completed_demo();b['stories']['stories'][0]['value_brief']['demonstration_evidence']['input_claim_ids']=ids
            self.assertTrue(validate_bundle(b,final=True))

    def test_output_seen_only_in_a_search_snippet_is_not_completed_task_evidence(self):
        b=completed_demo();b['sources']['sources'][0]['access'].update(read_level='search_snippet',visible_sections=[])
        self.assertTrue(validate_bundle(b,final=True))

    def test_demo_needs_explicit_scope_instead_of_implying_actual_use(self):
        b=completed_demo();b['stories']['stories'][0]['value_brief']['demonstration_evidence']['scope_limit']=''
        self.assertTrue(validate_bundle(b,final=True))

    def test_feature_announcement_stays_ineligible_even_with_a_high_score(self):
        b=completed_demo();b['stories']['stories'][0]['value_brief']['application_context']='product_demo'
        self.assertTrue(validate_bundle(b,final=True))

    def test_existing_pilot_does_not_acquire_a_demo_label(self):
        b=practical_fixture()
        self.assertEqual(validate_bundle(b,final=True),[])
        self.assertNotIn('demonstration',render(b)['sources'])


if __name__=='__main__':unittest.main()
