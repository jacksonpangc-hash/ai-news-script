"""Reserve one host call and its checkpoint together; never invoke a tool here."""
import copy
from datetime import datetime, timezone
from manage_state import consume, save_checkpoint


def _persist(run, workspace, profile):
    if run['config']['save_history']:
        if workspace is None:
            raise ValueError('Saved runs require workspace before calling a tool')
        save_checkpoint(workspace, profile, run)


def prepare_call(run, call, *, workspace=None, profile='default'):
    """Return the reserved snapshot only after validation and durable save succeed.

    Pass ONE dictionary rather than explicit keywords plus **item. Reassign the
    returned run before invoking a host tool. Exceptions mean do not invoke it.
    no-save runs return an in-memory reservation without writing any file.
    """
    if not isinstance(call, dict):
        raise ValueError('Call must be one dictionary')
    item = copy.deepcopy(call)
    kind = item.get('kind')
    if kind not in ('search', 'open') or not item.get('call_id'):
        raise ValueError('One search/open and a call_id are required')
    if item['call_id'] in {x.get('call_id') for x in run.get('tool_log', [])}:
        raise ValueError('Duplicate call_id')
    key = 'query' if kind == 'search' else 'url'
    if not item.get(key) or not item.get('discovery_channel'):
        raise ValueError('Actual query/url and discovery channel are required')
    if not (item.get('source_id') or item.get('lead_id')):
        raise ValueError('Source or lead association required')
    if item.get('outcome', 'reserved') != 'reserved':
        raise ValueError('Cannot reserve an already completed call')
    candidate = copy.deepcopy(run)
    consume(candidate, kind, source_id=item.get('source_id'),
            retry=item.get('retry', False), block_reason=item.get('block_reason'))
    item.update(outcome='reserved', timestamp=datetime.now(timezone.utc).isoformat())
    item.setdefault('fallback_of', None)
    candidate.setdefault('tool_log', []).append(item)
    _persist(candidate, workspace, profile)
    return candidate


def complete_call(run, call_id, outcome, *, workspace=None, profile='default'):
    """Record the real result, including failures, without refunding the budget."""
    if not isinstance(outcome, str) or not outcome.strip() or outcome == 'reserved':
        raise ValueError('Actual completed outcome required')
    candidate = copy.deepcopy(run)
    item = next((x for x in candidate.get('tool_log', []) if x.get('call_id') == call_id), None)
    if item is None or item.get('outcome') != 'reserved':
        raise ValueError('Only a reserved call can be completed')
    item.update(outcome=outcome, completed_at=datetime.now(timezone.utc).isoformat())
    _persist(candidate, workspace, profile)
    return candidate
