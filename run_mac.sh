#!/bin/bash
# 빌드 없이 맥에서 바로 실행 (개발/테스트용)
set -euo pipefail
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
if [ ! -d .venv-mac ]; then
  "$PY" -m venv .venv-mac
  .venv-mac/bin/python -m pip install --quiet --upgrade pip
  .venv-mac/bin/python -m pip install --quiet pywebview pyobjc-framework-CoreWLAN pyobjc-framework-CoreLocation
fi
exec .venv-mac/bin/python app.py "$@"
