# Position Finder

Postdoc and researcher positions in **urban planning, geography, landscape** and related fields
(GIS & remote sensing, participatory methods, risk, ecosystem services, housing, governance),
collected automatically every day from universities and research centres in **Spain** and
**Germany**, and scored against two research profiles. PhD positions are excluded.

Live site: https://positionfinder.github.io/Position_Finder/

Columns: position (English title, original underneath), institution, location (city, region,
country), topic, match % for profile A and B, deadline, link to the original announcement.
By default the site shows positions with at least 60 % match for either profile; a filter
switches to all positions.

## How it works

1. **Registry** (`sources/institutions.yaml`): every Spanish university and relevant research centre,
   and German universities, universities of applied sciences strong in planning/landscape, and
   research institutes (city and region for each), with their public vacancy pages.
2. **Collector** (`collector/collect.py`, runs daily via `.github/workflows/collect.yml`):
   - reads each job page, extracts the listed offers and opens each offer's own page (HTML or PDF);
   - strips text that repeats across a site (menus, footers) so it doesn't skew the classification;
   - keeps only postdoc and researcher offers (PhD positions and PhD programme calls are excluded)
     whose text matches the target fields or the research profiles (Spanish, Catalan, English and
     German vocabulary); German "Wissenschaftliche/r Mitarbeiter/in" ads that don't state a level
     are shown as "Researcher (level not stated)";
   - shows an offer only if it is confirmed open: a future deadline (from the listing row, the offer
     page, or estimated from "N working days after publication"), or an explicit "open" status;
   - drops offers marked closed / resolved / under evaluation, rows that already link to results
     (admitted lists, final resolutions, awards), and past editions of programme calls;
   - national/regional postdoc fellowship programmes open to all fields (Juan de la Cierva, Ramón y Cajal,
     Beatriu de Pinós…) are kept as "fellowship calls", merged into one card even when several
     universities list them;
   - writes `docs/data/jobs.json`, which the website reads.
3. **Matching** (`collector/match.py`, `sources/profiles.yaml`): each profile is a weighted list of
   research topics taken from a CV (main lines 3 points, related areas 2, methods 1). A topic
   counts fully if it appears in the title/listing row or at least twice in the announcement
   (including a linked call PDF), and half if once. Match % = covered points / "full match" points,
   capped at 100; a position touching no main line of a profile is capped at 55 %. No CV text is
   stored in this repository, only the topic lists, and profiles are labelled by research line.
4. **English titles** (`collector/translate.py`): offline translation with Argos Translate
   (Spanish, Catalan, German → English), cached in `data/translations.json`.
5. **Website** (`docs/`): a static page with a table, search and filters (country, postdoc/researcher,
   match threshold, region, topic, sort by match or deadline).
6. **Discovery** (`collector/discover.py`, weekly or on demand): follows job-related links from each
   institution's homepage and writes candidate job pages to `data/discovery.json`, to help find
   pages worth adding to the registry.

## Good manners

The collector identifies itself as `PositionFinderBot` with a link to this repository, respects every
site's `robots.txt`, waits 2 seconds between requests to the same site, caches offer pages for 14 days,
and never logs in anywhere. Sites that disallow automated access (for example EURAXESS's job pages,
and several universities that block all bots) are not collected; the website links to them instead.

## Adding or fixing a source

Add the page URL under the institution's `job_pages` in `sources/institutions.yaml` and push.
The collect workflow runs on every change to `sources/` or `collector/`, and the "Sources and their
status" table at the bottom of the website shows how many offers each page yielded.
Pages that list offers through JavaScript (e.g. UOC, Comillas) need a dedicated adapter.

## Turning on the website (one-time)

Repository **Settings → Pages → Build and deployment → Source: Deploy from a branch**,
branch `main`, folder `/docs`, then Save. The site appears at
`https://positionfinder.github.io/Position_Finder/` a minute later.

## Running locally

```bash
pip install -r requirements.txt
python collector/collect.py            # all sources
python collector/collect.py upc upm    # only some institutions (by id)
python -m http.server -d docs          # then open http://localhost:8000
```
