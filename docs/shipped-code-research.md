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

Mozilla builds Firefox on every push. These outputs are public, need no authentication, and are kept for a year:

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
2. Range-read the zip directory and the `FILE` header of each shipped `.sym` (about 20 MB, about 35 s).
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
- The symbols zip holds two `libxul.so` builds. The gtest one has `gtest` file paths; skip it.
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

## What is not counted

Shipped code that is not in the git tree: the `windows` crate (1.83M lines, fetched at build time, Windows builds
only), onnxruntime (prebuilt), wasi-libc (linked into six sandboxed libraries), the Rust standard library and libc++
from the toolchains. The symbol approach does not see these as repo files.

## Limits and risks

- **One platform.** Verified for Linux x86-64 only. Windows and macOS ship different crates (the union of the Linux, Windows
  and macOS crate sets is about 0.55M lines larger than Linux alone). The Windows `FILE` records for the `windows` crate will not
  resolve to git paths, so that code would be silently dropped. Label the chart "Linux x86-64".
- **Dependence on Mozilla infrastructure.** Taskcluster index, artifacts and the symbol server are public but are not
  a documented stable API. Artifacts expire after one year, so a shipped series cannot be backfilled past that.
  `coverage.moz.tools` has no DNS record any more; do not use it.
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
3. What "shipped" should mean for the chart: lines in files that contribute code (about 17% Rust), or machine-code
   bytes (libxul about 26% with the standard library, about 15% without)?
4. Depend on Mozilla's CI artifacts in the weekly cron, with the static fallback if they are missing?

## Suggested order

1. Issue #6: path-based test exclusion plus `*.mjs`, showing "all" and "non-test" views.
2. Prototype the shipped series as a separate, clearly labelled chart.
3. Do not build Firefox in CI.

## Method and verification

Four independent researchers covered the vendored-code inventory, build-graph recovery, test exclusion and counting
method, and bundle and CI cost. A fresh reviewer then reproduced the headline numbers (the current script totals, the
non-test split, the shipped Rust count, crate counts, the chrome-map and `omni.ja` JS counts, and the live endpoints)
over two rounds. Not independently verified: the range-read and batch-fetch timings, the BuildReader 3-5 s claim, the
`windows` crate size, and the Kotlin and SLOC figures. Windows/macOS symbols and the desktop SBOM were not examined.
