"""Find candidate job pages for every institution in sources/institutions.yaml.

Writes data/discovery.json: for each institution, robots status, the known job pages'
health, and a ranked list of candidate pages found by following job-related links
from the homepage (two levels deep, same site only).
"""
from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit

import yaml
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
from fetch import Blocked, fetch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

NAV_WORDS = re.compile(
    r"empleo|ofertas?|trabaj|treball|trebal|lan eskaintza|work with us|work at|careers?|jobs?|"
    r"convocatori|personal investigador|personal docente|\bpdi\b|\bpi\b|selecci|contrataci|contractaci|"
    r"recursos humanos|recursos humans|human resources|hrs4r|talent|sede electr|seu electr|"
    r"investigaci[oó]n|recerca|research",
    re.I,
)
JOB_WORDS = re.compile(
    r"predoctoral|postdoctoral|post-doctoral|posdoctoral|postdoc|ph\.?d|doctorand|doctoral|"
    r"investigador[a]? doctor|personal investigador|research(er)? (position|staff|assistant|fellow)|"
    r"\bR1\b|\bR2\b|juan de la cierva|ram[oó]n y cajal|margarita salas|\bfpi\b|\bfpu\b|"
    r"contrat[oa]s? .*proyecto|contracte.*projecte|plazas? de investigaci|oferta de trabajo",
    re.I,
)
MAX_CANDIDATES_L1 = 10
MAX_CANDIDATES_L2 = 12


def same_site(url: str, home: str) -> bool:
    def base(h: str) -> str:
        parts = h.lower().split(":")[0].split(".")
        return ".".join(parts[-2:])
    return base(urlsplit(url).netloc) == base(urlsplit(home).netloc)


def links(html: str, base_url: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        url = urldefrag(urljoin(base_url, href))[0]
        text = " ".join(a.get_text(" ").split())[:150]
        out.append((url, text))
    return out


def page_score(html: str) -> tuple[int, int]:
    text = BeautifulSoup(html, "lxml").get_text(" ")
    return len(JOB_WORDS.findall(text)), len(text)


def probe_page(url: str) -> dict:
    try:
        r = fetch(url)
        ctype = r.headers.get("Content-Type", "")
        info = {"url": url, "final_url": r.url, "status": r.status_code, "type": ctype.split(";")[0]}
        if "html" in ctype:
            hits, size = page_score(r.text)
            info.update(job_word_hits=hits, text_chars=size)
            info["_html"] = r.text
        return info
    except Blocked:
        return {"url": url, "blocked_by_robots": True}
    except Exception as e:  # noqa: BLE001
        return {"url": url, "error": f"{type(e).__name__}: {e}"[:200]}


def discover(inst: dict) -> dict:
    home = inst["homepage"]
    result = {"id": inst["id"], "name": inst["name"], "homepage": home, "known": [], "candidates": []}

    for url in inst.get("job_pages", []):
        info = probe_page(url)
        info.pop("_html", None)
        result["known"].append(info)

    home_info = probe_page(home)
    result["home"] = {k: v for k, v in home_info.items() if k != "_html"}
    html = home_info.get("_html")
    if not html:
        return result

    seen = {home, home_info.get("final_url")}
    level1 = []
    for url, text in links(html, home_info["final_url"]):
        if url in seen or not same_site(url, home) or url.lower().endswith((".pdf", ".doc", ".docx", ".jpg", ".png")):
            continue
        if NAV_WORDS.search(text) or NAV_WORDS.search(urlsplit(url).path):
            seen.add(url)
            level1.append((url, text))
    candidates = []
    for url, text in level1[:MAX_CANDIDATES_L1]:
        info = probe_page(url)
        info["link_text"] = text
        info["level"] = 1
        sub = info.pop("_html", None)
        candidates.append(info)
        if sub:
            for u2, t2 in links(sub, info["final_url"]):
                if u2 in seen or not same_site(u2, home) or u2.lower().endswith((".pdf", ".doc", ".docx")):
                    continue
                if JOB_WORDS.search(t2) or (NAV_WORDS.search(t2) and re.search(r"investig|recerca|research|pdi|\bpi\b", t2, re.I)):
                    seen.add(u2)
                    candidates.append({"url": u2, "link_text": t2, "level": 2, "_pending": True})
    level2 = [c for c in candidates if c.get("_pending")][:MAX_CANDIDATES_L2]
    for c in level2:
        info = probe_page(c["url"])
        info.pop("_html", None)
        c.update(info)
        c.pop("_pending")
    candidates = [c for c in candidates if not c.get("_pending")]
    candidates.sort(key=lambda c: c.get("job_word_hits", -1), reverse=True)
    result["candidates"] = candidates
    return result


def main() -> None:
    insts = yaml.safe_load((ROOT / "sources/institutions.yaml").read_text(encoding="utf-8"))
    only = set(sys.argv[1:])
    if only:
        insts = [i for i in insts if i["id"] in only]
    with ThreadPoolExecutor(max_workers=24) as pool:
        results = list(pool.map(discover, insts))
    out = ROOT / "data/discovery.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"generated": datetime.now(timezone.utc).isoformat(), "institutions": results},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    ok = sum(1 for r in results if r.get("home", {}).get("status") == 200)
    print(f"{len(results)} institutions, homepage reachable: {ok}")


if __name__ == "__main__":
    main()
