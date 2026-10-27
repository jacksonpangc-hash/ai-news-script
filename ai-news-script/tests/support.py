"""Hand-authored fictional evidence. Not news and not network results."""
import copy


def fixture():
    rid = '20261025T120000Z_fixture'
    config = dict(max_search_calls=8, max_open_calls=12, max_retries_per_source=2,
                  max_rewrite_passes=2, max_pool_stories=20, max_candidates=4,
                  max_selected_stories=1, min_editorial_score=60, lookback_days=7,
                  max_lookback_days=30, save_history=True, strict_window=False,
                  allow_evergreen_fallback=False, new_paid_providers=False,
                  retain_raw_pages=False, duration_seconds=[120, 180])
    run = dict(schema_version='1.0', run_id=rid,
               request=dict(text='虚构离线测试：讲一个企业流程', topic_scope='both', strict_window=False),
               config=config, status='reviewed', outcome=None,
               time_context=dict(now_utc='2026-10-25T12:00:00Z', effective_timezone='Asia/Shanghai',
                                 timezone_origin='host', window_start_utc='2026-10-18T12:00:00Z',
                                 window_end_utc='2026-10-25T12:00:00Z', window_type='rolling_days',
                                 lookback_days_used=7, expanded=False, content_mode='recent_news'),
               capabilities=dict(search_web='available', open_source='available', local_storage='available',
                                 host_name='fictional_test_host', adapter_verified=False),
               budget=dict(search_calls_used=2, open_calls_used=1, rewrite_passes_used=0,
                           retries_by_source={}, exhausted=False),
               coverage=dict(frontier='searched_no_qualified_result', enterprise='searched_with_qualified_result',
                             blocked_source_ids=[], limitations=['虚构测试；没有独立结果验证']),
               errors=[], output=dict(selected_story_ids=['story_001'], script_path=None,
                                      sources_path=None, history_saved=False), example_only=True)
    source = dict(source_id='src_001', url='https://example.invalid/case',
                  canonical_url='https://example.invalid/case', title='虚构乙公司客服试点',
                  publisher='虚构乙公司', source_kind='official_case',
                  published_at=dict(value='2026-10-22', precision='date', timezone=None),
                  updated_at=None, retrieved_at='2026-10-25T12:01:00Z',
                  access=dict(status='ok', read_level='full_text', visible_sections=['流程'],
                              audio_seen=False, visual_seen=False, transcript_seen=False, block_reason=None),
                  independence_group='fictional-company-statement',
                  evidence_notes=[dict(locator='流程第1段', observed_summary='企业自述试点，AI建议，员工确认，成本未知')],
                  example_only=True)
    story = dict(story_id='story_001', canonical_event_key='fictional|pilot|routing|v1|2026-10-22',
                 event_identity=dict(entity='虚构乙公司', action='pilot', object='工单分流', version='v1',
                                     event_date=dict(value='2026-10-22', precision='date', timezone='Asia/Shanghai', source_ids=['src_001'])),
                 channel='enterprise', source_ids=['src_001'], date_status='supported', history_match=None,
                 material_update=None, evidence_gate=dict(passed=True, checks=dict(
                     readable_core_evidence=True, entity_and_event_clear=True, date_conflict_resolved=True,
                     maturity_not_overstated=True, no_invented_testing_or_results=True), rejection_reasons=[]),
                 editorial_score=dict(practical_value=4, evidence_quality=2, information_gain=3,
                                      explainability=4, recency=4, total=82.5, rationale='虚构：流程清楚，只有自述'),
                 angle='建议和确认分开', selected=True, example_only=True)
    claims = [dict(claim_id='claim_001', story_id='story_001', claim_type='fact',
                   statement='虚构乙公司自述客服试点：AI建议分类，员工确认。', support_status='attributed_only',
                   evidence=[dict(source_id='src_001', locator='流程第1段', relationship='direct',
                                  observed_summary='公司自述试点，建议和确认分开')],
                   qualifiers=['公司自述', '试点'], depends_on_claim_ids=[], allowed_in_script=True),
              dict(claim_id='claim_002', story_id='story_001', claim_type='assistant_interpretation',
                   statement='建议和确认分开。', support_status='supported', evidence=[],
                   qualifiers=[], depends_on_claim_ids=['claim_001'], allowed_in_script=True)]
    sentences = [dict(sentence_id='sent_001', paragraph_index=0, text='客服要怎样安排AI的职责？',
                      sentence_kind='rhetorical', claim_ids=[], required_qualifiers_present=True),
                 dict(sentence_id='sent_002', paragraph_index=1,
                      text='虚构乙公司自述，客服试点中由AI建议分类，再交员工确认。',
                      sentence_kind='attributed', claim_ids=['claim_001'], required_qualifiers_present=True),
                 dict(sentence_id='sent_003', paragraph_index=2, text='这个流程把建议和确认分开了。',
                      sentence_kind='interpretive', claim_ids=['claim_002'], required_qualifiers_present=True)]
    names = ['schema', 'references_exist', 'factual_sentence_coverage', 'semantic_fact_review',
             'dates_and_numbers', 'attribution_and_maturity', 'no_fabricated_first_person_experience',
             'text_listenability', 'hook_promise_fulfilled']
    smap = dict(revision=1, title='虚构测试：工单分流的分工', sentences=sentences,
                checks={**dict.fromkeys(names, 'pass'), 'actual_audio_listened': False, 'issues': []},
                title_claim_ids=['claim_001'])
    wrap = lambda **kwargs: dict(schema_version='1.0', run_id=rid, **kwargs)
    return copy.deepcopy(dict(run=run, sources=wrap(sources=[source]),
                              stories=wrap(stories=[story], selected_story_ids=['story_001']),
                              fact_cards=wrap(claims=claims, metrics=[], enterprise_cases=[]), script_map=wrap(**smap)))
