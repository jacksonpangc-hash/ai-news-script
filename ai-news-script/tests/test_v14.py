"""Fictional routing evidence; no claims about real geography or writing quality."""
import copy
import unittest
from test_v11 import routed_fixture,URLS
import manage_state as state
import discovery
from validate_records import validate_bundle
from normalize_records import rank_stories
from render_output import render


def regional_fixture(region='china_mainland',scope='mainland_preferred'):
    b=routed_fixture();r=b['run']
    r['config'].update(region_policy='mainland_first_v1',builder_feed_policy='supplementary_v1',region_scope=scope)
    r['request'].update(region_scope=scope,region_scope_reason='默认偏好' if scope=='mainland_preferred' else '虚构用户明确范围')
    r['tool_log']=[dict(call_id='cn'+str(i),kind='search',discovery_channel='official_case_search',
        query='虚构大陆案例检索'+str(i),region_focus='china_mainland',search_angle=angle,
        outcome='results_returned',timestamp='2026-10-25T12:00:00Z',source_id='src_001',lead_id=None,fallback_of=None)
        for i,angle in enumerate(['学习实际演示','日常生活使用'])]
    r['budget'].update(open_calls_used=0,search_calls_used=2)
    r['discovery_routes']['official_case_search']['attempt_ids']=['cn0','cn1']
    for f in r['discovery_routes']['builder_feed']['feeds']:
        reason='mainland_evidence_sufficient' if region=='china_mainland' else ('user_scope' if scope!='mainland_preferred' else 'supplementary_not_needed')
        f.update(status='not_enabled',skip_reason=reason,attempt_ids=[],generated_at=None,items_count=None,window_items_count=None,qualified_items_count=None,error=None)
    r['discovery_routes']['builder_feed']['status']='not_enabled'
    r['region_review']=dict(mainland_result='qualified',fallback_reason=None,expansion_decision='not_needed',expansion_reason='已有合格大陆案例')
    c=copy.deepcopy(b['fact_cards']['claims'][0]);c.update(claim_id='region_fact',statement='虚构使用场景位于广州。')
    b['fact_cards']['claims'].append(c)
    b['stories']['stories'][0]['case_region']=dict(value=region,basis_type='location_of_use',text='虚构原文明示使用场景',claim_ids=['region_fact'])
    return b

class RegionPolicyTests(unittest.TestCase):
    def codes(self,b):return {e['code'] for e in validate_bundle(b,final=True)}

    def test_new_default_and_explicit_user_scope(self):
        r=state.new_run('最近AI新闻')
        self.assertEqual(r['request'].get('region_scope'),'mainland_preferred')
        self.assertEqual(r['config'].get('builder_feed_policy'),'supplementary_v1')
        for scope in ['mainland_only','overseas_only','global','user_specified']:
            r=state.new_run('用户明确范围',overrides={'region_scope':scope})
            self.assertEqual(r['request']['region_scope'],scope)
        with self.assertRaises(ValueError):state.new_run('x',overrides={'region_scope':'guess_from_name'})

    def test_sufficient_mainland_material_can_skip_all_feeds_honestly(self):
        self.assertEqual(self.codes(regional_fixture()),set())

    def test_skip_cannot_fake_success_or_budget_exhaustion(self):
        for mutation in ['attempt','count','reason']:
            b=regional_fixture();f=b['run']['discovery_routes']['builder_feed']['feeds'][0]
            if mutation=='attempt':f['attempt_ids']=['cn0']
            elif mutation=='count':f['items_count']=0
            else:f['skip_reason']='budget_exhausted'
            self.assertIn('discovery_coverage',self.codes(b))

    def test_two_distinct_mainland_angles_must_be_first_searches(self):
        for mutation in ['one','same_angle','foreign_first']:
            b=regional_fixture();logs=b['run']['tool_log']
            if mutation=='one':logs[1]['region_focus']='global'
            elif mutation=='same_angle':logs[1]['search_angle']=logs[0]['search_angle']
            else:logs[0]['region_focus']='overseas'
            self.assertIn('mainland_search_required',self.codes(b))

    def test_foreign_fallback_needs_gap_and_window_reason(self):
        b=regional_fixture('overseas')
        self.assertIn('region_fallback_unjustified',self.codes(b))
        b['run']['region_review'].update(mainland_result='insufficient',fallback_reason='两类大陆线索均无实际执行证据；原文不可读',expansion_decision='not_useful',expansion_reason='缺执行记录，延长日期不能补出执行依据')
        self.assertEqual(self.codes(b),set())
        out=render(b)
        self.assertIn('两类大陆线索',out['conversation'].split('# ')[0])
        self.assertNotIn('两类大陆线索',out['script'])

    def test_failed_mainland_query_then_successful_retry_preserves_order_and_budget(self):
        b=regional_fixture();r=b['run'];first,second=r['tool_log']
        retry=copy.deepcopy(first);retry.update(call_id='cn_retry',fallback_of=first['call_id'])
        first['outcome']='timeout';r['tool_log']=[first,retry,second]
        r['budget']['search_calls_used']=3;r['budget']['retries_by_source']={'src_001':1}
        r['discovery_routes']['official_case_search']['attempt_ids']=['cn0','cn_retry','cn1']
        self.assertEqual(self.codes(b),set())

    def test_feed_skip_reason_cannot_claim_sufficient_mainland_evidence_after_gap(self):
        b=regional_fixture('overseas');r=b['run']
        r['region_review'].update(mainland_result='insufficient',fallback_reason='大陆来源无执行证据',expansion_decision='not_useful',expansion_reason='扩窗不补执行依据')
        r['discovery_routes']['builder_feed']['feeds'][0]['skip_reason']='mainland_evidence_sufficient'
        self.assertIn('discovery_coverage',self.codes(b))

    def test_mainland_only_and_strict_window_do_not_silently_expand(self):
        b=regional_fixture('overseas','mainland_only')
        self.assertIn('region_scope_mismatch',self.codes(b))
        b=regional_fixture('overseas');r=b['run'];r['request']['strict_window']=True
        r['region_review'].update(mainland_result='insufficient',fallback_reason='严格本周大陆材料不足',expansion_decision='strict_window',expansion_reason='用户禁止扩窗')
        self.assertEqual(self.codes(b),set())
        r['region_review']['expansion_decision']='expanded_to_30_days'
        self.assertIn('region_fallback_unjustified',self.codes(b))

    def test_language_domain_model_and_name_are_not_location_evidence(self):
        for basis in ['language','publisher_domain','model_origin','person_name']:
            b=regional_fixture();b['stories']['stories'][0]['case_region']['basis_type']=basis
            self.assertIn('case_region_evidence',self.codes(b))
        b=regional_fixture();b['stories']['stories'][0]['case_region']=dict(value='unknown',basis_type='unknown',text='中文转载，实际地点未明',claim_ids=[])
        self.assertIn('region_fallback_unjustified',self.codes(b))
        for place in ['hong_kong','macau','taiwan']:
            self.assertIn('region_scope_mismatch',self.codes(regional_fixture(place,'mainland_only')))

    def test_explicit_global_or_topic_request_does_not_force_domestic_search(self):
        for scope in ['global','overseas_only','user_specified']:
            b=regional_fixture('overseas',scope);b['run']['tool_log'][0]['region_focus']='global'
            self.assertEqual(self.codes(b),set())

    def test_rank_prefers_eligible_mainland_without_region_percentages(self):
        cn=regional_fixture()['stories']['stories'][0];foreign=copy.deepcopy(cn)
        foreign.update(story_id='other',canonical_event_key='other');foreign['case_region']['value']='overseas'
        foreign['editorial_score'].update(evidence_quality=4,total=95)
        self.assertIs(rank_stories([foreign,cn],region_scope='mainland_preferred')[0],cn)
        self.assertEqual(rank_stories([foreign],region_scope='mainland_only'),[])
        self.assertIs(rank_stories([foreign,cn],region_scope='global')[0],foreign)

    def test_legacy_routes_keep_their_original_requirement(self):
        self.assertEqual(self.codes(routed_fixture()),set())
        b=routed_fixture();b['run']['discovery_routes']['builder_feed']['feeds'][0].update(status='not_enabled',attempt_ids=[])
        self.assertIn('discovery_coverage',self.codes(b))

    def test_supplementary_reader_can_fetch_one_and_skip_rest(self):
        r=state.new_run('全球案例',overrides={'region_scope':'global','save_history':False})
        reads=[]
        def reader(url):
            reads.append(url);return {'generatedAt':r['time_context']['now_utc'],'x':[]}
        discovery.discover(r,reader=reader,urls=[URLS[0]])
        discovery.skip_feeds(r,'supplementary_not_needed')
        self.assertEqual(reads,[URLS[0]])
        self.assertEqual(r['budget']['open_calls_used'],1)
        self.assertEqual([f['status'] for f in r['discovery_routes']['builder_feed']['feeds']],['ok_empty','not_enabled','not_enabled'])
        self.assertEqual(r['coverage']['limitations'],[])

if __name__=='__main__':unittest.main()
