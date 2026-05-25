# Deploy

You have three paths, pick one. The repo is configured for all three.

## Path A — Vercel + Fly + Cloudflare (recommended, cheapest at idle)

Best DX per role. ~$5–15/mo total at low traffic.

```
PWA            → Vercel       (free hobby tier, or $20/mo Pro)
Backend        → Fly.io       ($0 idle, ~$3/mo running, autoscale)
TTS sidecar    → Fly.io       ($0 idle, ~$2/mo)
Sandbox        → Cloudflare   (free tier covers a lot)
DB + Auth      → Supabase     (free / $25 Pro)
Vector / Graph → Qdrant Cloud + Neo4j Aura (free tiers)
```

```bash
# PWA → Vercel
cd apps/web && npx vercel --prod

# Backend + TTS → Fly
./scripts/deploy.sh
```

## Path B — Railway for compute + Cloudflare for sandbox

One platform for both PWA and Python backend. Slightly more expensive
(~$10–20/mo flat for the always-on Python service), but one dashboard, one
bill, one CLI.

```bash
# Both services
railway init                       # creates a project
# Service 1: PWA
railway service create jai-pwa
railway service connect jai-pwa
railway up --service jai-pwa --root apps/web
# Service 2: Backend
railway service create jai-api
railway service connect jai-api
railway up --service jai-api --root apps/api
```

Or in the Railway UI: New Service → GitHub Repo → set Root Directory per
service to `apps/web` or `apps/api`. Both have `railway.toml` configured.

Sandbox still goes to Cloudflare:

```bash
cd infra/cloudflare/sandbox && npx wrangler deploy
```

## Path C — All on Fly.io (most control, lowest cost)

```bash
./scripts/deploy.sh
```

This deploys: backend (`jai-api`), TTS (`jai-tts`), sandbox (Cloudflare),
PWA (Cloudflare Pages). Add a Vercel deploy or Fly static site for the PWA
if you prefer.

## Environment variables in production

Set the entries from `.env.example` as follows:

| Platform | Where |
|---|---|
| **Vercel** | Project Settings → Environment Variables |
| **Railway** | Service → Variables |
| **Fly.io** | `fly secrets set KEY=value --app jai-api` |
| **Cloudflare** | `wrangler secret put KEY` (sandbox), Pages → Settings (PWA) |

The PWA only needs the `NEXT_PUBLIC_*` vars. Everything else lives on the
backend host.

## Custom domain

Pick one host for the PWA and point `jai.yourdomain.com` at it. The backend
can live behind `api.jai.yourdomain.com` or just `jai-api.fly.dev` / the
Railway-provided domain. The PWA reads its backend URL from
`NEXT_PUBLIC_JAI_BACKEND_URL`.
