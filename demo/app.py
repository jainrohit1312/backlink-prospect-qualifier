"""Backlink prospect qualifier — live demo.

Give it a niche and a list of candidate domains. It fetches each site for real,
pulls the public qualification signals (guest-post page, contact email, publication
recency), optionally adds an AI fit verdict and an outreach draft, and hands back a
Sheet-ready table.

Run locally:   streamlit run demo/app.py
Deploy:        Streamlit Cloud, main file path `demo/app.py`
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import requests
import streamlit as st

TIMEOUT = 12
MAX_WORKERS = 6
UA = {"User-Agent": "Mozilla/5.0 (compatible; BacklinkProspectQualifier/1.0)"}

GUEST_POST_PATHS = (
    "write-for-us",
    "write-for-us/",
    "guest-post",
    "guest-posts",
    "contribute",
    "submit-guest-post",
    "advertise",
)

CONTACT_PATHS = ("contact", "contact-us", "about-us")

FEED_PATHS = ("feed", "feed.xml", "rss", "rss.xml", "blog/feed", "index.xml")

GUEST_POST_SIGNALS = (
    "write for us",
    "guest post",
    "guest article",
    "become a contributor",
    "submit a post",
)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PUBDATE_RE = re.compile(
    r"<(?:pubDate|lastBuildDate|updated|published)>\s*([^<]+?)\s*</",
    re.IGNORECASE,
)

# Addresses that live in page templates; nobody reads mail sent to them.
EMAIL_DENY = ("example.com", "sentry.io", "wixpress.com", "domain.com", "yourdomain.com")

# Retina assets look exactly like addresses: "flags@2x.webp", "badge_dark@2x.png".
ASSET_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".css", ".js", ".ico")

# Inboxes that actually receive guest-post pitches, best first.
PREFERRED_LOCAL = ("editor", "guest", "submit", "contribute", "hello", "contact", "info", "press")

# Checked against the live sites on 2026-09-24. The first five really do publish a
# guest-post page; the last two do not. Keeping both kinds in the default list is
# deliberate — it shows the qualification step actually rejecting something.
DEMO_SEEDS = [
    "bloggersideas.com",
    "contentmarketinginstitute.com",
    "smashingmagazine.com",
    "bloggerspassion.com",
    "shoutmeloud.com",
    "backlinko.com",
    "moz.com",
]

GEMINI_MODEL = "gemini-3.6-flash"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SHEET_COLUMNS = [
    "Website",
    "Domain",
    "Authority (proxy)",
    "Niche",
    "Contact Email",
    "Guest-post signal",
    "Latest post (RSS)",
    "Reachable",
    "Relevance",
    "Reason for fit",
    "Outreach subject",
    "Outreach body",
    "Outreach Status",
    "Date Added",
    "Last touch",
    "Result",
]


# --------------------------------------------------------------------------- fetch


def normalise(target: str) -> str | None:
    target = target.strip()
    if not target:
        return None
    if "://" not in target:
        target = "https://" + target
    host = urlparse(target).netloc.lower().removeprefix("www.")
    return host if host and "." in host else None


def fetch(url: str) -> tuple[str, int | None]:
    try:
        resp = requests.get(url, headers=UA, timeout=TIMEOUT, allow_redirects=True)
        return resp.text, resp.status_code
    except requests.RequestException:
        return "", None


def extract_emails(html: str) -> list[str]:
    found: list[str] = []
    for raw in EMAIL_RE.findall(html):
        email = raw.strip(".").lower()
        domain = email.split("@", 1)[1]
        if any(domain.endswith(bad) for bad in EMAIL_DENY):
            continue
        if email.endswith(ASSET_SUFFIXES):
            continue
        if email not in found:
            found.append(email)
    return found


def pick_email(emails: list[str]) -> str:
    """Dedupe, then prefer an inbox that actually reads guest-post pitches."""
    unique = list(dict.fromkeys(email for email in emails if email))
    for hint in PREFERRED_LOCAL:
        for email in unique:
            if hint in email.split("@", 1)[0]:
                return email
    return unique[0] if unique else ""


def first_page(domain: str, paths: tuple[str, ...]) -> tuple[str, str]:
    """Return the html and path of the first path that serves a real page."""
    for path in paths:
        html, status = fetch(f"https://{domain}/{path}")
        if status == 200 and len(html) > 500:
            return html, path
    return "", ""


def latest_post(domain: str) -> str:
    """Newest publication date from the site's feed — far more honest than scraping HTML."""
    for path in FEED_PATHS:
        html, status = fetch(f"https://{domain}/{path}")
        if status != 200:
            continue
        dates = []
        for raw in PUBDATE_RE.findall(html):
            try:
                dates.append(parsedate_to_datetime(raw.strip()).date().isoformat())
            except (TypeError, ValueError):
                continue
        if dates:
            return max(dates)
    return ""


def open_page_rank(domain: str, key: str) -> str:
    try:
        resp = requests.get(
            "https://openpagerank.com/api/v1.0/getPageRank",
            params={"domains[]": domain},
            headers={"API-OPR": key},
            timeout=TIMEOUT,
        )
        entry = resp.json()["response"][0]
        rank = entry.get("page_rank_decimal")
        return "not indexed" if rank is None else f"{rank} (0-10 page-rank proxy)"
    except (requests.RequestException, KeyError, IndexError, ValueError):
        return "lookup failed"


# ------------------------------------------------------------------------ qualifier


def qualify(domain: str, niche: str, opr_key: str | None = None) -> dict:
    """Fetch one site and return a Sheet-shaped row of public signals."""
    row = {column: "" for column in SHEET_COLUMNS}
    row["Domain"] = domain
    row["Website"] = f"https://{domain}/"
    row["Niche"] = niche
    row["Outreach Status"] = "New"
    row["Date Added"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    home_html, home_status = fetch(f"https://{domain}/")
    row["Reachable"] = "yes" if home_status == 200 else f"no ({home_status or 'unreachable'})"
    emails = extract_emails(home_html)

    # Guest-post page — the strongest signal that the site takes contributions.
    page_html, page_path = first_page(domain, GUEST_POST_PATHS)
    signal = f"/{page_path}" if page_path else ""
    if page_html:
        emails.extend(extract_emails(page_html))

    if not signal:
        lowered = home_html.lower()
        for phrase in GUEST_POST_SIGNALS:
            if phrase in lowered:
                signal = f"homepage mentions '{phrase}'"
                break
    row["Guest-post signal"] = signal or "none found"

    # Contact pages — where the address usually actually lives.
    for path in CONTACT_PATHS:
        contact_html, status = fetch(f"https://{domain}/{path}")
        if status == 200 and len(contact_html) > 500:
            emails.extend(extract_emails(contact_html))

    row["Contact Email"] = pick_email(emails)
    row["Latest post (RSS)"] = latest_post(domain)

    if opr_key:
        row["Authority (proxy)"] = open_page_rank(domain, opr_key)

    return row


# ------------------------------------------------------------------------------- AI


def llm_key() -> str | None:
    env = os.environ.get("GEMINI_API_KEY")
    if env:
        return env
    try:
        return st.secrets["GEMINI_API_KEY"] or None
    except Exception:  # no secrets file locally, or no such key
        return None


def ai_review(row: dict, api_key: str) -> dict:
    """Ask the LLM for a fit verdict and an outreach draft. Returns a note on failure."""
    prompt = f"""You are qualifying one website as a backlink prospect for a "{row['Niche']}" site.

Domain: {row['Domain']}
Guest-post signal: {row['Guest-post signal']}
Most recent post: {row['Latest post (RSS)'] or 'unknown'}
Contact email: {row['Contact Email'] or 'not found'}

Judge only from the lines above. Do not invent traffic, audience or history.

Return JSON only, with exactly these keys:
  "relevance": integer 0-100
  "reason_for_fit": one or two sentences a marketer would actually write
  "outreach_subject": a short subject line
  "outreach_body": under 120 words, specific, no flattery, one clear ask
"""

    try:
        resp = requests.post(
            GEMINI_URL.format(model=GEMINI_MODEL),
            headers={"x-goog-api-key": api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            },
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        payload = json.loads(text)
        return {
            "Relevance": payload.get("relevance", ""),
            "Reason for fit": payload.get("reason_for_fit", ""),
            "Outreach subject": payload.get("outreach_subject", ""),
            "Outreach body": payload.get("outreach_body", ""),
        }
    except requests.HTTPError as exc:
        # Report the status and the API's own message. Never the URL and never
        # str(exc): both embed the key, and this app is public.
        detail = ""
        try:
            detail = exc.response.json().get("error", {}).get("message", "")
        except ValueError:
            detail = ""
        return {"Reason for fit": f"AI step failed: HTTP {exc.response.status_code} {detail}".strip()}
    except Exception as exc:  # name the failure, never echo its message
        return {"Reason for fit": f"AI step failed: {type(exc).__name__}"}


# ------------------------------------------------------------------------------- UI


def to_csv(rows: list[dict]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=SHEET_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def parse_domains(raw: str) -> list[str]:
    domains, seen = [], set()
    for line in raw.splitlines():
        host = normalise(line)
        if host and host not in seen:
            seen.add(host)
            domains.append(host)
    return domains


def qualify_all(domains: list[str], niche: str, opr_key: str | None) -> list[dict]:
    """Qualify the sites concurrently — the work is network-bound, so this is safe."""
    rows, done = [], 0
    progress = st.progress(0.0, text="Qualifying…")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(qualify, d, niche, opr_key): d for d in domains}
        for future in as_completed(futures):
            rows.append(future.result())
            done += 1
            progress.progress(done / len(domains), text=f"{done}/{len(domains)} checked")
    progress.empty()

    order = {domain: index for index, domain in enumerate(domains)}
    rows.sort(key=lambda row: order[row["Domain"]])
    return rows


def main() -> None:
    st.set_page_config(page_title="Backlink prospect qualifier", page_icon="🔗", layout="wide")
    st.title("Backlink prospect qualifier")
    st.caption(
        "Live demo. Fetches real sites, extracts public qualification signals, and "
        "drafts outreach. No prospect data is invented."
    )

    key = llm_key()

    with st.sidebar:
        st.header("Inputs")
        niche = st.text_input("Niche", value="personal finance")
        raw = st.text_area(
            "Candidate domains — one per line",
            value="\n".join(DEMO_SEEDS),
            height=170,
        )
        opr_key = st.text_input("Open PageRank key (optional)", type="password")
        use_ai = st.checkbox("AI fit verdict + outreach draft", value=bool(key))
        run = st.button("Qualify prospects", type="primary", width="stretch")

        st.divider()
        st.caption(
            "**Authority column:** Open PageRank returns a 0–10 page-rank proxy. "
            "It is **not** Moz DA or Ahrefs DR, and this demo will not label it as "
            "DA. Plug your own Ahrefs/Semrush/Moz key in for the real metric."
        )
        st.caption(f"AI: {'Gemini key found' if key else 'no GEMINI_API_KEY set'}")

    if run:
        domains = parse_domains(raw)
        if not domains:
            st.warning("Add at least one domain.")
        elif use_ai and not key:
            st.error("AI is ticked but no GEMINI_API_KEY is set — untick it or add the key.")
        else:
            rows = qualify_all(domains, niche, opr_key or None)
            if use_ai and key:
                ai_bar = st.progress(0.0, text="Drafting outreach…")
                for index, row in enumerate(rows, start=1):
                    row.update(ai_review(row, key))
                    ai_bar.progress(index / len(rows), text=f"{index}/{len(rows)} drafted")
                ai_bar.empty()
            st.session_state["rows"] = rows

    rows = st.session_state.get("rows")
    if not rows:
        st.info("Pick a niche, list some domains, and press **Qualify prospects**.")
        return

    qualified = [r for r in rows if r["Guest-post signal"] != "none found"]
    with_contact = [r for r in qualified if r["Contact Email"]]
    st.subheader(
        f"{len(qualified)} of {len(rows)} show a guest-post signal · "
        f"{len(with_contact)} of those expose a contact email"
    )

    st.dataframe(
        [{c: r[c] for c in SHEET_COLUMNS if c != "Outreach body"} for r in rows],
        width="stretch",
        hide_index=True,
    )
    st.download_button(
        "Download Sheet-ready CSV",
        data=to_csv(rows),
        file_name=f"backlink-prospects-{niche.replace(' ', '-')}.csv",
        mime="text/csv",
    )

    if any(r["Outreach subject"] for r in rows):
        st.subheader("Drafted outreach — approve before anything sends")
        for row in rows:
            if not row["Outreach subject"]:
                continue
            with st.expander(f"{row['Domain']} — relevance {row['Relevance']}"):
                st.markdown(f"**Why this site:** {row['Reason for fit']}")
                st.markdown(f"**Subject:** {row['Outreach subject']}")
                st.text(row["Outreach body"])


if __name__ == "__main__":
    main()
