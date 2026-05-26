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
  // Cloudflare's official sandbox image ships `python3` only — there is no
  // bare `python` symlink. Invoking the wrong binary fails with
  // "python: command not found" before the script even gets a chance to run.
  python: { path: "/workspace/skill.py", cmd: "python3 /workspace/skill.py" },
  typescript: { path: "/workspace/skill.ts", cmd: "tsx /workspace/skill.ts" },
  bash: { path: "/workspace/skill.sh", cmd: "bash /workspace/skill.sh" },
} as const;

const ENV_FILE = "/workspace/.env.json";
const PIP_MARKER = "/workspace/.pip-installed";
const NPM_MARKER = "/workspace/.npm-installed";

// Packages JAI skills routinely need. Installed lazily on first run per
// container instance and then cached (via the marker file) so subsequent
// runs skip straight to executing the user script.
const PIP_PACKAGES = [
  "httpx",
  "pydantic",
  "google-api-python-client",
  "google-auth",
  "google-auth-oauthlib",
  "google-auth-httplib2",
  "notion-client",
  "slack-sdk",
  "supabase",
  "beautifulsoup4",
  "python-dateutil",
].join(" ");

const NPM_PACKAGES = ["tsx", "typescript"].join(" ");

// Bootstrap snippets injected at the top of every script:
//   1. Load env vars from /workspace/.env.json (bulletproof for OAuth blobs)
//   2. Lazy-install language-specific deps on first run (cached afterward)
const PRELUDE: Record<keyof typeof FILE_BY_LANG, string> = {
  python:
    "import os, json, subprocess, sys\n" +
    "try:\n" +
    `    with open(${JSON.stringify(ENV_FILE)}) as _f:\n` +
    "        for _k, _v in json.load(_f).items():\n" +
    "            if isinstance(_v, str):\n" +
    "                os.environ[_k] = _v\n" +
    "except Exception:\n" +
    "    pass\n" +
    `if not os.path.exists(${JSON.stringify(PIP_MARKER)}):\n` +
    "    try:\n" +
    `        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--no-cache-dir"] + ${JSON.stringify(
      PIP_PACKAGES.split(" "),
    )}, check=True)\n` +
    `        open(${JSON.stringify(PIP_MARKER)}, "w").close()\n` +
    "    except Exception as _e:\n" +
    '        print(f"[jai-prelude] pip install warning: {_e}", file=sys.stderr)\n',
  typescript:
    `import fs from "node:fs"; import { execSync } from "node:child_process";\n` +
    `try { const _e = JSON.parse(fs.readFileSync(${JSON.stringify(
      ENV_FILE,
    )}, "utf8")); for (const [k, v] of Object.entries(_e)) { if (typeof v === "string") process.env[k] = v; } } catch {}\n` +
    `if (!fs.existsSync(${JSON.stringify(NPM_MARKER)})) {\n` +
    `  try { execSync("npm install -g ${NPM_PACKAGES}", { stdio: "ignore" }); fs.writeFileSync(${JSON.stringify(
      NPM_MARKER,
    )}, ""); } catch (e) { console.error("[jai-prelude] npm install warning:", e); }\n` +
    `}\n`,
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
