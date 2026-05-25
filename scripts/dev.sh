#!/usr/bin/env bash
# JAI dev runner — starts API, TTS (docker), and PWA in parallel.
set -e
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
  echo ">> created .env from .env.example — fill in the keys, then re-run"
  exit 1
fi
set -a
. ./.env
set +a

# 1. Kokoro TTS (docker, optional)
if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
  echo ">> starting Kokoro TTS (docker)…"
  (cd infra && docker compose -f docker-compose.dev.yml up -d kokoro) || true
fi

# 2. Backend (uv)
if ! command -v uv >/dev/null; then
  echo ">> installing uv…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

echo ">> syncing Python deps…"
(cd apps/api && uv sync)

# 3. Frontend (pnpm)
if ! command -v pnpm >/dev/null; then
  echo ">> installing pnpm…"
  corepack enable
  corepack prepare pnpm@latest --activate
fi

echo ">> installing JS deps…"
pnpm install

# 4. Run in parallel — kill on Ctrl-C
trap 'kill 0' EXIT INT TERM
(cd apps/api && uv run uvicorn jai_api.main:app --reload --port 8000) &
pnpm --filter @jai/web dev &
wait
