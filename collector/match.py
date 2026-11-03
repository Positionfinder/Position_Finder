"""Match positions against research profiles (sources/profiles.yaml).

Each profile is a weighted set of research topics taken from a CV. A position's match % is how
much of a profile's research the ad covers:

    hit strength per topic: 1.0 if the topic is in the title / listing row or appears at least
    twice in the ad text, 0.5 if it appears once in the ad text, else 0
    raw   = sum(weight * strength) over the profile's topics
    match = min(100, 100 * raw / profile.full_match)

and a position with no strong hit on any of the profile's core topics is capped at 55 %, so it
cannot reach the default 60 % threshold on secondary topics alone. No CV text is stored; only
the topic lists in profiles.yaml.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

I = re.I
# id: (English name, [patterns]); a pattern starting with "CS:" is case-sensitive.
TOPICS: dict[str, tuple[str, list[str]]] = {
    "ppgis": ("Participatory GIS (PPGIS)", [
        r"\bppgis\b", r"\bpgis\b", r"public participation (gis|geographic)", r"participatory (gis|mapping|spatial)",
        r"mapeo participativo", r"cartograf[ií]a participativa", r"mapatge participatiu", r"partizipative[ns]? kartier",
        r"volunteered geographic", r"citizen science"]),
    "participation": ("Citizen participation & co-design", [
        r"citizen participation", r"public participation", r"community (engagement|participation|based)", r"co-?design",
        r"co-?creation", r"participatory (planning|research|methods?|approach|process)", r"participaci[oó]n ciudadana",
        r"participaci[oó] ciutadana", r"b[uü]rgerbeteiligung", r"\bbeteiligung", r"partizipati", r"stakeholder engagement",
        r"living lab", r"transdisciplinar", r"\bparticipatory\b", r"participativ"]),
    "risk_perception": ("Risk perception", [
        r"risk perception", r"perceived risk", r"percepci[oó]n del riesgo", r"percepci[oó] del risc",
        r"risikowahrnehmung", r"risk communication"]),
    "tech_risk": ("Industrial & technological risk", [
        r"industrial (risk|hazard|accident)", r"technological (risk|hazard)", r"petrochemi", r"chemical (industr|plant|accident)",
        r"riesgo tecnol[oó]gico", r"risc tecnol[oò]gic", r"st[oö]rfall", r"seveso"]),
    "flood": ("Flood risk & urban water", [
        r"\bflood", r"inundaci", r"hochwasser", r"starkregen", r"pluvial", r"water[- ]sensitive", r"blue[- ]green",
        r"blau[- ]gr[uü]n", r"stormwater", r"urban water", r"sponge cit", r"schwammstadt", r"river restoration",
        r"renaturierung"]),
    "ecosystem_services": ("Ecosystem services & nature-based solutions", [
        r"ecosystem service", r"servicios? ecosist[eé]mic", r"serveis? ecosist[eè]mic", r"[oö]kosystemleistung",
        r"natural capital", r"nature'?s contributions", r"\binvest model", r"nature[- ]based solution",
        r"soluciones basadas en la naturaleza", r"naturbasierte"]),
    "green_health": ("Urban green space, health & wellbeing", [
        r"green (space|infrastructure)", r"urban green", r"greenery", r"espacios? verdes?", r"espais? verds?",
        r"stadtgr[uü]n", r"gr[uü]nfl[aä]che", r"gr[uü]ne infrastruktur", r"mental health", r"well-?being", r"healthy cit",
        r"salud mental", r"salut mental", r"gesundheit", r"nature access", r"public health"]),
    "landscape": ("Landscape & landscape planning", [
        r"landscape", r"paisaj", r"paisatg", r"landschaft"]),
    "resilience": ("Climate adaptation & resilience", [
        r"resilien", r"climate (change )?adaptation", r"adaptaci[oó]n al cambio clim", r"adaptaci[oó] al canvi clim",
        r"klima(wandel)?anpassung", r"urban heat", r"heat (stress|island)", r"hitze", r"isla de calor", r"disaster risk",
        r"natural hazard"]),
    "spatial_justice": ("Spatial & environmental justice", [
        r"spatial justice", r"environmental justice", r"justicia (espacial|ambiental)", r"just[ií]cia (espacial|ambiental)",
        r"umweltgerechtigkeit", r"(socio-?)?spatial inequalit", r"segregation", r"social vulnerab", r"socio-?spatial",
        r"socioespacial", r"just transition", r"inclusive (city|cities|planning)"]),
    "urban_growth": ("Urbanization & land-use change", [
        r"urbani[sz]ation", r"urban (growth|expansion|sprawl)", r"land[- ]use change", r"land[- ]use (and|&) land[- ]cover",
        r"crecimiento urbano", r"expansi[oó]n urbana", r"siedlungsentwicklung", r"fl[aä]chen(inanspruchnahme|verbrauch)",
        r"suburbani", r"peri-?urban"]),
    "gis_rs": ("GIS, remote sensing & spatial analysis", [
        r"CS:\bGIS\b", r"CS:\bSIG\b", r"geographic(al)? information", r"remote sensing", r"teledetec", r"fernerkundung",
        r"earth observation", r"satellite (data|imag)", r"\blandsat", r"\bsentinel-?\d", r"geospatial", r"geoespacial",
        r"spatial (analysis|data|model)", r"an[aá]lisis espacial", r"geodaten", r"geoinformati", r"\bqgis\b", r"\barcgis\b"]),
    "urban_planning": ("Urban & spatial planning", [
        r"urban planning", r"spatial planning", r"regional planning", r"town planning", r"city planning", r"urbanism",
        r"planificaci[oó]n (urbana|territorial)", r"planificaci[oó] (urbana|territorial)", r"ordenaci[oó]n? del territori",
        r"stadtplanung", r"raumplanung", r"regionalplanung", r"st[aä]dtebau", r"stadtentwicklung", r"raumentwicklung",
        r"urban development", r"desarrollo urbano", r"urban design", r"dise[nñ]o urbano"]),
    "informal": ("Informal settlements, displacement & upgrading", [
        r"informal settlement", r"\bslum", r"asentamientos? informal", r"assentaments? informal", r"informelle siedlung",
        r"(neighbou?rhood|slum|settlement) upgrading", r"deprived (neighbou?rhood|area)", r"barrios? vulnerable",
        r"refugee", r"displace", r"desplazad", r"gefl[uü]chtete", r"flucht"]),
    "housing": ("Housing & housing policy", [
        r"\bhousing\b", r"vivienda", r"habitatge", r"wohnungs", r"\bwohnen\b", r"affordable hous", r"social hous"]),
    "governance": ("Urban governance & policy", [
        r"urban governance", r"\bgovernance\b", r"gobernanza", r"governan[cç]a", r"policy (analysis|evaluation)",
        r"planning polic", r"urban polic", r"pol[ií]ticas? urbanas?", r"public polic", r"stadtpolitik", r"planungskultur"]),
    "digital_ai": ("Digital planning tools & AI", [
        r"digital (planning|participation|platform|twin|tools?)", r"artificial intelligence", r"CS:\bAI\b", r"CS:\bKI\b",
        r"machine learning", r"aprendizaje autom[aá]tico", r"k[uü]nstliche intelligenz", r"smart cit", r"e-?participation",
        r"civic tech", r"urban (data|analytics|informatics)", r"digitale stadt"]),
    "sdg": ("Sustainable development (SDGs)", [
        r"sustainable development goals", r"CS:\bSDGs?\b", r"CS:\bODS\b", r"agenda 2030", r"sustainable urban development",
        r"desarrollo (urbano )?sostenible", r"nachhaltige (stadt)?entwicklung", r"sustainability transition",
        r"urban sustainab"]),
    "mcda": ("Multi-criteria decision analysis", [
        r"multi-?criteria", r"CS:\bAHP\b", r"CS:\bANP\b", r"analytic (hierarchy|network) process", r"decision support",
        r"multikriteri", r"an[aá]lisis multicriterio"]),
    "survey_methods": ("Surveys & mixed methods", [
        r"\bsurvey", r"questionnaire", r"encuesta", r"enquesta", r"befragung", r"mixed[- ]methods?", r"qualitative (research|methods|data)",
        r"interviews?\b", r"statistical analysis"]),
    "global_south": ("Global South & comparative studies", [
        r"global south", r"developing countr", r"\bafrica", r"latin america", r"middle east", r"\biran\b", r"colombia",
        r"comparative (case|stud|urban)", r"international development"]),
}

_COMPILED: dict[str, list[re.Pattern]] = {
    tid: [re.compile(p[3:]) if p.startswith("CS:") else re.compile(p, I) for p in pats]
    for tid, (_, pats) in TOPICS.items()
}


def topic_counts(text: str) -> dict[str, int]:
    """How often each topic occurs in a text (used for the offer page text; cached)."""
    out = {}
    for tid, pats in _COMPILED.items():
        n = sum(len(p.findall(text)) for p in pats)
        if n:
            out[tid] = min(n, 50)
    return out


def topic_strength(row_text: str, detail_counts: dict[str, int]) -> dict[str, float]:
    row = topic_counts(row_text)
    strength = {}
    for tid in TOPICS:
        if row.get(tid) or detail_counts.get(tid, 0) >= 2:
            strength[tid] = 1.0
        elif detail_counts.get(tid, 0) == 1:
            strength[tid] = 0.5
    return strength


def load_profiles(path: Path) -> list[dict]:
    profiles = yaml.safe_load(path.read_text(encoding="utf-8"))
    for pr in profiles:
        unknown = [t for t in list(pr["core"]) + list(pr.get("secondary", {})) + list(pr.get("methods", {})) if t not in TOPICS]
        assert not unknown, f"unknown topics in profile {pr['id']}: {unknown}"
    return profiles


def score(profile: dict, strength: dict[str, float]) -> tuple[int, list[str]]:
    weights = {**{t: 1.0 for t in profile.get("methods", [])},
               **{t: 2.0 for t in profile.get("secondary", [])},
               **{t: 3.0 for t in profile["core"]}}
    raw = sum(w * strength.get(t, 0) for t, w in weights.items())
    pct = min(100, round(100 * raw / profile["full_match"]))
    if not any(strength.get(t, 0) >= 1 for t in profile["core"]):
        pct = min(pct, 55)
    matched = sorted((t for t in weights if strength.get(t)), key=lambda t: -weights[t] * strength[t])
    return pct, matched


def main_topics(strength: dict[str, float], limit: int = 3) -> list[str]:
    """English names of the position's strongest topics, for the Topic column."""
    # Methods-only topics are less informative as a "topic"; list them last.
    order = sorted(strength, key=lambda t: (-strength[t], t in ("survey_methods", "global_south")))
    return [TOPICS[t][0] for t in order if strength[t] >= 1][:limit]
