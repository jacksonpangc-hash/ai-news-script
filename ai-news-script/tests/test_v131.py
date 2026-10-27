"""Execution evidence, rather than paired illustrative text, gates new records."""
import copy
import unittest
from test_v13 import completed_demo
from validate_records import validate_bundle
from render_output import render
import manage_state as state

def current_case(context='demonstration'):
    b=completed_demo()
    b['run']['config']['task_execution_policy']='required_v1'
    b['stories']['stories'][0]['value_brief']['application_context']=context
    return b

def executed_case(kind='author_execution_report'):
    b=current_case()
    claim=copy.deepcopy(b['fact_cards']['claims'][0])
    claim.update(claim_id='execution',statement='Fictional author explicitly reports submitting the input and obtaining the displayed result.')
    b['fact_cards']['claims'].append(claim)
    b['stories']['stories'][0]['value_brief']['execution_evidence']=dict(kind=kind,claim_ids=['execution'],summary='Fictional explicit execution report, not an illustrative answer.')
    return b

class ExecutionEvidenceTests(unittest.TestCase):
    def test_paired_input_and_output_without_execution_is_not_enough(self):
        self.assertIn('task_execution_unconfirmed',{e['code'] for e in validate_bundle(current_case(),final=True)})

    def test_relabeling_the_example_as_actual_use_does_not_bypass_execution(self):
        for context in ('actual_use','pilot'):
            with self.subTest(context=context):
                self.assertIn('task_execution_unconfirmed',{e['code'] for e in validate_bundle(current_case(context),final=True)})

    def test_explicit_author_execution_and_recorded_or_local_runs_can_be_referenced(self):
        for kind in ('author_execution_report','recorded_execution','local_reproduction'):
            with self.subTest(kind=kind):self.assertEqual(validate_bundle(executed_case(kind),final=True),[])

    def test_illustrative_output_is_not_an_execution_basis(self):
        b=executed_case('illustrative_example')
        self.assertIn('task_execution_unconfirmed',{e['code'] for e in validate_bundle(b,final=True)})

    def test_execution_cannot_be_an_assistant_interpretation(self):
        b=executed_case();c=b['fact_cards']['claims'][-1]
        c.update(claim_type='assistant_interpretation',depends_on_claim_ids=['claim_001'])
        self.assertIn('task_execution_unconfirmed',{e['code'] for e in validate_bundle(b,final=True)})

    def test_unread_or_contradicting_execution_evidence_does_not_pass(self):
        for mutation in ('blocked','contradicting'):
            b=executed_case()
            if mutation=='blocked':b['sources']['sources'][0]['access']['status']='blocked'
            else:b['fact_cards']['claims'][-1]['evidence'][0]['relationship']='contradicting'
            self.assertIn('task_execution_unconfirmed',{e['code'] for e in validate_bundle(b,final=True)})

    def test_new_run_requires_current_evidence_policy(self):
        self.assertEqual(state.new_run('ordinary request')['config'].get('task_execution_policy'),'required_v1')
        for disabled in ('off',None):
            with self.subTest(disabled=disabled):
                with self.assertRaises(ValueError):state.new_run('ordinary',overrides={'task_execution_policy':disabled})

    def test_legacy_demo_is_readable_but_not_silently_reapproved(self):
        b=completed_demo()
        self.assertEqual(validate_bundle(b,final=True),[])
        self.assertIn('历史兼容',render(b)['sources'])

if __name__=='__main__':unittest.main()
