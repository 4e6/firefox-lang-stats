# For each version, check that the repo paths named in a saved .sym FILE header (sym_<version>.txt, written by
# rzip.py or tecken.py) exist in the git tree of that release's tag, and that the hg revision in the records is the
# tag's hg node. usage: FIREFOX_REPO=/path/to/blobless-clone python3 checkpaths.py 135.0 143.0 ...
import re, subprocess, sys, collections, json, urllib.request
import os
G=os.environ['FIREFOX_REPO']   # blobless clone with the release tags fetched (see history/backfill.sh)
tags={l.split()[1].split('/')[-1]: l.split()[0] for l in subprocess.run(['git','-C',G,'show-ref','--tags'],capture_output=True,text=True).stdout.splitlines()}
def tag(v):
    return 'FIREFOX_'+v.replace('.','_')+'_RELEASE'
for v in sys.argv[1:]:
    t=tag(v); c=tags.get(t)
    if c is None: t='FIREFOX_47_0_1_RELEASE'; c=tags[t]
    objn=[0]; paths=set(); revs=collections.Counter(); repo=None
    for l in open(f'sym_{v}.txt'):
        if not l.startswith('FILE'): continue
        if ':obj-' in l: objn[0]+=1
        nm=l.rstrip('\n').split(' ',2)[2]
        m=re.match(r'^(hg:hg\.mozilla\.org/[^:]+|git:github\.com/mozilla-firefox/firefox):(.*):([0-9a-f]+)$', nm)
        if m and not m.group(2).startswith('<') and not m.group(2).startswith('obj-'): repo=m.group(1); paths.add(m.group(2)); revs[m.group(3)]+=1
    tree=set(subprocess.run(['git','-C',G,'ls-tree','-r','--name-only',c],capture_output=True,text=True).stdout.split('\n'))
    miss=[p for p in paths if p not in tree]
    # hg tag node check
    hgok='n/a'
    if repo.startswith('hg:'):
        try:
            d=json.load(urllib.request.urlopen(f'https://hg-edge.mozilla.org/{repo[3+len("hg.mozilla.org/"):]}/json-rev/{t}',timeout=30)); node=d['node']
            hgok=all(node.startswith(r) for r in revs)
        except Exception as e: hgok=f'err {e}'
    print(v, t, c[:10], repo, 'revs', dict((r[:12],n) for r,n in revs.items()), 'symrev==hgtag', hgok, 'obj-paths', objn[0], 'paths', len(paths), 'missing_in_git_tree', len(miss), miss[:4])
