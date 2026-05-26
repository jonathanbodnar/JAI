"""Important-only inbox across every connected Gmail account.

Filters out promotions, social/forum/updates, bounces, and obvious
no-reply senders so the user sees only conversations that came from a
real human. Parallelised across accounts and across messages.
"""

KEY = "gmail.important_inbox"
TITLE = "Important emails (humans only)"
DESCRIPTION = (
    "List the most recent IMPORTANT emails from every connected Gmail "
    "account, filtered to human senders. Excludes Gmail's "
    "Promotions/Social/Updates/Forums categories, bounces, and obvious "
    "no-reply / mailer-daemon addresses. Use for queries like "
    "'important emails', 'real emails', 'people emailed me', 'inbox "
    "without junk', 'what actually matters in my mail'."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["gmail"]

SOURCE = r"""
import os, json, re
from concurrent.futures import ThreadPoolExecutor
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Gmail's `category:primary` already strips the obvious junk
# (Promotions/Social/Forums/Updates). We layer on additional negatives
# for system mail that still slips through (bounces, GitHub blasts,
# automated notifications, calendar invites masquerading as primary).
QUERY = (
    "category:primary -from:noreply -from:no-reply -from:donotreply "
    "-from:notifications -from:mailer-daemon -from:postmaster "
    "-from:bounce -from:newsletter -from:updates -from:alerts "
    "-from:hello@ -from:support@ -label:CATEGORY_PROMOTIONS "
    "-label:CATEGORY_SOCIAL -label:CATEGORY_UPDATES -label:CATEGORY_FORUMS"
)

# Final belt-and-suspenders client-side filter. Even with the gmail
# search query above, a few automated senders still leak through if
# they use a "real-looking" From header (e.g. "Mike at Stripe").
NONHUMAN_PATTERNS = re.compile(
    r"(?:^|<)(?:no[-_]?reply|donotreply|notifications?|mailer[-_]?daemon|"
    r"postmaster|bounce|delivery|reply\+|updates?|alerts?|news(?:letter)?|"
    r"team|info|support|hello|admin|automated|system)@",
    re.IGNORECASE,
)
PROMO_SUBJECT = re.compile(
    r"(?:\b\d{1,2}%\s*off\b|\bsale\b|\bdeal\b|\bdiscount\b|\bsave\b|"
    r"\bclearance\b|\binvoice\b|\bshipped\b|\bunsubscribe\b|\bweekly\b|"
    r"\bdigest\b|\bnewsletter\b)",
    re.IGNORECASE,
)

def _svc(token_json):
    info = dict(token_json)
    info["token"] = info.get("token") or info.get("access_token")
    creds = Credentials.from_authorized_user_info(info)
    if not creds.valid:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)

def _fetch_one(svc, mid):
    full = svc.users().messages().get(
        userId="me", id=mid, format="metadata",
        metadataHeaders=["From", "Subject", "Date", "Reply-To"],
    ).execute()
    headers = {x["name"]: x["value"] for x in full["payload"].get("headers", [])}
    return {
        "id": mid,
        "from": headers.get("From"),
        "reply_to": headers.get("Reply-To"),
        "subject": headers.get("Subject"),
        "date": headers.get("Date"),
        "snippet": (full.get("snippet") or "")[:240],
        "labels": full.get("labelIds") or [],
    }

def _is_human(row):
    sender = row.get("from") or ""
    if NONHUMAN_PATTERNS.search(sender):
        return False
    # Bounces / delivery failures usually have a Reply-To pointing back
    # to a mailer-daemon style address.
    rt = row.get("reply_to") or ""
    if NONHUMAN_PATTERNS.search(rt):
        return False
    subj = row.get("subject") or ""
    if PROMO_SUBJECT.search(subj):
        return False
    labels = row.get("labels") or []
    # Belt-and-suspenders even with the gmail-side query.
    for promo in ("CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL",
                  "CATEGORY_UPDATES", "CATEGORY_FORUMS"):
        if promo in labels:
            return False
    return True

def _read_account(account):
    email = account.get("email") or "unknown"
    try:
        svc = _svc(account["token_json"])
        ids = svc.users().messages().list(
            userId="me", q=QUERY, maxResults=25,
        ).execute().get("messages", [])
        if not ids:
            return email, []
        with ThreadPoolExecutor(max_workers=10) as ex:
            rows = list(ex.map(lambda m: _fetch_one(svc, m["id"]), ids))
        # Apply the client-side filter, then cap at the top 10 humans.
        humans = [r for r in rows if _is_human(r)][:10]
        # Strip internal label list before returning — saves tokens in
        # synthesis and the user doesn't need to see Gmail's internals.
        for r in humans:
            r.pop("labels", None)
            r.pop("reply_to", None)
            r.pop("id", None)
        return email, humans
    except Exception as e:
        return email, {"error": str(e)[:240]}

accounts = json.loads(os.environ.get("GMAIL_ACCOUNTS_JSON") or "[]")
if not accounts and os.environ.get("GMAIL_OAUTH_JSON"):
    accounts = [{"email": "default", "token_json": json.loads(os.environ["GMAIL_OAUTH_JSON"])}]

per_account = {}
total = 0
with ThreadPoolExecutor(max_workers=max(1, len(accounts))) as ex:
    for email, result in ex.map(_read_account, accounts):
        per_account[email] = result
        if isinstance(result, list):
            total += len(result)

print(json.dumps({"status": "ok", "result": {
    "total": total,
    "by_account": per_account,
    "filter": "human senders only (no promotions/social/updates/bounces)",
}}))
"""
