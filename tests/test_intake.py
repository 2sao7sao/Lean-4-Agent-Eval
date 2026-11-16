"""Behavioral tests for conversation, dynamic criteria and review boundaries."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from lean4_agent_eval.contracts import validate_contract
from lean4_agent_eval.intake import compile_session, confirm, new_session, reply, SalesSpecCompiler
from lean4_agent_eval.cli import export, run_demo

MESSAGES = json.loads((ROOT / 'examples/sales-to-ppt/intake-conversation.json').read_text())['messages']


def complete_session():
    session = new_session(MESSAGES[0])
    for message in MESSAGES[1:]:
        session = reply(session, message)
    return session


class ConversationTests(unittest.TestCase):
    def test_vague_request_does_not_invent_critical_facts(self):
        result = compile_session(new_session(MESSAGES[0]))
        self.assertEqual(result['state'], 'needs_clarification')
        self.assertIsNone(result['contract'])
        for field in ('periods', 'currency_unit', 'metric', 'refund_policy', 'data_model', 'time_basis', 'external_policy'):
            self.assertNotIn(field, result['facts'])
            self.assertIn(field, [q['id'] for q in result['questions']])

    def test_three_turns_produce_traceable_criteria(self):
        result = compile_session(complete_session())
        self.assertEqual(result['state'], 'ready_for_review')
        self.assertEqual(validate_contract(result['contract']), [])
        self.assertEqual(len(result['contract']['checks']), 8)
        self.assertEqual(result['provenance']['periods']['turn_id'], 'T002')
        self.assertIn('currency_unit@T003', result['contract']['requirements'][0]['source'])
        self.assertTrue(all(c['implementation'] == 'planned' for c in result['contract']['checks']))

    def test_criteria_change_with_metric_currency_pages_and_dimensions(self):
        session = complete_session()
        session = reply(session, '更正：基期2025-11，对比期2025-12；按毛销售额；原始金额USD cents；七页英文PPT给客户；按channel和product拆分；审批后外发。')
        result = compile_session(session)
        self.assertEqual(result['state'], 'ready_for_review', result['questions'])
        checks = {c['id']:c for c in result['contract']['checks']}
        self.assertEqual(checks['C02']['parameters']['formula'], 'gross')
        self.assertEqual(checks['C02']['parameters']['refund_policy'], 'not_applicable')
        self.assertEqual(checks['C02']['parameters']['baseline_month'], '2025-11')
        self.assertEqual(checks['C02']['parameters']['currency'], 'USD')
        self.assertEqual(checks['C03']['parameters']['dimensions'], ['channel', 'product'])
        self.assertEqual(checks['C05']['parameters']['slide_count'], 7)
        self.assertEqual(checks['C05']['parameters']['language'], 'en')
        self.assertEqual(checks['C07']['parameters']['external_policy'], 'approval_required')

    def test_major_unit_is_not_inferred_as_minor_from_word_analysis(self):
        session = reply(complete_session(), '更正：原始金额人民币元；按region做贡献分析。')
        result = compile_session(session)
        self.assertEqual(result['state'], 'ready_for_review', result['questions'])
        check = next(c for c in result['contract']['checks'] if c['id'] == 'C06')
        self.assertEqual(check['parameters']['display_divisor'], 1)

    def test_conflicting_unit_requires_explicit_resolution(self):
        session = reply(complete_session(), '原始金额人民币元。')
        result = compile_session(session)
        self.assertEqual(result['state'], 'needs_clarification')
        self.assertIsNone(result['contract'])
        session = reply(session, '更正：原始金额人民币元。')
        self.assertEqual(compile_session(session)['state'], 'ready_for_review')

    def test_metric_and_refund_formula_contradiction_requires_clarification(self):
        result = compile_session(reply(complete_session(), '更正：净销售额不扣退款。'))
        self.assertEqual(result['state'], 'needs_clarification')
        self.assertIn('metric', [q['id'] for q in result['questions']])

    def test_relative_dates_are_not_resolved_from_machine_clock(self):
        session = new_session('分析上月和本月销售，五页中文PPT。')
        result = compile_session(session)
        self.assertNotIn('periods', result['facts'])

    def test_day_range_is_not_silently_expanded_to_full_months(self):
        result = compile_session(reply(complete_session(), '更正：2026-09-15到2026-10-15。'))
        self.assertEqual(result['state'], 'needs_clarification')

    def test_uncertain_amount_unit_is_not_accepted(self):
        result = compile_session(reply(complete_session(), '金额可能是CNY分。'))
        self.assertEqual(result['state'], 'needs_clarification')

    def test_alternative_units_are_not_accepted(self):
        result = compile_session(reply(complete_session(), '原始金额CNY分或元。'))
        self.assertEqual(result['state'], 'needs_clarification')

    def test_negation_is_not_an_affirmative_fact(self):
        for text in ('不要五页PPT。', '不只paid订单。', '不要净销售额。', '不面向客户。'):
            with self.subTest(text=text):
                result = compile_session(reply(complete_session(), text))
                self.assertEqual(result['state'], 'needs_clarification')

    def test_named_periods_work_in_reverse_text_order(self):
        result = compile_session(reply(complete_session(), '更正：对比期2026-10，基期2026-09。'))
        self.assertEqual(result['facts']['periods'], {'baseline':'2026-09','comparison':'2026-10'})

    def test_filename_is_not_a_period_declaration(self):
        result = compile_session(new_session('使用 sales_2026-09_2026-10.csv，制作5页PPT。'))
        self.assertNotIn('periods', result['facts'])

    def test_invalid_month_stays_a_question(self):
        result = compile_session(reply(complete_session(), '更正：基期2026-13，对比期2026-10。'))
        self.assertEqual(result['state'], 'needs_clarification')

    def test_chinese_fifteen_pages_not_five(self):
        result = compile_session(reply(complete_session(), '更正：十五页PPT。'))
        self.assertEqual(result['facts']['slide_count'], 15)

    def test_unsupported_refund_attribution_is_not_rewritten(self):
        result = compile_session(reply(complete_session(), '更正：按退款发生月份归属退款。'))
        self.assertEqual(result['state'], 'needs_clarification')
        self.assertIn('refund_policy', [q['id'] for q in result['questions']])

    def test_snapshot_and_date_basis_are_required_even_for_gross(self):
        result = compile_session(new_session('按毛销售额，仅paid订单，五页中文PPT。'))
        self.assertIn('data_model', [q['id'] for q in result['questions']])
        self.assertIn('time_basis', [q['id'] for q in result['questions']])
        self.assertNotIn('refund_policy', [q['id'] for q in result['questions']])

    def test_extra_forecasting_request_cannot_be_silently_dropped(self):
        result = compile_session(reply(complete_session(), '更正为六页PPT，并预测下个月销售。'))
        self.assertEqual(result['state'], 'needs_clarification')
        self.assertIn('unhandled', [q['id'] for q in result['questions']])

    def test_unrecognized_supplement_blocks_review(self):
        session = reply(complete_session(), '请增加未定义的XYZ指标。')
        self.assertEqual(compile_session(session)['state'], 'needs_clarification')
        session = reply(session, '撤回上一条未识别补充')
        self.assertEqual(compile_session(session)['state'], 'ready_for_review')

    def test_no_unapproved_external_send_template(self):
        result = compile_session(reply(complete_session(), '直接发送给客户，无需审批。'))
        self.assertEqual(result['state'], 'needs_clarification')

    def test_field_answers_implement_spec_compiler_port(self):
        result = SalesSpecCompiler().compile('销售数据到 PPT', {
            'input_path':'sales.csv', 'periods':'基期2026-09，对比期2026-10',
            'metric':'毛销售额', 'status_policy':'paid', 'data_model':'订单快照',
            'time_basis':'business_date','currency_unit':'CNY 分','group_by':'region',
            'analysis_scope':'变化贡献','slide_count':'5','language':'中文',
            'audience':'经营负责人','external_policy':'仅本地交付'})
        self.assertEqual(result['state'], 'ready_for_review', result['questions'])


class ReviewBoundaryTests(unittest.TestCase):
    def test_cannot_confirm_an_incomplete_contract(self):
        with self.assertRaises(ValueError):
            confirm(new_session(MESSAGES[0]), '0'*64, 'tester')

    def test_stale_review_hash_is_rejected(self):
        session = complete_session()
        old = compile_session(session)['review_sha256']
        changed = reply(session, '更正：六页PPT。')
        with self.assertRaises(ValueError):
            confirm(changed, old, 'tester')

    def test_confirmation_is_not_execution_approval(self):
        session = complete_session()
        session = confirm(session, compile_session(session)['review_sha256'], 'tester')
        result = compile_session(session)
        self.assertEqual(result['state'], 'requirements_confirmed')
        self.assertFalse(result['execution_ready'])
        self.assertEqual(result['contract']['status'], 'draft')
        self.assertEqual(result['contract']['approved_by'], [])
        self.assertEqual(validate_contract(result['contract']), [])

    def test_correction_invalidates_previous_confirmation(self):
        session = complete_session()
        session = confirm(session, compile_session(session)['review_sha256'], 'tester')
        session = reply(session, '更正：六页PPT。')
        self.assertIsNone(session['confirmation'])
        self.assertEqual(compile_session(session)['state'], 'ready_for_review')

    def test_edited_confirmed_contract_fails_hash_check(self):
        session = complete_session()
        result = compile_session(confirm(session, compile_session(session)['review_sha256'], 'tester'))
        changed = copy.deepcopy(result['contract'])
        changed['checks'][0]['acceptance'] = 'Always pass'
        self.assertIn('intake: confirmation does not match the reviewed contract', validate_contract(changed))

    def test_missing_provenance_rejected(self):
        contract = compile_session(complete_session())['contract']
        del contract['intake']['provenance']['metric']
        self.assertIn('intake: each fact must have provenance', validate_contract(contract))

    def test_incomplete_export_creates_no_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                export(new_session(MESSAGES[0]), directory)
            self.assertFalse((Path(directory)/'contract.json').exists())

    def test_demo_records_synthetic_confirmation_and_draft_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            report = run_demo(directory)
            self.assertEqual(report['stages'], ['needs_clarification','needs_clarification','ready_for_review','requirements_confirmed'])
            self.assertEqual(report['user_turns'], 3)
            self.assertEqual(report['agent_execution'], 'NOT_PERFORMED')
            self.assertEqual(json.loads((Path(directory)/'contract.json').read_text())['status'], 'draft')

    def test_interactive_cli_real_stdin_path(self):
        with tempfile.TemporaryDirectory() as directory:
            command = [sys.executable, str(ROOT/'scripts/intake.py'), 'chat', '--request', MESSAGES[0],
                       '--session', str(Path(directory)/'session.json'), '--out', str(Path(directory)/'export'), '--by', 'synthetic-test']
            proc = subprocess.run(command, input='\n'.join(MESSAGES[1:]+['确认'])+'\n', capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            output = json.loads((Path(directory)/'export/result.json').read_text())
            self.assertEqual(output['state'], 'requirements_confirmed')
            self.assertFalse(output['execution_ready'])


if __name__ == '__main__':
    unittest.main()
