"""Add English titles (title_en) to docs/data/jobs.json.

Offline machine translation with Argos Translate (Spanish, Catalan, German, Polish, Czech, Romanian,
Turkish -> English).
Translations are cached in data/translations.json, so each title is translated only once.
If a language model can't be installed, the original title is kept.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JOBS = ROOT / "docs/data/jobs.json"
CACHE = ROOT / "data/translations.json"

EN_WORDS = re.compile(r"\b(the|and|of|for|in|with|on|researcher|research|position|postdoctoral|university|project|"
                      r"associate|fellow|call|scientist|department|group|data|urban|planning)\b", re.I)
CA_WORDS = re.compile(r"\b(i|dels?|per a|amb|l'|d'un|d'una|recerca|investigador/a|contractaci[oó]|convocat[oò]ria|"
                      r"departament|projecte|ci[oó]\b)|\w+ci[oó]\b", re.I)
ES_WORDS = re.compile(r"\b(y|del|para|con|de la|investigaci[oó]n|contrato|convocatoria|departamento|proyecto)\b", re.I)
DE_WORDS = re.compile(r"\b(und|der|die|das|f[uü]r|mit|im|zur|wissenschaftliche|mitarbeiter|stelle|projekt)\b", re.I)


COUNTRY_LANG = {"PL": "pl", "CZ": "cs", "RO": "ro", "TR": "tr"}


def language(title: str, country: str) -> str:
    words = max(1, len(title.split()))
    en = len(EN_WORDS.findall(title))
    if country in COUNTRY_LANG:
        return "en" if en / words > 0.25 else COUNTRY_LANG[country]
    if country == "DE":
        de = len(DE_WORDS.findall(title))
        return "en" if en > de and en / words > 0.15 else "de"
    ca, es = len(CA_WORDS.findall(title)), len(ES_WORDS.findall(title))
    if en > max(ca, es) and en / words > 0.15:
        return "en"
    return "ca" if ca > es else "es"


def load_translators(langs: set[str]):
    try:
        import argostranslate.package
        import argostranslate.translate
    except ImportError:
        print("argostranslate not installed; titles stay in the original language")
        return {}
    argostranslate.package.update_package_index()
    available = argostranslate.package.get_available_packages()
    installed = {(p.from_code, p.to_code) for p in argostranslate.package.get_installed_packages()}
    out = {}
    for lang in langs:
        if (lang, "en") not in installed:
            pkg = next((p for p in available if p.from_code == lang and p.to_code == "en"), None)
            if pkg is None:
                print(f"no Argos model {lang}->en")
                continue
            argostranslate.package.install_from_path(pkg.download())
        out[lang] = lambda text, lang=lang: argostranslate.translate.translate(text, lang, "en")
    if "ca" not in out and "es" in out:
        out["ca"] = out["es"]  # Catalan titles are mostly readable through the Spanish model
    return out


DE_ASSOC = re.compile(r"(wissenschaftliche|akademische|wiss\.)\S{0,4}\s*(mitarbeiter|besch[aä]ftigte)\S*"
                      r"(\s*(bzw\.|oder|/)\s*(wissenschaftliche|akademische)?\S{0,4}\s*(mitarbeiter|besch[aä]ftigte)\S*)?", re.I)
EN_FIX = [(re.compile(r"\b(academic|scientific|science) (employee|staff member|collaborator|worker)s?\b", re.I), "Research associate"),
          (re.compile(r"\bknow\. employee\b", re.I), "Research associate")]


# Academic ranks the translation models get wrong ("Adiunkt lub adiunktka" -> "Assistant or Assistant").
RANKS = {
    "pl": [(re.compile(r"\badiunkt\w*(\s*(\(post-?doc\))?\s*(lub|/|i)\s*adiunkt\w*)?(\s*\(post-?doc\))?", re.I), "Assistant Professor"),
           (re.compile(r"\bbadacz\w*(\s*(lub|/)\s*badacz\w*)?", re.I), "Researcher")],
    "cs": [(re.compile(r"odborn[ýá]\w* asistent\w*(\s*/\s*odborn[áý]\w* asistent\w*)?", re.I), "Assistant Professor"),
           (re.compile(r"postdoktorand\w*(\s*/\s*postdoktorand\w*)?", re.I), "Postdoctoral researcher")],
    "ro": [(re.compile(r"lector universitar", re.I), "Lecturer (lector universitar)"),
           (re.compile(r"cercet[aă]tor\w* [sș]tiin[tț]ific\w*( \(?post-?doctorand\)?)?", re.I), "Research scientist")],
    "tr": [(re.compile(r"dr\.? ?[öo][gğ]r(etim|\.)? ?[üu]yesi|doktor [öo][gğ]retim [üu]yesi", re.I), "Assistant Professor"),
           (re.compile(r"doktora sonras[ıi] ara[sş]t[ıi]rmac[ıi]", re.I), "Postdoctoral researcher")],
}


def prepare(title: str, lang: str) -> str:
    if lang == "de":
        title = DE_ASSOC.sub("Research associate", title)
    has_postdoc = re.search(r"post-?doc", title, re.I)
    for pat, rep in RANKS.get(lang, []):
        title = pat.sub(rep, title)
    if lang == "pl" and has_postdoc and "post-doc" not in title.lower():
        title = title.replace("Assistant Professor", "Postdoc", 1)
    return title


def tidy(en: str) -> str:
    for pat, rep in EN_FIX:
        en = pat.sub(rep, en)
    return en


def main() -> None:
    data = json.loads(JOBS.read_text(encoding="utf-8"))
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    todo = {}
    for it in data["items"]:
        if it["kind"] == "call":
            it["title_en"] = it["title"]
            continue
        lang = language(it["title"], it.get("country", "ES"))
        if lang == "en":
            it["title_en"] = it["title"]
        elif it["title"] in cache and lang not in RANKS:
            it["title_en"] = tidy(cache[it["title"]])
        elif prepare(it["title"], lang) in cache:
            it["title_en"] = tidy(cache[prepare(it["title"], lang)])
        else:
            todo.setdefault(lang, []).append(it)
    if todo:
        translators = load_translators(set(todo))
        for lang, items in todo.items():
            tr = translators.get(lang)
            for it in items:
                if tr:
                    try:
                        src = prepare(it["title"], lang)
                        en = tidy(tr(src).strip())
                        cache[src if lang in RANKS else it["title"]] = en
                        it["title_en"] = en
                        continue
                    except Exception as e:  # noqa: BLE001
                        print("translation failed:", e)
                it["title_en"] = it["title"]
    # keep the cache to titles still in use plus recent ones (bounded)
    if len(cache) > 5000:
        keep = {it["title"] for it in data["items"]}
        cache = {k: v for k, v in cache.items() if k in keep}
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    JOBS.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"translated {sum(len(v) for v in todo.values())} new titles")


if __name__ == "__main__":
    main()
