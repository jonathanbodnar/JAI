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

import { getSandbox, Sandbox as _SandboxClass } from "@cloudflare/sandbox";
export { Sandbox } from "@cloudflare/sandbox";

type Env = {
  Sandbox: DurableObjectNamespace<_SandboxClass>;
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

const ENV_FILE = "/workspace/.env.json";

// Bootstrap snippets injected at the top of every script so env vars get
// loaded from a JSON file instead of shell-escaped on the command line.
// OAuth token blobs and other long JSON values shred the bash quoter; a
// JSON file is bulletproof regardless of the value content.
const PRELUDE: Record<keyof typeof FILE_BY_LANG, string> = {
  python:
    "import os, json\n" +
    "try:\n" +
    `    with open(${JSON.stringify(ENV_FILE)}) as _f:\n` +
    "        for _k, _v in json.load(_f).items():\n" +
    "            if isinstance(_v, str):\n" +
    "                os.environ[_k] = _v\n" +
    "except Exception:\n" +
    "    pass\n",
  typescript:
    `import fs from "node:fs"; try { const _e = JSON.parse(fs.readFileSync(${JSON.stringify(
      ENV_FILE,
    )}, "utf8")); for (const [k, v] of Object.entries(_e)) { if (typeof v === "string") process.env[k] = v; } } catch {}\n`,
  bash:
    `# bash skills can load env vars via:\n` +
    `#   eval "$(python3 -c 'import json,os,shlex; j=json.load(open(\\"${ENV_FILE}\\")); [print(f\"export {k}={shlex.quote(v)}\") for k,v in j.items() if isinstance(v,str)]')"\n`,
};

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    try {
      const url = new URL(req.url);

      if (!authed(req, env)) {
        return json({ error: "unauthorized" }, 401);
      }

      if (req.method === "POST" && url.pathname === "/run") {
        let body: RunBody;
        try {
          body = await req.json<RunBody>();
        } catch (e) {
          return json(errorResult(`invalid json body: ${(e as Error).message}`), 200);
        }
        return await runSkill(body, env);
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
    } catch (e) {
      // Top-level safety net — never let the worker throw a raw 500 with no
      // body. Returning a 200 with status:"error" lets the API surface the
      // actual problem to the user instead of "Server error '500'".
      const msg = (e as Error)?.stack || (e as Error)?.message || String(e);
      return json(errorResult(`sandbox worker crashed: ${msg}`), 200);
    }
  },
};

function errorResult(stderr: string) {
  return {
    status: "error",
    result: null,
    stdout: "",
    stderr,
    exit_code: -1,
    duration_ms: 0,
  };
}

function authed(req: Request, env: Env): boolean {
  if (!env.SANDBOX_AUTH_TOKEN) return true; // dev mode
  const got = req.headers.get("authorization")?.replace(/^Bearer\s+/i, "");
  return !!got && got === env.SANDBOX_AUTH_TOKEN;
}

async function runSkill(body: RunBody, env: Env): Promise<Response> {
  const started = Date.now();

  if (!body || typeof body.source !== "string" || typeof body.user_id !== "string") {
    return json(errorResult("missing required body fields (user_id, source)"), 200);
  }

  const target = FILE_BY_LANG[body.language];
  if (!target) {
    return json(errorResult(`unsupported language: ${body.language}`), 200);
  }

  let stdout = "", stderr = "", exit_code = -1;
  try {
    const sb = getSandbox(env.Sandbox, body.user_id);
    await sb.mkdir("/workspace", { recursive: true });

    // Env vars come via a JSON file so OAuth blobs / multi-line values don't
    // get mangled by bash. The prelude (prepended below) reads this file
    // and stuffs everything into the runtime env.
    const envObj = body.env ?? {};
    await sb.writeFile(ENV_FILE, JSON.stringify(envObj));

    const prelude = PRELUDE[body.language];
    await sb.writeFile(target.path, prelude + body.source);

    const result = await sb.exec(target.cmd, { timeout: body.timeout_ms ?? 300_000 });
    stdout = result.stdout ?? "";
    stderr = result.stderr ?? "";
    exit_code = result.exitCode ?? (result.success ? 0 : 1);
  } catch (e) {
    // sb.mkdir / sb.writeFile / sb.exec can throw if the container fails to
    // boot or the SDK can't reach it. Surface that as a structured error
    // instead of letting the worker 500.
    stderr = `sandbox host error: ${(e as Error)?.message || String(e)}`;
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
