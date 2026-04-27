#!/usr/bin/env bash
# Smoke-test the package layout, then run the pytest suite.

set -euo pipefail

PYTHON_BIN="python3"
if [ -x .venv/bin/python ]; then
  PYTHON_BIN=".venv/bin/python"
fi
export PYTHONDONTWRITEBYTECODE=1

"$PYTHON_BIN" -c "
import musecli.cli
import musecli.config
import musecli.journal
import musecli.queue
import musecli.utils
"
"$PYTHON_BIN" -m pytest
