"""EURAXESS and Faculty Radar -> data/external_candidates.json.

Two public sites that the manual picks task used to read in a browser. This script reads them
(politely, robots.txt respected, via fetch.py), scores each offer with the same method as the
website (match.py + sources/profiles.yaml) and writes the offers that reach 50 % for profile A or B
(plus Faculty Radar assistant-professor posts in core geography / urban-planning areas).

Output items use the docs/data/linkedin.json item format, so the picks task only has to add the
new ones. Items already on the site (docs/data/jobs.json) or in docs/data/linkedin.json are skipped.

    python collector/external.py [--days 10]
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
import match as matcher  # noqa: E402
from fetch import Blocked, fetch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/external_candidates.json"
SEEN = ROOT / "data/external_seen.json"
PROFILES = matcher.load_profiles(ROOT / "sources/profiles.yaml")
TODAY = date.today()
MIN_MATCH = 50
MAX_TEXT = 25000

COUNTRY = {"788": ("ES", "Spain"), "794": ("DE", "Germany")}
EUR_KEYWORDS = ["urban planning", "spatial planning", "geography", "landscape", "GIS", "flood", "ecosystem services",
                "climate adaptation", "housing", "participatory", "urbanismo", "territorio", "Stadtplanung",
                "Raumplanung", "Geographie"]
EUR_FIELDS = "&f%5B1%5D=job_research_field%3A210&f%5B2%5D=job_research_field%3A195&f%5B3%5D=job_research_field%3A21"
MAX_PAGES = 12
ERRORS: list[str] = []


def note_error(msg: str) -> None:
    print(msg)
    if len(ERRORS) < 12:
        ERRORS.append(msg[:300])

# Titles / texts that are not postdoc-or-researcher posts (STEP 1 A).
EXCLUDE_TITLE = re.compile(
    r"\bph\.?d\b(?!.{0,15}(required|holder))|predoc|pre-doc|doctoral (candidate|researcher|position|fellow)|doctorand|"
    r"promotionsstelle|promovend|\bFPU\b|\bFPI\b|student|internship|practicum|pr[aá]cticas|\bbeca\b|"
    r"professor|professur|catedr|titular|lecturer|technician|t[eé]cnic|laborant|"
    r"bachelor|master (thesis|student)|trainee|administrat|secretar|assistant professor.*tenure",
    re.I)
POSTDOC_HINT = re.compile(r"post-?doc|posdoc|postdoctoral|research (associate|scientist|fellow)|wissenschaftliche|"
                          r"investigador|researcher|scientist|forscher|senior researcher", re.I)

CITY_REGION = {
    "madrid": "Madrid", "barcelona": "Catalonia", "bellaterra": "Catalonia", "girona": "Catalonia", "lleida": "Catalonia",
    "tarragona": "Catalonia", "valencia": "Valencian Community", "alicante": "Valencian Community", "castell": "Valencian Community",
    "sevilla": "Andalusia", "seville": "Andalusia", "granada": "Andalusia", "málaga": "Andalusia", "malaga": "Andalusia",
    "córdoba": "Andalusia", "cordoba": "Andalusia", "almería": "Andalusia", "cádiz": "Andalusia", "huelva": "Andalusia",
    "jaén": "Andalusia", "bilbao": "Basque Country", "san sebastián": "Basque Country", "donostia": "Basque Country",
    "vitoria": "Basque Country", "zaragoza": "Aragon", "oviedo": "Asturias", "santander": "Cantabria", "pamplona": "Navarre",
    "murcia": "Murcia", "cartagena": "Murcia", "palma": "Balearic Islands", "laguna": "Canary Islands", "las palmas": "Canary Islands",
    "santiago de compostela": "Galicia", "coruña": "Galicia", "vigo": "Galicia", "salamanca": "Castile and León",
    "valladolid": "Castile and León", "león": "Castile and León", "burgos": "Castile and León", "badajoz": "Extremadura",
    "cáceres": "Extremadura", "logroño": "La Rioja", "albacete": "Castilla-La Mancha", "toledo": "Castilla-La Mancha",
    "berlin": "Berlin", "hamburg": "Hamburg", "bremen": "Bremen", "munich": "Bavaria", "münchen": "Bavaria",
    "nuremberg": "Bavaria", "würzburg": "Bavaria", "bayreuth": "Bavaria", "regensburg": "Bavaria", "augsburg": "Bavaria",
    "erlangen": "Bavaria", "freising": "Bavaria", "stuttgart": "Baden-Württemberg", "karlsruhe": "Baden-Württemberg",
    "freiburg": "Baden-Württemberg", "heidelberg": "Baden-Württemberg", "tübingen": "Baden-Württemberg",
    "mannheim": "Baden-Württemberg", "konstanz": "Baden-Württemberg", "frankfurt": "Hesse", "darmstadt": "Hesse",
    "kassel": "Hesse", "marburg": "Hesse", "giessen": "Hesse", "gießen": "Hesse", "köln": "North Rhine-Westphalia",
    "cologne": "North Rhine-Westphalia", "dortmund": "North Rhine-Westphalia", "aachen": "North Rhine-Westphalia",
    "bonn": "North Rhine-Westphalia", "bochum": "North Rhine-Westphalia", "düsseldorf": "North Rhine-Westphalia",
    "essen": "North Rhine-Westphalia", "münster": "North Rhine-Westphalia", "bielefeld": "North Rhine-Westphalia",
    "paderborn": "North Rhine-Westphalia", "wuppertal": "North Rhine-Westphalia", "jülich": "North Rhine-Westphalia",
    "hannover": "Lower Saxony", "göttingen": "Lower Saxony", "braunschweig": "Lower Saxony", "oldenburg": "Lower Saxony",
    "osnabrück": "Lower Saxony", "lüneburg": "Lower Saxony", "leipzig": "Saxony", "dresden": "Saxony", "chemnitz": "Saxony",
    "freiberg": "Saxony", "halle": "Saxony-Anhalt", "magdeburg": "Saxony-Anhalt", "jena": "Thuringia", "erfurt": "Thuringia",
    "weimar": "Thuringia", "ilmenau": "Thuringia", "potsdam": "Brandenburg", "cottbus": "Brandenburg",
    "rostock": "Mecklenburg-Western Pomerania", "greifswald": "Mecklenburg-Western Pomerania", "kiel": "Schleswig-Holstein",
    "flensburg": "Schleswig-Holstein", "lübeck": "Schleswig-Holstein", "mainz": "Rhineland-Palatinate",
    "trier": "Rhineland-Palatinate", "kaiserslautern": "Rhineland-Palatinate", "koblenz": "Rhineland-Palatinate",
    "saarbrücken": "Saarland",
}

# Faculty Radar
FR_URL = "https://facultyradar.eu/"
FR_RANK = re.compile(r"ayudante doctor|lector|lectora", re.I)
FR_RANK_NO = re.compile(r"titular|catedr|permanente|contratado doctor|agregat|asociad|sustitut|visitante", re.I)
FR_CORE = re.compile(r"an[aá]lisis geogr[aá]fico regional|geograf[ií]a (humana|f[ií]sica)|urban[ií]stica y ordenaci[oó]n del territorio", re.I)
FR_BORDER = re.compile(r"composici[oó]n arquitect|proyectos arquitect|ecolog[ií]a|sociolog[ií]a|ciencia pol[ií]tica|"
                       r"cartogr[aá]fica|geod[eé]sica|fotogrametr|arquitectura|urbanismo|paisaj", re.I)
FR_AREA_EN = [
    (r"an[aá]lisis geogr[aá]fico regional", "Regional Geographic Analysis"), (r"geograf[ií]a humana", "Human Geography"),
    (r"geograf[ií]a f[ií]sica", "Physical Geography"), (r"urban[ií]stica y ordenaci", "Urban Planning and Spatial Planning"),
    (r"composici[oó]n arquitect", "Architectural Composition"), (r"proyectos arquitect", "Architectural Projects"),
    (r"ecolog", "Ecology"), (r"sociolog", "Sociology"), (r"ciencia pol", "Political Science"),
    (r"cartogr", "Cartographic, Geodetic Engineering and Photogrammetry"),
]
FR_UNI_REGION = {
    "almería": ("Almería", "Andalusia"), "alicante": ("Alicante", "Valencian Community"), "burgos": ("Burgos", "Castile and León"),
    "vigo": ("Vigo", "Galicia"), "extremadura": ("Badajoz", "Extremadura"), "jaén": ("Jaén", "Andalusia"),
    "granada": ("Granada", "Andalusia"), "sevilla": ("Seville", "Andalusia"), "málaga": ("Málaga", "Andalusia"),
    "córdoba": ("Córdoba", "Andalusia"), "cádiz": ("Cádiz", "Andalusia"), "huelva": ("Huelva", "Andalusia"),
    "pablo de olavide": ("Seville", "Andalusia"), "valencia": ("Valencia", "Valencian Community"),
    "zaragoza": ("Zaragoza", "Aragon"), "oviedo": ("Oviedo", "Asturias"), "cantabria": ("Santander", "Cantabria"),
    "salamanca": ("Salamanca", "Castile and León"), "valladolid": ("Valladolid", "Castile and León"),
    "león": ("León", "Castile and León"), "murcia": ("Murcia", "Murcia"), "autónoma de madrid": ("Madrid", "Madrid"),
    "complutense": ("Madrid", "Madrid"), "alcalá": ("Alcalá de Henares", "Madrid"), "carlos iii": ("Madrid", "Madrid"),
    "rey juan carlos": ("Madrid", "Madrid"), "politécnica de madrid": ("Madrid", "Madrid"), "barcelona": ("Barcelona", "Catalonia"),
    "autònoma": ("Bellaterra", "Catalonia"), "girona": ("Girona", "Catalonia"), "lleida": ("Lleida", "Catalonia"),
    "rovira": ("Tarragona", "Catalonia"), "pompeu": ("Barcelona", "Catalonia"), "santiago": ("Santiago de Compostela", "Galicia"),
    "coruña": ("A Coruña", "Galicia"), "navarra": ("Pamplona", "Navarre"), "rioja": ("Logroño", "La Rioja"),
    "país vasco": ("Leioa", "Basque Country"), "illes balears": ("Palma", "Balearic Islands"), "laguna": ("San Cristóbal de La Laguna", "Canary Islands"),
    "las palmas": ("Las Palmas de Gran Canaria", "Canary Islands"), "castilla-la mancha": ("Ciudad Real", "Castilla-La Mancha"),
    "politècnica de catalunya": ("Barcelona", "Catalonia"), "politècnica de valència": ("Valencia", "Valencian Community"),
    "miguel hernández": ("Elche", "Valencian Community"), "jaume": ("Castellón", "Valencian Community"),
    "cartagena": ("Cartagena", "Murcia"), "pública de navarra": ("Pamplona", "Navarre"),
}


# ---------- helpers ----------

def clean(s: str) -> str:
    return " ".join((s or "").split())


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def score_text(title: str, text: str) -> tuple[dict, list[str]]:
    strength = matcher.topic_strength(title, matcher.topic_counts(text[:MAX_TEXT]))
    res = {p["id"]: matcher.score(p, strength)[0] for p in PROFILES}
    return res, matcher.main_topics(strength)


def region_of(*texts: str) -> str:
    blob = " ".join(texts).lower()
    for k, v in CITY_REGION.items():
        if k in blob:
            return v
    return ""


def parse_date(s: str):
    for fmt in ("%d %B %Y", "%d %b %Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    return None


def pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        return clean(" ".join((p.extract_text() or "") for p in reader.pages[:12]))
    except Exception:
        return ""


def known_urls() -> tuple[set[str], set[tuple[str, str]]]:
    urls, pairs = set(), set()
    for path in ("docs/data/jobs.json", "docs/data/linkedin.json"):
        for it in load_json(ROOT / path, {}).get("items", []):
            urls.add(it.get("url", ""))
            pairs.add((clean(it.get("institution", "")).lower(), clean(it.get("title", "")).lower()))
    return urls, pairs


# ---------- EURAXESS ----------

def eur_list(params: str, page: int):
    url = f"https://euraxess.ec.europa.eu/jobs/search?{params}&sort%5Bname%5D=created&sort%5Bdirection%5D=DESC"
    if page:
        url += f"&page={page}"
    soup = BeautifulSoup(fetch(url).text, "lxml")
    out = []
    for art in soup.find_all("article"):
        txt = clean(art.get_text(" "))
        m = re.search(r"Posted on:\s*(\d{1,2} \w+ \d{4})", txt)
        a = next((x for x in art.find_all("a", href=True) if re.fullmatch(r"(https://euraxess\.ec\.europa\.eu)?/jobs/\d+", x["href"])), None)
        if m and a:
            out.append({"id": re.search(r"(\d+)$", a["href"]).group(1), "title": clean(a.get_text(" ")),
                        "posted": parse_date(m.group(1)), "snippet": txt[:600]})
    return out


def eur_collect(cutoff: date) -> dict[str, dict]:
    found: dict[str, dict] = {}
    queries = []
    for cid, (cc, _) in COUNTRY.items():
        base = f"f%5B0%5D=job_country%3A{cid}"
        queries.append((base, cc))
        queries += [(f"keywords={quote(k)}&{base}", cc) for k in EUR_KEYWORDS]
        queries.append((base + EUR_FIELDS, cc))
    for params, cc in queries:
        for page in range(MAX_PAGES):
            try:
                items = eur_list(params, page)
            except Exception as e:  # network error, robots.txt, layout change
                note_error(f"EURAXESS list failed ({params[:50]}): {type(e).__name__} {e}")
                break
            if not items:
                break
            old = False
            for it in items:
                if it["posted"] and it["posted"] < cutoff:
                    old = True
                    continue
                found.setdefault(it["id"], {**it, "country": cc})
            if old:
                break
    return found


def eur_detail(offer: dict) -> dict | None:
    url = f"https://euraxess.ec.europa.eu/jobs/{offer['id']}"
    soup = BeautifulSoup(fetch(url).text, "lxml")
    main = soup.find("main") or soup
    h1 = soup.find("h1")
    title = clean(h1.get_text(" ")) if h1 else offer["title"]
    text = clean(main.get_text(" "))
    dl = re.search(r"Application Deadline:?\s*(\d{1,2} \w+ \d{4})", text)
    prof = re.search(r"Researcher Profile:?\s*(.{0,200}?)(Additional|Funding|Application|Where|Eligib|$)", text)
    org = re.search(r"Organisation/Company:?\s*(.{3,120}?)(Research Field|Department|Researcher Profile|Country)", text)
    loc = re.search(r"Work Locations:?\s*Number of offers:\s*\d+,\s*(.{0,200}?)(Research Field|Researcher Profile|$)", text)
    return {"url": url, "title": title, "text": text, "deadline": parse_date(dl.group(1)) if dl else None,
            "profile": clean(prof.group(1)) if prof else "", "org": clean(org.group(1)) if org else "",
            "loc": clean(loc.group(1)) if loc else ""}


def eur_item(offer: dict, d: dict, scores: dict, topics: list[str]) -> dict:
    cc = offer["country"]
    org = d["org"] or clean(offer["snippet"].split("Posted on")[0])[:90]
    blob = (d["loc"] + " " + org).lower()
    city = next((k.title() for k in CITY_REGION if k in blob), "")
    level = "postdoc" if re.search(r"post-?doc|posdoc|R2|R3|Recognised|Established", d["profile"] + d["title"], re.I) else "research"
    return {
        "title": d["title"], "title_en": d["title"], "institution": org, "city": city,
        "region": region_of(city, d["loc"], org), "country": cc, "level": level,
        "note": "via EURAXESS" + (f" – {d['profile']}" if d["profile"] else ""),
        "topics": topics, "match": {"A": scores["A"], "B": scores["B"]},
        "deadline": d["deadline"].isoformat() if d["deadline"] else None,
        "url": d["url"], "li_kind": "job", "first_seen": TODAY.isoformat(), "source": "EURAXESS",
    }


# ---------- Faculty Radar ----------

def fr_rows():
    r = fetch(FR_URL)
    soup = BeautifulSoup(r.text, "lxml")
    rows = []
    for tr in soup.find_all("tr")[1:]:
        cells = [clean(td.get_text(" ")) for td in tr.find_all(["td", "th"])]
        if len(cells) < 6:
            continue
        a = tr.find("a", href=True)
        dl = re.search(r"(\d{2}-\d{2}-\d{4})", cells[5])
        rows.append({"uni": cells[0], "pid": cells[1], "dept": cells[2], "rank": cells[3], "area": cells[4],
                     "deadline": parse_date(dl.group(1)) if dl else None, "href": urljoin(FR_URL, a["href"]) if a else ""})
    return rows


def fr_call_text(href: str) -> str:
    if not href:
        return ""
    try:
        r = fetch(href)
    except (Blocked, Exception) as e:
        note_error(f"FR call not readable {href}: {type(e).__name__} {e}")
        return ""
    if "pdf" in r.headers.get("content-type", "").lower() or href.lower().endswith(".pdf"):
        return pdf_text(r.content)
    return clean(BeautifulSoup(r.text, "lxml").get_text(" "))


def fr_collect(known_u: set, known_p: set) -> list[dict]:
    items = []
    try:
        rows = fr_rows()
    except Exception as e:
        note_error(f"Faculty Radar failed: {type(e).__name__} {e}")
        return items
    print(f"Faculty Radar: {len(rows)} rows")
    for r in rows:
        if not FR_RANK.search(r["rank"]) or FR_RANK_NO.search(r["rank"]):
            continue
        if r["deadline"] and r["deadline"] < TODAY:
            continue
        core = bool(FR_CORE.search(r["area"]))
        if not core and not FR_BORDER.search(r["area"] + " " + r["dept"]):
            continue
        if r["href"] in known_u or any(r["pid"].lower() in t for _, t in known_p if r["pid"]):
            continue
        text = fr_call_text(r["href"])
        title = f"{r['rank']} – {r['area']} ({r['pid']})"
        scores, topics = score_text(title, text)
        if not core and max(scores.values()) < MIN_MATCH:
            continue
        area_en = next((en for pat, en in FR_AREA_EN if re.search(pat, r["area"], re.I)), r["area"])
        city, region = next((v for k, v in FR_UNI_REGION.items() if k in r["uni"].lower()), ("", ""))
        note = "Assistant professor via Faculty Radar"
        if re.search(r"ayudante doctor", r["rank"], re.I):
            note += "; requires ANECA accreditation (Ayudante Doctor)"
        if re.search(r"catal[aà]n?|catal[aà] (nivel|level)|nivel C1 de catal|certificat de catal", text, re.I):
            note += "; Catalan may be required (check call)"
        items.append({
            "title": title, "title_en": f"Assistant professor – {area_en}", "institution": r["uni"], "city": city,
            "region": region, "country": "ES", "level": "research", "note": note, "topics": topics,
            "match": {"A": scores["A"], "B": scores["B"]},
            "deadline": r["deadline"].isoformat() if r["deadline"] else None,
            "url": r["href"] or FR_URL, "li_kind": "job", "first_seen": TODAY.isoformat(), "source": "Faculty Radar",
        })
    return items


# ---------- main ----------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=10)
    args = ap.parse_args()
    cutoff = TODAY - timedelta(days=args.days)
    known_u, known_p = known_urls()
    seen = load_json(SEEN, {})          # euraxess id -> {"score": .., "date": ..}
    prev = load_json(OUT, {}).get("items", [])
    stats = {"euraxess_listed": 0, "euraxess_opened": 0, "faculty_radar_kept": 0}

    items: dict[str, dict] = {it["url"]: it for it in prev if not it.get("deadline") or it["deadline"] >= TODAY.isoformat()}

    offers = eur_collect(cutoff)
    stats["euraxess_listed"] = len(offers)
    for oid, offer in offers.items():
        url = f"https://euraxess.ec.europa.eu/jobs/{oid}"
        if oid in seen or url in known_u or url in items:
            continue
        if EXCLUDE_TITLE.search(offer["title"]) and not re.search(r"post-?doc|posdoc", offer["title"], re.I):
            seen[oid] = {"skip": "title", "date": TODAY.isoformat()}
            continue
        try:
            d = eur_detail(offer)
        except Exception as e:
            note_error(f"EURAXESS offer {oid} failed: {type(e).__name__} {e}")
            continue
        stats["euraxess_opened"] += 1
        seen[oid] = {"date": TODAY.isoformat()}
        if not d or (d["deadline"] and d["deadline"] < TODAY):
            continue
        if d["profile"] and re.fullmatch(r"First Stage Researcher \(R1\)", d["profile"].strip()) and not POSTDOC_HINT.search(d["title"]):
            seen[oid]["skip"] = "R1"
            continue
        if EXCLUDE_TITLE.search(d["title"]) and not re.search(r"post-?doc|posdoc", d["title"], re.I):
            seen[oid]["skip"] = "title"
            continue
        if (d["org"] and (d["org"].lower(), d["title"].lower()) in known_p):
            continue
        scores, topics = score_text(d["title"], d["text"])
        seen[oid]["score"] = scores
        if max(scores.values()) >= MIN_MATCH:
            items[url] = eur_item(offer, d, scores, topics)

    for it in fr_collect(known_u, known_p):
        if it["url"] not in items:
            items[it["url"]] = it
    stats["faculty_radar_kept"] = sum(1 for i in items.values() if i["source"] == "Faculty Radar")

    # drop what is already known elsewhere or has expired
    final = [i for u, i in items.items() if u not in known_u and (not i.get("deadline") or i["deadline"] >= TODAY.isoformat())]
    final.sort(key=lambda i: -max(i["match"].values()))
    # forget seen ids older than 60 days
    keep_from = (TODAY - timedelta(days=60)).isoformat()
    seen = {k: v for k, v in seen.items() if v.get("date", "9") >= keep_from}
    OUT.write_text(json.dumps({"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "stats": stats, "errors": ERRORS,
                               "items": final}, ensure_ascii=False, indent=1), encoding="utf-8")
    SEEN.write_text(json.dumps(seen, ensure_ascii=False, indent=0), encoding="utf-8")
    print(stats, "kept", len(final))


if __name__ == "__main__":
    main()
