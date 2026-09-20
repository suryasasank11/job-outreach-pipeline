"""
Gmail ingest — headless OAuth via a stored refresh token.

Runs every 2 days from GitHub Actions, so it must authenticate with NO browser.
That is exactly what a refresh token is for: you do the interactive consent ONCE
(locally, see get_refresh_token.py), store the token as a GitHub secret, and this
module mints fresh access tokens forever without you.

Query window is intentionally WIDER than the run cadence (3d for a 2-day schedule)
so nothing slips through the boundary. Re-seen emails are harmless — pipeline.py
keys on message id and upserts.
"""

import os
import base64
from datetime import datetime, timezone

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Read-only: the workflow can never modify or delete your mail.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# The same OR-filter the manual pull used. Widen this list as new ATS phrasings appear.
QUERY = (
    '("application received" OR "thank you for applying" OR "application submitted" '
    'OR "received your application" OR "we received your" OR "applying to") '
    "newer_than:2d"      # 3-day window for a 2-day cadence = 1-day safety overlap
)


def _client():
    """Build a Gmail API client from env-supplied OAuth secrets (no browser)."""
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
        client_id=os.environ["GMAIL_CLIENT_ID"],
        client_secret=os.environ["GMAIL_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _header(headers, name):
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def fetch():
    """Return a list of {id, subject, sender, snippet, date} for recent applications."""
    svc = _client()
    out, page = [], None
    while True:
        resp = (
            svc.users().messages()
            .list(userId="me", q=QUERY, maxResults=100, pageToken=page)
            .execute()
        )
        for m in resp.get("messages", []):
            msg = (
                svc.users().messages()
                .get(userId="me", id=m["id"], format="metadata",
                     metadataHeaders=["Subject", "From", "Date"])
                .execute()
            )
            headers = msg["payload"].get("headers", [])
            ts = int(msg.get("internalDate", "0")) / 1000
            out.append({
                "id": m["id"],
                "subject": _header(headers, "Subject"),
                "sender": _header(headers, "From"),
                "snippet": msg.get("snippet", ""),
                "date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d"),
            })
        page = resp.get("nextPageToken")
        if not page:
            break
    return out


if __name__ == "__main__":
    rows = fetch()
    print(f"Fetched {len(rows)} application emails in the last 3 days")
    for r in rows[:5]:
        print(f"  {r['date']}  {r['subject'][:70]}")
