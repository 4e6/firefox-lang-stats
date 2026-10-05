"""Tests for dev/artifact.py. No network: the web is a stub and every repository is a throwaway local one.

Run: python3 -m unittest discover -s dev
"""
import contextlib
import http.server
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
import zlib
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import artifact  # noqa: E402
import history  # noqa: E402

GIT = 'git:github.com/mozilla-firefox/firefox'
HG_REV = 'f' * 40
XUL_BID = bytes(range(1, 21))          # the shipped libxul.so
GTEST_BID = bytes(range(101, 121))     # the gtest libxul.so in the same zip
FOO_BID = bytes(range(41, 61))
TEST_BID = bytes(range(61, 81))        # a test binary that is only in the zip


def did(bid):
    return artifact.artifact_files.debug_id(bid)


def quiet():
    return contextlib.redirect_stderr(io.StringIO())


def fake_elf(build_id=None, note_off=None, size=None):
    """A minimal 64-bit little-endian ELF file with one PT_NOTE holding a GNU build id (or no program headers)."""
    phoff, phentsize = 64, 56
    phnum = 1 if build_id else 0
    ident = b'\x7fELF' + bytes([2, 1, 1]) + b'\0' * 9
    hdr = ident + struct.pack('<HHIQQQIHHHHHH', 3, 62, 1, 0, phoff, 0, 0, 64, phentsize, phnum, 64, 0, 0)
    data = bytearray(hdr)
    if build_id:
        note = struct.pack('<III', 4, len(build_id), 3) + b'GNU\0' + build_id
        note_off = note_off or phoff + phentsize
        data += struct.pack('<IIQQQQQQ', 4, 4, note_off, 0, 0, len(note), len(note), 4)
        data += b'\0' * (note_off - len(data)) + note
    if size:
        data += b'\0' * (size - len(data))
    return bytes(data)


def make_zip(files, method=zipfile.ZIP_DEFLATED):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', method) as z:
        for name, data in files:
            z.writestr(name, data)
    return buf.getvalue()


def make_optimized_jar(files):
    """A Mozilla "optimized" jar (as in release builds): a 4-byte read-ahead length, the central directory, the stored
    entries, then the end record whose directory offset (4) is absolute. zipfile.ZipFile rejects it."""
    files = [(n.encode(), d.encode() if isinstance(d, str) else d) for n, d in files]
    cdsize = sum(46 + len(n) for n, _ in files)
    off, cd, local = 4 + cdsize, b'', b''
    for n, d in files:
        crc = zlib.crc32(d)
        cd += struct.pack('<IHHHHHHIIIHHHHHII', 0x02014b50, 20, 10, 0, 0, 0, 0, crc, len(d), len(d), len(n), 0, 0, 0,
                          0, 0, off + len(local)) + n
        local += struct.pack('<IHHHHHIIIHH', 0x04034b50, 10, 0, 0, 0, 0, crc, len(d), len(d), len(n), 0) + n + d
    end = struct.pack('<IHHHHIIH', 0x06054b50, 0, 0, len(files), len(files), cdsize, 4, 0)
    return struct.pack('<I', 4 + cdsize + len(local)) + cd + local + end


def make_tar_xz(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:xz') as tf:
        for name, data in files:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def sym(module, bid, records, funcs=3):
    lines = ['MODULE Linux x86_64 %s %s' % (did(bid), module), 'INFO CODE_ID %s' % bid.hex().upper()]
    lines += ['FILE %d %s' % (i, r) for i, r in enumerate(records)]
    lines += ['FUNC %x 10 0 f%d' % (i * 16, i) for i in range(funcs)] + ['0 10 1 0']
    return ('\n'.join(lines) + '\n').encode()


class FakeResponse:
    def __init__(self, url, data, status=200, headers=None):
        self.url, self.status, self.headers = url, status, dict(headers or {})
        self.headers.setdefault('Content-Length', str(len(data)))
        self._f = io.BytesIO(data)

    def read(self, n=-1):
        return self._f.read(n)

    def geturl(self):
        return self.url

    def close(self):
        pass


class FakeWeb:
    """urlopen stand-in: url -> bytes (or an exception to raise); honours Range unless ignore_range."""

    def __init__(self, files, ignore_range=False):
        self.files, self.ignore_range, self.calls = dict(files), ignore_range, []

    def __call__(self, req, timeout=None):
        url, rng = req.full_url, req.get_header('Range')
        self.calls.append((url, rng))
        v = self.files.get(url)
        if v is None:
            raise urllib.error.HTTPError(url, 404, 'Not Found', {}, None)
        if isinstance(v, BaseException):
            raise v
        if rng and not self.ignore_range:
            a, b = map(int, rng[len('bytes='):].split('-'))
            b = min(b, len(v) - 1)
            return FakeResponse(url, v[a:b + 1], 206, {'Content-Range': 'bytes %d-%d/%d' % (a, b, len(v))})
        return FakeResponse(url, v)


def ctx_for(web, **kw):
    return artifact.Context(opener=web, sleep=lambda s: None, **kw)


class ParseTest(unittest.TestCase):
    def test_repo_paths_filters_like_artifact_files(self):
        sha = 'a' * 40
        lines = [
            'MODULE Linux x86_64 ABC libxul.so', 'INFO CODE_ID 00',
            'FILE 0 %s:dom/base/Element.cpp:%s' % (GIT, sha),
            'FILE 1 %s:dom/base/Element.h:%s' % (GIT, sha),
            'FILE 2 %s:third_party/rust/serde/src/lib.rs:%s' % (GIT, sha),
            'FILE 3 %s:dom/base/Element.cpp:%s' % (GIT, sha),          # duplicate
            'FILE 4 %s:obj-x86_64/dist/include/foo.h:%s' % (GIT, sha),  # objdir
            'FILE 5 %s:<built-in>:%s' % (GIT, sha),                     # pseudo path
            'FILE 6 s3:gecko-generated-sources:abc/def.rs:',            # generated
            'FILE 7 git:github.com/rust-lang/rust:library/core/src/lib.rs:%s' % ('b' * 40),
            'FILE 8 /builds/worker/fetches/sysroot/usr/include/stdio.h',
            'FILE 9 /builds/worker/workspace/obj-build/x.cpp',
            'FUNC 0 1 0 never_reached',
        ]
        paths, revs, dropped = artifact.repo_paths(lines)
        self.assertEqual(paths, {'dom/base/Element.cpp', 'dom/base/Element.h', 'third_party/rust/serde/src/lib.rs'})
        self.assertEqual(dict(revs), {(GIT, sha): 4})
        self.assertEqual(dict(dropped), {'objdir': 1, 'pseudo': 1, 's3-generated': 1, 'other-repo': 1, 'not-repo': 2})

    def test_build_sha(self):
        sha = 'a' * 40
        one = artifact.collections.Counter({(GIT, sha): 5})
        self.assertEqual(artifact.build_sha(one), sha)
        self.assertEqual(artifact.build_sha(one, [HG_REV, sha]), sha)
        self.assertEqual(artifact.build_sha(one, expect=sha), sha)
        bad = [
            (artifact.collections.Counter(), {}),                                        # no records
            (artifact.collections.Counter({(GIT, sha): 5, (GIT, 'c' * 40): 1}), {}),     # mixed revisions
            (artifact.collections.Counter({('hg:hg.mozilla.org/mozilla-central', 'a' * 12): 2}), {}),  # hg era
            (one, {'candidates': [HG_REV]}),                                             # not the build's revision
            (one, {'expect': 'c' * 40}),
        ]
        for revs, kw in bad:
            with self.assertRaises(artifact.ArtifactUnavailable):
                artifact.build_sha(revs, **kw)

    def test_select_modules_picks_shipped_libxul_by_debug_id(self):
        elves = [('firefox/libxul.so', 9, XUL_BID.hex().upper()), ('firefox/libfoo.so', 9, FOO_BID.hex().upper()),
                 ('firefox/gtk2/libfoo.so', 9, FOO_BID.hex().upper()),   # same module twice: read once
                 ('firefox/libonnx.so', 9, None), ('firefox/glxtest', 9, ('77' * 20))]
        names = ['libxul.so/%s/libxul.so.sym' % did(GTEST_BID),          # gtest first, as in the real zip
                 'libxul.so/%s/libxul.so.sym' % did(XUL_BID),
                 'libfoo.so/%s/libfoo.so.sym' % did(FOO_BID),
                 'TestFoo/%s/TestFoo.sym' % did(TEST_BID), 'README.txt']
        chosen, skipped = artifact.select_modules(elves, names)
        self.assertEqual(chosen, [('libfoo.so', did(FOO_BID), names[2]), ('libxul.so', did(XUL_BID), names[1])])
        self.assertEqual(sorted(skipped), [('glxtest', 'not-in-zip'), ('libonnx.so', 'no-build-id')])
        with self.assertRaises(artifact.ArtifactUnavailable):   # only the gtest libxul.so is in the zip
            artifact.select_modules(elves, [names[0], names[2]])

    def test_debug_id_matches_zip_naming(self):
        # Breakpad's GUID byte order: the first three fields swapped, then age 0
        self.assertEqual(did(bytes.fromhex('00112233445566778899aabbccddeeff01020304')),
                         '33221100554477668899AABBCCDDEEFF0')

    def test_build_id_reads_only_as_far_as_the_note(self):
        elf = fake_elf(XUL_BID, note_off=300000, size=1 << 20)
        f = io.BytesIO(elf)
        self.assertEqual(artifact.build_id(f.read(64 << 10), f), XUL_BID)
        self.assertLess(f.tell(), 400000)
        f = io.BytesIO(fake_elf(None, size=4096))
        self.assertIsNone(artifact.build_id(f.read(64 << 10), f))

    def test_count_omni(self):
        jar = make_zip([('modules/a.sys.mjs', 'a\nb\nc\n'), ('chrome/b.js', 'x\n'), ('chrome/c.css', 'p\nq\n'),
                        ('chrome/d.xhtml', 'h\n'), ('chrome/e.json', '1\n2\n'), ('chrome/f.ftl', 'k\n'),
                        ('chrome/g.JS', 'upper\n'), ('chrome/dir/', '')], zipfile.ZIP_STORED)
        self.assertEqual(artifact.count_omni(jar), ({'js': 4, 'html': 3}, 4))
        deflated = make_zip([('modules/a.sys.mjs', 'a\nb\nc\n' * 50), ('chrome/c.css', 'p\nq\n')])
        self.assertEqual(artifact.count_omni(deflated), ({'js': 150, 'html': 2}, 2))

    def test_count_omni_reads_optimized_jars(self):
        jar = make_optimized_jar([('modules/a.sys.mjs', 'a\nb\nc\n'), ('chrome/c.css', 'p\nq\n'),
                                  ('chrome/e.json', '1\n'), ('chrome/', '')])
        with self.assertRaises(zipfile.BadZipFile):   # what the release omni.ja did to zipfile
            zipfile.ZipFile(io.BytesIO(jar))
        self.assertEqual(artifact.count_omni(jar), ({'js': 3, 'html': 2}, 2))

    def test_count_omni_malformed_is_unavailable(self):
        jar = bytearray(make_zip([('a.js', ''.join('line %d\n' % i for i in range(2000)))]))
        i = jar.index(b'PK\x03\x04')
        jar[i + 30 + 4:i + 30 + 12] = b'\xff' * 8   # corrupt the deflated data
        with self.assertRaisesRegex(artifact.ArtifactUnavailable, 'malformed'):
            artifact.count_omni(bytes(jar))
        with self.assertRaisesRegex(artifact.ArtifactUnavailable, 'end of central directory'):
            artifact.count_omni(b'not a zip' * 10)


class RemoteZipTest(unittest.TestCase):
    def test_header_stops_at_first_function(self):
        sha = 'a' * 40
        recs = ['%s:dir/f%04d.cpp:%s' % (GIT, i, sha) for i in range(3000)]
        body = sym('libxul.so', XUL_BID, recs, funcs=200000)
        name = 'libxul.so/%s/libxul.so.sym' % did(XUL_BID)
        z = make_zip([('other.txt', b'x' * 1000), (name, body)])
        web = FakeWeb({'https://x/s.zip': z})
        ctx = ctx_for(web)
        rf = artifact.RemoteFile(ctx, 'https://x/s.zip', 'symbols')
        ents = artifact.zip_directory(rf)
        self.assertEqual(set(ents), {'other.txt', name})
        lines = artifact.zip_sym_header(rf, ents[name], chunk=4096)
        self.assertEqual(len(lines), 3002)
        self.assertTrue(lines[0].startswith('MODULE') and lines[-1].endswith(recs[-1]))
        self.assertLess(ctx.bytes['symbols'], len(z) / 4)   # the FUNC records are never downloaded

    def test_range_ignored_is_unavailable(self):
        web = FakeWeb({'https://x/s.zip': make_zip([('a', 'b')])}, ignore_range=True)
        with self.assertRaises(artifact.ArtifactUnavailable):
            artifact.RemoteFile(ctx_for(web), 'https://x/s.zip', 'symbols')


class FailSoftTest(unittest.TestCase):
    def test_index_missing(self):
        web = FakeWeb({})
        with self.assertRaisesRegex(artifact.ArtifactUnavailable, 'index.*404'):
            artifact.head_artifact('/nonexistent', ctx=ctx_for(web))
        self.assertEqual(len(web.calls), 1)   # a 404 is not retried

    def test_transient_errors_are_retried_a_bounded_number_of_times(self):
        url = artifact.INDEX_URL.format(ns=artifact.INDEX)
        web = FakeWeb({url: urllib.error.URLError('connection reset')})
        with self.assertRaises(artifact.ArtifactUnavailable):
            artifact.head_artifact('/nonexistent', ctx=ctx_for(web))
        self.assertEqual(len(web.calls), artifact.TRIES)

    def test_deadline(self):
        ctx = ctx_for(FakeWeb({}), deadline=-1)
        with self.assertRaisesRegex(artifact.ArtifactUnavailable, 'deadline'):
            artifact.head_artifact('/nonexistent', ctx=ctx)

    def test_task_not_completed(self):
        web = FakeWeb({artifact.INDEX_URL.format(ns=artifact.INDEX): b'{"taskId":"T"}',
                       artifact.STATUS_URL.format(task='T'): b'{"status":{"state":"running"}}'})
        with self.assertRaisesRegex(artifact.ArtifactUnavailable, 'not completed'):
            artifact.head_artifact('/nonexistent', ctx=ctx_for(web))

    def test_bad_package_is_unavailable(self):
        web = FakeWeb({'https://x/p.tar.xz': b'not xz at all' * 100})
        with quiet(), self.assertRaisesRegex(artifact.ArtifactUnavailable, 'package'):
            artifact.artifact_from_build('https://x/s.zip', 'https://x/p.tar.xz', '/nonexistent', ctx=ctx_for(web))

    def test_malformed_index_answer_is_unavailable(self):
        web = FakeWeb({artifact.INDEX_URL.format(ns=artifact.INDEX): b'["a list, not an object"]'})
        with self.assertRaisesRegex(artifact.ArtifactUnavailable, 'malformed index answer'):
            artifact.head_artifact('/nonexistent', ctx=ctx_for(web))

    def test_cli_exit_status_and_try_head(self):
        web = FakeWeb({})
        with quiet():
            self.assertEqual(artifact.main(['head', '--repo', '/nonexistent'], ctx=ctx_for(web)),
                             artifact.EXIT_UNAVAILABLE)
            with mock.patch.object(artifact, 'Context', lambda *a, **k: ctx_for(web)):
                self.assertIsNone(artifact.try_head('/nonexistent'))
            with mock.patch.object(artifact, 'resolve_index', side_effect=RuntimeError('bug')):
                self.assertIsNone(artifact.try_head('/nonexistent', ctx=ctx_for(web)))

    def test_bugs_are_not_unavailable(self):
        """A KeyError outside the parsing of remote data is a bug: the CLI fails (exit 1, traceback) and try_head
        logs the traceback and returns None."""
        web = FakeWeb({})
        with mock.patch.object(artifact, 'resolve_index', side_effect=KeyError('bug')):
            with quiet(), self.assertRaises(KeyError):
                artifact.main(['head', '--repo', '/nonexistent'], ctx=ctx_for(web))
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertIsNone(artifact.try_head('/nonexistent', ctx=ctx_for(web)))
        self.assertIn('Traceback', err.getvalue())
        self.assertIn("KeyError: 'bug'", err.getvalue())


class BrokenHandler(http.server.BaseHTTPRequestHandler):
    """/chunked: a chunked answer that closes in the middle of a chunk (IncompleteRead while reading the body);
    /garbage: no HTTP status line at all (BadStatusLine while opening)."""
    hits = []

    def do_GET(self):
        BrokenHandler.hits.append(self.path)
        if self.path.startswith('/chunked'):
            self.wfile.write(b'HTTP/1.1 200 OK\r\nContent-Type: application/x-xz\r\nTransfer-Encoding: chunked\r\n\r\n'
                             b'10000\r\n' + b'\xfd7zXZ\x00' + b'x' * 100)
        else:
            self.wfile.write(b'garbage\r\n\r\n')
        self.wfile.flush()
        self.close_connection = True

    def log_message(self, *a):
        pass


class HttpFailureTest(unittest.TestCase):
    """Real urllib against a local server that breaks the HTTP protocol: such failures exit 3, never 1."""

    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), BrokenHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:%d' % cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def ctx(self):
        no_proxy = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # ignore any http_proxy
        return artifact.Context(opener=no_proxy.open, sleep=lambda s: None, timeout=10)

    def build(self, package):
        BrokenHandler.hits.clear()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = artifact.main(['build', '--symbols', self.base + '/garbage/s.zip', '--package', package,
                                  '--repo', '/nonexistent'], ctx=self.ctx())
        return code, err.getvalue()

    def test_connection_closed_mid_chunk_exits_3(self):
        code, err = self.build(self.base + '/chunked/p.tar.xz')
        self.assertEqual(code, artifact.EXIT_UNAVAILABLE)
        self.assertIn('IncompleteRead', err)

    def test_bad_status_line_is_retried_then_exits_3(self):
        code, err = self.build(self.base + '/garbage/p.tar.xz')
        self.assertEqual(code, artifact.EXIT_UNAVAILABLE)
        self.assertEqual(BrokenHandler.hits, ['/garbage/p.tar.xz'] * artifact.TRIES)
        self.assertIn('artifact unavailable', err)


def run(cwd, *args):
    return subprocess.run(args, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode()


def write(root, path, text):
    full = os.path.join(root, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w') as f:
        f.write(text)


def body(n):
    return ''.join('line %d\n' % i for i in range(n))


# repository files: path -> lines; which of them the FILE records name is in RECORDED
TREE = {'dom/a.cpp': 4, 'dom/a.h': 3, 'dom/b.c': 2, 'third_party/rust/x/src/lib.rs': 7, 'gfx/y.cc': 1,
        'mobile/android/m.rs': 50, 'dom/tests/t.cpp': 5, 'media/z.inc': 9, 'tools/p.py': 2, 'dom/unused.cpp': 100,
        'browser/app.js': 11, 'media/v.asm': 6}
RECORDED = ['dom/a.cpp', 'dom/a.h', 'dom/b.c', 'third_party/rust/x/src/lib.rs', 'gfx/y.cc', 'mobile/android/m.rs',
            'dom/tests/t.cpp', 'media/z.inc', 'tools/p.py', 'browser/app.js', 'media/v.asm', 'dom/gone.cpp']


class BuildTest(unittest.TestCase):
    """A whole build offline: a stub Taskcluster, a synthetic package and symbols zip, and local git repositories."""

    @classmethod
    def setUpClass(cls):
        cls._env = mock.patch.dict(os.environ, {
            'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1',
            'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.com',
            'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@example.com'})
        cls._env.start()
        cls.tmp = tempfile.mkdtemp(prefix='test_artifact-')
        up = cls.up = os.path.join(cls.tmp, 'upstream')
        os.makedirs(up)
        run(up, 'git', 'init', '-q')
        run(up, 'git', 'config', 'uploadpack.allowFilter', 'true')
        run(up, 'git', 'config', 'uploadpack.allowAnySHA1InWant', 'true')
        write(up, 'dom/a.cpp', body(1))
        run(up, 'git', 'add', '-A')
        run(up, 'git', 'commit', '-q', '-m', 'old')
        cls.old = run(up, 'git', 'rev-parse', 'HEAD').strip()
        # a depth-1 checkout of the old commit: the build's commit is not in it
        run(cls.tmp, 'git', 'clone', '-q', '--depth', '1', 'file://' + up, 'checkout')
        cls.checkout = os.path.join(cls.tmp, 'checkout')
        for p, n in TREE.items():
            write(up, p, body(n))
        run(up, 'git', 'add', '-A')
        run(up, 'git', 'commit', '-q', '-m', 'build')
        cls.sha = run(up, 'git', 'rev-parse', 'HEAD').strip()

        sha = cls.sha
        xul = ['%s:%s:%s' % (GIT, p, sha) for p in RECORDED[:6]] + [
            's3:gecko-generated-sources:x/y.cpp:', '/builds/worker/fetches/rustc/lib/rustlib/src/core.rs',
            '%s:obj-x86_64-pc-linux-gnu/dist/include/q.h:%s' % (GIT, sha)]
        foo = ['%s:%s:%s' % (GIT, p, sha) for p in RECORDED[5:]]
        gtest = ['%s:%s:%s' % (GIT, 'dom/unused.cpp', sha)]
        cls.zip = make_zip([
            ('libxul.so/%s/libxul.so.sym' % did(GTEST_BID), sym('libxul.so', GTEST_BID, gtest)),
            ('libxul.so/%s/libxul.so.sym' % did(XUL_BID), sym('libxul.so', XUL_BID, xul)),
            ('libfoo.so/%s/libfoo.so.sym' % did(FOO_BID), sym('libfoo.so', FOO_BID, foo)),
            ('TestFoo/%s/TestFoo.sym' % did(TEST_BID), sym('TestFoo', TEST_BID, gtest)),
        ])
        cls.package = make_tar_xz([
            ('firefox/libxul.so', fake_elf(XUL_BID, note_off=100000, size=200000)),
            ('firefox/libfoo.so', fake_elf(FOO_BID, size=5000)),
            ('firefox/libonnx.so', fake_elf(None, size=5000)),
            ('firefox/omni.ja', make_zip([('a.js', 'a\nb\n'), ('b.css', 'c\n'), ('c.json', '{}\n')])),
            ('firefox/browser/omni.ja', make_zip([('d.mjs', 'x\ny\nz\n'), ('e.xhtml', 'h\n')])),
            ('firefox/application.ini', b'[App]\nName=Firefox\n' * 10),
        ])
        cls.expected = {'rust': 7, 'c': 2, 'cpp': 4 + 1 + 5, 'h': 3, 'js': 2 + 3, 'html': 1 + 1, 'py': 2,
                        'java': 0, 'asm': 0}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        cls._env.stop()

    def web(self, task='T'):
        return FakeWeb({
            artifact.INDEX_URL.format(ns=artifact.INDEX): json.dumps({'taskId': task}).encode(),
            artifact.STATUS_URL.format(task=task): b'{"status":{"state":"completed"}}',
            artifact.TASK_URL.format(task=task): json.dumps({'routes': [
                'index.gecko.v2.mozilla-central.revision.%s.firefox.linux64-opt' % HG_REV,
                'index.gecko.v2.mozilla-central.revision.%s.firefox.linux64-opt' % self.sha]}).encode(),
            artifact.ARTIFACT_URL.format(task=task, name=artifact.SYMBOLS): self.zip,
            artifact.ARTIFACT_URL.format(task=task, name=artifact.PACKAGE): self.package,
        })

    def test_head_fetches_the_build_commit_into_a_throwaway_repository(self):
        ctx = ctx_for(self.web())
        before = run(self.checkout, 'git', 'count-objects', '-v')
        with quiet():
            rec = artifact.head_artifact(self.checkout, remote='file://' + self.up, ctx=ctx)
        self.assertEqual({k: rec[k] for k in history.KEYS}, self.expected)
        self.assertEqual(rec['sha'], self.sha)
        self.assertEqual(rec['source'], {'kind': 'symbols', 'index': artifact.INDEX, 'task': 'T',
                                         'libxul_debug_id': did(XUL_BID), 'modules': 2, 'paths': len(RECORDED)})
        self.assertEqual(list(rec), history.KEYS + ['sha', 'source'])
        st = ctx.stats
        self.assertTrue(st['count']['fetched_commit'])
        self.assertEqual(st['count']['missing_in_tree'], 1)        # dom/gone.cpp
        self.assertEqual(st['count']['excluded'], 1)               # mobile/
        self.assertEqual(st['file_pass_dropped'], {'js': 11, 'html': 0, 'asm': 6})
        self.assertEqual(sorted(st['modules_skipped']), [('libonnx.so', 'no-build-id')])
        # the checkout is only read
        self.assertEqual(run(self.checkout, 'git', 'count-objects', '-v'), before)
        self.assertIsNone(artifact.history.promisor_remote(self.checkout))

    def test_build_with_the_commit_already_present_needs_no_fetch(self):
        ctx = ctx_for(self.web())
        with quiet():
            rec = artifact.artifact_from_build(artifact.ARTIFACT_URL.format(task='T', name=artifact.SYMBOLS),
                                               artifact.ARTIFACT_URL.format(task='T', name=artifact.PACKAGE),
                                               self.up, sha=self.sha, remote='file:///nonexistent', ctx=ctx)
        self.assertEqual({k: rec[k] for k in history.KEYS}, self.expected)
        self.assertNotIn('fetched_commit', ctx.stats['count'])
        self.assertEqual(ctx.stats['count']['blobs_fetched'], 0)

    def test_source_from_the_caller_is_merged(self):
        ctx = ctx_for(self.web())
        src = {'kind': 'candidates', 'symbols': 'S', 'package': 'P', 'libxul_debug_id': 'stale', 'modules': 99}
        with quiet():
            rec = artifact.artifact_from_build(artifact.ARTIFACT_URL.format(task='T', name=artifact.SYMBOLS),
                                               artifact.ARTIFACT_URL.format(task='T', name=artifact.PACKAGE),
                                               self.up, sha=self.sha, source=src, ctx=ctx)
        self.assertEqual(rec['source'], {'kind': 'candidates', 'symbols': 'S', 'package': 'P',
                                         'libxul_debug_id': did(XUL_BID), 'modules': 2, 'paths': len(RECORDED)})
        self.assertEqual(src['modules'], 99)   # the caller's dict is not modified

    def test_unreachable_remote_is_unavailable(self):
        with quiet(), self.assertRaisesRegex(artifact.ArtifactUnavailable, '^count: '):
            artifact.head_artifact(self.checkout, remote='file:///nonexistent', ctx=ctx_for(self.web()))

    def test_cli_writes_the_record(self):
        out = os.path.join(self.tmp, 'rec.json')
        stats = os.path.join(self.tmp, 'stats.json')
        with quiet():
            code = artifact.main(['head', '--repo', self.up, '--out', out, '--stats', stats],
                                 ctx=ctx_for(self.web()))
        self.assertEqual(code, 0)
        with open(out) as f:
            rec = json.load(f)
        self.assertEqual(rec['rust'], 7)
        with open(stats) as f:
            self.assertIn('bytes', json.load(f))


if __name__ == '__main__':
    unittest.main()
