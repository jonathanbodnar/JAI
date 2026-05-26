"""Quick metadata + Open Graph tags for a URL (title, description, image)."""

KEY = "utility.url_meta"
TITLE = "URL metadata / link preview"
DESCRIPTION = (
    "Fetch the title, meta description, and Open Graph tags for a URL. "
    "Lightweight alternative to a full page fetch — for link previews or "
    "quick site identification. Use for 'what is this link', 'preview this URL'."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["web"]

SOURCE = r"""
import os, json, re, html as _html
import httpx

inputs = json.loads(os.environ.get("JAI_SKILL_INPUTS_JSON") or "{}")
url = inputs.get("url")
if not url:
    print(json.dumps({"status": "error", "error": "Missing required input: url"}))
    raise SystemExit(0)

try:
    with httpx.Client(timeout=15.0, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 (compatible; JAI/1.0)"}) as c:
        r = c.get(url)
        r.raise_for_status()
        page = r.text[:120_000]  # cap; OG tags are always in <head>
except Exception as e:
    print(json.dumps({"status": "error", "error": f"Fetch failed: {str(e)[:300]}"}))
    raise SystemExit(0)

def _meta(prop_or_name):
    # Try both name="..." and property="..." attribute styles.
    patterns = [
        rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop_or_name)}["\'][^>]*content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']{re.escape(prop_or_name)}["\']',
    ]
    for p in patterns:
        m = re.search(p, page, re.IGNORECASE)
        if m:
            return _html.unescape(m.group(1).strip())
    return None

title_m = re.search(r"<title[^>]*>(.*?)</title>", page, re.IGNORECASE | re.DOTALL)
title = _html.unescape((title_m.group(1).strip() if title_m else "")).replace("\n", " ")[:300]

print(json.dumps({"status": "ok", "result": {
    "url": str(r.url),
    "status_code": r.status_code,
    "title": title or None,
    "description": _meta("description") or _meta("og:description"),
    "og_title": _meta("og:title"),
    "og_image": _meta("og:image"),
    "og_site": _meta("og:site_name"),
    "twitter_card": _meta("twitter:card"),
    "canonical": (re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)', page, re.IGNORECASE) or [None, None])[1],
}}))
"""
