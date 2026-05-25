#!/usr/bin/env bash
# Regenerate TS types from FastAPI's OpenAPI schema.
#
# Strategy: boot the API in a temporary subshell, wait until it answers,
# dump /openapi.json, kill it, then run openapi-typescript.
#
# Usage: pnpm gen:types
#        or: ./scripts/gen-types.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/packages/shared-types/src/generated/api.ts"
PORT="${JAI_GEN_PORT:-8765}"
SCHEMA="$ROOT/.jai-openapi.json"

cleanup() {
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
  fi
  rm -f "$SCHEMA"
}
trap cleanup EXIT

mkdir -p "$(dirname "$OUT")"

echo "→ Booting FastAPI on :$PORT (schema-only, no external services hit)…"

(
  cd "$ROOT/apps/api"
  JAI_USER_ID="00000000-0000-0000-0000-000000000000" \
    SUPABASE_JWT_SECRET="dev-skip" \
    uv run uvicorn jai_api.main:app --host 127.0.0.1 --port "$PORT" \
      >/tmp/jai-gen.log 2>&1
) &
SERVER_PID=$!

for i in {1..40}; do
  if curl -sf "http://127.0.0.1:$PORT/openapi.json" -o "$SCHEMA" 2>/dev/null; then
    echo "→ Got schema after ${i}× try."
    break
  fi
  sleep 0.3
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "✗ API died during startup. Tail of /tmp/jai-gen.log:"
    tail -n 30 /tmp/jai-gen.log
    exit 1
  fi
done

if [[ ! -s "$SCHEMA" ]]; then
  echo "✗ Failed to fetch /openapi.json after ~12s."
  tail -n 30 /tmp/jai-gen.log
  exit 1
fi

echo "→ Running openapi-typescript…"
npx --yes -p openapi-typescript@7 openapi-typescript "$SCHEMA" -o "$OUT"

echo "✓ Wrote $(wc -l < "$OUT") lines to $OUT"
