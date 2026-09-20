"""
RUN THIS ONCE, ON YOUR LAPTOP. Not in CI.

It opens a browser, you approve read-only Gmail access, and it prints the three
values you paste into GitHub Secrets. After this, the daily workflow never needs
a browser again.

Setup before running:
  1. Google Cloud Console -> create a project.
  2. APIs & Services -> Library -> enable "Gmail API".
  3. APIs & Services -> OAuth consent screen -> External -> add yourself as a Test user.
  4. Credentials -> Create Credentials -> OAuth client ID -> "Desktop app".
     Download the JSON, save it next to this file as  client_secret.json.
  5. pip install google-auth-oauthlib
  6. python3 get_refresh_token.py
"""

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=0)   # opens browser, one-time consent

print("\n=== paste these into GitHub -> Settings -> Secrets -> Actions ===\n")
print("GMAIL_CLIENT_ID     =", creds.client_id)
print("GMAIL_CLIENT_SECRET =", creds.client_secret)
print("GMAIL_REFRESH_TOKEN =", creds.refresh_token)
print("\nKeep these private. Never commit client_secret.json — it's in .gitignore.")
