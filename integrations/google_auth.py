"""
Run this once to authorize Ronny to access your Google Calendar.
It will open a browser window for you to log in and grant permission.
A token.json file will be saved in the project root for future use.

Usage:
    venv\\Scripts\\python integrations\\google_auth.py
"""
import os
import sys

# Run from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


def main():
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"ERROR: {CREDENTIALS_FILE} not found in project root.")
        print("Download it from Google Cloud Console → APIs & Services → Credentials.")
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())

    print(f"Authorization successful. Token saved to {TOKEN_FILE}.")


if __name__ == "__main__":
    main()
