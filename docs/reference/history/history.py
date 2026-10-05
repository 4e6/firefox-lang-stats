#!/usr/bin/env python3
"""Reference implementation: language line counts per Firefox release, from a blobless clone.

Two steps, both driven by `git ls-tree` (no checkout, no working tree):

  history.py list-blobs REPO OUTDIR   write the distinct counted files of all releases, split into 4 chunk files
  history.py count REPO OUT.json      count lines per language for every release and write the history file

Run `backfill.sh` for the whole recipe. This is a prototype that produced the numbers in
docs/shipped-code-research.md; production code may restructure it, but one counter must serve the backfill, the weekly
append and the head point (see "One counter" in the doc).

Memory: per-release tree entries are NOT kept. Pass 1 collects only blob ids, pass 2 streams each tree again
(the first prototype kept everything and peaked at 8.9 GB for 111 majors).
"""
import argparse, collections, json, re, subprocess, sys, threading, time

METHOD_VERSION = 1

# extension -> language key (same set as dev/build-data, plus .mjs)
LANGS = [
    ('rust', ('.rs',)), ('c', ('.c',)), ('h', ('.h',)), ('cpp', ('.cc', '.cpp', '.cxx', '.hxx')),
    ('js', ('.jsm', '.jsx', '.js', '.mjs')), ('html', ('.htm', '.html', '.xhtml', '.xht', '.css')),
    ('py', ('.py',)), ('java', ('.java',)), ('asm', ('.asm',)),
]
EXT2LANG = {e: k for k, es in LANGS for e in es}
KEYS = [k for k, _ in LANGS]

# directory names that mark test code (any path component); see docs/reference/test-paths/README.md
TESTDIRS = {'test', 'tests', 'gtest', 'gtests', 'mochitest', 'mochitests', 'xpcshell', 'reftest', 'reftests',
            'crashtest', 'crashtests', '__tests__', 'androidTest', 'test262', 'unittests', 'googletest', 'testdata',
            'fixtures', 'browser_tests', 'jsapi-tests', 'jit-test'}
TEST_PREFIXES = ('js/src/tests/', 'js/src/jit-test/', 'js/src/jsapi-tests/', 'js/src/octane/',
                 'third_party/webkit/PerformanceTests/')


def is_test(path):
    parts = path.split('/')
    if parts[0] == 'testing' or path.startswith(TEST_PREFIXES):
        return True
    dirs = parts[:-1]
    for c in dirs:
        if c in TESTDIRS or re.search(r'[-_]tests?$', c) or re.match(r'tests?[-_]', c):
            return True
    if len(parts) > 2 and 'testing' in dirs[1:]:
        return True
    f = parts[-1]
    return path.endswith('.rs') and (f in ('tests.rs', 'test.rs') or f.endswith(('_test.rs', '_tests.rs')))


def git(repo, *args):
    return subprocess.check_output(['git', '-C', repo, *args])


def releases(repo):
    """[(major, tag)] for majors 46..newest. Uses FIREFOX_<n>_0_RELEASE, or FIREFOX_<n>_0_BUILD1 where the final tag
    is missing (release 125 has no _RELEASE tag)."""
    tags = set(git(repo, 'tag', '-l').decode().split())
    have = sorted(int(m.group(1)) for t in tags for m in [re.fullmatch(r'FIREFOX_(\d+)_0_RELEASE', t)] if m)
    out = []
    for v in range(46, max(have) + 1):
        for cand in (f'FIREFOX_{v}_0_RELEASE', f'FIREFOX_{v}_0_BUILD1'):
            if cand in tags:
                out.append((v, cand)); break
        else:
            print(f'warning: no tag for release {v}', file=sys.stderr)
    return out


def tree(repo, tag, excludes):
    """Yield (blob id, path, language) for counted files of a release, honouring excluded path prefixes."""
    out = git(repo, 'ls-tree', '-r', '-z', tag)
    for rec in out.split(b'\0'):
        if not rec:
            continue
        meta, path = rec.split(b'\t', 1)
        p = path.decode('utf8', 'replace')
        m = re.search(r'(\.[A-Za-z0-9]+)$', p)
        lang = EXT2LANG.get(m.group(1)) if m else None
        if lang and not p.startswith(excludes):
            yield meta.split()[2].decode(), p, lang


def cmd_list_blobs(a):
    need = set()
    for v, tag in releases(a.repo):
        need.update(oid for oid, _, _ in tree(a.repo, tag, tuple(a.exclude)))
    oids = sorted(need)
    print(f'{len(oids)} distinct counted files', file=sys.stderr)
    for i in range(4):
        with open(f'{a.outdir}/chunk{i}.txt', 'w') as f:
            f.write('\n'.join(oids[i::4]) + '\n')


def count_lines(repo, oids):
    p = subprocess.Popen(['git', '-C', repo, 'cat-file', '--batch'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    threading.Thread(target=lambda: (p.stdin.write(('\n'.join(oids) + '\n').encode()), p.stdin.close())).start()
    lines, missing = {}, 0
    for oid in oids:
        h = p.stdout.readline().split()
        if h[-1] == b'missing':
            lines[oid] = 0; missing += 1; continue
        size = int(h[2]); data = p.stdout.read(size); p.stdout.read(1)
        lines[oid] = data.count(b'\n')
    return lines, missing


def cmd_count(a):
    t0 = time.time(); ex = tuple(a.exclude); rel = releases(a.repo)
    need = set()
    for v, tag in rel:
        need.update(oid for oid, _, _ in tree(a.repo, tag, ex))
    lines, missing = count_lines(a.repo, sorted(need))
    print(f'counted {len(lines)} files, {missing} missing, {time.time() - t0:.0f}s', file=sys.stderr)
    if missing:
        sys.exit(f'{missing} blobs were not fetched; run the blob fetch step first')
    out = []
    for v, tag in rel:
        allc, nont = collections.Counter(), collections.Counter()
        for oid, path, lang in tree(a.repo, tag, ex):
            allc[lang] += lines[oid]
            if not is_test(path):
                nont[lang] += lines[oid]
        sha = git(a.repo, 'rev-list', '-n1', tag).decode().strip()
        date = git(a.repo, 'log', '-1', '--format=%cs', tag).decode().strip()
        out.append({'v': v, 'tag': tag, 'sha': sha, 'date': date,
                    'all': {k: allc[k] for k in KEYS}, 'nontest': {k: nont[k] for k in KEYS}, 'artifact': None})
    with open(a.out, 'w') as f:
        f.write('{"method_version":%d,"excluded_prefixes":%s,"releases":[\n' % (METHOD_VERSION, json.dumps(list(ex))))
        f.write(',\n'.join(json.dumps(r, separators=(',', ':')) for r in out))
        f.write('\n]}\n')
    print(f'wrote {len(out)} releases to {a.out}, {time.time() - t0:.0f}s', file=sys.stderr)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('list-blobs'); p.add_argument('repo'); p.add_argument('outdir')
    p.add_argument('--exclude', action='append', default=[], metavar='PREFIX', help='skip paths under PREFIX (e.g. mobile/)')
    p.set_defaults(fn=cmd_list_blobs)
    p = sub.add_parser('count'); p.add_argument('repo'); p.add_argument('out')
    p.add_argument('--exclude', action='append', default=[], metavar='PREFIX')
    p.set_defaults(fn=cmd_count)
    a = ap.parse_args(); a.fn(a)
