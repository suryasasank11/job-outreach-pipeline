# Job Application → Networking Pipeline

Turns raw Gmail application-confirmation emails into a prioritized outreach plan.

## What it does
1. **Ingest** — pulls application-confirmation emails via the Gmail API.
2. **Parse** — extracts company, role, date, and detects **status** (received vs auto-rejected).
3. **Classify** — tags each app by **track** (data-eng / AI-ML / SWE / DS / quant),
   **geography**, **level**, and **sponsorship risk** (US-citizenship-gated employers).
4. **Score** — assigns a **networking priority** (HIGH / MED / LOW / SKIP) so effort
   goes only where a message can move the needle.
5. **Play** — for each HIGH app, outputs *who to contact and the angle*.
6. **Metrics** — a funnel: applied → rejected → live → worth-networking.

## Why the LinkedIn step is manual (by design)
Automating a logged-in LinkedIn account to scrape profiles violates LinkedIn's
User Agreement and risks account restriction. The pipeline outputs *who to look for
and why*; the 30-second search is run by hand. Protecting the account is the
correct engineering trade-off.

## Run
```bash
pip install -r requirements.txt
python3 src/pipeline.py        # writes data/applications.csv + prints metrics
```

## Architecture
Gmail API → parser → classifier → scorer → CSV tracker + metrics.
Config-driven: edit TARGET_TRACKS / TARGET_GEOS / CITIZENSHIP_GATED at the top of
`src/pipeline.py` to re-steer the whole funnel.

## Daily-updatable (built)
- `src/gmail_client.py` — headless OAuth via refresh token; 3-day overlap query.
- `src/daily.py` — stateful run: upsert by Gmail message id, propagate status flips,
  emit a diff ("N new · M rejections"). State lives in `data/state.json`.
- `.github/workflows/every-2-days.yml` — runs every 2 days, commits the tracker back.

## Live dashboard (GitHub Pages)
Every run regenerates `public/index.html` from the fresh tracker and deploys it to
GitHub Pages — one fixed URL you bookmark and refresh. De-identified by default
(Pages is public). Repo → Settings → Pages → Source = **GitHub Actions**.
URL: `https://<user>.github.io/<repo>/`

### One-time setup
1. `python3 get_refresh_token.py` locally → prints 3 values.
2. GitHub → Settings → Secrets → Actions → add `GMAIL_CLIENT_ID`,
   `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`.
3. Push. The workflow runs on schedule; trigger manually via the Actions tab to test.

## Roadmap (v2)
- [ ] Persist to Postgres instead of committed JSON
- [ ] Response-rate per outreach → real ROI metric
- [ ] Event-driven Cloud Function on each new confirmation email
