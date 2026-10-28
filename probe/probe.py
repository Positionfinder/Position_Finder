"""Temporary probe: fetch candidate source pages from the GitHub runner and save raw responses."""
import json
import pathlib
import urllib.request

URLS = {
    "euraxess_search": "https://euraxess.ec.europa.eu/jobs/search",
    "euraxess_kw": "https://euraxess.ec.europa.eu/jobs/search?keywords=urban%20planning",
    "euraxess_rss": "https://euraxess.ec.europa.eu/jobs/search/rss",
    "euraxess_feed": "https://euraxess.ec.europa.eu/jobs/feed",
    "boe_sumario": "https://www.boe.es/datosabiertos/api/boe/sumario/20261027",
    "csic_empleo": "https://www.csic.es/es/empleo",
}

UA = "PositionFinderBot/0.1 (+https://github.com/Positionfinder/Position_Finder)"
out = pathlib.Path("probe/out")
out.mkdir(parents=True, exist_ok=True)
summary = {}
for name, url in URLS.items():
    headers = {"User-Agent": UA, "Accept": "application/json" if "boe" in name else "text/html,application/xml,*/*"}
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
