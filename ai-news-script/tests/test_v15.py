"""New-release contracts; fixtures are fictional and cannot prove writing quality."""
import copy
import tempfile
from pathlib import Path
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import manage_state as state
from normalize_records import rank_stories
from validate_records import validate_bundle
from test_v14 import regional_fixture

class V15Tests(unittest.TestCase):
    def test_actual_entry_identity_and_requested_version(self):
        from loaded_identity import read_identity
        root=Path(__file__).resolve().parents[1]
        got=read_identity(root,expected_version='1.6.0')
        self.assertEqual(got['version'],'1.6.0')
        self.assertEqual(Path(got['entry_path']),root/'SKILL.md')
        with self.assertRaisesRegex(ValueError,'version_mismatch'):
            read_identity(root,expected_version='1.1.1')

    def test_no_save_new_run_has_identity_without_creating_workspace(self):
        with tempfile.TemporaryDirectory() as temp:
            before=list(Path(temp).iterdir())
            r=state.new_run('最近AI新闻',overrides={'save_history':False})
            self.assertEqual(r['loaded_identity']['version'],'1.6.0')
            self.assertEqual(r['config']['sepia_policy'],'embedded_review_v1')
            self.assertFalse(r['config']['default_non_mainland_fallback'])
            self.assertEqual(list(Path(temp).iterdir()),before)

    def test_default_selection_can_stop_instead_of_foreign_fallback(self):
        foreign=regional_fixture('overseas')['stories']['stories'][0]
        self.assertEqual(rank_stories([foreign],region_scope='mainland_preferred',allow_non_mainland=False),[])
        self.assertEqual(len(rank_stories([foreign],region_scope='global',allow_non_mainland=False)),1)
        # Earlier records keep their original explicit fallback semantics.
        self.assertEqual(len(rank_stories([foreign],region_scope='mainland_preferred')),1)

    def test_new_marker_rejects_foreign_default_even_with_old_gap_reason(self):
        b=regional_fixture('overseas');r=b['run'];r['config']['default_non_mainland_fallback']=False
        r['region_review'].update(mainland_result='insufficient',fallback_reason='国内不足',expansion_decision='not_useful',expansion_reason='缺执行证据')
        codes={e['code'] for e in validate_bundle(b,final=True)}
        self.assertIn('default_region_gap',codes)

    def test_v15_identity_review_cannot_claim_unread_references_or_unmapped_changes(self):
        from editorial_contract import validate_editorial
        b=regional_fixture();r=b['run'];r['config']['sepia_policy']='embedded_review_v1'
        self.assertTrue(validate_editorial(b,final=True))

    def test_complete_record_and_concrete_changes_share_rewrite_budget(self):
        from loaded_identity import read_identity
        from editorial_contract import validate_editorial,BASE
        from datetime import datetime,timezone
        import hashlib
        root=Path(__file__).resolve().parents[1]
        b=regional_fixture();r=b['run'];r['config']['sepia_policy']='embedded_review_v1';r['loaded_identity']=read_identity()
        refs=[dict(path='vendor/sepia/'+p,sha256=hashlib.sha256((root/'vendor/sepia'/p).read_bytes()).hexdigest(),sections='实际测试元数据，非真实阅读',read_at=datetime.now(timezone.utc).isoformat()) for p in BASE]
        review=dict(route='business_explainer',venue_basis='虚构中文业务解释口播',loaded_references=refs,model=dict(author='unknown',executor=dict(family='GPT',version='unknown')),prose_layer=dict(author='none',executor='prior'),verdict='clean',findings=[],clean_basis='虚构测试记录仅检查结构，不证明好看',rewrite_count=0,fact_recheck=dict(status='pass',claim_ids=['claim_001']))
        b['script_map']['sepia_review']=review
        self.assertEqual(validate_editorial(b,final=True),[])
        review['findings']=[dict(check='density',quote='虚构原句',finding='重复前文',action='refactor',before='虚构原句',after='虚构修改')]
        self.assertIn('sepia_rewrite_budget',{e['code'] for e in validate_editorial(b,final=True)})
        r['budget']['rewrite_passes_used']=1;review['rewrite_count']=1
        self.assertEqual(validate_editorial(b,final=True),[])
        review['findings'][0].pop('after')
        self.assertIn('sepia_change_missing',{e['code'] for e in validate_editorial(b,final=True)})
        # A policy marker must not turn missing evidence into a pass.
        b['script_map']['sepia_review']={'loaded_references':[], 'findings':[], 'operation':'review'}
        self.assertTrue(validate_editorial(b,final=True))

if __name__=='__main__':unittest.main()
