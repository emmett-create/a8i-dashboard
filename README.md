# a8i Process Dashboard

First working version of a8i — a lighter, self-serve version of Agency
Eight's gifting service. Two parts in this one repo, deployed separately:

- **`docs/`** — the static site (hub page + one page per area: Onboarding,
  Sourcing, Gifting, Outreach, Order Placement, Content Tracking,
  Reporting). Deployed via GitHub Pages.
- **`app.py`** — the sourcing-matching API. Onboarding's "Describe your
  ideal creator" + Restrictions fields call this to actually filter a pool
  of real creator data, rather than just acknowledging the input. Deployed
  separately via Render, pointed at this same repo.

## Running the static site locally
No build step:

```
cd docs
python3 -m http.server 8899
```
Then open http://127.0.0.1:8899/.

## Running the API locally
```
pip install -r requirements.txt
uvicorn app:app --reload --port 8910
```
Needs `GOOGLE_CREDENTIALS_FILE` (defaults to the shared Agency 8 service
account file) or `GOOGLE_CREDENTIALS_JSON` set.

## Deploying
- **Static site**: GitHub Pages, serving from `/docs` on `main` — same
  pattern as the other Agency 8 tool sites in this account.
- **API**: a separate Render web service pointed at this repo (root
  directory, not `/docs`) — same pattern as Magna/Paid System, just
  sharing this repo instead of having its own. Needs the
  `GOOGLE_CREDENTIALS_JSON` env var set to the shared service account
  credentials.

## Editing content
Each area page's content lives in a small data array at the top of its own
`docs/<area>.html` file — no separate CMS or data file yet. The sourcing
matcher's test creator pool (which clients, which sheet, which columns) is
configured in `config.py`.
