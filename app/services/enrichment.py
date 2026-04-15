import re
from urllib.parse import quote_plus

import dns.resolver
import dns.exception


def check_mx(email: str, cache: dict | None = None) -> tuple[str, str]:
    if cache is None:
        cache = {}
    if not email or "@" not in email:
        return "invalid", "Ingen giltig e-post"
    domain = email.split("@")[1].strip().lower()
    is_generic = email.lower().startswith("info@")

    if domain in cache:
        status, detail = cache[domain]
        if status == "ok" and is_generic:
            return "catch_all", f"MX OK men generisk (info@{domain})"
        return status, detail

    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=5)
        servers = sorted(answers, key=lambda r: r.preference)
        detail = str(servers[0].exchange).rstrip(".")
        cache[domain] = ("ok", detail)
        if is_generic:
            return "catch_all", f"MX OK men generisk (info@{domain})"
        return "ok", detail
    except dns.resolver.NXDOMAIN:
        cache[domain] = ("no_mx", f"Domänen {domain} finns inte")
    except dns.resolver.NoAnswer:
        cache[domain] = ("no_mx", f"Ingen MX för {domain}")
    except dns.exception.Timeout:
        cache[domain] = ("error", "DNS timeout")
    except Exception as e:
        cache[domain] = ("error", str(e))
    return cache[domain]


def generate_linkedin_url(name: str, company: str) -> str:
    if not name:
        return ""
    clean = re.sub(
        r'\b(AB|HB|KB|Handelsbolag|Aktiebolag|Kommanditbolag|Inc|Ltd|GmbH|AS|A/S)\b',
        '', company or '', flags=re.IGNORECASE
    ).strip().rstrip(",").strip()
    search_term = f"{name} {clean}".strip()
    return f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(search_term)}"
