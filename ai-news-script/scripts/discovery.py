"""Read three public JSON feeds as leads. Does not execute repository code or verify claims."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import urllib.request
from urllib.parse import urlsplit
from normalize_records import date_status,iso,utc

FEED_URLS=tuple(f'https://raw.githubusercontent.com/zarazhangrui/follow-builders/main/feed-{name}.json'
                for name in ('x','blogs','podcasts'))


def blank_routes():
    return dict(builder_feed=dict(status='not_attempted',feeds=[dict(url=url,status='not_attempted',generated_at=None,
        items_count=None,window_items_count=None,qualified_items_count=None,attempt_ids=[],error=None) for url in FEED_URLS]),
        official_case_search=dict(status='not_attempted',attempt_ids=[]))


def parse_feed(data,url,observed_at,window_start,window_end,stale_hours=48,lead_limit=40):
    if url not in FEED_URLS or not isinstance(data,dict):raise ValueError('Unsupported feed or JSON object')
    name=Path(urlsplit(url).path).stem.removeprefix('feed-')
    collection=data.get(name)
    if not isinstance(collection,list):raise ValueError('Missing named feed collection: '+name)
    generated=data.get('generatedAt')
    try:age=(utc(observed_at)-utc(generated)).total_seconds()/3600
    except (ValueError,TypeError,AttributeError):raise ValueError('Missing/invalid generatedAt')
    if age<0:raise ValueError('Future feed generation timestamp')
    items=[]
    for group in collection:
        if not isinstance(group,dict):raise ValueError('Invalid feed item')
        if name=='x':
            nested=group.get('tweets')
            if not isinstance(nested,list):raise ValueError('X author has no tweets array')
        else:
            nested=next((group[k] for k in ('articles','posts','entries') if k in group),[group])
            if not isinstance(nested,list):raise ValueError('Invalid nested collection')
        for item in nested:
            if not isinstance(item,dict):raise ValueError('Invalid nested item')
            items.append((group,item))
    leads=[];window_count=0;unknown_dates=0
    for author,item in items:
        published=item.get('createdAt') or item.get('publishedAt') or item.get('pubDate') or item.get('date')
        precision='date' if isinstance(published,str) and len(published)==10 else 'timestamp'
        try:in_window=date_status(dict(value=published,precision=precision,timezone=None),window_start,window_end)
        except (ValueError,TypeError,AttributeError):in_window='unknown'
        if not published:in_window='unknown'
        if in_window=='unknown':unknown_dates+=1
        if in_window not in ('supported','ambiguous'):continue
        window_count+=1
        if len(leads)>=lead_limit:continue
        target=item.get('url') or item.get('link')
        if not isinstance(target,str):target=None
        text=item.get('text') or item.get('description') or item.get('summary') or ''
        title=item.get('title') or text[:100] or 'Untitled feed lead'
        specific=bool(target)
        if target:
            parts=urlsplit(target)
            if 'youtube.com' in parts.netloc and (parts.path.endswith('/videos') or parts.path.startswith('/@')):specific=False
        leads.append(dict(lead_id='lead_'+hashlib.sha256((url+'|'+str(item.get('id') or item.get('guid') or target)+str(published)).encode()).hexdigest()[:12],
            discovery_channel='builder_feed',feed_url=url,url=target,title=str(title)[:180],summary=str(text)[:500],
            published_at=dict(value=published,precision=precision,timezone=None),date_status=in_window,
            author=author.get('name') or author.get('handle'),specific_document=specific,
            evidence_role='lead_only_requires_original_document'))
    return dict(url=url,status='stale' if age>stale_hours else ('ok_empty' if not items else 'ok'),
        generated_at=generated,observed_at=observed_at,items_count=len(items),author_count=len(collection) if name=='x' else None,
        window_items_count=window_count,unknown_date_count=unknown_dates,qualified_items_count=None,
        qualification_note='Agent must screen actual application evidence; parser does not decide usefulness',
        leads=leads,omitted_window_items=max(0,window_count-len(leads)),error=None)


def read_public_json(url):
    if url not in FEED_URLS:raise ValueError('Only configured public feed URLs are accepted')
    request=urllib.request.Request(url,headers={'User-Agent':'ai-news-script/1.1 public-json-reader'})
    with urllib.request.urlopen(request,timeout=20) as response:
        content=response.read(4*1024*1024+1)
    if len(content)>4*1024*1024:raise ValueError('Public feed exceeds 4 MiB read limit')
    return json.loads(content.decode('utf-8'))


def discover(run,reader=read_public_json,before_call=None,urls=None):
    from manage_state import consume
    from region_policy import mainland_searches
    if run['config'].get('builder_feed_policy')=='supplementary_v1' and run['request'].get('region_scope') in ('mainland_preferred','mainland_only') and len({x['search_angle'] for x in mainland_searches(run)})<2:
        raise ValueError('mainland_search_required: supplemental feeds follow two mainland search angles')
    selected=set(FEED_URLS if urls is None else urls)
    if not selected.issubset(FEED_URLS):raise ValueError('Unsupported supplemental feed URL')
    routes=run.setdefault('discovery_routes',blank_routes());route=routes['builder_feed']
    for index,url in enumerate(FEED_URLS):
        entry=route['feeds'][index]
        if url not in selected:continue
        if entry.get('status')!='not_attempted':continue
        try:consume(run,'open')
        except ValueError:
            entry['error']='budget_exhausted';continue
        call_id='call_feed_'+str(len(run['tool_log'])+1)
        timestamp=iso(datetime.now(timezone.utc))
        log=dict(call_id=call_id,kind='open',discovery_channel='builder_feed',url=url,outcome='reserved',timestamp=timestamp,
                 source_id='src_feed_'+Path(urlsplit(url).path).stem.removeprefix('feed-'),lead_id=None,fallback_of=None)
        run['tool_log'].append(log);entry['attempt_ids'].append(call_id)
        if before_call:before_call(run)
        try:
            data=reader(url)
            parsed=parse_feed(data,url,timestamp,run['time_context']['window_start_utc'],run['time_context']['window_end_utc'],
                              run['config'].get('feed_stale_hours',48),run['config'].get('feed_lead_limit',40))
            entry.update(parsed);log['outcome']='json_parsed'
        except (OSError,ValueError,TypeError) as exc:
            entry.update(status='failed',observed_at=timestamp,error=type(exc).__name__+': '+str(exc)[:180])
            log['outcome']='read_or_parse_failed'
    statuses=[f['status'] for f in route['feeds']]
    route['status']='ok' if all(s in ('ok','ok_empty') for s in statuses) else 'limited'
    if route['status']=='limited':
        note='部分builder feed未读取、解析失败或生成时间陈旧；具体状态见discovery_routes'
        if note not in run['coverage']['limitations']:run['coverage']['limitations'].append(note)
    return route


def skip_feeds(run,reason):
    """Mark remaining unrequested feeds honestly; does not spend budget or claim reads."""
    from region_policy import SKIP_REASONS
    if run['config'].get('builder_feed_policy')!='supplementary_v1' or reason not in SKIP_REASONS:
        raise ValueError('Unsupported policy skip')
    route=run['discovery_routes']['builder_feed']
    for f in route['feeds']:
        if f.get('status')=='not_attempted' and not f.get('attempt_ids'):
            f.update(status='not_enabled',skip_reason=reason,error=None)
    statuses=[f['status'] for f in route['feeds']]
    route['status']='not_enabled' if all(s=='not_enabled' for s in statuses) else ('ok' if all(s in ('ok','ok_empty','not_enabled') for s in statuses) else 'limited')
    if route['status'] in ('ok','not_enabled'):
        note='部分builder feed未读取、解析失败或生成时间陈旧；具体状态见discovery_routes'
        run['coverage']['limitations']=[x for x in run['coverage']['limitations'] if x!=note]
    return route


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True,help='Checkpoint JSON, or - for session-only JSON from stdin')
    p.add_argument('--workspace');p.add_argument('--profile',default='default');args=p.parse_args()
    run=json.load(sys.stdin) if args.run=='-' else json.loads(Path(args.run).read_text(encoding='utf-8'))
    if run['config']['save_history'] and not args.workspace:p.error('Saved mode requires an authorized workspace')
    from manage_state import save_checkpoint
    checkpoint=(lambda r:save_checkpoint(args.workspace,args.profile,r)) if run['config']['save_history'] else None
    result=discover(run,before_call=checkpoint)
    if checkpoint:checkpoint(run)
    print(json.dumps(dict(run=run,discovery=result),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
