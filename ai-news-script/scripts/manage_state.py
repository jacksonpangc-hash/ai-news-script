"""Budget/state and workspace-local storage. No network, installations or publishing."""
import argparse
from contextlib import contextmanager
import copy
from datetime import datetime, timedelta, timezone as dt_timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
import uuid
from zoneinfo import ZoneInfo
from normalize_records import iso, utc
from validate_records import CHECKS, STATES, load_bundle, validate_bundle

ASSETS=Path(__file__).resolve().parents[1]/'assets'
SAFE_ID=re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}$')
DURABLE_KEYS={'language','audience','duration_seconds','target_characters','style_profile_id','timezone'}
TERMINAL={'delivered','blocked','failed','canceled'}


def default_config():
    return json.loads((ASSETS/'config.default.json').read_text(encoding='utf-8'))


def resolve_config(preferences=None,overrides=None):
    defaults=default_config();config=copy.deepcopy(defaults)
    for key,value in (preferences or {}).items():
        if key not in DURABLE_KEYS:raise ValueError('Unsupported durable preference')
        config[key]=copy.deepcopy(value)
    for key,value in (overrides or {}).items():
        if key not in config:raise ValueError('Unknown config key: '+key)
        config[key]=copy.deepcopy(value)
    for key in [k for k in defaults if k.startswith('max_')]+['lookback_days']:
        val=config[key]
        if isinstance(val,bool) or not isinstance(val,int) or val<0:raise ValueError('Invalid nonnegative config integer: '+key)
    if not 0<config['lookback_days']<=config['max_lookback_days']<=30:
        raise ValueError('News window must be 1..30 days')
    for key in ('strict_window','save_history','allow_evergreen_fallback','new_paid_providers','retain_raw_pages'):
        if not isinstance(config[key],bool):raise ValueError('Expected boolean: '+key)
    if config['new_paid_providers']:raise ValueError('This implementation does not provision paid providers')
    if config.get('task_execution_policy') != 'required_v1':
        raise ValueError('Task execution evidence policy cannot be disabled')
    if config.get('sepia_policy')!='embedded_review_v1' or config.get('editorial_policy') not in ('audience_problem_v15','ai_business_value_v16'):
        raise ValueError('Editorial evidence policy cannot be disabled')
    if not isinstance(config.get('default_non_mainland_fallback'),bool):
        raise ValueError('Expected explicit default region fallback boolean')
    from region_policy import SCOPES
    if config.get('region_scope') not in SCOPES or config.get('region_policy')!='mainland_first_v1' or config.get('builder_feed_policy')!='supplementary_v1':
        raise ValueError('Invalid region or supplementary discovery policy')
    if config['topic_scope'] not in ('practical_cases','both','frontier_only','enterprise_only'):
        raise ValueError('Unknown topic scope')
    for key in ('duration_seconds','target_characters','reference_characters_per_minute'):
        vals=config[key]
        if not isinstance(vals,list) or len(vals)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or v<=0 for v in vals) or vals[0]>vals[1]:
            raise ValueError('Expected positive ordered pair: '+key)
    if config['timezone']:ZoneInfo(config['timezone'])
    return config


def new_run(request, *, now=None, timezone=None, preferences=None, overrides=None, parent_run_id=None):
    config=resolve_config(preferences,overrides)
    actual=utc(now) if now else datetime.now(dt_timezone.utc)
    zone=config['timezone'] or timezone or 'Etc/UTC';ZoneInfo(zone)
    rid=actual.strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
    from discovery import blank_routes
    from loaded_identity import read_identity
    return dict(schema_version='1.1',run_id=rid,loaded_identity=read_identity(),
        request=dict(text=request,language=config['language'],audience=config['audience'],
                     topic_scope=config['topic_scope'],strict_window=config['strict_window'],
                     region_scope=config['region_scope'],region_scope_reason='默认大陆优先' if config['region_scope']=='mainland_preferred' else '用户明确覆盖默认范围，具体要求见request.text',
                     duration_seconds=config['duration_seconds'],style_profile_id=config['style_profile_id'],parent_run_id=parent_run_id,research_mode='full'),
        time_context=dict(now_utc=iso(actual),effective_timezone=zone,
                          timezone_origin='explicit_config' if config['timezone'] else ('host' if timezone else 'explicit_fallback'),
                          window_start_utc=iso(actual-timedelta(days=config['lookback_days'])),window_end_utc=iso(actual),
                          window_type='rolling_days',lookback_days_used=config['lookback_days'],expanded=False,content_mode='recent_news'),
        config=config,capabilities=dict(search_web='not_checked',open_source='not_checked',local_storage='not_checked',
                                      host_name=None,adapter_verified=False),
        budget=dict(search_calls_used=0,open_calls_used=0,rewrite_passes_used=0,retries_by_source={},exhausted=False),
        status='initialized',outcome=None,
        coverage=dict(frontier='not_searched',enterprise='not_searched',blocked_source_ids=[],limitations=[]),
        errors=[],output=dict(selected_story_ids=[],script_path=None,sources_path=None,history_saved=False,
                             duration_estimate_seconds=None,duration_method='not_estimated'),
        discovery_routes=blank_routes(),tool_log=[],checkpoint_revision=0,
        region_review=dict(mainland_result='not_attempted',fallback_reason=None,expansion_decision='not_needed',expansion_reason=None))


def transition(run,status,reason=None):
    current=run['status']
    if current in TERMINAL:raise ValueError('Terminal run cannot restart; create a child revision')
    normal=STATES[:12]
    if status in ('blocked','failed','canceled'):
        run.update(status=status,outcome=status)
        if reason:run['errors'].append(dict(stage=current,code=reason,source_id=None,retryable=False,attempt=0,message=reason))
        return
    if status not in normal or normal.index(status)!=normal.index(current)+1:
        raise ValueError('Invalid state transition')
    run['status']=status
    if status=='delivered':
        run['outcome']='delivered_with_limits' if run['coverage']['limitations'] else 'delivered'


def consume(run,kind,*,count=1,source_id=None,retry=False,block_reason=None):
    """Reserve BEFORE invoking real tools, including failed calls and each batch item."""
    if run['status'] in TERMINAL:raise ValueError('No calls after termination')
    if isinstance(count,bool) or not isinstance(count,int) or count<1:raise ValueError('Count must be a positive integer')
    if kind not in ('search','open','rewrite'):raise ValueError('Unknown budget kind')
    if retry and block_reason in ('login','captcha','paywall','forbidden','not_found','permission_denied'):
        raise ValueError('Permanent access restrictions must not be retried or bypassed')
    budget,config=run['budget'],run['config']
    used_key={'search':'search_calls_used','open':'open_calls_used','rewrite':'rewrite_passes_used'}[kind]
    max_key={'search':'max_search_calls','open':'max_open_calls','rewrite':'max_rewrite_passes'}[kind]
    if budget[used_key]+count>config[max_key]:
        budget['exhausted']=True;raise ValueError('budget_exhausted: '+kind)
    if retry:
        if not source_id:raise ValueError('Retry requires a source identity')
        previous=budget['retries_by_source'].get(source_id,0)
        if previous+count>config['max_retries_per_source']:raise ValueError('source_retry_limit')
        budget['retries_by_source'][source_id]=previous+count
    budget[used_key]+=count


def expand_window(run,*,evergreen=False):
    config,tc=run['config'],run['time_context']
    if config.get('strict_window') or run['request'].get('strict_window'):raise ValueError('Strict window')
    if evergreen:
        if not config['allow_evergreen_fallback']:raise ValueError('Evergreen requires explicit permission')
        tc['content_mode']='evergreen';return
    tc.update(window_start_utc=iso(utc(tc['window_end_utc'])-timedelta(days=config['max_lookback_days'])),
              lookback_days_used=config['max_lookback_days'],expanded=True,content_mode='expanded_window')


def _identifier(value):
    if not isinstance(value,str) or not SAFE_ID.fullmatch(value):raise ValueError('Unsafe local identifier')
    return value


def safe_path(workspace,*parts):
    root=Path(workspace).resolve(strict=True)
    if not root.is_dir():raise ValueError('Workspace must be a directory')
    p=root
    for part in parts:
        _identifier(part);p=p/part
        if p.is_symlink():raise ValueError('Symlink in runtime path refused')
    if not p.resolve().is_relative_to(root):raise ValueError('Runtime path escapes workspace')
    return p


def profile_path(workspace,profile):
    root=Path(workspace).resolve(strict=True)
    wid=hashlib.sha256(os.fsencode(str(root))).hexdigest()[:16]
    return safe_path(root,'runtime','ai-news-script',wid,_identifier(profile))


def _check_file(path):
    if path.is_symlink():raise ValueError('Symlink file refused')


def atomic_json(path,data):
    path=Path(path);_check_file(path)
    # Callers pass a directory checked under the workspace boundary.
    fd,tmp=tempfile.mkstemp(prefix='.tmp-',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as out:
            json.dump(data,out,ensure_ascii=False,indent=2,allow_nan=False);out.write('\n');out.flush();os.fsync(out.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


@contextmanager
def profile_lock(path):
    path.mkdir(parents=True,exist_ok=True)
    lock=path/'.write-lock';deadline=time.monotonic()+5
    while True:
        try:lock.mkdir();break
        except FileExistsError:
            if time.monotonic()>deadline:raise ValueError('Profile busy; retry after inspecting the interrupted writer')
            time.sleep(.02)
    try:yield
    finally:lock.rmdir()


def _load_versioned(path,default):
    _check_file(path)
    if not path.exists():return copy.deepcopy(default)
    obj=json.loads(path.read_text(encoding='utf-8'))
    if obj.get('schema_version') not in ('1.0','1.1'):raise ValueError('Unknown schema version; refusing rewrite')
    return obj


def load_preferences(workspace,profile):
    path=profile_path(workspace,profile)/'preferences.json'
    obj=_load_versioned(path,dict(schema_version='1.0',profile_id=profile,preferences=[]))
    if obj['profile_id']!=profile:raise ValueError('Preference profile mismatch')
    return {p['key']:p['value'] for p in obj['preferences'] if p.get('scope')=='durable'}


def save_preference(workspace,profile,key,value,*,explicit=False,authorization_summary=None,save_history=True):
    if not save_history or not explicit:return False
    if key not in DURABLE_KEYS or not authorization_summary:raise ValueError('Explicit durable preference authorization required')
    resolve_config(preferences={key:value})
    path=profile_path(workspace,profile)
    with profile_lock(path):
        file=path/'preferences.json'
        obj=_load_versioned(file,dict(schema_version='1.0',profile_id=profile,preferences=[],revision=0))
        if obj['profile_id']!=profile:raise ValueError('Preference profile mismatch')
        obj['preferences']=[p for p in obj['preferences'] if p['key']!=key]
        obj['preferences'].append(dict(key=key,value=value,scope='durable',authorized_at=iso(datetime.now(dt_timezone.utc)),
                                       authorization_summary=authorization_summary))
        obj['revision']=obj.get('revision',0)+1
        atomic_json(file,obj)
    return True


def load_history(workspace,profile):
    return _load_versioned(profile_path(workspace,profile)/'event_history.json',dict(schema_version='1.0',revision=0,events=[]))


def repeat_allowed(story,history,*,repeat_requested=False):
    key=story['canonical_event_key']
    match=any(key==event['canonical_event_key'] or key in event.get('aliases',[]) for event in history['events'])
    if not match or repeat_requested:return True
    update=story.get('material_update') or {}
    return bool(update.get('description') and update.get('new_claim_ids') and update.get('source_ids'))


def save_checkpoint(workspace,profile,run):
    """One atomic run snapshot; no page bodies. Can be resumed without re-spending calls."""
    if not run['config']['save_history']:return None
    path=profile_path(workspace,profile)
    with profile_lock(path):
        pending=path/'pending';_check_file(pending);pending.mkdir(exist_ok=True)
        target=pending/(_identifier(run['run_id'])+'.json')
        old=_load_versioned(target,dict(schema_version='1.0'))
        if old.get('status') in TERMINAL:raise ValueError('Terminal checkpoint is immutable')
        revision=old.get('checkpoint_revision',0)
        if run.get('checkpoint_revision',0)!=revision:
            raise ValueError('Checkpoint conflict; reload latest state before resuming')
        for key in ('search_calls_used','open_calls_used','rewrite_passes_used'):
            if run['budget'][key]<old.get('budget',{}).get(key,0):raise ValueError('Spent budget cannot be reduced')
        for sid,count in old.get('budget',{}).get('retries_by_source',{}).items():
            if run['budget']['retries_by_source'].get(sid,0)<count:raise ValueError('Retry count cannot be reduced')
        saved=copy.deepcopy(run);saved['checkpoint_revision']=revision+1
        atomic_json(target,saved)
        run['checkpoint_revision']=revision+1
    return target


def save_bundle(workspace,profile,bundle):
    run=bundle['run']
    if not run['config']['save_history']:return None
    errors=validate_bundle(bundle,final=True)
    if errors:raise ValueError(json.dumps(errors,ensure_ascii=False))
    from render_output import render
    output=render(bundle)
    path=profile_path(workspace,profile)
    with profile_lock(path):
        runs=path/'runs';_check_file(runs);runs.mkdir(exist_ok=True)
        target=runs/_identifier(run['run_id']);_check_file(target)
        if target.exists():raise FileExistsError('Run already saved; create a child revision')
        staging=Path(tempfile.mkdtemp(prefix='.staging-',dir=runs))
        try:
            saved=copy.deepcopy(bundle)
            saved['run']['status']='saved';saved['run']['outcome']=None
            saved['run']['output'].update(script_path=str(target/'script.md'),sources_path=str(target/'sources.md'),
                                          history_saved=False,duration_estimate_seconds=output['duration_estimate_seconds'],
                                          duration_method=output['duration_method'])
            for key,obj in saved.items():
                if key not in ('run','sources','stories','fact_cards','script_map'):raise ValueError('Unknown bundle component')
                atomic_json(staging/(key+'.json'),obj)
            (staging/'script.md').write_text(output['script'],encoding='utf-8')
            (staging/'sources.md').write_text(output['sources'],encoding='utf-8')
            os.rename(staging,target)
        except BaseException:
            shutil.rmtree(staging);raise
    return target


def record_delivery(workspace,profile,run_id):
    """Call only after actual user-visible delivery; does not itself deliver anything."""
    path=profile_path(workspace,profile)
    with profile_lock(path):
        root=path/'runs'/_identifier(run_id)
        safe_path(workspace,'runtime','ai-news-script',path.parent.name,profile,'runs',run_id)
        for key in ('run','sources','stories','fact_cards','script_map'):_check_file(root/(key+'.json'))
        bundle=load_bundle(root);run=bundle['run']
        if not run['config']['save_history']:return False
        if run['status'] not in ('saved','delivered'):raise ValueError('Only saved output may enter delivered history')
        errors=validate_bundle(bundle,final=True)
        if errors:raise ValueError(json.dumps(errors,ensure_ascii=False))
        history=load_history(workspace,profile)
        changed=False
        for story in bundle['stories']['stories']:
            if story['story_id'] not in bundle['stories']['selected_story_ids']:continue
            event=next((e for e in history['events'] if e['canonical_event_key']==story['canonical_event_key'] or
                        story['canonical_event_key'] in e.get('aliases',[])),None)
            if event is None:
                event=dict(canonical_event_key=story['canonical_event_key'],event_identity=story['event_identity'],
                           last_delivered_at=None,delivered_run_ids=[],angles_used=[],material_updates=[],aliases=[])
                history['events'].append(event)
            if run_id in event['delivered_run_ids']:continue
            changed=True;event['last_delivered_at']=iso(datetime.now(dt_timezone.utc));event['delivered_run_ids'].append(run_id)
            if story['angle'] not in event['angles_used']:event['angles_used'].append(story['angle'])
            if story.get('material_update'):event['material_updates'].append({**story['material_update'],'run_id':run_id})
        if changed:
            history['revision']+=1;atomic_json(path/'event_history.json',history)
        # Idempotent recovery if a crash occurred after history replace and before run replace.
        run.update(status='delivered',outcome='delivered_with_limits' if run['coverage']['limitations'] else 'delivered')
        run['output']['history_saved']=True;atomic_json(root/'run.json',run)
    return True


def revise_paragraph(bundle,index,replacements):
    clone=copy.deepcopy(bundle)
    run=clone['run'];old_id=run['run_id']
    if not any(s['paragraph_index']==index for s in clone['script_map']['sentences']):raise ValueError('Paragraph not found')
    if not replacements or any(s['paragraph_index']!=index for s in replacements):raise ValueError('Only replace the target paragraph')
    run['run_id']=datetime.now(dt_timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
    run['request']['parent_run_id']=old_id;run['status']='drafted';run['outcome']=None
    run['output'].update(script_path=None,sources_path=None,history_saved=False)
    for obj in clone.values():obj['run_id']=run['run_id']
    sentences=clone['script_map']['sentences'];start=next(i for i,s in enumerate(sentences) if s['paragraph_index']==index)
    kept=[s for s in sentences if s['paragraph_index']!=index]
    clone['script_map']['sentences']=kept[:start]+copy.deepcopy(replacements)+kept[start:]
    clone['script_map']['revision']+=1
    for check in CHECKS:clone['script_map']['checks'][check]='not_run'
    clone['script_map']['checks']['issues']=['Target paragraph changed; recheck affected claims and global consistency']
    consume(run,'rewrite')
    return clone


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='action',required=True)
    init=sub.add_parser('init',help='Emit initial run JSON to stdout; no disk writes')
    init.add_argument('--request',required=True);init.add_argument('--timezone');init.add_argument('--no-save',action='store_true')
    for action in ('save','delivered'):
        cmd=sub.add_parser(action);cmd.add_argument('--workspace',required=True);cmd.add_argument('--profile',default='default')
        cmd.add_argument('directory' if action=='save' else 'run_id')
    args=p.parse_args()
    try:
        if args.action=='init':
            print(json.dumps(new_run(args.request,timezone=args.timezone,overrides={'save_history':not args.no_save}),ensure_ascii=False,indent=2))
        elif args.action=='save':print(save_bundle(args.workspace,args.profile,load_bundle(args.directory)) or 'not_saved')
        else:print(record_delivery(args.workspace,args.profile,args.run_id))
    except (ValueError,OSError) as exc:p.exit(2,str(exc)+'\n')


if __name__=='__main__':main()
