"""Independent reference checker: positional CSV + string cents + SQLite SUM.

Does not import or call sales_reference, its parser, aggregation or formatting.
Shared spec constants define the supported domain, not the expected answers.
"""

import calendar
import csv
from hashlib import sha256
import io
from math import gcd
import sqlite3

from .sales_spec import MAX_AMOUNT_MINOR, MAX_BYTES, MAX_ROWS, columns


def recompute(data, spec):
    answer = {'schema_version':'sales.analysis.v1','input_sha256':sha256(data).hexdigest(),
              'status':'needs_clarification','issues':[]}
    problems, records = set(), []
    if len(data) > MAX_BYTES:
        answer['issues'] = ['INPUT_LIMIT_EXCEEDED']
        return {'analysis':answer, 'ledger':[], 'display':None}
    try:
        table = list(csv.reader(io.StringIO(data.decode('utf-8-sig')), strict=True))
    except (UnicodeError, csv.Error):
        table = []
        problems.add('CSV_SHAPE')
    needed = columns(spec)
    headings = table[0] if table else []
    if not problems and (len(headings) != len(set(headings)) or any(n not in headings for n in needed)):
        problems.add('MISSING_COLUMNS')
    source_rows = table[1:] if not problems else []
    # csv.DictReader ignores completely blank rows; match that declared CSV convention.
    source_rows = [r for r in source_rows if r]
    if not source_rows and not problems:
        problems.add('EMPTY_DATASET')
    if len(source_rows) > MAX_ROWS:
        problems.add('INPUT_LIMIT_EXCEEDED')
        source_rows = []
    unique_ids = set()
    for offset, cells in enumerate(source_rows, 2):
        if len(cells) != len(headings):
            problems.add('CSV_SHAPE')
            continue
        values = dict(zip(headings, [c.strip() for c in cells]))
        if any(values[key] == '' for key in needed):
            problems.add('MISSING_VALUE')
            continue
        oid = values['order_id']
        if oid in unique_ids:
            problems.add('DUPLICATE_ORDER_ID')
        unique_ids.add(oid)
        if values['currency'] != spec['currency']:
            problems.add('CURRENCY_MISMATCH')
        if values['payment_status'] not in {'paid','unpaid','cancelled'}:
            problems.add('INVALID_STATUS')
        try:
            raw_date = values['business_date']
            parts = raw_date.split('-')
            if len(parts) != 3 or [len(p) for p in parts] != [4,2,2] or any(not p.isascii() or not p.isdigit() for p in parts):
                raise ValueError
            y, m, d = map(int, parts)
            if not 1 <= y <= 9999 or not 1 <= m <= 12 or not 1 <= d <= calendar.monthrange(y,m)[1]:
                raise ValueError
            month = raw_date[:7]
        except ValueError:
            problems.add('INVALID_DATE')
            continue
        amounts = []
        for key in needed[4:6]:
            pieces = values[key].split('.')
            valid = all(piece and piece.isascii() and piece.isdigit() for piece in pieces)
            valid = valid and (len(pieces) == 1 if spec['input_unit'] == 'minor' else len(pieces) in (1,2))
            valid = valid and (len(pieces) == 1 or 1 <= len(pieces[1]) <= 2)
            if not valid:
                problems.add('INVALID_AMOUNT')
                break
            # Reject unbounded digit strings before conversion; allow leading zeros.
            whole = pieces[0].lstrip('0') or '0'
            if len(whole) > 13:
                problems.add('INPUT_LIMIT_EXCEEDED')
                break
            cents = int(whole)
            if spec['input_unit'] == 'major':
                cents = cents * 100 + (int(pieces[1].ljust(2,'0')) if len(pieces) == 2 else 0)
            if cents > MAX_AMOUNT_MINOR:
                problems.add('INPUT_LIMIT_EXCEEDED')
                break
            amounts.append(cents)
        if len(amounts) != 2:
            continue
        gross, refund = amounts
        if refund > gross:
            problems.add('REFUND_EXCEEDS_GROSS')
        reason = ('not_paid' if values['payment_status'] != 'paid' else
                  'outside_periods' if month not in {spec['baseline'], spec['comparison']} else 'included')
        records.append({'row_number':offset,'order_id':oid,'month':month,'gross_minor':gross,'refund_minor':refund,
                        'value_minor':gross-refund if spec['metric'] == 'net_sales' else gross,
                        'included':reason == 'included','reason':reason,
                        'groups':{dim:values[dim] for dim in spec['dimensions']}})
    if problems:
        answer['issues'] = sorted(problems)
        return {'analysis':answer,'ledger':records,'display':None}
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE orders (month TEXT, value INTEGER, included INTEGER)')
        db.execute('CREATE TABLE dimensions (dimension TEXT, label TEXT, month TEXT, value INTEGER)')
        db.executemany('INSERT INTO orders VALUES (?,?,?)', [(r['month'],r['value_minor'],r['included']) for r in records])
        db.executemany('INSERT INTO dimensions VALUES (?,?,?,?)',
                       [(dim,label,r['month'],r['value_minor']) for r in records if r['included'] for dim,label in r['groups'].items()])
        totals = {m:db.execute('SELECT COALESCE(SUM(value),0) FROM orders WHERE included=1 AND month=?',(m,)).fetchone()[0]
                  for m in (spec['baseline'],spec['comparison'])}
        groups = {dim:{} for dim in spec['dimensions']}
        for dim,label,before,after in db.execute('SELECT dimension,label,SUM(CASE WHEN month=? THEN value ELSE 0 END),SUM(CASE WHEN month=? THEN value ELSE 0 END) FROM dimensions GROUP BY dimension,label',
                                                (spec['baseline'],spec['comparison'])):
            groups[dim][label] = {'baseline_minor':before,'comparison_minor':after,'delta_minor':after-before}
    before, after = totals[spec['baseline']], totals[spec['comparison']]
    delta = after-before
    divisor = gcd(abs(delta),before) if before else None
    ratio = {'numerator':delta//divisor,'denominator':before//divisor} if before else None
    answer = {'schema_version':'sales.analysis.v1','input_sha256':sha256(data).hexdigest(),'status':'completed',
              'currency':spec['currency'],'amount_unit':'minor','monthly_minor':totals,'delta_minor':delta,
              'change_ratio':ratio,'groups':groups,'row_count':len(source_rows),'included_count':sum(r['included'] for r in records)}

    def decimal_string(integer):
        whole, fractional = divmod(abs(integer),100)
        return ('-' if integer < 0 else '') + str(whole) + '.' + str(fractional).zfill(2)

    percentage = None
    if before:
        quotient, remainder = divmod(abs(delta)*10000, before)
        rounded = quotient + int(remainder*2 >= before)
        percentage = ('-' if delta < 0 and rounded else '') + decimal_string(rounded) + '%'
    display = {'currency':spec['currency'],'amount_unit':'major','baseline':spec['baseline'],'comparison':spec['comparison'],
               'baseline_amount':decimal_string(before),'comparison_amount':decimal_string(after),'delta_amount':decimal_string(delta),
               'change_percent':percentage,'slide_count':spec['slide_count'],'language':spec['language']}
    return {'analysis':answer,'ledger':records,'display':display}
