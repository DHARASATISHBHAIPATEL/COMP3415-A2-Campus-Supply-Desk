#!/bin/sh
# Usage: sh evidence/run_tests.sh "<label>" evidence/<file>.txt
# Records date, Python version and commit with the full verbose test output.
label="$1"; out="$2"
{
  echo "# $label"
  echo "# date: $(date -u +%Y-%m-%dT%H:%M:%SZ)  $(python3 --version 2>&1)  commit: $(git rev-parse --short HEAD)"
  python3 -m unittest discover -s tests -v 2>&1
  echo "exit status: $?"
} > "$out"
tail -4 "$out"
