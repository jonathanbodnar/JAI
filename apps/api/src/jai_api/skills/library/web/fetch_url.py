"""Fetch a URL and return its readable text content."""

KEY = "web.fetch_url"
TITLE = "Fetch URL"
DESCRIPTION = (
    "Download a webpage and return its text content (stripped of HTML "
    "tags) plus the page title. Use for 'summarize this link', "
    "'what does this article say', 'read this page'."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["web"]

SOURCE = r"""
import os, json, re
import httpx

inputs = json.loads(os.environ.get("JAI_SKILL_INPUTS_JSON") or "{}")
url = inputs.get("url")
if not url:
    print(json.dumps({"status": "error", "error": "Missing required input: url"}))
    raise SystemExit(0)

try:
    with httpx.Client(timeout=20.0, follow_redirects=True,
                      headers={"User-Agent": "JAI/1.0 (+assistant)"}) as c:
        r = c.get(url)
        r.raise_for_status()
        html = r.text
except Exception as e:
    print(json.dumps({"status": "error", "error": f"Fetch failed: {str(e)[:300]}"}))
    raise SystemExit(0)

# Title extraction.
title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
title = (title_match.group(1).strip() if title_match else "").replace("\n", " ")[:200]

# Strip script/style/nav/header/footer chunks, then collapse tags.
clean = re.sub(r"<(script|style|nav|header|footer|noscript)[^>]*>.*?</\1>", "", html, flags=re.IGNORECASE | re.DOTALL)
clean = re.sub(r"<[^>]+>", " ", clean)
clean = re.sub(r"\s+", " ", clean).strip()
if len(clean) > 12000:
    clean = clean[:12000] + " …(truncated)"

print(json.dumps({"status": "ok", "result": {
    "url": str(r.url),
    "title": title,
    "text": clean,
    "status_code": r.status_code,
    "content_length": len(clean),
}}))
"""
