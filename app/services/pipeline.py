import time
import traceback
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Campaign, Lead
from app.services import scb, abpi, enrichment


def run_pipeline(campaign_id: int):
    db: Session = SessionLocal()
    try:
        campaign = db.get(Campaign, campaign_id)
        if not campaign:
            return
        campaign.status = "running"
        campaign.progress = 0
        db.commit()

        candidates = scb.get_candidates(campaign.sni_prefix, campaign.min_klass, campaign.max_klass)
        mx_cache: dict = {}
        max_tries = min(len(candidates), max(campaign.max_bolag, 1) * 6)
        found = 0

        for i, k in enumerate(candidates[:max_tries]):
            if found >= campaign.max_bolag:
                break
            data = abpi.fetch_company(k["orgnr"])
            if not data:
                continue

            rev_kr, rev_text = abpi.extract_revenue(data)
            if campaign.min_msek and rev_kr is not None and rev_kr / 1e6 < campaign.min_msek:
                continue

            bi = data.get("basic_info") or {}
            contact_name, contact_role = abpi.extract_contact(data)
            website = abpi.extract_website(data)
            email = abpi.extract_email(data)
            company_name = bi.get("name") or k["namn"]

            mx_status, mx_detail = enrichment.check_mx(email, mx_cache)
            linkedin = enrichment.generate_linkedin_url(contact_name, company_name)

            lead = Lead(
                campaign_id=campaign.id,
                company_name=company_name,
                org_nr=bi.get("organization_number") or k["orgnr"],
                revenue=rev_text,
                employees=str(data.get("number_of_employees") or ""),
                industry=abpi.extract_industry(data),
                sni=k.get("sni", ""),
                city=abpi.extract_city(data),
                website=website,
                phone=abpi.extract_phone(data),
                email=email,
                mx_status=mx_status,
                mx_detail=mx_detail,
                contact_name=contact_name,
                contact_role=contact_role,
                linkedin_url=linkedin,
            )
            db.add(lead)
            found += 1

            progress = min(99, int((found / campaign.max_bolag) * 100))
            campaign.progress = progress
            db.commit()
            time.sleep(settings.abpi_request_delay)

        campaign.progress = 100
        campaign.status = "done"
        db.commit()
    except Exception as e:
        db.rollback()
        campaign = db.get(Campaign, campaign_id)
        if campaign:
            campaign.status = "error"
            campaign.error_msg = f"{e}\n{traceback.format_exc()}"
            db.commit()
    finally:
        db.close()
