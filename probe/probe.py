"""Temporary probe: fetch candidate source pages from the GitHub runner and save raw responses."""
import json
import re
import pathlib
import urllib.request

URLS = {
    "upc_r1": "https://talenthub.upc.edu/en/jobs/r1",
    "upc_r2": "https://talenthub.upc.edu/en/jobs/r2",
    "upc_jobs": "https://talenthub.upc.edu/en/jobs",
    "upm_hrs4r": "https://web.upm.es/hrs4r/",
    "ub_seu_pdi": "https://seu.ub.edu/ofertaPublicaCategoriaPublic/categories/personaldocent?lang=en",
    "ub_seu_root": "https://seu.ub.edu/ofertaPublicaCategoriaPublic/categories?lang=en",
    "upv_empleo": "https://www.upv.es/empleopublico",
    "us_inv": "https://investigacion.us.es/",
    "ugr_inv_personal": "https://investigacion.ugr.es/personal",
    "dogv_home": "https://dogv.gva.es/es/",
    "dogv_opendata": "https://dogv.gva.es/es/datos-abiertos",
    "boja_home": "https://www.juntadeandalucia.es/eboja.html",
    "boja_rss": "https://www.juntadeandalucia.es/boja/distribucion/boja.xml",
    "dogc_portal": "https://portaldogc.gencat.cat/",
    "dogc_opendata": "https://analisi.transparenciacatalunya.cat/resource/n6hn-rmy7.json?$limit=5",
    "bocm_home": "https://www.bocm.es/",
    "bocm_rss": "https://www.bocm.es/boletines.rss",
}
for host in sorted({re.match(r"https://[^/]+", u).group(0) for u in list(URLS.values())}):
    URLS["robots_" + host.split("//")[1]] = host + "/robots.txt"

UA = "PositionFinderBot/0.1 (+https://github.com/Positionfinder/Position_Finder)"
out = pathlib.Path("probe/out")
out.mkdir(parents=True, exist_ok=True)
summary = {}
for name, url in URLS.items():
    headers = {"User-Agent": UA, "Accept": "application/json" if "opendata" in name else "text/html,application/xml,*/*"}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=40) as r:
            body = r.read()
            summary[name] = {"url": url, "status": r.status, "final_url": r.geturl(),
                             "type": r.headers.get("Content-Type"), "bytes": len(body)}
            (out / f"{name}.txt").write_bytes(body)
    except Exception as e:  # noqa: BLE001
        summary[name] = {"url": url, "error": repr(e)}
(out / "summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
