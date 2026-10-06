#!/usr/bin/env python3
"""Language line counts per Firefox major release (data/history.json) and the site data (build/data.json).

One counter serves the backfill, the weekly append and the head point. It reads git objects only (`git ls-tree`,
`git cat-file`), never a working tree, so it works on a blobless clone, a depth-1 checkout or a full clone.

Subcommands:

  backfill REPO OUT        count every major release tagged in REPO and write a new history file
  append HISTORY --repo R  add the majors that are missing from HISTORY: list the remote tags of R with
                           `git ls-remote --tags origin`, fetch each missing tag with `git fetch --depth 1` and count it
                           (works on the workflow's depth-1 checkout, which has no tags; never lists local tags).
                           Refuses a file whose method_version differs from this code's METHOD_VERSION
  head REPO                count HEAD of a checkout and print {"sha","date","all","browser"}
  build-site HISTORY --repo R --out DIR
                           write DIR/data.json: the history, the head point of R and the legacy fields of the old
                           pie chart (meta_date, title_date, lang)

Two views of every commit (METHOD_VERSION 4):
  "all"      every tracked file whose extension is in the language set, no exclusions (mobile/ included)
  "browser"  "all" minus the paths under a prefix of `browser_excluded_prefixes` and minus test paths (see is_test())
`backfill` and `head` use BROWSER_EXCLUDED_PREFIXES; `append` and `build-site` take the prefixes from the history
file's `browser_excluded_prefixes`, so new records always match the old ones.

BROWSER_EXCLUDED_PREFIXES (plain path-prefix matches, chosen by hand from the tree at release 157 and checked against
older releases; docs/methodology.md has the table with the lines under each):
  mobile/               the Android apps (Firefox for Android, Focus, GeckoView, Android Components)
  build/clang-plugin/   Mozilla's clang static-analysis plugin, run while compiling, not part of the browser
  build/pgo/            the pages and server that train profile-guided optimisation builds
  docs/                 the Firefox source documentation (Sphinx configuration and extensions)
  python/               mach, mozbuild and the other Python build and developer tools (before release 55 also the
                        vendored Python packages they use)
  taskcluster/          the CI task graph, Docker images and CI scripts
  third_party/node/     vendored Node packages (webpack, Babel and friends) used to bundle code at build time
  third_party/python/   vendored Python packages used by the build system and the tools above
  tools/@types/         TypeScript declaration files for type-checking the JavaScript; never compiled or shipped
  tools/lint/           the linters (ESLint configuration and plugins, Python linters)
  tools/tryselect/      `mach try`, which picks CI jobs to push to the try server
Other directories under build/ and tools/ stay: some hold shipped code (tools/profiler is the Gecko Profiler,
build/unix holds elfhack and stdc++compat, build/rust holds shim crates linked into libxul; build/stlport, in
releases 46 to 51, was the C++ runtime of Android builds).

Release set: FIREFOX_<n>_0_RELEASE for n = 46 up to the newest major with a _RELEASE tag. A major without a _RELEASE
tag inside that range is counted at FIREFOX_<n>_0_BUILD1 and stored under v = n (only 125 today). A newer major that
has only BUILD tags (still in the release process) is not added until its _RELEASE tag exists.

Languages (by extension, case-sensitive; `.h` headers are kept apart as `h` and split between C and C++ at display
time with `header_split`):
rust .rs | c .c | cpp .cc .cpp .cxx .hxx .hpp .hh | h .h | js .jsm .jsx .js .mjs | ts .ts |
html .htm .html .xhtml .xht .css | py .py | java .java | kt .kt | asm .asm .S .s
A blob that contains a NUL byte is binary and counts 0 lines (the .ts MPEG transport streams of the media tests,
for example). Changing the set, the test rules, the binary rule or the views means bumping METHOD_VERSION and
regenerating. The versions so far (details in the git history of this repository):
  1  the first backfill (mobile/ left out of every view)
  2  the two views above, with mobile/ as the only excluded prefix ("all" now includes mobile/)
  3  2 plus kt, ts, .hpp/.hh as cpp, .S/.s as asm and the binary rule
  4  3 plus the tooling prefixes of BROWSER_EXCLUDED_PREFIXES ("all" is the same as in 3)

How to regenerate data/history.json from scratch (about 10 minutes and 3.5 GB of disk; run it locally, not in CI):

  git clone --no-checkout --filter=blob:none --single-branch --branch main \\
      https://github.com/mozilla-firefox/firefox.git ff
  git -C ff fetch -q --filter=blob:none origin \\
      '+refs/tags/FIREFOX_*_0_RELEASE:refs/tags/FIREFOX_*_0_RELEASE' \\
      '+refs/tags/FIREFOX_*_0_BUILD1:refs/tags/FIREFOX_*_0_BUILD1'
  python3 dev/history.py backfill ff data/history.json

`backfill` first fetches every needed blob in a few parallel batched fetches (lazy per-object fetching would take
hours), then counts each distinct blob once. Rebuilding gives the same file apart from newly released versions;
compare it with the committed file whenever METHOD_VERSION changes. The weekly job only runs `append` and
`build-site`. Tests: python3 -m unittest discover -s dev

`date` is the committer date of the counted commit. A few converted commits carry a zero timestamp (1970-01-01;
FIREFOX_123_0_RELEASE is one); for those the date of the nearest first-parent ancestor with a real timestamp is stored,
and counting fails rather than store 1970 when no such ancestor is present (a depth-1 clone). `append` handles that
case by fetching 10 more commits of the tag (`git fetch --deepen 10`) and counting again.

Requires git 2.44 or newer for `backfill` on a partial clone (GIT_NO_LAZY_FETCH); older git still gives correct
counts but fetches missing blobs one at a time, which takes hours.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone

METHOD_VERSION = 4
FIRST_MAJOR = 46
# path prefixes left out of the "browser" view (never out of "all"): the mobile apps and build/developer tooling
# (what each one is: module docstring and docs/methodology.md)
BROWSER_EXCLUDED_PREFIXES = ('mobile/', 'build/clang-plugin/', 'build/pgo/', 'docs/', 'python/', 'taskcluster/',
                             'third_party/node/', 'third_party/python/', 'tools/@types/', 'tools/lint/',
                             'tools/tryselect/')
# Share of `.h` lines given to C and C++ at display time (by location about 81.5% of headers are C++).
HEADER_SPLIT = {'c': 0.185, 'cpp': 0.815}

# language key -> extensions; the key order is the order of the columns in every record
LANGS = [
    ('rust', ('.rs',)), ('c', ('.c',)), ('cpp', ('.cc', '.cpp', '.cxx', '.hxx', '.hpp', '.hh')), ('h', ('.h',)),
    ('js', ('.jsm', '.jsx', '.js', '.mjs')), ('ts', ('.ts',)), ('html', ('.htm', '.html', '.xhtml', '.xht', '.css')),
    ('py', ('.py',)), ('java', ('.java',)), ('kt', ('.kt',)), ('asm', ('.asm', '.S', '.s')),
]
EXT2LANG = {e: k for k, es in LANGS for e in es}
KEYS = [k for k, _ in LANGS]
EXT_RE = re.compile(r'(\.[A-Za-z0-9]+)$')

# name and key of each slice of the old pie chart, in the order of the deployed data.json
LEGACY_LANG = [('Rust', 'rust'), ('C', 'c'), ('C++', 'cpp'), ('JavaScript', 'js'), ('TypeScript', 'ts'),
               ('HTML', 'html'), ('Python', 'py'), ('Java', 'java'), ('Kotlin', 'kt'), ('Assembly', 'asm')]
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# directory names that mark test code (any path component); the rules are described in docs/methodology.md
TESTDIRS = {'test', 'tests', 'gtest', 'gtests', 'mochitest', 'mochitests', 'xpcshell', 'reftest', 'reftests',
            'crashtest', 'crashtests', '__tests__', 'androidTest', 'test262', 'unittests', 'googletest', 'testdata',
            'fixtures', 'browser_tests', 'jsapi-tests', 'jit-test'}
TEST_PREFIXES = ('js/src/tests/', 'js/src/jit-test/', 'js/src/jsapi-tests/', 'js/src/octane/',
                 'third_party/webkit/PerformanceTests/')
TESTDIR_SUFFIX_RE = re.compile(r'[-_]tests?$')
TESTDIR_PREFIX_RE = re.compile(r'tests?[-_]')
RELEASE_RE = re.compile(r'FIREFOX_(\d+)_0_RELEASE')
TAG_PATTERNS = ('FIREFOX_*_0_RELEASE', 'FIREFOX_*_0_BUILD1')


def no_lazy_fetch():
    """Environment for git commands that must not fetch missing objects one at a time (they are batched instead)."""
    return dict(os.environ, GIT_NO_LAZY_FETCH='1')


class HistoryError(RuntimeError):
    """A failure with a message meant for the user (printed without a traceback by the command line)."""


class ZeroTimestampError(HistoryError):
    """A commit has a zero timestamp and no dated first-parent ancestor is present (shallow clone)."""


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def is_test(path):
    """True if the repository path is test code (rules described in docs/methodology.md)."""
    parts = path.split('/')
    if parts[0] == 'testing' or path.startswith(TEST_PREFIXES):
        return True
    dirs = parts[:-1]
    for c in dirs:
        if c in TESTDIRS or TESTDIR_SUFFIX_RE.search(c) or TESTDIR_PREFIX_RE.match(c):
            return True
    if len(parts) > 2 and 'testing' in dirs[1:]:
        return True
    f = parts[-1]
    return path.endswith('.rs') and (f in ('tests.rs', 'test.rs') or f.endswith(('_test.rs', '_tests.rs')))


def git(repo, *args, env=None):
    return subprocess.check_output(['git', '-C', repo, *args], env=env)


# ---------------------------------------------------------------------------------------------------------------
# release set


def pick_majors(tag_names, first=FIRST_MAJOR):
    """[(major, tag)] from a collection of tag names, sorted by major.

    Majors run from `first` to the newest major that has a FIREFOX_<n>_0_RELEASE tag. A major without that tag uses
    FIREFOX_<n>_0_BUILD1 instead (release 125). Majors newer than the newest _RELEASE tag are left out even if they
    have BUILD tags: they have not shipped yet, and a record is never rewritten once stored."""
    names = set(tag_names)
    released = [int(m.group(1)) for m in map(RELEASE_RE.fullmatch, names) if m]
    out = []
    for v in range(first, max(released, default=first - 1) + 1):
        for cand in ('FIREFOX_%d_0_RELEASE' % v, 'FIREFOX_%d_0_BUILD1' % v):
            if cand in names:
                out.append((v, cand))
                break
        else:
            log('warning: no tag for release %d' % v)
    return out


def releases(repo, first=FIRST_MAJOR):
    """Majors from the tags of a local clone (backfill only; a depth-1 checkout has no tags)."""
    return pick_majors(git(repo, 'tag', '-l', *TAG_PATTERNS).decode().split(), first)


def remote_tags(repo, remote='origin'):
    """Release tag names on the remote, from `git ls-remote` (no fetch)."""
    out = git(repo, 'ls-remote', '--tags', remote, *TAG_PATTERNS).decode()
    names = set()
    for line in out.splitlines():
        ref = line.split('\t', 1)[1] if '\t' in line else ''
        if ref.startswith('refs/tags/'):
            names.add(ref[len('refs/tags/'):].replace('^{}', ''))
    return names


# ---------------------------------------------------------------------------------------------------------------
# counting


def tree(repo, rev):
    """Yield (blob id, path, language) for every counted file of a commit (no exclusions)."""
    out = git(repo, 'ls-tree', '-r', '-z', rev)
    for rec in out.split(b'\0'):
        if not rec:
            continue
        meta, path = rec.split(b'\t', 1)
        p = path.decode('utf8', 'replace')
        m = EXT_RE.search(p)
        lang = EXT2LANG.get(m.group(1)) if m else None
        if lang:
            mode, typ, oid = meta.split()
            if typ == b'blob':
                yield oid.decode(), p, lang


def count_lines(repo, oids):
    """({oid: newline count}, [missing oids]) for blobs, via one `git cat-file --batch` (no lazy fetch).

    A blob that contains a NUL byte is binary (not source code) and counts 0."""
    p = subprocess.Popen(['git', '-C', repo, 'cat-file', '--batch'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         env=no_lazy_fetch())

    def feed():
        try:
            p.stdin.write(('\n'.join(oids) + '\n').encode())
        finally:
            p.stdin.close()
    writer = threading.Thread(target=feed)
    writer.start()
    lines, missing = {}, []
    for oid in oids:
        h = p.stdout.readline().split()
        if not h:
            raise HistoryError('git cat-file ended early')
        if h[-1] == b'missing':
            missing.append(oid)
            continue
        size = int(h[2])
        data = p.stdout.read(size)
        p.stdout.read(1)
        lines[oid] = 0 if b'\0' in data else data.count(b'\n')
    writer.join()
    p.stdout.close()
    if p.wait():
        raise HistoryError('git cat-file failed')
    return lines, missing


def missing_blobs(repo, oids):
    """The oids of `oids` that are not in the local object store (no lazy fetch)."""
    out = subprocess.run(['git', '-C', repo, 'cat-file', '--batch-check=%(objectname)'], env=no_lazy_fetch(),
                         input=('\n'.join(oids) + '\n').encode(), stdout=subprocess.PIPE, check=True).stdout
    return [line.split()[0].decode() for line in out.splitlines() if line.endswith(b' missing')]


def promisor_remote(repo):
    """Name of the remote a partial clone fetches missing objects from, or None for a complete clone."""
    try:
        return git(repo, 'config', '--get', 'extensions.partialclone').decode().strip() or None
    except subprocess.CalledProcessError:
        pass
    try:  # newer git marks the remote instead: remote.<name>.promisor=true
        out = git(repo, 'config', '--bool', '--get-regexp', r'^remote\..*\.promisor$').decode()
    except subprocess.CalledProcessError:
        return None
    for line in out.splitlines():
        key, _, value = line.partition(' ')
        if value == 'true':
            return key[len('remote.'):-len('.promisor')]
    return None


def fetch_blobs(repo, oids, streams=4):
    """Fetch blobs of a partial clone by id, in `streams` parallel batched fetches."""
    remote = promisor_remote(repo)
    if not remote:
        raise HistoryError('%d blobs are missing and %s is not a partial clone' % (len(oids), repo))
    oids = sorted(oids)
    streams = max(1, min(streams, len(oids) // 1000 + 1))
    t0 = time.time()
    procs = []
    for i in range(streams):
        f = tempfile.TemporaryFile()
        f.write(('\n'.join(oids[i::streams]) + '\n').encode())
        f.seek(0)
        procs.append((f, subprocess.Popen(
            ['git', '-C', repo, '-c', 'fetch.negotiationAlgorithm=noop', 'fetch', '-q', '--no-tags',
             '--no-write-fetch-head', '--filter=blob:none', '--stdin', remote], stdin=f)))
    failed = 0
    for f, p in procs:
        failed += p.wait() != 0
        f.close()
    if failed:
        raise HistoryError('%d of %d blob fetches failed' % (failed, streams))
    log('fetched %d blobs in %d streams, %.0fs' % (len(oids), streams, time.time() - t0))


def resolve_commit(repo, rev):
    """The commit id `rev` points to (peeling annotated tags), or HistoryError if there is none."""
    try:
        return git(repo, 'rev-parse', '--verify', '-q', rev + '^{commit}').decode().strip()
    except subprocess.CalledProcessError:
        raise HistoryError('%s is not a commit in %s (empty repository or missing tag?)' % (rev, repo)) from None


def commit_date(repo, sha, limit=100):
    """Committer date (YYYY-MM-DD) of `sha`. A zero timestamp (a conversion artefact) is replaced by the date of the
    nearest first-parent ancestor with a non-zero one; HistoryError if none is reachable (for example a shallow clone)."""
    out = git(repo, 'log', '--first-parent', '-n', str(limit), '--format=%ct %cs', sha).decode()
    for line in out.splitlines():
        ct, cs = line.split()
        if int(ct) != 0:
            return cs
    raise ZeroTimestampError('commit %s has a zero timestamp and none of its first %d first-parent ancestors present '
                             'in %s has a real one; fetch more history (e.g. git fetch --deepen 10)' % (sha, limit, repo))


def count_release(repo, rev, browser_excluded=BROWSER_EXCLUDED_PREFIXES, cache=None, fetch=True):
    """Count one commit (a release tag or HEAD) of any clone: blobless, depth 1 or full.

    Returns {"sha","date","all","browser"}: "all" counts every file, "browser" leaves out the paths under a prefix of
    `browser_excluded` and the test paths. `cache` maps blob id -> line count and may be shared
    between calls so that a blob is read once across releases. On a partial clone, missing blobs are fetched in one
    batch first (unless fetch=False)."""
    if cache is None:
        cache = {}
    browser_excluded = tuple(browser_excluded)
    sha = resolve_commit(repo, rev)
    entries = list(tree(repo, sha))
    todo = sorted({oid for oid, _, _ in entries if oid not in cache})
    if todo:
        lines, missing = count_lines(repo, todo)
        if missing:
            if not fetch:
                raise HistoryError('%d blobs of %s are missing' % (len(missing), rev))
            fetch_blobs(repo, missing)
            more, missing = count_lines(repo, missing)
            if missing:
                raise HistoryError('%d blobs of %s are still missing after the fetch' % (len(missing), rev))
            lines.update(more)
        cache.update(lines)
    allc = dict.fromkeys(KEYS, 0)
    browser = dict.fromkeys(KEYS, 0)
    for oid, path, lang in entries:
        n = cache[oid]
        allc[lang] += n
        if not (browser_excluded and path.startswith(browser_excluded)) and not is_test(path):
            browser[lang] += n
    return {'sha': sha, 'date': commit_date(repo, sha), 'all': allc, 'browser': browser}


def release_record(v, tag, counted):
    return {'v': v, 'tag': tag, **counted}


# ---------------------------------------------------------------------------------------------------------------
# history file: a header line, then one release per line, sorted by v


def dumps(obj):
    return json.dumps(obj, separators=(',', ':'))


def default_meta(browser_excluded=BROWSER_EXCLUDED_PREFIXES):
    return {'method_version': METHOD_VERSION, 'browser_excluded_prefixes': list(browser_excluded),
            'header_split': dict(HEADER_SPLIT)}


def format_history(meta, records, extra=None):
    """The history layout: header keys, then "releases" with one record per line, then optional trailing keys."""
    head = ''.join('%s:%s,' % (dumps(k), dumps(v)) for k, v in meta.items())
    rows = ',\n'.join(dumps(r) for r in sorted(records, key=lambda r: r['v']))
    tail = ''.join(',\n%s:%s' % (dumps(k), dumps(v)) for k, v in (extra or {}).items())
    return '{%s"releases":[\n%s%s]%s}\n' % (head, rows, '\n' if rows else '', tail)


def write_atomic(path, text):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.history-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def read_history(path):
    """(header dict without "releases", list of release records) of a history file."""
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    records = data.pop('releases')
    return data, records


def read_current_history(path):
    """read_history() of a file written by this METHOD_VERSION; HistoryError (file untouched) for any other."""
    meta, records = read_history(path)
    if meta.get('method_version') != METHOD_VERSION:
        raise HistoryError('%s has method_version %s, this code writes %d; regenerate it with `backfill` instead of '
                           'mixing methods in one file' % (path, json.dumps(meta.get('method_version')), METHOD_VERSION))
    if not isinstance(meta.get('browser_excluded_prefixes'), list):
        raise HistoryError('%s has no browser_excluded_prefixes list' % path)
    return meta, records


# ---------------------------------------------------------------------------------------------------------------
# legacy fields of the old pie chart


def legacy_fields(head_all, header_split, now):
    """meta_date, title_date and lang as the old dev/build-data wrote them, with headers split by `header_split`."""
    h = head_all['h']
    hc = int(round(h * header_split['c']))
    split = dict(head_all, c=head_all['c'] + hc, cpp=head_all['cpp'] + h - hc)
    return {
        'meta_date': now.isoformat(timespec='seconds'),
        'title_date': '%s %d' % (MONTHS[now.month - 1], now.year),
        'lang': [{'name': name, 'loc': split[key]} for name, key in LEGACY_LANG],
    }


# ---------------------------------------------------------------------------------------------------------------
# subcommands


def backfill(repo, out, first=FIRST_MAJOR, streams=4):
    t0 = time.time()
    rel = releases(repo, first)
    if not rel:
        raise SystemExit('no FIREFOX_<n>_0_RELEASE tags in %s; fetch the release tags first' % repo)
    if promisor_remote(repo):
        need = set()
        for v, tag in rel:
            need.update(oid for oid, _, _ in tree(repo, tag))
        missing = missing_blobs(repo, sorted(need))
        log('%d distinct counted files, %d to fetch, %.0fs' % (len(need), len(missing), time.time() - t0))
        del need
        if missing:
            fetch_blobs(repo, missing, streams)
    t1 = time.time()
    cache, records = {}, []
    for v, tag in rel:
        records.append(release_record(v, tag, count_release(repo, tag, BROWSER_EXCLUDED_PREFIXES, cache)))
    log('counted %d distinct files for %d releases, %.0fs' % (len(cache), len(records), time.time() - t1))
    write_atomic(out, format_history(default_meta(), records))
    log('wrote %d releases to %s, %.0fs total' % (len(records), out, time.time() - t0))


def append(history, repo, remote='origin'):
    """Add the majors missing from `history`; returns how many were added. Leaves the file untouched if none.

    Refuses (HistoryError, file untouched) a file written by another METHOD_VERSION."""
    meta, records = read_current_history(history)
    browser_excluded = tuple(meta['browser_excluded_prefixes'])
    have = {r['v'] for r in records}
    first = min(have, default=FIRST_MAJOR)
    todo = [(v, tag) for v, tag in pick_majors(remote_tags(repo, remote), first) if v not in have]
    if not todo:
        log('%s is current (%d releases)' % (history, len(records)))
        return 0
    cache = {}
    for v, tag in todo:
        t0 = time.time()
        git(repo, 'fetch', '-q', '--no-tags', '--depth', '1', remote, 'tag', tag)
        try:
            counted = count_release(repo, tag, browser_excluded, cache)
        except ZeroTimestampError:
            # the tagged commit has a zero timestamp (like 123): fetch a few parents for the date and count again
            # (the blobs are cached, so the second count only lists the tree)
            log('%s has a zero timestamp; fetching 10 more commits for its date' % tag)
            git(repo, 'fetch', '-q', '--no-tags', '--deepen', '10', remote, 'tag', tag)
            counted = count_release(repo, tag, browser_excluded, cache)
        records.append(release_record(v, tag, counted))
        write_atomic(history, format_history(meta, records))
        log('added %d (%s), %.0fs' % (v, tag, time.time() - t0))
    return len(todo)


def build_site(history, repo, out_dir, now=None):
    """Write out_dir/data.json: legacy fields, the history header and releases, and the head point of `repo`.

    Refuses (HistoryError) a history file written by another METHOD_VERSION: the page reads this version's keys."""
    meta, records = read_current_history(history)
    head = count_release(repo, 'HEAD', meta['browser_excluded_prefixes'])
    now = now or datetime.now(timezone.utc).replace(microsecond=0)
    header = dict(legacy_fields(head['all'], meta.get('header_split', HEADER_SPLIT), now), **meta)
    path = os.path.join(out_dir, 'data.json')
    write_atomic(path, format_history(header, records, {'head': head}))
    log('wrote %s: %d releases and the head at %s' % (path, len(records), head['sha'][:12]))
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', metavar='COMMAND')
    sub.required = True

    p = sub.add_parser('backfill', help='count every major release tagged in REPO into a new history file')
    p.add_argument('repo')
    p.add_argument('out')
    p.add_argument('--first', type=int, default=FIRST_MAJOR, help='first major (default %(default)s)')
    p.add_argument('--streams', type=int, default=4, help='parallel blob fetches (default %(default)s)')

    p = sub.add_parser('append', help='add missing majors to HISTORY (lists remote tags, fetches each at depth 1)')
    p.add_argument('history')
    p.add_argument('--repo', required=True, help='checkout to fetch into and count in')
    p.add_argument('--remote', default='origin')

    p = sub.add_parser('head', help='count HEAD of REPO and print the record')
    p.add_argument('repo')
    p.add_argument('--out', help='write the record here instead of stdout')

    p = sub.add_parser('build-site', help='write OUT/data.json from HISTORY and the head of REPO')
    p.add_argument('history')
    p.add_argument('--repo', required=True)
    p.add_argument('--out', required=True, help='output directory (e.g. build)')

    a = ap.parse_args(argv)
    try:
        run(a)
    except HistoryError as e:
        ap.exit(1, '%s: error: %s\n' % (ap.prog, e))
    return 0


def run(a):
    if a.cmd == 'backfill':
        backfill(a.repo, a.out, a.first, a.streams)
    elif a.cmd == 'append':
        append(a.history, a.repo, a.remote)
    elif a.cmd == 'head':
        text = dumps(count_release(a.repo, 'HEAD')) + '\n'
        if a.out:
            write_atomic(a.out, text)
        else:
            sys.stdout.write(text)
    elif a.cmd == 'build-site':
        build_site(a.history, a.repo, a.out)


if __name__ == '__main__':
    sys.exit(main())
