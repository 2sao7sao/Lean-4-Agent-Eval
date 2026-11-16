"""Regression controls for omissions and misleading validation metadata."""

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from lean4_agent_eval.contracts import schema_errors, validate_contract


class ContractBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads((ROOT / 'examples/sales-to-ppt/contract.json').read_text())

    def test_draft_is_valid_but_is_not_execution_approval(self):
        self.assertEqual(validate_contract(self.contract), [])
        self.assertEqual(self.contract['status'], 'draft')

    def test_empty_checks_rejected(self):
        self.contract['checks'] = []
        self.assertTrue(validate_contract(self.contract))

    def test_all_optional_checks_cannot_certify(self):
        for check in self.contract['checks']:
            check['required'] = False
        self.assertIn('checks: at least one required check is necessary', validate_contract(self.contract))

    def test_omitted_permission_check_rejected(self):
        self.contract['checks'] = [c for c in self.contract['checks'] if c['id'] != 'C07']
        self.assertIn('R06: mandatory requirement has no required check', validate_contract(self.contract))

    def test_duplicate_check_rejected(self):
        self.contract['checks'].append(copy.deepcopy(self.contract['checks'][0]))
        self.assertIn('checks: duplicate id', validate_contract(self.contract))

    def test_unknown_evidence_rejected(self):
        self.contract['checks'][0]['evidence_ids'] = ['nonexistent']
        self.assertIn('C01: unknown evidence nonexistent', validate_contract(self.contract))

    def test_unknown_requirement_rejected(self):
        self.contract['checks'][0]['requirement_ids'] = ['nonexistent']
        self.assertIn('C01: unknown requirement nonexistent', validate_contract(self.contract))

    def test_freeze_requires_answers_approval_and_implemented_checks(self):
        self.contract['status'] = 'frozen'
        errors = validate_contract(self.contract)
        self.assertIn('frozen: unresolved questions', errors)
        self.assertIn('frozen: approval metadata is missing', errors)
        self.assertIn('frozen: verifier not implemented for C01', errors)

    def test_uncalibrated_model_judge_blocks_freeze(self):
        self.contract.update(status='frozen', open_questions=[], approved_by=['test-metadata-only'])
        for check in self.contract['checks']:
            check['implementation'] = 'implemented'
        self.contract['checks'][0]['method'] = 'model_judge'
        self.assertIn('frozen: missing calibration reference for C01', validate_contract(self.contract))

    def test_misspelled_method_is_not_silently_accepted(self):
        self.contract['checks'][0]['method'] = 'determinstic'
        self.assertTrue(validate_contract(self.contract))


class ReceiptShapeTests(unittest.TestCase):
    def setUp(self):
        self.receipt = {'schema_version':'0.1','contract_id':'test','contract_version':'0.1',
                        'contract_sha256':'0' * 64,'run_id':'test-run','case_id':'test-case',
                        'check_id':'C01','verifier':'test','verifier_version':'0.1',
                        'verdict':'UNKNOWN','evidence_ids':[],'reason':'No evidence available.',
                        'verification_level':'deterministic','proof_ref':None}

    def test_missing_evidence_can_be_unknown(self):
        self.assertEqual(schema_errors(self.receipt, 'receipt'), [])

    def test_pass_without_evidence_rejected(self):
        self.receipt['verdict'] = 'PASS'
        self.assertTrue(schema_errors(self.receipt, 'receipt'))

    def test_formal_pass_without_proof_reference_rejected(self):
        self.receipt.update(verdict='PASS', evidence_ids=['test-only'], verification_level='formal')
        self.assertTrue(schema_errors(self.receipt, 'receipt'))


if __name__ == '__main__':
    unittest.main()
