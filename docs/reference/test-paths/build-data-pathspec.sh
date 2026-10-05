#!/bin/sh
# Proposed: count every language twice -- "all" (current behaviour) and "non-test"
# (test suites / test dirs excluded by path). Pathspec magic ':(exclude,glob)' -- '*' does not
# cross '/', '**/' matches zero or more dirs. Plain '*.rs' include specs keep classic semantics.
GECKO_DEV=$1; cd "$GECKO_DEV" || exit 1
EXCL_TESTS="
:(exclude,glob)testing/**
:(exclude,glob)js/src/tests/**
:(exclude,glob)js/src/jit-test/**
:(exclude,glob)js/src/jsapi-tests/**
:(exclude,glob)js/src/octane/**
:(exclude,glob)third_party/webkit/PerformanceTests/**
:(exclude,glob)**/test/**
:(exclude,glob)**/tests/**
:(exclude,glob)*/**/testing/**
:(exclude,glob)**/*[_-]test/**
:(exclude,glob)**/*[_-]tests/**
:(exclude,glob)**/test[_-]*/**
:(exclude,glob)**/tests[_-]*/**
:(exclude,glob)**/gtest/**
:(exclude,glob)**/gtests/**
:(exclude,glob)**/mochitest/**
:(exclude,glob)**/mochitests/**
:(exclude,glob)**/xpcshell/**
:(exclude,glob)**/reftest/**
:(exclude,glob)**/reftests/**
:(exclude,glob)**/crashtest/**
:(exclude,glob)**/crashtests/**
:(exclude,glob)**/__tests__/**
:(exclude,glob)**/androidTest/**
:(exclude,glob)**/test262/**
:(exclude,glob)**/unittests/**
:(exclude,glob)**/googletest/**
:(exclude,glob)**/testdata/**
:(exclude,glob)**/fixtures/**
:(exclude,glob)**/browser_tests/**
:(exclude,glob)**/tests.rs
:(exclude,glob)**/test.rs
:(exclude,glob)**/*_test.rs
:(exclude,glob)**/*_tests.rs
"
# portable stand-in for: git ls-files -z ... | wc -l --files0-from=- | tail -n 1
loc() { git ls-files -z "$@" | xargs -0 cat | wc -l | tr -d ' '; }
loc_nontest() { ( IFS='
'; set -f; loc "$@" $EXCL_TESTS ) }   # subshell: IFS/set -f do not leak
for view in all nontest; do
  f=loc; [ $view = nontest ] && f=loc_nontest
  h=$($f '*.h')
  echo "$view Rust $($f '*.rs')"
  echo "$view C+h/3 $(( $($f '*.c') + h/3 ))"
  echo "$view C++ $(( $($f '*.cc' '*.cpp' '*.cxx' '*.hxx') + 2*h/3 ))"
  echo "$view JavaScript $($f '*.jsm' '*.jsx' '*.js')"
  echo "$view HTML $($f '*.htm' '*.html' '*.xhtml' '*.xht' '*.css')"
  echo "$view Python $($f '*.py')"
  echo "$view Java $($f '*.java')"
  echo "$view Assembly $($f '*.asm')"
  echo "$view (rust outside third_party/rust) $($f '*.rs' ':(exclude,glob)third_party/rust/**')"
done
