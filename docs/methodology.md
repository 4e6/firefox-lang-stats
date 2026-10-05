# Methodology

How the numbers on [How much Rust in Firefox?](https://4e6.github.io/firefox-lang-stats/) are produced, what they
mean and how far to trust them. Every rule below is taken from the code that produces the data (`dev/history.py`,
`dev/artifact.py`, `dev/artifact-files`, `.github/workflows/deploy.yml`). Figures are as of 2026-10-05 unless a
date is given; where a figure comes from an earlier measurement, the source is named.

## In short

The page counts **lines in files**, grouped into eight languages by file extension, for every major Firefox release
from 46 to the newest one and for the current head of the default branch of
[mozilla-firefox/firefox](https://github.com/mozilla-firefox/firefox). It offers three views of the same releases:

| View | What is counted | Releases covered |
|---|---|---|
| All files | Every file tracked by git at the release tag (or the head) with a counted extension | All 112 major releases and the head |
| Non-test files | The same files minus those under test directories or with test file names | All 112 major releases and the head |
| Browser artifact | Only the source files compiled into the Linux x86-64 desktop binaries of Mozilla's own build, plus the JavaScript, HTML and CSS packed inside its `omni.ja` archives | Release 157 and the head (other releases are gaps) |

`mobile/` is excluded from all three. A release without data in a view is drawn as a gap, never as zero.

Firefox 157 (`FIREFOX_157_0_RELEASE`, commit `fdd757a2`) in the three views, headers split as described below:

| Language | All files | Non-test files | Browser artifact |
|---|---:|---:|---:|
| C++ | 11,941,177 (24.6%) | 10,987,092 (42.0%) | 5,713,470 (48.2%) |
| Rust | 6,172,836 (12.7%) | 5,616,315 (21.4%) | 1,931,822 (16.3%) |
| C | 4,931,208 (10.2%) | 4,788,840 (18.3%) | 2,014,788 (17.0%) |
| JavaScript | 16,201,531 (33.4%) | 2,973,279 (11.4%) | 1,981,942 (16.7%) |
| HTML/CSS | 6,828,311 (14.1%) | 195,821 (0.7%) | 211,893 (1.8%) |
| Python | 2,150,644 (4.4%) | 1,275,464 (4.9%) | 0 (does not ship) |
| Java | 56,790 (0.1%) | 55,497 (0.2%) | 0 (does not ship) |
| Assembly | 295,963 (0.6%) | 295,548 (1.1%) | not counted |
| **Total** | **48,578,460** | **26,187,856** | **11,853,915** |

C and C++ include their share of the `.h` lines (fractional lines are rounded here).

## What a "line" is

- A line is a **newline character** in the file's content (`content.count(b'\n')`, the same as `wc -l`). A last line
  without a trailing newline is not counted.
- It is **not SLOC**: blank lines, comments and licence headers count like code. The research estimated that real SLOC
  would move the Rust share by only about 1 point (`docs/shipped-code-research.md`; that figure was not independently
  re-checked).
- It is **lines in files, not authored code**. Vendored third-party code is included: at the research snapshot 88% of
  tracked Rust (5.48M of 6.25M lines) was in `third_party/rust`, and about 81% of the shipped Rust lines were under
  `third_party/` (also a research-snapshot figure, not re-measured on the stored artifacts) (a location, not authorship: it includes Mozilla-written crates such as
  `third_party/application-services`).

## Which files

The tracked series read git objects only, never a working tree: `git ls-tree -r <commit>` lists every entry of the
commit's tree and `git cat-file --batch` reads the content of each counted blob once.

- Every tree entry of type `blob` whose path ends in a counted extension is counted. This includes files that git
  tracks but the build never uses.
- **Symbolic links** are blobs too (mode `120000`), so a link with a counted extension is counted; its content is the
  link target, normally with no newline, so it adds 0 lines. At commit `00a4d527` of 2026-10-05 there are none
  with a counted extension outside `mobile/`.
- **Submodules** (tree entries of type `commit`) are skipped. The repository has none at `00a4d527`.
- **Binary files are not detected.** If a file has a counted extension, its newline bytes are counted whatever it
  contains.
- Paths under `mobile/` are skipped (a prefix match on the path, stored as `excluded_prefixes` in
  `data/history.json`, so every new record uses the same exclusion). Desktop Firefox only: Mozilla's Android code
  and most of its Java and Kotlin live there. At release 157, excluding `mobile/` lowers Java from 147,346 to 56,790 lines
  and moves the Rust share from 12.67% to 12.71% (all files) and from 21.35% to 21.45% (non-test); Rust lines do not
  change.

### Extensions

Matching is case-sensitive and uses the last extension only (`foo.sys.mjs` counts as `.mjs`; `.C` or `.JS` would not
be counted; there are no such files outside `mobile/` at `00a4d527`).

| Key in the data | Shown as | Extensions |
|---|---|---|
| `rust` | Rust | `.rs` |
| `c` | C | `.c` |
| `cpp` | C++ | `.cc` `.cpp` `.cxx` `.hxx` |
| `h` | split between C and C++ | `.h` |
| `js` | JavaScript | `.jsm` `.jsx` `.js` `.mjs` |
| `html` | HTML/CSS | `.htm` `.html` `.xhtml` `.xht` `.css` |
| `py` | Python | `.py` |
| `java` | Java | `.java` |
| `asm` | Assembly | `.asm` |

Everything else is left out, both from the language lines and from the total that shares are computed against.
Measured for this document at `00a4d527` outside `mobile/`, some sizeable uncounted source extensions (examples, not
a complete ranking; `moz.build` files, for instance, hold 230,981 lines and `.idl` files 131,262):

| Extension | Files | Lines |
|---|---:|---:|
| `.hpp` (C++ headers) | 1,102 | 602,053 |
| `.ts` (TypeScript) | 2,084 | 567,724 |
| `.inc` | 149 | 261,262 |
| `.S` (assembly, preprocessed) | 231 | 199,506 |
| `.mm` (Objective-C++) | 422 | 136,602 |
| `.hh` (C++ headers) | 287 | 115,656 |
| `.s` (assembly) | 62 | 38,533 |

Nine of the `.ts` files are binary MPEG transport streams (media test files), not TypeScript; they hold 33,851 of
those lines. `.hpp`, `.hh`, `.mm` and `.S` were left out to keep the language set of the original chart (plus `.mjs`); adding any
of them is a method change (see "Changing the method").

### Headers

`.h` files can be C or C++, and the extension does not say which. The data keeps their lines apart, as `h`, and the
page splits them at display time with the ratio stored in the data (`header_split`): **18.5% to C and 81.5% to C++**.
The ratio comes from the research (`docs/shipped-code-research.md`: "by location about 81.5% of headers are C++"),
which replaced the old chart's 1/3 to 2/3 split. The repository records only that figure, not how it was derived
or on which commit, and the same ratio is applied to every release and to all three views, so treat the C/C++
boundary as approximate. The split moves lines between C and C++ only; the Rust share and the
totals do not depend on it.

## The three views

### All files

Every counted file at the commit, as above. This is the closest to what the original chart measured (that chart did
not count `.mjs`, included `mobile/` and split headers 1/3 to 2/3). It is dominated by tests: at the research
snapshot, tests were 47% of the counted lines (web-platform-tests alone 8.6M lines; `test262` is vendored twice,
about 3M lines each).

### Non-test files

The same files minus test paths (`is_test()` in `dev/history.py`). A path is a test path if any of these hold:

1. It starts with `testing/`, `js/src/tests/`, `js/src/jit-test/`, `js/src/jsapi-tests/`, `js/src/octane/` or
   `third_party/webkit/PerformanceTests/`.
2. Any directory in it is named `test`, `tests`, `gtest`, `gtests`, `mochitest`, `mochitests`, `xpcshell`, `reftest`,
   `reftests`, `crashtest`, `crashtests`, `__tests__`, `androidTest`, `test262`, `unittests`, `googletest`, `testdata`,
   `fixtures`, `browser_tests`, `jsapi-tests` or `jit-test`; or ends in `-test`, `-tests`, `_test` or `_tests`; or
   starts with `test-`, `tests-`, `test_` or `tests_`; or is a `testing` directory below the top level.
3. It is a Rust file named `tests.rs`, `test.rs`, or ending in `_test.rs` or `_tests.rs`.

How the rules were made and checked:

- They were derived by hand from **today's tree** during the research. Older trees used other directory names, so
  **non-test values for older releases are less reliable**. No release other than 157 was checked against a second
  method.
- A second implementation as git pathspecs (`docs/reference/test-paths/build-data-pathspec.sh`) gave 21.4-21.45%
  Rust on `main`, against 21.35% from the Python rules on the 157 tag: about 0.1 point apart, on different commits,
  so not an exact match. The two forms are close but not identical (the pathspec script has no `.mjs`, keeps
  `mobile/`, and matches `jsapi-tests` and `jit-test` only under `js/src/`).
- Detecting tests from test manifests (mochitest, xpcshell and similar) was tried and rejected: it misses 4.4M lines
  of tests.
- Test code inside non-test files is not removed: inline Rust `#[cfg(test)]` modules (about 12% of non-vendored and 7%
  of vendored Rust, from the research) count as non-test.

See `docs/reference/test-paths/README.md`.

### Browser artifact

The source files that are **compiled into the shipped Linux x86-64 desktop binaries**, learnt from Mozilla's own
build outputs (Firefox is never built here), plus the JavaScript, HTML and CSS **as shipped** inside the build's
`omni.ja` archives. Implemented in `dev/artifact.py`; every step is standard-library Python and git.

1. **Find the build.** For the head, the Taskcluster index `gecko.v2.mozilla-central.latest.firefox.linux64-opt`
   gives the newest finished mozilla-central build; the task must be `completed`, and its routes carry the build's
   revisions (an hg one and a git one). For a release, the URLs of a release candidate build under
   `https://archive.mozilla.org/pub/firefox/candidates/<v>.0-candidates/build<N>/linux-x86_64/en-US/` are given by
   hand to `history.py set-artifact`; the rule is to use the last `build<N>` (157: `build1`, the only one).
   Choosing them automatically is part of Task 6.
2. **Read the package once.** The build's package (`target.tar.xz`, or `firefox-<v>.0.tar.xz` for a release) is
   streamed once. For every ELF file it reads the GNU build id from the headers at the start of the file; for every `omni.ja`
   (`omni.ja` and `browser/omni.ja`) it counts the newlines of the `.js`, `.mjs`, `.jsm`, `.jsx`, `.css`, `.html`,
   `.htm`, `.xhtml` and `.xht` files inside.
3. **Pick the shipped modules in the symbols.** The build's `crashreporter-symbols.zip` holds a Breakpad `.sym` file
   per binary, keyed by module name and debug id. The debug id is derived from the build id (the first 16 bytes as a
   GUID with the first three fields byte-swapped, plus `0`). Only modules that are in the package are read, matched by
   name and debug id: the zip also holds test binaries and a second, gtest `libxul.so`, and the debug id selects the
   shipped one. A run without exactly one matching `libxul.so` fails. The zip is read with HTTP range requests: its
   directory, then only the `MODULE`, `INFO` and `FILE` lines at the top of each chosen `.sym` (about 15.6 MB of
   539 MB).
4. **Keep repository paths.** Each `FILE` record names a source file that contributed machine code. Records of the
   form `git:github.com/mozilla-firefox/firefox:<path>:<sha>` are kept as `<path>`. Dropped: generated code
   (`s3:gecko-generated-sources`), other repositories (`git:github.com/rust-lang/rust`, the Rust standard library),
   absolute paths (compiler, sysroot, Rust toolchain and crate registry, glibc, and files in the build's object
   directory `/builds/worker/workspace/obj-build`), `obj-*` and `<...>` pseudo-paths. For the head build of
   2026-10-05 that kept 19,978 paths and dropped 3,499 generated, 1,589 absolute-path and 852 other-repository records.
5. **One commit.** Every kept record must name the same git sha; otherwise the run fails. For the head that sha must
   be one of the task's route revisions; for a release it must be the release tag's commit. This sha is the commit
   the artifact is counted at, stored as `artifact.sha`.
6. **Count.** The Rust, C, C++, header, Python and Java lines of those paths at that commit, with exactly the
   tracked-series rules (same extensions, newline count, `mobile/` skipped). The commit's trees and the needed blobs
   are fetched into a throwaway repository that borrows the checkout's objects, so the checkout is never modified.
   Paths missing from the tree are reported (0 for the head build of 2026-10-05; not recorded for 157).
7. **Combine.** `js` and `html` come only from `omni.ja`, everything else only from the file pass, so nothing is
   counted twice (the run reports any JavaScript, HTML or assembly path the symbols name; for the head build of
   2026-10-05 there were none).

What this view does and does not include:

- **JavaScript, HTML and CSS are shipped lines**, after Mozilla's preprocessing and bundling, not the source files
  they come from. The implementation plan puts them at about 9% more lines than the corresponding source files. For
  157 they are 1,001,575 + 980,367 JavaScript lines in the two `omni.ja` files.
- **Assembly is not covered.** nasm objects carry no line information, so `.asm` files never appear in the `FILE`
  records. The data stores 0 and the page shows "not counted".
- **Python and Java do not ship** in the desktop binaries; they are 0.
- A file counts in full if any of it contributed machine code. This over-counts (platform branches, `#[cfg(test)]`
  modules, generic code never instantiated) and under-counts (generated code, anything without line information). It
  is a file-granularity estimate, not a bound.
- The head's artifact is counted at the build's own commit, which can differ from the head counted by the other two
  views: in the weekly job the newest finished build usually lags the default branch a little, and in a local run
  against an older checkout it can even be newer. In the workflow runs of 2026-10-05 both were `0b3661d5`. The page
  names the build commit wherever the head's artifact appears, including the headline.
- Nothing checks the build's age: if mozilla-central builds broke for a while, the index would keep pointing at the
  last good build and the page would show it as the head's artifact, with its commit but no date.

**Coverage.** Release 157 (stored in `data/history.json`) and the head (recomputed every run, never stored). Every
other release is `null` and drawn as a gap. Releases appended by the weekly job also get `null`: computing their
artifact automatically, and the artifacts of older releases, is Task 6 of `docs/implementation-plan.md` and is **not
done**.

**Saved symbol lists.** For releases 131.0.2 to 143.0.4 and 140.0esr to 140.3.1esr (45 versions) the symbols exist
only on Mozilla's symbol server (`symbols.mozilla.org`, Tecken), which appears to delete them about two years after
the build (inferred from probes; the mechanism is undocumented), and their `candidates/` zips are gone. Their path
lists were captured with `dev/artifact-files` on 2026-10-05 and committed to `data/artifact-files/<version>.txt` so
that those releases can still be counted later. They are **not used by any view yet**. See
`data/artifact-files/README.md`.

## Releases and dates

- **Release set:** major releases, `FIREFOX_<n>_0_RELEASE` for n = 46 up to the newest major that has such a tag.
  Release 125 has no `FIREFOX_125_0_RELEASE` tag and is counted at `FIREFOX_125_0_BUILD1`, stored under `v` = 125 with
  that tag in its record (the page notes this under the chart). A newer major that has only `BUILD` tags is not added
  until its `_RELEASE` tag exists. 112 releases today (46 to 157). Point releases and ESRs are not included.
- **Date:** the committer date of the counted commit (`git log --format=%cs`). Some converted commits carry a zero
  timestamp (1970-01-01; among the 112 counted tags only `FIREFOX_123_0_RELEASE`); for those the date of the nearest first-parent ancestor
  with a real timestamp is stored. The weekly job fetches 10 more commits of such a tag to find it.
- **x axis:** releases are placed one step apart in release order (by index, not by date); the head is one step after
  the newest release. Dates appear in the scrubber and the data, not on the axis.
- **Immutability:** a stored release is never recounted by the weekly job, and a stored artifact is never overwritten
  (`set-artifact` refuses).

## The head point

The head is the commit the workflow's depth-1 checkout of `mozilla-firefox/firefox` lands on (the tip of the default
branch). It is counted on every workflow run with the same counter as a release, and its browser artifact is computed
from the newest finished mozilla-central build (see above). It lives only in the deployed `build/data.json`, never in
`data/history.json`, because it changes every week. If the head artifact cannot be computed (Mozilla endpoints down,
no finished build, its 15-minute limit in the workflow, even a bug), `head.artifact` is `null` and the run goes on.

## The weekly pipeline

`.github/workflows/deploy.yml` runs every Sunday at 22:12 UTC, on every push to `main`, on pull requests and by hand.
One job, at most one run at a time per branch, 30-minute limit:

1. **Test:** `python3 -m unittest discover -s dev` (no network).
2. **Append:** `history.py append data/history.json --repo firefox` lists the remote release tags
   (`git ls-remote --tags`), and for each major missing from the file fetches its tag at depth 1, counts it and
   appends one line, with `artifact: null`.
3. **Build:** `history.py build-site ... --with-artifact --artifact-deadline 900` counts the head, computes the head
   artifact and writes `build/data.json`; the page, its icons and this document (rendered to `methodology.html` by
   `dev/render_docs.py`) are added; a check fails the step if any output file is empty, if the releases in
   `build/data.json` differ from `data/history.json`, or if there is no head point.
4. **Commit** (only on `main`, never for a pull request): if `data/` changed, commit `data: add releases` to `main`.
5. **Deploy** (only on `main`, never for a pull request): publish `build/` to the `gh-pages` branch.

A failure in steps 1 to 3 commits and deploys nothing.

## Data files

### `data/history.json` (committed)

One header line, then one release per line (a new release is a one-line diff). Shortened:

```
{"method_version":1,"excluded_prefixes":["mobile/"],"header_split":{"c":0.185,"cpp":0.815},"releases":[
{"v":157,"tag":"FIREFOX_157_0_RELEASE","sha":"fdd757a2...","date":"2026-09-24",
 "all":{"rust":6172836,"c":3992382,"cpp":7805270,"h":5074733,"js":16201531,"html":6828311,"py":2150644,"java":56790,"asm":295963},
 "nontest":{...the same nine keys...},
 "artifact":{...the same nine keys...,"sha":"fdd757a2...","source":{"kind":"candidates","symbols":"<url>","package":"<url>",
             "libxul_debug_id":"87478A7A722AC28D02CE6A36E9A614340","modules":26,"paths":19289}}}
]}
```

| Field | Meaning |
|---|---|
| `method_version` | Version of the counting rules the records were made with (1) |
| `excluded_prefixes` | Path prefixes skipped in every view (`mobile/`) |
| `header_split` | Share of `h` lines given to C and to C++ at display time |
| `v`, `tag`, `sha`, `date` | Major version, the tag counted, its commit and the commit's date |
| `all`, `nontest` | Lines per language key; `c` and `cpp` exclude headers, which are `h` |
| `artifact` | `null`, or the nine language keys plus `sha` (the commit counted) and `source` (where the file list came from: `kind`, the build's URLs or Taskcluster index and task, the `libxul.so` debug id, the number of modules read and of paths kept) |

Totals are not stored: a total is the sum of the nine language keys, and test lines are `all` minus `nontest`.

### `build/data.json` (deployed as `data.json`)

`data/history.json` plus a `head` object (`sha`, `date`, `all`, `nontest`, `artifact`, the same shapes, with
`artifact.source` holding the Taskcluster `index` and `task`) and three fields kept for readers of the old chart:
`meta_date` (time of the run), `title_date` (for example `Oct 2026`) and `lang` (lines per language at the head, all
files, headers split). Consumers should sum only the nine language keys and read `artifact.source.kind`.

### Changing the method

`method_version` is 1. The rule in `dev/history.py`: any change to the counted extensions or the test rules (and, by
the same logic, to the excluded prefixes or how lines are counted) bumps it and requires regenerating every release,
so all stored records always follow one set of rules. Changing the `header_split` ratio is not a bump: headers are
stored raw, so the new ratio applies to every release at display time; say so in the commit that changes it. The
browser-artifact rules have no version of their own yet: stored artifacts are never recomputed, so a change to those
rules would need the 157 artifact recomputed by hand.

## Reproducing the numbers

Requirements: Python 3.9 or newer (standard library only) and git (2.44 or newer for `backfill` on a partial clone and
for the browser artifact, which both rely on `GIT_NO_LAZY_FETCH`; older git gives the same counts but fetches missing
blobs one at a time, which is very slow).

```sh
python3 -m unittest discover -s dev                              # unit tests, no network

# the head point, the head artifact and the site, as the weekly job does
git clone --depth 1 https://github.com/mozilla-firefox/firefox.git firefox
python3 dev/history.py append data/history.json --repo firefox   # add releases missing from the file
mkdir -p build
python3 dev/history.py build-site data/history.json --repo firefox --out build --with-artifact
cp site/index.html rustacean-orig-noshadow.ico rustacean-orig-noshadow.png build/
python3 dev/render_docs.py docs/methodology.md --page site/index.html --out build/methodology.html
python3 -m http.server -d build                                  # then open http://localhost:8000

# one browser artifact on its own, with statistics
python3 dev/artifact.py head --repo firefox --stats stats.json
```

Regenerating `data/history.json` from scratch takes about 10 minutes and 3.5 GB of disk on a developer machine (run
it locally, not in CI):

```sh
git clone --no-checkout --filter=blob:none --single-branch --branch main \
    https://github.com/mozilla-firefox/firefox.git ff
git -C ff fetch -q --filter=blob:none origin \
    '+refs/tags/FIREFOX_*_0_RELEASE:refs/tags/FIREFOX_*_0_RELEASE' \
    '+refs/tags/FIREFOX_*_0_BUILD1:refs/tags/FIREFOX_*_0_BUILD1'
python3 dev/history.py backfill ff data/history.json

# backfill writes every artifact as null: restore release 157's
B=https://archive.mozilla.org/pub/firefox/candidates/157.0-candidates/build1/linux-x86_64/en-US
python3 dev/history.py set-artifact data/history.json --v 157 --repo ff \
    --symbols $B/firefox-157.0.crashreporter-symbols.zip --package $B/firefox-157.0.tar.xz
```

Rebuilding gives the same file apart from newly released versions; compare it with the committed file whenever
`method_version` changes. The symbol lists are rebuilt with `dev/artifact-files` (see its `--help`), but only while
the symbol server still has them; after that, only from the raw captures kept outside the repository on the
machine that made them (see `data/artifact-files/README.md`).

## Checks already done

| Check | Result | Where recorded |
|---|---|---|
| Backfill against the measurements of the first prototype (an earlier version of the same counter, so not independent; without the `mobile/` exclusion) | 0 mismatches in 222 release-views, 111 releases by two views (Rust, JavaScript, HTML, Python, Java and Assembly exact; C and C++ exact after the old split); release 125 was not in that series | `docs/implementation-plan.md`, "Verified reference results" |
| Non-test rules in Python against a git-pathspec version of them | 21.35% (157 tag) against 21.4-21.45% (`main`): about 0.1 point, different commits | `docs/reference/test-paths/README.md` |
| Appending a release against recounting it | Removing 157, and separately 123 (zero timestamp), then running `append` gave byte-identical files (a local simulation; the weekly job has not yet appended a real new release, 158 will be the first) | pull request #18 |
| Browser artifact, release 157 | 11,853,915 lines, Rust 16.30%, 19,289 paths, 26 modules; the research expected about 16-17% Rust, about 2.0M Rust lines and 19,000-20,000 paths | `docs/implementation-plan.md`, Task 5 |
| Browser artifact, head build `0b3661d5` | 12,235,473 lines, Rust 16.69%, 19,978 paths, 0 missing in the tree, no JavaScript, HTML or assembly path in the symbols | pull requests #19 and #20 |
| JavaScript inside `omni.ja`, 157 | 1,001,575 + 980,367 lines, the same as `unzip` and the research | pull request #20 |
| Release 157 against the nightly build | Rust 1.93M against 2.04M lines, C++ 5.44M against 5.57M (old split): the method is stable across builds; that does not make it exact | `docs/shipped-code-research.md` |
| The artifact's Rust share against the other views, 2026-10-05 | All files 12.78% and non-test 21.54% at `00a4d527`; artifact 16.69% at build `0b3661d5`, 72 commits later: between the two | pull request #19 |
| Saved symbol lists (45 versions) | Every path exists in the release tag's tree (0 missing; 136.0.4 has no git tag and was checked against the 136.0.3 tree); the `libxul.so` revision equals the tag's hg node | `data/artifact-files/README.md` |

## Known limitations and biases

- **One platform.** The browser artifact is Linux x86-64 only. Windows and macOS ship other crates (the union of the
  three platforms' crate sets is about 0.55M lines larger than Linux alone), and the `windows` crate (about 1.83M
  lines by the research's estimate, not independently verified) is fetched at build time, so it is not a repository file and would not be counted even from Windows symbols.
- **Shipped code outside the repository is not counted:** the Rust standard library and libc++ from the toolchains,
  onnxruntime (a prebuilt library), wasi-libc.
- **About 8 repository files are dropped by `#line` directives.** Some generated-looking files are attributed by
  `#line` directives to names in the build's object directory, so their `FILE` records are dropped as absolute paths:
  the sqlite amalgamation `third_party/sqlite3/ext/fts5.c`, five harfbuzz headers (four `hb-ot-shaper-*-machine.hh`
  and `hb-number-parser.hh`) and two angle `*_lex_autogen.cpp` files. At 143.0.4 that was 38,592 lines, under 1% (review of pull request
  #17). `dev/artifact.py` uses the same rules, so the 157 and head artifacts miss these files too; that was not
  re-measured for them.
- **Mixed revisions in the saved lists.** The symbol server keeps one file per debug id, so a module that came out
  byte-identical from another build carries that build's revision (131.0.2 has 5 revisions; review of pull request
  #17). Every path still exists at the release's own tag (136.0.4: at the 136.0.3 tag, as it has no git tag of its
  own), but the current counter requires a single revision, so Task 6 will need a rule for these.
- **Symbols expire.** About two years after a build (inferred); Taskcluster keeps build artifacts for about a year.
  Older release artifacts will depend on the `candidates/` zips (49 to 129, 144 onwards) and on the saved lists for
  131.0.2 to 143. 130.0, 130.0.1, 131.0, 46 and 48 have no symbols anywhere; 47 only has a 47.0.2 zip, which has no
  git tag, so it could only be approximated.
- **Non-test rules fit today's tree** (see above); the older a release, the less reliable its non-test value.
- **The header split is one fixed ratio** for all releases and views.
- **Dependence on Mozilla infrastructure.** The Taskcluster index, `archive.mozilla.org` and `symbols.mozilla.org` are
  public but not documented APIs. The head artifact fails soft; the tracked series do not depend on them.
- **The head date.** If the head commit had a zero timestamp, the depth-1 checkout would not hold an ancestor with a
  real one and the build step would fail (unlike `append`, it does not fetch more history). This has not happened.

## What "Rust share" says, and what it does not

It says: of the newline-terminated lines in files with the counted extensions, in the chosen view, this fraction is in
`.rs` files.

It does not say:

- **How much Rust Mozilla wrote.** Vendored crates are included, wherever they come from.
- **How much of the running browser is Rust.** Lines are not machine code. By machine-code bytes the research found
  Rust to be about 26% of `libxul.so` including the Rust standard library and about 15% without it; that is a
  different measure.
- **That other languages did not change.** A share moves when any language moves: non-test JavaScript, for example,
  grew from 2,299,867 lines at 156 to 2,973,279 at 157.
- **Anything about files the extension set leaves out** (`.hpp`, `.mm`, `.S`, `.ts`, ...). They are in neither the
  numerator nor the total.
- **The same thing in every view.** All files (12.7% at 157) is dominated by tests and test data, non-test files
  (21.4%) is what the repository holds outside tests, and the browser artifact (16.3%) is what is compiled or packed
  into the Linux build.

## Change log of the method

| Date | Change | Effect |
|---|---|---|
| 2018 to 2026-10-05 | The original chart (`dev/build-data`): `git ls-files` and `wc -l` at the head only, no `.mjs`, `mobile/` included, headers split 1/3 C to 2/3 C++, labelled "SLOC" | One pie for the current head |
| 2026-10-05 | `method_version` 1 (pull request #16): one counter for every release and the head; `.mjs` counted; `mobile/` excluded; non-test view added; headers stored raw and split 18.5% / 81.5%; 112 major releases backfilled | All existing numbers changed; the old `lang` figures are not comparable |
| 2026-10-05 | Weekly append of new releases and the four-view page (pull request #18) | No change to counts |
| 2026-10-05 | Browser artifact view: the head every run, release 157 stored (pull requests #19 and #20) | New view; tracked counts unchanged |
| 2026-10-05 | This document, published with the site as `methodology.html` | No change to counts |
