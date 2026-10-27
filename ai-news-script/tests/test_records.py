import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from support import fixture
try:
    import normalize_records as n
    import validate_records as v
except ImportError:
    n = v = None


class RecordsTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(n, 'record normalization not implemented')
        self.assertIsNotNone(v, 'record validation not implemented')

    def codes(self, b, final=True):
        return {x['code'] for x in v.validate_bundle(b, final=final)}

    def test_tracking_only_removed_and_version_preserved(self):
        self.assertEqual(n.normalize_url('https://EXAMPLE.invalid/A?utm_source=x&v=2&lang=zh#part'),
                         'https://example.invalid/A?v=2&lang=zh')
        self.assertNotEqual(n.normalize_url('https://example.invalid/A?v=1'),
                            n.normalize_url('https://example.invalid/A?v=2'))

    def test_secret_urls_refused_before_recording(self):
        for url in ['https://me:secret@example.invalid/a', 'https://example.invalid/a?token=secret']:
            with self.assertRaises(ValueError):
                n.normalize_url(url)

    def test_page_update_is_not_event_date(self):
        self.assertEqual(n.date_status({'value':'2026-04-01','precision':'date'},
                                      '2026-10-18T12:00:00Z','2026-10-25T12:00:00Z'), 'outside_window')

    def test_date_boundary_is_ambiguous_and_future_quarantined(self):
        self.assertEqual(n.date_status({'value':'2026-10-18','precision':'date','timezone':None},
                                      '2026-10-18T12:00:00Z','2026-10-25T12:00:00Z'), 'ambiguous')
        self.assertEqual(n.date_status({'value':'2026-11-01','precision':'date'},
                                      '2026-10-18T12:00:00Z','2026-10-25T12:00:00Z'), 'future_unverified')

    def test_metric_percentage_points_not_speed(self):
        m=dict(baseline={'value':50,'scope':'same'},outcome={'value':60,'scope':'same'},
               unit='percent_accuracy', denominator='same100', sample_size=100,
               timeframe={'start':'2026-10-20','end':'2026-10-21'},method='same_scope')
        self.assertEqual(n.derive_metric(m)['relative_change_percent'], 20)
        self.assertEqual(n.derive_metric(m)['percentage_points'], 10)
        m['outcome']['scope']='other'
        self.assertFalse(n.derive_metric(m)['eligible'])
        m['baseline']['value']=0
        self.assertIsNone(n.derive_metric(m)['relative_change_percent'])

    def test_missing_metric_fields_never_become_zero(self):
        self.assertFalse(n.derive_metric({'baseline':None, 'outcome':None})['eligible'])
        self.assertIsNone(n.derive_metric({})['relative_change_percent'])
        incomplete=dict(baseline={'value':10,'scope':'same'},outcome={'value':8,'scope':'same'},unit='minutes',
                        denominator='100 tickets',sample_size=100,timeframe={},method='same_scope')
        self.assertFalse(n.derive_metric(incomplete)['eligible'])
        incomplete['timeframe']={'start':'2026-10-22','end':'2026-10-20'}
        self.assertFalse(n.derive_metric(incomplete)['eligible'])

    def test_score_only_after_gate_and_stable_tie(self):
        s=fixture()['stories']['stories'][0]
        self.assertEqual(n.editorial_total(s['editorial_score']),82.5)
        bad=copy.deepcopy(s);bad['evidence_gate']['passed']=False
        self.assertEqual(n.rank_stories([bad]),[])
        other=copy.deepcopy(s);other['canonical_event_key']='aaa'
        self.assertEqual(n.rank_stories([s,other])[0]['canonical_event_key'],'aaa')

    def test_reprints_share_evidence_group_not_independent(self):
        src=fixture()['sources']['sources'][0]
        sources=[{**src,'source_id':f'src_{i:03d}','url':f'https://example.invalid/{i}'} for i in range(3)]
        self.assertEqual(n.independent_groups(sources),1)

    def test_valid_attributed_flow_without_roi(self):
        self.assertEqual(v.validate_bundle(fixture(),final=True),[])

    def test_snippet_cannot_support_core(self):
        b=fixture();b['sources']['sources'][0]['access']['read_level']='search_snippet'
        self.assertIn('unread_evidence', self.codes(b))

    def test_missing_refs_cycle_and_false_qualifiers_rejected(self):
        b=fixture();b['script_map']['sentences'][1]['claim_ids']=['claim_missing']
        self.assertIn('missing_reference',self.codes(b))
        b=fixture();b['fact_cards']['claims'][0]['depends_on_claim_ids']=['claim_002']
        self.assertIn('dependency_cycle',self.codes(b))
        b=fixture();b['script_map']['sentences'][1]['required_qualifiers_present']=False
        self.assertIn('missing_qualifier',self.codes(b))

    def test_final_requires_semantic_review_and_all_factual_mapping(self):
        b=fixture();b['script_map']['checks']['semantic_fact_review']='not_run'
        self.assertIn('review_incomplete',self.codes(b))
        b=fixture();b['script_map']['sentences'][1]['claim_ids']=[]
        self.assertIn('unmapped_sentence',self.codes(b))

    def test_future_outside_and_strict_expansion_rejected(self):
        b=fixture();b['stories']['stories'][0]['event_identity']['event_date']['value']='2026-11-01'
        self.assertIn('ineligible_date',self.codes(b))
        b=fixture();b['run']['config']['strict_window']=True;b['run']['time_context']['expanded']=True
        self.assertIn('strict_window',self.codes(b))

    def test_schema_major_duplicates_and_budget_overrun_rejected(self):
        b=fixture();b['sources']['schema_version']='2.0'
        self.assertIn('schema_version',self.codes(b))
        b=fixture();b['sources']['sources']*=2
        self.assertIn('duplicate_id',self.codes(b))
        b=fixture();b['run']['budget']['search_calls_used']=9
        self.assertIn('budget_exceeded',self.codes(b))

    def test_unknown_enums_and_missing_fields_rejected(self):
        b=fixture();b['fact_cards']['claims'][0]['support_status']='certain'
        self.assertIn('invalid_enum',self.codes(b))
        b=fixture();del b['sources']['sources'][0]['retrieved_at']
        self.assertIn('missing_field',self.codes(b))

    def test_demo_requires_separate_maturity_and_basis(self):
        b=fixture();b['fact_cards']['enterprise_cases']=[dict(case_id='case_001',story_id='story_001',
            organization='虚构乙公司',business_process='routing',problem=None,input=None,ai_action=None,
            human_role=None,output=None,integration=None,deployment_status='demo',evidence_basis='self_reported',
            independently_supported_claim_ids=[],deployment_scope=None,cost=None,cost_unknown_reason='not_disclosed',
            metric_ids=[],limitations=['演示'],claim_ids=['claim_001'])]
        self.assertEqual(v.validate_bundle(b,final=True),[])
        b['fact_cards']['enterprise_cases'][0]['evidence_basis']='independently_supported'
        self.assertIn('independence_unspecified',self.codes(b))

    def test_transitive_and_title_claims_cannot_bypass_evidence(self):
        b=fixture();b['fact_cards']['claims'][0].update(allowed_in_script=False,support_status='insufficient',evidence=[])
        b['script_map']['sentences']=[b['script_map']['sentences'][2]]
        b['script_map']['title_claim_ids']=['claim_002']
        self.assertIn('unsupported_dependency',self.codes(b))
        b=fixture();b['fact_cards']['claims'][0]['allowed_in_script']=False
        b['script_map']['sentences']=[b['script_map']['sentences'][0]]
        self.assertIn('unsupported_claim',self.codes(b))

    def test_strict_window_cannot_be_silently_redefined(self):
        b=fixture();b['run']['config']['strict_window']=True
        b['run']['time_context']['window_start_utc']='2026-09-25T12:00:00Z'
        b['stories']['stories'][0]['event_identity']['event_date']['value']='2026-10-01'
        self.assertIn('invalid_window',self.codes(b))

    def test_malformed_external_records_return_errors_not_tracebacks(self):
        for part,key in [('stories','selected_story_ids'),('run','time_context')]:
            b=fixture();b[part][key]=None
            self.assertTrue(v.validate_bundle(b,final=True))
        b=fixture();b['run']['time_context']['now_utc']=None
        self.assertTrue(v.validate_bundle(b,final=True))

    def test_material_update_references_must_exist(self):
        b=fixture();b['stories']['stories'][0]['material_update']=dict(description='new',new_claim_ids=['missing'],source_ids=['absent'])
        self.assertIn('missing_reference',self.codes(b))

    def test_derived_number_recomputed_not_just_eligible(self):
        b=fixture();b['fact_cards']['metrics']=[dict(metric_id='metric_001',story_id='story_001',name='耗时',
            unit='minute_per_ticket',baseline=dict(value=10,scope='same',source_ids=['src_001']),
            outcome=dict(value=8,scope='same',source_ids=['src_001']),sample_size=100,denominator='same100',
            timeframe=dict(start='2026-10-20',end='2026-10-21'),method='same_scope',cost=None,
            cost_unknown_reason='not_disclosed',limitations=['fiction'],
            derived=dict(eligible=True,value=99,formula='(baseline - outcome) / baseline * 100',unit='percent_reduction',ineligible_reasons=[]))]
        self.assertIn('incorrect_metric',self.codes(b))

    def test_empty_title_and_incomplete_gate_are_not_final(self):
        b=fixture();b['script_map']['title']=''
        self.assertIn('empty_title',self.codes(b))
        b=fixture();b['stories']['stories'][0]['evidence_gate']['checks']={'looks_good':True}
        self.assertIn('evidence_gate',self.codes(b))

    def test_rolling_window_cannot_shift_into_the_past(self):
        b=fixture();b['run']['config']['strict_window']=True
        b['run']['time_context'].update(window_start_utc='2026-10-01T12:00:00Z',window_end_utc='2026-10-08T12:00:00Z')
        b['stories']['stories'][0]['event_identity']['event_date']['value']='2026-10-05'
        self.assertIn('invalid_window',self.codes(b))

    def test_nonfinite_json_numbers_are_rejected(self):
        b=fixture();b['fact_cards']['metrics']=[dict(metric_id='metric_001',story_id='story_001',name='耗时',
            unit='minute_per_ticket',baseline=dict(value=10,scope='same',source_ids=['src_001']),
            outcome=dict(value=8,scope='same',source_ids=['src_001']),sample_size=100,denominator='same100',
            timeframe=dict(start='2026-10-20',end='2026-10-21'),method='same_scope',cost=None,
            cost_unknown_reason='not_disclosed',limitations=['fiction'],
            derived=dict(eligible=True,value=float('nan'),formula='reduction',unit='percent_reduction',ineligible_reasons=[]))]
        self.assertIn('invalid_number',self.codes(b))


if __name__=='__main__': unittest.main()
