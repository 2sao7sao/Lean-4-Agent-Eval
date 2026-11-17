"""Versioned agent/evaluator packages and independent offline verification."""

from collections import Counter
import json
import os
from pathlib import Path, PurePosixPath
import tempfile

from .contracts import ROOT, schema_errors
from .sales_cases import SCENARIOS, SPLITS, SalesCaseBuilder, controls
from .sales_graders import grade_analysis, grade_presentation_projection
from .sales_reference_sql import recompute
from .sales_spec import VERSION, confirmed_spec, contract_digest, digest, json_bytes


def _safe_path(root, relative):
    if not isinstance(relative, str) or '\\' in relative:
        raise ValueError('Invalid bundle path')
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or any(p in ('..','.') for p in path.parts):
        raise ValueError('Bundle path must be relative and contained')
    candidate = root.joinpath(*path.parts)
    if root.resolve() not in candidate.resolve().parents:
        raise ValueError('Bundle path escapes root')
    current = candidate
    while current != root:
        if current.is_symlink():
            raise ValueError('Symlinked bundle paths are not allowed')
        current = current.parent
    return candidate


def _load(root, relative):
    return json.loads(_safe_path(root, relative).read_text(encoding='utf-8'))


def _source_hashes():
    names = ('sales_spec.py','sales_cases.py','sales_reference.py','sales_reference_sql.py',
             'sales_graders.py','dataset_bundle.py','contracts.py','contract_builder.py')
    result = {name:digest((ROOT/'src/lean4_agent_eval'/name).read_bytes()) for name in names}
    result['sales-analysis.schema.json'] = digest((ROOT/'schemas/sales-analysis.schema.json').read_bytes())
    return result


def _task(contract, case, spec):
    return {
        'case_id':case['case_id'], 'contract_id':contract['contract_id'],
        'contract_sha256':contract_digest(contract), 'input_binding':{'I01':'input.csv'},
        'output_schema':'analysis.schema.json',
        'request':contract['goal'],
        'instructions':[
            '本场景 input.csv 替换合同 I01 的数据快照，仅可读取本场景目录；不提供参考答案。',
            f'仅 paid；按 business_date 归月；基期 {spec["baseline"]}，对比期 {spec["comparison"]}。',
            f'原始金额 {spec["currency"]}/{spec["input_unit"]}；字段名与字段规则见 input_rules。',
            '输出 analysis.json 的数值部分遵循随附 Schema，金额统一为整数分/美分；变化率可使用任何等价的精确分数。',
            '输入缺失或冲突时返回 needs_clarification 及问题代码，不编造金额结论；空输入需要澄清。',
            '正常输入同时交付实际 report.pptx；五类主题为摘要、月度对比、分组贡献、口径限制、建议。',
            '变化贡献不等于因果证明，必须说明数据和分析边界。',
            '输入只读，输出仅写运行目录；外发按约定权限，合同确认不是外发批准。',
        ],
        'input_rules':{'metric':spec['metric'], 'refund_attribution':'original_order_month',
                       'unique_key':'order_id','currency':spec['currency'],'input_unit':spec['input_unit'],
                       'amount_columns':['gross_minor','refund_minor'] if spec['input_unit']=='minor' else ['gross_amount','refund_amount'],
                       'amount_format':'nonnegative integer minor or decimal major with at most two fractional digits; no exponent/NaN',
                       'validation':'all rows, including excluded statuses and months; refund <= gross; required dimension values nonempty',
                       'dimensions':spec['dimensions'], 'invalid_input_action':'ask_for_clarification'},
        'presentation':{'slide_count':spec['slide_count'],'language':spec['language'],'audience':spec['audience'],
                        'amount_unit':'major','percentage_decimals':2,'rounding':'ROUND_HALF_UP'},
        'external_policy':spec['external_policy'],
    }


def build_bundle(contract, base_csv, destination, seed=42, splits=SPLITS):
    spec = confirmed_spec(contract)
    destination = Path(destination).absolute()
    if destination.exists():
        raise ValueError('输出目录已存在；数据集不可覆盖，请指定新目录。')
    destination.parent.mkdir(parents=True, exist_ok=True)
    cases = SalesCaseBuilder().build(contract, {'base_csv':base_csv,'seed':seed,'splits':list(splits)})
    sources = _source_hashes()
    identity = {'contract':contract_digest(contract),'base':digest(base_csv),'seed':seed,
                'splits':[s for s in SPLITS if s in splits],'version':VERSION,'source_hashes':sources}
    manifest = {
        'schema_version':VERSION, 'dataset_id':digest(json_bytes(identity)), 'identity':identity,
        'contract_path':'evaluator/contract.json', 'source_path':'evaluator/development-source.csv',
        'cases':[], 'controls':[], 'files':{},
        'split_policy':'Source groups are disjoint; all mutations of a source stay together. Identical empty-input case kept in the first selected split only.',
        'scope':{'agent_execution':'NOT_PERFORMED','actual_ppt_validation':'NOT_IMPLEMENTED',
                 'trace_and_quality_checks':'NOT_IMPLEMENTED','formal_proof':'NOT_PROVED',
                 'holdout':'Synthetic partitioning exercise, not an unseen or access-controlled benchmark.'},
    }
    with tempfile.TemporaryDirectory(prefix='.m2-build-', dir=destination.parent) as temporary:
        root = Path(temporary)/'bundle'
        root.mkdir()

        def put(relative, data):
            target = _safe_path(root,relative)
            target.parent.mkdir(parents=True,exist_ok=True)
            content = data if isinstance(data,bytes) else json_bytes(data)
            target.write_bytes(content)
            manifest['files'][relative] = digest(content)

        put(manifest['contract_path'],contract)
        put(manifest['source_path'],base_csv)
        output_schema = (ROOT/'schemas/sales-analysis.schema.json').read_bytes()
        for case in cases:
            cid, split = case['case_id'],case['split']
            public = f'agent/{split}/{cid}'
            private = f'evaluator/{split}/{cid}'
            input_path, task_path = public+'/input.csv', public+'/task.json'
            reference_path, audit_path = private+'/reference.json',private+'/row-audit.json'
            # Keep the numeric oracle and row audit exclusively on the evaluator side.
            ref = case['reference']
            put(input_path,case['input_csv'])
            put(task_path,_task(contract,case,spec))
            put(public+'/analysis.schema.json',output_schema)
            put(reference_path,{'analysis':ref['analysis'],'display':ref['display']})
            put(audit_path,ref['ledger'])
            manifest['cases'].append({k:case[k] for k in ('case_id','split','source_group','stratum','mutation','requirement_ids')} |
                                     {'input_path':input_path,'task_path':task_path,'reference_path':reference_path,'audit_path':audit_path})
            for control in controls(case):
                name = f'{cid}-{control["id"]}'
                candidate_path = f'evaluator/controls/{name}.json'
                put(candidate_path,control['candidate'])
                manifest['controls'].append({'control_id':name,'case_id':cid,'grader':control['grader'],
                                            'candidate_path':candidate_path,'expected':control['expected'],
                                            'origin':'synthetic_evaluator_fixture'})
        (root/'bundle.json').write_bytes(json_bytes(manifest))
        report = verify_bundle(root,contract)
        (root/'verification.json').write_bytes(json_bytes(report))
        os.replace(root,destination)
    return report


def verify_bundle(directory, external_contract=None):
    root = Path(directory).absolute()
    manifest = _load(root,'bundle.json')
    if manifest.get('schema_version') != VERSION or not manifest.get('cases') or not manifest.get('controls'):
        raise ValueError('Empty or unsupported bundle')
    files = manifest.get('files')
    if not isinstance(files,dict) or not files:
        raise ValueError('Missing artifact inventory')
    for name, expected in files.items():
        if digest(_safe_path(root,name).read_bytes()) != expected:
            raise ValueError('Artifact hash mismatch: '+name)
    actual_files = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()} - {'bundle.json','verification.json'}
    if actual_files != set(files):
        raise ValueError('Untracked or missing bundle artifact')

    def tracked(name):
        if name not in files:
            raise ValueError('Untracked manifest reference: '+str(name))
        return _load(root,name)

    contract = tracked(manifest['contract_path'])
    spec = confirmed_spec(contract)
    identity = manifest['identity']
    if contract_digest(contract) != identity['contract']:
        raise ValueError('Contract binding mismatch')
    if external_contract is not None and contract_digest(external_contract) != identity['contract']:
        raise ValueError('External confirmed contract mismatch')
    if digest(_safe_path(root,manifest['source_path']).read_bytes()) != identity['base']:
        raise ValueError('Source binding mismatch')
    if digest(json_bytes(identity)) != manifest['dataset_id'] or identity['source_hashes'] != _source_hashes():
        raise ValueError('Generator/checker version mismatch; use the matching source revision')
    selected = identity['splits']
    if not selected or selected != [s for s in SPLITS if s in selected]:
        raise ValueError('Invalid split selection')
    expected_cases = {f'{s}-{name}' for s in selected for name,_ in SCENARIOS if name != 'empty' or s == selected[0]}
    if {c['case_id'] for c in manifest['cases']} != expected_cases or len(manifest['cases']) != len(expected_cases):
        raise ValueError('Missing, extra or duplicate cases')
    references, input_splits, group_splits = {}, {}, {}
    partitions = Counter()
    strata = Counter()
    decisions = Counter()
    for case in manifest['cases']:
        cid = case['case_id']
        split = case['split']
        if split not in selected or cid != f'{split}-{case["mutation"]}' or case['stratum'] != dict(SCENARIOS).get(case['mutation']):
            raise ValueError('Case metadata mismatch')
        if case['requirement_ids'] != ['R01','R02']:
            raise ValueError('Numerical scenarios must not claim untested requirement coverage')
        for key, prefix in [('input_path','agent/'),('task_path','agent/'),('reference_path','evaluator/'),('audit_path','evaluator/')]:
            if case[key] not in files or not case[key].startswith(prefix):
                raise ValueError('Agent/evaluator packaging boundary violated')
        data = _safe_path(root,case['input_path']).read_bytes()
        data_hash = digest(data)
        if data_hash in input_splits and input_splits[data_hash] != split:
            raise ValueError('Identical input leaked across splits')
        input_splits[data_hash] = split
        group = case['source_group']
        if group != f'{split}-source-{identity["seed"]}':
            raise ValueError('Source group metadata mismatch')
        if group in group_splits and group_splits[group] != split:
            raise ValueError('Source family leaked across splits')
        group_splits[group] = split
        task = tracked(case['task_path'])
        if task != _task(contract,case,spec):
            raise ValueError('Agent task does not match the confirmed specification')
        public_files = {str(p.relative_to(root)) for p in _safe_path(root,case['task_path']).parent.iterdir()}
        expected_public = {case['task_path'],case['input_path'],str(PurePosixPath(case['task_path']).parent/'analysis.schema.json')}
        if public_files != expected_public:
            raise ValueError('Unexpected content in agent package')
        schema_path = str(PurePosixPath(case['task_path']).parent/'analysis.schema.json')
        if _safe_path(root,schema_path).read_bytes() != (ROOT/'schemas/sales-analysis.schema.json').read_bytes():
            raise ValueError('Output schema differs from the versioned numerical envelope')
        # Independent recomputation never imports the reference producer.
        independent = recompute(data,spec)
        oracle = tracked(case['reference_path'])
        if schema_errors(oracle.get('analysis'),'sales-analysis'):
            raise ValueError('Reference violates output schema')
        if oracle != {'analysis':independent['analysis'],'display':independent['display']}:
            raise ValueError('Independent reference mismatch: '+cid)
        if tracked(case['audit_path']) != independent['ledger']:
            raise ValueError('Independent row audit mismatch: '+cid)
        references[cid] = oracle
        partitions[split] += 1
        strata[case['stratum']] += 1
        decisions[oracle['analysis']['status']] += 1
    issue_by_mutation = {'empty':'EMPTY_DATASET','duplicate_order':'DUPLICATE_ORDER_ID',
                         'mixed_currency':'CURRENCY_MISMATCH','missing_amount':'MISSING_VALUE',
                         'excessive_refund':'REFUND_EXCEEDS_GROSS','invalid_date':'INVALID_DATE',
                         'unknown_status':'INVALID_STATUS','negative_amount':'INVALID_AMOUNT',
                         'invalid_precision':'INVALID_AMOUNT','missing_dimension':'MISSING_VALUE',
                         'missing_column':'MISSING_COLUMNS'}
    for case in manifest['cases']:
        name = case['mutation']
        observed = references[case['case_id']]['analysis']
        issue = issue_by_mutation.get(name)
        if issue:
            if observed['status'] != 'needs_clarification' or observed['issues'] != [issue]:
                raise ValueError('Scenario does not exercise its declared anomaly: '+case['case_id'])
            continue
        if observed['status'] != 'completed':
            raise ValueError('Normal/boundary scenario unexpectedly requires clarification')
        baseline = references[case['split']+'-baseline']['analysis']
        if name in ('reordered','excluded_orders','outside_period'):
            if any(observed[key] != baseline[key] for key in ('monthly_minor','delta_minor','change_ratio','groups','included_count')):
                raise ValueError('Metamorphic invariance failed: '+name)
        if name == 'zero_baseline' and (observed['monthly_minor'][spec['baseline']] != 0 or observed['change_ratio'] is not None):
            raise ValueError('Zero-baseline boundary was not constructed')
        if name == 'zero_current' and observed['monthly_minor'][spec['comparison']] != 0:
            raise ValueError('Zero-current boundary was not constructed')
        if name == 'no_paid' and (observed['included_count'] or any(observed['monthly_minor'].values())):
            raise ValueError('No-paid boundary was not constructed')
        if name == 'full_refund':
            want = {m:0 for m in baseline['monthly_minor']} if spec['metric'] == 'net_sales' else baseline['monthly_minor']
            if observed['monthly_minor'] != want:
                raise ValueError('Full-refund metric semantics failed')
    graders = {'analysis':grade_analysis,'presentation':grade_presentation_projection}
    counts, receipts = Counter(), []
    control_ids = set()
    for control in manifest['controls']:
        if control['control_id'] in control_ids or control['grader'] not in graders or control['case_id'] not in references:
            raise ValueError('Invalid or duplicate control')
        control_ids.add(control['control_id'])
        if not control['candidate_path'].startswith('evaluator/controls/'):
            raise ValueError('Control fixture leaked into agent input')
        receipt = graders[control['grader']](tracked(control['candidate_path']),references[control['case_id']])
        if receipt['verdict'] != control['expected']:
            raise ValueError('Grader counterexample mismatch: '+control['control_id'])
        counts[receipt['verdict']] += 1
        receipts.append({'control_id':control['control_id'],**receipt})
    # No empty/positive-only suite can be called a successful grader validation.
    if set(counts) != {'PASS','FAIL','UNKNOWN','ERROR'} or len(control_ids) != 20 * len(selected):
        raise ValueError('Incomplete grader control coverage')
    return {'status':'PASS_FOR_M2_DATASET_AND_CONTROLS', 'dataset_id':manifest['dataset_id'],
            'reference_checks':len(references),'partitions':dict(partitions),'strata':dict(strata),
            'expected_behaviors':dict(decisions),'control_count':len(receipts),'control_verdicts':dict(counts),
            'independent_checker':'CSV positional parser + string-to-cents + SQLite integer aggregation',
            'requirement_coverage':{'R01':'input validation and numerical scope only; runtime lineage not assessed',
                                    'R02':'monthly totals, exact ratio and group reconciliation',
                                    'R03':'NOT_ASSESSED', 'R04':'synthetic slide-count field only',
                                    'R05':'synthetic presentation summary fields only', 'R06':'NOT_ASSESSED'},
            'controls':receipts, 'agent_execution':'NOT_PERFORMED','actual_ppt_validation':'NOT_IMPLEMENTED',
            'full_contract_verdict':'NOT_ASSESSED','formal_proof':'NOT_PROVED'}
