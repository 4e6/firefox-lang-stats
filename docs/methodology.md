# Methodology

How the numbers on [How much Rust in Firefox?](https://4e6.github.io/firefox-lang-stats/) are produced, what they
mean and how far to trust them. Every rule below is taken from the code that produces the data (`dev/history.py`
and `.github/workflows/deploy.yml`). Figures measured for this document are at release 157
(`FIREFOX_157_0_RELEASE`, commit `fdd757a2`) unless another commit is named.

## In short

The page counts **lines in files**, grouped into eight languages by file extension, for every major Firefox release
from 46 to the newest one and for the current head of the default branch of
[mozilla-firefox/firefox](https://github.com/mozilla-firefox/firefox). It offers two views of the same releases:

| View | What is counted | Releases covered |
|---|---|---|
| All files | Every file tracked by git at the release tag (or the head) with a counted extension, `mobile/` included | Every major release from 46 and the head |
| Browser files | The same files minus `mobile/` (mostly Android code) and minus the files matched by the test rules | Every major release from 46 and the head |

A release without data in a view is drawn as a gap, never as zero.

Firefox 157 in Browser files, headers split as described below:

| Language | Lines | Share |
|---|---:|---:|
| C++ | 10,987,092 | 42.0% |
| Rust | 5,616,315 | 21.4% |
| C | 4,788,840 | 18.3% |
| JavaScript | 2,973,279 | 11.4% |
| HTML/CSS | 195,821 | 0.7% |
| Python | 1,275,464 | 4.9% |
| Java | 55,497 | 0.2% |
| Assembly | 295,548 | 1.1% |
| **Total** | **26,187,856** | **100%** |

C and C++ include their share of the `.h` lines (fractional lines are rounded here). The Rust share is 21.45% before
rounding.

## What a "line" is

- A line is a **newline character** in the file's content (`content.count(b'\n')`, the same as `wc -l`). A last line
  without a trailing newline is not counted.
- It is **not SLOC**: blank lines, comments and licence headers count like code.
- It is **lines in files, not authored code**. Vendored third-party code is included wherever it sits (for example
  `third_party/rust`, which also holds Mozilla-written crates).

## Which files

The counter reads git objects only, never a working tree: `git ls-tree -r <commit>` lists every entry of the commit's
tree and `git cat-file --batch` reads the content of each counted blob once.

- Every tree entry of type `blob` whose path ends in a counted extension is counted. This includes files that git
  tracks but the build never uses.
- **Symbolic links** are blobs too (mode `120000`), so a link with a counted extension is counted; its content is the
  link target, normally with no newline, so it adds 0 lines. The 157 tree has no symbolic links at all.
- **Submodules** (tree entries of type `commit`) are skipped. The 157 tree has none.
- **Binary files are not detected.** If a file has a counted extension, its newline bytes are counted whatever it
  contains.
- **`mobile/`** holds Mozilla's Android code (Firefox for Android, Focus, GeckoView, Android Components) and a little
  iOS and shared code. It is counted in All files and skipped in Browser files (a prefix match on the path, stored as
  `browser_excluded_prefixes` in the data). At release 157 it holds no Rust, 90,556 of the 147,346 Java lines in All
  files, and 970,364 lines of Kotlin, which is not counted in either view.

### Extensions

Matching is case-sensitive and uses the last extension only (`foo.sys.mjs` counts as `.mjs`; `.C` or `.JS` would not
be counted; the 157 tree has no such files).

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
Some sizeable uncounted source extensions in the whole 157 tree, `mobile/` included (examples, not a complete
ranking; the 2,853 `moz.build` files, for instance, hold 224,982 lines and the `.idl` files 130,809):

| Extension | Files | Lines |
|---|---:|---:|
| `.kt` (Kotlin; 5,855 of the files under `mobile/`) | 5,992 | 1,048,566 |
| `.hpp` (C++ headers) | 1,102 | 602,021 |
| `.ts` (TypeScript) | 2,086 | 566,722 |
| `.inc` | 147 | 260,473 |
| `.S` (assembly, preprocessed) | 229 | 197,306 |
| `.mm` (Objective-C++) | 416 | 135,189 |
| `.hh` (C++ headers) | 284 | 112,934 |
| `.s` (assembly) | 62 | 38,533 |

Nine of the `.ts` files are binary MPEG transport streams (media test files), not TypeScript; they hold 33,851 of
those lines. Adding any of these extensions is a method change (see "Changing the method").

### Headers

`.h` files can be C or C++, and the extension does not say which. The data keeps their lines apart, as `h`, and the
page splits them at display time with the ratio stored in the data (`header_split`): **18.5% to C and 81.5% to C++**.
The code records only the figure ("by location about 81.5% of headers are C++"), not how it was measured or on which
commit, and the same ratio is applied to every release and to both views, so treat the C/C++ boundary as
approximate. The split moves lines between C and C++ only; the Rust share and the totals do not depend on it.

## The two views

### All files

Every counted file at the commit, with no exclusions. This is the closest to what the original chart measured (that
chart ran `git ls-files` and `wc -l` at the head, did not count `.mjs` and split headers 1/3 to 2/3). It is dominated
by tests and test data: web-platform-tests (`testing/web-platform/tests/`, about 163,000 files at 157) and `test262`,
which is vendored twice (`js/src/tests/test262/` and a copy inside web-platform-tests).

### Browser files

The same files minus the paths under `mobile/` and minus test paths (`is_test()` in `dev/history.py`). Everything
else stays: the desktop code for every platform (Windows, macOS, Linux and the others), vendored third-party code
whether or not a given build compiles it, build tooling and scripts, documentation, devtools and so on. It is **not**
"what ships in the download": it is what the repository holds outside the mobile apps and the tests.

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
  for older releases are less reliable**.
- They work on paths only. Test code inside other files is not removed: inline Rust `#[cfg(test)]` modules, for
  example, count as Browser files.
- The difference between the two views is not "the tests": All files minus Browser files is the test files plus
  everything under `mobile/`.

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
  the newest release. Dates appear next to the Pie view's release slider and in the data, not on the axis.
- **Immutability:** the weekly job never recounts a stored release; it only appends new ones.

## The head point

The head is the commit the workflow's depth-1 checkout of `mozilla-firefox/firefox` lands on (the tip of the default
branch). It is counted on every workflow run with the same counter and rules as a release. It lives only in the
deployed `build/data.json`, never in `data/history.json`, because it changes every week.

## The weekly pipeline

`.github/workflows/deploy.yml` runs every Sunday at 22:12 UTC, on every push to `main`, on pull requests and by hand.
One job, at most one run at a time per ref:

1. **Test:** `python3 -m unittest discover -s dev` (no network).
2. **Append:** `history.py append` lists the remote release tags (`git ls-remote --tags`), and for each major
   missing from `data/history.json` fetches its tag at depth 1, counts it and appends one line.
3. **Build:** `history.py build-site` counts the head and writes `build/data.json`; the page, its icons and this
   document (rendered to `methodology.html` by `dev/render_docs.py`) are added, and a check fails the step if an
   output file is missing or empty or the site data does not match `data/history.json`.
4. **Commit** (only on `main`, never for a pull request): if `data/` changed, commit `data: add releases` to `main`.
5. **Deploy** (only on `main`, never for a pull request): publish `build/` to the `gh-pages` branch.

A failure in steps 1 to 3 commits and deploys nothing.

## Data files

### `data/history.json` (committed)

One header line, then one release per line (a new release is a one-line diff). Shortened:

```
{"method_version":2,"browser_excluded_prefixes":["mobile/"],"header_split":{"c":0.185,"cpp":0.815},"releases":[
{"v":157,"tag":"FIREFOX_157_0_RELEASE","sha":"fdd757a2...","date":"2026-09-24",
 "all":{"rust":6172836,"c":...,"cpp":...,"h":...,"js":...,"html":...,"py":...,"java":147346,"asm":...},
 "browser":{"rust":5616315,"c":3889947,"cpp":7027103,"h":4858882,"js":2973279,"html":195821,"py":1275464,"java":55497,"asm":295548}}
]}
```

| Field | Meaning |
|---|---|
| `method_version` | Version of the counting rules the records were made with (2) |
| `browser_excluded_prefixes` | Path prefixes skipped in Browser files (`mobile/`); All files skips nothing |
| `header_split` | Share of `h` lines given to C and to C++ at display time |
| `v`, `tag`, `sha`, `date` | Major version, the tag counted, its commit and the commit's date |
| `all`, `browser` | Lines per language key in each view; `c` and `cpp` exclude headers, which are `h` |

Totals are not stored: a total is the sum of the nine language keys. `all` minus `browser` is the lines of test files
and of `mobile/` together, not the test lines alone.

### `build/data.json` (deployed as `data.json`)

`data/history.json` plus a `head` object (`sha`, `date`, `all`, `browser`, the same shapes) and three fields kept for
readers of the old chart: `meta_date` (time of the run), `title_date` (for example `Oct 2026`) and `lang` (lines per
language at the head, All files, headers split). Consumers should sum only the nine language keys.

### Changing the method

`method_version` is 2. Any change to the rules (the counted extensions, the test rules, the excluded prefixes or how
lines are counted) bumps it and requires regenerating every release, so all stored records always follow one set of
rules. Changing the `header_split` ratio is not a bump: headers are stored raw, so the new ratio applies to every
release at display time; say so in the commit that changes it. The history of the rules themselves is in the git
history of this repository.

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
| Rust in All files and `mobile/` | No `.rs` file under `mobile/` at 157, so Rust in All files is the same with or without `mobile/` (6,172,836 lines) |
| Java in All files at 157 | 147,346 lines: 56,790 outside `mobile/` and 90,556 under it |
| Unusual tree entries at 157 | No symbolic links, no submodules, no `.C` or `.JS` files |
| Binary `.ts` files at 157 | 9 MPEG transport streams, 33,851 newline bytes, all outside the counted extensions |

## Known limitations and biases

- **Test rules fit today's tree** (see above); the older a release, the less reliable its Browser-files value.
- **Paths, not builds.** Neither view knows what a given build compiles or ships; Browser files includes code for
  every platform and every vendored library in the tree.
- **The header split is one fixed ratio** for all releases and both views.
- **Extensions left out** (`.hpp`, `.hh`, `.mm`, `.S`, `.ts`, `.kt`, ...) are in neither the numerator nor the total.
- **The head date.** If the head commit had a zero timestamp, the depth-1 checkout would not hold an ancestor with a
  real one and the build step would fail (unlike `append`, it does not fetch more history). This has not happened.

## What "Rust share" says, and what it does not

It says: of the newline-terminated lines in files with the counted extensions, in the chosen view, this fraction is in
`.rs` files.

It does not say:

- **How much Rust Mozilla wrote.** Vendored crates are included, wherever they come from.
- **How much of the running browser is Rust.** Lines are not machine code, and neither view is limited to what a
  build compiles.
- **That other languages did not change.** A share moves when any language moves: JavaScript in Browser files, for
  example, grew from 2,299,867 lines at 156 to 2,973,279 at 157.
- **Anything about files the extension set leaves out.** They are in neither the numerator nor the total.
- **The same thing in both views.** All files is dominated by tests and test data and includes the Android code;
  Browser files (21.4% Rust at 157) is what the repository holds outside the mobile apps and the tests.
