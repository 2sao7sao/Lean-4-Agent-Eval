"""Static contract checks only; this module never certifies an agent run."""

import copy
from hashlib import sha256
import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


def review_hash(contract):
    """Hash the complete proposed contract, excluding only the confirmation itself."""
    candidate = copy.deepcopy(contract)
    if 'intake' in candidate:
        candidate['intake']['requirements_confirmation'] = None
    encoded = json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return sha256(encoded.encode('utf-8')).hexdigest()


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

    intake = contract.get('intake')
    if intake:
        if set(intake['facts']) != set(intake['provenance']):
            errors.append('intake: each fact must have provenance')
        confirmation = intake['requirements_confirmation']
        if confirmation and confirmation['review_sha256'] != review_hash(contract):
            errors.append('intake: confirmation does not match the reviewed contract')

    if contract['status'] == 'frozen':
        if intake and not intake['requirements_confirmation']:
            errors.append('frozen: generated requirements have not been confirmed')
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
