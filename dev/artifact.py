#!/usr/bin/env python3
"""The browser-artifact line counts (the `artifact` block of data/history.json) for a Linux x86-64 Firefox build.

What ships is learnt from Mozilla's own build outputs, never from a local build (docs/implementation-plan.md, Task 5;
docs/reference/symbols/README.md):

  1. package  stream the build's target.tar.xz once: the GNU build id of every ELF file (turned into the Breakpad debug
              id) and the JavaScript, CSS and HTML lines of the files inside every omni.ja (omni.ja, browser/omni.ja)
  2. symbols  range-read the central directory of target.crashreporter-symbols.zip and only the MODULE/INFO/FILE header
              of the .sym of each shipped module, chosen by (module name, debug id). The zip also holds test binaries
              and a second (gtest) libxul.so; the debug id from the package picks the shipped one
  3. paths    keep the repository paths of the FILE records (git:github.com/mozilla-firefox/firefox:<path>:<sha>),
              dropping generated, toolchain, objdir and other-repository records (the rules of dev/artifact-files).
              Every record must carry the same sha; that sha is the commit the artifact is counted at
  4. count    count the lines of those paths at that sha with the rules of dev/history.py (same extensions, same
              newline count, paths under mobile/ skipped). Only the blobs of those paths are read; anything the
              --repo checkout lacks is fetched into a throwaway repository that borrows the checkout's objects
              (git alternates), so the checkout itself is never modified

Languages: rust, c, cpp, h, py, java from the file pass; js and html (CSS included) from omni.ja only, so nothing is
counted twice (the file pass reports any js/html path it sees and drops it; none are expected); asm is always 0
(nasm objects carry no line information). Headers stay in `h`, split at display time by `header_split`.

Subcommands:

  head --repo R [--index NS] [--out FILE]
        the artifact of the newest finished mozilla-central linux64-opt build
        (gecko.v2.mozilla-central.latest.firefox.linux64-opt). R is a checkout of mozilla-firefox/firefox, any depth
  build --symbols URL --package URL --repo R [--sha SHA]
        the same for any build given by its two artifact URLs (the entry point for release builds later)

Output: one JSON object, {"rust",...,"asm","sha","source"}, where source is
{"kind":"symbols","index","task","libxul_debug_id","modules","paths"} (`kind` names where the file list came from;
consumers should read source.kind and sum only the nine language keys). Statistics go to stderr, or to --stats FILE.

Fail soft: every network, format or git failure raises ArtifactUnavailable (exit status 3 on the command line), so a
weekly job can store `artifact: null` and carry on. Every request has a timeout and bounded retries, and the whole run
has a deadline (--deadline, default 20 minutes). Exit status 1 means a bug, 2 a usage error.

Python 3.9+, standard library only. Tests: python3 -m unittest discover -s dev
"""
import argparse
import bz2
import collections
import contextlib
import importlib.util
import io
import json
import lzma
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
import zlib
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import history  # noqa: E402


def _load_artifact_files():
    """dev/artifact-files (an executable without .py) as a module: its FILE-record classifier and ELF helpers."""
    path = os.path.join(HERE, 'artifact-files')
    loader = SourceFileLoader('artifact_files', path)
    spec = importlib.util.spec_from_loader('artifact_files', loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


artifact_files = _load_artifact_files()

TC = 'https://firefox-ci-tc.services.mozilla.com'
INDEX = 'gecko.v2.mozilla-central.latest.firefox.linux64-opt'
INDEX_URL = TC + '/api/index/v1/task/{ns}'
TASK_URL = TC + '/api/queue/v1/task/{task}'
STATUS_URL = TC + '/api/queue/v1/task/{task}/status'
ARTIFACT_URL = TC + '/api/queue/v1/task/{task}/artifacts/{name}'
SYMBOLS = 'public/build/target.crashreporter-symbols.zip'
PACKAGE = 'public/build/target.tar.xz'
GIT_REMOTE = 'https://github.com/mozilla-firefox/firefox.git'
FIREFOX_GIT = 'git:github.com/mozilla-firefox/firefox'
UA = 'firefox-lang-stats/artifact (+https://github.com/4e6/firefox-lang-stats)'

EXIT_UNAVAILABLE = 3
DEADLINE = 20 * 60          # seconds for a whole run
TIMEOUT = 60                # seconds per socket operation
TRIES = 3                   # attempts per request (transient errors only)
CHUNK = 2 << 20             # range-request size for .sym headers
MAX_PACKAGE = 1 << 30       # refuse a package larger than this (compressed)
MAX_ELF_PREFIX = 64 << 20   # never read more than this of an ELF file to find its build id
HEADER = (b'MODULE', b'INFO', b'FILE')
HEX40 = re.compile(r'\b[0-9a-f]{40}\b')
FILE_PASS_KEYS = ('rust', 'c', 'cpp', 'h', 'py', 'java')   # languages taken from the FILE records
OMNI_KEYS = ('js', 'html')                                   # languages taken from omni.ja


class ArtifactUnavailable(RuntimeError):
    """The artifact cannot be computed this time (missing build, network or format failure). Not a bug."""


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------------------------------------------
# network: one context per run, with a deadline, byte counters and a replaceable opener (tests stub it)


class Context:
    def __init__(self, deadline=DEADLINE, opener=None, timeout=TIMEOUT, tries=TRIES, sleep=time.sleep):
        self.t0 = time.time()
        self.deadline = self.t0 + deadline
        self.opener = opener or urllib.request.urlopen
        self.timeout = timeout
        self.tries = tries
        self.sleep = sleep
        self.bytes = collections.Counter()
        self.requests = collections.Counter()
        self.stats = {}

    def remaining(self):
        left = self.deadline - time.time()
        if left <= 0:
            raise ArtifactUnavailable('deadline of %.0fs exceeded' % (self.deadline - self.t0))
        return left

    def open(self, url, headers=None, kind='other'):
        """Response for a GET of `url`. Retries transient errors; a 4xx answer raises at once."""
        h = {'User-Agent': UA}
        h.update(headers or {})
        for i in range(self.tries):
            self.remaining()
            self.requests[kind] += 1
            try:
                return self.opener(urllib.request.Request(url, headers=h), timeout=min(self.timeout, self.remaining()))
            except urllib.error.HTTPError as e:
                if 400 <= e.code < 500 or i == self.tries - 1:
                    raise ArtifactUnavailable('%s: HTTP %d' % (url, e.code)) from None
            except (urllib.error.URLError, socket.timeout, OSError) as e:
                if i == self.tries - 1:
                    raise ArtifactUnavailable('%s: %s' % (url, e)) from None
            self.sleep(2 ** (i + 1))
        raise AssertionError('unreachable')

    def read_all(self, url, kind='other', limit=16 << 20):
        r = self.open(url, kind=kind)
        try:
            data = r.read(limit + 1)
        finally:
            r.close()
        if len(data) > limit:
            raise ArtifactUnavailable('%s: answer larger than %d bytes' % (url, limit))
        self.bytes[kind] += len(data)
        return data

    def json(self, url, kind='index'):
        try:
            return json.loads(self.read_all(url, kind).decode('utf-8'))
        except ValueError as e:
            raise ArtifactUnavailable('%s: not JSON (%s)' % (url, e)) from None


class RemoteFile:
    """A file read with HTTP range requests. The redirect (Taskcluster answers 303) is followed once."""

    def __init__(self, ctx, url, kind):
        self.ctx, self.kind = ctx, kind
        r = ctx.open(url, {'Range': 'bytes=0-0'}, kind)
        try:
            cr = r.headers.get('Content-Range', '')
            m = re.fullmatch(r'bytes 0-0/(\d+)', cr.strip())
            if r.status != 206 or not m:
                raise ArtifactUnavailable('%s: no range support (status %s, Content-Range %r)' % (url, r.status, cr))
            self.url = r.geturl()
            self.size = int(m.group(1))
            self.ctx.bytes[kind] += len(r.read(1))
        finally:
            r.close()

    def get(self, start, end):
        """Bytes start..end (inclusive). A server that ignores Range is an error, never a full download."""
        if start < 0 or end >= self.size or end < start:
            raise ArtifactUnavailable('%s: bad range %d-%d of %d' % (self.url, start, end, self.size))
        r = self.ctx.open(self.url, {'Range': 'bytes=%d-%d' % (start, end)}, self.kind)
        try:
            if r.status != 206:
                raise ArtifactUnavailable('%s: range request answered with status %s' % (self.url, r.status))
            want = end - start + 1
            data = r.read(want + 1)
        finally:
            r.close()
        self.ctx.bytes[self.kind] += len(data)
        if len(data) != want:
            raise ArtifactUnavailable('%s: asked for %d bytes at %d, got %d' % (self.url, want, start, len(data)))
        return data


class CountingReader:
    """A response body read through `read(n)`, counting bytes and checking the run's deadline."""

    def __init__(self, ctx, resp, kind):
        self.ctx, self.resp, self.kind = ctx, resp, kind

    def read(self, n=-1):
        self.ctx.remaining()
        data = self.resp.read(n)
        self.ctx.bytes[self.kind] += len(data)
        return data

    def readable(self):
        return True

    def close(self):
        self.resp.close()


# ---------------------------------------------------------------------------------------------------------------
# Taskcluster


def resolve_index(ctx, ns=INDEX):
    """{"task","revisions","symbols","package"} for a Taskcluster index namespace of a finished build.

    `revisions` are the 40-hex revisions in the task's routes, in order (an hg one and a git one for
    mozilla-central); the git sha is confirmed later from the FILE records."""
    task = ctx.json(INDEX_URL.format(ns=ns)).get('taskId')
    if not task:
        raise ArtifactUnavailable('index %s has no taskId' % ns)
    status = ctx.json(STATUS_URL.format(task=task)).get('status', {})
    if status.get('state') != 'completed':
        raise ArtifactUnavailable('task %s is %s, not completed' % (task, status.get('state')))
    routes = ctx.json(TASK_URL.format(task=task)).get('routes', [])
    revisions = []
    for r in routes:
        for h in HEX40.findall(r):
            if h not in revisions:
                revisions.append(h)
    if not revisions:
        raise ArtifactUnavailable('task %s has no revision in its routes' % task)
    return {'task': task, 'revisions': revisions,
            'symbols': ARTIFACT_URL.format(task=task, name=SYMBOLS),
            'package': ARTIFACT_URL.format(task=task, name=PACKAGE)}


# ---------------------------------------------------------------------------------------------------------------
# package: ELF build ids and omni.ja lines, in one pass over the stream


def elf_needed(head):
    """How many leading bytes of an ELF file hold its program headers and PT_NOTE segments (64-bit LE only)."""
    if len(head) < 64 or head[:4] != b'\x7fELF' or head[4] != 2 or head[5] != 1:
        return len(head)
    e_phoff, = struct.unpack('<Q', head[32:40])
    e_phentsize, e_phnum = struct.unpack('<HH', head[54:58])
    need = e_phoff + e_phentsize * e_phnum
    if need > len(head):
        return need
    for i in range(e_phnum):
        p = head[e_phoff + i * e_phentsize:e_phoff + (i + 1) * e_phentsize]
        typ, = struct.unpack('<I', p[:4])
        if typ == 4:
            off, = struct.unpack('<Q', p[8:16])
            sz, = struct.unpack('<Q', p[32:40])
            need = max(need, off + sz)
    return need


def build_id(head, f):
    """GNU build id (bytes) of an ELF file, or None. `head` is its first bytes; the rest is read from stream `f`
    only as far as the program headers and PT_NOTE segments reach (a few KB; libxul.so itself is 240 MB)."""
    while True:
        need = elf_needed(head)
        if need <= len(head):
            break
        if need > MAX_ELF_PREFIX:
            raise ArtifactUnavailable('ELF note at %d bytes, past the %d byte limit' % (need, MAX_ELF_PREFIX))
        more = f.read(need - len(head))
        if not more:
            break
        head += more
    return artifact_files.elf_build_id(head)


def lang_of(path):
    m = history.EXT_RE.search(path)
    return history.EXT2LANG.get(m.group(1)) if m else None


def count_omni(data):
    """({"js": lines, "html": lines}, files counted) for the files inside one omni.ja (a zip), by history.py's rules."""
    counts = dict.fromkeys(OMNI_KEYS, 0)
    nfiles = 0
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            lang = lang_of(info.filename)
            if lang in counts:
                counts[lang] += z.read(info).count(b'\n')
                nfiles += 1
    return counts, nfiles


def scan_package(ctx, url):
    """Stream a .tar.xz (or .tar.bz2) package once: ([(tar path, size, build id hex or None)], {omni path: counts})."""
    r = ctx.open(url, kind='package')
    try:
        size = r.headers.get('Content-Length')
        if size is not None and int(size) > MAX_PACKAGE:
            raise ArtifactUnavailable('%s: %s bytes, more than the %d byte limit' % (url, size, MAX_PACKAGE))
        ctx.stats['package_size'] = int(size) if size is not None else None
        log('package', r.geturl(), size, 'bytes')
        body = CountingReader(ctx, r, 'package')
        dec = bz2.BZ2File(body) if url.endswith('.bz2') else lzma.LZMAFile(body)
        elves, omni = [], {}
        with tarfile.open(fileobj=dec, mode='r|') as tf:
            for m in tf:
                if not m.isfile() or m.size < 64:
                    continue
                f = tf.extractfile(m)
                if os.path.basename(m.name) == 'omni.ja':
                    counts, nfiles = count_omni(f.read())
                    omni[m.name] = dict(counts, files=nfiles)
                    continue
                head = f.read(64 << 10)
                if head[:4] != b'\x7fELF':
                    continue
                bid = build_id(head, f)
                elves.append((m.name, m.size, bid.hex().upper() if bid else None))
    finally:
        r.close()
    return elves, omni


# ---------------------------------------------------------------------------------------------------------------
# symbols zip: central directory and the header of one .sym


def zip_directory(rf):
    """{entry name: (method, compressed size, uncompressed size, local header offset)} of a remote zip."""
    tail_start = max(0, rf.size - 65558)
    tail = rf.get(tail_start, rf.size - 1)
    i = tail.rfind(b'PK\x05\x06')
    if i < 0:
        raise ArtifactUnavailable('%s: no end of central directory' % rf.url)
    cnt, cdsize, cdoff = struct.unpack('<HII', tail[i + 10:i + 20])
    j = tail.rfind(b'PK\x06\x06')
    if j >= 0:
        cnt, cdsize, cdoff = struct.unpack('<QQQ', tail[j + 32:j + 56])
    cd = rf.get(cdoff, cdoff + cdsize - 1) if cdsize else b''
    p, ents = 0, {}
    while p + 46 <= len(cd) and cd[p:p + 4] == b'PK\x01\x02':
        meth, = struct.unpack('<H', cd[p + 10:p + 12])
        csz, usz = struct.unpack('<II', cd[p + 20:p + 28])
        nl, el, cl = struct.unpack('<HHH', cd[p + 28:p + 34])
        off, = struct.unpack('<I', cd[p + 42:p + 46])
        name = cd[p + 46:p + 46 + nl].decode('utf-8', 'replace')
        ex = cd[p + 46 + nl:p + 46 + nl + el]
        q = 0
        while q + 4 <= len(ex):  # zip64 extra field: 64-bit sizes and offset, present only for the saturated ones
            hid, hl = struct.unpack('<HH', ex[q:q + 4])
            if hid == 1:
                vals, k = ex[q + 4:q + 4 + hl], 0
                if usz == 0xffffffff:
                    usz, = struct.unpack('<Q', vals[k:k + 8]); k += 8
                if csz == 0xffffffff:
                    csz, = struct.unpack('<Q', vals[k:k + 8]); k += 8
                if off == 0xffffffff:
                    off, = struct.unpack('<Q', vals[k:k + 8]); k += 8
            q += 4 + hl
        ents[name] = (meth, csz, usz, off)
        p += 46 + nl + el + cl
    if len(ents) != cnt:
        raise ArtifactUnavailable('%s: central directory lists %d entries, read %d' % (rf.url, cnt, len(ents)))
    return ents


def zip_sym_header(rf, ent, chunk=CHUNK):
    """MODULE, INFO and FILE lines at the head of one .sym entry; reads only until the FILE records end."""
    meth, csz, usz, off = ent
    if meth not in (0, 8):
        raise ArtifactUnavailable('%s: unsupported compression method %d' % (rf.url, meth))
    lh = rf.get(off, off + 29)
    if lh[:4] != b'PK\x03\x04':
        raise ArtifactUnavailable('%s: no local header at %d' % (rf.url, off))
    nl, el = struct.unpack('<HH', lh[26:30])
    pos = off + 30 + nl + el
    end = pos + csz
    d = zlib.decompressobj(-15) if meth == 8 else None
    buf, lines = b'', []
    while pos < end:
        c = rf.get(pos, min(end, pos + chunk) - 1)
        pos += len(c)
        buf += d.decompress(c) if d else c
        *full, buf = buf.split(b'\n')
        for line in full:
            if not line.startswith(HEADER):
                return lines
            lines.append(line.rstrip(b'\r').decode('utf-8', 'replace'))
    if buf.startswith(HEADER):
        lines.append(buf.decode('utf-8', 'replace'))
    return lines


def sym_index(names):
    """{(module, debug id): entry name} for the `<module>/<DEBUG ID>/<module>.sym` entries of a symbols zip."""
    out = {}
    for n in names:
        parts = n.split('/')
        if len(parts) == 3 and parts[2] == parts[0] + '.sym':
            out[(parts[0], parts[1].upper())] = n
    return out


def select_modules(elves, names):
    """Shipped modules to read: ([(module, debug id, entry name)], [(module, reason)] skipped).

    A module is matched by name and debug id, so of the two libxul.so in the zip (shipped and gtest) only the one
    built into the package is chosen; test binaries are never chosen. No libxul.so match is an error."""
    idx = sym_index(names)
    chosen, skipped, seen = [], [], set()
    for path, size, bid in sorted(elves):
        mod = os.path.basename(path)
        if bid is None:
            skipped.append((mod, 'no-build-id'))
            continue
        did = artifact_files.debug_id(bytes.fromhex(bid))
        if (mod, did) in seen:
            continue
        seen.add((mod, did))
        ent = idx.get((mod, did))
        if ent is None:
            skipped.append((mod, 'not-in-zip'))
        else:
            chosen.append((mod, did, ent))
    xul = [c for c in chosen if c[0] == 'libxul.so']
    if len(xul) != 1:
        have = sorted(d for (m, d) in idx if m == 'libxul.so')
        want = sorted({artifact_files.debug_id(bytes.fromhex(b)) for p, s, b in elves
                       if b and os.path.basename(p) == 'libxul.so'})
        raise ArtifactUnavailable('libxul.so of the package (%s) is not in the symbols zip (%s)' % (want, have))
    return chosen, skipped


# ---------------------------------------------------------------------------------------------------------------
# FILE records -> repository paths and the build's git sha


def repo_paths(lines):
    """(set of repository paths, Counter of (repo, rev), Counter of drop reasons) from .sym header lines."""
    paths, revs, dropped = set(), collections.Counter(), collections.Counter()
    for line in lines:
        if not line.startswith('FILE '):
            continue
        parts = line.split(' ', 2)
        if len(parts) < 3:
            dropped['malformed'] += 1
            continue
        got, why = artifact_files.classify(parts[2])
        if got is None:
            dropped[why] += 1
            continue
        repo, path, rev = got
        revs[(repo, rev)] += 1
        paths.add(path)
    return paths, revs, dropped


def build_sha(revs, candidates=None, expect=None):
    """The one git sha all repository FILE records were built from. Mixed revisions, hg-era records or a sha that is
    not one of `candidates` (the task's route revisions) or not `expect` raise ArtifactUnavailable."""
    if not revs:
        raise ArtifactUnavailable('no repository FILE records')
    if len(revs) != 1:
        raise ArtifactUnavailable('FILE records name %d revisions: %s' % (
            len(revs), ', '.join('%s:%s (%d)' % (r, s[:12], n) for (r, s), n in revs.most_common(5))))
    (repo, sha), = revs
    if repo != FIREFOX_GIT or len(sha) != 40:
        raise ArtifactUnavailable('FILE records are not %s:<path>:<40-hex sha> but %s:...:%s' % (FIREFOX_GIT, repo, sha))
    if candidates is not None and sha not in candidates:
        raise ArtifactUnavailable('FILE records name %s, not one of the build revisions %s' % (sha, list(candidates)))
    if expect is not None and sha != expect:
        raise ArtifactUnavailable('FILE records name %s, expected %s' % (sha, expect))
    return sha


# ---------------------------------------------------------------------------------------------------------------
# counting: a throwaway repository that borrows the checkout's objects and fetches only what it lacks


def run_git(ctx, repo, *args, input=None):
    env = dict(history.no_lazy_fetch(), GIT_TERMINAL_PROMPT='0')
    try:
        return subprocess.run(['git', '-C', repo, *args], input=input, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, env=env, check=True, timeout=ctx.remaining()).stdout
    except subprocess.TimeoutExpired:
        raise ArtifactUnavailable('git %s timed out' % args[0]) from None
    except subprocess.CalledProcessError as e:
        raise ArtifactUnavailable('git %s failed: %s' % (' '.join(args[:3]), e.stderr.decode('utf-8', 'replace')
                                                       .strip()[-300:])) from None


def objects_dir(ctx, repo):
    out = run_git(ctx, repo, 'rev-parse', '--git-common-dir').decode().strip()
    path = os.path.join(os.path.abspath(repo), out, 'objects')
    if not os.path.isdir(path):
        raise ArtifactUnavailable('%s has no object directory at %s' % (repo, path))
    return os.path.normpath(path)


@contextlib.contextmanager
def scratch_repo(ctx, remote=GIT_REMOTE):
    """A temporary bare repository that fetches from `remote` as a blobless partial clone. Removed on exit."""
    tmp = tempfile.mkdtemp(prefix='artifact-git-')
    try:
        run_git(ctx, tmp, 'init', '-q', '--bare')
        run_git(ctx, tmp, 'remote', 'add', 'origin', remote)
        run_git(ctx, tmp, 'config', 'remote.origin.promisor', 'true')
        run_git(ctx, tmp, 'config', 'remote.origin.partialclonefilter', 'blob:none')
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def borrow_objects(ctx, tmp, repo):
    """Let `tmp` read every object of `repo` (git alternates); `repo` itself is only read."""
    with open(os.path.join(tmp, 'objects', 'info', 'alternates'), 'w') as f:
        f.write(objects_dir(ctx, repo) + '\n')


def du(path):
    total = 0
    for dp, dn, fn in os.walk(path):
        for f in fn:
            try:
                total += os.lstat(os.path.join(dp, f)).st_size
            except OSError:
                pass
    return total


def has_commit(ctx, repo, sha):
    try:
        run_git(ctx, repo, 'cat-file', '-e', sha + '^{commit}')
        return True
    except ArtifactUnavailable:
        return False


def fetch_blobs(ctx, repo, oids, streams=4):
    """Fetch blobs by id into a partial clone, in parallel batched fetches, within the run's deadline."""
    oids = sorted(oids)
    streams = max(1, min(streams, len(oids) // 1000 + 1))
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0')
    procs = []
    try:
        for i in range(streams):
            f = tempfile.TemporaryFile()
            f.write(('\n'.join(oids[i::streams]) + '\n').encode())
            f.seek(0)
            procs.append((f, subprocess.Popen(
                ['git', '-C', repo, '-c', 'fetch.negotiationAlgorithm=noop', 'fetch', '-q', '--no-tags',
                 '--no-write-fetch-head', '--filter=blob:none', '--stdin', 'origin'], stdin=f, env=env)))
        failed = 0
        for f, p in procs:
            failed += p.wait(timeout=ctx.remaining()) != 0
    except subprocess.TimeoutExpired:
        raise ArtifactUnavailable('blob fetch timed out') from None
    finally:
        for f, p in procs:
            if p.poll() is None:
                p.kill()
                p.wait()
            f.close()
    if failed:
        raise ArtifactUnavailable('%d of %d blob fetches failed' % (failed, streams))


def count_paths(ctx, repo, sha, paths, excludes=history.DEFAULT_EXCLUDES, remote=GIT_REMOTE):
    """({language: lines} for rust c cpp h js html py java asm, statistics) of `paths` at commit `sha`.

    Same rules as history.count_release: language by extension, newline count, paths under `excludes` skipped.
    Paths with other extensions are not counted; paths missing from the tree are reported."""
    excludes = tuple(excludes)
    st = {'excluded': sum(1 for p in paths if excludes and p.startswith(excludes))}
    # The commit and its trees come from the checkout if it has them, otherwise from `remote` (depth 1, no blobs,
    # about 17 MiB). The checkout's objects are borrowed only after that fetch: a promisor fetch that finds local
    # objects referenced by the new trees would copy all of them (about 1 GB) into a new pack.
    with scratch_repo(ctx, remote) as tmp:
        if not has_commit(ctx, repo, sha):
            log('fetching', sha[:12], 'from', remote, '(depth 1, no blobs)')
            run_git(ctx, tmp, 'fetch', '-q', '--no-tags', '--no-write-fetch-head', '--depth', '1',
                    '--filter=blob:none', 'origin', sha)
            st['fetched_commit'] = True
        borrow_objects(ctx, tmp, repo)
        entries = [(oid, p, lang) for oid, p, lang in history.tree(tmp, sha, excludes) if p in paths]
        seen = {p for _, p, _ in entries}
        counted = {p for p in paths if lang_of(p) and not (excludes and p.startswith(excludes))}
        missing_paths = sorted(counted - seen)
        st['missing_in_tree'] = len(missing_paths)
        if missing_paths:
            log('warning: %d paths are not in the tree of %s, e.g. %s' % (len(missing_paths), sha[:12],
                                                                         missing_paths[:3]))
        oids = sorted({oid for oid, _, _ in entries})
        missing = history.missing_blobs(tmp, oids)
        st['blobs'] = len(oids)
        st['blobs_fetched'] = len(missing)
        if missing:
            t = time.time()
            fetch_blobs(ctx, tmp, missing)
            log('fetched %d blobs, %.0fs' % (len(missing), time.time() - t))
        lines, still = history.count_lines(tmp, oids)
        if still:
            raise ArtifactUnavailable('%d blobs of %s are missing after the fetch' % (len(still), sha[:12]))
        ctx.bytes['git'] += du(os.path.join(tmp, 'objects'))
    counts = dict.fromkeys(history.KEYS, 0)
    files = collections.Counter()
    for oid, p, lang in entries:
        counts[lang] += lines[oid]
        files[lang] += 1
    st['files'] = dict(files)
    st['other_ext'] = sum(1 for p in paths if not lang_of(p))
    return counts, st


# ---------------------------------------------------------------------------------------------------------------
# the whole build


@contextlib.contextmanager
def stage(ctx, name):
    """Time a step and turn every expected failure inside it into ArtifactUnavailable."""
    t = time.time()
    try:
        yield
    except ArtifactUnavailable as e:
        raise ArtifactUnavailable('%s: %s' % (name, e)) from None
    except (urllib.error.URLError, socket.timeout, OSError, EOFError, tarfile.TarError, lzma.LZMAError,
            zipfile.BadZipFile, zlib.error, struct.error, subprocess.SubprocessError, history.HistoryError,
            ValueError, KeyError, IndexError, UnicodeError) as e:
        raise ArtifactUnavailable('%s: %s: %s' % (name, type(e).__name__, e)) from None
    finally:
        ctx.stats.setdefault('seconds', {})[name] = round(time.time() - t, 1)


def artifact_from_build(symbols_url, package_url, repo, sha=None, revisions=None, source=None,
                        excludes=history.DEFAULT_EXCLUDES, remote=GIT_REMOTE, ctx=None):
    """The `artifact` block for one Linux x86-64 build, given its symbols zip and package (target.tar.xz or a release
    tarball). The commit is taken from the FILE records; `sha` (if given) must equal it and `revisions` (if given)
    must contain it. `source` is merged into the record's source object. Raises ArtifactUnavailable."""
    ctx = ctx or Context()
    with stage(ctx, 'package'):
        elves, omni = scan_package(ctx, package_url)
        if not omni:
            raise ArtifactUnavailable('no omni.ja in the package')
        log('package: %d ELF files, omni.ja %s' % (len(elves), json.dumps(omni, sort_keys=True)))
    with stage(ctx, 'symbols'):
        rf = RemoteFile(ctx, symbols_url, 'symbols')
        names = zip_directory(rf)
        chosen, skipped = select_modules(elves, names)
        lines, read = [], []
        for mod, did, ent in chosen:
            head = zip_sym_header(rf, names[ent])
            if not head or not head[0].startswith('MODULE') or did not in head[0]:
                raise ArtifactUnavailable('%s: unexpected first line %r' % (ent, head[:1]))
            n = sum(1 for x in head if x.startswith('FILE '))
            read.append({'module': mod, 'debug_id': did, 'file_records': n})
            lines.extend(head)
        paths, revs, dropped = repo_paths(lines)
        commit = build_sha(revs, revisions, sha)
        xul = [r['debug_id'] for r in read if r['module'] == 'libxul.so'][0]
        ctx.stats.update(modules_read=read, modules_skipped=skipped, paths=len(paths), dropped=dict(dropped),
                         sha=commit, symbols_size=rf.size)
        log('symbols: %d modules read, %d skipped %s, %d paths at %s' % (
            len(read), len(skipped), [m for m, _ in skipped], len(paths), commit[:12]))
    with stage(ctx, 'count'):
        counts, st = count_paths(ctx, repo, commit, paths, excludes, remote)
        ctx.stats['count'] = st
    for k in OMNI_KEYS + ('asm',):
        if counts[k]:
            log('warning: the FILE records name %s files (%d lines); not counted, %s' % (
                k, counts[k], 'asm is not covered' if k == 'asm' else 'taken from omni.ja'))
    ctx.stats['file_pass_dropped'] = {k: counts[k] for k in OMNI_KEYS + ('asm',)}
    rec = {k: 0 for k in history.KEYS}
    for k in FILE_PASS_KEYS:
        rec[k] = counts[k]
    for jar in omni.values():
        for k in OMNI_KEYS:
            rec[k] += jar[k]
    rec['sha'] = commit
    rec['source'] = dict({'kind': 'symbols'}, **(source or {}), libxul_debug_id=xul, modules=len(read),
                         paths=len(paths))
    ctx.stats['seconds']['total'] = round(time.time() - ctx.t0, 1)
    ctx.stats['bytes'] = dict(ctx.bytes)
    return rec


def head_artifact(repo, index=INDEX, excludes=history.DEFAULT_EXCLUDES, remote=GIT_REMOTE, ctx=None):
    """The `artifact` block of the newest finished build in a Taskcluster index (default: mozilla-central
    linux64-opt). Raises ArtifactUnavailable."""
    ctx = ctx or Context()
    with stage(ctx, 'index'):
        b = resolve_index(ctx, index)
        log('index %s: task %s, revisions %s' % (index, b['task'], [r[:12] for r in b['revisions']]))
    return artifact_from_build(b['symbols'], b['package'], repo, revisions=b['revisions'],
                               source={'index': index, 'task': b['task']}, excludes=excludes, remote=remote, ctx=ctx)


def try_head(repo, **kw):
    """head_artifact(), or None (logged) if the artifact cannot be computed for any reason. For the weekly job."""
    try:
        return head_artifact(repo, **kw)
    except ArtifactUnavailable as e:
        log('artifact unavailable:', e)
    except Exception as e:  # never fail the weekly job because of the artifact
        log('artifact failed: %s: %s' % (type(e).__name__, e))
    return None


# ---------------------------------------------------------------------------------------------------------------
# command line


def main(argv=None, ctx=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', metavar='COMMAND')
    sub.required = True

    def common(p):
        p.add_argument('--repo', required=True, help='checkout of mozilla-firefox/firefox (only read)')
        p.add_argument('--remote', default=GIT_REMOTE, help='where missing commits and blobs are fetched from')
        p.add_argument('--out', help='write the record here instead of stdout')
        p.add_argument('--stats', help='write run statistics (JSON) here')
        p.add_argument('--deadline', type=float, default=DEADLINE, help='seconds for the whole run (default %(default)s)')

    p = sub.add_parser('head', help='artifact of the newest finished mozilla-central linux64-opt build')
    p.add_argument('--index', default=INDEX, help='Taskcluster index namespace (default %(default)s)')
    common(p)
    p = sub.add_parser('build', help='artifact of a build given by its symbols zip and package URLs')
    p.add_argument('--symbols', required=True, help='URL of the crashreporter-symbols.zip')
    p.add_argument('--package', required=True, help='URL of the target.tar.xz or release tarball')
    p.add_argument('--sha', help='the git sha the FILE records must name')
    common(p)
    a = ap.parse_args(argv)
    ctx = ctx or Context(a.deadline)
    try:
        if a.cmd == 'head':
            rec = head_artifact(a.repo, a.index, remote=a.remote, ctx=ctx)
        else:
            rec = artifact_from_build(a.symbols, a.package, a.repo, sha=a.sha, remote=a.remote, ctx=ctx)
    except ArtifactUnavailable as e:
        log('artifact unavailable:', e)
        return EXIT_UNAVAILABLE
    finally:
        if a.stats:
            ctx.stats.setdefault('bytes', dict(ctx.bytes))
            with open(a.stats, 'w') as f:
                json.dump(ctx.stats, f, indent=1, default=list)
    text = history.dumps(rec) + '\n'
    if a.out:
        history.write_atomic(a.out, text)
    else:
        sys.stdout.write(text)
    total = sum(rec[k] for k in history.KEYS)
    log('artifact at %s: %d lines, Rust %.2f%%; %s bytes downloaded, %.0fs' % (
        rec['sha'][:12], total, 100.0 * rec['rust'] / max(total, 1), dict(ctx.bytes), time.time() - ctx.t0))
    return 0


if __name__ == '__main__':
    sys.exit(main())
