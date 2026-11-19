"""Probe helper: fetch URLs (robots respected) and save HTML/text + robots status to probe_out/."""
import hashlib, json, sys
from pathlib import Path
sys.path.insert(0, "collector")
from fetch import Blocked, fetch
from bs4 import BeautifulSoup
out = Path("probe_out"); out.mkdir(exist_ok=True)
res = []
for url in [u.strip() for u in Path("tools/probe/urls.txt").read_text().splitlines() if u.strip() and not u.startswith("#")]:
    h = hashlib.sha1(url.encode()).hexdigest()[:10]
    try:
        r = fetch(url)
        info = {"url": url, "final": r.url, "status": r.status_code, "type": r.headers.get("content-type", ""), "bytes": len(r.content), "file": h}
        if "html" in info["type"] or "xml" in info["type"] or "json" in info["type"]:
            (out / f"{h}.html").write_text(r.text, encoding="utf-8")
            if "html" in info["type"]:
                soup = BeautifulSoup(r.text, "lxml")
                for t in soup(["script", "style"]): t.decompose()
                (out / f"{h}.txt").write_text(" ".join(soup.get_text(" ").split())[:60000], encoding="utf-8")
    except Blocked:
        info = {"url": url, "blocked_by_robots": True}
    except Exception as e:
        info = {"url": url, "error": f"{type(e).__name__}: {e}"[:300]}
    print(info)
    res.append(info)
(out / "index.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
