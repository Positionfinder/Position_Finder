# Position Finder

PhD and postdoc positions in **urban planning, architecture, geography** and related fields
(landscape, housing, GIS & remote sensing, urban mobility, heritage, climate risk) at Spanish
universities and research centres, collected automatically every day and published as a
searchable website on GitHub Pages.

## How it works

1. **Registry** (`sources/institutions.yaml`): every Spanish university and the relevant
   research centres, with the public job pages known to list PhD / postdoc / research-contract calls.
2. **Collector** (`collector/collect.py`, runs daily via `.github/workflows/collect.yml`):
   - reads each job page, extracts the listed offers and opens each offer's own page (HTML or PDF);
   - strips text that repeats across a site (menus, footers) so it doesn't skew the classification;
   - keeps only PhD or postdoc offers whose text matches the target fields, and drops closed offers,
     past deadlines, resolutions, lists of admitted candidates and similar notices;
   - national/regional fellowship programmes open to all fields (Juan de la Cierva, Ramón y Cajal, FPU,
     Beatriu de Pinós…) are kept as "fellowship calls", merged into one card even when several
     universities list them;
   - writes `docs/data/jobs.json`, which the website reads.
3. **Website** (`docs/`): a static page with search and filters (PhD/postdoc, field, region,
   institution type, deadline sort). Each card links to the original announcement.
4. **Discovery** (`collector/discover.py`, weekly or on demand): follows job-related links from each
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
