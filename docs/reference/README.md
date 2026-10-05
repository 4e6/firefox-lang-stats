# Reference material

Prototype code, data and the design preview behind `../shipped-code-research.md`. Nothing here is production code and
nothing in the repository's build uses it. It exists so that the feature can be implemented without the session that
produced it. `../implementation-plan.md` says what to build; this directory shows how the numbers were produced.

| Directory | What it holds | Status |
|---|---|---|
| `history/` | `history.py` and `backfill.sh`: language line counts for every major release from one blobless clone | **Run end to end**; output verified against the measured series (see `../implementation-plan.md`, section "Verified reference results") |
| `test-paths/` | `build-data-pathspec.sh`: test exclusion as git pathspecs, plus the rules in prose | Run on 157; matches the Python rules in `history.py` to about 0.1 point |
| `symbols/` | Range-reading symbol files, build ids from release tarballs, availability survey, path checks | Used to produce the findings; **no end-to-end extractor exists**, see `symbols/README.md` |
| `preview/` | `history-designs.html`: the four-view design, self-contained, with measured data and made-up browser-artifact data | Reviewed in a browser, dark mode only; the original also had a fifth tab (see `preview/README.md`) |
| `measured/` | `series-111-majors-with-mobile.json`: measured per-release counts from the first prototype | Includes `mobile/`; use only to cross-check |

Conventions: all line counts are newline counts (`wc -l`), not SLOC. Scripts need only `git`, `python3` (3.9+) and
`curl`; none needs a Firefox build.
