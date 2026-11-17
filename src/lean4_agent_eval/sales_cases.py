"""Materialize deterministic input variants from a confirmed M1 contract."""

import copy
import csv
from decimal import Decimal
import io
import random

from .sales_reference import reference
from .sales_spec import MAX_ROWS, columns, confirmed_spec

SPLITS = ('development','calibration','holdout')
SCENARIOS = (
    ('baseline','normal'), ('reordered','normal'), ('excluded_orders','normal'), ('outside_period','normal'),
    ('empty','boundary'), ('zero_baseline','boundary'), ('zero_current','boundary'),
    ('full_refund','boundary'), ('no_paid','boundary'),
    ('duplicate_order','anomaly'), ('mixed_currency','anomaly'), ('missing_amount','anomaly'),
    ('excessive_refund','anomaly'), ('invalid_date','anomaly'), ('unknown_status','anomaly'),
    ('negative_amount','anomaly'), ('invalid_precision','anomaly'), ('missing_dimension','anomaly'),
    ('missing_column','anomaly'),
)


def encode_csv(rows, fields):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n', extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')


def _format(minor, spec):
    return str(minor) if spec['input_unit'] == 'minor' else f'{minor // 100}.{minor % 100:02d}'


def synthetic_source(spec, seed, split):
    """Independent synthetic source groups, not mutations of the supplied CSV."""
    rng = random.Random(f'{seed}:{split}:sales-source-v1')
    rows = []
    gross, refund = columns(spec)[4:6]
    size = 13 if split == 'calibration' else 21
    for n in range(size):
        amount = rng.randint(101, 190003) * (3 if split == 'holdout' else 1)
        returned = rng.randint(0, amount // 3)
        row = {'order_id':f'{split}-{n:04d}', 'business_date':f'{spec["baseline"] if n % 2 == 0 else spec["comparison"]}-{n % 27 + 1:02d}',
               'currency':spec['currency'], 'payment_status':'paid' if n % 5 else 'unpaid',
               gross:_format(amount,spec), refund:_format(returned,spec)}
        for d, dim in enumerate(spec['dimensions']):
            row[dim] = f'{split}-{dim}-{(n + d) % (4 if split == "holdout" else 3)}'
        rows.append(row)
    return rows


def variants(rows, spec):
    fields = list(rows[0])
    gross, refund = columns(spec)[4:6]
    for name, stratum in SCENARIOS:
        changed, header = copy.deepcopy(rows), list(fields)
        if name == 'reordered':
            changed.reverse()
        elif name in ('excluded_orders','outside_period'):
            extra = copy.deepcopy(rows[0])
            extra['order_id'] = '__m2_extra__'
            while extra['order_id'] in {r['order_id'] for r in rows}:
                extra['order_id'] += '_'
            extra[gross], extra[refund] = _format(99999999,spec), _format(0,spec)
            if name == 'excluded_orders':
                extra['payment_status'] = 'cancelled'
            else:
                extra['payment_status'], extra['business_date'] = 'paid', '1999-01-01'
            changed.append(extra)
        elif name == 'empty':
            changed = []
        elif name in ('zero_baseline','zero_current'):
            target = spec['baseline'] if name == 'zero_baseline' else spec['comparison']
            for row in changed:
                if row['business_date'][:7] == target:
                    row[gross], row[refund] = _format(0,spec), _format(0,spec)
        elif name == 'full_refund':
            for row in changed:
                if row['payment_status'] == 'paid':
                    row[refund] = row[gross]
        elif name == 'no_paid':
            for row in changed:
                row['payment_status'] = 'unpaid'
        elif name == 'duplicate_order':
            changed.append(copy.deepcopy(changed[0]))
        elif name == 'mixed_currency':
            changed[0]['currency'] = 'USD' if spec['currency'] == 'CNY' else 'CNY'
        elif name == 'missing_amount':
            changed[0][gross] = ''
        elif name == 'excessive_refund':
            changed[0][gross], changed[0][refund] = _format(1,spec), _format(2,spec)
        elif name == 'invalid_date':
            changed[0]['business_date'] = '2026-02-30'
        elif name == 'unknown_status':
            changed[0]['payment_status'] = 'unknown_state'
        elif name == 'negative_amount':
            changed[0][gross] = '-1'
        elif name == 'invalid_precision':
            changed[0][gross] = '0.1' if spec['input_unit'] == 'minor' else '0.001'
        elif name == 'missing_dimension':
            changed[0][spec['dimensions'][0]] = ''
        elif name == 'missing_column':
            header.remove(refund)
        yield name, stratum, encode_csv(changed, header)


class SalesCaseBuilder:
    def build(self, confirmed_contract, coverage_plan):
        spec = confirmed_spec(confirmed_contract)
        seed = coverage_plan.get('seed', 42)
        splits = coverage_plan.get('splits', list(SPLITS))
        if type(seed) is not int or not 0 <= seed < 2**32:
            raise ValueError('seed 必须为 0 到 2^32-1 的整数。')
        if not splits or len(splits) != len(set(splits)) or not set(splits) <= set(SPLITS):
            raise ValueError('无效或重复的数据划分。')
        base = coverage_plan['base_csv']
        if isinstance(base, str):
            base = base.encode('utf-8')
        if not isinstance(base, bytes):
            raise ValueError('base_csv 必须为 CSV 文本或字节。')
        baseline = reference(base, spec)
        if baseline['analysis']['status'] != 'completed':
            raise ValueError('基准输入需要先澄清：' + ', '.join(baseline['analysis']['issues']))
        base_rows = list(csv.DictReader(io.StringIO(base.decode('utf-8-sig')), strict=True))
        base_rows = [{k:v.strip() for k,v in row.items()} for row in base_rows]
        if len(base_rows) >= MAX_ROWS:
            raise ValueError('基准数据需为增加边界行保留容量。')
        output = []
        first_split = next(s for s in SPLITS if s in splits)
        for split in SPLITS:
            if split not in splits:
                continue
            rows = base_rows if split == 'development' else synthetic_source(spec,seed,split)
            source_group = f'{split}-source-{seed}'
            for name, stratum, data in variants(rows, spec):
                # An empty CSV is identical across source groups. Keep it once.
                if name == 'empty' and split != first_split:
                    continue
                output.append({'case_id':f'{split}-{name}','split':split,'source_group':source_group,
                               'stratum':stratum,'mutation':name,'input_csv':data,
                               'reference':reference(data,spec),
                               'requirement_ids':['R01','R02']})
        return output


def controls(case):
    """Clearly labelled evaluator fixtures, never model-generated successes."""
    if case['mutation'] not in ('baseline','zero_baseline','duplicate_order'):
        return []
    oracle = case['reference']
    correct = oracle['analysis']
    result = [{'id':'correct_analysis','grader':'analysis','candidate':copy.deepcopy(correct),'expected':'PASS'}]

    def add(name, candidate, verdict='FAIL', grader='analysis'):
        result.append({'id':name,'grader':grader,'candidate':candidate,'expected':verdict})

    if correct['status'] == 'needs_clarification':
        bad = copy.deepcopy(correct)
        bad['issues'] = ['INVALID_DATE']
        add('wrong_clarification',bad)
        add('keywords_only',{'text':'净销售额 verifier approval tools 数据可靠，已完成PPT'})
        return result
    if case['mutation'] == 'zero_baseline':
        bad = copy.deepcopy(correct)
        bad['change_ratio'] = {'numerator':100,'denominator':1}
        add('fabricated_zero_baseline_growth',bad)
        return result
    for key in ('delta_minor','currency','input_sha256','groups','change_ratio'):
        bad = copy.deepcopy(correct)
        if key == 'delta_minor': bad[key] += 1
        elif key == 'currency': bad[key] = 'USD' if bad[key] == 'CNY' else 'CNY'
        elif key == 'input_sha256': bad[key] = '0'*64
        elif key == 'groups': bad[key] = {}
        else: bad[key] = {'numerator':1,'denominator':1} if bad[key] != {'numerator':1,'denominator':1} else {'numerator':2,'denominator':1}
        add('wrong_' + key,bad)
    bad = copy.deepcopy(correct)
    first = next(iter(bad['monthly_minor']))
    bad['monthly_minor'][first] += 1
    add('wrong_total_one_cent',bad)
    add('keywords_only',{'text':'净销售额 verifier approval tools 数据可靠，已完成PPT'})
    add('missing_submission',None,'UNKNOWN')
    projection = {'kind':'synthetic_presentation_projection','extraction_status':'complete','facts':copy.deepcopy(oracle['display'])}
    add('correct_presentation_facts',projection,'PASS','presentation')
    for key in ('delta_amount','amount_unit','slide_count'):
        bad = copy.deepcopy(projection)
        bad['facts'][key] = (bad['facts'][key] + 1 if key == 'slide_count' else 'minor' if key == 'amount_unit' else format(Decimal(bad['facts'][key]) + Decimal('.01'), '.2f'))
        add('wrong_presentation_' + key,bad,'FAIL','presentation')
    add('missing_presentation',None,'UNKNOWN','presentation')
    bad = copy.deepcopy(projection)
    bad['extraction_status'] = 'error'
    add('renderer_error',bad,'ERROR','presentation')
    return result
