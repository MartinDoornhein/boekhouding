#!/usr/bin/env bash
# Start de boekhouding (macOS / Linux). Eerste keer maakt hij een virtualenv aan.
#
# Met een ingevulde .env (zie .env.example) en Litestream geïnstalleerd:
#  - ontbreekt de database lokaal, dan wordt hij eerst hersteld vanaf Scaleway;
#  - daarna draait de app onder Litestream, dat elke wijziging direct repliceert.
set -euo pipefail
cd "$(dirname "$0")"

if [ -f .env ]; then set -a; . ./.env; set +a; fi
export BOEKHOUDING_DATA="${BOEKHOUDING_DATA:-$PWD/data}"
export BOEKHOUDING_DB="$BOEKHOUDING_DATA/boekhouding.db"
URL="http://127.0.0.1:${BOEKHOUDING_PORT:-5050}"

if [ ! -d .venv ]; then
  python3 -m venv .venv && .venv/bin/pip install -q -e .
fi

open_browser() {
  ( sleep 1.5 && (open "$URL" 2>/dev/null || xdg-open "$URL" 2>/dev/null) ) &
}

if [ -n "${BOEKHOUDING_S3_BUCKET:-}" ]; then
  if ! command -v litestream >/dev/null; then
    echo "Litestream niet gevonden. Installeer met 'brew install litestream'" >&2
    echo "of via https://github.com/benbjohnson/litestream/releases" >&2
    exit 1
  fi
  mkdir -p "$BOEKHOUDING_DATA"
  litestream restore -config litestream.yml -if-db-not-exists -if-replica-exists "$BOEKHOUDING_DB"
  open_browser
  exec litestream replicate -config litestream.yml -exec ".venv/bin/python -m boekhouding"
else
  echo "Let op: geen BOEKHOUDING_S3_BUCKET in .env; de database wordt NIET naar Scaleway gerepliceerd." >&2
  open_browser
  exec .venv/bin/python -m boekhouding
fi
