"""Add English titles (title_en) to docs/data/jobs.json.

Offline machine translation with Argos Translate (Spanish, Catalan, German -> English).
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


def language(title: str, country: str) -> str:
    words = max(1, len(title.split()))
    en = len(EN_WORDS.findall(title))
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


def prepare(title: str, lang: str) -> str:
    if lang == "de":
        title = DE_ASSOC.sub("Research associate", title)
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
        elif it["title"] in cache:
            it["title_en"] = tidy(cache[it["title"]])
        else:
            todo.setdefault(lang, []).append(it)
    if todo:
        translators = load_translators(set(todo))
        for lang, items in todo.items():
            tr = translators.get(lang)
            for it in items:
                if tr:
                    try:
                        en = tidy(tr(prepare(it["title"], lang)).strip())
                        cache[it["title"]] = en
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
