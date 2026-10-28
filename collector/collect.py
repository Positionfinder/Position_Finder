"""Collect PhD and postdoc positions in urban planning, architecture, geography and related fields.

Reads the curated job pages in sources/institutions.yaml, extracts listed items, reads
each item's detail page (HTML or PDF) when robots.txt allows it, classifies it and writes
docs/data/jobs.json for the website. Per-source health goes in the same file.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sys
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

ITEM_HINT = re.compile(
    r"contrat|contract|oferta|offer|position|plaza|pla[çc]a|convocat|call|vacan|investigador|researcher|"
    r"research|predoc|postdoc|posdoc|doctor|ph\.?d|fellowship|beca|ajut|ayuda|job|empleo|treball",
    re.I,
)
SKIP_LINK = re.compile(r"^(home|inicio|inici|login|accede|contact|contacto|contacte|english|español|català|castellano|"
                       r"more|ver más|veure més|read more|leer más|next|siguiente|previous|anterior|\d+|»|«|›|‹|all calls|open|closed|"
                       r"access to jobs|view more|view all|ver todas?|veure-les totes|tots|todas|abiertas?|cerradas?|obertes|tancades)$", re.I)
CONTAINERS = ("li", "tr", "article", "dd", "p", "h2", "h3", "h4")


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


# ---------- listing parsing ----------

def parse_listing(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]):
        tag.decompose()
    main = soup.find("main") or soup.find(id=re.compile(r"^(content|main|contingut|contenido)", re.I)) or soup.body or soup
    items: dict[str, dict] = {}
    for a in main.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        url = urldefrag(urljoin(base_url, href))[0]
        link_text = clean(a.get_text(" "))
        if len(link_text) < 6 or SKIP_LINK.match(link_text):
            continue
        box = a
        for parent in a.parents:
            if parent.name in CONTAINERS:
                box = parent
                break
            if parent is main:
                break
        context = clean(box.get_text(" "))[:1200]
        if len(context) < len(link_text):
            context = link_text
        if not ITEM_HINT.search(context):
            continue
        title = link_text if len(link_text) >= 20 else context[:220]
        prev = items.get(url)
        if prev is None or len(context) > len(prev["context"]):
            items[url] = {"url": url, "title": title, "context": context}
    return list(items.values())


# ---------- detail reading ----------

def read_detail(url: str) -> dict:
    try:
        r = fetch(url)
    except Blocked:
        return {"status": "blocked"}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error": f"{type(e).__name__}"}
    ctype = r.headers.get("Content-Type", "").lower()
    text = ""
    title = None
    if "pdf" in ctype or url.lower().endswith(".pdf"):
        if len(r.content) <= MAX_PDF_BYTES:
            try:
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(r.content))
                text = " ".join((p.extract_text() or "") for p in reader.pages[:6])
            except Exception:  # noqa: BLE001
                text = ""
    elif "html" in ctype:
        soup = BeautifulSoup(r.text, "lxml")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]):
            tag.decompose()
        h1 = soup.find("h1")
        title = clean(h1.get_text(" ")) if h1 else None
        main = soup.find("main") or soup.find(id=re.compile(r"^(content|main|contingut|contenido)", re.I)) or soup.body or soup
        text = main.get_text(" ")
    return {"status": "ok", "title": title, "text": clean(text)[:30000]}


# ---------- per source ----------

def collect_source(inst: dict, page: str, cache: dict) -> tuple[list[dict], dict, list[dict]]:
    status = {"institution": inst["id"], "url": page, "checked": now_iso()}
    try:
        r = fetch(page)
    except Blocked:
        status.update(ok=False, error="disallowed by robots.txt")
        return [], status, []
    except Exception as e:  # noqa: BLE001
        status.update(ok=False, error=f"{type(e).__name__}: {e}"[:200])
        return [], status, []

    raw = parse_listing(r.text, r.url)
    page_host = urlsplit(r.url).netloc
    results, debug = [], []
    details_used = 0
    today = date.today()
    for it in raw:
        quick = f"{it['title']} {it['context']}"
        lvl_quick = classify.level(quick)
        # Only read details for items that look like research positions.
        worth = lvl_quick or re.search(r"investig|research|contrat|contract|proyect|project|oferta|offer|position|pla[cç]a", quick, re.I)
        det = cache.get(it["url"])
        fresh = det and det.get("fetched", "") >= (today - timedelta(days=CACHE_DAYS)).isoformat()
        if worth and not fresh and details_used < MAX_DETAILS_PER_SOURCE:
            details_used += 1
            d = read_detail(it["url"])
            text = d.get("text", "")
            # Cache only the classification, not the page text.
            det = {"status": d["status"], "fetched": today.isoformat(), "title": d.get("title"),
                   "level": classify.level(text), "fields": classify.fields(text[:12000]),
                   "deadline": classify.deadline(text, date.min), "chars": len(text)}
            cache[it["url"]] = det
        det = det or {}
        lvl = classify.level(quick) or det.get("level")
        if lvl and det.get("level") and det["level"] != lvl:
            lvl = "phd+postdoc" if {lvl, det["level"]} == {"phd", "postdoc"} else lvl
        flds = sorted(set(classify.fields(f"{quick} {det.get('title') or ''}")) | set(det.get("fields") or []))
        dl = det.get("deadline") or classify.deadline(quick, date.min)
        if dl and dl < today.isoformat():
            continue  # deadline passed
        programme = classify.is_programme(it["title"]) and not flds
        if programme:
            years = [int(y) for y in re.findall(r"\b(20\d{2})\b", it["title"])]
            if (years and max(years) < today.year) or (not years and not dl):
                continue  # past edition, or an undated programme page with no deadline
        closed = bool(re.search(r"\b(closed|cerrad[ao]|tancad[ao]|finalitzad[ao]|resuelt[ao]|adjudicad[ao]|"
                                r"resoluci[oó] definitiva|desiert[ao])\b", it["context"], re.I))
        title = it["title"]
        if det.get("title") and len(det["title"]) > 15 and len(title) < 30:
            title = det["title"]
        rec = {
            "id": item_id(it["url"]), "title": title[:300], "url": it["url"],
            "institution": inst["name"], "inst_id": inst["id"], "region": inst.get("region"),
            "inst_type": inst.get("type"), "level": lvl, "fields": flds, "deadline": dl,
            "kind": "call" if programme else "position", "source_page": page,
        }
        debug.append({**rec, "context": it["context"][:400], "detail_status": det.get("status"), "closed_hint": closed})
        if closed or not lvl:
            continue
        if rec["kind"] == "position" and not flds:
            continue
        results.append(rec)
    status.update(ok=True, listed=len(raw), kept=len(results), details_fetched=details_used,
                  host=page_host)
    return results, status, debug


def main() -> None:
    insts = yaml.safe_load((ROOT / "sources/institutions.yaml").read_text(encoding="utf-8"))
    only = set(sys.argv[1:])
    jobs_pages = [(i, p) for i in insts for p in i.get("job_pages", []) if not only or i["id"] in only]
    cache = load_json(CACHE, {})
    seen = load_json(SEEN, {})
    today = date.today().isoformat()

    with ThreadPoolExecutor(max_workers=16) as pool:
        outs = list(pool.map(lambda ip: collect_source(ip[0], ip[1], cache), jobs_pages))

    items, sources, debug = {}, [], {}
    for (inst, page), (res, st, dbg) in zip(jobs_pages, outs):
        sources.append(st)
        debug[f"{inst['id']} {page}"] = dbg
        for rec in res:
            items.setdefault(rec["id"], rec)
    for rec in items.values():
        rec["first_seen"] = seen.setdefault(rec["id"], today)
    # Drop cache entries not seen for a long time.
    cutoff = (date.today() - timedelta(days=120)).isoformat()
    cache = {u: d for u, d in cache.items() if d.get("fetched", "") >= cutoff}

    payload = {
        "generated": now_iso(),
        "count": len(items),
        "items": sorted(items.values(), key=lambda r: (r["first_seen"], r["deadline"] or "9999"), reverse=True),
        "sources": sources,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    SEEN.write_text(json.dumps(seen, ensure_ascii=False, indent=0), encoding="utf-8")
    DEBUG.mkdir(exist_ok=True)
    (DEBUG / "items.json").write_text(json.dumps(debug, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = sum(1 for s in sources if s.get("ok"))
    print(f"{len(items)} positions kept; sources ok {ok}/{len(sources)}")


if __name__ == "__main__":
    main()
