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
