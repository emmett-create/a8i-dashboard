import os

APP_PASSWORD = os.environ.get("APP_PASSWORD", "")  # blank = no auth; this is a read-only matcher, nothing sensitive

# Service account creds — same pattern as every other Agency 8 tool.
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
GOOGLE_CREDENTIALS_FILE = os.environ.get(
    "GOOGLE_CREDENTIALS_FILE",
    "/Users/emmett/agency8-influencer-tool/google-credentials.json",
)

MASTER_LIST_TAB = "Master List"

# Test creator database — real client Master Lists pooled for the a8i
# Onboarding -> Sourcing prototype (2026-10-20). Picked for size: Feals
# (6.8k), Tilt Beauty (1.4k), BORNTOSTANDOUT (6.3k) are meaningfully
# smaller than e.g. Merit/Momofuku, so a cold fetch doesn't take forever.
#
# Column indices are 0-based, matching each sheet's own real header row —
# they differ per client because the Master List template has drifted
# client to client over time. BORNTOSTANDOUT has no Location or Age
# columns at all (confirmed 2026-10-20) — it uses Archetype/Tier instead.
CLIENT_SHEETS = {
    "Feals": {
        "sheet_id": "1x7OyNUkQS8lWvz-jRMlCC99fvROX-B7tDeuGG5PiwvM",
        "columns": {"name": 1, "ig_handle": 3, "tt_handle": 5, "followers": 7, "gender": 8, "vertical": 9, "location": 10, "age": 11},
    },
    "Tilt Beauty": {
        "sheet_id": "1PyowbTWyAZ_k86bGBtexotoExcqWmUQgYJloTSUZBC0",
        "columns": {"name": 3, "ig_handle": 5, "tt_handle": 7, "followers": 9, "gender": 10, "vertical": 11, "location": 12, "age": 13},
    },
    "BORNTOSTANDOUT": {
        "sheet_id": "1nsRCoRK9hdbH50rMD9zqp-GGwTpPyEAFWT69_pjVEbg",
        "columns": {"name": 1, "ig_handle": 3, "tt_handle": 5, "followers": 7, "gender": 8, "vertical": 9, "archetype": 10},
    },
}

CACHE_TTL_SECONDS = 600
