"""Fictional inputs; tests constraints and side effects, never declares semantic quality."""
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from support import fixture
import manage_state as state
import validate_records as validator
try:
    import discovery
except ImportError:
    discovery=None

URLS=[f'https://raw.githubusercontent.com/zarazhangrui/follow-builders/main/feed-{n}.json' for n in ('x','blogs','podcasts')]


def practical_fixture():
    b=fixture()
    for obj in b.values():obj['schema_version']='1.1'
    b['run']['request'].update(topic_scope='practical_cases',research_mode='fixed_source_regression')
    b['run']['config']['topic_scope']='practical_cases'
    s=b['stories']['stories'][0]
    s['practical_value_gate']=dict(decision='pass',reason='虚构团队实际试点完成工单分类；有定性过程和产出',claim_ids=['claim_001'])
    s['value_brief']=dict(domain='enterprise_efficiency',application_context='pilot',outcome_evidence_type='qualitative',
        beneficiary_task=dict(text='虚构团队分流工单',claim_ids=['claim_001']),
        before=dict(text='原先逐张分流；此为本fixture明确新增的虚构设定',claim_ids=['claim_001']),
        after=dict(text='AI提出分类建议，员工确认',claim_ids=['claim_001']),
        changed_mechanism=dict(text='把逐张判断转为审核建议',claim_ids=['claim_002']),
        result_evidence=dict(text='虚构团队用确认后的分类继续处理来单',claim_ids=['claim_001']),
        cost_boundary=dict(value=None,unknown_reason='not_disclosed',text='原文未披露成本',claim_ids=[]))
    s['editorial_bridge']=dict(text='听众关心重复分流。AI先给建议，改变员工从头分类的起点。这个案例能帮助判断人和AI的分工。',claim_ids=['claim_001','claim_002'])
    b['script_map']['review_evidence']=[dict(check=key,sentence_ids=['sent_002'],basis_claim_ids=['claim_001'],
        finding='虚构原句给出了AI建议和员工确认，主张限于这一试点；表达变化不增加效率数字。',change=None)
        for key in ('actual_value','explanation_chain','natural_expression','fact_fidelity')]
    b['run']['discovery_routes']={}
    return b


def routed_fixture():
    b=practical_fixture();r=b['run'];r['request']['research_mode']='full'
    r['tool_log']=[];feeds=[]
    for i,url in enumerate(URLS):
        ident='feed_'+str(i)
        r['tool_log'].append(dict(call_id=ident,kind='open',discovery_channel='builder_feed',url=url,
            outcome='json_parsed',timestamp='2026-10-25T12:00:00Z',source_id='src_001',lead_id=None,fallback_of=None))
        feeds.append(dict(url=url,status='ok_empty',generated_at='2026-10-25T11:00:00Z',items_count=0,
            window_items_count=0,qualified_items_count=0,attempt_ids=[ident],error=None))
    r['tool_log'].append(dict(call_id='search_1',kind='search',discovery_channel='official_case_search',query='fictional case query',
        outcome='results_returned',timestamp='2026-10-25T12:00:00Z',source_id='src_001',lead_id=None,fallback_of=None))
    r['budget'].update(open_calls_used=3,search_calls_used=1)
    r['discovery_routes']=dict(builder_feed=dict(status='ok',feeds=feeds),official_case_search=dict(status='ok',attempt_ids=['search_1']))
    return b


class V11Tests(unittest.TestCase):
    def codes(self,b):return {e['code'] for e in validator.validate_bundle(b,final=True)}

    def test_new_requests_default_to_practical_cases_and_v11(self):
        r=state.new_run('normal request')
        self.assertEqual((r['schema_version'],r['request']['topic_scope']),('1.1','practical_cases'))
        self.assertEqual(set(r['discovery_routes']),{'builder_feed','official_case_search'})

    def test_legacy_reads_do_not_get_new_gate_fabricated(self):
        b=fixture();self.assertEqual(validator.validate_bundle(b,final=True),[])
        self.assertNotIn('practical_value_gate',b['stories']['stories'][0])

    def test_actual_flow_without_roi_can_pass(self):
        self.assertEqual(validator.validate_bundle(practical_fixture(),final=True),[])

    def test_high_score_cannot_rescue_feature_only_release(self):
        b=practical_fixture();s=b['stories']['stories'][0]
        s['practical_value_gate']['decision']='reject';s['value_brief']['application_context']='product_demo'
        self.assertIn('practical_gate',self.codes(b))

    def test_pure_demo_cannot_pass_by_changing_gate_word(self):
        b=practical_fixture();b['stories']['stories'][0]['value_brief']['application_context']='product_demo'
        self.assertIn('application_not_demonstrated',self.codes(b))

    def test_value_brief_and_bridge_need_real_references(self):
        b=practical_fixture();b['stories']['stories'][0]['value_brief']['before']['claim_ids']=['absent']
        self.assertIn('missing_reference',self.codes(b))
        b=practical_fixture();b['stories']['stories'][0]['editorial_bridge']['text']=''
        self.assertIn('editorial_bridge',self.codes(b))

    def test_personal_case_does_not_require_fake_enterprise(self):
        b=practical_fixture();s=b['stories']['stories'][0];s['channel']='personal'
        s['value_brief'].update(domain='personal_efficiency',application_context='actual_use')
        self.assertEqual(validator.validate_bundle(b,final=True),[])

    def test_semantic_pass_is_not_enough_without_review_evidence(self):
        b=practical_fixture();b['script_map'].pop('review_evidence')
        self.assertIn('review_evidence',self.codes(b))
        b=practical_fixture();b['script_map']['review_evidence'][0]['finding']='pass'
        self.assertIn('review_evidence',self.codes(b))

    def test_review_evidence_references_must_exist(self):
        b=practical_fixture();b['script_map']['review_evidence'][1]['sentence_ids']=['absent']
        self.assertIn('missing_reference',self.codes(b))

    def test_disclosure_cannot_masquerade_as_new_execution(self):
        b=practical_fixture();s=b['stories']['stories'][0]
        s.update(news_basis='recent_disclosure',disclosed_at=dict(value='2026-10-22',precision='date',source_ids=['src_001']),
                 case_occurred_at=dict(value='2026-09-18',precision='date',source_ids=['src_001']))
        self.assertIn('disclosure_identity',self.codes(b))
        s['event_identity']['action']='disclose_case'
        self.assertEqual(validator.validate_bundle(b,final=True),[])

    def test_full_research_cannot_claim_feed_coverage_from_readme(self):
        b=practical_fixture();b['run']['request']['research_mode']='full'
        b['run']['discovery_routes']={'builder_feed':{'status':'ok','feeds':[]},'official_case_search':{'status':'ok','attempt_ids':[]}}
        self.assertIn('discovery_coverage',self.codes(b))

    def test_new_unknown_major_never_writes(self):
        b=practical_fixture();b['run']['schema_version']='2.0'
        self.assertIn('schema_version',self.codes(b))

    def test_failed_tool_records_cannot_claim_successful_routes(self):
        b=routed_fixture();self.assertEqual(self.codes(b),set())
        for call in b['run']['tool_log']:call['outcome']='read_or_parse_failed'
        self.assertIn('discovery_coverage',self.codes(b))

    def test_official_failure_requires_disclosed_gap(self):
        b=routed_fixture();r=b['run'];r['coverage']['limitations']=[]
        r['tool_log'][-1]['outcome']='failed';r['discovery_routes']['official_case_search']['status']='failed'
        self.assertIn('discovery_coverage',self.codes(b))

    def test_logged_reads_and_searches_cannot_exceed_charged_budget(self):
        b=routed_fixture();b['run']['budget'].update(open_calls_used=0,search_calls_used=0)
        self.assertIn('discovery_coverage',self.codes(b))

    def test_case_dates_parse_and_compare_actual_utc(self):
        b=practical_fixture();s=b['stories']['stories'][0]
        d=dict(value='2026-10-22T01:00:00Z',precision='timestamp',timezone=None,source_ids=['src_001'])
        s.update(news_basis='recent_disclosure',disclosed_at=d,case_occurred_at=dict(value='2026-10-22T00:30:00-04:00',precision='timestamp',timezone=None,source_ids=['src_001']))
        s['event_identity'].update(action='disclose_case',event_date=copy.deepcopy(d))
        self.assertIn('disclosure_identity',self.codes(b))
        s['case_occurred_at']['value']='0000-invalid-date'
        self.assertIn('disclosure_identity',self.codes(b))


class FeedTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(discovery,'public JSON adapter missing')

    def parse(self,data,name='x'):
        return discovery.parse_feed(data,URLS[('x','blogs','podcasts').index(name)],
            '2026-10-25T12:00:00Z','2026-10-18T12:00:00Z','2026-10-25T12:00:00Z')

    def test_named_author_tweets_are_consumed_not_root_items(self):
        x=self.parse({'generatedAt':'2026-10-25T11:00:00Z','x':[{'name':'fiction','tweets':[
            {'id':'a','text':'Fictional person used AI to organize records','createdAt':'2026-10-22T10:00:00Z','url':'https://example.invalid/a'}]}]})
        self.assertEqual(x['items_count'],1);self.assertEqual(x['window_items_count'],1)
        self.assertEqual(x['leads'][0]['url'],'https://example.invalid/a')

    def test_generation_time_never_refreshes_old_items(self):
        x=self.parse({'generatedAt':'2026-10-25T11:00:00Z','x':[{'tweets':[{'createdAt':'2026-04-01T00:00:00Z','text':'old','url':'https://example.invalid/old'}]}]})
        self.assertEqual(x['window_items_count'],0)

    def test_empty_stale_and_parse_failure_are_distinct(self):
        self.assertEqual(self.parse({'generatedAt':'2026-10-25T11:00:00Z','blogs':[]},'blogs')['status'],'ok_empty')
        self.assertEqual(self.parse({'generatedAt':'2026-10-01T11:00:00Z','blogs':[]},'blogs')['status'],'stale')
        with self.assertRaises(ValueError):self.parse({'generatedAt':'today','items':[]})

    def test_channel_link_is_not_a_read_episode_and_transcript_not_retained(self):
        x=self.parse({'generatedAt':'2026-10-25T11:00:00Z','podcasts':[{'title':'fiction','url':'https://www.youtube.com/@demo/videos',
            'publishedAt':'2026-10-22T10:00:00Z','transcript':'complete third party transcript'}]},'podcasts')
        self.assertFalse(x['leads'][0]['specific_document'])
        self.assertNotIn('transcript',json.dumps(x))

    def test_fetch_failures_are_counted_and_do_not_create_files(self):
        r=state.new_run('no save',now='2026-10-25T12:00:00Z',overrides={'save_history':False,'region_scope':'global'})
        def unavailable(url):raise OSError('fictional network failure')
        with tempfile.TemporaryDirectory() as d:
            result=discovery.discover(r,reader=unavailable)
            self.assertEqual(r['budget']['open_calls_used'],3)
            self.assertEqual([f['status'] for f in result['feeds']],['failed']*3)
            self.assertEqual(list(Path(d).iterdir()),[])

    def test_budget_stops_before_next_network_call(self):
        r=state.new_run('bounded',overrides={'max_open_calls':0,'region_scope':'global'})
        calls=[]
        discovery.discover(r,reader=lambda url:calls.append(url))
        self.assertEqual(calls,[])


if __name__=='__main__':unittest.main()
