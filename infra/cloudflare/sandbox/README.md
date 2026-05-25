# JAI Sandbox (Cloudflare Worker)

Runs untrusted skill scripts (Python / TypeScript / bash) in isolated
containers via `@cloudflare/sandbox`. The JAI backend (`apps/api`) calls this
worker over HTTP to execute generated skills.

## Setup

```bash
cd infra/cloudflare/sandbox
npm install

# set a shared secret used by the backend to call this worker
wrangler secret put SANDBOX_AUTH_TOKEN     # paste a random 32-byte hex string

# local dev (requires Docker)
wrangler dev

# deploy
wrangler deploy
```

Copy the deployed URL into the backend's `.env` as `SANDBOX_BASE_URL` and the
matching secret as `SANDBOX_AUTH_TOKEN`.

## API

`POST /run` — see `src/index.ts` for the wire format.
`DELETE /sandbox/:user_id` — destroy a user's sandbox container.
`GET /health` — liveness.

## Notes

- One sandbox container per `user_id`. Containers sleep after 10 min idle and
  are reused on the next call (warm start).
- Scripts must end with a single JSON line on stdout:
  `{"status":"ok","result":...}` or `{"status":"error","error":"..."}`.
- The Dockerfile pre-installs common Python packages (httpx, google api
  clients, supabase) so skills don't pay cold-install cost.
