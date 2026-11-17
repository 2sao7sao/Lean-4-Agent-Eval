"""Narrow offline graders. PASS here never means the complete task passed."""

from .contracts import schema_errors


def _receipt(verdict, scope, reasons):
    return {'verdict':verdict, 'scope':scope, 'reasons':reasons,
            'full_contract_verdict':'NOT_ASSESSED', 'formal_verification':'NOT_PROVED'}


def grade_analysis(candidate, reference):
    expected = reference.get('analysis') if isinstance(reference, dict) else None
    if schema_errors(expected, 'sales-analysis'):
        return _receipt('ERROR','numerical_or_clarification_envelope',['Invalid evaluator reference.'])
    if candidate is None:
        return _receipt('UNKNOWN','numerical_or_clarification_envelope',['Submission evidence not supplied.'])
    errors = schema_errors(candidate, 'sales-analysis')
    if errors:
        return _receipt('FAIL','numerical_or_clarification_envelope',['Submitted numerical envelope violates the schema.'])
    failures = []
    for key in ('input_sha256','status'):
        if candidate[key] != expected[key]:
            failures.append(key + ' mismatch')
    if not failures:
        if expected['status'] == 'needs_clarification':
            if set(candidate['issues']) != set(expected['issues']):
                failures.append('clarification issues mismatch')
        else:
            for key in ('currency','amount_unit','monthly_minor','delta_minor','groups','row_count','included_count'):
                if candidate[key] != expected[key]:
                    failures.append(key + ' mismatch')
            got, want = candidate['change_ratio'], expected['change_ratio']
            if got is None or want is None:
                if got != want:
                    failures.append('zero-baseline ratio must be undefined')
            elif got['numerator'] * want['denominator'] != want['numerator'] * got['denominator']:
                failures.append('change_ratio mismatch')
    return _receipt('FAIL' if failures else 'PASS','numerical_or_clarification_envelope',failures)


def grade_presentation_projection(candidate, reference):
    """Only synthetic extracted facts; no PPTX parsing or rendering takes place."""
    scope = 'synthetic_presentation_summary_fields_only'
    if candidate is None:
        return _receipt('UNKNOWN',scope,['No presentation extraction evidence.'])
    if not isinstance(candidate, dict) or candidate.get('kind') != 'synthetic_presentation_projection':
        return _receipt('ERROR',scope,['Expected a synthetic evaluator projection, not agent claims or a PPT file.'])
    if candidate.get('extraction_status') == 'error':
        return _receipt('ERROR',scope,['Simulated evaluator extraction failure.'])
    if candidate.get('extraction_status') != 'complete':
        return _receipt('UNKNOWN',scope,['Extraction is incomplete.'])
    if not isinstance(reference, dict) or not isinstance(reference.get('display'), dict):
        return _receipt('ERROR',scope,['No complete numeric presentation reference.'])
    expected = reference['display']
    values = candidate.get('facts')
    failures = []
    if not isinstance(values, dict):
        failures.append('Missing extracted summary fields')
    else:
        for key, value in expected.items():
            if key not in values or type(values[key]) is not type(value) or values[key] != value:
                failures.append(key + ' mismatch')
    return _receipt('FAIL' if failures else 'PASS',scope,failures)
