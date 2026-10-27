"""Mechanical aids, never a semantic news verifier. Python 3.9+, standard library."""
import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
import math
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

WEIGHTS = dict(practical_value=30, evidence_quality=25, information_gain=20,
               explainability=15, recency=10)
TRACKING = {'fbclid', 'gclid', 'dclid', 'msclkid', 'mc_cid', 'mc_eid', 'igshid'}
SECRET_KEYS = {'token', 'access_token', 'api_key', 'apikey', 'key', 'secret', 'signature',
               'sig', 'password', 'auth', 'authorization', 'cookie', 'code'}


def utc(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Timestamp must include timezone')
    return dt.astimezone(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def normalize_url(url):
    parts = urlsplit(url)
    if parts.scheme.lower() not in ('https', 'http') or not parts.hostname:
        raise ValueError('Only public HTTP(S) source URLs are supported')
    if parts.username or parts.password:
        raise ValueError('Credential-bearing URL must not be recorded')
    params = parse_qsl(parts.query, keep_blank_values=True)
    if any(k.lower() in SECRET_KEYS or k.lower().startswith('x-amz-') for k, _ in params):
        raise ValueError('Signed or credential-bearing URL must not be recorded')
    params = [(k, v) for k, v in params if not k.lower().startswith('utm_') and k.lower() not in TRACKING]
    # Preserve path case, content query parameters, their order and multiplicity.
    host = parts.hostname.lower()
    if ':' in host:
        host = '[' + host + ']'
    port = parts.port
    if port and (parts.scheme.lower(), port) not in [('https', 443), ('http', 80)]:
        host += ':' + str(port)
    return urlunsplit((parts.scheme.lower(), host, parts.path, urlencode(params), ''))


def date_status(record, start, end):
    if not record or not record.get('value'):
        return 'ambiguous'
    left, right = utc(start), utc(end)
    if left > right:
        raise ValueError('Reversed window')
    if record.get('precision') == 'date':
        d = date.fromisoformat(record['value'])
        zone = record.get('timezone')
        if zone:
            low = datetime.combine(d, time.min, ZoneInfo(zone)).astimezone(timezone.utc)
            high = datetime.combine(d + timedelta(days=1), time.min, ZoneInfo(zone)).astimezone(timezone.utc)
        else:
            # A date in an unspecified civil timezone can span UTC-12 through UTC+14.
            base = datetime.combine(d, time.min, timezone.utc)
            low, high = base - timedelta(hours=14), base + timedelta(days=1, hours=12)
        if high <= left:
            return 'outside_window'
        if low > right:
            return 'future_unverified'
        return 'supported' if low >= left and high <= right else 'ambiguous'
    instant = utc(record['value'])
    if instant > right:
        return 'future_unverified'
    return 'supported' if instant >= left else 'outside_window'


def editorial_total(scores):
    total = 0
    for key, weight in WEIGHTS.items():
        value = scores[key]
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 4:
            raise ValueError('Editorial component must be integer 0..4')
        total += value / 4 * weight
    return round(total, 2)


def rank_stories(stories, minimum=60, *, region_scope=None, allow_non_mainland=True):
    eligible = [s for s in stories if s.get('evidence_gate', {}).get('passed') is True
                and s.get('editorial_score') is not None
                and s.get('date_status') not in ('future_unverified', 'conflicting', 'outside_window')]
    eligible = [s for s in eligible if editorial_total(s['editorial_score']) >= minimum]
    if region_scope=='mainland_preferred' and not allow_non_mainland:
        eligible=[s for s in eligible if s.get('case_region',{}).get('value')=='china_mainland']
    if region_scope in ('mainland_only','overseas_only'):
        value='china_mainland' if region_scope=='mainland_only' else 'overseas'
        eligible=[s for s in eligible if s.get('case_region',{}).get('value')==value]
    return sorted(eligible, key=lambda s: (0 if region_scope!='mainland_preferred' or s.get('case_region',{}).get('value')=='china_mainland' else 1, -editorial_total(s['editorial_score']),
                  -s['editorial_score']['evidence_quality'], -s['editorial_score']['practical_value'],
                  -s['editorial_score']['information_gain'], s['canonical_event_key']))


def independent_groups(sources):
    return len({s['independence_group'] for s in sources if s.get('independence_group')})


def derive_metric(metric):
    """Only calculate a reported same-scope change; never derive ROI or layoffs."""
    result = dict(eligible=False, relative_change_percent=None, percentage_points=None, ineligible_reasons=[])
    before, after = metric.get('baseline'), metric.get('outcome')
    if not isinstance(before, dict) or not isinstance(after, dict):
        result['ineligible_reasons'].append('missing_baseline_or_outcome')
        return result
    for point in (before, after):
        value = point.get('value')
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            result['ineligible_reasons'].append('unknown_or_invalid_value')
    if not before.get('scope') or before.get('scope') != after.get('scope'):
        result['ineligible_reasons'].append('scope_mismatch_or_unknown')
    for key in ('unit', 'denominator', 'sample_size', 'timeframe', 'method'):
        if metric.get(key) is None or metric.get(key) == '':
            result['ineligible_reasons'].append('unknown_' + key)
    period=metric.get('timeframe')
    try:
        if not isinstance(period,dict) or date.fromisoformat(period['start'])>date.fromisoformat(period['end']):
            raise ValueError('Invalid observation period')
    except (KeyError,TypeError,ValueError):
        result['ineligible_reasons'].append('unknown_or_invalid_timeframe')
    sample=metric.get('sample_size')
    if isinstance(sample,bool) or not isinstance(sample,(int,float)) or not math.isfinite(sample) or sample<=0:
        result['ineligible_reasons'].append('unknown_or_invalid_sample')
    if before.get('value') == 0:
        result['ineligible_reasons'].append('zero_baseline')
    if result['ineligible_reasons']:
        return result
    a, b = before['value'], after['value']
    result.update(eligible=True, relative_change_percent=round((b-a)/a*100, 6))
    if metric['unit'].startswith('percent_'):
        result['percentage_points'] = round(b-a, 6)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('url', help='Public URL; known tracking fields are removed, content fields preserved')
    args = p.parse_args()
    try:
        print(json.dumps({'canonical_url':normalize_url(args.url)}, ensure_ascii=False))
    except ValueError as exc:
        p.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    main()
