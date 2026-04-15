import json
import urllib.request
from app.config import settings

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def fetch_company(orgnr: str) -> dict | None:
    url = f"{settings.abpi_base_url}/{orgnr}/data"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    if settings.abpi_api_key:
        req.add_header("Authorization", f"Bearer {settings.abpi_api_key}")
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=settings.abpi_timeout) as r:
                return json.loads(r.read())
        except Exception:
            if attempt == 0:
                continue
            return None
    return None


def extract_contact(data: dict) -> tuple[str, str]:
    kws = [
        ["marknadschef", "marketing", "cmo"],
        ["kundservice", "customer service", "cx"],
        ["it-chef", "cto", "it-ansvarig"],
    ]
    for g in (data.get("roles") or {}).get("role_groups", []):
        for r in g.get("roles", []):
            rt = (r.get("role") or "").lower()
            for kw in kws:
                if any(k in rt for k in kw):
                    return r.get("name", ""), r.get("role", "")
    return "", ""


def extract_revenue(data: dict) -> tuple[int | None, str]:
    fs = data.get("financial_summary") or {}
    rev = fs.get("revenue")
    if rev:
        return rev, f"{round(rev / 1e6)} MSEK"
    return None, fs.get("estimated_turnover", "") or ""


def extract_email(data: dict) -> str:
    bi = data.get("basic_info") or {}
    if bi.get("email"):
        return bi["email"]
    hp = bi.get("home_page", "") or ""
    if hp:
        try:
            domain = hp.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
            if domain:
                return f"info@{domain}"
        except Exception:
            pass
    return ""


def extract_website(data: dict) -> str:
    bi = data.get("basic_info") or {}
    hp = bi.get("home_page", "") or ""
    if hp and not hp.startswith("http"):
        hp = "https://" + hp
    return hp


def extract_city(data: dict) -> str:
    return ((data.get("addresses") or {}).get("visitor_address") or {}).get("post_place", "") or ""


def extract_phone(data: dict) -> str:
    bi = data.get("basic_info") or {}
    phones = bi.get("phone_numbers") or [""]
    return phones[0] if phones else ""


def extract_industry(data: dict) -> str:
    return (data.get("current_industry") or {}).get("name", "") or ""
