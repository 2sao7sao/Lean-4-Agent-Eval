"""Static contract checks only; this module never certifies an agent run."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


def schema_errors(document, name: str) -> list[str]:
    schema = json.loads((ROOT / 'schemas' / f'{name}.schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    errors = Draft202012Validator(schema).iter_errors(document)
    return [f'{"/".join(map(str, error.absolute_path)) or "/"}: {error.message}'
            for error in sorted(errors, key=lambda e: str(list(e.absolute_path)))]


def validate_contract(contract) -> list[str]:
    """Validate shape and references, not business meaning or approval identity."""
    errors = schema_errors(contract, 'contract')
    if errors:
        return errors

    for collection in ('inputs', 'deliverables', 'requirements', 'evidence_requirements', 'checks'):
        ids = [item['id'] for item in contract[collection]]
        if len(ids) != len(set(ids)):
            errors.append(f'{collection}: duplicate id')

    requirements = {r['id']: r for r in contract['requirements']}
    evidence = {e['id'] for e in contract['evidence_requirements']}
    required_checks = [c for c in contract['checks'] if c['required']]
    if not required_checks:
        errors.append('checks: at least one required check is necessary')
    covered = set()
    for check in contract['checks']:
        for rid in check['requirement_ids']:
            if rid not in requirements:
                errors.append(f'{check["id"]}: unknown requirement {rid}')
        for eid in check['evidence_ids']:
            if eid not in evidence:
                errors.append(f'{check["id"]}: unknown evidence {eid}')
        if check['required']:
            covered.update(check['requirement_ids'])
    for rid, requirement in requirements.items():
        if requirement['mandatory'] and rid not in covered:
            errors.append(f'{rid}: mandatory requirement has no required check')

    if contract['status'] == 'frozen':
        if contract['open_questions']:
            errors.append('frozen: unresolved questions')
        if not contract['approved_by']:
            errors.append('frozen: approval metadata is missing')
        for check in required_checks:
            if check['implementation'] != 'implemented':
                errors.append(f'frozen: verifier not implemented for {check["id"]}')
            if check['method'] == 'model_judge' and not check['parameters'].get('calibration_id'):
                errors.append(f'frozen: missing calibration reference for {check["id"]}')
    return errors
