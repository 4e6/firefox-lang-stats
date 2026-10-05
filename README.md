# firefox-lang-stats

How much Rust in Firefox? See the page [here][gh-pages].

The page shows how the language mix of the [mozilla-firefox/firefox] repository changed across major releases, from
Firefox 46 to the current head of the default branch. It has four tabs:

- **Composition**: share (or lines) of every language per release, stacked.
- **Small multiples**: one chart per language.
- **Language share**: one language over time, one line per view.
- **Pie**: one release at a time, with the change against the previous one.

Each tab offers two views: **All files** (every tracked file, `mobile/` included) and **Browser files** (the same
without `mobile/` and without test files; desktop code for every platform, vendored code, build tooling and docs
included). The (?) next to the view switch on the page explains them briefly.

**How the numbers are made, and how far to trust them: [`docs/methodology.md`](docs/methodology.md)**, published with
the site as [methodology.html][methodology]. It covers the counting rules, the extension and test rules, the header
split, the release set, the data files, known limitations and how to reproduce everything.

## How the data is built

Everything is done by `dev/history.py` (Python 3, standard library and git only). Run `python3 dev/history.py --help`
for the subcommands, the language and test rules, and the release set.

- `data/history.json` holds one record per major release (`FIREFOX_<n>_0_RELEASE`; 125 is counted at
  `FIREFOX_125_0_BUILD1`), one release per line. It is append-only: a stored release is never recounted.
- The workflow `.github/workflows/deploy.yml` runs every Sunday at 22:12 UTC, on every push to `main`, on pull
  requests and by hand (*Run workflow*). It checks out Firefox at depth 1 and then:
  1. runs the unit tests;
  2. `history.py append` adds the releases missing from `data/history.json`, fetching each new tag at depth 1;
  3. `history.py build-site` counts the head of Firefox and writes `build/data.json`; the page (`site/index.html`)
     and the favicon and `og:image` files are copied next to it, and `dev/render_docs.py` renders
     `docs/methodology.md` to `build/methodology.html` (standard library only; it fails the step on Markdown it does
     not support);
  4. on `main` only, if `data/` changed, it commits `data: add releases` as `github-actions[bot]` straight to `main`;
  5. on `main` only, it deploys `build/` to the `gh-pages` branch, replacing its whole content.

  Pull-request runs do steps 1 to 3 and neither commit nor deploy. A failure in the tests, `append` or
  `build-site` commits and deploys nothing.

### `build/data.json`

`data/history.json` plus a `head` point and the fields of the old pie chart:

```
{"meta_date":"2026-10-05T22:12:00+00:00","title_date":"Oct 2026","lang":[{"name":"Rust","loc":...}, ...],
 "method_version":3,"browser_excluded_prefixes":["mobile/"],"header_split":{"c":0.185,"cpp":0.815},
 "releases":[{"v":46,"tag":"FIREFOX_46_0_RELEASE","sha":"...","date":"2016-04-21",
              "all":{"rust":...,"c":...,"cpp":...,"h":...,"js":...,"ts":...,"html":...,"py":...,"java":...,"kt":...,
                     "asm":...},
              "browser":{...the same eleven keys...}}, ...],
 "head":{"sha":"...","date":"2026-10-05","all":{...},"browser":{...}}}
```

- Counts use short language keys and keep headers apart as `h`; totals are not stored (a total is the sum of the
  eleven keys). JavaScript (`js`) and TypeScript (`ts`), and Java (`java`) and Kotlin (`kt`), are separate keys; the
  page draws each pair as one series, JavaScript/TypeScript and Java/Kotlin.
  `date` is the committer date of the counted commit.
- Kept for anyone reading the old file: `meta_date` (time of the run), `title_date` and `lang` (name and lines per
  language at the head, all files). The `lang` numbers differ from the old ones: `.mjs` now counts as JavaScript,
  `.hpp`/`.hh` as C++ and `.S`/`.s` as Assembly, mobile code is included, files with NUL bytes count 0, and headers
  are split 18.5% C / 81.5% C++ instead of 1/3 / 2/3. The list has ten entries instead of eight: TypeScript (after
  JavaScript) and Kotlin (after Java) are new, and JavaScript and Java no longer include them.

## Running it locally

```sh
python3 -m unittest discover -s dev                              # tests, no network
python3 dev/history.py --help                                    # subcommands
git clone --depth 1 https://github.com/mozilla-firefox/firefox.git firefox
# then run the Append and Build steps of .github/workflows/deploy.yml, and:
python3 -m http.server -d build                                  # then open http://localhost:8000
```

To regenerate `data/history.json` from scratch (run it locally, not in CI), follow `python3 dev/history.py --help`
(on a blobless clone with the release tags). Compare the result with the committed file whenever `method_version`
changes.


[mozilla-firefox/firefox]: https://github.com/mozilla-firefox/firefox
[gh-pages]: https://4e6.github.io/firefox-lang-stats/
[methodology]: https://4e6.github.io/firefox-lang-stats/methodology.html
