import copy
import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from support import fixture
try:
    import manage_state as m
    import render_output as r
except ImportError:
    m = r = None


class StateTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(m,'state management not implemented')
        self.assertIsNotNone(r,'output rendering not implemented')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def test_budget_counts_failures_batch_and_retries_before_call(self):
        run=m.new_run('fiction',now='2026-10-25T12:00:00Z',timezone='Asia/Shanghai')
        m.consume(run,'search',count=7)
        with self.assertRaises(ValueError): m.consume(run,'search',count=2)
        self.assertEqual(run['budget']['search_calls_used'],7)
        m.consume(run,'open',source_id='src_001')
        for i in range(2):m.consume(run,'open',source_id='src_001',retry=True)
        with self.assertRaises(ValueError):m.consume(run,'open',source_id='src_001',retry=True)
        self.assertEqual(run['budget']['open_calls_used'],3)

    def test_permanent_blocks_not_retried(self):
        run=m.new_run('fiction')
        for why in ['login','captcha','paywall','forbidden','not_found']:
            with self.assertRaises(ValueError):m.consume(run,'open',source_id='src_001',retry=True,block_reason=why)
        self.assertEqual(run['budget']['open_calls_used'],0)

    def test_state_no_network_blocks_and_terminal_cannot_restart(self):
        run=m.new_run('fiction');m.transition(run,'capability_checked')
        m.transition(run,'blocked',reason='no_network')
        self.assertEqual(run['outcome'],'blocked')
        with self.assertRaises(ValueError):m.transition(run,'scanning')

    def test_strict_no_expansion_and_evergreen_requires_permission(self):
        run=m.new_run('today',overrides={'strict_window':True})
        with self.assertRaises(ValueError):m.expand_window(run)
        run=m.new_run('recent',now='2026-10-25T12:00:00Z');m.expand_window(run)
        self.assertEqual(run['time_context']['window_start_utc'],'2026-09-25T12:00:00Z')
        with self.assertRaises(ValueError):m.expand_window(run,evergreen=True)

    def test_no_save_means_zero_files_and_no_preference_change(self):
        b=fixture();b['run']['config']['save_history']=False
        self.assertIsNone(m.save_bundle(self.root,'default',b))
        self.assertFalse(m.save_preference(self.root,'default','duration_seconds',[90,90],
            authorization_summary='以后90秒',explicit=True,save_history=False))
        self.assertEqual(list(self.root.iterdir()),[])

    def test_path_traversal_and_symlink_escape_refused(self):
        b=fixture()
        with self.assertRaises(ValueError):m.save_bundle(self.root,'../../escape',b)
        p=self.root/'runtime';p.symlink_to(self.root.parent,target_is_directory=True)
        with self.assertRaises(ValueError):m.save_bundle(self.root,'default',b)

    def test_atomic_save_no_overwrite_and_delivered_history_only(self):
        b=fixture();p=m.save_bundle(self.root,'default',b)
        self.assertTrue((p/'script.md').is_file())
        self.assertFalse((p.parent.parent/'event_history.json').exists())
        with self.assertRaises(FileExistsError):m.save_bundle(self.root,'default',b)
        m.record_delivery(self.root,'default',b['run']['run_id'])
        hist=m.load_history(self.root,'default')
        self.assertEqual(hist['revision'],1)
        self.assertEqual(len(hist['events']),1)
        m.record_delivery(self.root,'default',b['run']['run_id'])
        self.assertEqual(m.load_history(self.root,'default')['revision'],1)

    def test_profile_and_workspace_isolation(self):
        m.save_preference(self.root,'alice','duration_seconds',[90,90],explicit=True,authorization_summary='以后90秒')
        self.assertEqual(m.load_preferences(self.root,'alice')['duration_seconds'],[90,90])
        self.assertEqual(m.load_preferences(self.root,'bob'),{})
        other=self.root/'other';other.mkdir()
        self.assertEqual(m.load_preferences(other,'alice'),{})

    def test_ephemeral_preference_not_persisted_and_explicit_read_back(self):
        self.assertFalse(m.save_preference(self.root,'default','duration_seconds',[90,90],explicit=False))
        self.assertEqual(list(self.root.iterdir()),[])
        m.save_preference(self.root,'default','duration_seconds',[90,90],explicit=True,authorization_summary='以后90秒')
        run=m.new_run('new request',preferences=m.load_preferences(self.root,'default'))
        self.assertEqual(run['config']['duration_seconds'],[90,90])
        run=m.new_run('one time',preferences=m.load_preferences(self.root,'default'),overrides={'duration_seconds':[60,60]})
        self.assertEqual(run['config']['duration_seconds'],[60,60])

    def test_concurrent_preferences_preserve_other_keys(self):
        def write(pair):
            m.save_preference(self.root,'default',pair[0],pair[1],explicit=True,authorization_summary='explicit fixture')
        with ThreadPoolExecutor(2) as pool:list(pool.map(write,[('audience','owners'),('duration_seconds',[90,90])]))
        self.assertEqual(m.load_preferences(self.root,'default'),{'audience':'owners','duration_seconds':[90,90]})

    def test_history_requires_material_update_or_explicit_repeat(self):
        story=fixture()['stories']['stories'][0]
        history={'events':[dict(canonical_event_key=story['canonical_event_key'],aliases=[])]}
        self.assertFalse(m.repeat_allowed(story,history))
        self.assertTrue(m.repeat_allowed(story,history,repeat_requested=True))
        story['material_update']=dict(description='new scope',new_claim_ids=['claim_001'],source_ids=['src_001'])
        self.assertTrue(m.repeat_allowed(story,history))

    def test_local_revision_changes_target_only_and_preserves_parent(self):
        b=fixture();before=copy.deepcopy(b)
        revision=m.revise_paragraph(b,1,[{**b['script_map']['sentences'][1], 'text':'公司自述试点：AI建议，员工确认。'}])
        self.assertEqual(b,before)
        self.assertEqual(revision['script_map']['sentences'][0],before['script_map']['sentences'][0])
        self.assertEqual(revision['script_map']['sentences'][2],before['script_map']['sentences'][2])
        self.assertEqual(revision['run']['request']['parent_run_id'],before['run']['run_id'])
        self.assertEqual(revision['script_map']['checks']['semantic_fact_review'],'not_run')

    def test_render_clean_body_and_expansion_notice_before_title(self):
        b=fixture();b['run']['time_context'].update(expanded=True,content_mode='expanded_window',lookback_days_used=30,
                                                  window_start_utc='2026-09-25T12:00:00Z')
        out=r.render(b)
        self.assertTrue(out['conversation'].startswith('检索范围已扩展'))
        self.assertNotIn('src_001',out['script'])
        self.assertNotIn('http',out['script'])
        self.assertIn('https://example.invalid/case',out['sources'])
        self.assertIn('未做真人计时',out['sources'])

    def test_failed_validation_does_not_create_output(self):
        b=fixture();b['script_map']['checks']['semantic_fact_review']='not_run'
        with self.assertRaises(ValueError):m.save_bundle(self.root,'default',b)
        self.assertEqual(list(self.root.iterdir()),[])

    def test_stale_checkpoint_cannot_reset_spent_budget(self):
        run=m.new_run('fiction');stale=copy.deepcopy(run)
        m.consume(run,'open',count=5);m.save_checkpoint(self.root,'default',run)
        with self.assertRaises(ValueError):m.save_checkpoint(self.root,'default',stale)

    def test_forged_same_revision_cannot_lower_budget(self):
        run=m.new_run('fiction');m.consume(run,'search',count=4);m.save_checkpoint(self.root,'default',run)
        run['budget']['search_calls_used']=0
        with self.assertRaises(ValueError):m.save_checkpoint(self.root,'default',run)


if __name__=='__main__':unittest.main()
