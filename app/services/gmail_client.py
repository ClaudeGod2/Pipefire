import base64
import json
import os
from email.mime.text import MIMEText
from datetime import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.config import settings

SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.readonly",
]


class GmailNotAuthorizedError(Exception):
    pass


def is_authorized() -> bool:
    path = settings.gmail_token_path
    if not os.path.exists(path):
        return False
    try:
        creds = Credentials.from_authorized_user_file(path, SCOPES)
        if creds.valid:
            return True
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(path, "w") as f:
                f.write(creds.to_json())
            return True
        return False
    except Exception:
        return False


def get_credentials() -> Credentials:
    path = settings.gmail_token_path
    if not os.path.exists(path):
        raise GmailNotAuthorizedError("No token found. Run OAuth flow first.")
    creds = Credentials.from_authorized_user_file(path, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(path, "w") as f:
                f.write(creds.to_json())
        else:
            raise GmailNotAuthorizedError("Token invalid.")
    return creds


def _service():
    return build("gmail", "v1", credentials=get_credentials(), cache_discovery=False)


def create_draft(to: str, subject: str, body: str, thread_id: str | None = None) -> tuple[str, str]:
    svc = _service()
    msg = MIMEText(body, "plain", "utf-8")
    msg["To"] = to
    msg["Subject"] = subject
    if settings.gmail_send_as:
        msg["From"] = settings.gmail_send_as
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    message_body: dict = {"raw": raw}
    if thread_id:
        message_body["threadId"] = thread_id
    draft = svc.users().drafts().create(
        userId="me", body={"message": message_body}
    ).execute()
    return draft["id"], draft["message"]["threadId"]


def search_sent_threads(query: str = "in:sent") -> list[dict]:
    svc = _service()
    res = svc.users().messages().list(userId="me", q=query, maxResults=200).execute()
    messages = res.get("messages", [])
    threads_seen: dict[str, dict] = {}
    for m in messages:
        tid = m["threadId"]
        if tid in threads_seen:
            continue
        thread = svc.users().threads().get(userId="me", id=tid, format="metadata",
                                           metadataHeaders=["To", "From", "Subject", "Date"]).execute()
        msgs = thread.get("messages", [])
        if not msgs:
            continue
        first = msgs[0]
        headers = {h["name"]: h["value"] for h in first.get("payload", {}).get("headers", [])}
        has_reply = False
        my_email = settings.gmail_send_as.lower()
        for msg in msgs[1:]:
            h = {x["name"]: x["value"] for x in msg.get("payload", {}).get("headers", [])}
            sender = (h.get("From") or "").lower()
            if my_email and my_email in sender:
                continue
            has_reply = True
            break
        ts = int(first.get("internalDate", 0)) / 1000 if first.get("internalDate") else 0
        sent_date = datetime.fromtimestamp(ts).isoformat() if ts else ""
        threads_seen[tid] = {
            "thread_id": tid,
            "to": headers.get("To", ""),
            "subject": headers.get("Subject", ""),
            "sent_date": sent_date,
            "has_reply": has_reply,
        }
    return list(threads_seen.values())


def read_thread(thread_id: str) -> dict:
    svc = _service()
    return svc.users().threads().get(userId="me", id=thread_id, format="full").execute()


def delete_token():
    path = settings.gmail_token_path
    if os.path.exists(path):
        os.remove(path)
