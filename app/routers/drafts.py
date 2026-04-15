from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from datetime import datetime

from app.config import settings
from app.database import get_db
from app.models import Campaign, Lead, EmailDraft
from app.services import mail_generator, gmail_client
from app.templating import templates

router = APIRouter()


def _eligible_leads(campaign: Campaign) -> list[Lead]:
    out = []
    for l in campaign.leads:
        if not l.email:
            continue
        if l.mx_status not in ("ok", "catch_all"):
            continue
        if l.call_status and l.call_status != "Ej kontaktad":
            continue
        if any(d.attempt == 1 for d in l.drafts):
            continue
        out.append(l)
    return out


@router.get("/campaigns/{cid}/drafts")
def drafts_page(cid: int, request: Request, db: Session = Depends(get_db)):
    c = db.get(Campaign, cid)
    if not c:
        raise HTTPException(404)
    drafts = (
        db.query(EmailDraft)
        .join(Lead)
        .filter(Lead.campaign_id == cid, EmailDraft.attempt == 1)
        .all()
    )
    eligible = _eligible_leads(c)
    return templates.TemplateResponse("drafts.html", {
        "request": request,
        "campaign": c,
        "drafts": drafts,
        "eligible_count": len(eligible),
    })


@router.post("/campaigns/{cid}/drafts/generate")
def generate_drafts(cid: int, db: Session = Depends(get_db)):
    c = db.get(Campaign, cid)
    if not c:
        raise HTTPException(404)
    for lead in _eligible_leads(c):
        d = EmailDraft(
            lead_id=lead.id,
            subject=mail_generator.generate_subject(lead),
            body=mail_generator.generate_body(lead, settings.sender_name),
            status="pending",
            attempt=1,
        )
        db.add(d)
    db.commit()
    return RedirectResponse(f"/campaigns/{cid}/drafts", status_code=303)


@router.post("/drafts/{did}/approve")
def approve(did: int, db: Session = Depends(get_db)):
    d = db.get(EmailDraft, did)
    if not d:
        raise HTTPException(404)
    d.status = "approved"
    db.commit()
    return HTMLResponse('<span class="text-green-700 font-semibold">Godkänd</span>')


@router.post("/drafts/{did}/reject")
def reject(did: int, db: Session = Depends(get_db)):
    d = db.get(EmailDraft, did)
    if not d:
        raise HTTPException(404)
    d.status = "rejected"
    db.commit()
    return HTMLResponse('<span class="text-slate-500">Hoppad över</span>')


@router.post("/campaigns/{cid}/drafts/push")
def push_drafts(cid: int, db: Session = Depends(get_db)):
    c = db.get(Campaign, cid)
    if not c:
        raise HTTPException(404)
    if not gmail_client.is_authorized():
        return HTMLResponse('<div class="text-red-600">Gmail är inte kopplat. <a class="underline" href="/auth/gmail">Koppla först</a>.</div>')
    drafts = (
        db.query(EmailDraft)
        .join(Lead)
        .filter(Lead.campaign_id == cid, EmailDraft.status == "approved", EmailDraft.gmail_draft_id.is_(None))
        .all()
    )
    ok, fail = 0, 0
    for d in drafts:
        lead = d.lead
        try:
            draft_id, thread_id = gmail_client.create_draft(lead.email, d.subject, d.body)
            d.gmail_draft_id = draft_id
            d.gmail_thread_id = thread_id
            d.status = "sent"
            d.sent_at = datetime.utcnow()
            ok += 1
        except Exception as e:
            d.status = "error"
            fail += 1
    db.commit()
    return HTMLResponse(
        f'<div class="text-green-700">✓ {ok} utkast skapade i Gmail'
        + (f' — {fail} misslyckade' if fail else '')
        + '</div>'
    )
