"""Classify a position text: PhD vs postdoc, subject fields, programme call, deadline."""
from __future__ import annotations

import re
from datetime import date

PHD = re.compile(
    r"predoctoral|pre-doctoral|predoc\b|ph\.?\s?d\.?\s?(student|candidate|position|fellowship|contract|scholarship)|"
    r"(?<![a-z-])doctoral (student|candidate|researcher|position|fellowship|contract)|doctorand[oa]?s?|"
    r"\bfpi\b|\bfpu\b|\bR1\b|first stage researcher|investigador[a]? (en formaci[oó]n|predoctoral)|"
    r"personal investigador en formaci|contrat[eo]s? predoctorals?|beca predoctoral|tesis doctoral|joan or[oó]|\bINPhINIT\b",
    re.I,
)
POSTDOC = re.compile(
    r"postdoctoral|post-doctoral|posdoctoral|postdoc|post-doc|\bR2\b|recognised researcher|recognized researcher|"
    r"investigador[a]? (doctor[a]?|posdoctoral|postdoctoral)|personal investigador doctor|"
    r"juan de la cierva|margarita salas|mar[ií]a zambrano|beatriu de pin[oó]s|ram[oó]n y cajal|junior leader|"
    r"marie (sk[lł]odowska-)?curie postdoctoral|msca postdoctoral|research fellow|doctor/a|doctor or doctora",
    re.I,
)
# Programme-level calls that are open to all fields (shown separately as "Fellowship calls").
PROGRAMME = re.compile(
    r"juan de la cierva|ram[oó]n y cajal|margarita salas|mar[ií]a zambrano|beatriu de pin[oó]s|beatriz galindo|"
    r"junior leader|\bfpu\b(?! ?upc)|fpu (ministry|ministeri|ministerio)|\bINPhINIT\b|joan or[oó]|\bFI\b ?(SDUR|STEP)?|"
    r"axa (post-?doctoral )?fellowship|google ph\.?d fellowship|marie (sk[lł]odowska-)?curie|\bmsca\b|"
    r"ayudas para contratos predoctorales|formaci[oó]n de profesorado universitario|requalificaci",
    re.I,
)

FIELDS: dict[str, re.Pattern] = {
    "Urban planning": re.compile(
        r"urban plann|urbanism|urbanis[mt]|urban[ií]stic|urbanist|planificaci[oó]n urbana|planificaci[oó] urbana|"
        r"ordenaci[oó]n del territorio|ordenaci[oó] del territori|spatial planning|regional planning|town planning|"
        r"city planning|land[- ]use planning|planning (theory|policy|system)|"
        r"urban (design|regeneration|renewal|policy|policies|studies|development|governance|form|transformation|analytics|"
        r"sustainability|transition|planning|space|spaces|environment|green|nature|morphology|growth|sprawl|segregation|inequalit|"
        r"adaptation|climate|health|heat|resilience|systems|economics|geography|ecology|mobility|areas?|land)|"
        r"\bsmart cit|socio-?spatial|socioespacial|spatial justice|justicia espacial|just[ií]cia espacial|"
        r"regeneraci[oó]n urbana|regeneraci[oó] urbana|espacio p[uú]blico|espai p[uú]blic|public space|"
        r"desarrollo urbano|desenvolupament urb|metropolitan (area|region|planning)|[aá]rea metropolitana|"
        r"pol[ií]ticas? urbanas?|estudios urbanos|estudis urbans|ciudades sostenibles|sustainable cities",
        re.I,
    ),
    "Architecture": re.compile(
        r"\barchitect(ure|ural|s)?\b|\barquitect(ura|ure|ònic|onic|[oó]nica|[oó]nico|es|os|as|a|e)?\b|\barquitectes\b|"
        r"edificaci[oó]|building (design|technology|physics|energy|performance|information|stock|renovation)|built environment|"
        r"\bETSA[BMVS]?\b|\bBIM\b|rehabilitaci[oó]n (de edificios|energ)|rehabilitaci[oó] (d'edificis|energ)|"
        r"construcci[oó]n sostenible|interior design|dise[nñ]o arquitect",
        re.I,
    ),
    "Geography": re.compile(r"geograf|geograph|demograf|demograph|population studies", re.I),
    "Landscape": re.compile(r"landscape|paisaj|paisatg|green infrastructure|infraestructura verde|infraestructures? verds?|"
                            r"nature-based solutions|soluciones basadas en la naturaleza|ecosystem services|servicios ecosist[eé]micos|"
                            r"serveis ecosist[eè]mics|urban green|espacios verdes|espais verds|green spaces", re.I),
    "Housing": re.compile(r"\bhousing\b|vivienda|habitatge", re.I),
    "GIS & remote sensing": re.compile(
        r"\bGIS\b|\bSIG\b|geographic information|informaci[oó]n geogr|informaci[oó] geogr|remote sensing|teledetec|"
        r"cartograf|cartograph|geospatial|geoespacial|geom[aà]tic|earth observation|observaci[oó]n de la tierra|PPGIS",
        re.I,
    ),
    "Mobility & transport": re.compile(
        r"urban mobility|movilidad urbana|mobilitat urbana|sustainable mobility|movilidad sostenible|mobilitat sostenible|"
        r"transport planning|planificaci[oó]n del transporte|planificaci[oó] del transport|public transport|transporte p[uú]blico|"
        r"transport p[uú]blic|active mobility|movilidad activa|cycling|ciclismo urbano|walkability|caminabilidad|"
        r"travel behaviou?r|accessibility (analysis|planning|to)|accesibilidad (urbana|territorial)", re.I),
    "Heritage": re.compile(r"architectural heritage|built heritage|patrimonio (arquitect|construido|urbano)|patrimoni (arquitect|construït|urb)", re.I),
    "Climate & risk": re.compile(
        r"climate (change )?adaptation|adaptaci[oó]n al cambio clim|adaptaci[oó] al canvi clim|flood risk|riesgo de inundaci|"
        r"risc d'inundaci|natural hazards|riesgos naturales|urban heat|isla de calor|illa de calor|heat island|"
        r"climate resilien|urban resilien|resiliencia (urbana|clim)|resili[eè]ncia (urbana|clim)|risk perception|percepci[oó]n del riesgo",
        re.I,
    ),
}
CORE = {"Urban planning", "Architecture", "Geography", "Landscape", "Housing"}
COMPUTING = re.compile(
    r"comput|software|hardware|network|xarx|redes|sistem|system|processad|processor|chip|cloud|data|dades|datos|"
    r"neural|neuronal|transformer|model|ia\b|ai\b|deep learning|memòria|memoria|quant|qu[aà]ntic|microarquitect|"
    r"5g|6g|telecom|circuit|fpga|gpu|cpu|servei|service",
    re.I,
)

MONTHS = {
    # es
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    # ca
    "gener": 1, "febrer": 2, "març": 3, "marc": 3, "maig": 5, "juny": 6, "juliol": 7, "agost": 8,
    "setembre": 9, "novembre": 11, "desembre": 12,
    # en
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}
_MON = "|".join(sorted(MONTHS, key=len, reverse=True))
DATE_PATTERNS = [
    (re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](20\d{2})\b"), lambda m: (int(m[3]), int(m[2]), int(m[1]))),
    (re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b"), lambda m: (int(m[1]), int(m[2]), int(m[3]))),
    (re.compile(rf"\b(\d{{1,2}})\s+(?:de\s+|d')?({_MON})\s+(?:de\s+|del\s+)?(20\d{{2}})\b", re.I),
     lambda m: (int(m[3]), MONTHS[m[2].lower()], int(m[1]))),
    (re.compile(rf"\b({_MON})\s+(\d{{1,2}}),?\s+(20\d{{2}})\b", re.I), lambda m: (int(m[3]), MONTHS[m[1].lower()], int(m[2]))),
]
DEADLINE_CUE = re.compile(
    r"deadline|closing date|apply (by|before)|application period|until|plazo|fecha l[ií]mite|fin de plazo|hasta el|"
    r"termini|data l[ií]mit|fins al|fins el|finaliza|fecha de cierre|cierre|solicitud:|solicitudes|sol·licituds|"
    r"presentaci[oó]n? de (solicitudes|sol·licituds)|applications?:",
    re.I,
)


def _dates(text: str) -> list[tuple[int, date]]:
    found = []
    for pat, conv in DATE_PATTERNS:
        for m in pat.finditer(text):
            try:
                y, mo, d = conv(m)
                found.append((m.start(), date(y, mo, d)))
            except (ValueError, KeyError):
                pass
    return found


def deadline(text: str, today: date | None = None) -> str | None:
    today = today or date.today()
    dates = _dates(text)
    if not dates:
        return None
    cues = [m.start() for m in DEADLINE_CUE.finditer(text)]
    # Dates shortly after a cue; for a window like "19/10/2026 - 30/10/2026" the later date is the deadline.
    near = [d for pos, d in dates if any(-40 <= pos - c <= 160 for c in cues)]
    if not near:
        return None
    first_cue = min(c for c in cues if any(-40 <= pos - c <= 160 for pos, _ in dates))
    window = [d for pos, d in dates if -40 <= pos - first_cue <= 160]
    best = max(window)
    return best.isoformat() if best >= today else None


def level(text: str) -> str | None:
    p, q = bool(PHD.search(text)), bool(POSTDOC.search(text))
    if p and q:
        return "phd+postdoc"
    return "phd" if p else "postdoc" if q else None


def _architecture_hits(text: str) -> int:
    n = 0
    for m in FIELDS["Architecture"].finditer(text):
        around = text[max(0, m.start() - 40): m.end() + 45]
        if not COMPUTING.search(around):
            n += 1
    return n


def fields(text: str) -> list[str]:
    hits = []
    for name, pat in FIELDS.items():
        if name == "Architecture":
            if _architecture_hits(text):
                hits.append(name)
        elif pat.search(text):
            hits.append(name)
    return hits


def relevant(flds: list[str]) -> bool:
    """A position counts if it has a core field, or at least two related ones."""
    return bool(CORE & set(flds)) or len(flds) >= 2


def is_programme(title: str) -> bool:
    return bool(PROGRAMME.search(title))


_NORMALISE = [
    (re.compile(r"juan de la cierva", re.I), "Juan de la Cierva"),
    (re.compile(r"ram[oó]n y cajal|ramon i cajal", re.I), "Ramón y Cajal"),
    (re.compile(r"margarita salas", re.I), "Margarita Salas"),
    (re.compile(r"mar[ií]a zambrano", re.I), "María Zambrano"),
    (re.compile(r"beatriu de pin[oó]s", re.I), "Beatriu de Pinós"),
    (re.compile(r"beatriz galindo", re.I), "Beatriz Galindo"),
    (re.compile(r"junior leader", re.I), "la Caixa Junior Leader"),
    (re.compile(r"\bINPhINIT\b", re.I), "la Caixa INPhINIT"),
    (re.compile(r"joan or[oó]", re.I), "Joan Oró FI"),
    (re.compile(r"\bfpu\b|formaci[oó]n de profesorado universitario|formaci[oó] de professorat universitari", re.I), "FPU"),
    (re.compile(r"doctorados? industriales|doctorats? industrials", re.I), "Industrial Doctorates"),
    (re.compile(r"marie (sk[lł]odowska-)?curie|\bmsca\b", re.I), "MSCA"),
]


def programme_key(text: str) -> str | None:
    """Normalised programme name plus year, e.g. 'Juan de la Cierva 2026', for calls open to all fields."""
    if not PROGRAMME.search(text) and not any(p.search(text) for p, _ in _NORMALISE):
        return None
    name = next((n for p, n in _NORMALISE if p.search(text)), None)
    if not name:
        return None
    if name == "FPU" and re.search(r"fpu[- ]?(upc|uam|ugr|us|um|uv)\b|plan propio|programa propio", text, re.I):
        return None  # university's own FPU-style scheme: treat as a local call, not the national one
    years = re.findall(r"\b(20\d{2})\b", text)
    return f"{name} {max(years)}" if years else name
