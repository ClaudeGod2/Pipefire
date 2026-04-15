from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Campaign, Lead, EmailDraft
from app.services import mail_generator, gmail_client
from app.templating import templates

router = APIRouter()


@router.get("/campaigns/{cid}/tracking")
def tracking(cid: int, request: Request, db: Session = Depends(get_db)):
    c = db.get(Campaign, cid)
    if not c:
        raise HTTPException(404)
    drafts = (
        db.query(EmailDraft)
        .join(Lead)
        .filter(Lead.campaign_id == cid)
        .all()
    )
    now = datetime.utcnow()
    sent, replied, waiting, needs_fu, cold = [], [], [], [], []
    for d in drafts:
        if d.status in ("sent", "replied", "cold"):
            sent.append(d)
        if d.status == "replied":
            replied.append(d)
        elif d.status == "sent" and d.sent_at:
            days = (now - d.sent_at).days
            if days >= settings.followup_cold:
                cold.append((d, days))
            elif days >= settings.followup_day_1 and d.attempt < 3:
                needs_fu.append((d, days))
            else:
                waiting.append((d, days))
    return templates.TemplateResponse("tracking.html", {
        "request": request,
        "campaign": c,
        "sent_count": len(sent),
        "replied": replied,
        "waiting": waiting,
        "needs_fu": needs_fu,
        "cold": cold,
    })


@router.post("/campaigns/{cid}/tracking/sync")
def sync(cid: int, db: Session = Depends(get_db)):
    c = db.get(Campaign, cid)
    if not c:
        raise HTTPException(404)
    if not gmail_client.is_authorized():
        return HTMLResponse('<div class="text-red-600">Gmail inte kopplat.</div>')
    threads = gmail_client.search_sent_threads()
    by_tid = {t["thread_id"]: t for t in threads}
    drafts = (
        db.query(EmailDraft)
        .join(Lead)
        .filter(Lead.campaign_id == cid, EmailDraft.gmail_thread_id.isnot(None))
        .all()
    )
    updated = 0
    for d in drafts:
        t = by_tid.get(d.gmail_thread_id)
        if not t:
            continue
        if t["has_reply"] and d.status != "replied":
            d.status = "replied"
            d.replied_at = datetime.utcnow()
            updated += 1
    db.commit()
    return HTMLResponse(f'<div class="text-green-700">✓ Synkad — {updated} uppdateringar</div>')


@router.post("/drafts/{did}/followup")
def create_followup(did: int, db: Session = Depends(get_db)):
    d = db.get(EmailDraft, did)
    if not d:
        raise HTTPException(404)
    if not gmail_client.is_authorized():
        return HTMLResponse('<div class="text-red-600">Gmail inte kopplat.</div>')
    lead = d.lead
    next_attempt = d.attempt + 1
    body = mail_generator.generate_followup_body(lead, next_attempt, settings.sender_name)
    subject = f"Re: {d.subject}" if not d.subject.lower().startswith("re:") else d.subject
    try:
        gid, tid = gmail_client.create_draft(lead.email, subject, body, thread_id=d.gmail_thread_id)
    except Exception as e:
        return HTMLResponse(f'<div class="text-red-600">Fel: {e}</div>')
    new = EmailDraft(
        lead_id=lead.id, subject=subject, body=body,
        gmail_draft_id=gid, gmail_thread_id=tid,
        status="sent", attempt=next_attempt, sent_at=datetime.utcnow(),
    )
    db.add(new)
    db.commit()
    return HTMLResponse(f'<span class="text-green-700">✓ Uppföljning #{next_attempt} skapad i Gmail</span>')
