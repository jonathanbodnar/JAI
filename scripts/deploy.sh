#!/usr/bin/env bash
# Manual one-shot deploy. Requires flyctl, wrangler, supabase, pnpm.
set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf "\n\033[1;35m>>>\033[0m \033[1m%s\033[0m\n" "$1"; }

if [ ! -f .env ]; then
  echo "no .env; aborting"; exit 1
fi
set -a; . ./.env; set +a

step "1/5  Supabase migrations"
supabase db push --linked

step "2/5  Backend → Fly.io (apps/api)"
(cd apps/api && fly deploy --remote-only)

step "3/5  TTS sidecar → Fly.io (apps/tts)"
(cd apps/tts && fly deploy --remote-only || echo "(skip if already deployed)")

step "4/5  Sandbox worker → Cloudflare (infra/cloudflare/sandbox)"
(cd infra/cloudflare/sandbox && npm install --silent && npx wrangler deploy)

step "5/5  PWA → Cloudflare Pages (apps/web)"
pnpm install --silent
pnpm --filter @jai/web build
(cd apps/web && npx wrangler pages deploy .next --project-name jai-pwa)

echo
echo "Done. Open the Pages URL, sign in, and start talking."
