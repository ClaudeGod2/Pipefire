from app.models import Lead


def generate_subject(lead: Lead) -> str:
    company = lead.company_name or "ert bolag"
    return f"Kundkommunikation hos {company} — en tanke"


def generate_body(lead: Lead, sender_name: str) -> str:
    company = lead.company_name or "ert bolag"
    contact = lead.contact_name or ""
    industry = lead.industry or ""
    greeting = f"Hej {contact.split()[0]}," if contact else "Hej,"
    if industry:
        context_line = f"Allt fler företag inom {industry.lower()} investerar i digital kundkommunikation"
    else:
        context_line = "Allt fler svenska företag investerar i digital kundkommunikation"
    return f"""{greeting}

Jag kontaktar er på {company} för att {context_line} — och jag tänkte att det kanske är relevant även för er.

ImBox är en svensk plattform som samlar livechatt, chatbot, ticketing och telefoni i ett enda gränssnitt. Det innebär att era kunder kan nå er på det sätt de föredrar, och att ert team slipper hoppa mellan verktyg.

Tre saker som brukar avgöra:
- Snabb setup — de flesta är live på under en vecka
- Svensk support och hosting (GDPR)
- Mätbar effekt — våra kunder ser i snitt 30% kortare svarstider

Är det värt 15 minuter av er tid att se hur det fungerar?

Vänliga hälsningar,
{sender_name}
ImBox"""


def generate_followup_body(lead: Lead, attempt: int, sender_name: str) -> str:
    company = lead.company_name or "ert bolag"
    contact = lead.contact_name or ""
    greeting = f"Hej {contact.split()[0]}," if contact else "Hej,"
    if attempt == 2:
        return f"""{greeting}

Jag hör av mig igen angående kundkommunikation hos {company}. Jag förstår att det kan vara svårt att hinna med allt — ville bara dubbelkolla om mitt förra mail hamnade rätt.

Kort sammanfattat erbjuder vi på ImBox en svensk plattform för livechatt, chatbot, ticketing och telefoni. Snabb setup, svensk support.

Skulle 15 minuter nästa vecka fungera för en snabb demo?

Vänliga hälsningar,
{sender_name}
ImBox"""
    return f"""{greeting}

Sista försöket — jag vill inte störa, men ville ge er möjligheten innan jag stänger ner kontakten.

Om kundkommunikation är en fråga för {company} längre fram, finns vi på imbox.io. Vi hjälper gärna till med en kostnadsfri analys av er nuvarande setup.

Allt gott,
{sender_name}
ImBox"""
