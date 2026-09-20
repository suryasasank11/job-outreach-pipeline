"""
Render applications.csv -> a static dashboard (public/index.html) for GitHub Pages.

Called at the end of every run by daily.py, so the public dashboard always reflects
the latest state. De-identified by default (no personal name) because Pages is public;
pass deidentify=False for a local/private build.
"""

import csv
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "applications.csv"
OUT = ROOT / "public" / "index.html"

PILL = {"HIGH": "high", "MED": "med", "LOW": "low", "SKIP": "skip"}


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(csv_path: Path = CSV, out_path: Path = OUT, deidentify: bool = True):
    rows = list(csv.DictReader(open(csv_path)))
    if not rows:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("<h1>No applications tracked yet</h1>")
        return

    total = len(rows)
    rej = sum(r["status"] == "rejected" for r in rows)
    live = total - rej
    gated = sum(r["priority"] == "SKIP" and "gate" in r["reason"] for r in rows)
    nonus = sum(r["geo"] not in ("US", "Remote-US") for r in rows)
    quant = sum(r["track"] == "quant_trading" for r in rows)
    intern = sum(r["level"] == "intern" for r in rows)
    high = sum(r["priority"] == "HIGH" for r in rows)

    order = {"HIGH": 0, "MED": 1, "LOW": 2, "SKIP": 3}
    rows.sort(key=lambda r: (order.get(r["priority"], 9), r["company"]))

    trs = []
    for r in rows:
        st = "rej" if r["status"] == "rejected" else "ok"
        trs.append(
            f'<tr class="p-{PILL[r["priority"]]}">'
            f'<td class="co">{esc(r["company"])}</td>'
            f'<td class="ro">{esc(r["role"])}</td>'
            f'<td><span class="tag">{r["track"].replace("_"," ")}</span></td>'
            f'<td>{r["geo"]}</td>'
            f'<td><span class="st st-{st}">{r["status"]}</span></td>'
            f'<td><span class="pr pr-{PILL[r["priority"]]}">{r["priority"]}</span></td>'
            f'<td class="rs">{esc(r["reason"])}</td></tr>'
        )
    tbody = "\n".join(trs)

    cards_data = [
        ("Applications tracked", total, "neutral"),
        ("Already rejected", rej, "bad"),
        ("Still live", live, "good"),
        ("Citizenship-gated", gated, "bad"),
        ("Non-US geography", nonus, "bad"),
        ("Off-track (quant)", quant, "warn"),
        ("Intern-level", intern, "warn"),
        ("WORTH NETWORKING", high, "good"),
    ]
    cards = "\n".join(
        f'<div class="card c-{t}"><div class="n">{v}</div><div class="l">{esc(l)}</div></div>'
        for l, v, t in cards_data
    )

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    footer_left = "job-outreach-pipeline" if deidentify else "Jaya Surya Sasank — job-outreach-pipeline"

    html = f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Application Tracker</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600&family=Inter:wght@400;600&display=swap" rel="stylesheet">
<style>
:root{{--bg:#f6f5f1;--ink:#16181d;--card:#fff;--line:#e4e2db;--muted:#6b6a65;--red:#d23b2f;--good:#1f7a4d;--bad:#c0392b;--warn:#b8860b;
box-sizing:border-box;padding-top:env(safe-area-inset-top,0);padding-bottom:env(safe-area-inset-bottom,0);}}
@media(prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#16181d;--ink:#f6f5f1;--card:#1f2229;--line:#2e323b;--muted:#9a9992;--red:#ff6f5e;}}}}
:root[data-theme="dark"]{{--bg:#16181d;--ink:#f6f5f1;--card:#1f2229;--line:#2e323b;--muted:#9a9992;--red:#ff6f5e;}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,system-ui,sans-serif;line-height:1.5;padding:20px}}
h1{{font-family:'Space Grotesk',sans-serif;font-weight:600;font-size:clamp(22px,5vw,32px);margin:0 0 4px}}
.sub{{color:var(--muted);font-size:14px;margin-bottom:20px}}
.label{{font-family:'Space Grotesk',sans-serif;letter-spacing:.14em;text-transform:uppercase;font-size:11px;color:var(--red);font-weight:600;margin:26px 0 10px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}}
.card .n{{font-family:'Space Grotesk',sans-serif;font-weight:600;font-size:26px}}
.card .l{{font-size:12px;color:var(--muted);margin-top:2px}}
.c-good .n{{color:var(--good)}}.c-bad .n{{color:var(--bad)}}.c-warn .n{{color:var(--warn)}}
.wrap{{overflow-x:auto;border:1px solid var(--line);border-radius:14px;margin-top:6px}}
table{{border-collapse:collapse;width:100%;font-size:13px;min-width:720px}}
th,td{{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{font-family:'Space Grotesk',sans-serif;font-weight:600;font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);position:sticky;top:0;background:var(--card)}}
.co{{font-weight:600;white-space:nowrap}}.ro{{color:var(--muted)}}.rs{{color:var(--muted);font-size:12px}}
tr.p-high td{{background:color-mix(in srgb,var(--good) 8%,transparent)}}
.tag,.st,.pr{{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600;white-space:nowrap}}
.tag{{background:var(--line);color:var(--ink)}}
.st-ok{{background:color-mix(in srgb,var(--good) 18%,transparent);color:var(--good)}}
.st-rej{{background:color-mix(in srgb,var(--bad) 18%,transparent);color:var(--bad)}}
.pr-high{{background:var(--good);color:#fff}}.pr-med{{background:var(--warn);color:#fff}}
.pr-low{{background:var(--line);color:var(--muted)}}.pr-skip{{background:color-mix(in srgb,var(--bad) 15%,transparent);color:var(--bad)}}
.foot{{color:var(--muted);font-size:12px;margin-top:24px;display:flex;justify-content:space-between}}
</style></head><body>
<h1>Application Tracker</h1>
<div class="sub">Auto-generated from live Gmail data · refreshes every 2 days</div>
<div class="label">The funnel</div>
<div class="grid">{cards}</div>
<div class="label">The honest read</div>
<div class="card" style="border-left:3px solid var(--red)">
Widening the funnel isn't the strategy. {rej} rejected, {gated} citizenship-gated,
{nonus} non-US, {quant} off-track — that's the spray tax. Put the energy into the
<b>{high} HIGH-priority</b> live, on-track, US roles (green rows): that's where a warm
LinkedIn contact changes the outcome.
</div>
<div class="label">Prioritized — network the green rows first</div>
<div class="wrap"><table>
<thead><tr><th>Company</th><th>Role</th><th>Track</th><th>Geo</th><th>Status</th><th>Priority</th><th>Why</th></tr></thead>
<tbody>{tbody}</tbody></table></div>
<div class="foot"><span>{footer_left}</span><span>updated {stamp}</span></div>
</body></html>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)
    print(f"Rendered dashboard -> {out_path} ({len(html)} bytes)")


if __name__ == "__main__":
    render(deidentify="--identify" not in sys.argv)
