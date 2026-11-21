#!/usr/bin/env bash
# Start de boekhouding (macOS / Linux). Eerste keer maakt hij een virtualenv aan.
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv && .venv/bin/pip install -q -e .
fi
( sleep 1.5 && (open http://127.0.0.1:5000 2>/dev/null || xdg-open http://127.0.0.1:5000 2>/dev/null) ) &
exec .venv/bin/python -m boekhouding
