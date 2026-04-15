from fastapi.templating import Jinja2Templates
from app.services import gmail_client

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["gmail_authorized"] = gmail_client.is_authorized
