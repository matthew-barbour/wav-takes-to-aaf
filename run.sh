#!/usr/bin/env bash
#
# run.sh — initialize the environment and run wav-takes-to-aaf on a session folder.
#
# Usage:
#   ./run.sh /path/to/session                 # preview only (no AAF written)
#   ./run.sh /path/to/session --write         # write the AAF
#   ./run.sh /path/to/session --write --gap-seconds 30 -o /path/out.aaf
#
# Any flags after the folder are passed straight through to the tool.
#
set -euo pipefail

# Always operate relative to this script's location so it works from anywhere.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 /path/to/session [--write] [other options]" >&2
  exit 1
fi

# Pick a Python 3.9+ interpreter.
PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Error: '$PYTHON' not found. Install Python 3.9+ (e.g. 'brew install python')." >&2
  exit 1
fi

# Create the virtual environment once.
if [ ! -d ".venv" ]; then
  echo ">> Creating virtual environment in .venv ..."
  "$PYTHON" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# Install (or update) the package and its dependencies. Marker file avoids
# reinstalling on every run; delete .venv/.installed to force a refresh.
if [ ! -f ".venv/.installed" ]; then
  echo ">> Installing wav-takes-to-aaf and dependencies ..."
  pip install --upgrade pip >/dev/null
  pip install -e .
  touch .venv/.installed
fi

echo ">> Running wav-takes-to-aaf ..."
exec wav-takes-to-aaf "$@"
