import io
import os
import time
import urllib.request
import zipfile
from app.config import settings

SCB_URL = "https://mr2.bolagsverket.se/ftp/scb_bulkfil.zip"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def _load_rader() -> list[str]:
    cache = settings.scb_cache_path
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    if os.path.exists(cache) and (time.time() - os.path.getmtime(cache)) < settings.scb_cache_ttl:
        with open(cache, encoding="utf-8") as f:
            return f.read().splitlines()
    req = urllib.request.Request(SCB_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = r.read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        txts = [f for f in z.namelist() if f.lower().endswith(".txt")]
        innehall = z.read(txts[0] if txts else z.namelist()[0]).decode("latin-1")
    with open(cache, "w", encoding="utf-8") as f:
        f.write(innehall)
    return innehall.splitlines()


def get_candidates(sni_prefix: str, min_klass: int, max_klass: int) -> list[dict]:
    rader = _load_rader()
    prefix = sni_prefix.replace(".", "")
    out = []
    for i, rad in enumerate(rader):
        if i == 0:
            continue
        d = rad.split("\t")
        if len(d) < 7:
            continue
        orgnr = d[0].strip()
        namn = d[1].strip()
        snis = [d[j].strip().replace(".", "") for j in (5, 6, 7) if len(d) > j]
        storlek = d[-3].strip() if len(d) > 10 else ""
        if not any(s.startswith(prefix) for s in snis if s):
            continue
        try:
            k = int(storlek)
            if k < min_klass or k > max_klass:
                continue
        except ValueError:
            pass
        o = orgnr.replace("16", "", 1) if orgnr.startswith("16") else orgnr
        if len(o) == 10:
            o = f"{o[:6]}-{o[6:]}"
        out.append({"orgnr": o, "namn": namn, "sni": snis[0] if snis else ""})
    return out
