import asyncio
import json
import io

from fastapi import APIRouter, Depends, Request, Form, BackgroundTasks, HTTPException
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import Campaign, Lead, EmailDraft
from app.services.pipeline import run_pipeline
from app.services.excel_export import build_workbook
from app.templating import templates

router = APIRouter()


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    campaigns = db.query(Campaign).order_by(Campaign.created_at.desc()).all()
    stats = {}
    for c in campaigns:
        lead_ids = [l.id for l in c.leads]
        mx_ok = sum(1 for l in c.leads if l.mx_status == "ok")
        drafted = db.query(EmailDraft).filter(EmailDraft.lead_id.in_(lead_ids)).count() if lead_ids else 0
        sent = db.query(EmailDraft).filter(EmailDraft.lead_id.in_(lead_ids), EmailDraft.status.in_(["sent", "replied", "cold"])).count() if lead_ids else 0
        replied = db.query(EmailDraft).filter(EmailDraft.lead_id.in_(lead_ids), EmailDraft.status == "replied").count() if lead_ids else 0
        stats[c.id] = {"leads": len(c.leads), "mx_ok": mx_ok, "drafted": drafted, "sent": sent, "replied": replied}
    return templates.TemplateResponse("dashboard.html", {"request": request, "campaigns": campaigns, "stats": stats})


@router.get("/campaigns/new")
def new_campaign(request: Request):
    return templates.TemplateResponse("campaign_new.html", {"request": request})


@router.post("/campaigns")
def create_campaign(
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    sni_prefix: str = Form(...),
    min_klass: int = Form(3),
    max_klass: int = Form(9),
    min_msek: int = Form(0),
    max_bolag: int = Form(50),
    db: Session = Depends(get_db),
):
    c = Campaign(name=name, sni_prefix=sni_prefix, min_klass=min_klass, max_klass=max_klass,
                 min_msek=min_msek, max_bolag=max_bolag, status="pending")
    db.add(c)
    db.commit()
    db.refresh(c)
    background_tasks.add_task(run_pipeline, c.id)
    return RedirectResponse(f"/campaigns/{c.id}", status_code=303)


@router.get("/campaigns/{cid}")
def campaign_detail(cid: int, request: Request, db: Session = Depends(get_db)):
    c = db.get(Campaign, cid)
    if not c:
        raise HTTPException(404)
    mx_prio = {"ok": 0, "catch_all": 1, "error": 2, "no_mx": 3, "invalid": 4}
    leads = sorted(c.leads, key=lambda l: (mx_prio.get(l.mx_status, 3), l.company_name or ""))
    return templates.TemplateResponse("campaign_detail.html", {"request": request, "campaign": c, "leads": leads})


@router.get("/campaigns/{cid}/progress")
async def campaign_progress(cid: int):
    async def gen():
        while True:
            db = SessionLocal()
            try:
                c = db.get(Campaign, cid)
                if not c:
                    yield f"data: {json.dumps({'done': True, 'error': 'not found'})}\n\n"
                    return
                data = {
                    "progress": c.progress,
                    "done": c.status in ("done", "error"),
                    "status": c.status,
                    "leads": len(c.leads),
                    "error": c.error_msg,
                }
                yield f"data: {json.dumps(data)}\n\n"
                if c.status in ("done", "error"):
                    return
            finally:
                db.close()
            await asyncio.sleep(1)
    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/campaigns/{cid}/export")
def export_excel(cid: int, db: Session = Depends(get_db)):
    c = db.get(Campaign, cid)
    if not c:
        raise HTTPException(404)
    wb = build_workbook(c, c.leads)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    safe = (c.name or f"campaign_{cid}").replace(" ", "_").replace("/", "_")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{safe}.xlsx"'},
    )


@router.post("/campaigns/{cid}/delete")
def delete_campaign(cid: int, db: Session = Depends(get_db)):
    c = db.get(Campaign, cid)
    if c:
        db.delete(c)
        db.commit()
    return RedirectResponse("/", status_code=303)
