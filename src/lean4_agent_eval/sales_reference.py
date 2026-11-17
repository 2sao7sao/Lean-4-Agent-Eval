"""Reference producer: CSV + Decimal amount parsing + Python integer aggregation.

The independent checker in sales_reference_sql.py must not call this module.
"""

import csv
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from fractions import Fraction
import io
import re

from .sales_spec import MAX_AMOUNT_MINOR, MAX_BYTES, MAX_ROWS, columns, digest


def _amount(text, unit):
    pattern = r'[0-9]+' if unit == 'minor' else r'[0-9]+(?:\.[0-9]{1,2})?'
    if not re.fullmatch(pattern, text):
        raise ValueError('INVALID_AMOUNT')
    with localcontext() as ctx:
        ctx.prec = 60
        value = Decimal(text) * (100 if unit == 'major' else 1)
    if value > MAX_AMOUNT_MINOR:
        raise ValueError('INPUT_LIMIT_EXCEEDED')
    return int(value)


def reference(data, spec):
    issues, ledger = set(), []
    result = {'schema_version':'sales.analysis.v1', 'input_sha256':digest(data), 'status':'needs_clarification', 'issues':[]}
    if len(data) > MAX_BYTES:
        result['issues'] = ['INPUT_LIMIT_EXCEEDED']
        return {'analysis':result, 'ledger':ledger, 'display':None}
    try:
        reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig')), strict=True)
        header = reader.fieldnames or []
        if len(header) != len(set(header)) or not set(columns(spec)) <= set(header):
            issues.add('MISSING_COLUMNS')
            rows = []
        else:
            rows = list(reader)
    except (UnicodeError, csv.Error):
        issues.add('CSV_SHAPE')
        rows = []
    if not rows and not issues:
        issues.add('EMPTY_DATASET')
    if len(rows) > MAX_ROWS:
        issues.add('INPUT_LIMIT_EXCEEDED')
        rows = []
    seen = set()
    gross_key, refund_key = columns(spec)[4:6]
    for number, raw in enumerate(rows, 2):
        if None in raw or any(v is None for v in raw.values()):
            issues.add('CSV_SHAPE')
            continue
        row = {k:v.strip() for k, v in raw.items()}
        if any(not row[key] for key in columns(spec)):
            issues.add('MISSING_VALUE')
            continue
        if row['order_id'] in seen:
            issues.add('DUPLICATE_ORDER_ID')
        seen.add(row['order_id'])
        if row['currency'] != spec['currency']:
            issues.add('CURRENCY_MISMATCH')
        if row['payment_status'] not in ('paid', 'unpaid', 'cancelled'):
            issues.add('INVALID_STATUS')
        try:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', row['business_date']):
                raise ValueError
            date.fromisoformat(row['business_date'])
            month = row['business_date'][:7]
        except ValueError:
            issues.add('INVALID_DATE')
            continue
        try:
            gross = _amount(row[gross_key], spec['input_unit'])
            refund = _amount(row[refund_key], spec['input_unit'])
        except (ValueError, InvalidOperation) as exc:
            issues.add(str(exc) if str(exc) == 'INPUT_LIMIT_EXCEEDED' else 'INVALID_AMOUNT')
            continue
        if refund > gross:
            issues.add('REFUND_EXCEEDS_GROSS')
        reason = 'included'
        if row['payment_status'] != 'paid':
            reason = 'not_paid'
        elif month not in (spec['baseline'], spec['comparison']):
            reason = 'outside_periods'
        ledger.append({'row_number':number,'order_id':row['order_id'],'month':month,
                       'gross_minor':gross,'refund_minor':refund,
                       'value_minor':gross - refund if spec['metric'] == 'net_sales' else gross,
                       'included':reason == 'included','reason':reason,
                       'groups':{dim:row[dim] for dim in spec['dimensions']}})
    if issues:
        result['issues'] = sorted(issues)
        return {'analysis':result, 'ledger':ledger, 'display':None}
    monthly = {spec['baseline']:0, spec['comparison']:0}
    groups = {dim:{} for dim in spec['dimensions']}
    for row in ledger:
        if not row['included']:
            continue
        value, month = row['value_minor'], row['month']
        monthly[month] += value
        for dim in spec['dimensions']:
            values = groups[dim].setdefault(row['groups'][dim], {'baseline_minor':0,'comparison_minor':0,'delta_minor':0})
            values['baseline_minor' if month == spec['baseline'] else 'comparison_minor'] += value
    for entries in groups.values():
        for values in entries.values():
            values['delta_minor'] = values['comparison_minor'] - values['baseline_minor']
    baseline, current = monthly[spec['baseline']], monthly[spec['comparison']]
    delta = current - baseline
    fraction = Fraction(delta, baseline) if baseline else None
    result = {'schema_version':'sales.analysis.v1','input_sha256':digest(data),'status':'completed',
              'currency':spec['currency'],'amount_unit':'minor','monthly_minor':monthly,'delta_minor':delta,
              'change_ratio':{'numerator':fraction.numerator,'denominator':fraction.denominator} if fraction is not None else None,
              'groups':groups,'row_count':len(rows),'included_count':sum(r['included'] for r in ledger)}
    with localcontext() as ctx:
        ctx.prec = 60
        money = lambda n: format(Decimal(n) / 100, '.2f')
        percentage = format((Decimal(delta) * 100 / baseline).quantize(Decimal('.01'), rounding=ROUND_HALF_UP), '.2f') + '%' if baseline else None
        if percentage == '-0.00%':
            percentage = '0.00%'
        display = {'currency':spec['currency'],'amount_unit':'major','baseline':spec['baseline'],'comparison':spec['comparison'],
                   'baseline_amount':money(baseline),'comparison_amount':money(current),'delta_amount':money(delta),
                   'change_percent':percentage,'slide_count':spec['slide_count'],'language':spec['language']}
    return {'analysis':result,'ledger':ledger,'display':display}
