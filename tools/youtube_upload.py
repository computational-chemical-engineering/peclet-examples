#!/usr/bin/env python3
"""Upload a gallery movie to the @PecletCode YouTube channel (YouTube Data API v3).

One-time authorisation (interactive, run it yourself):
    python tools/youtube_upload.py --auth
  It starts a tiny local server on port 8765 and prints a Google URL: open it in a browser (with a
  VS Code remote session the port is forwarded automatically), approve, and the refresh token is
  stored in ~/.config/peclet-youtube/token.json (mode 600, never in a repo).

Upload (non-interactive once the token exists):
    python tools/youtube_upload.py upload --file examples/<slug>/<movie>.mp4 \
        --title "..." --description "..." [--tags a,b,c] [--privacy unlisted|public|private]
  Prints the video id and the watch/embed URLs. Default privacy: unlisted (review before public).

Credentials: ~/.config/peclet-youtube/client_secret.json (an OAuth "Desktop app" client of a
Google Cloud project with YouTube Data API v3 enabled; the channel owner added as a test user).
An upload costs 1600 quota units of the default 10 000/day.
"""
import argparse
import json
import os
import sys
from pathlib import Path

CONF = Path.home() / ".config" / "peclet-youtube"
CLIENT = CONF / "client_secret.json"
TOKEN = CONF / "token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def credentials(interactive: bool):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        if not interactive:
            sys.exit(f"no valid token at {TOKEN}: run `python tools/youtube_upload.py --auth` first")
        from google_auth_oauthlib.flow import InstalledAppFlow

        if not CLIENT.exists():
            sys.exit(f"missing {CLIENT}")
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT), SCOPES)
        creds = flow.run_local_server(port=8765, open_browser=False,
                                      authorization_prompt_message="Open this URL in a browser:\n{url}\n")
        CONF.mkdir(parents=True, exist_ok=True)
        TOKEN.write_text(creds.to_json())
        os.chmod(TOKEN, 0o600)
        print(f"token stored at {TOKEN}")
    return creds


def upload(args):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = credentials(interactive=False)
    yt = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": args.title,
            "description": args.description,
            "tags": [t for t in (args.tags or "").split(",") if t],
            "categoryId": "28",  # Science & Technology
        },
        "status": {"privacyStatus": args.privacy, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(args.file, mimetype="video/mp4", resumable=True, chunksize=4 * 1024 * 1024)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"  {int(status.progress() * 100)} %", flush=True)
    vid = resp["id"]
    print(json.dumps({"id": vid, "watch": f"https://www.youtube.com/watch?v={vid}",
                      "embed": f"https://www.youtube.com/embed/{vid}", "privacy": args.privacy}, indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--auth", action="store_true", help="run the one-time interactive authorisation")
    sub = ap.add_subparsers(dest="cmd")
    up = sub.add_parser("upload")
    up.add_argument("--file", required=True)
    up.add_argument("--title", required=True)
    up.add_argument("--description", default="")
    up.add_argument("--tags", default="peclet,CFD,VoF,two-phase flow,GPU")
    up.add_argument("--privacy", default="unlisted", choices=["unlisted", "public", "private"])
    args = ap.parse_args()
    if args.auth:
        credentials(interactive=True)
        return
    if args.cmd == "upload":
        upload(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
