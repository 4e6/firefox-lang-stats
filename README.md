# firefox-lang-stats

How much Rust in Firefox? See the page [here][gh-pages].

The page shows how the language mix of the [mozilla-firefox/firefox] repository changed across major releases, from
Firefox 46 to the current head of the default branch. It has four views:

- **Composition**: share (or lines) of every language per release, stacked.
- **Small multiples**: one chart per language.
- **Language share**: one language over time, one line per series.
- **Pie**: one release at a time, with the change against the previous one.

Each view offers three series: **all files** (every tracked file), **non-test files** (test paths dropped) and
**browser artifact** (the code built into the Linux x86-64 desktop browser; so far for release 157 and the head).
`mobile/` is excluded from every series. The (?) next to the view switch on the page explains them briefly.

**How the numbers are made, and how far to trust them: [`docs/methodology.md`](docs/methodology.md)**, published with
the site as [methodology.html][methodology]. It covers the counting rules, the extension and test rules, the header
split, the browser-artifact method, the release set, the data files, known limitations and how to reproduce
everything.

## How the data is built

Everything is done by `dev/history.py` (Python 3, standard library and git only). Run `python3 dev/history.py --help`
for the subcommands, the language and test rules, and the release set.

- `data/history.json` holds one record per major release (`FIREFOX_<n>_0_RELEASE`; 125 is counted at
  `FIREFOX_125_0_BUILD1`), one release per line. It is append-only: a stored release is never recounted.
- The workflow `.github/workflows/deploy.yml` runs every Sunday at 22:12 UTC, on every push to `main`, on pull
  requests and by hand (*Run workflow*). It checks out Firefox at depth 1 and then:
  1. runs the unit tests;
  2. `history.py append` adds the releases missing from `data/history.json`, fetching each new tag at depth 1;
  3. `history.py build-site --with-artifact` counts the head of Firefox, computes the head's browser artifact
     (below) and writes `build/data.json`; the page (`site/index.html`) and the favicon and `og:image` files are
     copied next to it, and `dev/render_docs.py` renders `docs/methodology.md` to `build/methodology.html` (standard
     library only; it fails the step on Markdown it does not support);
  4. on `main` only, if `data/` changed, it commits `data: add releases` as `github-actions[bot]` straight to `main`;
  5. on `main` only, it deploys `build/` to the `gh-pages` branch, replacing its whole content.

  Pull-request runs do steps 1 to 3 and neither commit nor deploy. A failure in the tests, `append` or
  `build-site` commits and deploys nothing. The head artifact never fails the run: if it cannot be computed
  (Mozilla endpoints down, no finished build, a 15-minute limit, even a bug) `head.artifact` is `null` and the log
  says why. The job has a 30-minute limit.

### The browser-artifact series

What ships is learnt from Mozilla's own build outputs (the package and the `FILE` records of its debug symbols),
never from a local build: `dev/artifact.py`, Python standard library and git only. The method step by step, and what
it leaves out, is in [`docs/methodology.md`](docs/methodology.md#browser-artifact).

- **Head** (every run, `build/data.json` only): the newest finished mozilla-central `linux64-opt` build from the
  Taskcluster index. Its `sha` is the build's commit, usually a few hours older than `head.sha`; the page says so.
- **Releases** (stored once in `data/history.json`): `history.py set-artifact` computes a release's artifact
  from its release candidate build and writes it into that release's record (the only change to the file; a
  stored artifact is never recomputed). Release 157 was filled this way:

  ```sh
  B=https://archive.mozilla.org/pub/firefox/candidates/157.0-candidates/build1/linux-x86_64/en-US
  python3 dev/history.py set-artifact data/history.json --v 157 --repo firefox \
      --symbols $B/firefox-157.0.crashreporter-symbols.zip --package $B/firefox-157.0.tar.xz
  ```

  Use the last `build<N>` of the release's candidates; the build's `FILE` records must name the release tag's
  commit, otherwise nothing is written (exit status 3).

Next step (Task 6 of `docs/implementation-plan.md`): artifacts for older releases (147 onwards use the same git
`FILE` records; older ones need per-era rules and the saved lists in `data/artifact-files/`), and running
`set-artifact` automatically for each release `append` adds. Until then new releases are appended with
`artifact: null`.

### `build/data.json`

`data/history.json` plus a `head` point and the fields of the old pie chart:

```
{"meta_date":"2026-10-05T22:12:00+00:00","title_date":"Oct 2026","lang":[{"name":"Rust","loc":6249372}, ...],
 "method_version":1,"excluded_prefixes":["mobile/"],"header_split":{"c":0.185,"cpp":0.815},
 "releases":[{"v":46,"tag":"FIREFOX_46_0_RELEASE","sha":"...","date":"2016-04-26",
              "all":{"rust":2862,"c":...,"cpp":...,"h":...,"js":...,"html":...,"py":...,"java":...,"asm":...},
              "nontest":{...},"artifact":null}, ...,
             {"v":157,...,"artifact":{"rust":1931822,"c":...,"cpp":...,"h":...,"js":...,"html":...,"py":0,"java":0,
              "asm":0,"sha":"fdd757a2...","source":{"kind":"candidates","symbols":"<url>","package":"<url>",
              "libxul_debug_id":"...","modules":26,"paths":19289}}}],
 "head":{"sha":"...","date":"2026-10-05","all":{...},"nontest":{...},
         "artifact":{...nine keys...,"sha":"<build commit>","source":{"kind":"symbols","index":"gecko.v2...",
                     "task":"...","libxul_debug_id":"...","modules":27,"paths":19978}}}}
```

- New: `releases`, `head`, `method_version`, `excluded_prefixes`, `header_split`. Counts use short language keys and
  keep headers apart as `h`; totals are not stored. `date` is the committer date of the counted commit.
- `artifact` is `null` or the nine language keys plus `sha` (the commit counted) and `source` (where the file list
  came from); sum only the nine language keys.
- Kept for anyone reading the old file: `meta_date` (time of the run), `title_date` and `lang` (name and lines per
  language at the head, all files). The `lang` numbers differ from the old ones: `.mjs` now counts as JavaScript,
  `mobile/` is excluded, and headers are split 18.5% C / 81.5% C++ instead of 1/3 / 2/3.

## Running it locally

```sh
python3 -m unittest discover -s dev                              # tests, no network
git clone --depth 1 https://github.com/mozilla-firefox/firefox.git firefox
python3 dev/history.py append data/history.json --repo firefox   # add new releases
mkdir -p build
python3 dev/history.py build-site data/history.json --repo firefox --out build --with-artifact
cp site/index.html rustacean-orig-noshadow.ico rustacean-orig-noshadow.png build/
python3 dev/render_docs.py docs/methodology.md --page site/index.html --out build/methodology.html
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

- `docs/methodology.md`: how the numbers are made and how far to trust them (published as `methodology.html`).
- `docs/shipped-code-research.md`: what ships in the browser, and the storage design.
- `docs/implementation-plan.md`: the plan this pipeline follows.
- `docs/reference/`: prototype code, measured data and the design preview.


[mozilla-firefox/firefox]: https://github.com/mozilla-firefox/firefox
[gh-pages]: https://4e6.github.io/firefox-lang-stats/
[methodology]: https://4e6.github.io/firefox-lang-stats/methodology.html
