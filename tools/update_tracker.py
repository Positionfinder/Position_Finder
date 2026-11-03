"""Update a personal Excel tracker of positions.

    python tools/update_tracker.py --xlsx Positions.xlsx [--site docs/data/jobs.json] [--linkedin new.json]

Sheets
  Website   open positions and calls from the Position Finder data (rebuilt each run)
  LinkedIn  LinkedIn ads/posts found by the daily search (new rows added, old rows kept)
  Archive   rows that left the website or whose deadline has passed

Columns "My status" and "My notes" are the user's own: they are kept for every row (matched by link),
also when a row moves to the Archive. Nothing personal is stored in this script.

--linkedin is docs/data/linkedin.json: {"items": [{title, title_en, institution, city, region, country (ES/DE),
  level (postdoc/research/professional), note, topics, match {A, B}, deadline (YYYY-MM-DD or null), url,
  li_kind (job/post), first_seen}]}
"""
import argparse, datetime as dt, json, os
from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

COLS = ["Source", "Type", "Position (English)", "Original title", "Institution", "City", "Region", "Country", "Level",
        "Topics", "Note", "Match A %", "Match B %", "Best match %", "Deadline", "Days left", "Link",
        "First seen", "My status", "My notes", "URL"]
WIDTH = [13, 13, 48, 36, 32, 16, 18, 10, 26, 38, 24, 10, 10, 11, 13, 10, 10, 12, 14, 30, 40]
KEYS = ["source", "type", "title_en", "title", "institution", "city", "region", "country", "level", "topics", "note",
        "A", "B", None, "deadline", None, "url", "first_seen", "status", "notes", "url"]
COUNTRY = {"ES": "Spain", "DE": "Germany"}
STATUS = '"To check,Interested,Applied,Not relevant,Closed"'
F = "Arial"
TODAY = dt.date.today()


def as_date(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, str):
        for f in ("%Y-%m-%d", "%d %b %Y", "%d %B %Y"):
            try:
                return dt.datetime.strptime(v.strip(), f).date()
            except ValueError:
                pass
    return v


def read_existing(path):
    """{sheet: [row dict]} from an existing tracker, by header name."""
    out = {"Website": [], "LinkedIn": [], "Archive": []}
    if not os.path.exists(path):
        return out
    wb = load_workbook(path)
    for name in out:
        if name not in wb.sheetnames:
            continue
        ws = wb[name]
        hdr_row = next((r for r in range(1, 10) if ws.cell(r, 1).value == "Source"), None)
        if not hdr_row:
            continue
        hdr = {ws.cell(hdr_row, c).value: c for c in range(1, ws.max_column + 1)}
        for r in range(hdr_row + 1, ws.max_row + 1):
            row = {}
            for col, key in zip(COLS, KEYS):
                if key and col in hdr:
                    cell = ws.cell(r, hdr[col])
                    row[key] = cell.value if col != "Link" else (cell.hyperlink.target if cell.hyperlink else None)
            if row.get("url"):
                if isinstance(row.get("topics"), str):
                    row["topics"] = [t.strip() for t in row["topics"].split(";") if t.strip()]
                row["deadline"] = as_date(row.get("deadline"))
                row["first_seen"] = as_date(row.get("first_seen"))
                out[name].append(row)
    return out


LEVEL = {"postdoc": "Postdoc", "research": "Researcher (level not stated)", "professional": "Professional"}


def sector(level):
    return "Professional" if level == "professional" else "Academic"


def linkedin_rows(path):
    d = json.load(open(path, encoding="utf-8"))
    rows = []
    for it in d.get("items", []):
        m = it.get("match") or {}
        rows.append({
            "source": "LinkedIn post" if it.get("li_kind") == "post" else "LinkedIn job",
            "type": sector(it.get("level")),
            "title_en": it.get("title_en") or it["title"],
            "title": it["title"] if it["title"] != it.get("title_en") else "",
            "institution": it.get("institution"), "city": it.get("city"), "region": it.get("region"),
            "country": COUNTRY.get(it.get("country"), it.get("country")),
            "level": LEVEL.get(it.get("level"), it.get("level")), "topics": it.get("topics") or [],
            "note": it.get("note") or "", "A": m.get("A"), "B": m.get("B"),
            "deadline": as_date(it["deadline"]) if it.get("deadline") else "see ad",
            "url": it["url"], "first_seen": as_date(it.get("first_seen")),
        })
    return rows


def site_rows(path):
    d = json.load(open(path, encoding="utf-8"))
    rows = []
    for it in d["items"]:
        m = it.get("match") or {}
        call = it["kind"] == "call"
        rows.append({
            "source": "Website (call)" if call else "Website",
            "type": "Fellowship call" if call else sector(it.get("level")),
            "title_en": it.get("title_en") or it["title"],
            "title": it["title"] if it["title"] != it.get("title_en") else "",
            "institution": "Agencia Estatal de Investigación (national call)" if call else it["institution"],
            "city": "" if call else it.get("city") or "",
            "region": it.get("region") or "",
            "country": COUNTRY.get(it.get("country") or "ES", ""),
            "level": "Fellowship call (all fields)" if call else
                     LEVEL.get(it.get("level"), ""),
            "topics": it.get("topics") or [],
            "note": "Estimated deadline" if it.get("deadline_estimated") else "",
            "A": m.get("A"), "B": m.get("B"),
            "deadline": as_date(it["deadline"]) if it.get("deadline") else "Not stated",
            "url": it["url"],
        })
    return rows


def expired(row, max_age=None):
    d = row.get("deadline")
    if isinstance(d, dt.date):
        return d < TODAY
    seen = row.get("first_seen")  # no deadline: assume closed after max_age days
    return bool(max_age and isinstance(seen, dt.date) and (TODAY - seen).days > max_age)


def write_sheet(ws, rows, title, subtitle):
    ws["A1"] = title
    ws["A1"].font = Font(name=F, bold=True, size=14)
    ws["A2"] = subtitle
    ws["A2"].font = Font(name=F, size=9, italic=True, color="595959")
    ws["A3"] = (f"Updated {TODAY:%d %b %Y}. Match A = Spatial risk, landscape & participatory GIS; "
                "Match B = Participatory planning, housing & informal settlements. Green = 60% or more. "
                "Yellow columns are yours: they are kept when the file is updated.")
    ws["A3"].font = Font(name=F, size=9, italic=True, color="595959")
    h = 5
    for c, (name, w) in enumerate(zip(COLS, WIDTH), 1):
        x = ws.cell(h, c, name)
        x.font = Font(name=F, bold=True, color="FFFFFF")
        x.fill = PatternFill("solid", fgColor="2F5D50")
        x.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.row_dimensions[h].height = 30
    body = Font(name=F, size=10)
    line = Border(bottom=Side(style="thin", color="D9D9D9"))
    mine = PatternFill("solid", fgColor="FFFF99")
    for i, row in enumerate(rows):
        r = h + 1 + i
        for c, key in enumerate(KEYS, 1):
            v = row.get(key) if key else None
            if key == "topics":
                v = "; ".join(v or [])
            x = ws.cell(r, c, v)
            x.font = body
            x.border = line
            x.alignment = Alignment(vertical="top", wrap_text=c in (3, 4, 5, 9, 10, 11, 20))
        ws.cell(r, 14, f'=IF(COUNT(L{r}:M{r})=0,"",MAX(L{r}:M{r}))')
        ws.cell(r, 16, f'=IF(ISNUMBER(O{r}),O{r}-TODAY(),"")')
        for c in (15, 18):
            if isinstance(ws.cell(r, c).value, dt.date):
                ws.cell(r, c).number_format = "DD MMM YYYY"
        link = ws.cell(r, 17, "Open")
        link.hyperlink = row["url"]
        link.font = Font(name=F, size=10, color="0563C1", underline="single")
        for c in (19, 20):
            ws.cell(r, c).fill = mine
    last = max(h + 1, h + len(rows))
    ws.conditional_formatting.add(f"L{h+1}:N{last}", CellIsRule(operator="greaterThanOrEqual", formula=["60"],
                                  fill=PatternFill("solid", fgColor="C6E0B4")))
    ws.conditional_formatting.add(f"L{h+1}:N{last}", CellIsRule(operator="between", formula=["40", "59"],
                                  fill=PatternFill("solid", fgColor="FFF2CC")))
    ws.conditional_formatting.add(f"P{h+1}:P{last}", FormulaRule(formula=[f'AND(ISNUMBER(P{h+1}),P{h+1}<=7)'],
                                  font=Font(name=F, bold=True, color="C00000")))
    dv = DataValidation(type="list", formula1=STATUS, allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"S{h+1}:S{last}")
    ws.column_dimensions["U"].hidden = True  # plain-text link, used to match rows between updates
    ws.freeze_panes = f"D{h+1}"
    ws.auto_filter.ref = f"A{h}:{get_column_letter(len(COLS))}{last}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", required=True)
    ap.add_argument("--site")
    ap.add_argument("--linkedin")
    ap.add_argument("--out", help="write here instead of --xlsx")
    a = ap.parse_args()

    old = read_existing(a.xlsx)
    mine = {}  # url -> user columns + first seen
    for rows in old.values():
        for r in rows:
            k = mine.setdefault(r["url"], {})
            for key in ("status", "notes", "first_seen"):
                if r.get(key) and not k.get(key):
                    k[key] = r[key]

    def keep_mine(r):
        k = mine.get(r["url"], {})
        r["status"], r["notes"] = k.get("status"), k.get("notes")
        r["first_seen"] = k.get("first_seen") or r.get("first_seen") or TODAY
        return r

    archive = {r["url"]: r for r in old["Archive"]}

    # Website: rebuilt from the current data; rows that left the site go to the archive
    if a.site:
        website = [keep_mine(r) for r in site_rows(a.site)]
        now = {r["url"] for r in website}
        for r in old["Website"]:
            if r["url"] not in now:
                r["note"] = ((r.get("note") or "") + f" · no longer listed on {TODAY:%d %b %Y}").strip(" ·")
                archive[r["url"]] = r
    else:
        website = old["Website"]

    # LinkedIn: keep old rows, add new ones (by link)
    linkedin = {r["url"]: r for r in old["LinkedIn"]}
    added = 0
    if a.linkedin:
        for n in linkedin_rows(a.linkedin):
            if n["url"] in linkedin or n["url"] in archive:
                continue
            linkedin[n["url"]] = keep_mine(n)
            added += 1

    # past deadlines go to the archive
    for pool in (linkedin,):
        for url in [u for u, r in pool.items() if expired(r, max_age=45)]:
            archive[url] = pool.pop(url)
    still_open = [r for r in website if not expired(r)]
    for r in website:
        if expired(r):
            archive[r["url"]] = r

    best = lambda r: max([v for v in (r.get("A"), r.get("B")) if isinstance(v, (int, float))] or [-1])
    still_open.sort(key=lambda r: (r["source"] != "Website", -best(r)))
    li_rows = sorted(linkedin.values(), key=lambda r: (-(as_date(r.get("first_seen")) or TODAY).toordinal(), -best(r)))
    ar_rows = sorted(archive.values(), key=lambda r: str(r.get("deadline")), reverse=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Website"
    write_sheet(ws, still_open, "Open positions – Position Finder website",
                "Rebuilt from the website data on every update.")
    write_sheet(wb.create_sheet("LinkedIn"), li_rows, "LinkedIn – research positions found by the daily search",
                "Academic: Spain & Germany, postdoc/researcher. Professional: Spain. Newest first. \"see ad\" = no deadline in the ad.")
    write_sheet(wb.create_sheet("Archive"), ar_rows, "Archive – closed or no longer listed",
                "Rows move here when the deadline has passed or the position left the website.")
    out = a.out or a.xlsx
    wb.save(out)
    print(json.dumps({"file": out, "website": len(still_open), "linkedin": len(li_rows),
                      "linkedin_added": added, "archive": len(ar_rows)}))


if __name__ == "__main__":
    main()
