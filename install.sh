#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$SCRIPT_DIR/requirements.txt"

# openWakeWord 0.6 declares tflite-runtime on Linux, but tflite-runtime has no
# Python 3.12 wheel. This client explicitly uses ONNX Runtime, so TFLite is not
# needed and is intentionally omitted.
"$VENV_DIR/bin/python" -m pip install --no-deps "openwakeword==0.6.0"

"$VENV_DIR/bin/python" - <<'PY'
import numpy
import openwakeword
import onnxruntime
import requests
import sounddevice
print("Cài đặt thành công.")
PY
