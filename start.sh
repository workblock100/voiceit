#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ -f .env ]; then
  set -a; source .env; set +a
fi

if [ -z "$ELEVENLABS_API_KEY" ]; then
  echo "ELEVENLABS_API_KEY not set. Add it to ~/voiceit/.env:"
  echo "  ELEVENLABS_API_KEY=sk_your_new_key_here"
  exit 1
fi

source .venv/bin/activate
export PYTHONUNBUFFERED=1
exec python3 voiceit.py 2>&1 | tee /tmp/voiceit.log
