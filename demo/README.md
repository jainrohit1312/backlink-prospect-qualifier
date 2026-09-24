# Backlink prospect qualifier — live demo

A working demo of the qualification step in a backlink prospecting workflow. Paste a
niche and some candidate domains; the app fetches each site **for real**, pulls the
public signals that decide whether it is worth an outreach email, and returns a
Sheet-ready table.

Nothing in the output is invented. Every row is either something the site publishes or
is left blank.

## What it checks per domain

- Does the site publish a guest-post page? (`/write-for-us`, `/guest-post`,
  `/contribute`, `/submit-guest-post`, `/advertise`) — if no dedicated page exists it
  also checks whether the homepage mentions one
- Contact email, extracted from the fetched pages, with template addresses
  (`example.com`, `sentry.io`, …) filtered out
- Reachability and the latest ISO date seen on the page, as a crude activity signal
- Optional: a page-rank authority **proxy** (see below)
- Optional: an AI fit verdict and a personalised outreach draft

## Run locally

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r demo/requirements.txt
.venv/Scripts/python.exe -m streamlit run demo/app.py
```

## Deploy on Streamlit Cloud

1. Push this repository to GitHub (public).
2. On share.streamlit.io, create an app pointing at this repo with main file path
   `demo/app.py`.
3. Optional, for the AI step: add `GEMINI_API_KEY` under the app's **Secrets**.

```toml
GEMINI_API_KEY = "your-key"
```

Without the secret the app still runs — the AI checkbox simply has nothing to do, and
the table still fills from live data.

## About the authority column

The free option is the Open PageRank API, which returns a **0–10 page-rank proxy**.
That is *not* Moz DA and *not* Ahrefs DR, so the column is labelled as a proxy and the
UI says so. Plugging in a Moz/Ahrefs/Semrush key gives you the real metric.

This is deliberate: a number is only useful if the label on it is true.

## Notes

- The default domain list is a demo set, checked against the live sites on 2026-09-24.
  Five of them publish a guest-post page and two do not — the two are kept in on
  purpose so the filter is visibly rejecting something.
- `GEMINI_MODEL` at the top of `demo/app.py` is easy to change if your key is scoped to
  a different model.
- Outreach drafts are drafts. Nothing in this app sends email.
