"""Classify a position text: PhD vs postdoc, subject fields, programme call, deadline."""
from __future__ import annotations

import re
from datetime import date

PHD = re.compile(
    r"predoctoral|pre-doctoral|predoc\b|ph\.?\s?d\.?\s?(student|candidate|position|fellowship|contract|scholarship)|"
    r"(?<![a-z-])doctoral (student|candidate|researcher|position|fellowship|contract)|(?<!post)(?<!post-)(?<!pos)doctorand[oa]?s?|"
    r"\bfpi\b|\bfpu\b|\bR1\b|first stage researcher|investigador[a]? (en formaci[oó]n|predoctoral)|"
    r"personal investigador en formaci|contrat[eo]s? predoctorals?|beca predoctoral|tesis doctoral|joan or[oó]|\bINPhINIT\b|"
    # de
    r"(?<!post)(?<!post-)doktorand|promotionsstelle|promotionsvorhaben|(m[oö]glichkeit|gelegenheit) zur (promotion|weiterqualifikation)|"
    r"zur promotion|promovieren|dissertation|promotionsm[oö]glichkeit|mit promotion\b|promotionsstelle|"
    r"(?<![a-z-])doctoral researcher|phd position|phd candidate|phd student|"
    # pl / cs / ro / tr (Poland, Czech Republic, Romania, Turkey)
    r"doktorant|szko[lł]\w* doktorsk|stypendi\w* doktoranck|\basystent\w*|"
    r"(?<!post)(?<!post-)doktorand|doktorsk\w* student|(?<!odborn[ýy] )\basistent\b(?! (?:professor|prof))|"
    r"(?<!post)(?<!post-)doctorand|asistent de cercetare|asistent universitar|burs[aă] doctoral|"
    r"ara[sş]t[ıi]rma g[oö]revlisi|doktora (ö[gğ]rencisi|bursiyeri|bursu)|yüksek lisans ö[gğ]rencisi",
    re.I,
)
POSTDOC = re.compile(
    r"postdoctoral|post-doctoral|posdoctoral|postdoc|post-doc|\bR2\b|recognised researcher|recognized researcher|"
    r"investigador[a]? (doctor[a]?|posdoctoral|postdoctoral)|personal investigador doctor|"
    r"juan de la cierva|margarita salas|mar[ií]a zambrano|beatriu de pin[oó]s|ram[oó]n y cajal|junior leader|"
    r"marie (sk[lł]odowska-)?curie postdoctoral|msca postdoctoral|research fellow|doctor/a|doctor or doctora|"
    # de
    r"postdoktorand|promoviert|abgeschlossene[nr]? promotion|nach (der|abgeschlossener) promotion|"
    r"(promotion|ph\.?\s?d\.?) (ist |wird )?(vorausgesetzt|erforderlich)|nachwuchsgruppenleit|habilitation|"
    r"completed (a |your )?(ph\.?\s?d|doctora)|(ph\.?\s?d|doctoral degree) (is )?(required|completed)|holding a ph\.?\s?d|"
    # pl / cs / ro / tr
    r"sta[zż]\w* podoktorsk|stopie[nń]\w* doktora|stopniem doktora|naukowiec ze stopniem doktora|"
    r"postdoktorand|postdok|titul\w* ph\.?\s?d|absolvent\w* doktorsk|"
    r"postdoctorand|post-doctorand|cercet[aă]tor\w* postdoctoral|titlul\w* de doctor|\bCS ?III\b|"
    r"doktora sonras[ıi]|post-?doktora|doktora derecesine sahip|doktoras[ıi]n[ıi] tamamlam[ıi][sş]",
    re.I,
)
# Assistant-professor level posts in Poland, Czech Republic, Romania and Turkey (PhD required).
# They are kept as researcher-level posts with a note, like the Spanish assistant-professor posts.
ASSISTANT_PROF = re.compile(
    r"\badiunkt\w*|odborn[ýy]\w* asistent\w*|lector universitar|\blector\b|[sș]ef de lucr[aă]ri|"
    r"dr\.? ?[öo][gğ]r(etim|\.)? ?[üu]yesi|doktor [öo][gğ]retim [üu]yesi|assistant professor",
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
        r"pol[ií]ticas? urbanas?|estudios urbanos|estudis urbans|ciudades sostenibles|sustainable cities|"
        # de
        r"stadtplanung|raumplanung|st[aä]dtebau|stadtentwicklung|raumentwicklung|regionalplanung|regionalentwicklung|"
        r"stadtforschung|stadt- und regionalplanung|raumordnung|raumwissenschaft|stadtumbau|quartiersentwicklung|"
        r"siedlungsentwicklung|fl[aä]chennutzung|urbane (transformation|resilienz|r[aä]ume)|stadtregion|"
        r"planungswissenschaft|landesplanung|bauleitplanung|transformationsforschung"
        # pl / cs / ro / tr
        r"|gospodark\w* przestrzenn|planowani\w* przestrzenn|urbanisty|rozw[oó]j\w* (miast|regionaln|lokaln)|rewitalizac|"
        r"polityk\w* miejsk|studi\w* miejsk|geografi\w* spo[lł]eczno-ekonomiczn|"
        r"územní\w* plánování|územního plánování|regionální\w* rozvoj|rozvoj\w* měst|městsk\w* studi|"
        r"amenaj\w* (a )?teritori|planific\w* (urban|spa[tț]ial|teritorial)|dezvoltare (urban|regional|teritorial)|regenerare urban|"
        r"[sş]ehir ve b[oö]lge planlama|[sş]ehir planlama|kentsel (tasar[ıi]m|d[oö]n[üu][sş][üu]m|planlama|çal[ıi][sş]malar)|"
        r"b[oö]lge planlama|kent planlama|kentle[sş]me|mek[aâ]nsal planlama",
        re.I,
    ),
    "Architecture": re.compile(
        r"\barchitect(ure|ural|s)?\b|\barquitect(ura|ure|ònic|onic|[oó]nica|[oó]nico|es|os|as|a|e)?\b|\barquitectes\b|"
        r"edificaci[oó]|building (design|technology|physics|energy|performance|information|stock|renovation)|built environment|"
        r"\bETSA[BMVS]?\b|\bBIM\b|rehabilitaci[oó]n (de edificios|energ)|rehabilitaci[oó] (d'edificis|energ)|"
        r"construcci[oó]n sostenible|interior design|dise[nñ]o arquitect|"
        r"\barchitektur\b|architektonisch|baukultur|geb[aä]udeplanung|entwerfen|bauphysik"
        r"|architektur\w*|\barchitekt\w*|arhitectur|\barhitect|mimarl[ıi]k|\bmimari\b",
        re.I,
    ),
    "Geography": re.compile(r"geograf|geograph|demograf|demograph|population studies|humangeograph|"
                            r"wirtschaftsgeograph|sozialgeograph|co[gğ]rafya", re.I),
    "Landscape": re.compile(r"landscape|paisaj|paisatg|green infrastructure|infraestructura verde|infraestructures? verds?|"
                            r"nature-based solutions|soluciones basadas en la naturaleza|ecosystem services|servicios ecosist[eé]micos|"
                            r"serveis ecosist[eè]mics|urban green|espacios verdes|espais verds|green spaces|"
                            r"landschaft|gr[uü]ne infrastruktur|[oö]kosystemleistung|stadtgr[uü]n|freiraumplanung|"
                            r"naturbasierte l[oö]sungen|umweltplanung|landnutzung|"
                            r"krajobraz|zieleń miejsk|zielon\w* infrastruktur|us[lł]ug\w* ekosystem|rozwi[aą]za\w* oparte na przyrodzie|"
                            r"krajin|ekosystémov\w* služ|zelen\w* infrastruktur|městsk\w* zele|"
                            r"peisaj|servicii(le)? ecosistemic|infrastructur\w* verde|spa[tț]ii verzi|"
                            r"peyzaj|ekosistem hizmet|ye[sş]il altyap[ıi]|kentsel ye[sş]il|ye[sş]il alan", re.I),
    "Housing": re.compile(r"\bhousing\b|vivienda|habitatge|wohnungs(markt|politik|bau|forschung)|\bwohnen\b|"
                         r"mieszkalnictw|mieszkaniow|bydlen[íi]|bytov\w* politik|locuin[tț]|locuire|\bkonut", re.I),
    "GIS & remote sensing": re.compile(
        r"\bGIS\b|\bSIG\b|geographic information|informaci[oó]n geogr|informaci[oó] geogr|remote sensing|teledetec|"
        r"cartograf|cartograph|geospatial|geoespacial|geom[aà]tic|earth observation|observaci[oó]n de la tierra|PPGIS|"
        r"fernerkundung|geoinformati|kartograph|erdbeobachtung|"
        r"kartograf|teledetekc|geoinformac|geoinformatyk|dálkov\w* průzkum|teledetec[tț]i|sisteme informatice geografice|"
        r"co[gğ]rafi bilgi sistem|uzaktan alg[ıi]lama|\bCBS\b",
        re.I,
    ),
    "Mobility & transport": re.compile(
        r"urban mobility|movilidad urbana|mobilitat urbana|sustainable mobility|movilidad sostenible|mobilitat sostenible|"
        r"transport planning|planificaci[oó]n del transporte|planificaci[oó] del transport|public transport|transporte p[uú]blico|"
        r"transport p[uú]blic|active mobility|movilidad activa|cycling|ciclismo urbano|walkability|caminabilidad|"
        r"travel behaviou?r|accessibility (analysis|planning|to)|accesibilidad (urbana|territorial)|"
        r"verkehrsplanung|mobilit[aä]tsforschung|verkehrswende|mobilit[aä]tswende|nachhaltige mobilit[aä]t|"
        r"st[aä]dtische mobilit[aä]t|mobilno[sś][cć] miejsk|transport\w* publiczn|komunikacj\w* miejsk|"
        r"městsk\w* mobilit|veřejn\w* doprav|udržiteln\w* mobilit|mobilitate urban|transport public|"
        r"kentsel ula[sş][ıi]m|toplu ta[sş][ıi]ma|s[üu]rd[üu]r[üu]lebilir ula[sş][ıi]m", re.I),
    "Heritage": re.compile(r"architectural heritage|built heritage|patrimonio (arquitect|construido|urbano)|patrimoni (arquitect|construït|urb)", re.I),
    "Climate & risk": re.compile(
        r"climate (change )?adaptation|adaptaci[oó]n al cambio clim|adaptaci[oó] al canvi clim|flood risk|riesgo de inundaci|"
        r"risc d'inundaci|natural hazards|riesgos naturales|urban heat|isla de calor|illa de calor|heat island|"
        r"climate resilien|urban resilien|resiliencia (urbana|clim)|resili[eè]ncia (urbana|clim)|risk perception|percepci[oó]n del riesgo|"
        r"hochwasser|starkregen|klima(wandel)?anpassung|naturgefahren|risikowahrnehmung|katastrophenschutz|"
        r"hitzevorsorge|klimaresilienz|disaster risk|"
        r"ryzyk\w* powodziow|pow[oó]d[zź]|powodzi|adaptacj\w* do zmian\w* klimatu|zagro[zż]e\w* naturaln|wysp\w* ciep[lł]a|"
        r"povod(e[nň]|n[ěií])|adaptac\w* na změn\w* klimatu|přírodní\w* rizik|tepeln\w* ostrov|"
        r"inunda[tț]i|adaptare(a)? la schimb[aă]ri(le)? climatic|hazard\w* natural|insul\w* de c[aă]ldur|"
        r"ta[sş]k[ıi]n|iklim de[gğ]i[sş]ikli[gğ]ine uyum|afet risk|deprem risk|do[gğ]al afet|kentsel [ıi]s[ıi] adas",
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
    # de
    "januar": 1, "jänner": 1, "februar": 2, "märz": 3, "maerz": 3, "mai": 5, "juni": 6, "juli": 7,
    "oktober": 10, "dezember": 12,
    # pl (genitive and nominative)
    "stycznia": 1, "styczeń": 1, "lutego": 2, "luty": 2, "marca": 3, "marzec": 3, "kwietnia": 4, "kwiecień": 4,
    "maja": 5, "maj": 5, "czerwca": 6, "czerwiec": 6, "lipca": 7, "lipiec": 7, "sierpnia": 8, "sierpień": 8,
    "września": 9, "wrzesień": 9, "października": 10, "październik": 10, "listopada": 11, "listopad": 11,
    "grudnia": 12, "grudzień": 12,
    # cs
    "ledna": 1, "leden": 1, "února": 2, "únor": 2, "března": 3, "březen": 3, "dubna": 4, "duben": 4,
    "května": 5, "květen": 5, "června": 6, "červen": 6, "července": 7, "červenec": 7, "srpna": 8, "srpen": 8,
    "září": 9, "října": 10, "říjen": 10, "listopadu": 11, "prosince": 12, "prosinec": 12,
    # ro
    "ianuarie": 1, "februarie": 2, "martie": 3, "aprilie": 4, "iunie": 6, "iulie": 7, "septembrie": 9,
    "octombrie": 10, "noiembrie": 11, "decembrie": 12,
    # tr (dotless ı written as i here; see _mon_key)
    "ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4, "mayis": 5, "haziran": 6, "temmuz": 7,
    "ağustos": 8, "agustos": 8, "eylül": 9, "eylul": 9, "ekim": 10, "kasim": 11, "aralik": 12,
}


def _mon_key(s: str) -> str:
    """Month name as a MONTHS key: lower case, Turkish dotted/dotless i folded to i."""
    return s.lower().replace("\u0307", "").replace("ı", "i")


MONTHS = {_mon_key(k): v for k, v in MONTHS.items()}
_MON = "|".join(k.replace("i", "[iıİI]") for k in sorted(MONTHS, key=len, reverse=True))
DATE_PATTERNS = [
    (re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](20\d{2})\b"), lambda m: (int(m[3]), int(m[2]), int(m[1]))),
    (re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b"), lambda m: (int(m[1]), int(m[2]), int(m[3]))),
    (re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th|\.)?\s+(?:de\s+|d'|of\s+)?({_MON})\s*,?\s+(?:de\s+|del\s+)?(20\d{{2}})\b", re.I),
     lambda m: (int(m[3]), MONTHS[_mon_key(m[2])], int(m[1]))),
    (re.compile(rf"\b({_MON})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(20\d{{2}})\b", re.I), lambda m: (int(m[3]), MONTHS[_mon_key(m[1])], int(m[2]))),
    # Czech style "6. 12. 2025"
    (re.compile(r"\b(\d{1,2})\.\s(\d{1,2})\.\s?(20\d{2})\b"), lambda m: (int(m[3]), int(m[2]), int(m[1]))),
]
DEADLINE_CUE = re.compile(
    r"deadline|closing date|apply (by|before)|application period|until|plazo|fecha l[ií]mite|fin de plazo|hasta el|"
    r"termini|data l[ií]mit|fins al|fins el|finaliza|fecha de cierre|cierre|solicitud:|solicitudes|sol·licituds|"
    r"presentaci[oó]n? de (solicitudes|sol·licituds)|applications?:|"
    r"bewerbungsfrist|bewerbungsschluss|bewerbungen (bitte )?bis|bis (zum|sp[aä]testens)|einsendeschluss|"
    r"ende der bewerbungsfrist|frist:|application deadline|closing date|"
    # pl / cs / ro / tr
    r"termin\w* (sk[lł]adania|nadsy[lł]ania|zg[lł]osze|aplikacj)|do dnia|ostateczny termin|nieprzekraczaln|"
    r"uz[aá]v[eě]rk|term[ií]n\w* (pro )?(pod[aá]n[ií]|p[rř]ihl[aá][sš]|odevzd|doru[cč]en)|p[rř]ihl[aá][sš]k\w* .{0,40}do|nejpozd[eě]ji do|"
    r"termen(ul)? limit|data limit|p[aâ]n[aă] la data de|p[aâ]n[aă] la|depunere\w* dosarelor|[iî]nscrier\w*|"
    r"son ba[sş]vuru|ba[sş]vuru (tarih|s[üu]resi|biti[sş])|ba[sş]vurular",
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


_NUM_WORDS = {"tres": 3, "three": 3, "cinc": 5, "cinco": 5, "five": 5, "set": 7, "siete": 7, "seven": 7,
              "deu": 10, "diez": 10, "ten": 10, "quinze": 15, "quince": 15, "fifteen": 15,
              "vint": 20, "veinte": 20, "twenty": 20, "trenta": 30, "treinta": 30, "thirty": 30}
_RELATIVE = re.compile(
    r"\b(\d{1,2}|" + "|".join(_NUM_WORDS) + r")\s*(?:\(\d{1,2}\)\s*)?"
    r"(d[ií]as?|dies|days)\s+(h[aà]bils|h[aá]biles|laborables|naturals|naturales|working|business|calendar)",
    re.I,
)


def relative_deadline(text: str) -> str | None:
    """Estimate deadlines written as 'N working days from publication'.

    Base date: the latest date in the document that is not in the future (usually the signature
    or publication date). Working days are converted at 7/5 plus two days' margin.
    """
    m = _RELATIVE.search(text)
    if not m:
        return None
    n = m[1].lower()
    n = int(n) if n.isdigit() else _NUM_WORDS.get(n)
    if not n or n > 60:
        return None
    today = date.today()
    past = [d for _, d in _dates(text) if d <= today]
    if not past:
        return None
    base = max(past)
    working = not re.match(r"natural|calendar", m[3], re.I)
    days = round(n * 7 / 5) if working else n
    from datetime import timedelta
    return (base + timedelta(days=days + 2)).isoformat()


_STATUS = re.compile(
    r"\b(estat|estado|status|situaci[oó]n?|state)\s*(?:de la convocat[oò]ria|de la oferta|of the call)?\s*:?\s*"
    r"(oberta|obert|abierta|open|tancada|tancat|cerrada|closed|resolta|resuelta|resolved|"
    r"en avaluaci[oó]|en evaluaci[oó]n|finalitzada|finalizada|adjudicada)\b",
    re.I,
)


def page_status(text: str) -> str | None:
    """'open' or 'closed' when the offer page states its status explicitly."""
    m = _STATUS.search(text)
    if not m:
        return None
    return "open" if re.match(r"obert|oberta|abierta|open", m[2], re.I) else "closed"
