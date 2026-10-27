"""One-time sign-in: get a Google Calendar refresh token for the calendar server.

Run it once on your own computer (not in Docker), see the README section
"Calendar". A browser opens; sign in with the interviewer's Google account
and click Allow. The script prints a refresh token: put it in .env as
CALENDAR_REFRESH_TOKEN. Never commit it or paste it into a chat.

    python get_refresh_token.py <client_id> <client_secret>
"""

import sys

from google_auth_oauthlib.flow import InstalledAppFlow

CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"


def main() -> None:
    """Open the Google sign-in in a browser and print the refresh token."""
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    client_id, client_secret = sys.argv[1], sys.argv[2]
    config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(config, scopes=[CALENDAR_SCOPE])
    # prompt="consent" makes Google return a refresh token every time.
    credentials = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    print("\nCALENDAR_REFRESH_TOKEN=" + credentials.refresh_token)
    print("\nCopy that line into .env. Keep it secret.")


if __name__ == "__main__":
    main()
