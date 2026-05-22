#!/usr/bin/env bash
# ./make path/to/input.json [extra pipeline.py flags...]
#
# Activates the project venv and runs the pipeline.

set -euo pipefail

cd "$(cd "$(dirname "$0")" && pwd)"

if [ ! -x .venv/bin/python ]; then
  echo "❌ .venv missing. Run ./run first." >&2
  exit 1
fi

if [ $# -lt 1 ]; then
  cat >&2 <<'EOF'
Usage: ./make <inputs...> [--no-intro] [--no-bgm] [--stop-on-error] [-v]

Inputs can be:
  • one .json file       ./make in/ep01.json
  • many .json files     ./make in/ep01.json in/ep02.json
  • a shell glob         ./make in/*.json
  • a directory          ./make in            (renders every *.json inside)

Run ./make -h for the full flag list.
EOF
  exit 2
fi

exec .venv/bin/python pipeline.py "$@"
