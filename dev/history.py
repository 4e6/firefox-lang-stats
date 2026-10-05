#!/usr/bin/env python3
"""Language line counts per Firefox major release (data/history.json) and the site data (build/data.json).

One counter serves the backfill, the weekly append and the head point. It reads git objects only (`git ls-tree`,
`git cat-file`), never a working tree, so it works on a blobless clone, a depth-1 checkout or a full clone.

Subcommands:

  backfill REPO OUT        count every major release tagged in REPO and write a new history file
  append HISTORY --repo R  add the majors that are missing from HISTORY: list the remote tags of R with
                           `git ls-remote --tags origin`, fetch each missing tag with `git fetch --depth 1` and count it
                           (works on the workflow's depth-1 checkout, which has no tags; never lists local tags)
  head REPO                count HEAD of a checkout and print {"sha","date","all","nontest","artifact"}
  build-site HISTORY --repo R --out DIR [--with-artifact]
                           write DIR/data.json: the history, the head point of R and the legacy fields of the old
                           pie chart (meta_date, title_date, lang). --with-artifact also computes head.artifact, the
                           browser artifact of the newest finished mozilla-central linux64-opt build (dev/artifact.py);
                           when it cannot be computed it is null and the command still succeeds
  set-artifact HISTORY --v N --symbols URL --package URL --repo R
                           compute the browser artifact of release N from its build's crashreporter-symbols.zip and
                           package (for example Mozilla's release candidates) and store it in that release's record,
                           the only change to the file. Refuses a release that already has one; exit status 3 (file
                           untouched) if the artifact cannot be computed. For release N the build is the last
                           build<B> directory of https://archive.mozilla.org/pub/firefox/candidates/N.0-candidates/
                           and its linux-x86_64/en-US/ files firefox-N.0.crashreporter-symbols.zip and
                           firefox-N.0.tar.xz (.tar.bz2 for older releases)

`backfill` and `head` skip paths under `mobile/` by default (desktop browser only). `--exclude PREFIX` (repeatable)
replaces that default, `--no-exclude` counts everything. `append` and `build-site` take the prefixes from the
history file's `excluded_prefixes`, so new records always match the old ones.

Release set: FIREFOX_<n>_0_RELEASE for n = 46 up to the newest major with a _RELEASE tag. A major without a _RELEASE
tag inside that range is counted at FIREFOX_<n>_0_BUILD1 and stored under v = n (only 125 today). A newer major that
has only BUILD tags (still in the release process) is not added until its _RELEASE tag exists.

Languages (by extension; C/C++ headers are kept apart as `h` and split at display time with `header_split`):
rust .rs | c .c | cpp .cc .cpp .cxx .hxx | h .h | js .jsm .jsx .js .mjs | html .htm .html .xhtml .xht .css |
py .py | java .java | asm .asm. Changing the set or the test rules means bumping METHOD_VERSION and regenerating.
"all" is every tracked file; "nontest" drops test paths (see is_test()).

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

METHOD_VERSION = 1
FIRST_MAJOR = 46
DEFAULT_EXCLUDES = ('mobile/',)
# Share of `.h` lines given to C and C++ at display time (by location about 81.5% of headers are C++).
HEADER_SPLIT = {'c': 0.185, 'cpp': 0.815}

# language key -> extensions; the key order is the order of the columns in every record
LANGS = [
    ('rust', ('.rs',)), ('c', ('.c',)), ('cpp', ('.cc', '.cpp', '.cxx', '.hxx')), ('h', ('.h',)),
    ('js', ('.jsm', '.jsx', '.js', '.mjs')), ('html', ('.htm', '.html', '.xhtml', '.xht', '.css')),
    ('py', ('.py',)), ('java', ('.java',)), ('asm', ('.asm',)),
]
EXT2LANG = {e: k for k, es in LANGS for e in es}
KEYS = [k for k, _ in LANGS]
EXT_RE = re.compile(r'(\.[A-Za-z0-9]+)$')

# name and key of each slice of the old pie chart, in the order of the deployed data.json
LEGACY_LANG = [('Rust', 'rust'), ('C', 'c'), ('C++', 'cpp'), ('JavaScript', 'js'), ('HTML', 'html'),
               ('Python', 'py'), ('Java', 'java'), ('Assembly', 'asm')]
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# directory names that mark test code (any path component); see docs/reference/test-paths/README.md
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
    """True if the repository path is test code (rules in docs/reference/test-paths/README.md)."""
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


def tree(repo, rev, excludes=()):
    """Yield (blob id, path, language) for the counted files of a commit, skipping paths under `excludes`."""
    excludes = tuple(excludes)
    out = git(repo, 'ls-tree', '-r', '-z', rev)
    for rec in out.split(b'\0'):
        if not rec:
            continue
        meta, path = rec.split(b'\t', 1)
        p = path.decode('utf8', 'replace')
        m = EXT_RE.search(p)
        lang = EXT2LANG.get(m.group(1)) if m else None
        if lang and not (excludes and p.startswith(excludes)):
            mode, typ, oid = meta.split()
            if typ == b'blob':
                yield oid.decode(), p, lang


def count_lines(repo, oids):
    """({oid: newline count}, [missing oids]) for blobs, via one `git cat-file --batch` (no lazy fetch)."""
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
        lines[oid] = data.count(b'\n')
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


def count_release(repo, rev, excludes=DEFAULT_EXCLUDES, cache=None, fetch=True):
    """Count one commit (a release tag or HEAD) of any clone: blobless, depth 1 or full.

    Returns {"sha","date","all","nontest","artifact": None}. `cache` maps blob id -> line count and may be shared
    between calls so that a blob is read once across releases. On a partial clone, missing blobs are fetched in one
    batch first (unless fetch=False)."""
    if cache is None:
        cache = {}
    sha = resolve_commit(repo, rev)
    entries = list(tree(repo, sha, excludes))
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
    nont = dict.fromkeys(KEYS, 0)
    for oid, path, lang in entries:
        n = cache[oid]
        allc[lang] += n
        if not is_test(path):
            nont[lang] += n
    return {'sha': sha, 'date': commit_date(repo, sha), 'all': allc, 'nontest': nont, 'artifact': None}


def release_record(v, tag, counted):
    return {'v': v, 'tag': tag, **counted}


# ---------------------------------------------------------------------------------------------------------------
# history file: a header line, then one release per line, sorted by v


def dumps(obj):
    return json.dumps(obj, separators=(',', ':'))


def default_meta(excludes):
    return {'method_version': METHOD_VERSION, 'excluded_prefixes': list(excludes), 'header_split': dict(HEADER_SPLIT)}


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


def backfill(repo, out, excludes=DEFAULT_EXCLUDES, first=FIRST_MAJOR, streams=4):
    t0 = time.time()
    excludes = tuple(excludes)
    rel = releases(repo, first)
    if not rel:
        raise SystemExit('no FIREFOX_<n>_0_RELEASE tags in %s; fetch the release tags first' % repo)
    if promisor_remote(repo):
        need = set()
        for v, tag in rel:
            need.update(oid for oid, _, _ in tree(repo, tag, excludes))
        missing = missing_blobs(repo, sorted(need))
        log('%d distinct counted files, %d to fetch, %.0fs' % (len(need), len(missing), time.time() - t0))
        del need
        if missing:
            fetch_blobs(repo, missing, streams)
    t1 = time.time()
    cache, records = {}, []
    for v, tag in rel:
        records.append(release_record(v, tag, count_release(repo, tag, excludes, cache)))
    log('counted %d distinct files for %d releases, %.0fs' % (len(cache), len(records), time.time() - t1))
    write_atomic(out, format_history(default_meta(excludes), records))
    log('wrote %d releases to %s, %.0fs total' % (len(records), out, time.time() - t0))


def append(history, repo, remote='origin'):
    """Add the majors missing from `history`; returns how many were added. Leaves the file untouched if none."""
    meta, records = read_history(history)
    excludes = tuple(meta.get('excluded_prefixes', ()))
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
            counted = count_release(repo, tag, excludes, cache)
        except ZeroTimestampError:
            # the tagged commit has a zero timestamp (like 123): fetch a few parents for the date and count again
            # (the blobs are cached, so the second count only lists the tree)
            log('%s has a zero timestamp; fetching 10 more commits for its date' % tag)
            git(repo, 'fetch', '-q', '--no-tags', '--deepen', '10', remote, 'tag', tag)
            counted = count_release(repo, tag, excludes, cache)
        records.append(release_record(v, tag, counted))
        write_atomic(history, format_history(meta, records))
        log('added %d (%s), %.0fs' % (v, tag, time.time() - t0))
    return len(todo)


EXIT_UNAVAILABLE = 3   # set-artifact: the artifact cannot be computed (same status as dev/artifact.py)


def _artifact_module():
    """dev/artifact.py, imported on first use (it imports this module, so not at the top)."""
    import artifact
    return artifact


def head_artifact(repo, excludes=DEFAULT_EXCLUDES, index=None, deadline=None):
    """The `artifact` block of the newest finished mozilla-central build, or None. Never raises (except
    KeyboardInterrupt): every failure, a bug included, is logged and gives None, so the weekly job carries on."""
    t0 = time.time()
    try:
        artifact = _artifact_module()
        ctx = artifact.Context(deadline or artifact.DEADLINE)
        kw = {'index': index} if index else {}
        block = artifact.try_head(repo, excludes=excludes, ctx=ctx, **kw)
    except Exception as e:
        import traceback
        log('head artifact: failed (a bug): %s: %s\n%s' % (type(e).__name__, e, traceback.format_exc().rstrip()))
        block, ctx = None, None
    if block is None:
        log('head artifact: none this run (reason above); head.artifact is null, the build goes on (%.0fs)'
            % (time.time() - t0))
        return None
    total = sum(block[k] for k in KEYS)
    log('head artifact: build commit %s, %d lines, Rust %.2f%%; seconds %s, bytes %s' % (
        block['sha'][:12], total, 100.0 * block['rust'] / max(total, 1), json.dumps(ctx.stats.get('seconds')),
        json.dumps(ctx.stats.get('bytes'))))
    return block


def build_site(history, repo, out_dir, now=None, with_artifact=False, artifact_index=None, artifact_deadline=None):
    """Write out_dir/data.json: legacy fields, the history header and releases, and the head point of `repo`.

    with_artifact: also compute head.artifact (null when it cannot be computed; never an error). Its `sha` is the
    commit of the build it was counted at, which is usually a little older than head.sha."""
    meta, records = read_history(history)
    head = count_release(repo, 'HEAD', meta.get('excluded_prefixes', ()))
    if with_artifact:
        head['artifact'] = head_artifact(repo, tuple(meta.get('excluded_prefixes', ())), artifact_index,
                                         artifact_deadline)
    now = now or datetime.now(timezone.utc).replace(microsecond=0)
    header = dict(legacy_fields(head['all'], meta.get('header_split', HEADER_SPLIT), now), **meta)
    path = os.path.join(out_dir, 'data.json')
    write_atomic(path, format_history(header, records, {'head': head}))
    log('wrote %s: %d releases and the head at %s' % (path, len(records), head['sha'][:12]))
    return path


def set_artifact(history, v, symbols, package, repo, kind='candidates'):
    """Store the browser artifact of release `v` in `history`, computed from its build's symbols zip and package.

    The artifact is a property of the release: computed once, never overwritten. The FILE records of the build must
    name the release's own commit (the record's sha). Only that record changes: the file is rewritten with the same
    writer, and refused if it is not already in that exact layout. Raises artifact.ArtifactUnavailable (file
    untouched) if the artifact cannot be computed, HistoryError for a usage problem."""
    with open(history, encoding='utf-8') as f:
        before = f.read()
    meta, records = read_history(history)
    if format_history(meta, records) != before:
        raise HistoryError('%s is not in the layout format_history() writes; refusing to rewrite it' % history)
    rec = next((r for r in records if r['v'] == v), None)
    if rec is None:
        raise HistoryError('release %d is not in %s' % (v, history))
    if rec.get('artifact') is not None:
        raise HistoryError('release %d already has an artifact (a stored artifact is never recomputed)' % v)
    artifact = _artifact_module()
    block = artifact.artifact_from_build(symbols, package, repo, sha=rec['sha'],
                                         source={'kind': kind, 'symbols': symbols, 'package': package},
                                         excludes=tuple(meta.get('excluded_prefixes', ())))
    rec['artifact'] = block
    write_atomic(history, format_history(meta, records))
    total = sum(block[k] for k in KEYS)
    log('release %d: artifact at %s, %d lines, Rust %.2f%%, %d paths' % (
        v, block['sha'][:12], total, 100.0 * block['rust'] / max(total, 1), block['source']['paths']))
    return block


def resolve_excludes(a, parser):
    if a.no_exclude:
        return ()
    if a.exclude is None:
        return DEFAULT_EXCLUDES
    if any(not e for e in a.exclude):
        parser.error("--exclude '' would exclude every path; use --no-exclude to count everything")
    return tuple(a.exclude)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', metavar='COMMAND')
    sub.required = True

    def add_excludes(p):
        g = p.add_mutually_exclusive_group()
        g.add_argument('--exclude', action='append', default=None, metavar='PREFIX',
                       help='skip paths under PREFIX; repeatable; replaces the default (mobile/)')
        g.add_argument('--no-exclude', action='store_true', help='count every path, including mobile/')

    p = sub.add_parser('backfill', help='count every major release tagged in REPO into a new history file')
    p.add_argument('repo')
    p.add_argument('out')
    p.add_argument('--first', type=int, default=FIRST_MAJOR, help='first major (default %(default)s)')
    p.add_argument('--streams', type=int, default=4, help='parallel blob fetches (default %(default)s)')
    add_excludes(p)

    p = sub.add_parser('append', help='add missing majors to HISTORY (lists remote tags, fetches each at depth 1)')
    p.add_argument('history')
    p.add_argument('--repo', required=True, help='checkout to fetch into and count in')
    p.add_argument('--remote', default='origin')

    p = sub.add_parser('head', help='count HEAD of REPO and print the record')
    p.add_argument('repo')
    p.add_argument('--out', help='write the record here instead of stdout')
    add_excludes(p)

    p = sub.add_parser('build-site', help='write OUT/data.json from HISTORY and the head of REPO')
    p.add_argument('history')
    p.add_argument('--repo', required=True)
    p.add_argument('--out', required=True, help='output directory (e.g. build)')
    p.add_argument('--with-artifact', action='store_true',
                   help='also compute head.artifact (null, not an error, when it cannot be computed)')
    p.add_argument('--artifact-index', metavar='NS',
                   help='Taskcluster index namespace of the head build (default: mozilla-central linux64-opt)')
    p.add_argument('--artifact-deadline', type=float, metavar='SECONDS',
                   help='time limit for the head artifact (default: dev/artifact.py\'s, 20 minutes)')

    p = sub.add_parser('set-artifact', help='store the browser artifact of release V, computed from its build')
    p.add_argument('history')
    p.add_argument('--v', type=int, required=True, help='major release number')
    p.add_argument('--symbols', required=True, help='URL of the build\'s crashreporter-symbols.zip')
    p.add_argument('--package', required=True, help='URL of the build\'s package (.tar.xz or .tar.bz2)')
    p.add_argument('--repo', required=True, help='a clone of mozilla-firefox/firefox (only read)')
    p.add_argument('--kind', default='candidates', help='source.kind to store (default %(default)s)')

    a = ap.parse_args(argv)
    try:
        run(a, ap)
    except HistoryError as e:
        ap.exit(1, '%s: error: %s\n' % (ap.prog, e))
    except Exception as e:
        if a.cmd == 'set-artifact' and isinstance(e, _artifact_module().ArtifactUnavailable):
            log('artifact unavailable: %s; %s left unchanged' % (e, a.history))
            return EXIT_UNAVAILABLE
        raise
    return 0


def run(a, ap):
    if a.cmd == 'backfill':
        backfill(a.repo, a.out, resolve_excludes(a, ap), a.first, a.streams)
    elif a.cmd == 'append':
        append(a.history, a.repo, a.remote)
    elif a.cmd == 'head':
        text = dumps(count_release(a.repo, 'HEAD', resolve_excludes(a, ap))) + '\n'
        if a.out:
            write_atomic(a.out, text)
        else:
            sys.stdout.write(text)
    elif a.cmd == 'build-site':
        build_site(a.history, a.repo, a.out, with_artifact=a.with_artifact, artifact_index=a.artifact_index,
                   artifact_deadline=a.artifact_deadline)
    elif a.cmd == 'set-artifact':
        set_artifact(a.history, a.v, a.symbols, a.package, a.repo, a.kind)


if __name__ == '__main__':
    # dev/artifact.py imports `history`: let it get this module, not a second copy (one HistoryError class)
    sys.modules.setdefault('history', sys.modules[__name__])
    sys.exit(main())
