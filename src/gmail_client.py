import time
from googleapiclient.errors import HttpError


def fetch():
    """Return {id, subject, sender, snippet, date} for recent applications.
    Throttled + retried to stay under Gmail's per-minute quota during wide backfills."""
    svc = _client()
    out, page = [], None
    while True:
        resp = (
            svc.users().messages()
            .list(userId="me", q=QUERY, maxResults=100, pageToken=page)
            .execute()
        )
        for m in resp.get("messages", []):
            for attempt in range(5):                      # retry on rate limit
                try:
                    msg = (
                        svc.users().messages()
                        .get(userId="me", id=m["id"], format="metadata",
                             metadataHeaders=["Subject", "From", "Date"])
                        .execute()
                    )
                    break
                except HttpError as e:
                    if e.resp.status in (403, 429) and attempt < 4:
                        time.sleep(2 ** attempt)          # 1,2,4,8s backoff
                        continue
                    raise
            headers = msg["payload"].get("headers", [])
            ts = int(msg.get("internalDate", "0")) / 1000
            out.append({
                "id": m["id"],
                "subject": _header(headers, "Subject"),
                "sender": _header(headers, "From"),
                "snippet": msg.get("snippet", ""),
                "date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d"),
            })
            time.sleep(0.3)                                # ~200/min, under quota
        page = resp.get("nextPageToken")
        if not page:
            break
    return out