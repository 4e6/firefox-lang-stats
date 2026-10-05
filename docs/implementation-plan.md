# Implementation plan: language history, test exclusion and the browser artifact

For whoever builds this. It assumes you have read `shipped-code-research.md` (the findings and the storage design) and
that you have `reference/` (prototype code, measured data and the design preview) next to it. Everything the plan relies
on is in those two places; nothing depends on the session that wrote them.

## Goal

Replace the current pie chart with a page that shows how the language mix of Firefox changed across releases, for issues
[#6](https://github.com/4e6/firefox-lang-stats/issues/6) (ignore tests) and
[#10](https://github.com/4e6/firefox-lang-stats/issues/10) (history), and add the code that ships in the desktop browser
as a third series.

- Four views, in this order: **Composition**, **Small multiples**, **Language share**, **Pie + scrubber**. See
  `reference/preview/README.md`.
- Three series in every view: all tracked files, non-test files, **browser artifact** (Linux x86-64 desktop).
- Data: one append-only `data/history.json` in this repository plus a head point computed each week. See "Storage design"
  in the research document.

Done means: the page is live on `https://4e6.github.io/firefox-lang-stats/`, the weekly job keeps it current without
manual steps, and the browser-artifact series exists at least for the current release.

## Before you start

1. **Confirm merge permission.** Merging to `main` deploys the live site. The owner asked for the work to be carried
   through to the end; if you cannot confirm that includes merging and deploying, stop after the pull request is green
   and reviewed, and say so.
2. **The time-critical task is task 0.** Symbols for Firefox 131.0.2 expire from the symbol server around 2026-10-08, and
   later releases follow every few weeks. If that date has passed, extract whatever is still available and record what
   was lost.
3. Work in a git worktree on a branch off `main` (for example `feature/history`), never on `docs/shipped-code-research`.

## Decisions

### Made by the owner

| Decision | Choice |
|---|---|
| Scope | Desktop browser only. `mobile/` is excluded from every series |
| Series | Add the browser artifact next to the tracked series; do not replace anything |
| Weekly commits | The weekly job commits to `main` directly. Verified: `main` has no branch protection and the workflow's default token permission is `write` |
| Symbol file lists | Kept in `data/artifact-files/<version>.txt` on `main`, for the expiring releases only (131.0.2 to 143 and 140.0esr to 140.3.1esr) |
| Views | The four above, in that order. Drop tab E (line + pie) |
| Names | The UI says "Browser artifact"; the research document says "shipped" for the same thing |
| Scales | Composition, Small multiples and Language share switch between share and lines; Language share has a language switch instead of a view switch |

### Defaults chosen for you (change them if the owner says otherwise)

| Decision | Default | Why |
|---|---|---|
| Release set | Major releases only (`FIREFOX_<n>_0_RELEASE`, 46 to 157). Release 125 has no `_RELEASE` tag: use `FIREFOX_125_0_BUILD1` and store it under `v: 125` | 112 records, about 13 new per year; all 505 releases are an easy later change |
| Platform | Linux x86-64 only, labelled | Only platform verified; Windows crate sources are fetched at build time and would be dropped |
| x axis | Release number; store the tag commit date as well | Releases are about four weeks apart |
| Test/`third_party`/rest split | Not stored | No view needs it; `all` minus `nontest` gives test lines. Adding it later is one 8-12 minute recompute |
| Headers | Store raw `h`; split 18.5% C and 81.5% C++ at display time from `header_split` in the file | By location about 81.5% of headers are C++ |
| Legacy `data.json` fields | Keep `meta_date`, `title_date` and `lang` in the published `data.json`, filled from the new "all" view | Somebody may read the file; the numbers will shift (`.mjs` added, `mobile/` dropped) |
| Assembly in the artifact series | Not covered (nasm objects carry no line info); write 0 and mention it on the page | Taking it from the build configuration is possible but not worth it yet |
| d3 | Version 7.8.5 from cdnjs with a subresource-integrity hash | What the preview uses |
| Language set | Rust, C, C++ (`.cc .cpp .cxx .hxx`), `h`, JavaScript (`.jsm .jsx .js .mjs`), HTML/CSS (`.htm .html .xhtml .xht .css`), Python, Java, Assembly (`.asm`) | The existing set plus `.mjs`. Kotlin, `.hpp`, `.hh`, `.mm`, `.S` stay out; changing the set is a `method_version` bump |

## What exists today (verified 2026-10-05)

- `.github/workflows/deploy.yml`: runs on push to `main`, on pull requests and every Sunday 22:12 UTC. Checks out this
  repository and `mozilla-firefox/firefox` (depth 1), installs `mustache` with npm, runs `dev/build-data ./firefox >
  build/data.json`, renders `index.mustache` to `build/index.html`, and deploys `build/` to the `gh-pages` branch with
  `JamesIves/github-pages-deploy-action@v4` (only on `main`). The whole job takes about 2.3 minutes. The action's `clean`
  input defaults to true, so anything not in `build/` is removed from `gh-pages` on every deploy.
- `gh-pages` holds only `data.json` (`meta_date`, `title_date`, `lang: [{name, loc}]`) and `index.html` (a Google Charts pie).
- `dev/build-data` counts `git ls-files` by extension with GNU `wc`; it has no `.mjs`, no non-test view and uses a stale
  2/3 : 1/3 header split. `dev/git-file-stats` and `git-file-stats.log` are leftovers.
- Repository settings: default workflow permission `write`; `main` unprotected.

## Data contract

### `data/history.json` (committed, append-only, one release per line)

```json
{"method_version":1,"excluded_prefixes":["mobile/"],"header_split":{"c":0.185,"cpp":0.815},"releases":[
{"v":46,"tag":"FIREFOX_46_0_RELEASE","sha":"<40 hex>","date":"2016-04-26",
 "all":{"rust":0,"c":0,"cpp":0,"h":0,"js":0,"html":0,"py":0,"java":0,"asm":0},
 "nontest":{"rust":0,"c":0,"cpp":0,"h":0,"js":0,"html":0,"py":0,"java":0,"asm":0},
 "artifact":null}
]}
```

- `v` is the major release number (integer). `artifact` is `null` or the same nine keys plus `"sha"` (the commit its file
  list was counted at) and `"source"` (`"symbols"` with the symbol origin and build ids, or `"candidates"`).
- `reference/history/history.py` writes exactly this shape, except `header_split` (add it) and `artifact` (always `null`).
- Totals are not stored; the page sums the language columns. Test lines are `all` minus `nontest`.

### `build/data.json` (deployed; what the page loads)

`data/history.json` merged with a `head` object (same shape as a release without `v`, `tag`: `{"sha","date","all","nontest","artifact"}`)
and the legacy fields `meta_date` (ISO time of the run), `title_date` (for example `"Oct 2026"`) and `lang` (the old
pie: name and lines for Rust, C, C++, JavaScript, HTML, Python, Java, Assembly, from `head.all` with the header split applied).

### `data/artifact-files/<version>.txt`

Sorted repository paths, one per line, plain text, for the expiring releases only (see `reference/symbols/README.md`).

## Work breakdown

Do the tasks in this order. Each ends with checks; do not start the next before they pass.

### Task 0: symbol file lists for the expiring releases (time-critical, independent)

Goal: for each of 131.0.2, 131.0.3, 132.0 to 143.0 and 140.0esr to 140.3.1esr, commit `data/artifact-files/<version>.txt`.

1. Write `dev/artifact-files` (Python, stdlib only) that implements the seven steps in `reference/symbols/README.md`, reusing
   the logic of `rzip.py`, `tecken.py` and `buildid.py`. It must work for every module in the release tarball, not only
   `libxul.so`, and write one sorted path per line.
2. Run it for every version in the range. Record in a table (commit it as `data/artifact-files/README.md`) per version:
   number of paths, modules read, modules skipped (404), and the symbol-server debug id of `libxul.so`.
3. Branch, commit, open a pull request. It is independent of everything else and can merge first.

Checks: every path exists in the git tree of the release tag (`reference/symbols/checkpaths.py`; the earlier run found 0 missing
for 135.0 and 143.0 after dropping toolchain headers and `obj-*` paths); 15,000-21,000 paths per release; `libxul.so`'s file
list contains the same shipped binaries as the release tarball (about 28 ELF files for 135.0). If a release's symbols are already gone, skip it and note it in the README.

### Task 1: counter, tests and the backfill

Goal: `data/history.json` with all major releases, produced by a counter that the weekly job will also use.

1. Move `reference/history/history.py` to `dev/history.py` and finish it. It already streams per release (no memory
   peak). Add: the `header_split` field; `--exclude mobile/` as the default; a `count_release(repo, tag)` function that
   works on a single release in any clone (blobless or depth 1), used by both the backfill and the weekly append; a
   `head` subcommand that counts `HEAD` of a normal checkout; and an `append` subcommand that adds missing majors to an
   existing file (comparing by `v`, fetching each missing tag with `git fetch --depth 1 origin tag <tag>`).
2. Add `dev/test_history.py` (`unittest`, no network): build a throwaway git repository with a few files of each language,
   test directories and a `mobile/` directory, tag it, and assert the counts for `all` and `nontest`, the `--exclude`
   handling, the 125 fallback tag rule, and `is_test` on a table of paths taken from `reference/test-paths/README.md`.
3. Run the backfill (`reference/history/backfill.sh`, about 8-9 minutes and 3.5 GB) into `data/history.json`, with
   `--exclude mobile/`, and add `header_split`.

Checks: see "Verified reference results": run without `--exclude` and compare with `reference/measured/`, then run with
`--exclude mobile/` and compare with the table below; unit tests pass; peak memory of the count step stays near the measured 2.7 GB
(`/usr/bin/time -l` on macOS, `-v` on Linux); reduce it only if the runner needs it.

### Task 2: weekly job

Goal: the existing workflow appends new releases, computes the head, builds `build/data.json` and commits `data/` back to `main`.

Change `.github/workflows/deploy.yml`:

```yaml
permissions:
  contents: write
concurrency:
  group: history-and-pages
  cancel-in-progress: false
steps:
  - uses: actions/checkout@v6
    with: { fetch-depth: 0 }                  # needed to rebase before pushing
  - uses: actions/checkout@v6
    with: { repository: mozilla-firefox/firefox, path: firefox }
  - name: Update history
    run: |
      python3 dev/history.py append data/history.json --repo firefox
      mkdir build
      python3 dev/history.py build-site data/history.json --repo firefox --out build   # head + merge + legacy fields
  - name: Commit history
    if: ${{ github.ref == 'refs/heads/main' && github.event_name != 'pull_request' }}
    run: |
      git config user.name 'github-actions[bot]'; git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
      git add data
      git diff --cached --quiet || { git commit -m 'data: add releases'; git pull --rebase origin main; git push origin HEAD:main; }
  - uses: JamesIves/github-pages-deploy-action@v4   # unchanged, still only on main
```

Notes: the commit step must run before the deploy step and only on `main`; a push made with the default token does not
start another run; pull-request runs compute everything but neither commit nor deploy. Remove `npm install -g mustache`
and `index.mustache` once the new page exists.

Checks: a pull-request run succeeds and uploads nothing; a manual run on `main` (use `workflow_dispatch`, add it)
appends nothing when history is current and adds exactly one line when a release is missing (test by deleting the last line
locally); two overlapping runs do not fail (concurrency group).

### Task 3: the page

Goal: replace `index.mustache` with a static page that fetches `data.json`.

1. Start from `reference/preview/history-designs.html`; follow "Changes needed before it can ship" in
   `reference/preview/README.md`. Keep the existing page's meta tags, favicon and "Fork me" ribbon (`index.mustache`),
   the title "How much Rust in Firefox?" and the date line.
2. Build the display data from `data.json`: apply `header_split`, add `Other`-free language list, derive totals, shares and
   deltas, and treat `artifact: null` and mid-series `null` values as gaps in all four views.
3. Order the views Composition, Small multiples, Language share, Pie + scrubber; default view "Non-test files", default
   scale "Share", default language Rust, default release the newest.
4. Check it in a browser at desktop and phone width, in light and dark themes, with the real data.

Checks: all four views render with real data in both themes and at 400 px width without horizontal scroll; hovering
shows the right values (spot-check three releases against `data/history.json`); the table disclosure lists the same numbers;
a `null` in the middle of the artifact series draws a gap, not a zero.

### Task 4: cleanup and documentation

Update `README.md` (how the data is built, where it lives, how to rerun the backfill), delete `dev/build-data`,
`dev/git-file-stats`, `git-file-stats.log`, `index.mustache`; keep `docs/`. Note the changed `data.json` shape in the README.

### Task 5: browser artifact for the current release (second slice)

Goal: `artifact` filled for the newest release and appended every week.

Implement the "Proposed weekly job" in the research document: resolve `gecko.v2.mozilla-central.latest.firefox.linux64-opt`
to the build and its git sha; range-read the symbols zip (`target.crashreporter-symbols.zip`) for the shipped modules;
intersect with the binaries in the same build's `target.tar.xz`; pick the non-gtest `libxul.so`; keep repository paths; fetch that
sha and count lines of those files with the same counter; JavaScript, CSS and HTML from `chrome-map.json` of the
`linux64-ccov-opt` build for the same revision; assembly left at 0 and noted. Fall back to "no artifact point this week" if any artifact is missing; never
fail the whole job. The artifact is a property of a release, so for a new release it is computed once and stored; for the head it is
recomputed each run.

Checks: Rust about 16-17% of the artifact total for Firefox 157 (2.0M Rust lines, 5.6M C++, 2.3M C, 1.8-2.0M JavaScript, from the research);
the file list for the release has 19,000-20,000 paths; the job still succeeds with the artifact step disabled.

### Task 6: artifact history (later)

Only after tasks 0 to 5 are merged and live. Releases 49 to 129 and 144 to 157 come from `candidates/`, 131.0.2 to 143 from the
saved lists in `data/artifact-files/`. Handle the three FILE record eras described in `reference/symbols/README.md`. Start with
147 to 157 (git paths); older eras need hg-prefix stripping and per-era exclusion rules. Versions that cannot be covered stay `null`.

## Verified reference results

`reference/history/backfill.sh` was run from scratch on 2026-10-05 (a developer machine, Python 3.9, fresh clone):

| Result | Value |
|---|---|
| Total time, clone to finished file | **561 s (9.4 minutes)** |
| Releases written | 112 (111 tagged majors plus 125 from `FIREFOX_125_0_BUILD1`) |
| Distinct counted files fetched and counted | 1,478,871 (1,463,367 with `mobile/` excluded) |
| Count step alone | 151 s; peak memory **2.7 GB** (the first prototype used 8.9 GB) |
| Size of `history.json` | 42,979 bytes for 112 releases (one release per line, no artifact blocks) |
| Comparison with `reference/measured/` (no `--exclude`) | **0 mismatches in 222 release-views** (Rust, JavaScript, HTML, Python, Java, Assembly exact; C and C++ exact after applying the 2/3 : 1/3 split) |

Values to compare against after a run with `--exclude mobile/` (Rust share of all counted lines, headers included in the total):

| Release | Tag | Rust lines (all) | Rust % all | Rust lines (non-test) | Rust % non-test |
|---|---|---|---|---|---|
| 46 | `FIREFOX_46_0_RELEASE` | 2,862 | 0.02% | 2,856 | 0.03% |
| 56 | `FIREFOX_56_0_RELEASE` | 1,024,084 | 4.39% | 980,362 | 7.31% |
| 66 | `FIREFOX_66_0_RELEASE` | 1,766,567 | 6.83% | 1,670,064 | 11.46% |
| 86 | `FIREFOX_86_0_RELEASE` | 3,041,592 | 9.88% | 2,787,717 | 16.40% |
| 106 | `FIREFOX_106_0_RELEASE` | 3,291,266 | 9.50% | 2,985,480 | 15.39% |
| 125 | `FIREFOX_125_0_BUILD1` | 4,279,450 | 11.29% | 3,948,161 | 18.23% |
| 127 | `FIREFOX_127_0_RELEASE` | 4,348,662 | 11.29% | 4,000,602 | 18.14% |
| 157 | `FIREFOX_157_0_RELEASE` (`fdd757a2`) | 6,172,836 | 12.71% | 5,616,315 | 21.45% |

At 157, excluding `mobile/` changes the shares from 12.67% / 21.35% to 12.71% / 21.45% and Java from 147,346 to 56,790 lines. Rust
line counts do not change. The numbers in other parts of the research document that start from the current `main` (12.8% / 21.5%) are
for a later commit and agree within 0.1 point.

Not verified: the weekly append and head steps (no code yet), a run on a GitHub runner, and the symbol-list extraction.

## Risks and things to check while implementing

- **Runner limits.** The backfill takes about 8-9 minutes and 3.5 GB on a developer machine. A standard runner has 16 GB of
  RAM and about 14 GB of free disk next to the head checkout; the streaming counter should fit, but nobody has run it there. Run the first
  backfill locally, not in the workflow.
- **Test rules on old trees.** Rules written for today's tree; earlier non-test values are less reliable. State this on the page.
- **Release 125.** Counted at `FIREFOX_125_0_BUILD1`; say so in the record (`tag`).
- **Mozilla endpoints.** The Taskcluster index, `archive.mozilla.org` and `symbols.mozilla.org` are public but not documented
  APIs. Every step that uses them must fail soft.
- **Idempotency.** Rebuilding `history.json` from scratch must give the same file apart from newly released versions.
  Compare the regenerated file with the committed one in review whenever `method_version` changes.
- **Do not build Firefox in CI.**

## Definition of done

- [ ] `data/artifact-files/` holds the lists for the expiring releases (or a README says which are lost).
- [ ] `dev/history.py` and its tests are merged; `data/history.json` has 112 major releases with `mobile/` excluded.
- [ ] The workflow appends releases, builds `data.json`, commits `data/` on `main` and deploys, and a pull-request run is green.
- [ ] The live page shows the four views with real data in light and dark themes and at phone width.
- [ ] The newest release has an `artifact` block and the page offers the Browser artifact view.
- [ ] README documents the new pipeline; the old scripts are gone.
- [ ] A fresh reviewer has read the pull requests and approved the head commit of each.
