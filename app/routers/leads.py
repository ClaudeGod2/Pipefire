from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Lead
from app.templating import templates

router = APIRouter()


@router.post("/leads/{lid}/status")
def update_status(lid: int, request: Request, call_status: str = Form(...), db: Session = Depends(get_db)):
    l = db.get(Lead, lid)
    if not l:
        raise HTTPException(404)
    l.call_status = call_status
    if call_status and call_status != "Ej kontaktad":
        l.call_date = date.today()
    db.commit()
    return templates.TemplateResponse("partials/lead_row.html", {"request": request, "lead": l})


@router.post("/leads/{lid}/comment")
def update_comment(lid: int, request: Request, comment: str = Form(""), db: Session = Depends(get_db)):
    l = db.get(Lead, lid)
    if not l:
        raise HTTPException(404)
    l.comment = comment
    db.commit()
    return HTMLResponse(f'<span hx-post="/leads/{l.id}/comment-edit" hx-swap="outerHTML" class="cursor-pointer text-slate-700">{comment or "—"}</span>')


@router.post("/leads/{lid}/comment-edit")
def edit_comment(lid: int, db: Session = Depends(get_db)):
    l = db.get(Lead, lid)
    if not l:
        raise HTTPException(404)
    html = (
        f'<form hx-post="/leads/{l.id}/comment" hx-swap="outerHTML" class="flex gap-1">'
        f'<input name="comment" value="{(l.comment or "").replace(chr(34), "&quot;")}" '
        f'class="border px-1 py-0.5 text-xs rounded w-full" autofocus />'
        f'<button class="text-xs text-blue-600">✓</button></form>'
    )
    return HTMLResponse(html)
