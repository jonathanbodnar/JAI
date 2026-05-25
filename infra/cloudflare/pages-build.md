# Cloudflare Pages — JAI PWA

Pages can build the Next.js app directly. Connect this repo, then use:

| Setting | Value |
|---|---|
| Framework preset | Next.js |
| Build command | `pnpm install && pnpm --filter @jai/web build` |
| Build output directory | `apps/web/.next` |
| Root directory | `/` |

## Environment variables (set in Pages → Settings → Variables)

```
NEXT_PUBLIC_JAI_BACKEND_URL  = https://jai-api.fly.dev
NEXT_PUBLIC_SUPABASE_URL     = https://<your-project>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY= <anon key>
```

## Custom domain

Add `jai.yourdomain.com` to the Pages project, then add a CNAME in Cloudflare
DNS pointing at the `.pages.dev` URL Cloudflare gives you. HTTPS is automatic.

## iOS install

After the domain is live, open in Mobile Safari → Share → Add to Home Screen.
The app appears full-screen with mic permissions on first use.
