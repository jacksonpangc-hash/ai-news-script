"""Render the reviewed sentence map; never maintain a separate, divergent script."""
import argparse
import json
import math
from zoneinfo import ZoneInfo
from normalize_records import utc
from validate_records import load_bundle, validate_bundle


def render(bundle):
    errors=validate_bundle(bundle,final=True)
    if errors:raise ValueError(json.dumps(errors,ensure_ascii=False))
    run=bundle['run'];smap=bundle['script_map'];tc=run['time_context']
    paragraphs=[];last=None
    for sentence in smap['sentences']:
        if sentence['paragraph_index']!=last:paragraphs.append('');last=sentence['paragraph_index']
        paragraphs[-1]+=sentence['text']
    body='\n\n'.join(paragraphs)
    script='# '+smap['title']+'\n\n'+body+'\n'
    # Follow dependencies to list only evidence actually used in this output.
    claims={c['claim_id']:c for c in bundle['fact_cards']['claims']};used_claims=set()
    def follow(cid):
        if cid in used_claims:return
        used_claims.add(cid)
        for dep in claims[cid]['depends_on_claim_ids']:follow(dep)
    for s in smap['sentences']:
        for cid in s['claim_ids']:follow(cid)
    for cid in smap.get('title_claim_ids',[]):follow(cid)
    used_sources={e['source_id'] for cid in used_claims for e in claims[cid]['evidence']}
    lines=[]
    for src in bundle['sources']['sources']:
        if src['source_id'] not in used_sources:continue
        notes=[e['observed_summary'] for cid in used_claims for e in claims[cid]['evidence'] if e['source_id']==src['source_id']]
        limitation='；仅限实际可见片段' if src['access']['read_level']=='visible_excerpt' else ''
        lines.append('- ['+src['title']+']('+src['canonical_url']+') — '+src['publisher']+'（'+src['source_kind']+'）'+limitation+'。支持：'+'；'.join(dict.fromkeys(notes)))
    tz=ZoneInfo(tc['effective_timezone'])
    fmt=lambda value:utc(value).astimezone(tz).strftime('%Y-%m-%d %H:%M')
    lines+=['','检索截止：'+fmt(tc['window_end_utc'])+' '+tc['effective_timezone']+'。实际窗口：'+fmt(tc['window_start_utc'])+' 至 '+fmt(tc['window_end_utc'])+'。']
    events=[s['event_identity']['event_date'] for s in bundle['stories']['stories'] if s['story_id'] in bundle['stories']['selected_story_ids']]
    lines.append('事件日期：'+'；'.join((d or {}).get('value') or '未知' for d in events)+'。模式：'+str(tc['content_mode'])+'。')
    legacy_execution=run['config'].get('task_execution_policy')!='required_v1'
    if legacy_execution:lines.append('执行证据检查：历史兼容记录，未按当前实际执行证据要求审核。')
    if run['config'].get('region_policy')!='mainland_first_v1':
        lines.append('地区偏好：历史兼容记录，未按1.4大陆优先规则检查。')
    for story in bundle['stories']['stories']:
        brief=story.get('value_brief',{})
        if story['story_id'] in bundle['stories']['selected_story_ids'] and brief.get('application_context')=='demonstration':
            label='历史演示记录，执行状态需复核' if legacy_execution else '有执行依据的公开任务演示'
            lines.append('案例性质：demonstration（'+label+'）。范围：'+brief['demonstration_evidence']['scope_limit'])
    if run['coverage']['limitations']:lines.append('检索与证据限制：'+'；'.join(run['coverage']['limitations'])+'。')
    count=sum(not c.isspace() for c in body)
    speed=run['config'].get('reference_characters_per_minute',[220,280])
    seconds=[math.floor(count/speed[1]*60/10)*10,math.ceil(count/speed[0]*60/10)*10]
    lines.append(f'正文约{count}个可见字符；按编辑参考速度估算约{seconds[0]}–{seconds[1]}秒，未做真人计时或音频听测。')
    if not run['config']['save_history']:lines.append('本次未保存历史；仅在会话中交付。')
    sources='\n'.join(lines)+'\n'
    notice=''
    if tc['content_mode']=='evergreen':notice='没有找到足够可核实的近期信息，以下为非近期新闻的常青解释稿。\n\n'
    elif tc.get('expanded'):notice=f'检索范围已扩展至最近{tc["lookback_days_used"]}天，下面并非仅限最近7天的消息。\n\n'
    if run['config'].get('region_policy')=='mainland_first_v1' and run['request'].get('region_scope')=='mainland_preferred':
        chosen=[s for s in bundle['stories']['stories'] if s['story_id'] in bundle['stories']['selected_story_ids']]
        if chosen and chosen[0]['case_region']['value']!='china_mainland':
            label={'overseas':'海外','hong_kong':'香港','macau':'澳门','taiwan':'台湾','unknown':'地区未明'}.get(chosen[0]['case_region']['value'],'非大陆')
            notice+='本次采用'+label+'案例：'+run['region_review']['fallback_reason']+'。\n\n'
    return dict(script=script,sources=sources,conversation=notice+script+'\n'+sources,
                duration_estimate_seconds=seconds,duration_method='visible_characters_at_editorial_reference_220_280_per_minute_not_audio')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory');p.add_argument('--part',choices=['script','sources','conversation'],default='conversation')
    args=p.parse_args()
    try:print(render(load_bundle(args.directory))[args.part],end='')
    except (ValueError,OSError) as exc:p.exit(2,str(exc)+'\n')


if __name__=='__main__':main()
