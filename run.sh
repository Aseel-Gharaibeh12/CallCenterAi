#!/bin/bash
set -e
echo "Pipecat demo - FREE GROQ version"
cd "$(dirname "$0")"
if [ ! -f .env ] || ! grep -q GROQ_API_KEY .env; then
  read -s -p "Paste your free Groq API key (starts with gsk_): " KEY; echo
  echo "GROQ_API_KEY=$KEY" > .env
fi
if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
if [ ! -d .venv ]; then
  uv venv -p 3.12 .venv
  uv pip install --python .venv/bin/python -r requirements.txt --override overrides.txt \
    --only-binary onnxruntime --only-binary cryptography --only-binary av \
    --only-binary numpy --only-binary numba --only-binary llvmlite --only-binary opencv-python-headless \
    || { echo "Install failed - cleaning up so you can retry."; rm -rf .venv; exit 1; }
fi
echo "Starting... open http://localhost:7860 in Chrome, allow the mic, click Connect."
.venv/bin/python bot.py
