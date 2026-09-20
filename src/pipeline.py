"""
Job Application -> Networking Pipeline
--------------------------------------
Turns raw Gmail application-confirmation emails into:
  1. a clean, deduped application tracker (applications.csv)
  2. a per-application STATUS (received / rejected)
  3. a NETWORKING PRIORITY score (who is worth an outreach message)
  4. an outreach PLAY per company (who to target + the angle)
  5. funnel metrics (applied -> rejected -> live -> worth-networking)

Design notes
------------
- Input is email-shaped dicts: {subject, sender, snippet, date}. In production the
  `gmail_client` module fetches these via the Gmail API; here they are seeded with a
  real pull so the pipeline is runnable and demonstrable end-to-end.
- The LinkedIn leg is deliberately NOT automated (ToS + account-ban risk). The pipeline
  outputs *who to look for and why*; the human runs the 30-second search by hand.
"""

import csv
import re
from dataclasses import dataclass, asdict, field
from pathlib import Path

# ----------------------------------------------------------------------------- #
# 1. TARGETING CONFIG  (edit this to steer the whole pipeline)
# ----------------------------------------------------------------------------- #

# Roles you actually want, as a new grad graduating Dec 2026.
TARGET_TRACKS = {"data_engineering", "ai_ml_engineering", "software_engineering"}

# Geographies you can realistically take.
TARGET_GEOS = {"US", "Remote-US"}

# Companies that gate on US citizenship / clearance (defense, FFRDC, some fed).
# Networking cannot open these for a candidate needing sponsorship.
CITIZENSHIP_GATED = {"MITRE", "SimVentions", "Booz Allen Hamilton"}

# Tracks that are a different career (you can pursue, but flag the drift).
OFF_TRACK = {"quant_trading"}


# ----------------------------------------------------------------------------- #
# 2. PARSING  (raw email -> structured fields)
# ----------------------------------------------------------------------------- #

REJECT_PATTERNS = [
    r"move forward with other candidates",
    r"unable to (find|offer|move)",
    r"not (?:be )?able to offer",
    r"decided to (?:move|proceed)",
    r"unfortunately",
    r"were not able to offer",
    r"other candidates that better",
    r"not (?:been )?selected",
]

QUANT_HINTS = ["jane street", "quantbot", "headlands", "cartesian", "lazard",
               "trading", "quant"]
DATA_ENG_HINTS = ["data engineer", "data engineering", "databricks", "spark",
                  "sql", "etl", "customer data"]
AIML_HINTS = ["ai engineer", "ai-native", "machine learning", "ml ", "ai/ml",
              "ai engineering", "applied ai", "ai development", "ai lab", "(ai)"]
DS_HINTS = ["data scientist", "data science", "data analyst", "analytics"]
SWE_HINTS = ["software engineer", "software developer", "software development",
             "swe", "full stack", "backend"]

NON_US_HINTS = {
    "UK": ["uk -", "london", "burgess hill"],
    "Canada": ["canada", "export development canada", "winter 2027) job"],
    "Colombia": ["colombia", "ingeniero"],
    "Singapore": ["ncs"],
    "EU": ["stage", "eu-frankfurt", "bip ai lab", "n-ix", "-frankfurt-"],
}


def detect_status(snippet: str) -> str:
    s = snippet.lower()
    for pat in REJECT_PATTERNS:
        if re.search(pat, s):
            return "rejected"
    return "received"


def detect_track(text: str) -> str:
    t = text.lower()
    if any(h in t for h in QUANT_HINTS):
        return "quant_trading"
    if any(h in t for h in DATA_ENG_HINTS):
        return "data_engineering"
    if any(h in t for h in AIML_HINTS):
        return "ai_ml_engineering"
    if any(h in t for h in SWE_HINTS):
        return "software_engineering"
    if any(h in t for h in DS_HINTS):
        return "data_science"
    return "other"


def detect_geo(company: str, text: str) -> str:
    t = (company + " " + text).lower()
    for geo, hints in NON_US_HINTS.items():
        if any(h in t for h in hints):
            return geo
    if "remote" in t:
        return "Remote-US"
    return "US"


def detect_level(text: str) -> str:
    t = text.lower()
    if "intern" in t or "co-op" in t or "stage" in t or "trainee" in t or "fellowship" in t:
        return "intern"
    if "new grad" in t or "graduate" in t or "campus" in t or "entry" in t or "junior" in t or "associate" in t or "new grad" in t:
        return "new_grad"
    return "unknown"


# ----------------------------------------------------------------------------- #
# 3. SCORING  (structured fields -> networking priority + play)
# ----------------------------------------------------------------------------- #

@dataclass
class Application:
    company: str
    role: str
    date: str
    status: str = ""
    track: str = ""
    geo: str = ""
    level: str = ""
    sponsor_ok: bool = True
    priority: str = ""          # HIGH / MED / LOW / SKIP
    reason: str = ""
    outreach_play: str = ""

    def score(self):
        # SKIP: no point networking
        if self.status == "rejected":
            self.priority, self.reason = "SKIP", "already rejected"
            return
        if self.company in CITIZENSHIP_GATED:
            self.priority, self.reason = "SKIP", "US-citizenship / clearance gate"
            self.sponsor_ok = False
            return
        if self.geo not in TARGET_GEOS:
            self.priority, self.reason = "LOW", f"geo mismatch ({self.geo})"
            return
        if self.track in OFF_TRACK:
            self.priority, self.reason = "LOW", "off-track (quant/trading)"
            return
        if self.track in TARGET_TRACKS:
            self.priority, self.reason = "HIGH", "live + on-track + US + sponsor-ok"
        else:
            self.priority, self.reason = "MED", f"live but track={self.track}"

    def make_play(self):
        if self.priority in ("SKIP", "LOW"):
            self.outreach_play = "—"
            return
        # who to target, in priority order
        self.outreach_play = (
            "1) recent grads in this exact program (highest reply rate) "
            "2) alumni from your school at the company "
            "3) the req's recruiter / TA. "
            "Angle: 'applied to <role>, would value one insight on what makes an app stand out.'"
        )


# ----------------------------------------------------------------------------- #
# 4. RAW DATA  (real pull, 2026-09-15 -> 2026-09-19 window)
# ----------------------------------------------------------------------------- #

RAW = [
    ("Healthesystems", "Intern, AI Engineer (PT, Remote)", "2026-09-19", "received"),
    ("Study.com", "AI-Native Software Engineer (New Grad)", "2026-09-19", "received"),
    ("EXL", "Data Engineer", "2026-09-19", "received"),
    ("Sia", "Consulting (Data/AI)", "2026-09-19", "received"),
    ("Lazard", "2027 Software Engineer Summer Internship", "2026-09-19", "received"),
    ("Oracle (EU)", "Data & AI - Stage", "2026-09-19", "received"),
    ("Scale AI", "Software Engineer Intern (Summer 2027)", "2026-09-18", "rejected"),
    ("CapTech", "New Grad (Tech)", "2026-09-18", "received"),
    ("MITRE", "TECH Futures Intern", "2026-09-18", "received"),
    ("JPMorgan Chase", "2027 Software Engineer Program (FT)", "2026-09-18", "received"),
    ("SimVentions", "SEDSS Software Developer", "2026-09-18", "received"),
    ("Inetum Colombia", "Ingeniero SQL - Spark", "2026-09-18", "received"),
    ("NCS", "Junior Data Engineer (Databricks)", "2026-09-18", "received"),
    ("Export Development Canada", "Student/New Grad Tech & Analytics (Winter 2027)", "2026-09-18", "received"),
    ("GM Financial", "Intern - Technology Innovation Lab", "2026-09-18", "received"),
    ("VML MAP", "Associate Data Engineer", "2026-09-18", "received"),
    ("SharkNinja", "Applied AI & Analytics Co-op", "2026-09-18", "received"),
    ("NCS", "Junior Data Scientist", "2026-09-18", "received"),
    ("Klaviyo", "Software Engineer I", "2026-09-17", "rejected"),
    ("Booz Allen Hamilton", "Data Scientist, Junior", "2026-09-17", "received"),
    ("BIP AI LAB", "Junior Data Scientist", "2026-09-17", "received"),
    ("WPP", "Tech (Data/AI)", "2026-09-17", "received"),
    ("EarnIn", "Software Engineer", "2026-09-17", "received"),
    ("BIP AI LAB", "Junior Data Engineer", "2026-09-17", "received"),
    ("Headlands Technologies", "Quant/SWE", "2026-09-17", "received"),
    ("UDig", "Consulting (Data)", "2026-09-17", "received"),
    ("Reply", "AI/Machine Learning Intern", "2026-09-17", "received"),
    ("Jane Street", "SWE / Trading", "2026-09-17", "received"),
    ("Cartesian Systems", "Software Engineer", "2026-09-17", "received"),
    ("Coram AI", "Graduate Software Engineer", "2026-09-17", "received"),
    ("Itential", "Software Engineer", "2026-09-17", "received"),
    ("Emergent Labs", "Software Engineer", "2026-09-17", "received"),
    ("Jabil", "Supply Chain Data Analyst Intern", "2026-09-16", "rejected"),
    ("Brivo", "Software Engineer - New Grad", "2026-09-16", "rejected"),
    ("Quantbot", "Data Trading Analyst Summer Intern 2027 (NY)", "2026-09-16", "rejected"),
    ("Red Bull", "Internship Data Science", "2026-09-16", "received"),
    ("NISC", "Intern - Software Dev (AI)", "2026-09-16", "received"),
    ("NielsenIQ", "Software Engineer (AI)", "2026-09-16", "received"),
    ("N-iX", "Trainee AI Engineer", "2026-09-16", "received"),
    ("Optimove", "Customer Data Engineer", "2026-09-16", "received"),
    ("Texas Instruments", "IT Intern - Data Engineering", "2026-09-16", "received"),
    ("EarnIn", "Software Engineer (dup)", "2026-09-16", "received"),
    ("Gomry", "Silicon Valley Fellowship", "2026-09-15", "rejected"),
    ("Jane Street", "SWE / Trading", "2026-09-15", "rejected"),
    ("Jane Street", "SWE / Trading", "2026-09-15", "received"),
    ("Cherry Technologies", "Software Engineer, Entry-Level", "2026-09-15", "received"),
    ("Securian Financial", "Engineering Internship Summer 2027", "2026-09-15", "rejected"),
    ("American Express", "Campus FT Software Engineer 2027 (UK)", "2026-09-15", "received"),
    ("American Express", "Campus Intern Undergrad AI Engineer 2027 (UK)", "2026-09-15", "received"),
]


def build(raw):
    apps = []
    for company, role, date, status in raw:
        text = f"{company} {role}"
        a = Application(
            company=company, role=role, date=date,
            status=status or detect_status(role),
            track=detect_track(text),
            geo=detect_geo(company, text),
            level=detect_level(text),
        )
        a.score()
        a.make_play()
        apps.append(a)
    return apps


def dedupe(apps):
    seen, out = set(), []
    for a in apps:
        key = (a.company.lower(), a.track, a.geo)
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


def metrics(apps):
    total = len(apps)
    rej = sum(a.status == "rejected" for a in apps)
    live = total - rej
    gated = sum(a.priority == "SKIP" and "gate" in a.reason for a in apps)
    high = sum(a.priority == "HIGH" for a in apps)
    med = sum(a.priority == "MED" for a in apps)
    low = sum(a.priority == "LOW" for a in apps)
    non_us = sum(a.geo not in TARGET_GEOS for a in apps)
    quant = sum(a.track == "quant_trading" for a in apps)
    intern = sum(a.level == "intern" for a in apps)
    return {
        "total_apps_in_sample": total,
        "already_rejected": rej,
        "still_live": live,
        "citizenship_gated (wasted)": gated,
        "non_US_geo": non_us,
        "off_track_quant": quant,
        "intern_level (you graduate Dec 2026)": intern,
        "WORTH_NETWORKING (HIGH)": high,
        "maybe (MED)": med,
        "deprioritize (LOW)": low,
    }


def main():
    out_dir = Path(__file__).resolve().parent.parent / "data"
    out_dir.mkdir(exist_ok=True)
    apps = dedupe(build(RAW))

    csv_path = out_dir / "applications.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(apps[0]).keys()))
        w.writeheader()
        for a in apps:
            w.writerow(asdict(a))

    print(f"\nWrote {len(apps)} deduped applications -> {csv_path}\n")
    print("FUNNEL METRICS")
    print("-" * 42)
    for k, v in metrics(apps).items():
        print(f"{k:<42} {v}")

    print("\nTOP NETWORKING TARGETS (HIGH priority, live, on-track, US):")
    print("-" * 42)
    for a in sorted(apps, key=lambda x: x.priority):
        if a.priority == "HIGH":
            print(f"  • {a.company:<26} {a.role}")


if __name__ == "__main__":
    main()
