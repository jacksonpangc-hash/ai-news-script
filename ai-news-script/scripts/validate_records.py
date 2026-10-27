"""Validate record structure and provenance links; semantic review remains the host's duty."""
import argparse
import json
import math
from pathlib import Path
from normalize_records import date_status, derive_metric, editorial_total, normalize_url, utc

VERSION = '1.1'
STATES = ['initialized','capability_checked','scanning','deduplicated','screened','selected',
          'deep_read','fact_checked','drafted','reviewed','saved','delivered','blocked','failed','canceled']
OUTCOMES = [None,'delivered','delivered_with_limits','blocked','failed','canceled']
CHECKS = ['schema','references_exist','factual_sentence_coverage','semantic_fact_review','dates_and_numbers',
          'attribution_and_maturity','no_fabricated_first_person_experience','text_listenability','hook_promise_fulfilled']
COVERAGE = ['not_requested','not_searched','searched_with_qualified_result','searched_no_qualified_result',
            'partially_blocked','blocked']
TOP = {
    'run':['run_id','request','time_context','config','capabilities','budget','status','outcome','coverage','errors','output'],
    'sources':['run_id','sources'], 'stories':['run_id','stories','selected_story_ids'],
    'fact_cards':['run_id','claims','metrics','enterprise_cases'],
    'script_map':['run_id','revision','title','sentences','checks']}
REQUIRED = {
    'sources':['source_id','url','canonical_url','title','publisher','source_kind','published_at','updated_at',
               'retrieved_at','access','independence_group','evidence_notes'],
    'stories':['story_id','canonical_event_key','event_identity','channel','source_ids','date_status','history_match',
               'material_update','evidence_gate','editorial_score','angle','selected'],
    'claims':['claim_id','story_id','claim_type','statement','support_status','evidence','qualifiers',
              'depends_on_claim_ids','allowed_in_script'],
    'metrics':['metric_id','story_id','name','unit','baseline','outcome','sample_size','denominator','timeframe',
               'method','cost','cost_unknown_reason','limitations','derived'],
    'enterprise_cases':['case_id','story_id','organization','business_process','problem','input','ai_action','human_role',
                        'output','integration','deployment_status','evidence_basis','independently_supported_claim_ids',
                        'deployment_scope','cost','cost_unknown_reason','metric_ids','limitations','claim_ids'],
    'sentences':['sentence_id','paragraph_index','text','sentence_kind','claim_ids','required_qualifiers_present']}


def validate_bundle(bundle, final=False):
    try:
        def finite(value):
            if isinstance(value,float) and not math.isfinite(value):return False
            if isinstance(value,dict):return all(finite(v) for v in value.values())
            if isinstance(value,list):return all(finite(v) for v in value)
            return True
        if not finite(bundle):
            return [dict(code='invalid_number',path='$',message='NaN and Infinity are not valid record numbers')]
        return _validate_bundle(bundle, final=final)
    except (TypeError, AttributeError, KeyError, ValueError, RecursionError, OverflowError) as exc:
        # Imports are data, including malformed nested types. Do not print raw contents.
        return [dict(code='invalid_record',path='$',message='Malformed record ('+type(exc).__name__+')')]


def _validate_bundle(bundle, final=False):
    errors = []
    def err(code, path, message):
        errors.append(dict(code=code,path=path,message=message))
    def required(obj, fields, path):
        if not isinstance(obj, dict):
            err('invalid_type',path,'Expected object');return False
        for field in fields:
            if field not in obj:err('missing_field',path+'.'+field,'Required field absent')
        return all(field in obj for field in fields)
    def enum(value, options, path):
        if value not in options:err('invalid_enum',path,'Unsupported enum value')
    if not isinstance(bundle,dict):
        return [dict(code='invalid_type',path='$',message='Expected bundle object')]
    for key, fields in TOP.items():
        obj = bundle.get(key)
        required(obj, ['schema_version']+fields, key)
        if isinstance(obj,dict) and (obj.get('schema_version') not in ('1.0','1.1') or obj.get('schema_version')!=bundle.get('run',{}).get('schema_version')):
            err('schema_version',key,'Use consistent supported schema 1.0 or 1.1; legacy is not auto-upgraded')
    if errors:return errors
    run, smap = bundle['run'], bundle['script_map']
    rid = run['run_id']
    for key in TOP:
        if bundle[key]['run_id'] != rid:err('run_id_mismatch',key,'Mixed runs')
    for key in ['request','config','time_context','capabilities','budget','coverage','output']:
        if not isinstance(run[key],dict):err('invalid_type','run.'+key,'Expected object')
    if errors:return errors
    config, budget, tc = run['config'], run['budget'], run['time_context']
    enum(run['status'],STATES,'run.status');enum(run['outcome'],OUTCOMES,'run.outcome')
    for channel in ('frontier','enterprise'):
        enum(run['coverage'].get(channel),COVERAGE,'run.coverage.'+channel)
        if final and run['request'].get('topic_scope','both') == 'both' and run['coverage'].get(channel) in ('not_requested','not_searched'):
            err('coverage_incomplete','run.coverage.'+channel,'Both channels require an actual search or recorded block')
    for used, limit in [('search_calls_used','max_search_calls'),('open_calls_used','max_open_calls'),
                        ('rewrite_passes_used','max_rewrite_passes')]:
        a,b=budget.get(used),config.get(limit)
        if any(isinstance(x,bool) or not isinstance(x,int) or x<0 for x in [a,b]):
            err('invalid_budget','run.budget.'+used,'Expected nonnegative integers')
        elif a>b:err('budget_exceeded','run.budget.'+used,'Limit exceeded')
    retries=budget.get('retries_by_source',{})
    if not isinstance(retries,dict):err('invalid_type','run.budget.retries_by_source','Expected object')
    else:
        for sid,n in retries.items():
            if isinstance(n,bool) or not isinstance(n,int) or not 0<=n<=config.get('max_retries_per_source',2):
                err('budget_exceeded','run.budget.retries_by_source.'+sid,'Invalid retry count')
    strict = config.get('strict_window') or run['request'].get('strict_window')
    mode = tc.get('content_mode')
    enum(mode,[None,'recent_news','expanded_window','evergreen'],'run.time_context.content_mode')
    if strict and (tc.get('expanded') or mode=='evergreen'):
        err('strict_window','run.time_context','Strict window cannot expand or use evergreen')
    if mode=='evergreen' and not config.get('allow_evergreen_fallback'):
        err('evergreen_not_authorized','run.time_context','Explicit permission required')
    try:
        start,end,now = [utc(tc[k]) for k in ['window_start_utc','window_end_utc','now_utc']]
        if start>end or end>now:err('invalid_window','run.time_context','Invalid or future window')
        if (end-start).total_seconds()>30*86400:err('invalid_window','run.time_context','News window exceeds 30 days')
        if tc.get('expanded') and mode not in ('expanded_window','evergreen'):
            err('invalid_window','run.time_context','Expansion must be disclosed by content mode')
        used=tc.get('lookback_days_used',config.get('lookback_days',7))
        days=(end-start).total_seconds()/86400
        if tc.get('window_type')=='rolling_days' and abs(days-used)>1/86400:
            err('invalid_window','run.time_context','Rolling window does not match recorded days')
        if tc.get('window_type')=='rolling_days' and abs((end-now).total_seconds())>1:
            err('invalid_window','run.time_context','Rolling news window must end at this run clock')
        if strict and days>config.get('lookback_days',7)+1/86400:
            err('invalid_window','run.time_context','Strict window exceeds the requested length')
        if days>config.get('lookback_days',7)+1/86400 and not tc.get('expanded'):
            err('invalid_window','run.time_context','Larger news window must disclose expansion')
    except (KeyError,ValueError,TypeError):
        err('invalid_window','run.time_context','Missing or malformed timezone-aware window')
    # Index records; never silently let duplicate IDs replace each other.
    tables={}
    collection_parent={'sources':'sources','stories':'stories','claims':'fact_cards','metrics':'fact_cards',
                       'enterprise_cases':'fact_cards','sentences':'script_map'}
    id_fields=dict(sources='source_id',stories='story_id',claims='claim_id',metrics='metric_id',
                   enterprise_cases='case_id',sentences='sentence_id')
    for name,parent in collection_parent.items():
        rows=bundle[parent].get(name)
        if not isinstance(rows,list):err('invalid_type',parent+'.'+name,'Expected array');continue
        tables[name]={}
        for i,row in enumerate(rows):
            path=f'{parent}.{name}[{i}]'
            if not required(row,REQUIRED[name],path):continue
            ident=row[id_fields[name]]
            if not isinstance(ident,str) or not ident:
                err('invalid_id',path,'ID must be nonempty string');continue
            if ident in tables[name]:err('duplicate_id',path,'Duplicate ID')
            tables[name][ident]=row
    if errors:return errors
    def refs(ids,table,path):
        if not isinstance(ids,list):err('invalid_type',path,'Expected ID array');return
        for ident in ids:
            if not isinstance(ident,str) or ident not in tables[table]:
                err('missing_reference',path,'Referenced '+table+' ID absent')
    def story_ref(row,path):refs([row['story_id']],'stories',path+'.story_id')
    for sid,source in tables['sources'].items():
        path='sources.'+sid
        for key in ('url','canonical_url'):
            try:normalize_url(source[key])
            except (ValueError,TypeError):err('unsafe_url',path+'.'+key,'URL is invalid or contains credentials')
        if not run.get('example_only') and ('example.invalid' in source['url'] or source.get('example_only')):
            err('fiction_in_live_run',path,'Fictional fixture cannot enter live evidence')
        access=source['access']
        if required(access,['status','read_level','visible_sections','audio_seen','visual_seen','transcript_seen','block_reason'],path+'.access'):
            enum(access['status'],['ok','partial','blocked','not_found','transient_error','not_read'],path+'.access.status')
            enum(access['read_level'],['full_text','visible_excerpt','search_snippet','metadata_only','none'],path+'.access.read_level')
        try:utc(source['retrieved_at'])
        except (ValueError,TypeError):err('invalid_date',path+'.retrieved_at','Expected timezone-aware timestamp')
        for key in ('published_at','updated_at'):
            d=source[key]
            if d is not None:
                try:date_status(d,tc['window_start_utc'],tc['window_end_utc'])
                except (KeyError,ValueError,TypeError):err('invalid_date',path+'.'+key,'Malformed date record')
    selected=bundle['stories']['selected_story_ids']
    refs(selected,'stories','stories.selected_story_ids')
    if run['output'].get('selected_story_ids') != selected:
        err('selection_mismatch','run.output.selected_story_ids','Selection differs across records')
    if len(selected)>config.get('max_selected_stories',1):err('selection_limit','stories','Too many selected stories')
    if len(tables['stories'])>config.get('max_pool_stories',20):err('pool_limit','stories','Too many pooled stories')
    for sid,story in tables['stories'].items():
        path='stories.'+sid;refs(story['source_ids'],'sources',path+'.source_ids')
        enum(story['channel'],['frontier','enterprise','personal','business'] if run['schema_version']=='1.1' else ['frontier','enterprise'],path+'.channel')
        enum(story['date_status'],['supported','ambiguous','future_unverified','conflicting','outside_window'],path+'.date_status')
        gate=story['evidence_gate']
        if not isinstance(gate,dict):err('invalid_type',path+'.evidence_gate','Expected object');continue
        if gate.get('passed') is not True and story['editorial_score'] is not None:
            err('score_before_gate',path,'Failed evidence gate cannot receive score')
        if story['editorial_score'] is not None:
            try:
                total=editorial_total(story['editorial_score'])
                if total!=story['editorial_score'].get('total'):err('incorrect_score',path,'Score arithmetic differs')
            except (KeyError,ValueError,TypeError):err('invalid_score',path,'Invalid score components')
        if sid in selected:
            checks=gate.get('checks',{})
            gate_keys=['readable_core_evidence','entity_and_event_clear','date_conflict_resolved',
                       'maturity_not_overstated','no_invented_testing_or_results']
            if gate.get('passed') is not True or not all(checks.get(k) is True for k in gate_keys):
                err('evidence_gate',path,'Selected story must pass explicit evidence checks')
            if story['editorial_score'] is None or editorial_total(story['editorial_score'])<config.get('min_editorial_score',60):
                err('editorial_threshold',path,'Selected story below the editorial threshold')
            try:
                d=story['event_identity']['event_date']
                actual=date_status(d,tc['window_start_utc'],tc['window_end_utc'])
                refs(d.get('source_ids',[]),'sources',path+'.event_date.source_ids')
                if actual=='future_unverified' or story['date_status'] in ('future_unverified','conflicting') or (actual=='outside_window' and mode!='evergreen'):
                    err('ineligible_date',path,'Selected event outside eligible window or unresolved date conflict')
                if actual=='ambiguous' and story['date_status']!='ambiguous':
                    err('date_precision',path,'Date-boundary uncertainty must remain visible')
            except (KeyError,ValueError,TypeError):err('invalid_date',path,'Missing or invalid event date')
            if story.get('selected') is not True:err('selection_mismatch',path,'Selected flag missing')
        update=story.get('material_update')
        if update is not None and required(update,['description','new_claim_ids','source_ids'],path+'.material_update'):
            refs(update['new_claim_ids'],'claims',path+'.material_update.new_claim_ids')
            refs(update['source_ids'],'sources',path+'.material_update.source_ids')
            if not update['description'] or not update['new_claim_ids'] or not update['source_ids']:
                err('empty_material_update',path,'A material update needs actual new claims and sources')
    for cid,claim in tables['claims'].items():
        path='claims.'+cid;story_ref(claim,path)
        enum(claim['claim_type'],['fact','source_opinion','assistant_interpretation'],path+'.claim_type')
        enum(claim['support_status'],['supported','attributed_only','disputed','insufficient'],path+'.support_status')
        refs(claim['depends_on_claim_ids'],'claims',path+'.depends_on_claim_ids')
        if claim['allowed_in_script'] and claim['support_status'] not in ('supported','attributed_only'):
            err('unsupported_claim',path,'Unresolved claim not allowed in final script')
        if not isinstance(claim['evidence'],list):err('invalid_type',path+'.evidence','Expected array');continue
        if claim['allowed_in_script']:
            if claim['claim_type']!='assistant_interpretation' and not claim['evidence']:
                err('missing_evidence',path,'Factual claim requires read evidence')
            if claim['claim_type']=='assistant_interpretation' and not claim['evidence'] and not claim['depends_on_claim_ids']:
                err('missing_dependency',path,'Interpretation must depend on evidence or claims')
        for evidence in claim['evidence']:
            if not required(evidence,['source_id','locator','relationship','observed_summary'],path+'.evidence'):continue
            refs([evidence['source_id']],'sources',path+'.evidence')
            source=tables['sources'].get(evidence['source_id'])
            if source and claim['allowed_in_script']:
                access=source['access']
                if access.get('status') not in ('ok','partial') or access.get('read_level') not in ('full_text','visible_excerpt'):
                    err('unread_evidence',path,'Search snippets and inaccessible pages cannot support a script claim')
                if not evidence['locator'] or not evidence['observed_summary']:
                    err('missing_locator',path,'Observed evidence needs a usable locator and summary')
    visiting,visited=set(),set()
    def walk(cid):
        if cid in visiting:err('dependency_cycle','claims.'+cid,'Cyclic explanation dependencies');return
        if cid in visited or cid not in tables['claims']:return
        visiting.add(cid)
        for dep in tables['claims'][cid]['depends_on_claim_ids']:walk(dep)
        visiting.remove(cid);visited.add(cid)
    for cid in tables['claims']:walk(cid)
    # Check the entire reachable graph, including title-only references.
    def allowed_graph(cid,seen):
        if cid in seen or cid not in tables['claims']:return
        seen.add(cid);claim=tables['claims'][cid]
        if claim.get('allowed_in_script') is not True or claim.get('support_status') not in ('supported','attributed_only'):
            err('unsupported_dependency','claims.'+cid,'Every used dependency must be supported and allowed')
        for dep in claim['depends_on_claim_ids']:allowed_graph(dep,seen)
    used_ids=list(smap.get('title_claim_ids',[]))
    for sentence in tables['sentences'].values():used_ids.extend(sentence['claim_ids'])
    for cid in used_ids:allowed_graph(cid,set())
    for mid,metric in tables['metrics'].items():
        path='metrics.'+mid;story_ref(metric,path)
        derived=metric.get('derived') or {}
        if derived.get('eligible') is True:
            calculated=derive_metric(metric)
            if not calculated['eligible']:err('invalid_metric',path,'Derived metric lacks comparable data')
            else:
                unit=derived.get('unit')
                if unit=='percent_reduction':expected=-calculated['relative_change_percent']
                elif unit in ('percent_change','percent_increase','relative_change_percent'):expected=calculated['relative_change_percent']
                elif unit=='percentage_points':expected=calculated['percentage_points']
                else:expected=None
                value=derived.get('value')
                if expected is None or isinstance(value,bool) or not isinstance(value,(int,float)) or abs(value-expected)>0.000001:
                    err('incorrect_metric',path,'Derived value/unit does not match comparable inputs')
        elif derived.get('value') is not None:err('invalid_metric',path,'Ineligible metric must have null derived value')
        for part in ('baseline','outcome'):
            if isinstance(metric.get(part),dict):refs(metric[part].get('source_ids',[]),'sources',path+'.'+part)
    for caseid,case in tables['enterprise_cases'].items():
        path='enterprise_cases.'+caseid;story_ref(case,path)
        enum(case['deployment_status'],['deployed','pilot','demo','proposed','unknown'],path+'.deployment_status')
        enum(case['evidence_basis'],['self_reported','independently_supported','mixed','unknown'],path+'.evidence_basis')
        refs(case['claim_ids'],'claims',path+'.claim_ids');refs(case['metric_ids'],'metrics',path+'.metric_ids')
        refs(case['independently_supported_claim_ids'],'claims',path+'.independently_supported_claim_ids')
        if case['evidence_basis'] in ('independently_supported','mixed') and not case['independently_supported_claim_ids']:
            err('independence_unspecified',path,'Identify exactly which claims have independent support')
    refs(smap.get('title_claim_ids',[]),'claims','script_map.title_claim_ids')
    if not isinstance(smap['title'],str) or not smap['title'].strip():err('empty_title','script_map.title','Title required')
    for cid in smap.get('title_claim_ids',[]):
        if cid in tables['claims'] and not tables['claims'][cid]['allowed_in_script']:
            err('unsupported_claim','script_map.title_claim_ids','Title uses disallowed claim')
    last=-1
    for sentenceid,sentence in tables['sentences'].items():
        path='sentences.'+sentenceid
        enum(sentence['sentence_kind'],['factual','attributed','interpretive','rhetorical','mixed'],path+'.sentence_kind')
        refs(sentence['claim_ids'],'claims',path+'.claim_ids')
        if sentence['sentence_kind']!='rhetorical' and not sentence['claim_ids']:
            err('unmapped_sentence',path,'Substantive sentence needs claims')
        if sentence['required_qualifiers_present'] is not True:err('missing_qualifier',path,'Review required qualifiers')
        for cid in sentence['claim_ids']:
            claim=tables['claims'].get(cid)
            if claim and not claim['allowed_in_script']:err('unsupported_claim',path,'Sentence uses a disallowed claim')
        pi=sentence['paragraph_index']
        if isinstance(pi,bool) or not isinstance(pi,int) or pi<0 or pi<last:
            err('invalid_paragraph',path,'Paragraph indices must be nonnegative and ordered')
        else:last=pi
        if not isinstance(sentence['text'],str) or not sentence['text'].strip():err('empty_sentence',path,'Missing text')
    checks=smap['checks']
    if not isinstance(checks,dict):err('invalid_type','script_map.checks','Expected object')
    else:
        for key in CHECKS:
            enum(checks.get(key),['pass','fail','not_run','not_applicable'],'script_map.checks.'+key)
            if final and checks.get(key)!='pass':err('review_incomplete','script_map.checks.'+key,'Final output requires completed review')
        if not isinstance(checks.get('actual_audio_listened'),bool):err('invalid_type','script_map.checks.actual_audio_listened','Expected boolean')
    if final:
        if not selected or not tables['sentences']:err('empty_output','script_map','No selected story or complete script')
        if run['status'] not in ('reviewed','saved','delivered'):err('not_reviewed','run.status','Final output must be reviewed')
    if run['schema_version']=='1.1':
        from practical_contract import validate_practical
        errors.extend(validate_practical(bundle,final=final))
    from editorial_contract import validate_editorial
    errors.extend(validate_editorial(bundle,final=final))
    return errors


def load_bundle(directory):
    root=Path(directory)
    return {key:json.loads((root/(key+'.json')).read_text(encoding='utf-8')) for key in TOP}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory');p.add_argument('--final',action='store_true')
    args=p.parse_args()
    try:
        errors=validate_bundle(load_bundle(args.directory),final=args.final)
    except (OSError,ValueError) as exc:
        p.exit(2, 'Cannot load record bundle: '+str(exc)+'\n')
    print(json.dumps(dict(valid=not errors,errors=errors,semantic_guarantee=False,legacy_records_are_not_practical_gate_acceptance=True),ensure_ascii=False,indent=2))
    raise SystemExit(1 if errors else 0)


if __name__=='__main__':main()
