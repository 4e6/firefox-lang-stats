# Measured series (first prototype)

`series-111-majors-with-mobile.json`: per-release language lines for the 111 major releases that have a
`FIREFOX_<n>_0_RELEASE` tag (46 to 157, no 125), from the first prototype of `history/history.py`. Differences from
what the product should store:

- It includes `mobile/` (the decision is to exclude it).
- `C` and `C++` already include the header split (`C = c + h/3`, `C++ = cpp + 2h/3`), and there is no separate `h`.
- `Java` and `Assembly` are separate keys; `total` and `rust_pct` are derived.

Structure: `{"missing":0,"res":{"<tag>":{"all":{...},"nontest":{...}}}}`. Use it only to cross-check a new run (run
`history/backfill.sh` without `--exclude`, then compare Rust, JavaScript, HTML, Python, Java and Assembly exactly and C and C++ after applying the split).
