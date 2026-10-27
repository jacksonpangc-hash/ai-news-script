"""Defaults and host-call safety; no claim of semantic or audience acceptance."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from manage_state import new_run, profile_path
from tool_calls import prepare_call, complete_call


class V16Tests(unittest.TestCase):
    def call(self):
        return dict(call_id='search_1', kind='search', query='fictional business task',
                    discovery_channel='official_case_search', lead_id='lead',
                    region_focus='china_mainland', search_angle='fictional')

    def test_defaults_and_explicit_override(self):
        run = new_run('最近AI新闻')
        self.assertEqual(run['request']['audience'], 'mainland_sme_owners')
        self.assertEqual(run['config']['default_case_focus'], ['enterprise_efficiency', 'business_operations'])
        self.assertEqual(run['config']['editorial_policy'], 'ai_business_value_v16')
        other = new_run('给学生讲学习应用', overrides={'audience': 'students', 'region_scope': 'global'})
        self.assertEqual(other['request']['audience'], 'students')
        self.assertEqual(other['request']['region_scope'], 'global')

    def test_reservation_is_durable_before_return_and_failure_keeps_charge(self):
        with tempfile.TemporaryDirectory() as temp:
            run = new_run('fixture')
            reserved = prepare_call(run, self.call(), workspace=temp)
            pending = profile_path(temp, 'default')/'pending'/(run['run_id']+'.json')
            self.assertTrue(pending.is_file())
            self.assertIn('reserved', pending.read_text())
            self.assertEqual(reserved['budget']['search_calls_used'], 1)
            done = complete_call(reserved, 'search_1', 'fetch_timeout', workspace=temp)
            self.assertEqual(done['budget']['search_calls_used'], 1)
            self.assertEqual(done['tool_log'][0]['outcome'], 'fetch_timeout')
            self.assertEqual(run['budget']['search_calls_used'], 0)

    def test_checkpoint_failure_returns_no_reservation_and_leaves_input_unchanged(self):
        run = new_run('fixture'); before = copy.deepcopy(run)
        with patch('tool_calls.save_checkpoint', side_effect=OSError('fixture write failure')):
            with self.assertRaises(OSError):
                prepare_call(run, self.call(), workspace='unused')
        self.assertEqual(run, before)

    def test_budget_or_duplicate_rejected_before_host_step(self):
        run = new_run('fixture', overrides={'save_history': False, 'max_search_calls': 1})
        reserved = prepare_call(run, self.call())
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            prepare_call(reserved, self.call())
        another = self.call(); another['call_id'] = 'search_2'
        with self.assertRaisesRegex(ValueError, 'budget_exhausted'):
            prepare_call(reserved, another)

    def test_no_save_reservation_and_completion_write_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            run = new_run('fixture', overrides={'save_history': False})
            reserved = prepare_call(run, self.call(), workspace=temp)
            done = complete_call(reserved, 'search_1', 'search_results_returned', workspace=temp)
            self.assertEqual(done['budget']['search_calls_used'], 1)
            self.assertEqual(list(Path(temp).iterdir()), [])

    def test_completed_calls_cannot_be_predeclared_or_completed_twice(self):
        run = new_run('fixture', overrides={'save_history': False})
        bad = self.call(); bad['outcome'] = 'search_results_returned'
        with self.assertRaises(ValueError): prepare_call(run, bad)
        reserved = prepare_call(run, self.call())
        done = complete_call(reserved, 'search_1', 'search_results_returned')
        with self.assertRaises(ValueError): complete_call(done, 'search_1', 'search_results_returned')


if __name__ == '__main__': unittest.main()
