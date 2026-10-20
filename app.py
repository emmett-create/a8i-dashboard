"""a8i Sourcing API — prototype matcher.

Pools a few real client Master Lists together as a stand-in "creator
database" and filters them against whatever the Onboarding form's
Restrictions & Preferences fields say. This is deliberately simple
substring/keyword matching, not a real NLP/AI layer — the point right now
is to see where real, messy client data holds up or breaks against the
kind of free-text filters Onboarding collects, before investing in
anything smarter.
"""
import json
import re
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from google.oauth2 import service_account
from googleapiclient.discovery import build as gbuild

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
        for r in rows:
            name = _cell(r, cols.get("name"))
            if not name:
                continue
            creators.append({
                "client": client_name,
                "name": name,
                "ig_handle": _cell(r, cols.get("ig_handle")),
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

def vertical_matches(description: str, vertical, archetype):
    desc_words = _words(description)
    if not desc_words:
        return "match"
    combined = f"{vertical or ''} {archetype or ''}"
    combined_words = _words(combined)
    if not combined_words:
        return "unknown"
    return "match" if desc_words & combined_words else "no_match"

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

def classify(creator: dict, criteria: dict) -> dict:
    checks = {
        "vertical": vertical_matches(criteria.get("description", ""), creator["vertical"], creator["archetype"]),
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
    matched, partial, no_match = [], [], []
    for c in creators:
        result = classify(c, criteria)
        row = {**c, **result}
        if result["status"] == "match":
            matched.append(row)
        elif result["status"] == "partial":
            partial.append(row)
        else:
            no_match.append(row)
    return {
        "total": len(creators),
        "matched": len(matched),
        "partial": len(partial),
        "no_match": len(no_match),
        "sample_matched": matched[:10],
        "sample_partial": partial[:5],
    }

@app.get("/")
def root():
    return {"ok": True, "service": "a8i-sourcing-api"}
