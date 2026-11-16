"""Build and audit the verdict model. This is not a runtime or agent proof."""

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FORMAL = ROOT / 'formal'
WORK = FORMAL / '.lake/verification'
ALLOWED = {'propext', 'Quot.sound', 'Classical.choice'}


def axiom_map(text):
    pattern = r"'([^']+)' (?:depends on axioms:\s*\[([^\]]*)\]|does not depend on any axioms)"
    return {name: sorted(a.strip() for a in (axioms or '').split(',') if a.strip())
            for name, axioms in re.findall(pattern, text)}


def main():
    report = {'status': 'RUNNING', 'scope': 'Lean mandatory verdict aggregation only',
              'started_at_utc': datetime.now(timezone.utc).isoformat(), 'commands': [],
              'limitations': ['No independent checker replay or sandboxed source build.',
                              'No proof of Python, evidence capture, business checkers or agent performance.']}
    destination = ROOT / '.artifacts/formal-verification.json'
    destination.parent.mkdir(exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)

    def run(label, args, required=True):
        proc = subprocess.run(['lake', *args], cwd=FORMAL, capture_output=True, text=True, timeout=180)
        report['commands'].append({'label':label,'argv':['lake', *args], 'exit_code':proc.returncode,
                                   'stdout':proc.stdout, 'stderr':proc.stderr})
        if required and proc.returncode:
            raise RuntimeError(f'{label} failed: {proc.stdout}{proc.stderr}')
        return proc

    try:
        if not shutil.which('lake'):
            raise RuntimeError('lake is not on PATH; configure the toolchain pinned by formal/lean-toolchain.')
        pin = (FORMAL / 'lean-toolchain').read_text().strip()
        version = run('toolchain', ['env', 'lean', '--version']).stdout
        if f"version {pin.rsplit(':v', 1)[-1]}," not in version:
            raise RuntimeError('Unexpected Lean toolchain version')
        report['toolchain'] = {'pin':pin,'observed':version.strip()}
        run('build', ['--wfail', 'build'])
        sources = sorted((FORMAL / 'Lean4AgentEval').glob('*.lean'))
        declared = ['Lean4AgentEval.' + name for source in sources
                    for name in re.findall(r'^theorem (\w+)', source.read_text(), re.M)]
        audited = re.findall(r'^#print axioms (\S+)', (FORMAL / 'AxiomAudit.lean').read_text(), re.M)
        if not declared or set(declared) != set(audited) or len(audited) != len(set(audited)):
            raise RuntimeError('Every named theorem must be audited exactly once')
        footprints = axiom_map(run('axioms', ['env', 'lean', 'AxiomAudit.lean']).stdout)
        if set(footprints) != set(audited) or any(set(a) - ALLOWED for a in footprints.values()):
            raise RuntimeError('Missing audit output or unapproved axiom dependency')
        report['theorems'] = footprints
        controls = {
            'unknown_pass': ('example : Lean4AgentEval.aggregate [.pass, .unknown] = .pass := by decide\n', None),
            'missing_required': ('example : Lean4AgentEval.evaluateRequired [1, 2] (fun id => if id = 1 then some .pass else none) = .pass := by decide\n', None),
            'custom_axiom': ('axiom inventedTruth : False\ntheorem forged : False := inventedTruth\n#print axioms forged\n', 'inventedTruth'),
            'unfinished': ('theorem unfinished : False := by sorry\n#print axioms unfinished\n', 'sorryAx'),
        }
        report['negative_controls'] = {}
        for name, (body, forbidden) in controls.items():
            path = WORK / f'{name}.lean'
            path.write_text('import Lean4AgentEval\n' + body)
            proc = run(name, ['env', 'lean', str(path.relative_to(FORMAL))], required=False)
            output = proc.stdout + proc.stderr
            if forbidden is None:
                if proc.returncode == 0 or 'decide' not in output or 'false' not in output:
                    raise RuntimeError(f'{name}: did not fail for the intended false proposition')
                report['negative_controls'][name] = 'REJECTED_BY_PROOF_CHECK'
            else:
                found = {a for deps in axiom_map(output).values() for a in deps}
                if proc.returncode != 0 or forbidden not in found or not found - ALLOWED:
                    raise RuntimeError(f'{name}: did not exercise the axiom gate')
                report['negative_controls'][name] = 'REJECTED_BY_AXIOM_POLICY'
        files = [*sources, FORMAL/'Lean4AgentEval.lean', FORMAL/'AxiomAudit.lean',
                 FORMAL/'lean-toolchain', FORMAL/'lakefile.toml', FORMAL/'lake-manifest.json', Path(__file__).resolve()]
        report['source_sha256'] = {str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in files}
        report['status'] = 'PASS_FOR_VERDICT_MODEL'
    except Exception as exc:
        report.update(status='FAILED', error=str(exc))
        raise
    finally:
        report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status':report['status'], 'named_theorems':len(report['theorems']),
                      'negative_controls':report['negative_controls']}, indent=2))


if __name__ == '__main__':
    main()
