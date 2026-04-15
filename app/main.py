from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routers import campaigns, leads, drafts, tracking, gmail_auth

app = FastAPI(title="Pipefire")


@app.on_event("startup")
def _startup():
    init_db()


app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(campaigns.router)
app.include_router(leads.router)
app.include_router(drafts.router)
app.include_router(tracking.router)
app.include_router(gmail_auth.router)
