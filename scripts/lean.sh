#!/bin/sh
# Use the project-local elan installation and the checked-in lean-toolchain.
set -eu
LEAN4AGENT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export ELAN_HOME="$LEAN4AGENT_ROOT/.tools/elan"
export PATH="$ELAN_HOME/bin:$PATH"
cd "$LEAN4AGENT_ROOT"
if [ ! -x "$ELAN_HOME/bin/lake" ]; then
  echo "Project-local Lean is missing; see docs/06_first_verified_rules.md." >&2
  exit 1
fi
exec "$ELAN_HOME/bin/lake" "$@"
