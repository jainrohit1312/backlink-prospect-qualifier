"""Verification for the qualifier demo.

Two kinds of check:

* pure-function checks that run offline, and
* live checks that fetch real websites — those need network access and will fail if a
  site changes its mind about publishing a guest-post page.

Run after touching demo/app.py:

    .venv/Scripts/python.exe tests/test_pipeline.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "demo"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app import (  # noqa: E402
    SHEET_COLUMNS,
    extract_emails,
    normalise,
    parse_domains,
    pick_email,
    to_csv,
)
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(ROOT / "demo" / "app.py")

POSITIVE = "bloggersideas.com"  # publishes /write-for-us and a contact address
NEGATIVE = "moz.com"  # publishes no guest-post page

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


# ------------------------------------------------------------------ pure functions

check("normalise bare host", normalise("moz.com") == "moz.com", repr(normalise("moz.com")))
check("normalise strips scheme, www and path", normalise("https://www.moz.com/blog") == "moz.com")
check("normalise rejects blank", normalise("   ") is None)
check("normalise rejects a hostless string", normalise("no-such-host") is None)

check(
    "parse_domains dedupes and keeps order",
    parse_domains("moz.com\n\nhttps://www.moz.com/x\nbacklinko.com\n") == ["moz.com", "backlinko.com"],
)

check(
    "emails drop template addresses and dedupe",
    extract_emails("mail hello@example.com or editors@x.com and editors@x.com") == ["editors@x.com"],
)
check(
    "emails reject retina asset filenames",
    extract_emails("badge@2x.png flags@2x.webp globe@2x.svg hello@real.io") == ["hello@real.io"],
)
check(
    "pick_email prefers an editorial inbox",
    pick_email(["jeff@site.com", "editors@site.com"]) == "editors@site.com",
)
check("pick_email falls back to the first", pick_email(["jeff@site.com"]) == "jeff@site.com")
check("pick_email dedupes", pick_email(["a@b.com", "a@b.com"]) == "a@b.com")
check("pick_email tolerates nothing", pick_email([]) == "")

blank_row = {column: "" for column in SHEET_COLUMNS}
csv_bytes = to_csv([blank_row])
lines = csv_bytes.decode("utf-8-sig").splitlines()
check("csv header is the sheet schema", lines[0] == ",".join(SHEET_COLUMNS))
check("csv starts with a BOM so Excel opens it cleanly", csv_bytes[:3] == b"\xef\xbb\xbf")

# ------------------------------------------------------------------------ the app

at = AppTest.from_file(APP)
at.run()
check("no exception on first render", not at.exception, str(at.exception))
check("title rendered", [t.value for t in at.title] == ["Backlink prospect qualifier"])
check("run button present", "Qualify prospects" in [b.label for b in at.button])
check("empty state shown before any run", bool(at.info))

# Click through the real pipeline: two live domains, one of which should be rejected.
at.text_area[0].set_value(f"{POSITIVE}\n{NEGATIVE}")
at.checkbox[0].set_value(False)  # AI off: this environment has no GEMINI_API_KEY
at.button[0].click()
at.run(timeout=240)

check("no exception while qualifying live sites", not at.exception, str(at.exception))

subheaders = [s.value for s in at.subheader]
check("summary rendered", any("of 2" in s for s in subheaders), str(subheaders))

metrics = getattr(at, "metric", [])
print(f"metrics: {[m.label for m in metrics]}")
check("summary counters rendered", len(metrics) >= 3, f"{len(metrics)} counters")

panel_labels = [e.label for e in at.expander]
check(
    "how-to panel explains the steps",
    any("How to use this demo" in label for label in panel_labels),
    str(panel_labels),
)
check(
    "rules panel explains the signals",
    any("What it checks" in label for label in panel_labels),
    str(panel_labels),
)
check(
    "column glossary is shown to the reader",
    any("What each column means" in label for label in panel_labels),
    str(panel_labels),
)

frames = getattr(at, "dataframe", [])
check("result table rendered", len(frames) >= 1)
check(
    "csv download offered",
    any("CSV" in d.label for d in getattr(at, "download_button", [])),
)

if frames:
    value = frames[0].value
    records = value.to_dict("records") if hasattr(value, "to_dict") else list(value)
    by_domain = {record["Domain"]: record for record in records}

    positive = by_domain.get(POSITIVE, {})
    negative = by_domain.get(NEGATIVE, {})
    print(f"LIVE  {POSITIVE}: {positive.get('Guest-post signal')} / {positive.get('Latest post (RSS)')}")
    print(f"LIVE  {NEGATIVE}: {negative.get('Guest-post signal')}")

    check(
        "a guest-post host is detected as one",
        str(positive.get("Guest-post signal", "")).startswith("/"),
        str(positive.get("Guest-post signal")),
    )
    check(
        "a site without a guest-post page is rejected",
        negative.get("Guest-post signal") == "none found",
        str(negative.get("Guest-post signal")),
    )
    check("every row is dated", all(len(str(r.get("Date Added", ""))) == 10 for r in records))
    check("rows start in status New", all(r.get("Outreach Status") == "New" for r in records))

print()
print(f"result: {'ALL PASS' if not failures else 'FAILURES: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
