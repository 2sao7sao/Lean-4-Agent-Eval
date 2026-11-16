"""Validate repository assets; not an agent benchmark or a general CSV verifier."""

import csv
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'examples/sales-to-ppt'
sys.path.insert(0, str(ROOT / 'src'))
from lean4_agent_eval.contracts import validate_contract


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_reference():
    """Independently recompute the small, fixed baseline fixture's numeric oracle."""
    source = EXAMPLE / 'input/sales.csv'
    reference = json.loads((EXAMPLE / 'reference.json').read_text())
    require(sha256(source.read_bytes()).hexdigest() == reference['input_sha256'], 'Input hash mismatch')
    totals = {'2026-09': 0, '2026-10': 0}
    groups = {month: {} for month in totals}
    seen = set()
    with source.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    require(bool(rows), 'Empty baseline fixture')
    for row in rows:
        require(all(row.values()), 'Missing fixture value')
        require(row['order_id'] not in seen, 'Duplicate order ID')
        seen.add(row['order_id'])
        month = date.fromisoformat(row['business_date']).strftime('%Y-%m')
        require(month in totals, 'Unexpected month in baseline')
        require(row['currency'] == 'CNY', 'Mixed currency')
        require(row['payment_status'] in ('paid', 'cancelled', 'unpaid'), 'Unknown payment status')
        gross, refund = int(row['gross_minor']), int(row['refund_minor'])
        require(0 <= refund <= gross, 'Invalid refund or gross amount')
        if row['payment_status'] == 'paid':
            net = gross - refund
            totals[month] += net
            region = row['region']
            groups[month][region] = groups[month].get(region, 0) + net
    delta = totals['2026-10'] - totals['2026-09']
    require(totals['2026-09'] != 0, 'Baseline oracle expects a nonzero previous month')
    ratio = Fraction(delta, totals['2026-09'])
    regions = set(groups['2026-09']) | set(groups['2026-10'])
    region_delta = {r: groups['2026-10'].get(r, 0) - groups['2026-09'].get(r, 0) for r in regions}
    require(reference['currency'] == 'CNY' and reference['amount_unit'] == 'minor', 'Oracle unit mismatch')
    require(totals == reference['monthly_net_minor'], 'Oracle monthly total mismatch')
    require(delta == reference['delta_minor'], 'Oracle delta mismatch')
    require({'numerator': ratio.numerator, 'denominator': ratio.denominator} == reference['change_ratio'], 'Oracle ratio mismatch')
    require(region_delta == reference['region_delta_minor'], 'Oracle region mismatch')
    require(sum(region_delta.values()) == delta, 'Groups do not reconcile')
    display = {
        'baseline_yuan': f'{Decimal(totals["2026-09"]) / 100:.2f}',
        'comparison_yuan': f'{Decimal(totals["2026-10"]) / 100:.2f}',
        'delta_yuan': f'{Decimal(delta) / 100:.2f}',
        'change_percent': str((Decimal(delta) / Decimal(totals['2026-09']) * 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) + '%',
    }
    require(display == reference['display'], 'Oracle display mismatch')
    return {'rows': len(rows), 'monthly_net_minor': totals, 'delta_minor': delta}


def main():
    for schema_path in (ROOT / 'schemas').glob('*.schema.json'):
        Draft202012Validator.check_schema(json.loads(schema_path.read_text()))
    contract = json.loads((EXAMPLE / 'contract.json').read_text())
    issues = validate_contract(contract)
    require(not issues, '\n'.join(issues))
    require((EXAMPLE / contract['source_request']).is_file(), 'Missing source request')
    for item in contract['inputs']:
        require((EXAMPLE / item['path']).is_file(), f'Missing input: {item["path"]}')
    plan = json.loads((EXAMPLE / 'case-plan.json').read_text())
    require(plan['contract_id'] == contract['contract_id'] and plan['contract_version'] == contract['version'], 'Case plan contract mismatch')
    require(plan['status'] == 'design_only' and plan['split'] == 'development', 'Unexpected sample maturity')
    ids = [case['id'] for case in plan['cases']]
    require(len(ids) == len(set(ids)) and bool(ids), 'Empty or duplicate scenario IDs')
    requirements = {r['id'] for r in contract['requirements']}
    covered = set()
    for case in plan['cases']:
        require(case['kind'] in ('agent_scenario', 'verifier_control'), 'Unknown case kind')
        require(bool(case['requirement_ids']) and set(case['requirement_ids']) <= requirements, 'Invalid case requirement references')
        require(case['materialization'] == 'planned', 'Sample must not claim unperformed execution')
        covered.update(case['requirement_ids'])
    require(requirements <= covered, 'Case plan misses a requirement')
    numeric = check_reference()

    for document in [ROOT / 'README.md', *(ROOT / 'docs').glob('*.md'), *EXAMPLE.glob('*.md')]:
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', document.read_text()):
            if target.startswith(('http:', 'https:', '#', 'mailto:')):
                continue
            relative = unquote(target.split('#', 1)[0])
            require((document.parent / relative).exists(), f'Broken link: {document.relative_to(ROOT)} -> {target}')

    print(json.dumps({'status': 'PASS_FOR_REPOSITORY_ASSETS',
                      'scope': 'Static contracts, reference fixture, coverage-plan references and local document links only.',
                      'requirements': len(contract['requirements']), 'required_checks': sum(c['required'] for c in contract['checks']),
                      'planned_cases': len(plan['cases']), 'reference': numeric,
                      'agent_execution': 'NOT_PERFORMED', 'ppt_validation': 'NOT_IMPLEMENTED'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
