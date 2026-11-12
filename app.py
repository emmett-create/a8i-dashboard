"""a8i Sourcing API — prototype matcher.

Pools a few real client Master Lists together as a stand-in "creator
database" and filters them against whatever the Onboarding form's
Restrictions & Preferences fields say. This is deliberately simple
substring/keyword matching, not a real NLP/AI layer — the point right now
is to see where real, messy client data holds up or breaks against the
kind of free-text filters Onboarding collects, before investing in
anything smarter.
"""
import base64
import email.mime.text
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv()
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")  # local-dev only, see a8i-email-test

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from google.oauth2 import service_account
from googleapiclient.discovery import build as gbuild
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
import anthropic

import config

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Google Sheets ────────────────────────────────────────────────────────────
_sheets_client = None

def sheets():
    global _sheets_client
    if _sheets_client is None:
        if config.GOOGLE_CREDENTIALS_JSON:
            info = json.loads(config.GOOGLE_CREDENTIALS_JSON)
            creds = service_account.Credentials.from_service_account_info(
                info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
        else:
            creds = service_account.Credentials.from_service_account_file(
                config.GOOGLE_CREDENTIALS_FILE, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
        _sheets_client = gbuild("sheets", "v4", credentials=creds)
    return _sheets_client

# ── Pooled creator pool (cached) ─────────────────────────────────────────────
_pool_cache = {"creators": None, "fetched_at": 0}

def _cell(row: list, i):
    return row[i].strip() if i is not None and len(row) > i and row[i] else ""

def _to_int(s: str):
    s = (s or "").replace(",", "").strip()
    try:
        return int(float(s))
    except ValueError:
        return None

def fetch_pool(force: bool = False) -> list:
    if not force and _pool_cache["creators"] is not None and time.time() - _pool_cache["fetched_at"] < config.CACHE_TTL_SECONDS:
        return _pool_cache["creators"]

    creators = []
    for client_name, client_cfg in config.CLIENT_SHEETS.items():
        cols = client_cfg["columns"]
        resp = sheets().spreadsheets().values().get(
            spreadsheetId=client_cfg["sheet_id"],
            range=f"'{config.MASTER_LIST_TAB}'!A2:AM20000",
        ).execute()
        rows = resp.get("values", [])
        for i, r in enumerate(rows):
            name = _cell(r, cols.get("name"))
            if not name:
                continue
            ig_handle = _cell(r, cols.get("ig_handle")).lstrip("@")
            tt_handle = _cell(r, cols.get("tt_handle")).lstrip("@")
            creators.append({
                "id": f"{client_name}::{i}",
                "client": client_name,
                "name": name,
                "ig_handle": ig_handle,
                "ig_url": f"https://instagram.com/{ig_handle}" if ig_handle else None,
                "tt_handle": tt_handle,
                "tt_url": f"https://tiktok.com/@{tt_handle}" if tt_handle else None,
                "followers": _to_int(_cell(r, cols.get("followers"))),
                "gender": _cell(r, cols.get("gender")) or None,
                "vertical": _cell(r, cols.get("vertical")) or None,
                "archetype": _cell(r, cols.get("archetype")) or None,
                "location": _cell(r, cols.get("location")) or None,
                "age": _cell(r, cols.get("age")) or None,
            })

    _pool_cache["creators"] = creators
    _pool_cache["fetched_at"] = time.time()
    return creators

# ── Matching ─────────────────────────────────────────────────────────────────
# Every matcher returns one of "match" / "no_match" / "unknown" (filter was
# specified but this creator's row has no data for that field) / "match"
# when the filter itself was left blank (nothing to check against).

STOPWORDS = {
    "the", "a", "an", "and", "or", "who", "that", "not", "like", "we", "want",
    "creators", "creator", "for", "with", "our", "us", "is", "are", "feel",
    "think", "already", "love", "worked", "before", "trying", "to", "reach",
    "also", "but", "than", "just", "in", "on", "of", "be", "been", "about",
}

def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-z]+", (text or "").lower()) if w not in STOPWORDS and len(w) > 2}

# A vertical/archetype word that shows up on more than this fraction of the
# WHOLE pool is too generic to count as a real signal on its own. Found via
# a real query ("Cool lifestyle creators who would care about health and
# skincare", no other restrictions) that matched 9,525 of 14,491 creators —
# traced back to "lifestyle" alone (41% of the pool) and "fashion" (40%)
# being common enough that almost everyone has one of them tagged, so
# requiring just ANY shared word was nowhere near restrictive enough.
GENERIC_WORD_DOC_FREQ = 0.25

def _generic_vertical_words(creators: list) -> set:
    from collections import Counter
    freq = Counter()
    for c in creators:
        combined = f"{c['vertical'] or ''} {c['archetype'] or ''}"
        for w in _words(combined):
            freq[w] += 1
    total = len(creators) or 1
    return {w for w, n in freq.items() if n / total > GENERIC_WORD_DOC_FREQ}

def vertical_matches(description: str, vertical, archetype, generic_words: set):
    desc_words = _words(description)
    if not desc_words:
        return "match"
    combined = f"{vertical or ''} {archetype or ''}"
    combined_words = _words(combined)
    if not combined_words:
        return "unknown"
    overlap = desc_words & combined_words
    if not overlap:
        return "no_match"
    # At least one SPECIFIC shared word required — an overlap made up
    # entirely of generic tags (e.g. just "lifestyle") doesn't count.
    return "match" if (overlap - generic_words) else "no_match"

US_HINTS = {
    "us", "usa", "u.s", "u.s.a", "united", "states", "america", "american",
    "ny", "nyc", "la", "tx", "ca", "fl", "il", "ga", "wa", "ma", "nj", "pa",
    "new", "york", "los", "angeles", "chicago", "austin", "miami", "dallas",
    "atlanta", "seattle", "boston", "denver", "houston", "utah",
}

def location_matches(filter_text: str, value):
    f_words = _words(filter_text)
    if not f_words:
        return "match"
    if not value:
        return "unknown"
    v_words = _words(value)
    if f_words & US_HINTS and v_words & US_HINTS:
        return "match"
    return "match" if (f_words & v_words) else "no_match"

# Maps every term we might see in free text to one canonical bucket, then
# checks that bucket (not the raw term) against the creator's value — doing
# this with plain substring checks is a trap: "men" is literally a substring
# of "women", and "male" a substring of "female", so naive `in` matching
# treated almost every real "Female" value as also matching a "men" filter.
# _term_in uses word-boundary regex instead, so "female" with no boundary
# before "male" correctly does NOT match a bare \bmale\b search.
GENDER_SYNONYMS = {
    "female": "female", "woman": "female", "women": "female",
    "male": "male", "man": "male", "men": "male",
    "non-binary": "non-binary", "nonbinary": "non-binary",
    "couple": "couple",
}

def _term_in(text: str, term: str) -> bool:
    return re.search(rf"\b{re.escape(term)}\b", text) is not None

def gender_matches(filter_text: str, value):
    ft = (filter_text or "").lower()
    if "any" in ft:
        return "match"
    buckets = {canon for term, canon in GENDER_SYNONYMS.items() if _term_in(ft, term)}
    if not buckets:
        return "match"
    if not value:
        return "unknown"
    v = value.lower()
    return "match" if any(_term_in(v, b) for b in buckets) else "no_match"

def _parse_age_range(text: str):
    if not text:
        return None
    text = text.strip().lower()
    nums = [int(n) for n in re.findall(r"\d+", text)]
    if not nums:
        return None
    # "under 30" / "below 30" / "younger than 30" — not just the "<30" symbol
    # form the sheet data itself uses. Missing this meant a free-text age
    # filter like "women under 30" was parsed as exactly age 30, not a range.
    if text.startswith("<") or re.search(r"\b(under|below|younger)\b", text):
        return (0, nums[0])
    if text.endswith("+") or re.search(r"\b(over|above|older)\b", text):
        return (nums[0], 120)
    if len(nums) >= 2:
        return (min(nums[0], nums[1]), max(nums[0], nums[1]))
    return (nums[0], nums[0])

def age_matches(filter_text: str, value):
    f_range = _parse_age_range(filter_text)
    if not f_range:
        return "match"
    if not value:
        return "unknown"
    v_range = _parse_age_range(value)
    if not v_range:
        return "unknown"
    return "match" if f_range[0] <= v_range[1] and v_range[0] <= f_range[1] else "no_match"

def follower_matches(f_min, f_max, value):
    if f_min is None and f_max is None:
        return "match"
    if value is None:
        return "unknown"
    lo = f_min if f_min is not None else 0
    hi = f_max if f_max is not None else float("inf")
    return "match" if lo <= value <= hi else "no_match"

def classify(creator: dict, criteria: dict, generic_words: set) -> dict:
    # What they're gifting is a real fit signal too — a vegan-protein gift
    # should weight fitness/wellness creators higher than a skincare gift
    # would, independent of anything else matching. Folded into the same
    # free-text vertical match as the description rather than scored
    # separately, so it benefits from the same generic-word filtering.
    vertical_text = f"{criteria.get('description', '')} {criteria.get('product', '')}"
    checks = {
        "vertical": vertical_matches(vertical_text, creator["vertical"], creator["archetype"], generic_words),
        "location": location_matches(criteria.get("location", ""), creator["location"]),
        "gender": gender_matches(criteria.get("gender", ""), creator["gender"]),
        "age": age_matches(criteria.get("age", ""), creator["age"]),
        "followers": follower_matches(criteria.get("follower_min"), criteria.get("follower_max"), creator["followers"]),
    }
    if any(v == "no_match" for v in checks.values()):
        status = "no_match"
    elif any(v == "unknown" for v in checks.values()):
        status = "partial"
    else:
        status = "match"
    return {"status": status, "checks": checks}

# ── API ──────────────────────────────────────────────────────────────────────
@app.get("/api/pool_summary")
async def pool_summary():
    creators = fetch_pool()
    by_client = {}
    for c in creators:
        by_client[c["client"]] = by_client.get(c["client"], 0) + 1
    return {"total": len(creators), "by_client": by_client}

@app.post("/api/match")
async def match(criteria: dict):
    creators = fetch_pool()
    generic_words = _generic_vertical_words(creators)
    matched, partial, no_match = [], [], []
    for c in creators:
        result = classify(c, criteria, generic_words)
        row = {**c, **result}
        if result["status"] == "match":
            matched.append(row)
        elif result["status"] == "partial":
            partial.append(row)
        else:
            no_match.append(row)

    # Biggest creators first within each bucket — a reasonable default
    # ordering for a review list, not a ranking claim.
    matched.sort(key=lambda c: c["followers"] or 0, reverse=True)
    partial.sort(key=lambda c: c["followers"] or 0, reverse=True)

    limit_matched = min(int(criteria.get("limit_matched") or 150), len(matched))
    limit_partial = min(int(criteria.get("limit_partial") or 75), len(partial))

    return {
        "total": len(creators),
        "matched": len(matched),
        "partial": len(partial),
        "no_match": len(no_match),
        "matched_creators": matched[:limit_matched],
        "partial_creators": partial[:limit_partial],
    }

# ── Brand materials (brand decks, visual guidelines, target-demo PDFs) ──────
# Accepted and stored (in memory, keyed by a per-browser session id the
# frontend generates and keeps in localStorage) so the upload flow is real.
# NOT parsed into the matcher yet — that's a real next step (extracting
# actual signal out of a PDF deck), not something to fake. Render's disk is
# ephemeral too, so this is memory-only and won't survive a redeploy/restart
# — fine for a prototype, not a place to rely on for anything durable yet.
_briefs_by_session: dict = {}

@app.post("/api/upload_briefs")
async def upload_briefs(session_id: str = Form(...), files: list[UploadFile] = File(...)):
    stored = _briefs_by_session.setdefault(session_id, [])
    added = []
    for f in files:
        content = await f.read()
        entry = {"id": str(uuid.uuid4()), "filename": f.filename, "size": len(content), "content_type": f.content_type}
        stored.append(entry)
        added.append(entry)
    return {"added": added, "total_for_session": len(stored)}

@app.get("/api/briefs")
async def list_briefs(session_id: str):
    return {"files": _briefs_by_session.get(session_id, [])}

@app.delete("/api/briefs/{session_id}/{file_id}")
async def delete_brief(session_id: str, file_id: str):
    stored = _briefs_by_session.get(session_id, [])
    _briefs_by_session[session_id] = [f for f in stored if f["id"] != file_id]
    return {"files": _briefs_by_session[session_id]}

# ── Outreach / Inbox (Gmail OAuth + CASA path test, 2026-11-04) ──────────────
# Wires the Outreach page's "Inbox" mockup tab to a real Gmail test account
# (a8itesting@gmail.com) instead of the seeded localStorage data — same code
# proven out standalone in the a8i-email-test repo, moved here so it's
# visible in the actual site instead of a terminal. Token reused from that
# same project (same OAuth client, same granted scopes), so this shouldn't
# need a fresh consent unless the Testing-mode 7-day token expiry hits.
BASE_DIR = Path(__file__).parent
TOKEN_FILE = BASE_DIR / "token.json"
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8910/api/outreach/oauth/callback")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]
TEST_SUBJECT = "A8i test outreach — please reply"


def _flow() -> Flow:
    client_config = {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [GOOGLE_REDIRECT_URI],
        }
    }
    return Flow.from_client_config(client_config, scopes=GMAIL_SCOPES, redirect_uri=GOOGLE_REDIRECT_URI)


def _gmail_service():
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), GMAIL_SCOPES)
    return gbuild("gmail", "v1", credentials=creds)


def _extract_body(payload: dict) -> str:
    if payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode(errors="replace")
    for part in payload.get("parts", []) or []:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode(errors="replace")
        nested = _extract_body(part)
        if nested:
            return nested
    return ""


def _classify(reply_text: str) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model="claude-haiku-5-5",
        max_tokens=20,
        system=(
            "You're sorting a creator's reply to a gifting outreach email into exactly "
            "one category: Agree, Decline, Asks For Paid, or Needs Human Review (use "
            "this last one for anything hedged, ambiguous, bundling an extra question, "
            "or an out-of-office reply). Reply with ONLY the category name, nothing else."
        ),
        messages=[{"role": "user", "content": reply_text}],
    )
    return resp.content[0].text.strip()


@app.get("/api/outreach/status")
def outreach_status():
    """Actually verifies the token still works, not just that the file
    exists — Testing-mode refresh tokens expire every 7 days, so a stale
    token.json otherwise looks "connected" right up until a real send/read
    call 500s."""
    if not TOKEN_FILE.exists():
        return {"connected": False}
    try:
        _gmail_service().users().getProfile(userId="me").execute()
        return {"connected": True}
    except Exception:
        return {"connected": False, "expired": True}


@app.get("/api/outreach/connect")
def outreach_connect():
    flow = _flow()
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    return RedirectResponse(auth_url)


@app.get("/api/outreach/oauth/callback")
def outreach_oauth_callback(request: Request):
    flow = _flow()
    flow.fetch_token(authorization_response=str(request.url))
    TOKEN_FILE.write_text(flow.credentials.to_json())
    return RedirectResponse("/")


# Sends to a genuinely separate account, not back to the connected test
# inbox itself — found 2026-11-04 that a self-addressed test email makes a
# reply from that same account still carry Gmail's SENT label (correct
# behavior, not a bug), so our own is_outgoing check couldn't tell it apart
# from a real incoming reply. A different recipient account fixes that.
TEST_CREATOR_EMAIL = "emmettdunn4@gmail.com"

# Real test-creator inboxes to send to / read replies from — lets the reply
# classifier get exercised against a real variety of reply types (agree,
# decline, asks for paid, ambiguous, etc.) instead of just one thread.
# File-backed (not just in-memory) so added test inboxes survive a restart.
TEST_CREATORS_FILE = BASE_DIR / "test_creators.json"


def _load_test_creators() -> list:
    if TEST_CREATORS_FILE.exists():
        return json.loads(TEST_CREATORS_FILE.read_text())
    seeded = [{"name": "Emmett Dunn", "email": TEST_CREATOR_EMAIL}]
    TEST_CREATORS_FILE.write_text(json.dumps(seeded, indent=2))
    return seeded


def _save_test_creators(creators: list):
    TEST_CREATORS_FILE.write_text(json.dumps(creators, indent=2))


@app.get("/api/outreach/test_creators")
def list_test_creators():
    return {"creators": _load_test_creators()}


@app.post("/api/outreach/test_creators")
def add_test_creator(payload: dict):
    email_addr = (payload.get("email") or "").strip().lower()
    if not email_addr:
        raise HTTPException(400, "email is required")
    name = (payload.get("name") or "").strip() or email_addr
    creators = _load_test_creators()
    if any(c["email"] == email_addr for c in creators):
        raise HTTPException(409, "already added")
    creators.append({"name": name, "email": email_addr})
    _save_test_creators(creators)
    return {"creators": creators}


@app.delete("/api/outreach/test_creators/{email_addr}")
def remove_test_creator(email_addr: str):
    creators = [c for c in _load_test_creators() if c["email"] != email_addr.strip().lower()]
    _save_test_creators(creators)
    return {"creators": creators}


@app.post("/api/outreach/send")
def outreach_send(payload: Optional[dict] = None):
    """Sends a real outreach email. With no body (the Inbox tab's own "Send
    test outreach" button), sends the original static test message to the
    first saved test creator. With {"to", "body"} in the body, sends that
    instead — used by Outreach's Initial Outreach / Follow-up #1 batch-send
    flow to actually deliver mail (via Gmail, same subject so it still shows
    up in /api/outreach/replies) to creators flagged `testable` in the
    mockup data, rather than only simulating a send."""
    service = _gmail_service()
    default_to = (_load_test_creators() or [{}])[0].get("email", TEST_CREATOR_EMAIL)
    to = (payload or {}).get("to") or default_to
    body_text = (payload or {}).get("body") or (
        "Hi! This is a test outreach email from the A8i prototype.\n\n"
        "Reply to this email to test the reply-detection flow.\n\n- A8i test"
    )
    msg = email.mime.text.MIMEText(body_text)
    msg["to"] = to
    msg["subject"] = TEST_SUBJECT
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return {"sent": True, "to": to, "thread_id": sent["threadId"]}


EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _extract_email_addr(header_value: Optional[str]) -> str:
    if not header_value:
        return ""
    m = EMAIL_RE.search(header_value)
    return (m.group(0) if m else header_value).lower()


def _gmail_thread_url(thread_id: str) -> str:
    # Opens in whichever Google account is logged into the browser tab —
    # correct for us (a8itesting@gmail.com owns this mailbox), and exactly
    # the "click through to the real Gmail thread" behavior asked for, since
    # a8i organizes status itself and never needs to touch labels/threads
    # inside Gmail to do it.
    return f"https://mail.google.com/mail/u/0/#all/{thread_id}"


@app.get("/api/outreach/replies")
def outreach_replies():
    """Real inbox data for the Outreach page's Inbox tab, replacing the
    seeded localStorage mock. Grouped into one thread per real test creator
    (not a flat list) so testing several real inboxes at once stays
    readable, and each thread links straight through to the real Gmail
    thread. Each reply gets classified via Claude if ANTHROPIC_API_KEY is
    set."""
    service = _gmail_service()
    results = service.users().messages().list(
        userId="me", q=f'subject:"{TEST_SUBJECT}"'
    ).execute()
    message_refs = results.get("messages", [])

    threads: dict = {}
    for ref in message_refs:
        full = service.users().messages().get(userId="me", id=ref["id"], format="full").execute()
        headers = {h["name"]: h["value"] for h in full["payload"]["headers"]}
        body = _extract_body(full["payload"]).strip()
        is_outgoing = "SENT" in (full.get("labelIds") or [])
        counterpart = _extract_email_addr(headers.get("To") if is_outgoing else headers.get("From"))
        entry = {
            "id": ref["id"],
            "from": headers.get("From"),
            "subject": headers.get("Subject"),
            "snippet": full.get("snippet"),
            "body": body,
            "is_outgoing": is_outgoing,
            "internal_date": int(full.get("internalDate") or 0),
        }
        if ANTHROPIC_API_KEY and body and not is_outgoing:
            entry["classification"] = _classify(body)

        thread_id = full["threadId"]
        t = threads.setdefault(thread_id, {
            "thread_id": thread_id,
            "gmail_url": _gmail_thread_url(thread_id),
            "counterpart": None,
            "messages": [],
        })
        if counterpart and not t["counterpart"]:
            t["counterpart"] = counterpart
        t["messages"].append(entry)

    thread_list = list(threads.values())
    for t in thread_list:
        t["messages"].sort(key=lambda m: m["internal_date"])
    thread_list.sort(key=lambda t: t["messages"][-1]["internal_date"] if t["messages"] else 0, reverse=True)

    total = sum(len(t["messages"]) for t in thread_list)
    return {"count": total, "threads": thread_list}


@app.get("/")
def root():
    return {"ok": True, "service": "a8i-sourcing-api"}
