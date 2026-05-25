/**
 * JAI Cron Worker — fires every hour via Cloudflare's scheduler.
 *
 * On each tick it calls POST /jobs/consolidate on the JAI API, which:
 *   1. Runs the nightly summary / reflection / Qdrant pruning (if 24h elapsed)
 *   2. Executes any due scheduled_actions rows for the user
 *
 * Deploy:
 *   cd infra/cloudflare/cron
 *   npx wrangler secret put JAI_MCP_SERVER_TOKEN   # same token as the API
 *   npx wrangler deploy
 */

interface Env {
  JAI_BACKEND_URL: string;
  JAI_MCP_SERVER_TOKEN: string;
}

export default {
  /**
   * Cron handler — triggered by the schedule in wrangler.jsonc.
   */
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runConsolidate(env));
  },

  /**
   * HTTP handler for manual/test triggers:
   *   curl https://jai-cron.<account>.workers.dev/run -H "Authorization: Bearer <token>"
   */
  async fetch(request: Request, env: Env): Promise<Response> {
    const auth = request.headers.get("authorization") ?? "";
    if (auth !== `Bearer ${env.JAI_MCP_SERVER_TOKEN}`) {
      return new Response("Unauthorized", { status: 401 });
    }
    const result = await runConsolidate(env);
    return Response.json(result);
  },
};

async function runConsolidate(env: Env): Promise<unknown> {
  const url = `${env.JAI_BACKEND_URL}/jobs/consolidate`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${env.JAI_MCP_SERVER_TOKEN}`,
    },
  });

  const body = await res.text();
  const ok = res.ok;

  console.log(`[jai-cron] POST ${url} → ${res.status}`, ok ? "" : body.slice(0, 200));

  if (!ok) {
    throw new Error(`consolidate failed: ${res.status} ${body.slice(0, 200)}`);
  }

  return JSON.parse(body);
}
