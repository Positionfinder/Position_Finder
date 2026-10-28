"""Collect PhD and postdoc positions in urban planning, architecture, geography and related fields.

Reads the curated job pages in sources/institutions.yaml, extracts listed items, reads
each item's detail page (HTML or PDF) when robots.txt allows it, strips text that repeats
across a site (menus, footers), classifies the rest and writes docs/data/jobs.json.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit

import yaml
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
import classify  # noqa: E402
from fetch import Blocked, fetch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs/data/jobs.json"
CACHE = ROOT / "data/detail_cache.json"
SEEN = ROOT / "data/seen.json"
DEBUG = ROOT / "debug"
CACHE_DAYS = 14
MAX_DETAILS_PER_SOURCE = 60
MAX_PDF_BYTES = 8_000_000
SAVE_DEBUG_HTML = os.environ.get("PF_DEBUG_HTML") == "1"

ITEM_HINT = re.compile(
    r"contrat|contract|oferta|offer|position|plaza|pla[çc]a|convocat|call\b|vacan|investigador|researcher|"
    r"research|predoc|postdoc|posdoc|doctor|ph\.?d|fellowship|beca|ajut|ayuda|job|empleo|treball",
    re.I,
)
OFFER = re.compile(
    r"contrat|contract|oferta|offer|position|plaza|pla[çc]a|convocat|\bcall\b|vacan|investigador|researcher|"
    r"predoc|postdoc|posdoc|ph\.?d|doctoral|doctorand|fellowship|beca|ajut|ayuda|job|selecci|\bR[12]\b|hrs20\d\d",
    re.I,
)
NOT_OFFER = re.compile(
    r"resoluci[oó]n? (provisional|definitiva|de adjudicaci|parcial)|resoluci[oó] (provisional|definitiva)|"
    r"\blista(do)?s? (provisional|definitiv|de admitid|de excluid)|llista (provisional|definitiva)|admitidos|exclosos|excluidos|"
    r"correcci[oó]n? (de errores|definitiva)|nombramiento|nomenament|comisi[oó]n (de evaluaci|evaluadora|juzgadora)|"
    r"defensa (de la )?tesis|thesis defen[cs]e|lectura de tesis|gu[ií]a (del|de|para)|consultas|certificad|"
    r"equivalen|preguntas frecuentes|\bfaq\b|normativa|reglamento|instrucciones|plantilla|manual|"
    r"acta |actas |memoria anual|news|noticia|evento|jornada|seminario|webinar|premio|award|"
    r"tramos de investigaci|sexenios|estabilizaci[oó]n|sorteo|committee selection|selection draws|tribunal|"
    r"cuerpos docentes|profesor(ado)? (titular|catedr|ayudante|asociado|agregat|lector|visitante)|catedr[aá]tic|"
    r"plazas? de profesor|places? de professor",
    re.I,
)
GENERIC_LINK = re.compile(
    r"^(download|descarga|descargar|descàrrega|more info|more information|más información|més informació|ver|veure|"
    r"details?|detalles?|apply|solicitar|sol·licitar|pdf|link|enlace|enllaç|aquí|here|click here|continúa leyendo|"
    r"leer más|read more|ver convocatoria|ver convocatorias|veure la convocatòria|job description|"
    r"download job description)\b"
    r"|^(convocat[oò]ria|convocatoria|bases|oferta|offer|anuncio|anunci|pdf|document|documento|enlace)\.?$",
    re.I,
)
SKIP_LINK = re.compile(r"^(home|inicio|inici|login|accede|contact|contacto|contacte|english|español|català|castellano|"
                       r"more|ver más|veure més|next|siguiente|previous|anterior|\d+|»|«|›|‹|all calls|open|closed|"
                       r"access to jobs|view more|view all|ver todas?|veure-les totes|tots|todas|abiertas?|cerradas?|obertes|tancades)$",
                       re.I)
TECH_STAFF = re.compile(r"personal t[eé]cnico|t[eé]cnic[oa]s? (de apoyo|superior|especialista|de laboratorio)|t[eè]cnic/?a|"
                        r"\bPTA\b|technician|research support|gestor[a]? de|project manager|administrativ|developer|ingeniero de dise|engineer\b", re.I)
ROW_CONTAINERS = ("tr", "li", "article", "dd")
TEXT_CONTAINERS = ("p", "h2", "h3", "h4", "h5", "td", "div")
MAIN_ID = re.compile(r"^(content|main|contingut|contenido|region-content|main-content)", re.I)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def clean(text: str) -> str:
    return " ".join(text.split())


def item_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:12]


def seg_hash(s: str) -> str:
    return hashlib.sha1(s.lower().encode()).hexdigest()[:10]


def main_element(soup: BeautifulSoup):
    """The page's main content: the candidate container holding the most links, else <body>."""
    cands = soup.find_all("main") + soup.find_all(id=MAIN_ID) + soup.find_all(attrs={"role": "main"})
    best = max(cands, key=lambda c: len(c.find_all("a")), default=None)
    if best is None or len(best.find_all("a")) < 3:
        return soup.body or soup
    return best


# ---------- listing parsing ----------

def parse_listing(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]):
        tag.decompose()
    main = main_element(soup)
    items: dict[str, dict] = {}
    for a in main.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        url = urldefrag(urljoin(base_url, href))[0]
        link_text = clean(a.get_text(" "))
        if len(link_text) < 4 or SKIP_LINK.match(link_text):
            continue
        box = None
        for depth, parent in enumerate(a.parents):
            if parent is main or depth > 7:
                break
            if parent.name in ROW_CONTAINERS:
                box = parent
                break
        if box is None:
            for parent in a.parents:
                if parent is main:
                    break
                if parent.name in TEXT_CONTAINERS and len(clean(parent.get_text(" "))) > len(link_text) + 10:
                    box = parent
                    break
        box = box or a
        context = clean(box.get_text(" "))[:1200]
        if len(context) < len(link_text):
            context = link_text
        if not ITEM_HINT.search(context):
            continue
        generic = bool(GENERIC_LINK.match(link_text)) or len(link_text) < 20
        if generic:
            rest = clean(context.replace(link_text, " "))
            title = rest[:220] if len(rest) >= 15 else link_text
        else:
            title = link_text
        prev = items.get(url)
        if prev is None or len(context) > len(prev["context"]):
            items[url] = {"url": url, "title": title, "context": context,
                          "weak_title": generic and len(context) > 250}
    return list(items.values())


# ---------- detail reading ----------

def read_detail(url: str) -> dict:
    try:
        r = fetch(url)
    except Blocked:
        return {"status": "blocked", "segments": []}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error": type(e).__name__, "segments": []}
    ctype = r.headers.get("Content-Type", "").lower()
    title, segments, is_pdf = None, [], False
    if "pdf" in ctype or url.lower().endswith(".pdf"):
        is_pdf = True
        if len(r.content) <= MAX_PDF_BYTES:
            try:
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(r.content))
                text = "\n".join((p.extract_text() or "") for p in reader.pages[:6])
                segments = [clean(x) for x in text.split("\n") if clean(x)]
                title = next((x for x in segments[:15] if len(x) >= 25 and OFFER.search(x)), None)
            except Exception:  # noqa: BLE001
                pass
    elif "html" in ctype:
        soup = BeautifulSoup(r.text, "lxml")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]):
            tag.decompose()
        h1 = soup.find("h1")
        title = clean(h1.get_text(" ")) if h1 else None
        segments = [clean(x) for x in main_element(soup).get_text("\n").split("\n") if clean(x)]
    return {"status": "ok", "title": title, "segments": segments[:3000], "pdf": is_pdf}


def max_year(text: str) -> int | None:
    years = [int(y) for y in re.findall(r"\b(20[1-3]\d)\b", text) if int(y) <= date.today().year + 2]
    return max(years) if years else None


def classify_text(text: str) -> dict:
    return {"level": classify.level(text), "fields": classify.fields(text[:15000]),
            "deadline": classify.deadline(text, date.min), "max_year": max_year(text)}


# ---------- per source ----------

def collect_source(inst: dict, page: str, cache: dict, boiler: dict) -> tuple[list[dict], dict, list[dict]]:
    status = {"institution": inst["id"], "url": page, "checked": now_iso()}
    try:
        r = fetch(page)
    except Blocked:
        status.update(ok=False, error="disallowed by robots.txt")
        return [], status, []
    except Exception as e:  # noqa: BLE001
        status.update(ok=False, error=f"{type(e).__name__}: {e}"[:200])
        return [], status, []

    raw = [it for it in parse_listing(r.text, r.url)
           if it["url"].rstrip("/") not in (page.rstrip("/"), r.url.rstrip("/"))
           and not (r.url.startswith(it["url"].rstrip("/") + "/") and len(it["url"]) < len(r.url))]
    today = date.today()
    cutoff = (today - timedelta(days=CACHE_DAYS)).isoformat()

    # 1) fetch details that are worth reading and not cached recently
    to_read = []
    for it in raw:
        quick = f"{it['title']} {it['context']}"
        if NOT_OFFER.search(it["title"]) or not OFFER.search(quick):
            it["skip"] = "not an offer"
            continue
        det = cache.get(it["url"])
        if not (det and det.get("fetched", "") >= cutoff) and len(to_read) < MAX_DETAILS_PER_SOURCE:
            to_read.append(it)
    fetched = {it["url"]: read_detail(it["url"]) for it in to_read}

    # 2) learn site boilerplate: lines repeated on many detail pages of the same host
    by_host: dict[str, list[set[str]]] = {}
    for url, d in fetched.items():
        if d.get("segments") and not d.get("pdf"):
            by_host.setdefault(urlsplit(url).netloc, []).append({seg_hash(s) for s in d["segments"] if len(s) >= 3})
    for host, pages in by_host.items():
        if len(pages) >= 3:
            counts = Counter(h for p in pages for h in p)
            common = {h for h, c in counts.items() if c >= max(3, 0.3 * len(pages))}
            boiler[host] = sorted(set(boiler.get(host, [])) | common)[-4000:]

    # 3) classify freshly fetched pages without boilerplate and cache the result
    for url, d in fetched.items():
        common = set(boiler.get(urlsplit(url).netloc, []))
        text = " ".join(s for s in d.get("segments", []) if seg_hash(s) not in common)
        cache[url] = {"status": d["status"], "fetched": today.isoformat(), "title": d.get("title"),
                      "chars": len(text), **classify_text(text)}

    # 4) build records
    results, debug = [], []
    for it in raw:
        if it.get("skip"):
            debug.append({"title": it["title"][:200], "url": it["url"], "skip": it["skip"]})
            continue
        quick = f"{it['title']} {it['context']}"
        det = cache.get(it["url"], {})
        lvl_title = classify.level(it["title"]) or classify.level(it["context"])
        lvl = classify.level(it["title"]) or classify.level(it["context"]) or det.get("level")
        flds = sorted(set(classify.fields(f"{quick} {det.get('title') or ''}")) | set(det.get("fields") or []))
        dl = classify.deadline(quick, date.min) or det.get("deadline")
        title = it["title"]
        if det.get("title") and len(det["title"]) > 15 and (len(title) < 30 or GENERIC_LINK.match(title) or it.get("weak_title")):
            title = det["title"]
        prog = classify.programme_key(f"{title} {it['context'][:200]}")
        reason = None
        if dl and dl < today.isoformat():
            reason = "deadline passed"
        elif re.search(r"\b(closed|cerrad[ao]|tancad[ao]|finalitzad[ao]|resuelt[ao]|adjudicad[ao]|desiert[ao]|expired)\b",
                       it["context"], re.I):
            reason = "marked closed"
        elif not lvl:
            reason = "not PhD/postdoc"
        elif TECH_STAFF.search(title) and not classify.level(title):
            reason = "technical / support staff"
        elif not prog and not lvl_title and len(title) < 45:
            reason = "vague title (looks like a menu or section link)"
        elif not dl and max([y for y in (max_year(f"{title} {it['context']}"), det.get("max_year")) if y] or [today.year]) < today.year:
            reason = "old (no deadline, latest year mentioned is in the past)"
        elif prog and not classify.relevant(flds):
            years = [int(y) for y in re.findall(r"\b(20\d{2})\b", f"{title} {it['context'][:300]}")]
            if (years and max(years) < today.year) or (not years and not dl):
                reason = "old or undated programme call"
        elif not prog and not classify.relevant(flds):
            reason = "field not relevant"
        is_call = bool(prog and not classify.relevant(flds))
        if is_call and not dl:
            future = [d for _, d in classify._dates(it["context"]) if d >= today]
            dl = max(future).isoformat() if future else None
        if is_call:
            title = f"{prog} call"
        rec = {
            "id": item_id(it["url"]), "title": title[:300], "url": it["url"],
            "institution": inst["name"], "inst_id": inst["id"], "region": inst.get("region"),
            "inst_type": inst.get("type"), "level": lvl, "fields": flds, "deadline": dl,
            "kind": "call" if (prog and not classify.relevant(flds)) else "position",
            "programme": prog if (prog and not classify.relevant(flds)) else None, "source_page": page,
        }
        debug.append({**rec, "reason": reason, "context": it["context"][:300], "detail": det.get("status")})
        if not reason:
            results.append(rec)

    status.update(ok=True, listed=len(raw), kept=len(results), details_fetched=len(fetched))
    if SAVE_DEBUG_HTML and (not raw or not results):
        (DEBUG / "html").mkdir(parents=True, exist_ok=True)
        (DEBUG / "html" / f"{inst['id']}-{item_id(page)}.html").write_text(r.text, encoding="utf-8")
    return results, status, debug


def merge_calls(items: list[dict]) -> list[dict]:
    """The same national call (e.g. Juan de la Cierva 2026) is listed by many universities: keep one."""
    out, calls = [], {}
    for rec in items:
        if rec["kind"] != "call" or not rec.get("programme"):
            out.append(rec)
            continue
        key = rec["programme"]
        if not re.search(r"20\d\d$", key) and rec.get("deadline"):
            key = f"{key} {rec['deadline'][:4]}"
            rec = {**rec, "programme": key, "title": f"{key} call"}
        if key in calls:
            c = calls[key]
            c["listed_by"].append(rec["institution"])
            if not c["deadline"] and rec["deadline"]:
                c["deadline"] = rec["deadline"]
            continue
        rec = {**rec, "listed_by": [rec["institution"]]}
        calls[key] = rec
        out.append(rec)
    for c in calls.values():
        if len(c["listed_by"]) > 1:
            c["institution"] = f"Listed by {len(c['listed_by'])} institutions"
            c["region"] = None
    return out


def main() -> None:
    insts = yaml.safe_load((ROOT / "sources/institutions.yaml").read_text(encoding="utf-8"))
    only = set(sys.argv[1:])
    pages = [(i, p) for i in insts for p in i.get("job_pages", []) if not only or i["id"] in only]
    cache = load_json(CACHE, {})
    boiler = cache.pop("__boilerplate__", {})
    seen = load_json(SEEN, {})
    today = date.today().isoformat()
    DEBUG.mkdir(exist_ok=True)

    with ThreadPoolExecutor(max_workers=16) as pool:
        outs = list(pool.map(lambda ip: collect_source(ip[0], ip[1], cache, boiler), pages))

    found, sources, debug = {}, [], {}
    for (inst, page), (res, st, dbg) in zip(pages, outs):
        sources.append(st)
        debug[f"{inst['id']} {page}"] = dbg
        for rec in res:
            found.setdefault(rec["id"], rec)
    items = merge_calls(list(found.values()))
    for rec in items:
        rec["first_seen"] = seen.setdefault(rec["id"], today)

    old = (date.today() - timedelta(days=120)).isoformat()
    cache = {u: d for u, d in cache.items() if d.get("fetched", "") >= old}
    cache["__boilerplate__"] = boiler

    payload = {
        "generated": now_iso(),
        "count": len(items),
        "items": sorted(items, key=lambda r: (r["first_seen"], r["deadline"] or "9999"), reverse=True),
        "sources": sources,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    SEEN.write_text(json.dumps(seen, ensure_ascii=False, indent=0), encoding="utf-8")
    (DEBUG / "items.json").write_text(json.dumps(debug, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = sum(1 for s in sources if s.get("ok"))
    print(f"{len(items)} positions kept; sources ok {ok}/{len(sources)}")


if __name__ == "__main__":
    main()
