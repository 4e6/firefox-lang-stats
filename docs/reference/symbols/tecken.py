# Reads the FILE header of a .sym on the symbol server without downloading the file (about 2 MB for libxul.so).
# usage: tecken.py https://symbols.mozilla.org/libxul.so/<DEBUG_ID>/libxul.so.sym [out.txt]
# IMPORTANT: the Accept-Encoding: gzip header is required. Without it the CDN ignores Range and answers 200 with the whole
# file already decompressed (723 MB for libxul.so of 131.0.2); with it the answer is 206 and gzip-compressed.
import sys, zlib, urllib.request, collections, re, time
url = sys.argv[1]; t=time.time(); pos=0; chunk=2<<20; d=zlib.decompressobj(31); buf=b''; lines=[]; n=0; done=False
while not done:
    r = urllib.request.Request(url, headers={'Accept-Encoding': 'gzip', 'Range': f'bytes={pos}-{pos+chunk-1}'})
    c = urllib.request.urlopen(r, timeout=120).read(); n += len(c); pos += len(c)
    buf += d.decompress(c); *full, buf = buf.split(b'\n')
    for l in full:
        if l.startswith((b'MODULE', b'INFO', b'FILE')): lines.append(l.decode('utf-8','replace'))
        else: done=True; break
    if len(c) < chunk: break
files=[l for l in lines if l.startswith('FILE')]
pref=collections.Counter(re.match(r'^(hg:[^:]+|git:[^:]+|s3:[^:]+|/[^/]+/[^/]+/[^/]+|[^/]*)', l.split(' ',2)[2]).group(1) for l in files)
print([l for l in lines if not l.startswith('FILE')]); print('FILE', len(files), pref.most_common(5)); print('sample', [f.split(' ',2)[2] for f in files if 'third_party/rust' in f][:1])
print('compressed bytes', n, 'secs', round(time.time()-t,1))
if len(sys.argv)>2: open(sys.argv[2],'w').write('\n'.join(lines)+'\n')
