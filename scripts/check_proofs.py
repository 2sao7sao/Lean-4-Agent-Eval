"""Reproducible checks for the stated Lean model; not an office-agent benchmark.

The project sources are built locally. Exported proof data is replayed in fresh
checker processes. This is not the sandboxed adversarial-source lake check flow.
"""

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".lake/verification"
EVIDENCE = ROOT / "evidence"
ALLOWED = {"propext", "Quot.sound", "Classical.choice"}
PREFIX = ["sh", "scripts/lean.sh"]


def axiom_map(text):
    pattern = r"'([^']+)' (?:depends on axioms:\s*\[([^\]]*)\]|does not depend on any axioms)"
    return {
        name: sorted(x.strip() for x in (axioms or "").split(",") if x.strip())
        for name, axioms in re.findall(pattern, text)
    }


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(exist_ok=True)
    report = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "RUNNING",
        "scope": "Lean mathematical model: integer totals and mandatory verdict aggregation",
        "platform": {"system": platform.system(), "machine": platform.machine()},
        "commands": [],
        "trust_boundaries": [
            "Business intent, source truth and trace completeness are not proved.",
            "No equivalence proof connects the Python lab to the Lean definitions.",
            "The export is produced locally from reviewed project sources, without a build sandbox.",
            "Checker/toolchain implementation correctness remains trusted.",
            "No real agent, PPT rendering or population reliability experiment is performed.",
        ],
    }

    def command(label, args, required=True, output_file=None):
        if output_file is None:
            proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=180)
            stdout = proc.stdout
        else:
            with output_file.open("w") as dest:
                proc = subprocess.run(args, cwd=ROOT, stdout=dest, stderr=subprocess.PIPE,
                                      text=True, timeout=180)
            stdout = f"Export written to {output_file.relative_to(ROOT)}"
        record = {"label": label, "argv": args, "exit_code": proc.returncode,
                  "stdout": stdout, "stderr": proc.stderr}
        report["commands"].append(record)
        if required and proc.returncode != 0:
            raise RuntimeError(f"{label} failed: {stdout}{proc.stderr}")
        return record

    try:
        pinned = (ROOT / "lean-toolchain").read_text().strip()
        version = command("toolchain", PREFIX + ["env", "lean", "--version"])
        if f"version {pinned.rsplit(':v', 1)[-1]}," not in version["stdout"]:
            raise RuntimeError("Loaded Lean version does not match lean-toolchain")
        report["toolchain"] = {"pin": pinned, "observed": version["stdout"].strip()}
        command("build", PREFIX + ["--wfail", "build"])

        audited = re.findall(r"^#print axioms (\S+)", (ROOT / "labs/AxiomAudit.lean").read_text(), re.M)
        declared = ["Lean4Agent." + name for path in sorted((ROOT / "Lean4Agent").glob("*.lean"))
                    for name in re.findall(r"^theorem (\w+)", path.read_text(), re.M)]
        if set(audited) != set(declared) or len(audited) != len(set(audited)):
            raise RuntimeError("Every named theorem must appear exactly once in the audit")
        audit = command("axioms", PREFIX + ["env", "lean", "labs/AxiomAudit.lean"])
        footprints = axiom_map(audit["stdout"])
        if set(footprints) != set(audited):
            raise RuntimeError("Incomplete axiom audit output")
        for name, axioms in footprints.items():
            if not set(axioms) <= ALLOWED:
                raise RuntimeError(f"Forbidden axiom dependency: {name}: {axioms}")
        report["theorems"] = footprints

        exported = WORK / "proofs.ndjson"
        command("export_selected_theorems", PREFIX + ["env", "leanexport", "Lean4Agent", "--", *audited],
                output_file=exported)
        report["proof_export"] = {"path": str(exported.relative_to(ROOT)),
                                  "sha256": digest(exported), "bytes": exported.stat().st_size}
        for label, args in [
            ("kernel_replay", ["leanchecker", "--from-export"]),
            ("paranoid_kernel_replay", ["leanchecker-paranoid", "--from-export"]),
            ("lean4lean_replay", ["lean4lean", "--import"]),
        ]:
            command(label, PREFIX + ["env", *args, str(exported.relative_to(ROOT))])
        report["sandboxed_lake_check"] = {
            "status": "NOT_RUN_BY_THIS_SCRIPT",
            "note": "The macOS setup probe returned exit 2: lake check requires bwrap/Linux namespaces. "
                    "This script replays proof exports, not sandboxed source builds.",
        }

        controls = {
            "wrong_total": ("example : Lean4Agent.checkTotal [10000, 20000, -2000] 30000 = true := by decide\n", None),
            "unknown_pass": ("example : Lean4Agent.aggregate [.pass, .unknown] = .pass := by decide\n", None),
            "omitted_required_check": ("example : Lean4Agent.evaluateRequired [1, 2] (fun id => if id = 1 then some .pass else none) = .pass := by decide\n", None),
            "custom_axiom": ("axiom inventedTruth : False\ntheorem forged : False := inventedTruth\n#print axioms forged\n", "inventedTruth"),
            "unfinished": ("theorem unfinished : False := by sorry\n#print axioms unfinished\n", "sorryAx"),
        }
        report["negative_controls"] = {}
        for name, (body, forbidden) in controls.items():
            path = WORK / (name + ".lean")
            path.write_text("import Lean4Agent\n" + body)
            result = command("negative_" + name, PREFIX + ["env", "lean", str(path.relative_to(ROOT))], required=False)
            if forbidden is None:
                # Require the intended false-proposition diagnostic, not a parser/import error.
                if result["exit_code"] == 0 or "decide" not in result["stdout"] or "false" not in result["stdout"]:
                    raise RuntimeError(f"Negative control {name} did not fail for the intended reason")
                report["negative_controls"][name] = "REJECTED_BY_PROOF_CHECK"
            else:
                found = {a for values in axiom_map(result["stdout"]).values() for a in values}
                if result["exit_code"] != 0 or forbidden not in found or not (found - ALLOWED):
                    raise RuntimeError(f"Negative control {name} did not exercise the axiom gate")
                report["negative_controls"][name] = "COMPILES_BUT_REJECTED_BY_AXIOM_POLICY"

        lab = command("offline_python_regression", [sys.executable, "labs/01_contract_lab.py"])
        lab_data = json.loads(lab["stdout"])
        report["python_regression"] = {
            "scenarios": lab_data["scenario_expectations_matched"],
            "boundary_checks": lab_data["additional_boundary_checks_matched"],
            "scope": "synthetic fixtures only; not formally verified Python",
        }
        # The structured Python report already exists separately; keep this receipt compact.
        lab["stdout"] = "Synthetic regression output parsed successfully; see python_regression."
        source_paths = [ROOT / "Lean4Agent.lean", *(ROOT / "Lean4Agent").glob("*.lean"),
                        ROOT / "labs/AxiomAudit.lean", ROOT / "labs/01_contract_lab.py",
                        ROOT / "lean-toolchain", ROOT / "lakefile.toml", ROOT / "lake-manifest.json",
                        Path(__file__).resolve(), ROOT / "scripts/lean.sh"]
        report["source_sha256"] = {str(p.relative_to(ROOT)): digest(p) for p in sorted(source_paths)}
        report["status"] = "PASS_FOR_STATED_FORMAL_SCOPE"
    except Exception as exc:
        report["status"] = "FAILED"
        report["error"] = str(exc)
        raise
    finally:
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        (EVIDENCE / "formal_verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "theorems": len(report["theorems"]),
                      "negative_controls": report["negative_controls"],
                      "python_regression": report["python_regression"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
