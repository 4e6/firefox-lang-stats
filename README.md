# firefox-lang-stats

How much Rust in Firefox? See the page [here][gh-pages].

The page shows how the language mix of the [mozilla-firefox/firefox] repository changed across major releases, from
Firefox 46 to the current head of the default branch. It has four views:

- **Composition**: share (or lines) of every language per release, stacked.
- **Small multiples**: one chart per language.
- **Language share**: one language over time, one line per series.
- **Pie + scrubber**: one release at a time, with the change against the previous one.

Each view offers three series: **all files** (every tracked file), **non-test files** (test paths dropped) and
**browser artifact** (the code built into the Linux x86-64 desktop browser). The artifact series has no data yet and
is disabled on the page. `mobile/` is excluded from every series. Lines are counted by file extension: Rust, C, C++,
C/C++ headers (split 18.5% C, 81.5% C++ at display time), JavaScript, HTML/CSS, Python, Java and Assembly.

## How the data is built

Everything is done by `dev/history.py` (Python 3, standard library and git only). Run `python3 dev/history.py --help`
for the subcommands, the language and test rules, and the release set.

- `data/history.json` holds one record per major release (`FIREFOX_<n>_0_RELEASE`; 125 is counted at
  `FIREFOX_125_0_BUILD1`), one release per line. It is append-only: a stored release is never recounted.
- The workflow `.github/workflows/deploy.yml` runs every Sunday at 22:12 UTC, on every push to `main`, on pull
  requests and by hand (*Run workflow*). It checks out Firefox at depth 1 and then:
  1. runs the unit tests;
  2. `history.py append` adds the releases missing from `data/history.json`, fetching each new tag at depth 1;
  3. `history.py build-site` counts the head of Firefox and writes `build/data.json`; the page
     (`site/index.html`) and the favicon and `og:image` files are copied next to it;
  4. on `main` only, if `data/` changed, it commits `data: add releases` as `github-actions[bot]` straight to `main`;
  5. on `main` only, it deploys `build/` to the `gh-pages` branch, replacing its whole content.

  Pull-request runs do steps 1 to 3 and neither commit nor deploy. If any step fails, nothing is committed or deployed.

### `build/data.json`

`data/history.json` plus a `head` point and the fields of the old pie chart:

```
{"meta_date":"2026-10-05T22:12:00+00:00","title_date":"Oct 2026","lang":[{"name":"Rust","loc":6249372}, ...],
 "method_version":1,"excluded_prefixes":["mobile/"],"header_split":{"c":0.185,"cpp":0.815},
 "releases":[{"v":46,"tag":"FIREFOX_46_0_RELEASE","sha":"...","date":"2016-04-26",
              "all":{"rust":2862,"c":...,"cpp":...,"h":...,"js":...,"html":...,"py":...,"java":...,"asm":...},
              "nontest":{...},"artifact":null}, ...],
 "head":{"sha":"...","date":"2026-10-05","all":{...},"nontest":{...},"artifact":null}}
```

- New: `releases`, `head`, `method_version`, `excluded_prefixes`, `header_split`. Counts use short language keys and
  keep headers apart as `h`; totals are not stored. `date` is the committer date of the counted commit.
- Kept for anyone reading the old file: `meta_date` (time of the run), `title_date` and `lang` (name and lines per
  language at the head, all files). The `lang` numbers differ from the old ones: `.mjs` now counts as JavaScript,
  `mobile/` is excluded, and headers are split 18.5% C / 81.5% C++ instead of 1/3 / 2/3.

## Running it locally

```sh
python3 -m unittest discover -s dev                              # tests, no network
git clone --depth 1 https://github.com/mozilla-firefox/firefox.git firefox
python3 dev/history.py append data/history.json --repo firefox   # add new releases
mkdir -p build
python3 dev/history.py build-site data/history.json --repo firefox --out build
cp site/index.html rustacean-orig-noshadow.ico rustacean-orig-noshadow.png build/
python3 -m http.server -d build                                  # then open http://localhost:8000
```

To regenerate `data/history.json` from scratch (about 10 minutes and 3.5 GB of disk; run it locally, not in CI),
follow `python3 dev/history.py --help` (the `backfill` subcommand on a blobless clone with the release tags). Compare
the result with the committed file whenever `METHOD_VERSION` changes.

## Symbol file lists

`data/artifact-files/<version>.txt` lists the repository source files compiled into the Linux x86-64 binaries of the
releases whose symbols expire from the Mozilla symbol server (131.0.2 to 143 and 140.0esr to 140.3.1esr). They are
produced by `dev/artifact-files` and kept for the browser-artifact series; see `data/artifact-files/README.md`.

## Documents

- `docs/shipped-code-research.md`: what ships in the browser, and the storage design.
- `docs/implementation-plan.md`: the plan this pipeline follows.
- `docs/reference/`: prototype code, measured data and the design preview.


[mozilla-firefox/firefox]: https://github.com/mozilla-firefox/firefox
[gh-pages]: https://4e6.github.io/firefox-lang-stats/
