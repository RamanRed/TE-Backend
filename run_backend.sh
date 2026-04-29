#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"

if [[ -x "${VENV_DIR}/bin/python" ]]; then
  PYTHON_BIN="${PYTHON_BIN:-${VENV_DIR}/bin/python}"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="${PYTHON_BIN:-python3}"
else
  PYTHON_BIN="${PYTHON_BIN:-python}"
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Error: ${PYTHON_BIN} is not available. Install Python 3.13+ or set PYTHON_BIN." >&2
  exit 1
fi

cd "${ROOT_DIR}"

export PYTHONPATH="${ROOT_DIR}:${PYTHONPATH:-}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"
export API_HOST="${API_HOST:-0.0.0.0}"
export API_PORT="${API_PORT:-8000}"
export DEBUG="${DEBUG:-false}"

if ! "${PYTHON_BIN}" - <<'PY' >/dev/null 2>&1
import importlib.util
required = ("uvicorn", "fastapi", "pydantic")
missing = [name for name in required if importlib.util.find_spec(name) is None]
raise SystemExit(1 if missing else 0)
PY
then
  echo "Error: backend dependencies are not installed for ${PYTHON_BIN}." >&2
  echo "Run: cd ${ROOT_DIR} && ${PYTHON_BIN} -m pip install -r requirements.txt" >&2
  exit 1
fi

echo "Starting backend from ${ROOT_DIR}"
echo "Using ${PYTHON_BIN}"
echo "API_HOST=${API_HOST} API_PORT=${API_PORT} LOG_LEVEL=${LOG_LEVEL} DEBUG=${DEBUG}"

exec "${PYTHON_BIN}" -m uvicorn src.api.app:app \
  --host "${API_HOST}" \
  --port "${API_PORT}" \
  --log-level "$(printf '%s' "${LOG_LEVEL}" | tr '[:upper:]' '[:lower:]')" \
  $([[ "${DEBUG}" == "true" ]] && printf '%s' "--reload")
