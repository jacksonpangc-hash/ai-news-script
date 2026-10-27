"""v1.1 constraint checks. Editorial findings are evidence records, not quality scores."""
from normalize_records import utc
from discovery import FEED_URLS
from datetime import date,datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo

REVIEW_CHECKS={'actual_value','explanation_chain','natural_expression','fact_fidelity'}


def _date_bounds(record):
    """Preserve date-only uncertainty; compare timestamps in UTC, never lexically."""
    if record.get('precision')=='timestamp':
        instant=utc(record['value']);return instant,instant
    if record.get('precision')!='date':raise ValueError('Date precision required')
    d=date.fromisoformat(record['value']);zone=record.get('timezone')
    if zone:
        return (datetime.combine(d,time.min,ZoneInfo(zone)).astimezone(timezone.utc),
                datetime.combine(d+timedelta(days=1),time.min,ZoneInfo(zone)).astimezone(timezone.utc))
    base=datetime.combine(d,time.min,timezone.utc)
    return base-timedelta(hours=14),base+timedelta(days=1,hours=12)


def validate_practical(bundle,final=False):
    errors=[];run=bundle['run'];smap=bundle['script_map']
    claims={c['claim_id']:c for c in bundle['fact_cards']['claims']}
    sources={s['source_id']:s for s in bundle['sources']['sources']}
    sentences={s['sentence_id']:s for s in smap['sentences']}
    def err(code,path,message):errors.append(dict(code=code,path=path,message=message))
    def substantive(text):return isinstance(text,str) and text.strip().lower() not in ('','pass','通过','ok','已检查','已通过')
    def refs(ids,table,path,nonempty=False):
        if not isinstance(ids,list) or (nonempty and not ids):err('missing_reference',path,'Nonempty reference list required');return
        for ident in ids:
            if ident not in table:err('missing_reference',path,'Referenced ID absent')
    selected=bundle['stories']['selected_story_ids']
    for story in bundle['stories']['stories']:
        path='stories.'+story['story_id'];gate=story.get('practical_value_gate')
        if not isinstance(gate,dict) or gate.get('decision') not in ('pass','reject','needs_evidence'):
            err('practical_gate',path,'Explicit practical value decision required');continue
        if not substantive(gate.get('reason')):err('practical_gate',path,'Explain the decision')
        refs(gate.get('claim_ids'),claims,path+'.practical_value_gate.claim_ids',gate['decision']=='pass')
        if gate['decision']!='pass' and story.get('editorial_score') is not None:
            err('practical_gate',path,'Score only after practical gate passes')
        if story['story_id'] not in selected:continue
        if gate['decision']!='pass':err('practical_gate',path,'Selected case must pass practical value gate')
        brief=story.get('value_brief')
        if not isinstance(brief,dict):err('value_brief',path,'Selected case needs value brief');continue
        if run['config'].get('task_execution_policy')=='required_v1':
            execution=brief.get('execution_evidence')
            if not isinstance(execution,dict) or execution.get('kind') not in (
                    'author_execution_report','recorded_execution','local_reproduction') or not substantive(execution.get('summary')):
                err('task_execution_unconfirmed',path,'Actual execution needs its own factual evidence; a paired example is insufficient')
            else:
                ids=execution.get('claim_ids')
                refs(ids,claims,path+'.execution_evidence.claim_ids',True)
                for cid in ids if isinstance(ids,list) else []:
                    claim=claims.get(cid,{})
                    readable=any(
                        sources.get(e.get('source_id'),{}).get('access',{}).get('status') in ('ok','partial') and
                        sources.get(e.get('source_id'),{}).get('access',{}).get('read_level') in ('full_text','visible_excerpt') and
                        e.get('relationship') in ('direct','supporting') for e in claim.get('evidence',[]))
                    if not (readable and claim.get('claim_type')=='fact' and claim.get('allowed_in_script') is True and
                            claim.get('support_status') in ('supported','attributed_only')):
                        err('task_execution_unconfirmed',path,'Execution must cite readable factual evidence, not an inference or illustrative output')
        if brief.get('domain') not in ('daily_life','learning','light_work','personal_creation',
                                       'personal_efficiency','enterprise_efficiency','business_operations','business_model'):
            err('value_brief',path,'Unknown practical domain')
        context=brief.get('application_context')
        if context not in ('actual_use','pilot','demonstration'):
            err('application_not_demonstrated',path,'A feature announcement alone is not a completed task')
        if context=='demonstration':
            demo=brief.get('demonstration_evidence')
            if not isinstance(demo,dict) or not substantive(demo.get('scope_limit')):
                err('demonstration_evidence',path,'Completed public task needs input/output evidence and a scope limit')
            else:
                for key in ('input_claim_ids','output_claim_ids'):
                    ids=demo.get(key)
                    refs(ids,claims,path+'.demonstration_evidence.'+key,True)
                    for cid in ids if isinstance(ids,list) else []:
                        claim=claims.get(cid,{})
                        readable=any(sources.get(e.get('source_id'),{}).get('access',{}).get('read_level')
                                     in ('full_text','visible_excerpt') for e in claim.get('evidence',[]))
                        if not (readable and claim.get('allowed_in_script') is True and
                                claim.get('support_status') in ('supported','attributed_only')):
                            err('demonstration_evidence',path,'Task input/output must link to readable, usable evidence')
        if brief.get('outcome_evidence_type') not in ('quantified','qualitative'):
            err('value_brief',path,'Known outcome evidence type required')
        for section in ('beneficiary_task','before','after','changed_mechanism','result_evidence'):
            part=brief.get(section)
            if not isinstance(part,dict) or not substantive(part.get('text')):
                err('value_brief',path+'.'+section,'Actual task/change/outcome text required');continue
            refs(part.get('claim_ids'),claims,path+'.'+section+'.claim_ids',True)
        cost=brief.get('cost_boundary')
        if not isinstance(cost,dict) or not substantive(cost.get('text')):
            err('value_brief',path+'.cost_boundary','Cost or explicit unknown boundary required')
        else:
            refs(cost.get('claim_ids'),claims,path+'.cost_boundary.claim_ids',cost.get('value') is not None)
            if cost.get('value') is None and cost.get('unknown_reason') not in ('not_disclosed','not_checked','inaccessible','not_applicable'):
                err('value_brief',path+'.cost_boundary','Unknown cost must remain null with reason')
        bridge=story.get('editorial_bridge')
        if not isinstance(bridge,dict) or not substantive(bridge.get('text')):err('editorial_bridge',path,'Write the internal explanatory bridge')
        else:refs(bridge.get('claim_ids'),claims,path+'.editorial_bridge.claim_ids',True)
        if story.get('news_basis')=='recent_disclosure':
            disclosed=story.get('disclosed_at');occurred=story.get('case_occurred_at')
            if not isinstance(disclosed,dict) or story['event_identity'].get('action')!='disclose_case' or story['event_identity']['event_date'].get('value')!=disclosed.get('value'):
                err('disclosure_identity',path,'Recent event identity must actually describe disclosure')
            if isinstance(disclosed,dict):
                refs(disclosed.get('source_ids'),sources,path+'.disclosed_at.source_ids',True)
                try:_date_bounds(disclosed)
                except (ValueError,TypeError,KeyError,AttributeError):err('disclosure_identity',path,'Malformed disclosure date')
            if occurred is not None:
                if not isinstance(occurred,dict):err('disclosure_identity',path,'Case time must be separate date record or null')
                else:
                    refs(occurred.get('source_ids'),sources,path+'.case_occurred_at.source_ids',True)
                    try:
                        low,_=_date_bounds(occurred)
                        if isinstance(disclosed,dict) and low>_date_bounds(disclosed)[1]:
                            err('disclosure_identity',path,'Case execution cannot follow its disclosure')
                    except (ValueError,TypeError,KeyError,AttributeError):err('disclosure_identity',path,'Malformed case or disclosure date')
    if final:
        review=smap.get('review_evidence')
        if not isinstance(review,list):err('review_evidence','script_map','Actual editorial findings required')
        else:
            found=set()
            for item in review:
                if not isinstance(item,dict):err('review_evidence','script_map','Expected finding object');continue
                found.add(item.get('check'))
                refs(item.get('sentence_ids'),sentences,'script_map.review_evidence.sentence_ids',True)
                refs(item.get('basis_claim_ids'),claims,'script_map.review_evidence.basis_claim_ids',True)
                if not substantive(item.get('finding')) or 'change' not in item:
                    err('review_evidence','script_map','Finding must explain actual text and include change/null')
            if not REVIEW_CHECKS.issubset(found):err('review_evidence','script_map','Review all four editorial dimensions')
    mode=run['request'].get('research_mode','full')
    if mode not in ('full','fixed_source_regression','local_revision'):err('discovery_coverage','run.request.research_mode','Unknown research mode')
    if final and mode=='full':
        routes=run.get('discovery_routes',{});logs=run.get('tool_log',[])
        calls={l.get('call_id'):l for l in logs if isinstance(l,dict) and l.get('call_id')}
        if len(calls)!=sum(bool(l.get('call_id')) for l in logs):err('discovery_coverage','run.tool_log','Duplicate call IDs')
        for kind in ('open','search'):
            charged=run['budget'].get(kind+'_calls_used',0)
            if sum(l.get('kind')==kind for l in logs)>charged:
                err('discovery_coverage','run.budget','Logged calls exceed charged budget')
        feed_route=routes.get('builder_feed',{});feeds=feed_route.get('feeds',[])
        if len(feeds)!=3 or {f.get('url') for f in feeds}!=set(FEED_URLS):
            err('discovery_coverage','run.discovery_routes.builder_feed','Three exact public JSON entries required')
        def attempts(entry,route,kind,url=None):
            ids=entry.get('attempt_ids',[])
            if not ids:err('discovery_coverage','run.discovery_routes','Actual attempt link required');return
            for ident in ids:
                call=calls.get(ident)
                if not call or call.get('discovery_channel')!=route or call.get('kind')!=kind or call.get('outcome') in (None,'reserved','not_attempted'):
                    err('discovery_coverage','run.tool_log','Coverage must link to completed actual tool records');continue
                if url and call.get('url')!=url:err('discovery_coverage','run.tool_log','README is not feed JSON consumption')
                if kind=='search' and not substantive(call.get('query')):err('discovery_coverage','run.tool_log','Actual query required')
                try:utc(call['timestamp'])
                except (KeyError,ValueError,AttributeError,TypeError):err('discovery_coverage','run.tool_log','Actual timestamp required')
                if call.get('source_id') is None and call.get('lead_id') is None:err('discovery_coverage','run.tool_log','Source/lead association required')
                if 'fallback_of' not in call:err('discovery_coverage','run.tool_log','Explicit fallback relation/null required')
        limited=False
        for feed in feeds:
            status=feed.get('status')
            if status not in ('ok','ok_empty','failed','stale','not_attempted','not_enabled'):err('discovery_coverage','run.discovery_routes','Invalid feed status')
            if status=='not_enabled':
                from region_policy import SKIP_REASONS
                if run['config'].get('builder_feed_policy')!='supplementary_v1' or feed.get('skip_reason') not in SKIP_REASONS or feed.get('attempt_ids') or any(feed.get(k) is not None for k in ('generated_at','items_count','window_items_count','qualified_items_count','error')):
                    err('discovery_coverage','run.discovery_routes','Policy-disabled feed must have an honest reason, no attempts or claimed results')
                if feed.get('skip_reason')=='mainland_evidence_sufficient' and (run.get('region_review',{}).get('mainland_result')!='qualified' or not any(s.get('case_region',{}).get('value')=='china_mainland' for s in bundle['stories']['stories'] if s['story_id'] in selected)):
                    err('discovery_coverage','run.discovery_routes','Sufficient-mainland skip must agree with review and selected case')
                continue
            if status=='not_attempted':
                limited=True
                if feed.get('attempt_ids') or feed.get('error')!='budget_exhausted' or not run['budget']['exhausted']:
                    err('discovery_coverage','run.discovery_routes','Unattempted feed cannot count as coverage')
                continue
            attempts(feed,'builder_feed','open',feed.get('url'))
            outcomes=[calls.get(i,{}).get('outcome') for i in feed.get('attempt_ids',[])]
            if status in ('ok','ok_empty','stale') and 'json_parsed' not in outcomes:
                err('discovery_coverage','run.discovery_routes','Parsed feed status needs a successful parse record')
            if status=='failed' and (not substantive(feed.get('error')) or 'json_parsed' in outcomes):
                err('discovery_coverage','run.discovery_routes','Failed feed needs error and consistent attempts')
            if status in ('failed','stale'):limited=True
            if status!='failed':
                try:utc(feed['generated_at'])
                except (KeyError,ValueError,AttributeError,TypeError):err('discovery_coverage','run.discovery_routes','Parsed generation timestamp required')
                a,b=feed.get('items_count'),feed.get('window_items_count')
                if any(isinstance(v,bool) or not isinstance(v,int) or v<0 for v in (a,b)) or b>a:
                    err('discovery_coverage','run.discovery_routes','Actual item/window counts required')
                q=feed.get('qualified_items_count')
                if q is not None and (isinstance(q,bool) or not isinstance(q,int) or q<0 or q>b):err('discovery_coverage','run.discovery_routes','Invalid qualified count')
                if q is None and not substantive(feed.get('qualification_note')):err('discovery_coverage','run.discovery_routes','Unknown qualified count needs reason')
                if status=='ok_empty' and a!=0:err('discovery_coverage','run.discovery_routes','Nonempty feed cannot be ok_empty')
        official=routes.get('official_case_search',{})
        attempts(official,'official_case_search','search')
        if official.get('status') not in ('ok','no_qualified_results','failed','limited'):err('discovery_coverage','run.discovery_routes','Record official search result')
        outcomes=[calls.get(i,{}).get('outcome') for i in official.get('attempt_ids',[])]
        success={'results_returned','search_results_returned','no_results'}
        if official.get('status') in ('ok','no_qualified_results') and not any(o in success for o in outcomes):
            err('discovery_coverage','run.discovery_routes','Successful official route requires completed search results')
        if official.get('status') in ('failed','limited'):limited=True
        if official.get('status')=='failed' and any(o in success for o in outcomes):
            err('discovery_coverage','run.discovery_routes','Failed official route contradicts successful attempts')
        if limited and not run['coverage'].get('limitations'):err('discovery_coverage','run.coverage','Coverage gaps must be disclosed')
    from region_policy import validate_region
    errors.extend(validate_region(bundle,final=final))
    return errors
