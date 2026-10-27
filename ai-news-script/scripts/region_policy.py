"""Small source-backed region preference; no inference from names or model brands."""
REGIONS={'china_mainland','hong_kong','macau','taiwan','overseas','unknown'}
SCOPES={'mainland_preferred','mainland_only','overseas_only','global','user_specified'}
SKIP_REASONS={'mainland_evidence_sufficient','user_scope','supplementary_not_needed'}
SUCCESS={'results_returned','search_results_returned','no_results'}


def mainland_searches(run):
    return [x for x in run.get('tool_log',[]) if x.get('kind')=='search'
            and x.get('discovery_channel')=='official_case_search'
            and x.get('region_focus')=='china_mainland' and x.get('outcome') in SUCCESS
            and x.get('query') and x.get('search_angle')]


def validate_region(bundle,final=False):
    r=bundle['run'];errors=[]
    if r['config'].get('region_policy')!='mainland_first_v1':return errors
    def err(code,path,message):errors.append(dict(code=code,path=path,message=message))
    def text(x):return isinstance(x,str) and bool(x.strip())
    scope=r['request'].get('region_scope')
    if scope not in SCOPES:err('region_scope_mismatch','run.request.region_scope','Explicit supported scope required')
    if scope!='mainland_preferred' and not text(r['request'].get('region_scope_reason')):
        err('region_scope_mismatch','run.request.region_scope_reason','Record the explicit user scope override')
    if final and r['request'].get('research_mode','full')=='full' and scope in ('mainland_preferred','mainland_only'):
        searches=mainland_searches(r);all_searches=[x for x in r.get('tool_log',[]) if x.get('kind')=='search']
        prefix=[]
        for x in all_searches:
            if x.get('region_focus')!='china_mainland':break
            if x in searches:prefix.append(x)
        if len({x['search_angle'] for x in prefix})<2 or len({x['query'] for x in prefix})<2:
            err('mainland_search_required','run.tool_log','First two actual searches must cover distinct mainland angles')
    claims={x['claim_id']:x for x in bundle['fact_cards']['claims']};sources={x['source_id']:x for x in bundle['sources']['sources']}
    selected=bundle['stories']['selected_story_ids'];stories=bundle['stories']['stories']
    for s in stories:
        region=s.get('case_region');path='stories.'+s['story_id']+'.case_region'
        if not isinstance(region,dict) or region.get('value') not in REGIONS or not text(region.get('text')):
            err('case_region_evidence',path,'Actual case location or explicit unknown required');continue
        if region['value']=='unknown':
            if region.get('basis_type')!='unknown':err('case_region_evidence',path,'Unknown location must stay unknown')
        else:
            ids=region.get('claim_ids',[])
            if region.get('basis_type') not in ('location_of_use','location_of_user','explicit_case_location') or not isinstance(ids,list) or not ids:
                err('case_region_evidence',path,'Language, publisher, model origin and name are not location evidence')
            for cid in ids if isinstance(ids,list) else []:
                c=claims.get(cid,{})
                readable=any(sources.get(e.get('source_id'),{}).get('access',{}).get('status') in ('ok','partial') and sources.get(e.get('source_id'),{}).get('access',{}).get('read_level') in ('full_text','visible_excerpt') and e.get('relationship') in ('direct','supporting') for e in c.get('evidence',[]))
                if c.get('claim_type')!='fact' or c.get('allowed_in_script') is not True or c.get('support_status') not in ('supported','attributed_only') or not readable:
                    err('case_region_evidence',path,'Known region needs readable factual support')
        if s['story_id'] not in selected:continue
        val=region['value']
        if (scope=='mainland_only' and val!='china_mainland') or (scope=='overseas_only' and val!='overseas'):
            err('region_scope_mismatch',path,'Selected case does not match strict user region')
        review=r.get('region_review',{})
        if scope=='mainland_preferred' and val!='china_mainland':
            if r['config'].get('default_non_mainland_fallback') is False:
                err('default_region_gap',path,'Default domestic evidence gap does not authorize a foreign or unknown filler case')
            decision=review.get('expansion_decision')
            allowed=(decision=='not_useful' or
                     (decision=='strict_window' and (r['request'].get('strict_window') or r['config'].get('strict_window'))) or
                     (decision=='expanded_to_30_days' and r['time_context'].get('expanded')))
            if review.get('mainland_result')!='insufficient' or not text(review.get('fallback_reason')) or not allowed or not text(review.get('expansion_reason')):
                err('region_fallback_unjustified','run.region_review','Record mainland gap, follow-up/window consideration and fallback reason')
            from normalize_records import rank_stories
            if any(x.get('case_region',{}).get('value')=='china_mainland' for x in rank_stories(stories,r['config'].get('min_editorial_score',60))):
                err('region_fallback_unjustified',path,'An eligible mainland case takes priority')
    return errors
