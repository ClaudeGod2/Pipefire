from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from google_auth_oauthlib.flow import Flow

from app.config import settings
from app.services import gmail_client
from app.services.gmail_client import SCOPES

router = APIRouter()


def _flow() -> Flow:
    config = {
        "web": {
            "client_id": settings.gmail_client_id,
            "client_secret": settings.gmail_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.gmail_redirect_uri],
        }
    }
    flow = Flow.from_client_config(config, scopes=SCOPES)
    flow.redirect_uri = settings.gmail_redirect_uri
    return flow


@router.get("/auth/gmail")
def gmail_auth():
    if not settings.gmail_client_id:
        return HTMLResponse(
            '<div style="font-family:sans-serif;padding:40px">'
            '<h2>Gmail OAuth är inte konfigurerat</h2>'
            '<p>Sätt GMAIL_CLIENT_ID och GMAIL_CLIENT_SECRET i .env.</p>'
            '<a href="/">Tillbaka</a></div>',
            status_code=500,
        )
    flow = _flow()
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline", include_granted_scopes="true")
    return RedirectResponse(auth_url)


@router.get("/auth/gmail/callback")
def gmail_callback(code: str):
    flow = _flow()
    flow.fetch_token(code=code)
    creds = flow.credentials
    import os
    os.makedirs(os.path.dirname(settings.gmail_token_path) or ".", exist_ok=True)
    with open(settings.gmail_token_path, "w") as f:
        f.write(creds.to_json())
    return RedirectResponse("/")


@router.get("/auth/gmail/status")
def gmail_status():
    if gmail_client.is_authorized():
        return HTMLResponse('<span class="text-green-700 text-xs">● Gmail kopplat</span>')
    return HTMLResponse('<a href="/auth/gmail" class="text-red-600 text-xs underline">● Koppla Gmail</a>')


@router.post("/auth/gmail/disconnect")
def gmail_disconnect():
    gmail_client.delete_token()
    return RedirectResponse("/", status_code=303)
