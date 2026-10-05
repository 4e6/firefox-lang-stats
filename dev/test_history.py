"""Tests for dev/history.py. No network: every repository is a throwaway local one.

Run: python3 -m unittest discover -s dev
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import history  # noqa: E402

# (path, number of lines, language key or None if not counted, test path?)
FILES = [
    ('browser/app.rs', 3, 'rust', False),
    ('browser/lib.c', 2, 'c', False),
    ('browser/lib.h', 10, 'h', False),
    ('browser/x.cpp', 4, 'cpp', False),
    ('browser/y.cc', 1, 'cpp', False),
    ('browser/z.cxx', 1, 'cpp', False),
    ('browser/w.hxx', 1, 'cpp', False),
    ('browser/foo.hpp', 4, 'cpp', False),   # v3: .hpp and .hh are C++ (not the split `h`)
    ('browser/foo.hh', 4, 'cpp', False),
    ('browser/a.js', 2, 'js', False),
    ('browser/b.mjs', 3, 'js', False),
    ('browser/c.jsm', 1, 'js', False),
    ('browser/d.jsx', 1, 'js', False),
    ('browser/e.ts', 5, 'ts', False),
    ('mobile/android/f.ts', 7, 'ts', False),
    ('browser/p.html', 1, 'html', False),
    ('browser/q.css', 2, 'html', False),
    ('browser/r.xhtml', 1, 'html', False),
    ('browser/s.htm', 1, 'html', False),
    ('browser/t.xht', 1, 'html', False),
    ('python/tool.py', 2, 'py', False),   # v4: python/ is tooling, in "all" but not in "browser"
    ('browser/J.java', 1, 'java', False),
    ('browser/Foo.kt', 4, 'kt', False),
    ('media/x.asm', 2, 'asm', False),
    ('media/y.S', 4, 'asm', False),   # v3: .S and .s are assembly
    ('media/z.s', 3, 'asm', False),
    ('browser/tests/t.rs', 5, 'rust', True),
    ('browser/tests/t.cpp', 6, 'cpp', True),
    ('dom/test/test_a.html', 8, 'html', True),
    ('testing/harness.py', 7, 'py', True),
    ('src/foo_test.rs', 4, 'rust', True),
    ('js/src/jit-test/a.js', 9, 'js', True),
    ('mobile/android/M.java', 100, 'java', False),
    ('mobile/android/m.rs', 50, 'rust', False),
    ('mobile/android/tests/T.java', 20, 'java', True),
    ('mobile/android/K.kt', 40, 'kt', False),
    ('mobile/android/tests/KT.kt', 13, 'kt', True),
    ('toolkit/tests/U.kt', 6, 'kt', True),
    ('mobilex/keep.rs', 11, 'rust', False),  # "mobile/" is a directory prefix, not a name prefix
    # not counted: other extensions (Kotlin scripts .kts, Objective-C++ .mm, .inc too), upper-case extensions
    ('README.md', 4, None, False),
    ('browser/foo.mm', 4, None, False),
    ('browser/foo.inc', 4, None, False),
    ('mobile/android/build.gradle.kts', 4, None, False),
    ('browser/X.RS', 4, None, False),
    ('browser/Y.KT', 4, None, False),
    ('browser/Z.TS', 4, None, False),
]
# a file without a final newline counts like `wc -l`: newlines only
NO_NEWLINE = ('browser/nonl.js', 'a\nb', 'js', False)
# a blob with a NUL byte is binary and counts 0 lines, whatever its extension (an MPEG transport stream named .ts)
BINARY = [('dom/media/stream.ts', b'G\x00\x11\x10\n' * 9, 'ts', False),
          ('browser/packed.js', b'var a;\n\x00\n', 'js', False)]

# is_test() cases built from the test-path rules (described in docs/methodology.md)
IS_TEST = [
    # rule 1: path prefixes
    ('testing/web-platform/tests/a.js', True),
    ('testing/mozbase/x.py', True),
    ('js/src/tests/non262/a.js', True),
    ('js/src/jit-test/tests/a.js', True),
    ('js/src/jsapi-tests/testFoo.cpp', True),
    ('js/src/octane/a.js', True),
    ('third_party/webkit/PerformanceTests/a.js', True),
    # rule 2: directory names
    ('dom/base/test/test_a.html', True),
    ('tests/a.js', True),
    ('gfx/tests/gtest/A.cpp', True),
    ('xpcom/gtests/a.cpp', True),
    ('dom/mochitest/a.js', True),
    ('dom/mochitests/a.js', True),
    ('netwerk/xpcshell/a.js', True),
    ('layout/reftest/a.html', True),
    ('layout/reftests/a.html', True),
    ('layout/crashtest/a.html', True),
    ('layout/crashtests/a.html', True),
    ('browser/components/__tests__/a.js', True),
    ('mobile/android/app/src/androidTest/java/A.java', True),
    ('third_party/foo/test262/a.js', True),
    ('media/libvpx/unittests/a.cc', True),
    ('third_party/googletest/src/a.cc', True),
    ('python/foo/testdata/a.py', True),
    ('tools/fixtures/a.js', True),
    ('devtools/browser_tests/a.js', True),
    ('foo/jsapi-tests/a.cpp', True),
    ('foo/jit-test/a.js', True),
    ('third_party/rust/serde/serde-tests/a.rs', True),
    ('third_party/rust/foo/foo_test/a.rs', True),
    ('third_party/rust/foo/foo_tests/a.rs', True),
    ('third_party/rust/foo/test-utils/a.rs', True),
    ('third_party/rust/foo/tests_common/a.rs', True),
    ('python/mozbuild/mozbuild/testing/a.py', True),  # nested testing directory
    # rule 3: Rust test file names
    ('third_party/rust/foo/src/tests.rs', True),
    ('third_party/rust/foo/src/test.rs', True),
    ('servo/components/style/a_test.rs', True),
    ('servo/components/style/a_tests.rs', True),
    # not test paths
    ('dom/base/nsDocument.cpp', False),
    ('testing.c', False),
    ('foo/testing.py', False),
    ('testingx/a.c', False),
    ('a/b/testing', False),
    ('src/latest/a.rs', False),
    ('foo/test.cpp', False),
    ('foo/tests.py', False),
    ('foo/testsuite/a.c', False),
    ('foo/contest/a.c', False),
    ('foo/attestation/a.rs', False),
    ('third_party/rust/foo/src/test_util.rs', False),
    ('third_party/rust/foo/src/contest.rs', False),
    ('mytesting/foo/a.c', False),
]


def run(cwd, *args, **kw):
    return subprocess.run(args, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw).stdout


def git(cwd, *args, date=None):
    env = None
    if date:
        env = dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    return run(cwd, 'git', *args, env=env).decode().strip()


def write(root, path, text):
    full = os.path.join(root, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'wb' if isinstance(text, bytes) else 'w') as f:
        f.write(text)


def body(n):
    return ''.join('line %d\n' % i for i in range(n))


def expected(files, browser_excluded=history.BROWSER_EXCLUDED_PREFIXES):
    """(all, browser): all counts every file of a counted language; browser drops the prefixes and the tests."""
    allc, browser = dict.fromkeys(history.KEYS, 0), dict.fromkeys(history.KEYS, 0)
    for path, n, lang, test in files:
        if lang is None:
            continue
        allc[lang] += n
        if not test and not path.startswith(tuple(browser_excluded)):
            browser[lang] += n
    return allc, browser


def quiet():
    return contextlib.redirect_stderr(io.StringIO())


class GitTestCase(unittest.TestCase):
    """An "upstream" repository with four commits:

    c1  FIREFOX_46_0_RELEASE (annotated)
    c2  FIREFOX_47_0_BUILD1 only (like release 125) and FIREFOX_47_0b1_RELEASE (a beta, ignored)
    c3  FIREFOX_48_0_BUILD1 and FIREFOX_48_0_RELEASE (lightweight; RELEASE wins), FIREFOX_48_0_1_RELEASE (ignored)
    c4  FIREFOX_49_0_BUILD1 only: newest major, not released yet, so never counted
    """

    @classmethod
    def setUpClass(cls):
        cls._env = mock.patch.dict(os.environ, {
            'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1',
            'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.com',
            'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@example.com'})
        cls._env.start()
        cls.tmp = tempfile.mkdtemp(prefix='test_history-')
        up = cls.up = os.path.join(cls.tmp, 'upstream')
        os.makedirs(up)
        git(up, 'init', '-q')
        git(up, 'symbolic-ref', 'HEAD', 'refs/heads/main')
        git(up, 'config', 'uploadpack.allowFilter', 'true')
        git(up, 'config', 'uploadpack.allowAnySHA1InWant', 'true')
        for path, n, _, _ in FILES:
            write(up, path, body(n))
        write(up, NO_NEWLINE[0], NO_NEWLINE[1])
        for path, data, _, _ in BINARY:
            write(up, path, data)
        cls.c1_files = FILES + [(NO_NEWLINE[0], 1, 'js', False)] + [(p, 0, k, t) for p, _, k, t in BINARY]
        cls.commit('c1', '2016-04-26T10:00:00Z')
        git(up, 'tag', '-a', '-m', '46', 'FIREFOX_46_0_RELEASE')

        write(up, 'browser/app.rs', body(30))
        write(up, 'mobile/android/m.rs', body(70))
        cls.commit('c2', '2024-04-15T10:00:00Z')
        git(up, 'tag', 'FIREFOX_47_0_BUILD1')
        git(up, 'tag', 'FIREFOX_47_0b1_RELEASE')

        write(up, 'browser/new.mjs', body(12))
        cls.commit('c3', '2024-05-13T10:00:00Z')
        git(up, 'tag', 'FIREFOX_48_0_BUILD1')
        git(up, 'tag', 'FIREFOX_48_0_RELEASE')
        git(up, 'tag', 'FIREFOX_48_0_1_RELEASE')

        write(up, 'browser/later.rs', body(5))
        cls.commit('c4', '2024-06-10T10:00:00Z')
        git(up, 'tag', 'FIREFOX_49_0_BUILD1')

        cls.full_history = os.path.join(cls.tmp, 'full.json')
        with quiet():
            history.backfill(up, cls.full_history)
        with open(cls.full_history, 'rb') as f:
            cls.full_bytes = f.read()

    @classmethod
    def commit(cls, msg, date):
        git(cls.up, 'add', '-A')
        git(cls.up, 'commit', '-q', '-m', msg, date=date)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        cls._env.stop()

    def mkdtemp(self):
        d = tempfile.mkdtemp(dir=self.tmp)
        return d

    def url(self):
        return 'file://' + self.up


class PickMajorsTest(unittest.TestCase):
    def test_125_fallback(self):
        names = ['FIREFOX_124_0_RELEASE', 'FIREFOX_124_0_BUILD2', 'FIREFOX_125_0_BUILD1', 'FIREFOX_125_0_1_RELEASE',
                 'FIREFOX_125_0b3_RELEASE', 'FIREFOX_126_0_BUILD1', 'FIREFOX_126_0_RELEASE', 'FIREFOX_127_0_BUILD1']
        with quiet():
            got = history.pick_majors(names, first=124)
        self.assertEqual(got, [(124, 'FIREFOX_124_0_RELEASE'), (125, 'FIREFOX_125_0_BUILD1'),
                               (126, 'FIREFOX_126_0_RELEASE')])

    def test_release_tag_wins_over_build1(self):
        names = ['FIREFOX_125_0_BUILD1', 'FIREFOX_125_0_RELEASE']
        self.assertEqual(history.pick_majors(names, first=125), [(125, 'FIREFOX_125_0_RELEASE')])

    def test_newest_build_only_major_is_left_out(self):
        names = ['FIREFOX_157_0_RELEASE', 'FIREFOX_158_0_BUILD1']
        self.assertEqual(history.pick_majors(names, first=157), [(157, 'FIREFOX_157_0_RELEASE')])

    def test_gaps_and_empty(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            got = history.pick_majors(['FIREFOX_46_0_RELEASE', 'FIREFOX_48_0_RELEASE'])
        self.assertEqual(got, [(46, 'FIREFOX_46_0_RELEASE'), (48, 'FIREFOX_48_0_RELEASE')])
        self.assertIn('no tag for release 47', err.getvalue())
        self.assertEqual(history.pick_majors([]), [])
        self.assertEqual(history.pick_majors(['FIREFOX_45_0_RELEASE']), [])


class IsTestTest(unittest.TestCase):
    def test_table(self):
        for path, want in IS_TEST:
            with self.subTest(path=path):
                self.assertIs(history.is_test(path), want)

    def test_fixture_flags_agree(self):
        for path, _, _, test in FILES:
            with self.subTest(path=path):
                self.assertIs(history.is_test(path), test)


class CountTest(GitTestCase):
    def test_all_includes_mobile_browser_excludes_mobile_and_tests(self):
        r = history.count_release(self.up, 'FIREFOX_46_0_RELEASE')
        allc, browser = expected(self.c1_files)
        self.assertEqual(r['all'], allc)
        self.assertEqual(r['browser'], browser)
        # spot values computed by hand. all .rs: 3 + 5 (test) + 4 (test) + 50 (mobile/) + 11 (mobilex/);
        # browser .rs: 3 + 11 (mobile/ and the tests dropped)
        self.assertEqual(r['all']['rust'], 73)
        self.assertEqual(r['browser']['rust'], 14)
        self.assertEqual(r['all']['java'], 1 + 100 + 20)   # mobile/ is in "all", its tests too
        self.assertEqual(r['browser']['java'], 1)
        # Kotlin (v3): counted in both views; mobile/ Kotlin and Kotlin tests only in "all"; .kts never
        self.assertEqual(r['all']['kt'], 4 + 40 + 13 + 6)
        self.assertEqual(r['browser']['kt'], 4)
        self.assertEqual(r['all']['js'], 2 + 3 + 1 + 1 + 9 + 1)  # .mjs counted, no-newline file counts 1, binary 0
        self.assertEqual(r['browser']['js'], 2 + 3 + 1 + 1 + 1)
        # v3: TypeScript (the binary .ts counts 0), .hpp/.hh in cpp (h is .h only), .S/.s in asm
        self.assertEqual((r['all']['ts'], r['browser']['ts']), (5 + 7, 5))
        self.assertEqual((r['all']['cpp'], r['browser']['cpp']), (4 + 1 + 1 + 1 + 4 + 4 + 6, 4 + 1 + 1 + 1 + 4 + 4))
        self.assertEqual(r['all']['h'], 10)
        self.assertEqual((r['all']['asm'], r['browser']['asm']), (2 + 4 + 3, 2 + 4 + 3))
        self.assertEqual(list(r), ['sha', 'date', 'all', 'browser'])
        self.assertEqual(list(r['all']), ['rust', 'c', 'cpp', 'h', 'js', 'ts', 'html', 'py', 'java', 'kt', 'asm'])
        self.assertEqual(list(r['browser']), list(r['all']))
        self.assertEqual(r['date'], '2016-04-26')
        self.assertEqual(r['sha'], git(self.up, 'rev-parse', 'FIREFOX_46_0_RELEASE^{commit}'))

    def test_browser_prefixes_never_change_all(self):
        default = history.count_release(self.up, 'FIREFOX_46_0_RELEASE')
        r = history.count_release(self.up, 'FIREFOX_46_0_RELEASE', ())
        self.assertEqual((r['all'], r['browser']), expected(self.c1_files, ()))
        self.assertEqual(r['all'], default['all'])
        self.assertEqual(r['browser']['java'], 101)  # mobile/ non-test code is browser code without the prefix
        self.assertEqual(r['browser']['kt'], 4 + 40)
        r = history.count_release(self.up, 'FIREFOX_46_0_RELEASE', ('media/', 'browser/tests/'))
        self.assertEqual((r['all'], r['browser']), expected(self.c1_files, ('media/', 'browser/tests/')))
        self.assertEqual(r['all'], default['all'])
        self.assertEqual((r['all']['asm'], r['browser']['asm']), (9, 0))

    def test_shared_cache_gives_same_counts(self):
        cache = {}
        a = history.count_release(self.up, 'FIREFOX_46_0_RELEASE', cache=cache)
        n = len(cache)
        b = history.count_release(self.up, 'FIREFOX_47_0_BUILD1', cache=cache)
        self.assertEqual(len(cache), n + 2)  # only the changed browser/app.rs and mobile/android/m.rs were read
        self.assertEqual(b, history.count_release(self.up, 'FIREFOX_47_0_BUILD1'))
        self.assertEqual(b['all']['rust'] - a['all']['rust'], 27 + 20)
        self.assertEqual(b['browser']['rust'] - a['browser']['rust'], 27)


# v4: tooling prefixes of the "browser" view. (path, lines, language key, excluded from "browser"?)
TOOLING = [
    ('build/clang-plugin/Checker.cpp', 3, 'cpp', True),
    ('build/pgo/index.html', 4, 'html', True),
    ('docs/conf.py', 2, 'py', True),
    ('python/mozbuild/mozbuild/base.py', 5, 'py', True),
    ('taskcluster/docker/x/main.rs', 6, 'rust', True),
    ('third_party/node/node_modules/webpack/lib/a.js', 7, 'js', True),
    ('third_party/python/pip/pip/a.py', 8, 'py', True),
    ('tools/@types/lib.gecko.dom.d.ts', 9, 'ts', True),
    ('tools/lint/eslint/plugin.mjs', 2, 'js', True),
    ('tools/lint/rust/x.rs', 3, 'rust', True),
    ('tools/tryselect/selectors/fuzzy.py', 4, 'py', True),
    # shipped code and look-alike names stay in "browser"
    ('tools/profiler/core/platform.cpp', 10, 'cpp', False),   # the Gecko Profiler, compiled into libxul
    ('tools/fuzzing/interface/a.cpp', 2, 'cpp', False),
    ('tools/performance/PerfStats.cpp', 2, 'cpp', False),
    ('build/unix/elfhack/elfhack.cpp', 3, 'cpp', False),
    ('build/rust/shim/lib.rs', 4, 'rust', False),
    ('build/moz.configure/init.configure.py', 1, 'py', False),   # only the listed build/ subdirectories go
    ('config/nsinstall.c', 2, 'c', False),
    ('devtools/client/a.js', 3, 'js', False),
    ('js/src/vm/a.cpp', 3, 'cpp', False),
    ('third_party/rust/serde/src/lib.rs', 5, 'rust', False),
    ('third_party/js/PKI.js/a.ts', 2, 'ts', False),
    ('third_party/nodejs/a.js', 2, 'js', False),     # a prefix is a directory, not a name prefix
    ('tools/lintx/a.py', 2, 'py', False),
    ('mytools/lint/a.py', 2, 'py', False),
    ('src/python/a.py', 2, 'py', False),              # matched from the start of the path only
    ('browser/docs/a.js', 2, 'js', False),
]


class ToolingPrefixTest(GitTestCase):
    """The v4 tooling prefixes leave "browser" and never "all"; shipped code under tools/ and build/ stays."""

    def test_prefix_table(self):
        self.assertEqual(history.METHOD_VERSION, 4)
        self.assertEqual(history.BROWSER_EXCLUDED_PREFIXES, (
            'mobile/', 'build/clang-plugin/', 'build/pgo/', 'docs/', 'python/', 'taskcluster/', 'third_party/node/',
            'third_party/python/', 'tools/@types/', 'tools/lint/', 'tools/tryselect/'))
        self.assertEqual(history.default_meta()['browser_excluded_prefixes'], list(history.BROWSER_EXCLUDED_PREFIXES))
        self.assertTrue(all(p.endswith('/') for p in history.BROWSER_EXCLUDED_PREFIXES))
        for path, _, _, excluded in TOOLING:
            with self.subTest(path=path):
                self.assertFalse(history.is_test(path))
                self.assertIs(path.startswith(history.BROWSER_EXCLUDED_PREFIXES), excluded)

    def test_counts(self):
        r = os.path.join(self.mkdtemp(), 'tooling')
        os.makedirs(r)
        git(r, 'init', '-q')
        for path, n, _, _ in TOOLING:
            write(r, path, body(n))
        write(r, 'tools/lint/test/t.py', body(50))   # a test path under a tooling prefix: in "all" only, once
        git(r, 'add', '-A')
        git(r, 'commit', '-q', '-m', 'tooling', date='2026-09-24T10:00:00Z')
        got = history.count_release(r, 'HEAD')
        files = [(p, n, k, False) for p, n, k, _ in TOOLING] + [('tools/lint/test/t.py', 50, 'py', True)]
        self.assertEqual((got['all'], got['browser']), expected(files))
        allc = dict.fromkeys(history.KEYS, 0)
        browser = dict.fromkeys(history.KEYS, 0)
        for path, n, lang, excluded in TOOLING:
            allc[lang] += n
            browser[lang] += 0 if excluded else n
        allc['py'] += 50
        self.assertEqual(got['all'], allc)          # every tooling file is in "all"
        self.assertEqual(got['browser'], browser)
        self.assertEqual(got['browser']['rust'], 4 + 5)             # build/rust and third_party/rust only
        self.assertEqual(got['browser']['cpp'], 10 + 2 + 2 + 3 + 3)  # profiler, fuzzing, performance, elfhack, js/src
        self.assertEqual(got['browser']['ts'], 2)                   # tools/@types left out, PKI.js kept
        # with the v3 prefixes everything but the test file is browser code: the prefixes change "browser" only
        v3 = history.count_release(r, 'HEAD', ('mobile/',))
        self.assertEqual(v3['all'], got['all'])
        self.assertEqual(sum(v3['browser'].values()), sum(n for _, n, _, _ in TOOLING))


class HeadCliTest(GitTestCase):
    def head(self, *flags):
        out = os.path.join(self.mkdtemp(), 'head.json')
        with quiet():
            history.main(['head', self.up, '--out', out] + list(flags))
        with open(out) as f:
            return json.load(f)

    def test_head_record(self):
        r = self.head()
        self.assertEqual(list(r), ['sha', 'date', 'all', 'browser'])
        self.assertEqual((r['all']['java'], r['browser']['java']), (121, 1))
        self.assertEqual((r['all']['kt'], r['browser']['kt']), (63, 4))
        self.assertEqual(r['sha'], git(self.up, 'rev-parse', 'HEAD'))
        self.assertEqual(r, history.count_release(self.up, 'HEAD'))

    def test_exclude_flags_are_gone(self):
        for cmd in (['head', self.up], ['backfill', self.up, os.path.join(self.mkdtemp(), 'h.json')]):
            for flags in (['--exclude', 'mobile/'], ['--no-exclude']):
                with self.subTest(cmd=cmd[0], flags=flags), quiet(), self.assertRaises(SystemExit) as cm:
                    history.main(cmd + flags)
                self.assertEqual(cm.exception.code, 2)
        for flag in ('--with-artifact', '--artifact-deadline'):
            with self.subTest(flag=flag), quiet(), self.assertRaises(SystemExit):
                history.main(['build-site', self.full_history, '--repo', self.up, '--out', self.mkdtemp(), flag])
        with quiet(), self.assertRaises(SystemExit):
            history.main(['set-artifact', self.full_history])


class BackfillTest(GitTestCase):
    def test_file_shape(self):
        lines = self.full_bytes.decode().split('\n')
        self.assertEqual(lines[0], '{"method_version":4,"browser_excluded_prefixes":["mobile/","build/clang-plugin/",'
                                   '"build/pgo/","docs/","python/","taskcluster/","third_party/node/",'
                                   '"third_party/python/","tools/@types/","tools/lint/","tools/tryselect/"],'
                                   '"header_split":{"c":0.185,"cpp":0.815},"releases":[')
        self.assertEqual(lines[-2:], [']}', ''])
        recs = [json.loads(line.rstrip(',')) for line in lines[1:-2]]
        self.assertEqual([(r['v'], r['tag']) for r in recs],
                         [(46, 'FIREFOX_46_0_RELEASE'), (47, 'FIREFOX_47_0_BUILD1'), (48, 'FIREFOX_48_0_RELEASE')])
        for r in recs:
            self.assertEqual(list(r), ['v', 'tag', 'sha', 'date', 'all', 'browser'])
            self.assertEqual(list(r['all']), history.KEYS)
            self.assertEqual(list(r['browser']), history.KEYS)
            self.assertEqual((r['all']['kt'], r['browser']['kt']), (63, 4))
        self.assertNotIn(b'artifact', self.full_bytes)
        self.assertNotIn(b'nontest', self.full_bytes)
        data = json.loads(self.full_bytes)
        self.assertEqual(data['header_split'], {'c': 0.185, 'cpp': 0.815})
        self.assertEqual(data['releases'], recs)
        self.assertEqual(recs[1]['all']['rust'], 73 + 27 + 20)   # browser/app.rs and mobile/android/m.rs grew
        self.assertEqual(recs[1]['browser']['rust'], 14 + 27)
        self.assertEqual(recs[2]['all']['js'], recs[1]['all']['js'] + 12)

    def test_deterministic(self):
        out = os.path.join(self.mkdtemp(), 'again.json')
        with quiet():
            history.backfill(self.up, out)
        with open(out, 'rb') as f:
            self.assertEqual(f.read(), self.full_bytes)

    def test_blobless_clone(self):
        d = self.mkdtemp()
        git(d, 'clone', '-q', '--no-checkout', '--filter=blob:none', self.url(), 'c')
        clone = os.path.join(d, 'c')
        self.assertTrue(history.promisor_remote(clone))
        self.assertTrue(history.missing_blobs(clone, [h for h, _, _ in history.tree(clone, 'HEAD')]))
        # count_release alone fetches what it needs
        with quiet():
            r = history.count_release(clone, 'FIREFOX_46_0_RELEASE')
        self.assertEqual(r, history.count_release(self.up, 'FIREFOX_46_0_RELEASE'))
        out = os.path.join(d, 'h.json')
        with quiet():
            history.backfill(clone, out)
        with open(out, 'rb') as f:
            self.assertEqual(f.read(), self.full_bytes)


class AppendTest(GitTestCase):
    def shallow(self):
        d = self.mkdtemp()
        git(d, 'clone', '-q', '--depth', '1', self.url(), 'c')
        return os.path.join(d, 'c')

    def truncated(self, keep):
        lines = self.full_bytes.decode().split('\n')
        recs = lines[1:-2]
        text = '\n'.join([lines[0]] + [r.rstrip(',') if i == keep - 1 else r for i, r in enumerate(recs[:keep])]
                         + [']}', ''])
        path = os.path.join(self.mkdtemp(), 'history.json')
        with open(path, 'w') as f:
            f.write(text)
        return path

    def test_append_matches_backfill_and_is_idempotent(self):
        clone = self.shallow()
        path = self.truncated(1)
        with mock.patch.object(history, 'releases', side_effect=AssertionError('releases() called')), quiet():
            self.assertEqual(history.append(path, clone), 2)
            with open(path, 'rb') as f:
                self.assertEqual(f.read(), self.full_bytes)
            st = os.stat(path)
            self.assertEqual(history.append(path, clone), 0)
            self.assertEqual(history.main(['append', path, '--repo', clone]), 0)
        with open(path, 'rb') as f:
            self.assertEqual(f.read(), self.full_bytes)
        self.assertEqual(os.stat(path).st_mtime_ns, st.st_mtime_ns)  # not rewritten
        self.assertEqual(os.stat(path).st_ino, st.st_ino)

    def test_new_release_adds_one_line(self):
        up = os.path.join(self.mkdtemp(), 'up2')
        git(self.tmp, 'clone', '-q', '--bare', self.up, up)
        git(up, 'config', 'uploadpack.allowAnySHA1InWant', 'true')
        d = self.mkdtemp()
        git(d, 'clone', '-q', '--depth', '1', 'file://' + up, 'c')
        clone = os.path.join(d, 'c')
        path = self.truncated(3)
        with quiet():
            self.assertEqual(history.append(path, clone), 0)
        git(up, 'tag', 'FIREFOX_49_0_RELEASE', 'FIREFOX_49_0_BUILD1')
        with quiet():
            self.assertEqual(history.append(path, clone), 1)
        with open(path) as f:
            text = f.read()
        self.assertTrue(text.startswith(self.full_bytes.decode()[:-len('\n]}\n')] + ',\n{"v":49,'))
        self.assertEqual(len(text.splitlines()), len(self.full_bytes.splitlines()) + 1)
        rec = json.loads(text)['releases'][-1]
        self.assertEqual((rec['v'], rec['tag'], rec['date']), (49, 'FIREFOX_49_0_RELEASE', '2024-06-10'))
        self.assertEqual((rec['all']['java'], rec['browser']['java']), (121, 1))
        self.assertEqual(rec, dict(v=49, tag='FIREFOX_49_0_RELEASE',
                                   **history.count_release(self.up, 'FIREFOX_49_0_BUILD1')))

    def test_browser_prefixes_come_from_the_file(self):
        meta, recs = history.read_history(self.full_history)
        meta['browser_excluded_prefixes'] = ['media/']
        path = os.path.join(self.mkdtemp(), 'history.json')
        with open(path, 'w') as f:
            f.write(history.format_history(meta, recs[:1]))
        with quiet():
            self.assertEqual(history.append(path, self.shallow()), 2)
        meta2, recs2 = history.read_history(path)
        self.assertEqual(meta2, meta)
        rec = recs2[-1]
        self.assertEqual((rec['browser']['asm'], rec['browser']['java']), (0, 101))
        self.assertEqual(rec['all'], recs[-1]['all'])

    def test_other_method_version_is_refused(self):
        clone = self.shallow()
        meta, recs = history.read_history(self.full_history)
        v1 = {'method_version': 1, 'excluded_prefixes': ['mobile/'], 'header_split': meta['header_split']}
        old = [dict({k: v for k, v in r.items() if k != 'browser'}, nontest=r['browser'], artifact=None)
               for r in recs[:1]]
        # a v2 file: the same layout without the kt key
        v2 = [dict(r, **{view: {k: n for k, n in r[view].items() if k != 'kt'} for view in ('all', 'browser')})
              for r in recs[:1]]
        cases = [('v1', history.format_history(v1, old)),
                 ('v2', history.format_history(dict(meta, method_version=2), v2)),
                 ('v3', history.format_history(dict(meta, method_version=3, browser_excluded_prefixes=['mobile/']),
                                               recs[:1])),
                 ('v5', history.format_history(dict(meta, method_version=5), recs[:1])),
                 ('none', history.format_history({k: v for k, v in meta.items() if k != 'method_version'}, recs[:1]))]
        for name, text in cases:
            path = os.path.join(self.mkdtemp(), 'history.json')
            with open(path, 'w') as f:
                f.write(text)
            err = io.StringIO()
            with self.subTest(name), mock.patch.object(history, 'remote_tags', side_effect=AssertionError('listed')), \
                    contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
                history.main(['append', path, '--repo', clone])
            self.assertEqual(cm.exception.code, 1)
            self.assertIn('method_version', err.getvalue())
            self.assertNotIn('Traceback', err.getvalue())
            with open(path) as f:
                self.assertEqual(f.read(), text)   # untouched
            with self.subTest(name + ' build-site'), quiet(), self.assertRaises(SystemExit) as cm:
                history.main(['build-site', path, '--repo', clone, '--out', self.mkdtemp()])
            self.assertEqual(cm.exception.code, 1)


class ZeroDateTest(GitTestCase):
    """A commit with a zero timestamp (like FIREFOX_123_0_RELEASE) takes the date of its first dated ancestor."""

    def repo(self):
        r = os.path.join(self.mkdtemp(), 'zero')
        os.makedirs(r)
        git(r, 'init', '-q')
        git(r, 'config', 'uploadpack.allowFilter', 'true')
        write(r, 'a.rs', body(2))
        git(r, 'add', '-A')
        git(r, 'commit', '-q', '-m', 'dated', date='2024-02-13T05:05:35Z')
        write(r, 'a.rs', body(3))
        git(r, 'add', '-A')
        git(r, 'commit', '-q', '-m', 'zero', date='@0 +0000')
        git(r, 'tag', 'FIREFOX_123_0_RELEASE')
        self.assertEqual(git(r, 'log', '-1', '--format=%ct %cs'), '0 1970-01-01')
        return r

    def test_zero_timestamp_uses_first_dated_ancestor(self):
        r = self.repo()
        rec = history.count_release(r, 'FIREFOX_123_0_RELEASE')
        self.assertEqual(rec['date'], '2024-02-13')
        self.assertEqual(rec['sha'], git(r, 'rev-parse', 'HEAD'))  # the sha stays the tagged commit
        self.assertEqual(rec['all']['rust'], 3)

    def test_zero_timestamp_without_ancestor_fails(self):
        d = self.mkdtemp()
        git(d, 'clone', '-q', '--depth', '1', 'file://' + self.repo(), 'c')
        clone = os.path.join(d, 'c')
        with self.assertRaisesRegex(history.HistoryError, 'zero timestamp'):
            history.count_release(clone, 'HEAD')
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            history.main(['head', clone])
        self.assertEqual(cm.exception.code, 1)
        self.assertIn('error: commit', err.getvalue())
        self.assertNotIn('Traceback', err.getvalue())

    def test_append_deepens_a_zero_timestamp_tag(self):
        up = self.repo()
        d = self.mkdtemp()
        git(d, 'clone', '-q', '--depth', '1', '--no-tags', 'file://' + up, 'c')
        clone = os.path.join(d, 'c')
        self.assertEqual(git(clone, 'rev-list', '--count', 'HEAD'), '1')
        path = os.path.join(d, 'history.json')
        prev = dict(v=122, tag='FIREFOX_122_0_RELEASE', **history.count_release(up, 'HEAD~1'))
        with open(path, 'w') as f:
            f.write(history.format_history(history.default_meta(), [prev]))
        with quiet():
            self.assertEqual(history.append(path, clone), 1)
        rec = history.read_history(path)[1][-1]
        self.assertEqual((rec['v'], rec['tag'], rec['date']), (123, 'FIREFOX_123_0_RELEASE', '2024-02-13'))
        self.assertEqual(rec['sha'], git(up, 'rev-parse', 'HEAD'))
        self.assertEqual(rec['all']['rust'], 3)


class ErrorMessageTest(GitTestCase):
    def test_head_on_empty_repo(self):
        r = os.path.join(self.mkdtemp(), 'empty')
        os.makedirs(r)
        git(r, 'init', '-q')
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            history.main(['head', r])
        self.assertEqual(cm.exception.code, 1)
        self.assertIn('error: HEAD is not a commit', err.getvalue())

    def test_append_starts_at_the_files_first_release(self):
        d = self.mkdtemp()
        git(d, 'clone', '-q', '--depth', '1', self.url(), 'c')
        meta, recs = history.read_history(self.full_history)
        path = os.path.join(d, 'from47.json')
        with open(path, 'w') as f:
            f.write(history.format_history(meta, recs[1:]))
        with open(path, 'rb') as f:
            before = f.read()
        with quiet():
            self.assertEqual(history.append(path, os.path.join(d, 'c')), 0)  # 46 is not added
        with open(path, 'rb') as f:
            self.assertEqual(f.read(), before)


class BuildSiteTest(GitTestCase):
    def test_build_site(self):
        clone = os.path.join(self.mkdtemp(), 'c')
        git(self.tmp, 'clone', '-q', '--depth', '1', self.url(), clone)
        out = self.mkdtemp()
        now = datetime(2026, 10, 5, 0, 55, 25, tzinfo=timezone.utc)
        with quiet():
            path = history.build_site(self.full_history, clone, out, now=now)
        self.assertEqual(path, os.path.join(out, 'data.json'))
        with open(path) as f:
            data = json.load(f)
        hist = json.loads(self.full_bytes)
        self.assertEqual(list(data), ['meta_date', 'title_date', 'lang', 'method_version', 'browser_excluded_prefixes',
                                      'header_split', 'releases', 'head'])
        with open(path) as f:
            text = f.read()
        self.assertNotIn('artifact', text)
        self.assertNotIn('nontest', text)
        self.assertEqual(data['meta_date'], '2026-10-05T00:55:25+00:00')
        self.assertEqual(data['title_date'], 'Oct 2026')
        self.assertEqual(data['releases'], hist['releases'])
        for k in ('method_version', 'browser_excluded_prefixes', 'header_split'):
            self.assertEqual(data[k], hist[k])
        self.assertEqual((data['method_version'], data['browser_excluded_prefixes']),
                         (4, list(history.BROWSER_EXCLUDED_PREFIXES)))
        head = data['head']
        self.assertEqual(list(head), ['sha', 'date', 'all', 'browser'])
        self.assertEqual(list(head['all']), ['rust', 'c', 'cpp', 'h', 'js', 'ts', 'html', 'py', 'java', 'kt', 'asm'])
        self.assertEqual(list(head['browser']), list(head['all']))
        self.assertEqual(head['sha'], git(self.up, 'rev-parse', 'HEAD'))
        self.assertEqual(head, history.count_release(self.up, 'HEAD'))
        self.assertEqual(head['date'], '2024-06-10')
        a = head['all']
        hc = round(a['h'] * 0.185)
        self.assertEqual(data['lang'], [
            {'name': 'Rust', 'loc': a['rust']}, {'name': 'C', 'loc': a['c'] + hc},
            {'name': 'C++', 'loc': a['cpp'] + a['h'] - hc}, {'name': 'JavaScript', 'loc': a['js']},
            {'name': 'TypeScript', 'loc': a['ts']}, {'name': 'HTML', 'loc': a['html']}, {'name': 'Python', 'loc': a['py']},
            {'name': 'Java', 'loc': a['java']}, {'name': 'Kotlin', 'loc': a['kt']},
            {'name': 'Assembly', 'loc': a['asm']}])
        self.assertEqual(sum(x['loc'] for x in data['lang']), sum(a.values()))
        self.assertEqual(a['h'], 10)
        # the pie is "all", so mobile/ is in it: Java 1 + 100 + 20, Rust 73 + 27 + 20 + 5 (browser/later.rs)
        self.assertEqual((data['lang'][7]['loc'], data['lang'][0]['loc']), (121, 125))
        self.assertEqual(data['lang'][8], {'name': 'Kotlin', 'loc': 4 + 40 + 13 + 6})   # mobile/ is in the pie
        self.assertEqual(data['lang'][4], {'name': 'TypeScript', 'loc': 5 + 7})       # the binary .ts counts 0
        # C++ is cpp (.hpp and .hh included) plus its share of .h
        self.assertEqual((data['lang'][1]['loc'], data['lang'][2]['loc']), (2 + 2, 21 + 10 - 2))

    def test_cli_uses_current_time(self):
        out = self.mkdtemp()
        with quiet():
            history.main(['build-site', self.full_history, '--repo', self.up, '--out', out])
        with open(os.path.join(out, 'data.json')) as f:
            data = json.load(f)
        now = datetime.now(timezone.utc)
        self.assertTrue(data['meta_date'].endswith('+00:00'))
        self.assertLess(abs((datetime.fromisoformat(data['meta_date']) - now).total_seconds()), 300)
        self.assertEqual(len(data['lang']), 10)


if __name__ == '__main__':
    unittest.main()
