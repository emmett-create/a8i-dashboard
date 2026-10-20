# a8i Process Dashboard

Rough visual skeleton of a8i's "Our Process" outline — a lighter, self-serve
gifting-automation product Agency 8 is scoping out. Not a functional build
yet; content mirrors the live "Our Process" Notion page as of the
2026-10-20 working session.

## Running locally
Static site, no build step:

```
cd docs
python3 -m http.server 8899
```

Then open http://127.0.0.1:8899/.

## Deploying
Static only — GitHub Pages, serving from `/docs` on `main`, same pattern as
the other Agency 8 budget-tracker sites in this account.

## Editing content
All step content lives in the `STEPS` / `BIG_QUESTIONS` arrays at the top of
`docs/index.html`'s `<script>` block — no separate CMS or data file yet.
