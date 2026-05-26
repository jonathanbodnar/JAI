"""Search the web via DuckDuckGo's HTML interface (no API key needed)."""

KEY = "web.search"
TITLE = "Web search"
DESCRIPTION = (
    "Search the web with a free-text query (uses DuckDuckGo HTML — no API "
    "key required). Returns top 10 result titles + URLs + snippets. Use "
    "for 'search for X', 'find articles about Y', 'look up the latest on Z'."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["web"]

SOURCE = r"""
import os, json, re, html as _html
import httpx

inputs = json.loads(os.environ.get("JAI_SKILL_INPUTS_JSON") or "{}")
query = (inputs.get("query") or "").strip()
max_results = int(inputs.get("max_results") or 10)

if not query:
    print(json.dumps({"status": "error", "error": "Missing required input: query"}))
    raise SystemExit(0)

try:
    with httpx.Client(timeout=20.0, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 (compatible; JAI/1.0)"}) as c:
        r = c.post(
            "https://duckduckgo.com/html/",
            data={"q": query, "kl": "us-en"},
        )
        r.raise_for_status()
        page = r.text
except Exception as e:
    print(json.dumps({"status": "error", "error": f"Search failed: {str(e)[:300]}"}))
    raise SystemExit(0)

# DDG HTML output is fragile but stable enough: each result has a
# `result__title` link + `result__snippet` block. Regex over raw HTML
# beats pulling beautifulsoup which isn't installed in the sandbox.
results = []
for m in re.finditer(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
    r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
    page, re.DOTALL,
):
    url = m.group(1)
    # DDG wraps target URLs in a redirect (//duckduckgo.com/l/?uddg=...).
    if url.startswith("//duckduckgo.com/l/?"):
        uddg = re.search(r"uddg=([^&]+)", url)
        if uddg:
            from urllib.parse import unquote
            url = unquote(uddg.group(1))
    title = _html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
    snippet = _html.unescape(re.sub(r"<[^>]+>", "", m.group(3))).strip()
    results.append({"title": title, "url": url, "snippet": snippet[:300]})
    if len(results) >= max_results:
        break

print(json.dumps({"status": "ok", "result": {
    "query": query,
    "count": len(results),
    "results": results,
}}))
"""
