"""
Stateful 2-day run.

The point of a recurring run is NOT re-listing applications — it's catching what
CHANGED: new applications, and status flips (received -> rejected / interview) that
arrive days later on a fresh email. So this keeps a committed state file and emits a
diff each run: "N new · M new rejections".

Flow:  gmail_client.fetch()  ->  parse  ->  classify/score (pipeline.py)  ->
        upsert into data/state.json (key = Gmail message id)  ->
        propagate company-level status flips  ->  write applications.csv + print diff.

Falls back to pipeline.RAW when no Gmail creds are present, so it still runs in a demo.
"""

import os
import re
import csv
import json
from pathlib import Path
from dataclasses import asdict

from pipeline import (
    Application, detect_status, detect_track, detect_geo, detect_level,
    dedupe, metrics,
)

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "state.json"
CSV = ROOT / "data" / "applications.csv"

# ATS/sender domains that are NOT the employer — used to fall back to subject parsing.
ATS = ("greenhouse", "lever", "ashbyhq", "workday", "icims", "smartrecruiters",
       "oraclecloud", "oracle", "paylocity", "myworkday", "pinpoint", "workablemail",
       "tsenta", "recruiting", "notifications", "no-reply", "noreply")


def company_from(sender: str, subject: str) -> str:
    """Best-effort employer name: prefer subject phrasing, fall back to sender domain."""
    s = subject
    for pat in [r"applying to ([^|!.\-–]+)", r"application to ([^|!.\-–]+)",
                r"interest in ([^|!.\-–]+)", r" at ([A-Z][^|!.\-–]+)"]:
        m = re.search(pat, s)
        if m:
            return m.group(1).strip().strip("!.").strip()
    # fall back to the sender display name / domain
    dom = re.search(r"@([\w.-]+)", sender)
    if dom:
        host = dom.group(1).split(".")
        parts = [p for p in host if p not in ("com", "io", "org", "co", "net", "email",
                                              "mail", "us", "eu")]
        cand = next((p for p in parts if not any(a in p for a in ATS)), parts[0] if parts else "")
        return cand.capitalize()
    return "Unknown"


def parse_email(e: dict) -> Application:
    text = f"{e['subject']} {e['snippet']}"
    a = Application(
        company=company_from(e["sender"], e["subject"]),
        role=e["subject"],
        date=e["date"],
        status=detect_status(e["snippet"]),
        track=detect_track(text),
        geo=detect_geo("", text),
        level=detect_level(text),
    )
    a.score(); a.make_play()
    return a


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {}


def run():
    # 1. INGEST — live if creds exist, else demo seed
    if os.environ.get("GMAIL_REFRESH_TOKEN"):
        from gmail_client import fetch
        emails = fetch()
        records = {e["id"]: parse_email(e) for e in emails}
    else:
        from pipeline import RAW, build
        # demo: synth ids so state logic still exercises
        records = {f"seed-{i}": a for i, a in enumerate(build(RAW))}

    state = load_state()
    new_apps, new_rejections = [], []

    # 2. UPSERT by message id
    for mid, a in records.items():
        row = asdict(a)
        if mid not in state:
            new_apps.append(a)
            state[mid] = row
        elif state[mid]["status"] != row["status"]:
            state[mid]["status"] = row["status"]
            if row["status"] == "rejected":
                new_rejections.append(a)

    # 3. Propagate company-level flips: a fresh rejection email marks that company rejected
    rejected_cos = {r["company"].lower() for r in state.values() if r["status"] == "rejected"}
    for mid, row in state.items():
        if row["status"] != "rejected" and row["company"].lower() in rejected_cos:
            row["status"] = "rejected"

    STATE.write_text(json.dumps(state, indent=1))

    # 4. Rebuild the flat tracker from state
    apps = dedupe([Application(**{k: v for k, v in r.items()}) for r in state.values()])
    with open(CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(apps[0]).keys()))
        w.writeheader()
        for a in apps:
            w.writerow(asdict(a))

    # 5. DIFF — the thing you read each run
    print("=" * 44)
    print("2-DAY RUN SUMMARY")
    print("=" * 44)
    print(f"  new applications : {len(new_apps)}")
    for a in new_apps:
        print(f"      + {a.company} — {a.role[:50]}")
    print(f"  new rejections   : {len(new_rejections)}")
    for a in new_rejections:
        print(f"      - {a.company}")
    print(f"  total tracked    : {len(apps)}")
    print(f"  worth networking : {sum(a.priority == 'HIGH' for a in apps)}")

    # 6. RENDER the public dashboard from the fresh tracker (de-identified for Pages)
    from render import render
    render(deidentify=True)


if __name__ == "__main__":
    run()
