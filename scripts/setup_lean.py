"""Install the pinned Lean toolchain locally on this project's Apple Silicon Mac."""

from hashlib import sha256
import os
from pathlib import Path
import platform
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ELAN_VERSION = "v4.2.4"
ELAN_ARCHIVE = "elan-aarch64-apple-darwin.tar.gz"
ELAN_SHA256 = "7ad829861392c718dfebde3a83b5c8508df47be02af68894b094b0b3952616e5"


def main():
    if (platform.system(), platform.machine()) != ("Darwin", "arm64"):
        raise SystemExit("This bootstrap targets macOS arm64; use official elan for other platforms.")
    downloads = ROOT / ".tools/downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    archive = downloads / ELAN_ARCHIVE
    if not archive.exists() or sha256(archive.read_bytes()).hexdigest() != ELAN_SHA256:
        subprocess.run([
            "curl", "--fail", "--location", "--silent", "--show-error",
            "--retry", "2", "--connect-timeout", "20", "--max-time", "120",
            "--output", str(archive),
            f"https://github.com/leanprover/elan/releases/download/{ELAN_VERSION}/{ELAN_ARCHIVE}",
        ], check=True)
    if sha256(archive.read_bytes()).hexdigest() != ELAN_SHA256:
        raise SystemExit("Elan installer archive failed its pinned SHA-256 check.")
    env = os.environ.copy()
    env["ELAN_HOME"] = str(ROOT / ".tools/elan")
    elan = ROOT / ".tools/elan/bin/elan"
    if not elan.exists():
        subprocess.run(["tar", "-xzf", str(archive), "-C", str(downloads)], check=True)
        subprocess.run([
            str(downloads / "elan-init"), "-y", "--no-modify-path",
            "--default-toolchain", "none",
        ], env=env, check=True)
    toolchain = (ROOT / "lean-toolchain").read_text().strip()
    subprocess.run([str(elan), "toolchain", "install", toolchain], env=env, cwd=ROOT, check=True)
    subprocess.run(["sh", "scripts/lean.sh", "env", "lean", "--version"], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
