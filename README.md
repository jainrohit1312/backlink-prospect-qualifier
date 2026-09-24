# Backlink prospect qualifier

Demo of the qualification step in a backlink prospecting workflow. Give it a niche and
some candidate domains; it fetches each site for real and returns the signals that decide
whether it is worth an outreach email — as a Sheet-ready table.

Nothing in the output is invented: every cell is either something the site publishes, or
it is left blank.

## Signals

- **Guest-post page** — probes `/write-for-us`, `/guest-post`, `/contribute`,
  `/submit-guest-post`, `/advertise`, and falls back to a mention on the homepage
- **Contact email** — pulled from the homepage, the guest-post page and `/contact`,
  `/about-us`; template addresses and retina asset filenames are filtered out, and an
  editorial inbox is preferred over a personal one
- **Publication recency** — the newest `pubDate` from the site's RSS/Atom feed, which is
  far more reliable than scraping dates out of HTML
- **Reachability** — the homepage HTTP status
- **Authority** — optional 0–10 page-rank proxy from Open PageRank, labelled as a proxy
  rather than as "DA"
- **Fit verdict and outreach draft** — optional, via the Gemini API

## What you see when you open it

The app explains itself, so it can be handed to someone who has never seen it before:

1. A **How to use this demo** panel giving the three steps — type a niche, paste the
   domains, press **Qualify prospects**.
2. A **What it checks** panel listing the rules above in plain language.
3. After a run, a summary line plus three counters: sites checked, qualified, and how many
   of those expose a contact email.
4. The results table, and directly beneath it a **What each column means** panel covering
   all sixteen columns — including the `Outreach Status`, `Last touch` and `Result`
   tracking columns that the follow-up step writes into.
5. A **Download Sheet-ready CSV** button, and the drafted outreach — one expander per
   site, each showing why that site was picked.

Nothing in the app contacts anyone. Every outreach email stays a draft, and a site that
fails the guest-post check stays visible in the table on purpose, so the filter can be
seen rejecting something rather than passing everything.

## Run

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r demo/requirements.txt
.venv/Scripts/python.exe -m streamlit run demo/app.py
```

Put `GEMINI_API_KEY = "..."` in `.streamlit/secrets.toml` to enable the AI step. Without
it the table still fills from live data.

Deployment, including Streamlit Cloud: [demo/README.md](demo/README.md).

## Tests

```bash
.venv/Scripts/python.exe tests/test_pipeline.py
.venv/Scripts/python.exe tests/test_ai_step.py
```

`test_pipeline.py` makes live requests, so it fails if a site stops publishing a
guest-post page. `test_ai_step.py` skips cleanly when no key is configured.

## Notes

Outreach drafts stay drafts — nothing here sends email.
