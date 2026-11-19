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
        r"participaci[oó] ciutadana", r"b[uü]rgerbeteiligung", r"[oö]ffentlichkeitsbeteiligung", r"beteiligungs(verfahren|prozess|formate)", r"partizipati", r"stakeholder engagement",
        r"living ?labs?", r"transdisciplinar", r"\bparticipatory\b", r"participativ", r"co-?creaci[oó]",
        r"tallers? participatius", r"talleres participativos", r"actores locales", r"agents locals", r"local stakeholders",
        r"zivilgesellschaft", r"civil society", r"sociedad civil", r"societat civil", r"multi-?stakeholder",
        r"stakeholder-?(workshop|dialog|prozess)", r"prozessmoderation", r"akteurs(beteiligung|einbindung)"]),
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
        r"natural hazard", r"coastal (zone|change|risk|adaptation)", r"zonas? costeras?", r"costa mediterr", r"k[uü]stenschutz"]),
    "spatial_justice": ("Spatial & environmental justice", [
        r"spatial justice", r"environmental justice", r"justicia (espacial|ambiental)", r"just[ií]cia (espacial|ambiental)",
        r"umweltgerechtigkeit", r"(socio-?)?spatial inequalit", r"segregation", r"social vulnerab", r"socio-?spatial",
        r"socioespacial", r"just transition", r"inclusive (city|cities|planning)"]),
    "urban_growth": ("Urbanization & land-use change", [
        r"urbani[sz]ation", r"urban (growth|expansion|sprawl)", r"land[- ]use change", r"land[- ]use (and|&) land[- ]cover",
        r"crecimiento urbano", r"expansi[oó]n urbana", r"siedlungsentwicklung", r"fl[aä]chen(inanspruchnahme|verbrauch)",
        r"suburbani", r"peri-?urban"]),
    "gis_rs": ("GIS, remote sensing & spatial analysis", [
        r"CS:\b(?:Open|Web)?GIS\b", r"CS:\bSIG\b", r"sistemas? de informaci[oó]n geogr", r"sistemes? d'informaci[oó] geogr", r"geographic(al)? information", r"remote sensing", r"teledetec", r"fernerkundung",
        r"earth observation", r"satellite (data|imag)", r"\blandsat", r"\bsentinel-?\d", r"geospatial", r"geoespacial",
        r"spatial (analysis|data|model)", r"an[aá]lisis espacial", r"geodaten", r"geoinformati", r"\bqgis\b", r"\barcgis\b"]),
    "urban_planning": ("Urban & spatial planning", [
        r"urban planning", r"spatial planning", r"regional planning", r"town planning", r"city planning", r"urbanism",
        r"planificaci[oó]n (urbana|territorial)", r"planificaci[oó] (urbana|territorial)", r"ordenaci[oó]n? del territori",
        r"stadtplanung", r"raumplanung", r"regionalplanung", r"st[aä]dtebau", r"stadtentwicklung", r"raumentwicklung",
        r"urban development", r"desarrollo urbano", r"urban design", r"dise[nñ]o urbano", r"urban systems",
        r"sistemas urbanos", r"sistemes urbans", r"territorial (analysis|planning|development)", r"an[aà]lisis territorial",
        r"an[aà]lisi territorial", r"raumanalyse", r"stadtgestalt", r"urban regeneration", r"regeneraci[oó]n urbana",
        r"regenerative (urban|stadt)", r"stadtumbau", r"quartiersentwicklung", r"new european bauhaus", r"urban renewal"]),
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
    "mobility": ("Sustainable mobility & accessibility", [
        r"sustainable mobility", r"mobilitat sostenible", r"movilidad sostenible", r"nachhaltige mobilit", r"accessibility",
        r"accesibilidad", r"accessibilitat", r"erreichbarkeit", r"cycling", r"bicycle", r"bicicleta", r"active (mobility|travel)",
        r"public transport", r"transporte p[uú]blico", r"mobility (burden|justice|poverty)", r"verkehrswende", r"mobilit[aä]tswende"]),
    "geography": ("Geography", [
        r"geograf", r"geograph", r"humangeograph", r"territorial (analysis|studies)", r"an[aà]lisi territorial"]),
    "tourism": ("Tourism & heritage", [
        r"touris", r"turism", r"turisme", r"cultural heritage", r"patrimonio cultural", r"patrimoni cultural"]),
    "global_south": ("Global South & comparative studies", [
        r"global south", r"developing countr", r"\bafrica", r"latin america", r"middle east", r"\biran\b", r"colombia",
        r"comparative (case|stud|urban)", r"international development"]),
}

# Polish, Czech, Romanian and Turkish vocabulary for the same topics (added Nov 2026 with PL/CZ/RO/TR).
_EXTRA: dict[str, list[str]] = {
    "ppgis": [r"partycypacyjn\w* (gis|mapowani)", r"mapowani\w* partycypacyjn", r"participativn\w* mapov[aá]n",
              r"cartografiere participativ", r"kat[ıi]l[ıi]mc[ıi] (cbs|haritalama)", r"nauk\w* obywatelsk", r"občansk\w* věd"],
    "participation": [r"partycypac", r"konsultacj\w* społeczn", r"participac", r"zapojen\w* veřejnosti",
                      r"participare (public|cet[aă][tț]eneasc)", r"implicare(a)? comunit", r"kat[ıi]l[ıi]mc[ıi]",
                      r"vatanda[sş] kat[ıi]l[ıi]m", r"payda[sş]"],
    "risk_perception": [r"percepcj\w* ryzyk", r"postrzegani\w* ryzyk", r"vn[ií]m[aá]n[ií]\w* rizik", r"percep[tț]i\w* risc",
                        r"risk alg[ıi]s"],
    "tech_risk": [r"ryzyk\w* (przemys[lł]ow|technologiczn)", r"pr[uů]myslov\w* rizik", r"risc\w* (tehnologic|industrial)",
                  r"(end[üu]striyel|teknolojik) risk", r"petrokimya"],
    "flood": [r"pow[oó]d[zź]", r"powodzi", r"povod(e[nň]|n[ěií]|í)", r"inunda[tț]i", r"ta[sş]k[ıi]n", r"\bsel (riski|bask)",
              r"retencj\w* wód", r"zadržov[aá]n[ií] vody"],
    "ecosystem_services": [r"us[lł]ug\w* ekosystem", r"ekosyst[eé]mov\w* služ", r"servicii(le)? ecosistemic", r"ekosistem hizmet",
                           r"rozwi[aą]za\w* oparte na przyrodzie", r"p[rř][ií]rod[eě] bl[ií]zk\w* [rř]e[sš]en", r"solu[tț]ii bazate pe natur",
                           r"do[gğ]a temelli [cç][öo]z[üu]m", r"kapita[lł]\w* naturaln"],
    "green_health": [r"ziele[nń]\w* miejsk", r"teren\w* zieleni", r"zielon\w* infrastruktur", r"zdrowi\w* psychiczn", r"dobrostan",
                     r"m[eě]stsk\w* zele", r"zelen\w* infrastruktur", r"du[sš]evn[ií]\w* zdrav", r"spa[tț]ii verzi",
                     r"infrastructur\w* verde", r"s[aă]n[aă]tate(a)? mintal", r"ye[sş]il (alan|altyap)", r"ruh sa[gğ]l[ıi][gğ]"],
    "landscape": [r"krajobraz", r"krajin", r"peisaj", r"peyzaj"],
    "resilience": [r"adaptacj\w* do zmian\w* klimatu", r"rezylienc", r"adaptac\w* na zm[eě]n\w* klimatu", r"rezilienc",
                   r"adaptare(a)? la schimb[aă]ri", r"rezilien[tț]", r"iklim de[gğ]i[sş]ikli[gğ]ine uyum", r"diren[cç]lilik",
                   r"afet risk", r"deprem", r"wysp\w* ciep[lł]a", r"tepeln\w* ostrov", r"insul\w* de c[aă]ldur", r"[ıi]s[ıi] adas"],
    "spatial_justice": [r"sprawiedliwo[sś]\w* (przestrzenn|środowiskow)", r"segregac", r"wykluczeni\w* społeczn",
                        r"prostorov\w* spravedlnost", r"soci[aá]ln\w* vylou[cč]en", r"justi[tț]i\w* (spa[tț]ial|de mediu)", r"segrega",
                        r"mek[aâ]nsal adalet", r"[cç]evresel adalet", r"ayr[ıi][sş]ma"],
    "urban_growth": [r"urbanizac", r"suburbanizac", r"rozlewani\w* si[eę] miast", r"zmian\w* (u[zż]ytkowania|pokrycia) terenu",
                     r"zm[eě]n\w* vyu[zž]it[ií] [uú]zem", r"urbaniz[aă]r", r"expansiune(a)? urban", r"extindere(a)? urban",
                     r"kentle[sş]me", r"kentsel yay[ıi]lma", r"arazi kullan[ıi]m"],
    "gis_rs": [r"teledetekc", r"geoinformac", r"geoinformatyk", r"analiz\w* przestrzenn", r"system\w* informacji (geograficzn|przestrzenn)",
               r"d[aá]lkov\w* pr[uů]zkum", r"prostorov\w* anal[yý]z", r"geografick\w* informa[cč]n", r"teledetec[tț]i",
               r"sisteme(le)? informatic\w* geografic", r"analiz[aă] spa[tț]ial", r"uzaktan alg[ıi]lama", r"co[gğ]rafi bilgi sistem",
               r"CS:\bCBS\b", r"mek[aâ]nsal analiz", r"kartograf"],
    "urban_planning": [r"planowani\w* przestrzenn", r"gospodark\w* przestrzenn", r"urbanistyk", r"rozw[oó]j\w* (miast|regionaln|lokaln)",
                       r"rewitalizac", r"polityk\w* miejsk", r"zagospodarowani\w* przestrzenn", r"architektur\w* i urbanistyk",
                       r"[uú]zemn[ií]\w* pl[aá]nov[aá]n", r"region[aá]ln[ií]\w* rozvoj", r"rozvoj\w* m[eě]st", r"urbanismus",
                       r"amenaj\w* (a )?teritori", r"planificar\w* (urban|spa[tț]ial|teritorial)", r"dezvoltar\w* (urban|regional|teritorial)",
                       r"regenerar\w* urban", r"[sş]ehir (ve b[oö]lge )?planlama", r"kentsel (planlama|tasar[ıi]m|d[oö]n[üu][sş][üu]m)",
                       r"b[oö]lge planlama", r"mek[aâ]nsal planlama", r"kent planlama"],
    "informal": [r"uchod[zź]c", r"uprchl", r"neform[aá]ln\w* os[ií]dlen", r"refugia", r"a[sș]ez[aă]ri informale", r"gecekondu",
                 r"m[üu]lteci", r"g[oö][cç]men", r"informel yerle[sş]im"],
    "housing": [r"mieszkalnictw", r"mieszkaniow", r"bydlen[ií]", r"bytov\w* (politik|v[yý]stavb|fond)", r"locuin[tț]", r"locuire",
                r"\bkonut"],
    "governance": [r"zarz[aą]dzani\w* (miast|rozwojem)", r"polityk\w* publiczn", r"ve[rř]ejn\w* politik", r"spr[aá]v\w* m[eě]st",
                   r"guvernan[tț]", r"politici publice", r"y[öo]neti[sş]im", r"kamu politika"],
    "digital_ai": [r"sztuczn\w* inteligencj", r"uczeni\w* maszynow", r"inteligentn\w* miast", r"um[eě]l[aáé]\w* inteligenc",
                   r"strojov\w* u[cč]en", r"chytr\w* m[eě]st", r"inteligen[tț][aă] artificial", r"ora[sș]e inteligente",
                   r"yapay zek[aâ]", r"makine [öo][gğ]renme", r"ak[ıi]ll[ıi] (kent|[sş]ehir)"],
    "sdg": [r"zr[oó]wnowa[zż]on\w* rozw", r"udr[zž]iteln\w* rozvoj", r"dezvoltare(a)? durabil", r"s[üu]rd[üu]r[üu]lebilir kalk[ıi]nma"],
    "mcda": [r"wielokryterialn", r"v[ií]cekriteri[aá]ln", r"multicriteri", r"[cç]ok kriterli"],
    "survey_methods": [r"ankiet", r"wywiad\w* (pog[lł][eę]bion|jako[sś]ciow)", r"dotazn[ií]k", r"chestionar", r"\banchet",
                       r"\banket", r"metod\w* mieszan"],
    "mobility": [r"dost[eę]pno[sś][cć] (przestrzenn|transport)", r"transport\w* publiczn", r"mobilno[sś][cć] (miejsk|zr[oó]wnowa)",
                 r"dostupnost", r"ve[rř]ejn\w* doprav", r"udr[zž]iteln\w* mobilit", r"accesibilitat", r"mobilitate(a)? urban",
                 r"transport(ul)? public", r"eri[sş]ilebilirlik", r"toplu ta[sş][ıi]ma", r"kentsel ula[sş][ıi]m", r"bisiklet"],
    "geography": [r"co[gğ]rafya"],
    "tourism": [r"turystyk", r"cestovn[ií]\w* ruch", r"turizm", r"dziedzictw\w* kulturow", r"kulturn[ií]\w* d[eě]dictv",
                r"patrimoniu(l)? cultural", r"k[üu]lt[üu]rel miras"],
    "global_south": [r"globaln\w* południ", r"globáln[ií]\w* jih", r"sudul global", r"k[üu]resel g[üu]ney"],
}
for _tid, _pats in _EXTRA.items():
    TOPICS[_tid][1].extend(_pats)

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
