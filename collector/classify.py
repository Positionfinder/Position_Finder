"""Classify a position text: PhD vs postdoc, subject fields, programme call, deadline."""
from __future__ import annotations

import re
from datetime import date

PHD = re.compile(
    r"predoctoral|pre-doctoral|predoc\b|ph\.?\s?d\.?\s?(student|candidate|position|fellowship|contract|scholarship)|"
    r"doctoral (student|candidate|researcher|position|fellowship|contract)|doctorand[oa]?s?|"
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
        r"city planning|planning (theory|policy)|urban (design|regeneration|renewal|policy|studies|development|governance|form)|"
        r"\bsmart cit|ciudades?\b|ciutats?\b|\bcities\b|\bcity\b|metropolitan|metropolita|territorial|territori\b|"
        r"urban\b|urbanas?\b|urbans?\b|urbanes\b",
        re.I,
    ),
    "Architecture": re.compile(
        r"architect|arquitect|edificaci[oó]|building (design|technology|physics|energy|performance)|built environment|"
        r"\bETSA[BMVS]?\b|construcci[oó]n arquitect|rehabilitaci[oó]n (de edificios|energ)|rehabilitaci[oó] (d'edificis|energ)|"
        r"interior design|dise[nñ]o arquitect",
        re.I,
    ),
    "Geography": re.compile(r"geograf|geograph|demograf|demograph|population studies|human geography", re.I),
    "Landscape": re.compile(r"landscape|paisaj|paisatg|green infrastructure|infraestructura verde|ecosystem services|servicios ecosist", re.I),
    "GIS & remote sensing": re.compile(
        r"\bGIS\b|\bSIG\b|geographic information|informaci[oó]n geogr|informaci[oó] geogr|remote sensing|teledetec|"
        r"cartograf|cartograph|geospatial|geoespacial|geomatic|geom[aà]tica|earth observation|observaci[oó]n de la tierra",
        re.I,
    ),
    "Mobility & transport": re.compile(r"mobility|movilidad|mobilitat|transport planning|planificaci[oó]n del transporte|accessibility|accesibilidad|accessibilitat", re.I),
    "Housing": re.compile(r"\bhousing\b|vivienda|habitatge", re.I),
    "Heritage": re.compile(r"heritage|patrimonio (arquitect|cultural|hist)|patrimoni (arquitect|cultural)", re.I),
    "Climate & risk": re.compile(
        r"climate adaptation|adaptaci[oó]n al cambio clim|adaptaci[oó] al canvi clim|flood risk|riesgo de inundaci|"
        r"risc d'inundaci|natural hazards|riesgos naturales|urban heat|isla de calor|resilien",
        re.I,
    ),
}
# "Urban planning" catches broad words like city/urban/territorial; require something stronger
# from another field, or a strong planning term, before trusting it alone.
STRONG_PLANNING = re.compile(
    r"urban plann|urbanism|urbanis[mt]|urban[ií]stic|planificaci[oó]n urbana|planificaci[oó] urbana|ordenaci[oó]n del territorio|"
    r"ordenaci[oó] del territori|spatial planning|regional planning|town planning|city planning|urban (design|regeneration|studies|policy|governance)",
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
    r"termini|data l[ií]mit|fins al|fins el|finaliza|fecha de cierre|cierre",
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
    best = None
    for pos, d in dates:
        near = [abs(pos - c) for c in cues if -40 <= pos - c <= 200]
        if near and (best is None or min(near) < best[0]):
            best = (min(near), d)
    if best and best[1] >= today:
        return best[1].isoformat()
    return None


def level(text: str) -> str | None:
    p, q = bool(PHD.search(text)), bool(POSTDOC.search(text))
    if p and q:
        return "phd+postdoc"
    return "phd" if p else "postdoc" if q else None


def fields(text: str) -> list[str]:
    hits = [name for name, pat in FIELDS.items() if pat.search(text)]
    if hits == ["Urban planning"] and not STRONG_PLANNING.search(text):
        # broad "urban/city" only: keep it if it appears several times
        if len(FIELDS["Urban planning"].findall(text)) < 3:
            return []
    return hits


def is_programme(title: str) -> bool:
    return bool(PROGRAMME.search(title))
