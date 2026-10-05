# Counts files and newline-lines by type under extracted directories. Used on the unzipped contents of omni.ja and
# browser/omni.ja (both are plain stored zips) to measure the shipped JavaScript, CSS and HTML: 1,001,575 + 980,367 JS lines
# for Firefox 157. usage: omni_loc.py DIR [DIR...]
import os, sys, collections
groups = {'JavaScript': ('.js','.mjs','.jsm','.jsx','.sys.mjs'), 'CSS': ('.css',), 'HTML/XHTML': ('.html','.htm','.xhtml','.xht'),
          'FTL': ('.ftl',), 'JSON': ('.json',), 'SVG': ('.svg',), 'properties': ('.properties',), 'wasm': ('.wasm',)}
for root in sys.argv[1:]:
    tot = collections.defaultdict(lambda: [0,0,0])
    for dp, dn, fn in os.walk(root):
        for f in fn:
            p = os.path.join(dp,f)
            g = 'other'
            for k, ex in groups.items():
                if f.endswith(ex): g = k; break
            data = open(p,'rb').read()
            t = tot[g]; t[0]+=1; t[1]+=len(data); t[2]+=data.count(b'\n')
    print('==', root)
    for k,(n,b,l) in sorted(tot.items(), key=lambda x:-x[1][1]):
        print(f'{k:12s} files={n:5d} bytes={b:11d} lines={l:9d} bytes/line={b/max(l,1):.1f}')
