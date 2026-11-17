"""M2 behavior, independent oracle checks, isolation and verifier counterexamples."""

import copy
import csv
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from lean4_agent_eval.contracts import review_hash
from lean4_agent_eval.dataset_bundle import build_bundle, verify_bundle
from lean4_agent_eval.dataset_cli import demo_contract
from lean4_agent_eval.intake import compile_session, confirm, new_session, reply
from lean4_agent_eval.sales_cases import SalesCaseBuilder, encode_csv
from lean4_agent_eval.sales_graders import grade_analysis, grade_presentation_projection
from lean4_agent_eval.sales_reference import reference
from lean4_agent_eval.sales_reference_sql import recompute
from lean4_agent_eval.sales_spec import confirmed_spec, digest, json_bytes

BASE = (ROOT/'examples/sales-to-ppt/input/sales.csv').read_bytes()


def changed_contract(message):
    turns = json.loads((ROOT/'examples/sales-to-ppt/intake-conversation.json').read_text())['messages']
    session = new_session(turns[0])
    for text in turns[1:] + [message]:
        session = reply(session,text)
    result = compile_session(session)
    return compile_session(confirm(session,result['review_sha256'],'synthetic-test'))['contract']


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.contract = demo_contract()
        self.spec = confirmed_spec(self.contract)

    def test_hand_calculated_baseline_and_row_audit(self):
        got = reference(BASE,self.spec)
        self.assertEqual(got,recompute(BASE,self.spec))
        self.assertEqual(got['analysis']['monthly_minor'],{'2026-09':220000,'2026-10':180000})
        self.assertEqual(got['analysis']['change_ratio'],{'numerator':-2,'denominator':11})
        self.assertEqual(got['display']['change_percent'],'-18.18%')
        self.assertEqual(got['analysis']['included_count'],7)
        self.assertEqual(sum(r['value_minor'] for r in got['ledger'] if r['included']),400000)

    def test_major_units_use_exact_decimal_not_binary_float(self):
        spec = self.spec | {'input_unit':'major','dimensions':['region']}
        data = b'order_id,business_date,currency,payment_status,gross_amount,refund_amount,region\na,2026-09-01,CNY,paid,0.10,0.01,R\nb,2026-09-02,CNY,paid,0.20,0,R\nc,2026-10-01,CNY,paid,0.30,0.05,R\n'
        got = reference(data,spec)
        self.assertEqual(got,recompute(data,spec))
        self.assertEqual(got['analysis']['monthly_minor'],{'2026-09':29,'2026-10':25})
        self.assertEqual(got['analysis']['change_ratio'],{'numerator':-4,'denominator':29})
        self.assertEqual(got['display']['change_percent'],'-13.79%')

    def test_equivalent_fraction_is_accepted(self):
        ref = reference(BASE,self.spec)
        candidate = copy.deepcopy(ref['analysis'])
        candidate['change_ratio'] = {'numerator':-4,'denominator':22}
        receipt = grade_analysis(candidate,ref)
        self.assertEqual(receipt['verdict'],'PASS')
        self.assertEqual(receipt['full_contract_verdict'],'NOT_ASSESSED')

    def test_negative_rounded_zero_is_normalized(self):
        data = b'order_id,business_date,currency,payment_status,gross_minor,refund_minor,region\na,2026-09-01,CNY,paid,100000000,0,R\nb,2026-10-01,CNY,paid,99999999,0,R\n'
        got = reference(data,self.spec)
        self.assertEqual(got,recompute(data,self.spec))
        self.assertEqual(got['display']['change_percent'],'0.00%')

    def test_validation_applies_to_excluded_rows_too(self):
        data = BASE.replace(b'cancelled,40000,0',b'cancelled,40000,50000')
        got = reference(data,self.spec)
        self.assertEqual(got,recompute(data,self.spec))
        self.assertEqual(got['analysis']['issues'],['REFUND_EXCEEDS_GROSS'])
        self.assertNotIn('monthly_minor',got['analysis'])

    def test_invalid_encoding_and_duplicate_headers_fail_closed(self):
        for data in (b'\xff\xfe',b'order_id,order_id\na,b\n',BASE.replace(b'100000,0',b'NaN,0')):
            with self.subTest(data=data[:20]):
                got = reference(data,self.spec)
                self.assertEqual(got,recompute(data,self.spec))
                self.assertEqual(got['analysis']['status'],'needs_clarification')

    def test_missing_candidate_is_unknown_broken_oracle_is_error(self):
        self.assertEqual(grade_analysis(None,reference(BASE,self.spec))['verdict'],'UNKNOWN')
        self.assertEqual(grade_analysis({}, {})['verdict'],'ERROR')

    def test_keyword_only_submission_is_rejected(self):
        got = grade_analysis({'text':'净销售额 正确 PPT 完成 verifier approval'},reference(BASE,self.spec))
        self.assertEqual(got['verdict'],'FAIL')


class GeneratorTests(unittest.TestCase):
    def test_unconfirmed_contract_is_rejected(self):
        contract = demo_contract()
        contract['intake']['requirements_confirmation'] = None
        with self.assertRaisesRegex(ValueError,'已确认'):
            SalesCaseBuilder().build(contract,{'base_csv':BASE})

    def test_modified_confirmed_contract_is_rejected(self):
        contract = demo_contract()
        contract['checks'][1]['acceptance'] = 'Always pass'
        with self.assertRaisesRegex(ValueError,'confirmation'):
            confirmed_spec(contract)

    def test_resigned_custom_rules_are_not_silently_ignored(self):
        contract = demo_contract()
        contract['checks'][1]['parameters']['formula'] = 'gross + refund'
        contract['intake']['requirements_confirmation']['review_sha256'] = review_hash(contract)
        with self.assertRaisesRegex(ValueError,'超出当前'):
            confirmed_spec(contract)

    def test_all_variants_recompute_and_anomalies_have_no_numbers(self):
        contract = demo_contract()
        spec = confirmed_spec(contract)
        cases = SalesCaseBuilder().build(contract,{'base_csv':BASE,'seed':7})
        self.assertEqual(len(cases),55)
        for case in cases:
            with self.subTest(case=case['case_id']):
                self.assertEqual(case['reference'],recompute(case['input_csv'],spec))
                if case['stratum'] == 'anomaly':
                    self.assertEqual(case['reference']['analysis']['status'],'needs_clarification')
                    self.assertNotIn('monthly_minor',case['reference']['analysis'])

    def test_empty_case_exists_once_across_splits(self):
        cases = SalesCaseBuilder().build(demo_contract(),{'base_csv':BASE})
        self.assertEqual([c['split'] for c in cases if c['mutation']=='empty'],['development'])
        hashes, groups = {}, {}
        for case in cases:
            h = digest(case['input_csv'])
            self.assertIn(hashes.get(h,case['split']),[case['split']])
            hashes[h] = case['split']
            groups.setdefault(case['source_group'],set()).add(case['split'])
        self.assertTrue(all(len(s)==1 for s in groups.values()))

    def test_gross_usd_major_multi_dimension_contract_is_respected(self):
        contract = changed_contract('更正：毛销售额；原始金额USD元；按region和channel拆分；七页英文PPT。')
        rows = list(csv.DictReader(StringIO(BASE.decode())))
        for row in rows:
            row['currency'] = 'USD'
            for old,new in [('gross_minor','gross_amount'),('refund_minor','refund_amount')]:
                amount = int(row.pop(old))
                row[new] = f'{amount//100}.{amount%100:02d}'
        data = encode_csv(rows,list(rows[0]))
        spec = confirmed_spec(contract)
        cases = SalesCaseBuilder().build(contract,{'base_csv':data,'splits':['development']})
        baseline = cases[0]['reference']
        self.assertEqual(baseline['analysis']['monthly_minor'],{'2026-09':230000,'2026-10':190000})
        self.assertEqual(baseline['display']['slide_count'],7)
        self.assertEqual(set(baseline['analysis']['groups']),{'region','channel'})
        for case in cases:
            self.assertEqual(case['reference'],recompute(case['input_csv'],spec))


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'bundle'
        self.contract = demo_contract()
        self.report = build_bundle(self.contract,BASE,self.root)

    def manifest(self):
        return json.loads((self.root/'bundle.json').read_text())

    def change_file_and_rehash(self,relative,value):
        content = json_bytes(value)
        (self.root/relative).write_bytes(content)
        manifest = self.manifest()
        manifest['files'][relative] = digest(content)
        (self.root/'bundle.json').write_bytes(json_bytes(manifest))

    def test_default_bundle_and_counterexample_counts(self):
        self.assertEqual(self.report['reference_checks'],55)
        self.assertEqual(self.report['control_count'],60)
        self.assertEqual(self.report['control_verdicts'],{'PASS':12,'FAIL':39,'UNKNOWN':6,'ERROR':3})
        self.assertEqual(self.report['agent_execution'],'NOT_PERFORMED')
        self.assertTrue(all(c['full_contract_verdict']=='NOT_ASSESSED' for c in self.report['controls']))

    def test_same_seed_reproduces_identical_artifacts(self):
        second = Path(self.temp.name)/'second'
        build_bundle(self.contract,BASE,second)
        self.assertEqual((self.root/'bundle.json').read_bytes(),(second/'bundle.json').read_bytes())

    def test_seed_changes_synthetic_sources(self):
        second = Path(self.temp.name)/'different'
        build_bundle(self.contract,BASE,second,seed=43)
        path = 'agent/holdout/holdout-baseline/input.csv'
        self.assertNotEqual((self.root/path).read_bytes(),(second/path).read_bytes())

    def test_bundle_cannot_overwrite_an_existing_dataset(self):
        with self.assertRaisesRegex(ValueError,'不可覆盖'):
            build_bundle(self.contract,BASE,self.root)

    def test_external_contract_must_match(self):
        changed = changed_contract('更正：六页PPT。')
        with self.assertRaisesRegex(ValueError,'External confirmed contract mismatch'):
            verify_bundle(self.root,changed)

    def test_reference_tampering_is_caught_after_checksum_is_updated(self):
        path = self.manifest()['cases'][0]['reference_path']
        value = json.loads((self.root/path).read_text())
        value['analysis']['delta_minor'] += 1
        self.change_file_and_rehash(path,value)
        with self.assertRaisesRegex(ValueError,'Independent reference mismatch'):
            verify_bundle(self.root)

    def test_row_audit_tampering_is_independently_detected(self):
        path = self.manifest()['cases'][0]['audit_path']
        value = json.loads((self.root/path).read_text())
        value[0]['included'] = not value[0]['included']
        self.change_file_and_rehash(path,value)
        with self.assertRaisesRegex(ValueError,'Independent row audit mismatch'):
            verify_bundle(self.root)

    def test_empty_case_inventory_is_not_a_pass(self):
        manifest = self.manifest()
        manifest['cases'] = []
        (self.root/'bundle.json').write_bytes(json_bytes(manifest))
        with self.assertRaisesRegex(ValueError,'Empty'):
            verify_bundle(self.root)

    def test_reference_is_not_allowed_in_agent_package(self):
        case = self.manifest()['cases'][0]
        destination = str(Path(case['task_path']).parent/'reference.json')
        self.change_file_and_rehash(destination,{'leaked':True})
        with self.assertRaisesRegex(ValueError,'Unexpected content'):
            verify_bundle(self.root)

    def test_path_traversal_is_rejected(self):
        manifest = self.manifest()
        manifest['files']['../outside.json'] = '0'*64
        (self.root/'bundle.json').write_bytes(json_bytes(manifest))
        with self.assertRaisesRegex(ValueError,'relative and contained'):
            verify_bundle(self.root)

    def test_always_pass_grader_is_detected_by_counterexamples(self):
        with patch('lean4_agent_eval.dataset_bundle.grade_analysis',return_value={'verdict':'PASS'}):
            with self.assertRaisesRegex(ValueError,'counterexample mismatch'):
                verify_bundle(self.root)

    def test_faulty_reference_producer_fails_independent_check_before_publish(self):
        original = reference
        def faulty(data,spec):
            result = original(data,spec)
            if result['analysis']['status']=='completed':
                result['analysis']['delta_minor'] += 1
            return result
        target = Path(self.temp.name)/'faulty'
        with patch('lean4_agent_eval.sales_cases.reference',side_effect=faulty):
            with self.assertRaisesRegex(ValueError,'Independent reference mismatch'):
                build_bundle(self.contract,BASE,target)
        self.assertFalse(target.exists())

    def test_verify_command_runs_as_separate_process(self):
        proc = subprocess.run([sys.executable,str(ROOT/'scripts/evalset.py'),'verify','--bundle',str(self.root)],capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['reference_checks'],55)


if __name__ == '__main__':
    unittest.main()
