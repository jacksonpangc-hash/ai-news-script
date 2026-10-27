"""v1.5 evidence slots. Structural validation cannot prove reading or writing quality."""
import re

BASE={'SKILL.md','references/professional-pass.md','references/style-pass.md',
      'references/languages/zh.md','references/voice-skills.md'}


def validate_editorial(bundle,final=False):
    r=bundle['run'];errors=[]
    if r['config'].get('sepia_policy')!='embedded_review_v1':return errors
    def err(code,message):errors.append(dict(code=code,path='script_map.sepia_review',message=message))
    def text(x):return isinstance(x,str) and bool(x.strip())
    identity=r.get('loaded_identity',{})
    if not (identity.get('name')=='ai-news-script' and text(identity.get('version'))
            and text(identity.get('entry_path')) and text(identity.get('package_id'))
            and re.fullmatch('[0-9a-f]{64}',identity.get('entry_sha256',''))
            and identity.get('verification')=='actual_entry_bytes'):
        err('loaded_identity_missing','Record the actual entry bytes, version, path and package identity')
    if identity.get('expected_version') not in (None,identity.get('version')):
        err('loaded_version_mismatch','Requested and loaded versions differ')
    if not final:return errors
    sm=bundle['script_map'];review=sm.get('sepia_review')
    if not isinstance(review,dict):err('sepia_review_missing','Record the actual Sepia read and editorial pass');return errors
    required=set(BASE)
    route=review.get('route')
    if route not in ('business_explainer','news_report','case_narrative'):
        err('sepia_route','Choose the actual non-fiction venue')
    if route in ('news_report','case_narrative'):required.add('references/domains/journalism.md')
    loaded=review.get('loaded_references',[])
    if not isinstance(loaded,list):loaded=[]
    read=set()
    for x in loaded:
        if not isinstance(x,dict):continue
        path=x.get('path','')
        if path.startswith('vendor/sepia/') and text(x.get('sections')) and text(x.get('read_at')) and re.fullmatch('[0-9a-f]{64}',x.get('sha256','')):
            read.add(path[len('vendor/sepia/'):])
    if not required.issubset(read):err('sepia_reads_missing','Record actual reads of the canonical and applicable embedded references')
    if not text(review.get('venue_basis')) or review.get('verdict') not in ('clean','isolated_hits','cluster'):
        err('sepia_review_incomplete','Record the venue and a concrete review verdict')
    for role in ('author','executor'):
        model=review.get('model',{}).get(role)
        if not (model=='unknown' or (isinstance(model,dict) and text(model.get('family')) and text(model.get('version')))):
            err('sepia_model_identity','Record each model from metadata or unknown, never infer from prose')
        if review.get('prose_layer',{}).get(role) not in ('operative','prior','none'):
            err('sepia_model_identity','Record release-scoped prose-layer applicability')
    findings=review.get('findings')
    if not isinstance(findings,list):err('sepia_review_incomplete','Record the complete defect list before editing');findings=[]
    for x in findings:
        if not isinstance(x,dict) or not all(text(x.get(k)) for k in ('check','quote','finding')) or x.get('action') not in ('retain','refactor','recreate','deferred'):
            err('sepia_review_incomplete','Each finding needs actual quoted text and a specific action')
        elif x['action'] in ('refactor','recreate') and not all(text(x.get(k)) for k in ('before','after')):
            err('sepia_change_missing','Keep the concrete before/after for an applied edit')
    if not findings and not text(review.get('clean_basis')):err('sepia_review_incomplete','Explain a clean result rather than inventing edits')
    count=review.get('rewrite_count')
    if isinstance(count,bool) or not isinstance(count,int) or count<0 or count>r['budget']['rewrite_passes_used']:
        err('sepia_rewrite_budget','Sepia revisions share the total rewrite budget')
    elif count==0 and any(isinstance(x,dict) and x.get('action') in ('refactor','recreate') for x in findings):
        err('sepia_rewrite_budget','Applied rewrites must be charged')
    recheck=review.get('fact_recheck',{})
    claims={c['claim_id'] for c in bundle['fact_cards']['claims']}
    ids=recheck.get('claim_ids',[])
    if recheck.get('status')!='pass' or not isinstance(ids,list) or not ids or not set(ids).issubset(claims):
        err('sepia_fact_recheck','Recheck edited claims against the existing evidence')
    return errors
