from sqlalchemy import Column, Integer, String, Text, DateTime, Date, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database import Base


class Campaign(Base):
    __tablename__ = "campaigns"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    sni_prefix = Column(String, nullable=False)
    min_klass = Column(Integer, default=3)
    max_klass = Column(Integer, default=9)
    min_msek = Column(Integer, default=0)
    max_bolag = Column(Integer, default=50)
    status = Column(String, default="pending")
    progress = Column(Integer, default=0)
    error_msg = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    leads = relationship("Lead", back_populates="campaign", cascade="all, delete-orphan")


class Lead(Base):
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"))
    company_name = Column(String)
    org_nr = Column(String)
    revenue = Column(String)
    employees = Column(String)
    industry = Column(String)
    sni = Column(String)
    city = Column(String)
    website = Column(String)
    phone = Column(String)
    email = Column(String)
    mx_status = Column(String)
    mx_detail = Column(String)
    contact_name = Column(String)
    contact_role = Column(String)
    linkedin_url = Column(String)
    call_status = Column(String, default="Ej kontaktad")
    call_date = Column(Date, nullable=True)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    campaign = relationship("Campaign", back_populates="leads")
    drafts = relationship("EmailDraft", back_populates="lead", cascade="all, delete-orphan")


class EmailDraft(Base):
    __tablename__ = "email_drafts"
    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    subject = Column(String)
    body = Column(Text)
    gmail_draft_id = Column(String, nullable=True)
    gmail_thread_id = Column(String, nullable=True)
    status = Column(String, default="pending")
    attempt = Column(Integer, default=1)
    created_at = Column(DateTime, default=func.now())
    sent_at = Column(DateTime, nullable=True)
    replied_at = Column(DateTime, nullable=True)

    lead = relationship("Lead", back_populates="drafts")
