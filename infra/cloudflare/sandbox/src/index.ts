/**
 * JAI sandbox worker.
 *
 * POST /run
 *   Auth: Bearer SANDBOX_AUTH_TOKEN (rotated secret, set via `wrangler secret put`)
 *   Body: {
 *     user_id:    string,             // used as sandbox id (one container per user)
 *     skill_id:   string,
 *     language:   "python" | "typescript" | "bash",
 *     source:     string,             // full script
 *     env:        Record<string,string>,  // injected as env vars in the container
 *     timeout_ms: number              // wall clock, default 300_000
 *   }
 *   Returns: {
 *     status:    "ok" | "error",
 *     result:    unknown | null,
 *     stdout:    string,
 *     stderr:    string,
 *     exit_code: number,
 *     duration_ms: number
 *   }
 *
 * DELETE /sandbox/:user_id   destroys the container immediately
 *
 * Re-export `Sandbox` so the Durable Object class binding resolves.
 */

import { getSandbox } from "@cloudflare/sandbox";
export { Sandbox } from "@cloudflare/sandbox";

type Env = {
  Sandbox: DurableObjectNamespace;
  SANDBOX_AUTH_TOKEN?: string;
};

type RunBody = {
  user_id: string;
  skill_id: string;
  language: "python" | "typescript" | "bash";
  source: string;
  env?: Record<string, string>;
  timeout_ms?: number;
};

const FILE_BY_LANG = {
  python: { path: "/workspace/skill.py", cmd: "python /workspace/skill.py" },
  typescript: { path: "/workspace/skill.ts", cmd: "tsx /workspace/skill.ts" },
  bash: { path: "/workspace/skill.sh", cmd: "bash /workspace/skill.sh" },
} as const;

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    if (!authed(req, env)) {
      return json({ error: "unauthorized" }, 401);
    }

    if (req.method === "POST" && url.pathname === "/run") {
      return await runSkill(await req.json<RunBody>(), env);
    }

    if (req.method === "DELETE" && url.pathname.startsWith("/sandbox/")) {
      const user_id = url.pathname.split("/")[2];
      const sb = getSandbox(env.Sandbox, user_id);
      await sb.destroy();
      return json({ ok: true });
    }

    if (req.method === "GET" && url.pathname === "/health") {
      return json({ ok: true, service: "jai-sandbox" });
    }

    return json({ error: "not found" }, 404);
  },
};

function authed(req: Request, env: Env): boolean {
  if (!env.SANDBOX_AUTH_TOKEN) return true; // dev mode
  const got = req.headers.get("authorization")?.replace(/^Bearer\s+/i, "");
  return !!got && got === env.SANDBOX_AUTH_TOKEN;
}

async function runSkill(body: RunBody, env: Env): Promise<Response> {
  const started = Date.now();
  const sb = getSandbox(env.Sandbox, body.user_id);
  const target = FILE_BY_LANG[body.language];
  if (!target) {
    return json({ status: "error", result: null, stdout: "", stderr: `unsupported language: ${body.language}`, exit_code: -1, duration_ms: 0 }, 400);
  }

  await sb.mkdir("/workspace", { recursive: true });
  await sb.writeFile(target.path, body.source);

  const envFlags = Object.entries(body.env ?? {})
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(" ");
  const cmd = envFlags ? `${envFlags} ${target.cmd}` : target.cmd;

  let stdout = "", stderr = "", exit_code = -1;
  try {
    const result = await sb.exec(cmd, { timeout: body.timeout_ms ?? 300_000 });
    stdout = result.stdout ?? "";
    stderr = result.stderr ?? "";
    exit_code = result.exitCode ?? (result.success ? 0 : 1);
  } catch (e) {
    stderr = (e as Error).message;
    exit_code = -1;
  }

  const parsed = parseLastJson(stdout);
  const duration_ms = Date.now() - started;

  return json({
    status: parsed?.status === "ok" ? "ok" : (exit_code === 0 && parsed === null ? "ok" : "error"),
    result: parsed?.result ?? null,
    stdout,
    stderr,
    exit_code,
    duration_ms,
  });
}

function parseLastJson(s: string): { status?: string; result?: unknown; error?: string } | null {
  // Skills must end with a single JSON line. Walk back to find it.
  const lines = s.trim().split("\n");
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i].trim();
    if (line.startsWith("{") && line.endsWith("}")) {
      try { return JSON.parse(line); } catch { /* continue */ }
    }
  }
  return null;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}
