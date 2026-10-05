# Counting the code that ships in desktop Firefox

Research for [#6 "Ignore test directories"](https://github.com/4e6/firefox-lang-stats/issues/6), widened to the
question: can the chart count only the code that ends up in the Firefox bundle, third-party libraries included,
without building Firefox on a CI runner?

- Snapshot: `mozilla-firefox/firefox` @ `00a4d527` (2026-10-05). Ground truth: Firefox 157.0 release (`fdd757a2`).
- All counts are `wc -l` newline counts (not SLOC), Linux x86-64 unless stated.
- Scope decided with the owner: **desktop browser only**. Mobile (`mobile/`, Kotlin, Java) is out of scope.

## Decision

Use **Mozilla's own CI build outputs** to learn which source files ship, then count lines of exactly those files
at the same commit. We do not build Firefox ourselves. The shipped-code series is added **next to** the existing
series, not in place of it.

Presentation: four views on one page, in this order: **Composition**, **Small multiples**, **Language share**, and
**Pie + scrubber**, over the same three views of the data (all files, non-test, browser artifact), with a share/lines scale switch
where it applies (Language share always draws all three views, and Pie + scrubber has no scale switch). See Storage
design.

## Why the current chart overstates things

The script counts every tracked file with `git ls-files | wc -l`.

| View (same language set, `.mjs` counted as JS, mobile excluded) | Rust share |
|---|---|
| Every tracked file (the script today) | 12.8% (13.1% as published; the script ignores `.mjs`) |
| Tracked files minus test paths (what #6 asks for) | 21.5% |
| **Shipped on Linux x86-64** | **about 16-17%** (16.9% nightly, 16.2% release 157) |

- **Tests are 47% of the counted lines.** WPT alone is 8.6M of 47.5M; `test262` is vendored twice (about 3M each).
- **Most Rust is vendored.** 88% of tracked Rust (5.48M of 6.25M lines) is in `third_party/rust`. Rust written by
  Mozilla outside `third_party/` is about 0.65M lines.
- **Only part of the vendored Rust ships.** About 294-318 of the 635 vendored crates contribute code to the Linux
  binaries.
- **By machine-code size, Rust is about 26% of libxul** (C++ 65%, C 4%, header-only 6%). Roughly half of the Rust is
  the standard library. This is bytes, not lines, so it does not corroborate the 16.9%.
- Python and mobile code ship nothing in the desktop bundle.

## How the exact approach works

Mozilla builds Firefox on every push. For the current version these outputs are public, need no authentication, and the
Taskcluster copies are kept for a year (older releases are covered in the History section):

| Artifact | What it gives | Size |
|---|---|---|
| `public/build/target.crashreporter-symbols.zip` | Breakpad `.sym` per shipped binary. Its `FILE` records list every source file that contributed machine code, as `git:github.com/mozilla-firefox/firefox:<path>:<commit>` | 539 MB zip; the file lists alone are about 20 MB |
| `public/build/chrome-map.json` (from the `linux64-ccov-opt` build) | Maps shipped JS/CSS/HTML to sources | 2 MB |
| `public/build/config.status` | The build configuration (for the optional assembly step) | 57 KB |

Index: `https://firefox-ci-tc.services.mozilla.com/api/index/v1/task/gecko.v2.mozilla-central.latest.firefox.linux64-opt`.
I confirmed on 2026-10-05 that it resolves to the build of `00a4d527` and that the symbols zip answers range requests.

### Proposed weekly job

1. Resolve the `latest.firefox.linux64-opt` index entry to a task id and read the git sha from its routes. Do not
   use `HEAD`: it can be ahead of the last finished build.
2. Range-read the zip directory and the `FILE` header of each shipped `.sym` (about 20 MB, about 35 s). The zip also
   holds test binaries, so intersect its modules with the binaries in the build's package (a release tarball for released versions, about
   55-90 MB; for the weekly mozilla-central build, the same task's `public/build/target.tar.xz`, 96.7 MB), streamed in a few
   seconds. The package is also where the build id of each module comes from.
3. Fetch that sha blobless (`git fetch --depth 1 --filter=blob:none origin <sha>`, about 17 MiB), then fetch only
   the referenced blobs with one `git fetch --filter=blob:none --stdin` (about 80 MB, about 45 s).
4. Classify each path by extension and count lines.
5. JS/CSS/HTML: take the file list from `chrome-map.json` of the same revision (or read a release `omni.ja`).
6. Assembly: `.asm` files do not appear in symbols (nasm objects carry no line info). Take them from moz.build
   evaluation with the downloaded `config.status`, or leave assembly out and say so.

Estimated cost: about 2 minutes and under 1 GB of disk, summed from separately measured steps. It has never been run
as one job. If the job also keeps the tracked-file series, it still needs today's full checkout (about 1 GB download,
5.7 GB on disk, about 2 minutes), so the total is the sum of both.

### Pitfalls found during the research

- `git ls-tree -l` or `git checkout` on a blobless clone fetches blobs one at a time (about 0.7 s each, hours for
  19k files). Always batch-fetch with `--stdin`.
- The symbols zip holds two `libxul.so` builds (shipped and gtest). Zip order is arbitrary. Pick the module by the
  build id found in the release tarball, or failing that by the variant without `gtest` file paths.
- Skip `FILE` records that are not tracked source: Rust standard library (`/builds/worker/fetches/rustc/...`),
  sysroot headers, and generated sources (`s3:gecko-generated-sources...`, about 3,500 records).
- The recursive GitHub trees API truncates on this repo (at about 59k entries), so it cannot replace the fetch.
- Bytes can rank languages like lines do (within 1.4 points) but cannot be obtained without downloading blobs.

## What the shipped numbers do and do not mean

The shipped figure is a **file-granularity estimate**, not a strict bound. A file counts in full if any of it
contributes machine code.

- It over-counts: inline `#[cfg(test)]` modules (about 7-12% of Rust), platform-specific branches, generic code that
  is never instantiated.
- It under-counts: generated code, assembly (see step 6), anything with no line info.
- Headers (`.h`) cannot be attributed to C or C++ exactly. The script's 2/3 : 1/3 split is stale (by location about
  81.5% of headers are C++). This only moves lines between C and C++; Rust is unaffected.
- Two independent runs agree: release 157 and nightly give Rust 1.93M vs 2.04M lines, C++ 5.44M vs 5.57M (like for
  like). That shows the method is stable across builds, not that it is exact.
- About 81% of shipped Rust lines are under `third_party/`. That is a location, not authorship: it includes
  `third_party/application-services` (Mozilla-written) and Mozilla-org crates inside `third_party/rust` (29 crates,
  about 8% of shipped Rust lines).

## History (issue #10): time and data per version, and for all releases

Issue #10 asks for older charts. This section measures what that costs. All timings come from a developer machine
(a home connection) unless marked "CI". The CI checkout of the current version (about 2 minutes, 1 GB) was
measured on real GitHub runs.

### Which versions exist

`mozilla-firefox/firefox` has 505 final-release tags of the form `FIREFOX_<n>_RELEASE` (versions 45 to 157, including
point releases and ESR), of which **111 are major releases** (`FIREFOX_<n>_0_RELEASE`, 46 to 157). Release 125 is
missing from that list: it has `FIREFOX_125_0_BUILD1` and `FIREFOX_125_0_1_RELEASE` to `_3_`, but no
`FIREFOX_125_0_RELEASE`, so the chart should use `FIREFOX_125_0_BUILD1` or 125.0.1. There are no final-release tags
before 45 (beta tags go back to Firefox 36); `main` history itself goes back to 1998, so date-based snapshots could
extend the chart, but Rust is negligible before 46 (2,862 lines at 46). Release tags sit on release-branch commits that are not reachable from
`main`, so a clone must fetch them explicitly (`git fetch origin '+refs/tags/FIREFOX_*_RELEASE:refs/tags/FIREFOX_*_RELEASE'`,
22 s and 0.13 GiB).

### Tracked-file series (what the chart shows today)

**Naive: one fresh depth-1 checkout per version.** Measured with `git clone --depth 1 --branch <tag>`:

| Version | Time | Pack download | Files |
|---|---|---|---|
| 46 | 49 s | 294 MB | 135,747 |
| 100 | 91 s | 722 MB | 306,082 |
| 157 (CI, real runs, about 480k files) | 117-125 s | about 1 GB | about 480,000 |

Adding about 40 s per version to count lines (the current script takes 37 s on a current checkout), this extrapolates to roughly
**4 hours and 75 GB** of downloads for the 111 majors and **18 hours and 340 GB** for all 505 releases. These two
totals are extrapolations from the three points above, not measured runs.

**Incremental: one blobless clone, count each distinct file once.** Successive releases share almost all files: the
111 majors list about 26M file entries but only **1,477,275 distinct counted files** (an 18x reduction); all 505
releases add only 2.2% more (1,510,333 distinct, about 33k more files) on the same language set. Measured end to end for the 111 majors:

| Step | Time | Download / disk |
|---|---|---|
| Blobless clone with full history (1.0M commits) | 90 s | 1.1 GiB |
| Fetch the release tags | 22 s | +0.13 GiB |
| `git ls-tree -r` for 111 tags (all 505 tags: 148 s) | 46 s | none (trees are local) |
| Fetch the 1,477,275 distinct counted files, 4 parallel streams | 269 s | +2.2 GB |
| Count lines of every file, then aggregate per version | 39 s | none |
| **Total** | **about 8-9 minutes** | **about 3.5 GB downloaded and on disk** |

- A single fetch stream is slower: 20,000 files took 24 s (57 MiB), which would be about 31 minutes for 1.5M files. The
  parallel run was about 7x faster than that extrapolation. Four streams were enough; I did not test more.
- All 505 releases: the same recipe, about **12 minutes by extrapolation, not measured** (`ls-tree` 148-183 s, about 33k
  more files to fetch, aggregation over 4.5x more tree entries). **Memory matters:** the prototype keeps every tag's
  tree entries in memory and peaked at 8.9 GB for the 111 majors (reviewer's rerun); all 505 tags would not fit a 16 GB
  runner and need per-tag streaming aggregation.
- Timings: the 269 s fetch covered 1,468,643 files; about 19k more came from the earlier 24 s sample. Counting plus
  aggregation took 39 s in my run and 78 s in the reviewer's rerun, so the total is **8-9 minutes**.
- This beats per-version checkouts by roughly 30x for 111 versions. For a single version, a depth-1 checkout (about
  2 minutes) is still faster than a blobless fetch of that version's files (about 360k files, about 7 minutes on one
  stream).

**Design options.** Release trees never change, so an append-only design fits: backfill the history once, then each
week compute only the new release tags (a depth-1 checkout of each, about 2 minutes) and append to the stored series.
That avoids re-downloading 3.5 GB and holding about 9 GB in memory every week. Regenerating everything weekly is
simpler but needs the streaming aggregation above, and has never been run on a CI runner (all incremental timings here
are from a developer machine).

**Where to store it.** The workflow deploys `build/` with `JamesIves/github-pages-deploy-action@v4`, whose `clean`
input defaults to true, so a history file kept only on `gh-pages` is deleted on every deploy unless each run
regenerates it or it is committed to `main` (or excluded from the clean). Pick one before implementing.

**Data to store.** Results are tiny: one record per version and view is about 0.25 KB (about 0.5 KB per version for two views), so the 111-version series with
the "all" and "non-test" views is 56 KB pretty-printed, and 505 versions would be about 250 KB. A per-file line-count
cache (1.48M files x about 24 bytes) would be about 35 MB, but it is not needed: recomputing the whole history takes
about 8-9 minutes for the majors, so regenerating it is an option (see Design options) and only the output JSON needs storing (see Storage design).

**Real series (measured, same method, 111 majors).** Language set as the script plus `.mjs`; non-test uses a
re-implementation of the path rules above in Python (it gives 21.35% for 157, against 21.4-21.45% from the git
pathspec version, so the two agree to about 0.1 point). Rust includes vendored crates.

| Version | Rust lines | Rust % (all files) | Rust % (non-test) |
|---|---|---|---|
| 46 | 2,862 | 0.02% | 0.03% |
| 56 | 1,024,084 | 4.3% | 7.1% |
| 66 | 1,766,567 | 6.7% | 11.1% |
| 76 | 2,371,967 | 8.3% | 13.7% |
| 86 | 3,041,592 | 9.8% | 16.2% |
| 96 | 3,096,054 | 9.4% | 15.2% |
| 106 | 3,291,266 | 9.4% | 15.2% |
| 116 | 3,356,027 | 9.4% | 15.0% |
| 127 | 4,348,662 | 11.2% | 17.9% |
| 137 | 4,530,117 | 11.2% | 18.1% |
| 147 | 5,090,304 | 12.0% | 19.2% |
| 157 | 6,172,836 | 12.7% | 21.4% |

Caveats: the test-path rules were written for today's tree, and older trees used other directory names, so earlier
non-test values are less reliable. Only 157 was cross-checked against another method. The numbers are the tracked-file
view, not the shipped view.

### Shipped series for older releases

Feasible for most of 45-157, but only with era-specific handling. The method is the same as for the current version
(file lists from the symbol files, line counts at the git tag). Symbols for old releases are not on Taskcluster. They
are on archive.mozilla.org under `candidates/<ver>-candidates/build<N>/linux-x86_64/en-US/firefox-<ver>.crashreporter-symbols.zip`
(not under `releases/`), and on the symbol server (Tecken). I checked the zips for 60, 100, 129, 144 and 157 (present)
and 140.0 (404).

| Versions | Source | Feasible? |
|---|---|---|
| 49-129 and ESR 52/60/68/78/91/102/115/128.x | `candidates/` zip | Yes |
| 130.0, 130.0.1, 131.0 | none (zip deleted, symbol server expired) | No; use 131.0.2 as a proxy for 131 |
| 131.0.2-143, 140.0-140.3.1esr | symbol server only, build id from the release tarball | Yes, **until the symbols expire** |
| 144-157, 140.4esr and later | `candidates/` zip | Yes |
| 45 | `candidates/` for 45.3.0esr-45.9.0esr only | Yes, through the ESR |
| 46, 48 | none | No; fall back to tracked-file counts |
| 47 | 47.0.2 zip only, no git tag for 47.0.2 | Approximate (use the 47.0.1 tree) |
| 44 and earlier | none | No |

- **There is a deadline, and it is days away.** The symbol server appears to delete symbols about two years after
  upload (inferred from probes; the mechanism, upload age or last access, is undocumented). On 2026-10-05 libxul for
  131.0 (built 2024-09-23, debug id `346A619AA15B85ECD0F409165F54E6F90`) returns 404, while 131.0.2 (built 2024-10-08,
  `4CF815C463F6367F0E0432563847F4FE0`) still returns 200. If expiry is two years from build, 131.0.2 goes around
  2026-10-08, and then roughly one release every 2-4 weeks. Releases 131.0.2 to 143 live only there, so their file
  lists should be extracted **now**, oldest first, and kept (about 1-2 MB per module). Use 131.0.2 as the proxy for 131
  only while it lasts.
- **The 130-143 hole in `candidates/` is unexplained.** ESR builds from the same months are intact, so other zips may
  also vanish without notice.
- **Formats change.** Versions 45-56 use `hg:hg.mozilla.org/releases/mozilla-release:<path>:<12-char rev>`; 57-146 use `hg:` too (12-char
  revs at 57, 40-char by 60; generated code under `s3:gecko-generated-sources` from 57); 147 and later use `git:`. The hg
  path maps to the git tag's tree by stripping the prefix and revision: 0 missing paths for 91, 102, 106, 115, 128, 129,
  135, 143, 144, 140.17esr, 150 and 157. For 45-78 there are 57-103 unmatched paths (toolchain headers, `obj-*`,
  absolute paths), which need per-era exclusion rules.
- **Per-version cost.** About 55-110 MB and 30-60 requests (release tarball 53-89 MB, which must be streamed to find
  the shipped modules and their build ids, plus 1-20 MB of symbol headers), roughly 5-15 s of network time. For 111
  majors that is about 8-11 GB of transfer and an estimated 20-30 minutes of network time. These are estimates; no
  whole series was run. Line counts reuse the blobs already fetched for the tracked series.
- **The real cost is engineering, not compute.** Three FILE record eras, per-era exclusion rules, build-id based module
  selection, and the missing versions. A first version could cover only 147-157 (`git:` paths, about 11 majors; 144-146 are
  still `hg:` and need the prefix stripping) and add earlier eras later.
- A static fallback (config.status plus BuildReader) is not verified for old trees: `candidates/` has no
  `config.status`, and old trees likely need Python 2.

### Summary: time and data

| | Time | Download / disk | Stored output |
|---|---|---|---|
| One version, tracked (today) | about 2.3 min (CI) | about 1 GB / 5.7 GB | a few KB |
| One version, shipped (new) | about 2 min (estimate) | about 150-250 MB | a few KB |
| 111 majors, tracked, per-version checkouts | about 4 h (extrapolated) | about 75 GB | 56 KB |
| **111 majors, tracked, incremental** | **about 8-9 min (measured)** | **about 3.5 GB** | **56 KB** |
| 505 releases, tracked, incremental | about 12 min (extrapolated) | about 3.5 GB, memory needs streaming | about 250 KB |
| 111 majors, shipped | about 30 min of network (estimate) plus engineering | about 8-11 GB | about 1-2 MB per module if lists are kept |

## Storage design

The history page has four views, in this order. An interactive preview with sample data was built for them; the
"Browser artifact" series in it is made up. In this document "browser artifact" means the same thing as "shipped"
above: the lines of the files that end up in the desktop browser.

| # | View | What the reader can switch | What it reads |
|---|---|---|---|
| 1 | **Composition** | view (all files, non-test, browser artifact), scale (share or lines), click a language to isolate it | every language, every release |
| 2 | **Small multiples** | view, scale (share or lines) | every language, every release |
| 3 | **Language share** | language, scale (share or lines); always draws all three views as lines | one language, every release, all three views (in share mode it also needs the total, which is every language) |
| 4 | **Pie + scrubber** | view, a release slider with Play; shows change against the previous release | every language, one release (and its predecessor) |

All four views are drawn from the same record: **lines per language, per release, per view**. Shares, totals and
the change against the previous release are computed in the browser, so none of them is stored. The only
difference between views is how much of the file they read.

### What is stored, and where

**One append-only file in the repository, `data/history.json`, committed to `main`.** One release per line, so a
new release is a one-line diff and git history stays readable. Releases are immutable, so a stored point never
changes unless the counting method changes (see below). Proposed record (illustrative numbers based on the Firefox 157
measurements; in the real file `c` and `cpp` exclude headers, which are the separate `h` column, and the `artifact`
block holds placeholders):

```json
{"method_version":1,"releases":[
{"v":157,"tag":"FIREFOX_157_0_RELEASE","sha":"fdd757a2e09c9471cddf383e64e631e4ce178499","date":"2026-09-24",
 "all":    {"rust":6172836,"c":5684104,"cpp":11190622,"h":1500000,"js":16229210,"html":6839860,"py":2159226,"java":147346,"asm":295963},
 "nontest":{"rust":5616315,"c":5509719,"cpp":10268555,"h":1400000,"js":2997940,"html":197874,"py":1281628,"java":137247,"asm":295548},
 "artifact":{"platform":"linux-x86_64","sha":"fdd757a2e09c9471cddf383e64e631e4ce178499","rust":0,"c":0,"cpp":0,"h":0,"js":0,"html":0,"py":0,"java":0,"asm":0}}
]}
```

- **Scope:** `all` and `nontest` should exclude `mobile/`, matching the desktop-only decision. The preview and the
  measured series so far include it (Java is 147k lines at 157, against about 56k outside `mobile/`), so the first
  backfill must apply the exclusion; Rust is 12.7% / 21.4% with it and 12.8% / 21.5% without it. Java and Assembly stay
  separate columns because the views show them separately, even though Java is small without `mobile/`.
- **Languages:** Rust, C, C++, JavaScript (including `.mjs`), HTML/CSS, Python, Java and Assembly. Java and Assembly are
  separate columns because the views show them separately.
- **`artifact` is `null`** until the browser-artifact collector exists, and for releases it cannot cover (46, 48, 130,
  131.0, 45.0esr and 45.2.0esr if all releases are stored, and releases 131.0.2 to 143 if their symbol file lists are not
  extracted in time, see Suggested order). Until the collector exists, the page hides the browser-artifact option. The page must handle missing values in the middle of the series in all four views: in the preview only Language share
  does, and the other three assume gaps are at the start (stacks drop to zero, small multiples break the line, and the pie's
  "change against the previous release" would compute against nothing). Its `sha` records which commit
  the file list was counted at. `platform` is only needed if more than one platform is ever stored (Open decision 1).
- **Headers (`h`) are stored raw** and split between C and C++ when the page is drawn, using a ratio kept as metadata in
  the file (`"header_split":{"c":0.185,"cpp":0.815}`). The current 2/3 to 1/3 split is out of date (by location about
  81.5% of headers are C++). Changing the ratio rewrites how past releases are displayed without recomputing anything, so
  it is a metadata change, not a `method_version` bump; say so in the commit that changes it.
- **`date`** is the date of the release tag's commit. The preview uses the version number as the x axis (releases are
  about four weeks apart); the date keeps a calendar axis possible for one field per release.
- **Totals are not stored.** The total is the sum of the language columns, and the test lines of a release are
  `all` minus `nontest`.

**The current head is not stored in git.** It changes every week and has no lasting value. The weekly job computes it
fresh from its checkout and merges it with `data/history.json` into `build/data.json`, which is deployed to `gh-pages` as today. The current
page bakes its numbers into `index.html` with Mustache; the new page either fetches `data.json` next to it or the build
inlines it, which is a choice for the implementation. This also avoids a problem with the deploy step: it wipes `gh-pages` on
every run by default, so history kept only there would be deleted.

### Size

Projected from the real series (compact JSON, one release per line; the sha, date and `h` values are synthetic):

| | Per release | 111 majors | All 505 releases | Growth per year |
|---|---|---|---|---|
| Tracked views only (`all`, `nontest`) | about 0.4 KB | about 43 KB | about 190 KB (estimate) | about 5 KB (13 majors) or about 20 KB (about 50 releases) |
| With the `artifact` block | about 0.6 KB | about 64 KB | about 290 KB (estimate) | about 8 KB or about 30 KB |

This is negligible for git. Pretty-printed it would be about 1.3 to 2 times larger depending on indentation, and every release would touch many
lines, so keep one release per line.

### Updating it

1. The weekly job lists the remote release tags with `git ls-remote --tags` (the workflow's checkout is depth 1 and has
   no tags) and compares them with `data/history.json` by version number `v`. The release set follows Open decision 2:
   for majors only, the pattern is `FIREFOX_<n>_0_RELEASE`. If point releases or ESRs are added, `v` must become the full
   version string (for example `"140.3.1esr"`), and the "previous release" in the pie and the x axis need a rule.
2. For each missing release it computes the record (a depth-1 checkout of that tag, about 2 minutes) and appends it.
   When a major has no `_0_RELEASE` tag (125 has only `_BUILD1` and `125.0.1`), use the nearest tag, store it under
   `v: 125`, and say so in the record, so it is not fetched again every week. The majors-only file then has 112
   records (111 tagged majors plus 125).
3. It computes the head point and merges everything into `build/data.json`.
4. It commits the appended line to `main` directly (decided; branch protection on `main` was not checked, and a protected
   branch would force a pull request instead). The workflow also runs on `pull_request` and on every push to `main`, so gate the commit
   step like the Deploy step, put it in a `concurrency` group, and rebase before pushing so a push run and the cron run
   cannot race. A push made with the default token does not trigger another run, which is what we want here.

The first run backfills the majors with the incremental method from the History section (about 8-9 minutes, about
3.5 GB on a developer machine, with a memory peak of 8.9 GB; on a standard runner with 16 GB of RAM and about 14 GB of
free disk next to the head checkout this is tight and has not been tried). After that, a normal week adds nothing except the head, and a release week adds one record.

### One counter

Use a single counter for the backfill, the weekly append and the head point: it takes a tree listing of a commit
(`git ls-tree -r`) and counts lines per file, and it works on a depth-1 checkout as well as on a blobless clone. Do not
reuse today's `dev/build-data` for the new data: it has no `.mjs`, no non-test view and no raw headers, and uses the
2/3 header split. Mixing counters would put seams in the series (the Python and git-pathspec test rules already differ
by about 0.1 point at 157). One counter is also what makes the rebuild below idempotent.

### When the method changes

Each file carries a `method_version`. Anything that changes the numbers (the language set, the test-path rules, the
header handling) bumps it and requires recomputing every release, about 8-12 minutes with the incremental method.
The script that builds the history must be idempotent so that a full rebuild is one command, and the diff of the
regenerated file shows exactly what moved. Test-path rules written for today's tree apply to older trees that used
other directory names, so earlier non-test values are less reliable than recent ones.

### Not stored on purpose

- **A split of lines into tests, `third_party` and the rest.** None of the four views needs it, and `all` minus
  `nontest` already gives test lines. Adding it later means one full recompute (8-12 minutes), so it is cheap to defer.
  Store it now only if a "vendored vs written by Mozilla" toggle is planned.
- **File lists.** The records hold counts only. The exception is the list of source files behind each release's browser
  artifact, for releases 131.0.2 to 143 (and 140.0esr to 140.3.1esr), whose symbols exist only on a server that appears
  to delete them after about two years (see History). Without the list, the counts of those releases cannot be
  recomputed after a method change. What has to be kept is small: only the sorted repository paths, one per line,
  deduplicated across modules. Measured on release 157: 19,124 paths, 0.79 MB as text, 112 KB gzipped (the nightly list is
  similar). A simulation of 14 consecutive lists with 3% change between releases (synthetic, real churn is unknown) packs
  into about 200 KB in git when stored as plain text, because git deltas similar lists. The JavaScript side does not
  expire: the release tarballs stay on `archive.mozilla.org/pub/firefox/releases/`.

  Options for where to keep them (option 1 decided, see below):

  | Option | Cost | For | Against |
  |---|---|---|---|
  | 1. `data/artifact-files/<version>.txt` on `main` (plain sorted text) | about 0.8 MB per file in the checkout, about 200 KB for 14 releases in git history (estimate) | Simplest. Same workflow and permissions. Diffable and reviewable. Moves easily to another option later | Adds data files to `main`; they stay in history |
  | 2. Same files on an orphan `data` branch | Same size | Keeps `main` clean | A second long-lived branch to explain and check out in the workflow |
  | 3. GitHub Release assets (one `.txt.gz` per version) | about 112 KB each | Out of git history; easy to delete or replace | Needs API calls in the workflow; not diffable; tied to the repository |
  | 4. Keep counts only | none | No upkeep | After a method change those releases are either frozen at the old method or dropped from the series |
  | 5. External archive (Zenodo, Internet Archive, own bucket) | none in the repo | Permanent, citable | A new outside dependency and a public upload for 200 KB of data |

  **Decision: option 1, only for the expiring releases** (131.0.2 to 143 and 140.0esr to 140.3.1esr). The lists go in
  `data/artifact-files/<version>.txt` on `main`: sorted repository paths, one per line, plain text so that git can delta
  them. Lists are not kept for other releases. The file for a release whose symbols are still available elsewhere can be
  rebuilt from `candidates/` or the release tarball, so only the expiring range needs a copy. If `candidates/` loses
  more builds, add those releases to the directory before their zips disappear. Provenance (tag, commit, symbol source, build id of each module) goes in the
  release's `artifact` block in `history.json`, not in the list file.

## What is not counted

Shipped code that is not in the git tree: the `windows` crate (1.83M lines, fetched at build time, Windows builds
only), onnxruntime (prebuilt), wasi-libc (linked into six sandboxed libraries), the Rust standard library and libc++
from the toolchains. The symbol approach does not see these as repo files.

## Limits and risks

- **One platform.** Verified for Linux x86-64 only. Windows and macOS ship different crates (the union of the Linux, Windows
  and macOS crate sets is about 0.55M lines larger than Linux alone). The Windows `FILE` records for the `windows` crate will not
  resolve to git paths, so that code would be silently dropped. Label the chart "Linux x86-64".
- **Dependence on Mozilla infrastructure.** Taskcluster index, artifacts and the symbol server are public but are not
  a documented stable API. The Taskcluster copies expire after one year, but older releases have symbols elsewhere (see
  History). `coverage.moz.tools` has no DNS record any more; do not use it.
- **Fallback without the artifacts:** the official `config.status` plus mozbuild `BuildReader`, `cargo tree --offline`
  on the vendored crates, and `jar.mn` parsing. This needs only Python 3.10+ and cargo. It gives an upper bound that
  overstates Rust about 2.2x (4.54M lines reachable vs about 2.0M that ship), so it is a fallback, not a stats source.
- A real build on a free runner is impractical: the docs ask for 30 GB or more of disk against about 14-22 GB free,
  and I did not measure a cold build (Mozilla's own warm-cache build takes 7 minutes on 16 vCPU).

## Related fixes the script needs regardless

- Count `*.mjs` (1.52M lines; `*.sys.mjs` is 0.98M). After excluding tests, JS is undercounted by about 47% without it.
- Relabel the chart from "SLOC" to "lines". Real SLOC moves the Rust share by only about 1 point.
- Update or drop the 2/3 : 1/3 header split.
- With mobile out of scope, no Kotlin slice is needed (all of it is in `mobile/`), and the "Java" slice nearly
  disappears (about 56k lines outside `mobile/`).
- Path-based test exclusion beats test manifests, which miss 4.4M lines of tests. A verified exclusion snippet gives
  22.66% Rust on the current language set (21.4% with `.mjs`). The patterns that matter: `testing/**`,
  `js/src/tests/**`, `js/src/jit-test/**`, any `test`/`tests` directory, plus Rust `tests.rs`, `*_test.rs`.

## Open decisions

1. Linux x86-64 only (recommended, labelled), or also Windows and macOS?
2. Add the shipped chart beside the existing one (recommended; keeps history from issue #10 comparable), or replace it?
   For history, majors only (111 versions) or every release (505)?
3. What "shipped" should mean for the chart: lines in files that contribute code (about 17% Rust), or machine-code
   bytes (libxul about 26% with the standard library, about 15% without)?
4. Depend on Mozilla's CI artifacts in the weekly cron, with the static fallback if they are missing?
5. Storage: keep raw header counts and a test/`third_party`/rest split now, or defer the split? The weekly update is committed to `main` directly, and the expiring symbol file lists are kept in
   `data/artifact-files/` on `main` for 131.0.2-143 and 140.0esr-140.3.1esr only (both decided).

## Suggested order

1. Issue #6: path-based test exclusion plus `*.mjs`, showing "all" and "non-test" views.
2. **Time-critical, independent of everything else:** extract the symbol file lists (not the zips) for releases
   131.0.2-143 and 140.0esr-140.3.1esr from the symbol server before they expire, and commit them to
   `data/artifact-files/` (see History and Storage design).
3. Issue #10, tracked-file history for all major releases (about 8-9 minutes, measured, see History), stored as in
   Storage design, with the four views.
4. Prototype the shipped series for the current version as a separate, clearly labelled chart.
5. Remaining shipped history (49-129 and 144-157 from `candidates/`).
6. Do not build Firefox in CI.

## Method and verification

Four independent researchers covered the vendored-code inventory, build-graph recovery, test exclusion and counting
method, and bundle and CI cost. A fresh reviewer then reproduced the headline numbers (the current script totals, the
non-test split, the shipped Rust count, crate counts, the chrome-map and `omni.ja` JS counts, and the live endpoints)
over two rounds. The History section was measured directly (blobless full clone, fetch and count of all 1,477,275
distinct counted files of the 111 majors, depth-1 checkouts of 46 and 100) plus a researcher survey of symbol availability
for 553 `candidates/` directories, spot-checked by me (zips for 60, 100, 129, 144, 157 present; 140.0 absent). Not independently verified: the range-read and batch-fetch timings, the BuildReader 3-5 s claim, the
`windows` crate size, and the Kotlin and SLOC figures. Windows/macOS symbols and the desktop SBOM were not examined.
