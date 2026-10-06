# Methodology

How the numbers on [How much Rust in Firefox?](https://4e6.github.io/firefox-lang-stats/) are produced, what they
mean and how far to trust them. Every rule below is taken from the code that produces the data (`dev/history.py`
and `.github/workflows/deploy.yml`). Figures measured for this document are at release 157
(`FIREFOX_157_0_RELEASE`, commit `fdd757a2`) unless another commit is named.

## In short

The page counts **lines in files**, grouped into ten languages by file extension, for every major Firefox release
from 46 to the newest one and for the current head of the default branch of
[mozilla-firefox/firefox](https://github.com/mozilla-firefox/firefox). It offers two views of the same releases:

| View | What is counted |
|---|---|
| All files | Every file tracked by git at the release tag (or the head) with a counted extension, `mobile/` included |
| Browser files | The same files minus `mobile/` (mostly Android code), minus ten directories of build and developer tooling (vendored Python and Node packages included) and minus the files matched by the test rules |

The charts combine two pairs of languages: **JavaScript and TypeScript as one series, JavaScript/TypeScript**, and
**Java and Kotlin as one series, Java/Kotlin**, so they show eight series for the ten languages: the page has eight
series colours and does not add more. The data keeps each pair apart (`js` and `ts`, `java` and `kt`), and the
page's tooltips (and its tables, in Lines mode) give the split.

Firefox 157 in Browser files, headers split as described below:

| Language | Lines | Share |
|---|---:|---:|
| C++ | 11,689,446 | 45.8% |
| Rust | 5,613,873 | 22.0% |
| C | 4,693,307 | 18.4% |
| JavaScript/TypeScript (JavaScript 2,270,727, TypeScript 67,204) | 2,337,931 | 9.2% |
| Assembly | 531,363 | 2.1% |
| Python | 319,029 | 1.3% |
| HTML/CSS | 182,925 | 0.7% |
| Java/Kotlin (Java 55,497, Kotlin 72,324) | 127,821 | 0.5% |
| **Total** | **25,495,695** | **100%** |

C and C++ include their share of the `.h` lines (fractional lines are rounded here). The Rust share is 22.02% before
rounding. In All files at 157 Rust is 6,172,779 of 51,249,799 lines, 12.04%.

## What a "line" is

- A line is a **newline character** in the file's content (`content.count(b'\n')`, the same as `wc -l`). A last line
  without a trailing newline is not counted. A binary file counts 0 lines (see "Which files").
- It is **not SLOC**: blank lines, comments and licence headers count like code.
- It is **lines in files, not authored code**. Vendored third-party code is included wherever it sits (for example
  `third_party/rust`, which also holds Mozilla-written crates); Browser files leave out only the vendored Python and
  Node tooling (`third_party/python/`, `third_party/node/`).

## Which files

The counter reads git objects only, never a working tree: `git ls-tree -r <commit>` lists every entry of the commit's
tree and `git cat-file --batch` reads the content of each counted blob once.

- Every tree entry of type `blob` whose path ends in a counted extension is counted. This includes files that git
  tracks but the build never uses.
- **Symbolic links** are blobs too (mode `120000`), so a link with a counted extension is counted; its content is the
  link target, normally with no newline, so it adds 0 lines. The 157 tree has no symbolic links at all.
- **Submodules** (tree entries of type `commit`) are skipped. The 157 tree has none.
- **Binary files count 0 lines.** A blob with a NUL byte anywhere in its content is taken as binary and counts 0
  lines, whatever its extension (`count_lines()` in `dev/history.py`). At 157 this leaves out the nine binary `.ts`
  files (MPEG transport streams used as media test files, 33,851 newline bytes) and, in All files only, 57 Rust,
  278 JavaScript and 1,265 HTML/CSS lines. Browser files lose nothing to this rule in any release; in All files it
  takes 3 to 278 JavaScript and 788 to 1,598 HTML/CSS lines per release, and 57 Rust lines from 119 on.
- **`mobile/`** holds Mozilla's Android code (Firefox for Android, Focus, GeckoView, Android Components) and a little
  iOS and shared code. It is counted in All files and skipped in Browser files (a prefix match on the path; the data
  stores it, with the tooling prefixes of "Browser files" below, as `browser_excluded_prefixes`). At release 157 it
  holds no Rust, 90,556 of the 147,346 Java lines in All files, and 970,364 of the 1,048,566 Kotlin lines (92.5%;
  5,855 of the 5,992 `.kt` files), so Browser files hold only 72,324 lines of Kotlin. Android code outside `mobile/`
  counts as Browser files: most of those 72,324 lines (63,151 at 157) are the generated Kotlin bindings under
  `toolkit/components/uniffi-bindgen-gecko-js/android/`.

### Extensions

Matching is case-sensitive and uses the last extension only (`foo.sys.mjs` counts as `.mjs`; `.C` or `.JS` would not
be counted; the 157 tree has no such files). `.S` and `.s` are both listed, so both count.

| Key in the data | Shown as | Extensions |
|---|---|---|
| `rust` | Rust | `.rs` |
| `c` | C | `.c` |
| `cpp` | C++ | `.cc` `.cpp` `.cxx` `.hxx` `.hpp` `.hh` |
| `h` | split between C and C++ | `.h` |
| `js` | JavaScript/TypeScript (with `ts`) | `.jsm` `.jsx` `.js` `.mjs` |
| `ts` | JavaScript/TypeScript (with `js`) | `.ts` |
| `html` | HTML/CSS | `.htm` `.html` `.xhtml` `.xht` `.css` |
| `py` | Python | `.py` |
| `java` | Java/Kotlin (with `kt`) | `.java` |
| `kt` | Java/Kotlin (with `java`) | `.kt` |
| `asm` | Assembly | `.asm` `.S` `.s` |

JavaScript and TypeScript, and Java and Kotlin, are stored separately and added together for the
JavaScript/TypeScript and Java/Kotlin series on the charts (see "In short").

Everything else is left out, both from the language lines and from the total that shares are computed against.
Some sizeable uncounted source extensions in the whole 157 tree, `mobile/` included (examples, not a complete
ranking; the 2,853 `moz.build` files, for instance, hold 224,982 lines and the `.idl` files 130,809):

| Extension | Files | Lines |
|---|---:|---:|
| `.inc` | 147 | 260,473 |
| `.mm` (Objective-C++) | 416 | 135,189 |

Kotlin script files (`.kts`) are not counted either: matching uses the last extension and only `.kt` is listed.
Adding any of these extensions is a method change (see "Changing the method").

### Headers

`.h` files can be C or C++, and the extension does not say which. The data keeps their lines apart, as `h`, and the
page splits them at display time with the ratio stored in the data (`header_split`): **18.5% to C and 81.5% to C++**.
The code records only the figure ("by location about 81.5% of headers are C++"), not how it was measured or on which
commit, and the same ratio is applied to every release and to both views, so treat the C/C++ boundary as
approximate. The split moves lines between C and C++ only; the Rust share and the totals do not depend on it.
`.hpp` and `.hh` are C++ headers and count as C++ directly (key `cpp`); only `.h` is split.

## The two views

### All files

Every counted file at the commit, with no path excluded. This is the closest to what the original chart measured (that
chart ran `git ls-files` and `wc -l` at the head, did not count `.mjs` and split headers 1/3 to 2/3). It is dominated
by tests and test data: web-platform-tests (`testing/web-platform/tests/`, about 163,000 files at 157) and `test262`,
which is vendored twice since 152 (`js/src/tests/test262/` and a copy inside web-platform-tests; see "Reading the
series").

### Browser files

The same files minus the paths under the prefixes of `browser_excluded_prefixes` (`mobile/` and ten tooling
directories) and minus test paths (`is_test()` in `dev/history.py`). Everything else stays: the desktop code for every
platform (Windows, macOS, Linux and the others), vendored third-party code whether or not a given build compiles it,
devtools and so on. It is **not** "what ships in the download": it is what the repository holds outside the mobile
apps, the listed tooling directories and the tests.

The excluded prefixes are plain path-prefix matches from the top of the repository, like `mobile/`. They were picked
by hand from the 157 tree and checked against older releases. Lines are the non-test lines a prefix removes from
Browser files at 157:

| Prefix | What it is | Why it is excluded | Lines at 157 |
|---|---|---|---:|
| `mobile/` | The Android apps: Firefox for Android, Focus, GeckoView, Android Components | Not the desktop browser | 550,595 |
| `third_party/python/` | Vendored Python packages (pip, setuptools, pygments, aiohttp with its C code, ...) | Used by the build system and the tools, not by the browser | 891,420 |
| `third_party/node/` | Vendored Node packages: webpack, Babel and their dependencies, and the React/Redux runtime packages (80,369 lines with their small dependencies) | Used at build time to bundle code; new at 157 (see below) | 706,931 |
| `python/` | mach, mozbuild, mozlint and the other Mozilla Python tools; vendored Python packages too before 55 | Build system and developer tools | 103,933 |
| `tools/@types/` | TypeScript declaration files (`.d.ts`) describing Gecko's APIs | Only type-check the JavaScript; never compiled or shipped | 84,999 |
| `taskcluster/` | The CI task graph, its Docker images and CI scripts | Continuous integration | 44,332 |
| `tools/lint/` | The linters: ESLint configuration and plugins, Python and Rust lint code | Developer tooling | 21,607 |
| `build/clang-plugin/` | Mozilla's clang static-analysis plugin | Runs inside the compiler; not part of the browser | 12,311 |
| `build/pgo/` | The pages and server used to train profile-guided-optimisation builds | Build-time training input | 11,735 |
| `tools/tryselect/` | `mach try`, which picks the CI jobs to run on the try server | Developer tooling | 9,442 |
| `docs/` | The Firefox source documentation (Sphinx configuration and extensions) | Documentation | 1,694 |

The ten tooling prefixes remove 1,888,404 lines at 157, most of them vendored (`third_party/python/` and
`third_party/node/` together 1,598,351): 956,435 Python lines, 702,552 JavaScript, 105,951 TypeScript, 94,744 C,
13,384 C++ and headers, 12,896 HTML/CSS and 2,442 Rust (`tools/lint` 1,835, `taskcluster` 607). Not everything
under `build/` and `tools/` is tooling, so those directories are not excluded as a whole: `tools/profiler/` is the
Gecko Profiler, compiled into the browser (47,628 lines at 157); `tools/fuzzing/` and `tools/performance/` are
compiled into Gecko too; `build/unix/` holds elfhack and stdc++compat, which end up in Linux builds; `build/rust/`
holds small crates linked into libxul; and `build/stlport/` (releases 46 to 51, 85,629 lines) was the C++ runtime of
Android builds. `config/` (5,614 lines at 157) mixes build scripts with wrapper headers used when compiling the
browser, so it stays as well.

`third_party/node/` is not pure tooling. At 157 the new tab page's build script
(`browser/extensions/newtab/build-newtab-bundles.py`) runs webpack on `third_party/node/node_modules`, and its vendor
bundle (`content-src/vendor.mjs`) imports React, ReactDOM, Redux, React Redux, PropTypes and React Transition Group
from there. Code from those packages (80,369 lines in the tree) therefore reaches the shipped new tab page in bundled
form, yet the packages are left out of Browser files with the rest of the directory. A second copy of React and Redux,
`toolkit/content/vendor/react/` (30,430 lines at 157, packaged by `toolkit/content/jar.mn`), is not under any excluded
prefix and stays counted.

A path is a test path if any of these hold:

1. It starts with `testing/`, `js/src/tests/`, `js/src/jit-test/`, `js/src/jsapi-tests/`, `js/src/octane/` or
   `third_party/webkit/PerformanceTests/`.
2. Any directory in it is named `test`, `tests`, `gtest`, `gtests`, `mochitest`, `mochitests`, `xpcshell`, `reftest`,
   `reftests`, `crashtest`, `crashtests`, `__tests__`, `androidTest`, `test262`, `unittests`, `googletest`, `testdata`,
   `fixtures`, `browser_tests`, `jsapi-tests` or `jit-test`; or ends in `-test`, `-tests`, `_test` or `_tests`; or
   starts with `test-`, `tests-`, `test_` or `tests_`; or is a `testing` directory below the top level.
3. It is a Rust file named `tests.rs`, `test.rs`, or ending in `_test.rs` or `_tests.rs`.

Limits of the test rules:

- They were derived by hand from **today's tree**. Older trees used other directory names, so **Browser-files values
  for older releases are less reliable**. The same holds for the tooling prefixes (see "Known limitations").
- They work on paths only. Test code inside other files is not removed: inline Rust `#[cfg(test)]` modules, for
  example, count as Browser files.
- The difference between the two views is not "the tests": All files minus Browser files is the test files plus
  everything under `mobile/` and the tooling prefixes.

## Releases and dates

- **Release set:** major releases, `FIREFOX_<n>_0_RELEASE` for n = 46 up to the newest major that has such a tag.
  Release 125 has no `FIREFOX_125_0_RELEASE` tag and is counted at `FIREFOX_125_0_BUILD1`, stored under `v` = 125 with
  `"tag": "FIREFOX_125_0_BUILD1"` in its record; it is the only release counted at a tag other than
  `FIREFOX_<n>_0_RELEASE`. A newer major that has only `BUILD` tags is not added until its `_RELEASE` tag exists.
  Point releases and ESRs are not included.
- **Date:** the committer date of the counted commit (`git log --format=%cs`). Some converted commits carry a zero
  timestamp (1970-01-01; `FIREFOX_123_0_RELEASE` is one); for those the date of the nearest first-parent ancestor
  with a real timestamp is stored. The weekly job fetches 10 more commits of such a tag to find it.
- **x axis:** releases are placed one step apart in release order (by index, not by date); the head is one step after
  the newest release. Dates appear next to the Pie view's release slider (labelled "commit date"), in the headline and
  tooltips for the head, and in the data, not on the axis. A release's commit date is usually a few days before its
  public release: 2022-04-28 for release 100, which shipped on 2022-05-03.
- **Immutability:** the weekly job never recounts a stored release; it only appends new ones.

## The head point

The head is the commit the workflow's depth-1 checkout of `mozilla-firefox/firefox` lands on (the tip of the default
branch). It is counted on every workflow run with the same counter and rules as a release. It lives only in the
deployed `build/data.json`, never in `data/history.json`, because it changes every week.

## The weekly pipeline

`.github/workflows/deploy.yml` is scheduled for every Sunday at 22:12 UTC and also runs on every push to `main`, on
pull requests and by hand. GitHub often starts scheduled runs late: the 59 scheduled runs from 2025-08-24 to
2026-10-05 started between 22:18 and 00:53 UTC, the last five after 23:50, so a week's data can lag until early Monday
(UTC). Those runs all ran the workflow of an earlier version of this repository with the same schedule; as of
2026-10-06 the current workflow has not yet run on a schedule (the first is due on 2026-10-11). One job, at most one
run at a time per ref:

1. **Test:** `python3 -m unittest discover -s dev` (no network).
2. **Append:** `history.py append` lists the remote release tags (`git ls-remote --tags`), and for each major
   missing from `data/history.json` fetches its tag at depth 1, counts it and appends one line.
3. **Build:** `history.py build-site` counts the head and writes `build/data.json`; the page, its icons and this
   document (rendered to `methodology.html` by `dev/render_docs.py`) are added, and a check fails the step if an
   output file is missing or empty, the site data does not match `data/history.json` or the stored releases are not
   46, 47, 48 and so on without a gap.
4. **Commit** (only on `main`, never for a pull request): if `data/` changed, commit `data: add releases` to `main`.
5. **Deploy** (only on `main`, never for a pull request): publish `build/` to the `gh-pages` branch.

A failure in steps 1 to 3 commits and deploys nothing.

## Data files

### `data/history.json` (committed)

One header line, then one release per line (a new release is a one-line diff). Shortened:

```
{"method_version":4,"browser_excluded_prefixes":["mobile/","build/clang-plugin/","build/pgo/","docs/","python/",
 "taskcluster/","third_party/node/","third_party/python/","tools/@types/","tools/lint/","tools/tryselect/"],
 "header_split":{"c":0.185,"cpp":0.815},"releases":[
{"v":157,"tag":"FIREFOX_157_0_RELEASE","sha":"fdd757a2...","date":"2026-09-24",
 "all":{"rust":6172779,"c":3992382,"cpp":8522133,"h":5075167,"js":16228932,"ts":532871,"html":6838595,"py":2159226,
        "java":147346,"kt":1048566,"asm":531802},
 "browser":{"rust":5613873,"c":3795203,"cpp":7732935,"h":4854615,"js":2270727,"ts":67204,"html":182925,"py":319029,
            "java":55497,"kt":72324,"asm":531363}}
]}
```

| Field | Meaning |
|---|---|
| `method_version` | Version of the counting rules the records were made with (4) |
| `browser_excluded_prefixes` | Path prefixes skipped in Browser files (`mobile/` and the ten tooling prefixes); All files skips no path. `append` and `build-site` read the list from here, so new records follow the stored one |
| `header_split` | Share of `h` lines given to C and to C++ at display time |
| `v`, `tag`, `sha`, `date` | Major version, the tag counted, its commit and the commit's date |
| `all`, `browser` | Lines per language key in each view; `c` and `cpp` exclude `.h` headers, which are `h`; `js` and `ts`, `java` and `kt` are separate |

Totals are not stored: a total is the sum of the eleven language keys. `all` minus `browser` is the lines of test files,
of `mobile/` and of the tooling prefixes together, not the test lines alone.

### `build/data.json` (deployed as `data.json`)

`data/history.json` plus a `head` object (`sha`, `date`, `all`, `browser`, the same shapes) and three fields kept for
readers of the old chart: `meta_date` (time of the run), `title_date` (for example `Oct 2026`) and `lang` (lines per
language at the head, All files, headers split). Consumers should sum only the eleven language keys.

### Changing the method

`method_version` is 4: the rules described here, which count Kotlin (`.kt`), TypeScript (`.ts`), `.hpp` and `.hh` as
C++ and `.S` and `.s` as Assembly, count a blob with a NUL byte as 0 lines, and leave `mobile/` and the ten tooling
prefixes out of Browser files. Any change to the rules (the counted
extensions, the test rules, the excluded prefixes or how lines are counted) bumps it and requires regenerating every
release, so all stored records always follow one set of rules. Changing the `header_split` ratio is not a bump:
headers are stored raw, so the new ratio applies to every release at display time; say so in the commit that changes
it. The history of the rules themselves is in the git history of this repository.

## Reproducing the numbers

Requirements: Python 3.9 or newer (standard library only) and git (2.44 or newer to regenerate the history from a
partial clone, which relies on `GIT_NO_LAZY_FETCH`; older git gives the same counts but fetches missing blobs one at a
time, which is very slow).

```sh
python3 -m unittest discover -s dev          # unit tests, no network
python3 dev/history.py --help                # the subcommands: regenerate the history, append releases,
                                             # count a head, write the site data
git clone --depth 1 https://github.com/mozilla-firefox/firefox.git firefox
# then run the Append and Build steps of .github/workflows/deploy.yml, and view the result:
python3 -m http.server -d build              # then open http://localhost:8000
```

Regenerating `data/history.json` from scratch is done locally, not in CI, on a blobless clone that has the release
tags; `python3 dev/history.py --help` gives the commands. Rebuilding gives the same file apart from newly released
versions; compare it with the committed file whenever `method_version` changes.

## Checks

| Check | Result |
|---|---|
| Unit tests (`python3 -m unittest discover -s dev`, run by every workflow run) | The release set (125 and newest-major rules), the test rules, excluded prefixes, the file layout, the zero-timestamp rule, append and the site data on small generated repositories |
| Rust in All files and `mobile/` | No `.rs` file under `mobile/` at 157, so Rust in All files is the same with or without `mobile/` (6,172,779 lines) |
| Java in All files at 157 | 147,346 lines: 56,790 outside `mobile/` and 90,556 under it |
| Unusual tree entries at 157 | No symbolic links, no submodules, no `.C` or `.JS` files |
| Kotlin at 157 | All files 1,048,566 lines (970,364 under `mobile/`), Browser files 72,324 |
| Binary `.ts` files at 157 | 9 MPEG transport streams, 33,851 newline bytes, count 0: TypeScript in All files is 532,871 lines (566,722 in all `.ts` files minus 33,851) |
| Binary rule, against counts made without it (the keys `rust` `c` `h` `js` `html` `py` `java`, every release) | Browser files identical; All files lower only in Rust (57 lines, 119 to 157), JavaScript and HTML/CSS, at most 1,634 lines together in a release |
| `.hpp` `.hh` `.S` `.s` at 157 | All files `cpp` grows by exactly their 714,955 lines and `asm` by their 235,839: none of them is binary |
| Tooling prefixes, against the previous rules (`mobile/` only), every release | `v`, `tag`, `sha`, `date` and All files identical; Browser files lower by exactly the non-test lines under the ten tooling prefixes, per language |
| Independent recount at 46, 60, 125 and 157 (own `git ls-tree`/`git cat-file` loop, own extension map and NUL rule, the same test rules) | All files and Browser files equal to the stored records |
| Shipped code under `tools/` and `build/` at 157 | Still in Browser files: `tools/profiler` 47,628 lines, `tools/fuzzing` 15,366, `tools/performance` 1,381, `build/unix` 4,632, `build/rust` 1,595 |

## Reading the series

Some steps in the charts are real changes to the repository, not counting artefacts. The steps below are explained
here; others are not explained yet. For example, the Java/Kotlin series in All files rises by 105,340 lines at 55
and by 70,346 at 79 and falls by 110,629 at 151.

- **Release 54, Rust.** In Browser files Rust grows from 67,654 lines (0.60% of the view) to 785,871 (6.46%), and from
  105 to 1,885 files: Servo and WebRender arrived in mozilla-central. Commit `5f7f5313de79` (Bug 1322769, "vendor
  Servo") merged the servo/servo repository (minus its web-platform and ref tests) into `servo/`, all of it counted
  whether or not Firefox builds it: +732 Rust files and +314,383 lines, of them 272,784 in `servo/components/` (`style`
  123,206, `script` 82,418, `layout` 25,051) and 41,221 in `servo/ports/` (`cef` 37,952). WebRender came to
  `gfx/webrender`, `gfx/webrender_traits` and `gfx/webrender_bindings` (45 files, 22,687 lines; Bug 1335525).
  `third_party/rust/` grows by 1,003 files and 380,653 lines, 378,130 of them in 115 new crates: 48 crates (191,130
  lines) came with WebRender's dependencies (commit `cbdf0c332f77`, Bug 1335525), 59 (170,784 lines) with Stylo's
  (`geckolib`) dependencies (commit `b4ab990a0d87`, Bug 1336607) and 8 (16,216 lines) in other commits. In All files
  Rust grows from 70,437 to 815,996 lines.
- **Release 71, Java.** In All files Java falls from 551,092 to 161,770 lines: Fennec, the old Firefox for Android
  UI, was removed from mozilla-central (Bug 1580356, commit `997b7d114877`; 2,147 `.java` files, 345,851 lines under
  `mobile/android/` in `thirdparty`, `base`, `services`, `app` and `stumbler`), and so were the Robocop tests (Bug
  1580832). All of it was under `mobile/`, so Browser files are not affected by them. Browser files have their own,
  smaller Java step at 71 (49,147 to 26,423 lines): the WebRTC Android SDK (`media/webrtc/trunk/webrtc/sdk/android`,
  about 22,700 lines) was removed (Bug 1588346). The directory came back at 75 in a newer form: commit
  `07116fe4e2b4` (Bug 1578073) added 5,946 lines of newer webrtc.org Android camera code, `sdk/android` holds 5,943
  lines at 75, and Java in Browser files rises by 5,516 lines at 75.
- **Release 119, Rust.** In Browser files the Rust share rises from 15.62% to 17.65% (+489,534 lines). Commit
  `c18610945143` (Bug 1853084, "Vendor windows-sys") added `third_party/rust/windows-sys/`: 281 files, 497,626 lines of
  Rust bindings to the Windows API, generated from Microsoft's API metadata (as the crate's readme says). Without the
  crate the share at 119 would be 15.59%, so it is the whole step; the `ntapi` crate (20,891 lines) left at the same
  release. The crate is smaller later: 249 files and 334,283 lines at 157, 6.0% of Rust in Browser files (13.8% at 119).
- **Release 126, Kotlin.** In All files Kotlin jumps from 36,678 to 615,415 lines because the firefox-android
  repository (Android Components, Fenix, Focus) was merged into mozilla-central on 2024-03-18 (Bug 1822248, commit
  `3b8cd5f81382`). Release 125 is counted at `FIREFOX_125_0_BUILD1`, whose branch was cut about an hour before the
  merge, so no 125 tag could include it. Java barely moves (278,159 to 279,504).
- **Java/Kotlin as one series.** Because of the Java and Kotlin steps at 71 and 126, the combined Java/Kotlin series in All files falls at
  71 and rises at 126. In Browser files the series is small (127,821 lines, 0.5% of the view at 157) but not flat:
  Android code outside `mobile/` counts there. Besides the WebRTC SDK step at 71 (-22,724), it doubles at 155
  (64,480 to 127,535 lines), when 62,985 lines of generated Kotlin bindings arrived under
  `toolkit/components/uniffi-bindgen-gecko-js/android/` (64,014 lines with their tests, most of the +65,004 step
  in All files at 155).
  Other steps of similar size to the one at 71 are not explained here: +15,978 at 56, +20,078 at 96, +11,943 at 106,
  -9,357 at 48 and -8,119 at 113.
- **Release 131, HTML/CSS.** In Browser files HTML/CSS falls from 277,082 to 157,219 lines (-119,863). The update of
  FreeType to 2.13.3 (Bug 1912903, commit `4f64bf65d3d0`) removed `modules/freetype2/docs/`, all 137 files, among them
  FreeType's API reference in HTML (`docs/reference/`): 110,073 HTML/CSS lines (and 7,298 JavaScript lines). The new
  tab page's three per-platform style sheets (`activity-stream-linux.css`, `-mac.css` and `-windows.css` in
  `browser/components/newtab/css/`) became one, `activity-stream.css` (-10,933 lines), and small changes elsewhere add
  back 1,143. In All files web-platform-tests offset part of it: HTML/CSS falls by 84,151.
- **Release 152, JavaScript/TypeScript.** In All files JavaScript/TypeScript grows from 12,676,181 to 15,605,903 lines
  (+2,929,722), and the JavaScript/TypeScript files of web-platform-tests from 6,868 to 60,453: web-platform-tests
  now vendors its own copy of test262, `testing/web-platform/tests/third_party/test262/` (53,482 JavaScript files,
  2,840,767 lines at 152). It arrived with a web-platform-tests sync committed on 2026-04-23 (commit `05939139fd15`, Bug
  2032330, wpt PR 59244, 2,840,673 lines added). It is test code, so Browser files leave it out; the Rust share of All
  files falls from 12.20% to 11.74% at 152 although Rust grows by 209,880 lines there.

## Known limitations and biases

- **Test rules fit today's tree** (see above); the older a release, the less reliable its Browser-files value.
- **The tooling prefixes are hand-picked and written for today's tree.** They name directories, not files, and the
  list is short on purpose; it is not a complete inventory of tooling. Vendored tooling under other names stays in
  Browser files: `third_party/chromium/build/` (100,402 lines at 157), `intl/icu/source/tools/` (82,405) or
  `third_party/libwebrtc/tools/`, for example. Matching directory names instead would be wrong: `xpcom/build/`,
  `memory/build/` and pdf.js's `content/build/` are shipped code. In older releases: before 55 the vendored Python
  packages lived in `python/` (215,814 lines at 54, 44,361 at 55 when `third_party/python/` appeared with 150,457),
  which both prefixes cover; `third_party/python/` changes in large steps as packages are added and removed (for
  example +275k lines at 61, -314k at 82, +209k at 96, -229k at 149, +171k at 152); `tools/@types/` exists from 125
  and `third_party/node/` only from 157. Tooling that only older trees had is not on the list: `build/pymake/`
  (5,817 lines, 46 to 78), `tools/check-moz-style/` (4,202, 46 to 52) and `build/mobile/` (up to 10,237, 46 to 85,
  mostly Java).
- **Paths, not builds.** Neither view knows what a given build compiles or ships; Browser files includes code for
  every platform and every vendored library in the tree outside the tooling prefixes.
- **The header split is one fixed ratio** for all releases and both views.
- **Extensions left out** (`.mm`, `.inc`, `.kts`, ...) are in neither the numerator nor the total.
- **The binary rule is one test** (a NUL byte anywhere in the blob). A text file saved as UTF-16 contains NUL bytes too
  and counts 0 like a binary file; a binary file without any NUL byte would be counted.
- **Two pairs share a series** on the charts (JavaScript/TypeScript, Java/Kotlin); the split is only in the tooltips,
  the Lines-mode tables and the data.
- **The head date.** If the head commit had a zero timestamp, the depth-1 checkout would not hold an ancestor with a
  real one and the build step would fail (unlike `append`, it does not fetch more history). This has not happened.

## What "Rust share" says, and what it does not

It says: of the newline-terminated lines in non-binary files with the counted extensions, in the chosen view, this
fraction is in `.rs` files.

It does not say:

- **How much Rust Mozilla wrote.** Vendored crates are included, wherever they come from.
- **How much of the running browser is Rust.** Lines are not machine code, and neither view is limited to what a
  build compiles.
- **That other languages did not change.** A share moves when any language moves: at 151, for example, Rust in
  Browser files grew by 16,427 lines and its share still fell from 21.22% to 20.83%, because C++ (key `cpp`, without
  headers) grew by 407,494 lines.
- **Anything about files the extension set leaves out.** They are in neither the numerator nor the total.
- **The same thing in both views.** All files is dominated by tests and test data and includes the Android code;
  Browser files (22.0% Rust at 157, against 12.0% in All files) is what the repository holds outside the mobile apps,
  the listed tooling directories and the tests.
