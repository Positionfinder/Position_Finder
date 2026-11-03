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
import match as matcher  # noqa: E402
from fetch import Blocked, fetch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs/data/jobs.json"
PROFILES = matcher.load_profiles(ROOT / "sources/profiles.yaml")
SHOW_THRESHOLD = 60  # default "match" filter on the website
REGION_EN = {
    "Andalucía": "Andalusia", "Aragón": "Aragon", "Asturias": "Asturias", "Illes Balears": "Balearic Islands",
    "Canarias": "Canary Islands", "Cantabria": "Cantabria", "Castilla-La Mancha": "Castilla-La Mancha",
    "Castilla y León": "Castile and León", "Catalunya": "Catalonia", "Comunitat Valenciana": "Valencian Community",
    "Extremadura": "Extremadura", "Galicia": "Galicia", "Madrid": "Madrid", "Murcia": "Murcia", "Navarra": "Navarre",
    "País Vasco": "Basque Country", "La Rioja": "La Rioja", "Spain": "Spain",
    "Baden-Württemberg": "Baden-Württemberg", "Bayern": "Bavaria", "Berlin": "Berlin", "Brandenburg": "Brandenburg",
    "Bremen": "Bremen", "Hamburg": "Hamburg", "Hessen": "Hesse", "Mecklenburg-Vorpommern": "Mecklenburg-Western Pomerania",
    "Niedersachsen": "Lower Saxony", "Nordrhein-Westfalen": "North Rhine-Westphalia", "Rheinland-Pfalz": "Rhineland-Palatinate",
    "Saarland": "Saarland", "Sachsen": "Saxony", "Sachsen-Anhalt": "Saxony-Anhalt", "Schleswig-Holstein": "Schleswig-Holstein",
    "Thüringen": "Thuringia",
}
CACHE = ROOT / "data/detail_cache.json"
SEEN = ROOT / "data/seen.json"
DEBUG = ROOT / "debug"
CACHE_DAYS = 14
CACHE_VERSION = 4  # bump when the way offer pages are read changes, so cached pages are re-read
MAX_DETAILS_PER_SOURCE = 80
MAX_PDF_BYTES = 8_000_000
SAVE_DEBUG_HTML = os.environ.get("PF_DEBUG_HTML") == "1"

ITEM_HINT = re.compile(
    r"contrat|contract|oferta|offer|position|plaza|pla[çc]a|convocat|call\b|vacan|investigador|researcher|"
    r"research|predoc|postdoc|posdoc|doctor|ph\.?d|fellowship|beca|ajut|ayuda|job|empleo|treball|"
    r"mitarbeiter|stelle|wissenschaftl|promotion|\bE ?1[3-5]\b|TV-?L|TV[oö]D",
    re.I,
)
OFFER = re.compile(
    r"contrat|contract|oferta|offer|position|plaza|pla[çc]a|convocat|\bcall\b|vacan|investigador|researcher|"
    r"predoc|postdoc|posdoc|ph\.?d|doctoral|doctorand|fellowship|beca|ajut|ayuda|job|selecci|\bR[12]\b|hrs20\d\d|"
    r"mitarbeiter|wissenschaftl|stellenausschreibung|\bE ?1[3-5]\b|TV-?L|TV[oö]D|kennziffer",
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
    r"plazas? de profesor|places? de professor|"
    r"\bW ?[23]\b|w[23]-professur|professur f[uü]r|full professor|associate professor|lehrkraft f[uü]r besondere|"
    r"studentische hilfskraft|studentische[rn]? mitarbeiter|wissenschaftliche hilfskraft|praktikum|internship|"
    r"ausbildung|azubi|werkstudent|lehrkr[aä]ft|lehrer|"
    r"^(ausschreibungen|stellenangebote|stellenausschreibungen|offene stellen|job offers|vacancies|jobs|karriere)\b",
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
# Research posts that don't say whether they are PhD or postdoc level.
PHD_PROGRAMME = re.compile(r"^(FPU|la Caixa INPhINIT|Joan Oró FI|Industrial Doctorates)\b|MSCA.*doctoral", re.I)
RESEARCHER = re.compile(r"investigador(/a|a)?\b(?!\W{0,3}(predoctoral|en formaci|pre-doctoral))|"
                        r"personal investigador(?! en formaci)|\bresearcher\b|research (fellow|associate|scientist)|"
                        r"cient[ií]fic[oa]\b|investigaci[oó]n posdoctoral", re.I)
# German research posts that don't say whether they are PhD or postdoc level.
DE_ASSOCIATE = re.compile(r"(wissenschaftliche|akademische|wiss\.)\S{0,4}\s*(mitarbeiter|besch[aä]ftigte)|"
                          r"research (associate|scientist)|scientist \(|wissenschaftler\S{0,4}in\b", re.I)
TECH_STAFF = re.compile(r"technische[rn]? (angestellte|mitarbeiter|assistent)|sachbearbeit|verwaltungs|sekretariat|"
                        r"systemadministr|it-administr|laborant|personal t[eé]cnico|t[eé]cnic[oa]s? (de apoyo|superior|especialista|de laboratorio)|t[eè]cnic/?a|"
                        r"\bPTA\b|technician|research support|gestor[a]? de|project manager|administrativ|developer|ingeniero de dise|engineer\b", re.I)
# Professional (non-academic) roles, for employers with type: professional.
PRO_ROLE = re.compile(
    r"planner|planificador|planejador|urbanista|urban (planning|designer|development)|"
    r"t[eéè]cnic\S{0,5}\s.{0,40}?"
    r"(urbanis|planeja|planea|planifica|territor|medi ?ambient|medio ?ambient|ambiental|habitatge|vivienda|mobilitat|movilidad|"
    r"projecte|proyecto|cooperaci|sostenib|clima|paisatge|paisaje|participaci|pol[ií]tiques|pol[ií]ticas|estudis|estudios|sig\b|gis\b|cartograf|geogra|"
    r"arquitect|desenvolupament|desarrollo|regeneraci|rehabilitaci|inclusi|comunitari)|"
    r"consultor|consultant|project (manager|officer|coordinator|lead)|programme (manager|officer)|gestor[a]?(/a)? de (proyectos|projectes)|"
    r"cap de projecte|jefe/?a? de proyecto|coordinador|policy (officer|analyst|advisor|adviser)|"
    r"analyst|analista|especialista|specialist|\bexpert|officer|advis[oe]r|asesor|assessor|responsable de|"
    r"arquitect[oa]|architect|ge[oò]graf|ambient[oó]log|\bGIS\b|\bSIG\b|spatial|cart[oò]graf|"
    r"llicenciat|titulad[oa] superior|grup A1|grupo A1|subgrup A1|subgrupo A1",
    re.I,
)
PRO_EXCLUDE = re.compile(
    r"auxiliar|administrativ|conserje|consergeria|operari|pe[oó]n|conductor|ch[oó]fer|mantenimient|manteniment|limpieza|neteja|"
    r"recepci|secretari|developer|desarrollador|programador|software|devops|sysadmin|full ?stack|front ?end|back ?end|"
    r"helpdesk|soporte (t[eé]cnico|inform)|it support|becari|\bbeca\b|pr[aà]ctiques|pr[aá]cticas|intern(ship)?\b|trainee|"
    r"electricista|fontaner|delineant|laborant|t[eè]cnic[oa]? (auxiliar|de laboratori|de manteniment|de mantenimiento|inform)|"
    r"comercial|ventas|sales|account manager|contabl|comptabl|n[oó]min|payroll|abogad|advocat|jur[ií]dic|"
    r"socorrista|vigilant|agent de|agente de|polic[ií]a|guardia urbana|bomber|bombero|educador|monitor|cuidador|enfermer|infermer|m[eé]dic",
    re.I,
)

# Documents that are only published once applications have closed (lists, results, awards).
RESULT_DOC = re.compile(
    r"llista (provisional|definitiva)|lista (provisional|definitiva)|listado (provisional|definitivo)|"
    r"resoluci[oó]n? (provisional|definitiva|de adjudicaci|final)|resoluci[oó] (provisional|definitiva|final)|"
    r"admesos|admitidos|admitted|exclosos|excluidos|adjudicaci|proposta de contractaci|propuesta de contrataci|"
    r"\bacta\b|resultad|resultats|results|seleccionad|seleccionat|selected candidate|persona candidata proposada",
    re.I,
)
BARE_RESOLUTION = re.compile(r"^resoluci[oó]n?\.?$", re.I)
CALL_DOC = re.compile(r"^(convocat[oò]ria|convocatoria|bases|call)\b", re.I)
# Row-level status words.
CLOSED_STATUS = re.compile(
    r"\b(cerrad[ao]s?|tancad[ao]s?|tancat|closed|resuelt[ao]s?|resolt[ao]s?|resolved|en evaluaci[oó]n|en avaluaci[oó]|"
    r"under (evaluation|review)|finalitzad[ao]|finalizad[ao]|adjudicad[ao]|desiert[ao]|deserta|expired|"
    r"fuera de plazo|fora de termini|plazo (cerrado|finalizado)|termini (tancat|finalitzat)|no longer accepting)\b",
    re.I,
)
OPEN_STATUS = re.compile(
    r"\b(abiert[ao]|obert[ao]?|open( call| position)?|en plazo|en termini|plazo abierto|termini obert|"
    r"accepting applications|pr[oó]xima publicaci[oó]n|upcoming)\b",
    re.I,
)
MAX_ROW_CHARS = 1500
APPLY_LINK = re.compile(r"e-tauler|^sol·licitud$|^solicitud$|form submission|^formulari|^formulario|^apply( now| here)?$|"
                        r"^inscripci[oó]n?$|^inscriure", re.I)
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

def _link_url(a, base_url: str) -> str:
    return urldefrag(urljoin(base_url, a["href"].strip()))[0]


def row_of(a, main, base_url: str):
    """The listing row that holds this link.

    Climb from the link while the ancestor still describes only this offer. Stop before an
    ancestor that also holds another row: a link with the same text pointing elsewhere (the next
    row's "Convocatòria"), or a link that looks like another offer's title.
    """
    url = _link_url(a, base_url)
    text = clean(a.get_text(" "))
    box = a
    for depth, parent in enumerate(a.parents):
        if parent is main or depth > 9 or parent.name in ("body", "html"):
            break
        if len(clean(parent.get_text(" "))) > MAX_ROW_CHARS:
            break
        other_row = False
        for x in parent.find_all("a", href=True):
            if x is a or x["href"].startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            xu, xt = _link_url(x, base_url), clean(x.get_text(" "))
            if xu == url:
                continue
            if xt and xt.lower() == text.lower():
                other_row = True
                break
            if len(xt) >= 40 and OFFER.search(xt) and not RESULT_DOC.search(xt) \
                    and not re.search(r"bases|pdf|formulari|sol·licitud|solicitud|annex|anexo|e-tauler", xt, re.I):
                other_row = True
                break
        if other_row:
            break
        box = parent
    return box


def row_flags(box, a) -> dict:
    """Result documents linked from the same row (so applications are over)."""
    texts = [clean(x.get_text(" ")) for x in box.find_all("a", href=True) if x is not a] if box is not a else []
    has_call_doc = any(CALL_DOC.match(t) for t in texts) or bool(CALL_DOC.match(clean(a.get_text(" "))))
    results = [t for t in texts if RESULT_DOC.search(t) or (has_call_doc and BARE_RESOLUTION.match(t))]
    return {"result_links": results[:5]}


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
        url = _link_url(a, base_url)
        link_text = clean(a.get_text(" "))
        if len(link_text) < 4 or SKIP_LINK.match(link_text) or RESULT_DOC.search(link_text) \
                or BARE_RESOLUTION.match(link_text) or APPLY_LINK.search(link_text):
            continue
        box = row_of(a, main, base_url)
        context = clean(box.get_text(" "))[:MAX_ROW_CHARS]
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
        flags = row_flags(box, a)
        prev = items.get(url)
        if prev is None or len(context) > len(prev["context"]):
            items[url] = {"url": url, "title": title, "context": context,
                          "weak_title": generic and len(context) > 400, **flags}
    # One entry per row: several links in the same row (call PDF, notice board) describe one offer.
    seen_rows, out = set(), []
    for it in items.values():
        key = (it["title"], it["context"])
        if key in seen_rows:
            continue
        seen_rows.add(key)
        out.append(it)
    return out


# ---------- detail reading ----------

CALL_PDF = re.compile(r"\bbases\b|convocat|resoluci|ausschreibung|stellenausschreibung|job description|"
                      r"call (text|document)|anuncio|anunci\b|\bpdf\b", re.I)


NOT_CALL_DOC = re.compile(r"calendari|formulari|sol·licitud|solicitud|application form|antrag|ptgas|\bpas\b|"
                          r"privacy|privacidad|protecci[oó]n de datos|datenschutz", re.I)


def pdf_segments(url: str) -> list[str]:
    try:
        r = fetch(url)
    except Exception:  # noqa: BLE001  (blocked or unreachable)
        return []
    if not r.content[:5].startswith(b"%PDF"):
        return []
    if len(r.content) > MAX_PDF_BYTES:
        return []
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(r.content))
        text = "\n".join((p.extract_text() or "") for p in reader.pages[:6])
    except Exception:  # noqa: BLE001
        return []
    return [clean(x) for x in text.split("\n") if clean(x)]


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
                title = pdf_title(segments)
            except Exception:  # noqa: BLE001
                pass
    elif "html" in ctype:
        soup = BeautifulSoup(r.text, "lxml")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]):
            tag.decompose()
        h1 = soup.find("h1")
        title = clean(h1.get_text(" ")) if h1 else None
        main = main_element(soup)
        segments = [clean(x) for x in main.get_text("\n").split("\n") if clean(x)]
        if sum(len(x) for x in segments) < 2500:
            # Short offer page that links to the call document (bases / Ausschreibung): read that too.
            docs = [a for a in main.find_all("a", href=True)
                    if (CALL_PDF.search(clean(a.get_text(" "))) or a["href"].lower().endswith(".pdf"))
                    and not NOT_CALL_DOC.search(clean(a.get_text(" ")))]
            docs.sort(key=lambda a: (not re.search(r"\bbases\b|ausschreibung|job description", a.get_text(" "), re.I),
                                     not re.search(r"convocat|resoluci|call", a.get_text(" "), re.I)))
            for a in docs[:2]:
                segments += pdf_segments(urldefrag(urljoin(r.url, a["href"]))[0])
    return {"status": "ok", "title": title, "segments": segments[:3000], "pdf": is_pdf}


def max_year(text: str) -> int | None:
    years = [int(y) for y in re.findall(r"\b(20[1-3]\d)\b", text) if int(y) <= date.today().year + 2]
    return max(years) if years else None


PDF_HEAD = re.compile(r"^(resoluci[oó]n?|convocat[oò]ria|anuncio|anunci|bases|oferta|offer|call for|job offer|position)", re.I)


def pdf_title(segments: list[str]) -> str | None:
    """Heading of a call PDF: the first line that starts like one, plus the lines that continue it."""
    for i, seg in enumerate(segments[:60]):
        if PDF_HEAD.match(seg) and len(seg) >= 12:
            title = seg
            for nxt in segments[i + 1:i + 4]:
                if len(title) >= 160:
                    break
                title += " " + nxt
            return clean(title)[:220]
    return next((x for x in segments[:15] if len(x) >= 25 and OFFER.search(x)), None)


def classify_text(text: str) -> dict:
    return {"level": classify.level(text), "fields": classify.fields(text[:15000]),
            "deadline": classify.deadline(text, date.min), "max_year": max_year(text),
            "topics": matcher.topic_counts(text),
            "deadline_est": classify.relative_deadline(text), "page_status": classify.page_status(text)}


# ---------- per source ----------

def collect_source(inst: dict, page: str, cache: dict, boiler: dict) -> tuple[list[dict], dict, list[dict]]:
    status = {"institution": inst["id"], "url": page, "checked": now_iso()}
    pro = inst.get("type") == "professional"
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
        is_offer = OFFER.search(quick) or (pro and PRO_ROLE.search(it["title"]))
        if NOT_OFFER.search(it["title"]) or not is_offer:
            it["skip"] = "not an offer"
            continue
        row_dl = classify.deadline(quick, date.min)
        if (row_dl and row_dl < today.isoformat()) or CLOSED_STATUS.search(quick) or it.get("result_links"):
            continue  # already over according to the listing row: no need to open it
        det = cache.get(it["url"])
        if not (det and det.get("fetched", "") >= cutoff and det.get("v") == CACHE_VERSION):
            to_read.append(it)
    # Big portals list hundreds of jobs: read the most promising ones first (field words, then
    # postdoc/PhD words in the title); the rest are read on later days (pages are cached).
    to_read.sort(key=lambda it: (not classify.fields(f"{it['title']} {it['context']}"),
                                 not classify.level(f"{it['title']} {it['context']}")))
    to_read = to_read[:MAX_DETAILS_PER_SOURCE]
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
        cache[url] = {"v": CACHE_VERSION, "status": d["status"], "fetched": today.isoformat(), "title": d.get("title"),
                      "chars": len(text), **classify_text(text)}

    # 4) build records
    results, debug = [], []
    for it in raw:
        if it.get("skip"):
            debug.append({"title": it["title"][:200], "url": it["url"], "skip": it["skip"]})
            continue
        quick = f"{it['title']} {it['context']}"
        det = cache.get(it["url"], {})
        # The title is the most reliable signal for the level; the offer text often mentions both
        # ("PhD position ... after the doctorate you can ...").
        lvl_title = classify.level(it["title"]) or classify.level(it["context"])
        lvl = lvl_title or det.get("level")
        if lvl == "phd+postdoc":
            # Both levels mentioned: it is a postdoc offer unless the title itself says PhD.
            lvl = "phd" if classify.level(it["title"]) == "phd" else "postdoc"
        if not lvl and (DE_ASSOCIATE.search(it["title"]) or RESEARCHER.search(it["title"])):
            lvl = "research"  # shown as "Researcher (level not stated)"
        pro_role = pro and not lvl and bool(PRO_ROLE.search(it["title"]) or PRO_ROLE.search(det.get("title") or ""))
        if pro_role:
            lvl = "professional"
        title_flds = classify.fields(f"{quick} {det.get('title') or ''}")
        flds = sorted(set(title_flds) | set(det.get("fields") or []))
        dl = classify.deadline(quick, date.min) or det.get("deadline")
        if dl and dl > (today + timedelta(days=400)).isoformat():
            dl = None  # a "deadline" years away is a contract end date or similar, not the closing date
        title = it["title"]
        if det.get("title") and len(det["title"]) > 15 and (len(title) < 30 or GENERIC_LINK.match(title) or it.get("weak_title")):
            title = det["title"]
        elif it.get("weak_title"):
            debug.append({"title": title[:200], "url": it["url"], "skip": "link inside a long list, no own title"})
            continue
        prog = classify.programme_key(f"{title} {it['context'][:200]}")
        # A national/regional programme named in the title is a call, whatever fields its page mentions.
        is_call = bool(prog and (classify.programme_key(title) or not classify.relevant(flds)))
        estimated = False
        if is_call and not dl:
            future = [d for _, d in classify._dates(it["context"]) if d >= today]
            dl = max(future).isoformat() if future else None
        row_status = f"{it['title']} {it['context']}"
        strength = matcher.topic_strength(f"{title} {it['context']} {det.get('title') or ''}", det.get("topics") or {})
        matches = {pr["id"]: matcher.score(pr, strength) for pr in PROFILES}
        best = max(pct for pct, _ in matches.values())
        is_open = bool(OPEN_STATUS.search(row_status)) or det.get("page_status") == "open"
        if not dl and OPEN_STATUS.search(row_status):
            # Rows like "Oberta 13-11-2026": in an open row, the future date is the closing date.
            future = [d for _, d in classify._dates(it["context"]) if d >= today]
            dl = max(future).isoformat() if future else None
        if not dl and det.get("deadline_est"):
            dl, estimated = det["deadline_est"], True
        reason = None
        if dl and dl < today.isoformat():
            reason = "deadline passed" + (" (estimated)" if estimated else "")
        elif CLOSED_STATUS.search(row_status):
            reason = "marked closed / resolved / under evaluation"
        elif it.get("result_links"):
            reason = "results already published: " + "; ".join(it["result_links"])[:120]
        elif det.get("page_status") == "closed":
            reason = "offer page says closed / resolved"
        elif is_call and re.search(r"20\d\d$", prog) and int(prog[-4:]) < today.year:
            reason = "past edition of a programme call"
        elif is_call and PHD_PROGRAMME.search(prog):
            reason = "PhD programme call (excluded)"
        elif not lvl:
            reason = "not a postdoc / researcher position"
        elif lvl not in ("postdoc", "research", "professional"):
            reason = "PhD position (excluded)"
        elif lvl == "professional" and PRO_EXCLUDE.search(title):
            reason = "technical / support / non-planning job"
        elif lvl != "professional" and TECH_STAFF.search(title) and not classify.level(title):
            reason = "technical / support staff"
        elif not prog and not lvl_title and not pro_role and len(title) < 45 and not DE_ASSOCIATE.search(title):
            reason = "vague title (looks like a menu or section link)"
        elif not dl and not is_open and not (pro_role and inst.get("open_list")):
            reason = "no deadline and not marked open (can't confirm it is still open)"
        elif not dl and max([y for y in (max_year(f"{title} {it['context']}"), det.get("max_year")) if y] or [today.year]) < today.year:
            reason = "old (latest year mentioned is in the past)"
        elif not prog and not classify.relevant(flds) and best < 40:
            reason = "field not relevant"
        elif not prog and not classify.relevant(title_flds) and len(det.get("fields") or []) < 2 and best < SHOW_THRESHOLD:
            reason = "field only mentioned in passing in the offer text"
        if is_call:
            title = f"{prog} call"
        rec = {
            "id": item_id(it["url"]), "title": title[:300], "url": it["url"],
            "institution": inst.get("name_en") or inst["name"], "inst_id": inst["id"],
            "region": REGION_EN.get(inst.get("region"), inst.get("region")), "city": inst.get("city"),
            "country": inst.get("country", "ES"),
            "match": None if is_call else {pid: pct for pid, (pct, _) in matches.items()},
            "topics": [] if is_call else matcher.main_topics(strength),
            "inst_type": inst.get("type"), "sector": "professional" if lvl == "professional" else "academic", "level": lvl, "fields": flds, "deadline": dl,
            "deadline_estimated": estimated,
            "kind": "call" if is_call else "position",
            "programme": prog if is_call else None, "source_page": page,
        }
        debug.append({**rec, "reason": reason, "context": it["context"][:400], "detail": det.get("status"),
                      "result_links": it.get("result_links"), "page_status": det.get("page_status")})
        if not reason:
            results.append(rec)

    status.update(ok=True, listed=len(raw), kept=len(results), details_fetched=len(fetched))
    if SAVE_DEBUG_HTML and (not raw or not results):
        (DEBUG / "html").mkdir(parents=True, exist_ok=True)
        (DEBUG / "html" / f"{inst['id']}-{item_id(page)}.html").write_text(r.text, encoding="utf-8")
    return results, status, debug


OFFICIAL_HOSTS = re.compile(r"(^|\.)(aei\.gob\.es|ciencia\.gob\.es|agaur\.gencat\.cat|fundacionlacaixa\.org|"
                           r"ec\.europa\.eu|europa\.eu|universidades\.gob\.es)$")


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
            if rec["institution"] not in c["listed_by"]:
                c["listed_by"].append(rec["institution"])
            if rec["deadline"]:
                c["_deadlines"].append(rec["deadline"])
            c["_urls"].append(rec["url"])
            continue
        rec = {**rec, "listed_by": [rec["institution"]], "_deadlines": [rec["deadline"]] if rec["deadline"] else [],
               "_urls": [rec["url"]]}
        calls[key] = rec
        out.append(rec)
    for c in calls.values():
        dls = c.pop("_deadlines")
        if dls:
            # Universities sometimes post their own earlier internal deadline; the date most of them
            # give is the official one. Ties go to the later date.
            c["deadline"] = max(set(dls), key=lambda d: (dls.count(d), d))
        if c.get("_urls"):
            official = [u for u in c["_urls"] if OFFICIAL_HOSTS.search(urlsplit(u).netloc)]
            if official:
                c["url"] = official[0]
        c.pop("_urls", None)
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
        "profiles": [{"id": pr["id"], "label": pr["label"], "short": pr["short"]} for pr in PROFILES],
        "threshold": SHOW_THRESHOLD,
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
