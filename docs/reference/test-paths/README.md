# Test-path exclusion

"Non-test" means: not under a test path. The rules were derived from the Firefox tree (see "Why the current chart overstates things" and "Related fixes the script needs regardless" in
`../../shipped-code-research.md`) and exist in two forms that agree to about 0.1 point at Firefox 157 (Rust 21.35% with the
Python rules on the release tag, 21.4-21.45% with the pathspecs on `main`; different commits, so not an exact match).

- `../history/history.py`: `is_test()`. This is the form to use, because it also works on historical trees (it is driven
  by `git ls-tree`, not by a working tree) and keeps one counter for the backfill, the weekly append and the head.
- `build-data-pathspec.sh`: the same rules as `git ls-files` pathspecs. Run it as `sh build-data-pathspec.sh PATH_TO_CHECKOUT`; it prints the
  "all" and "non-test" counts per language. Kept as an independent cross-check.

Rules (a path is a test path if any of these hold):

1. It starts with `testing/` (harness, WPT, marionette, talos and so on), `js/src/tests/` (includes a vendored test262),
   `js/src/jit-test/`, `js/src/jsapi-tests/`, `js/src/octane/` or `third_party/webkit/PerformanceTests/`.
2. Any directory component is one of: `test`, `tests`, `gtest`, `gtests`, `mochitest`, `mochitests`, `xpcshell`,
   `reftest`, `reftests`, `crashtest`, `crashtests`, `__tests__`, `androidTest`, `test262`, `unittests`, `googletest`,
   `testdata`, `fixtures`, `browser_tests`, `jsapi-tests`, `jit-test`, or matches `*-test(s)`, `*_test(s)`, `test(s)-*`,
   `test(s)_*`, or is a nested `testing` directory.
3. A Rust file is named `tests.rs`, `test.rs`, `*_test.rs` or `*_tests.rs`.

Known limits: inline `#[cfg(test)]` modules cannot be excluded by path (about 12% of non-vendored and 7% of vendored
Rust). Test directory names differ in older trees, so earlier non-test values are less reliable. Manifest-based
detection (mochitest, xpcshell and similar manifests) was tried and is worse: it misses 4.4M lines of tests.
