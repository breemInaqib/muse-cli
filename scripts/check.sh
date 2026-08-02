#!/usr/bin/env bash
# Smoke-test the package layout, then run the pytest suite.

set -euo pipefail

PYTHON_BIN="${MUSE_PYTHON_BIN:-python3}"
if [ -z "${MUSE_PYTHON_BIN:-}" ] && [ -x .venv/bin/python ]; then
  PYTHON_BIN=".venv/bin/python"
fi
export PYTHONDONTWRITEBYTECODE=1

"$PYTHON_BIN" -c "
import musecli.cli
import musecli.code_cli
import musecli.config
import musecli.journal
import musecli.queue
import musecli.session
import musecli.interactive
import musecli.tui
import musecli.utils
import musecli.workflow_index
import musecli.workflow_view
import musecli.agent.audit
import musecli.agent.contracts
import musecli.agent.evaluation
import musecli.agent.harness
import musecli.agent.permissions
"
"$PYTHON_BIN" -m pytest
