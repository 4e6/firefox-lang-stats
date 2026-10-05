import sys, struct, zlib, urllib.request, json, time, re
BYTES=0; REQS=0
def get(url, start, end):
    global BYTES, REQS
    r = urllib.request.Request(url, headers={'Range': f'bytes={start}-{end}'})
    d = urllib.request.urlopen(r, timeout=120).read(); BYTES += len(d); REQS += 1; return d
def size(url):
    r = urllib.request.Request(url, method='HEAD'); return int(urllib.request.urlopen(r).headers['Content-Length'])
def cdir(url):
    n = size(url); tail = get(url, max(0, n-65536), n-1); base = max(0, n-65536)
    i = tail.rfind(b'PK\x05\x06'); cnt, cdsize, cdoff = struct.unpack('<HII', tail[i+10:i+20])
    j = tail.rfind(b'PK\x06\x06')
    if j >= 0: cnt, cdsize, cdoff = struct.unpack('<QQQ', tail[j+32:j+56])
    cd = get(url, cdoff, cdoff+cdsize-1); p = 0; ents = {}
    while p < len(cd) and cd[p:p+4] == b'PK\x01\x02':
        meth, = struct.unpack('<H', cd[p+10:p+12]); csz, usz = struct.unpack('<II', cd[p+20:p+28])
        nl, el, cl = struct.unpack('<HHH', cd[p+28:p+34]); off, = struct.unpack('<I', cd[p+42:p+46])
        name = cd[p+46:p+46+nl].decode('utf-8','replace'); ex = cd[p+46+nl:p+46+nl+el]
        # zip64 extra
        q = 0
        while q < len(ex):
            hid, hl = struct.unpack('<HH', ex[q:q+4])
            if hid == 1:
                vals = ex[q+4:q+4+hl]; k = 0
                if usz == 0xffffffff: usz, = struct.unpack('<Q', vals[k:k+8]); k += 8
                if csz == 0xffffffff: csz, = struct.unpack('<Q', vals[k:k+8]); k += 8
                if off == 0xffffffff: off, = struct.unpack('<Q', vals[k:k+8]); k += 8
            q += 4+hl
        ents[name] = (meth, csz, usz, off); p += 46+nl+el+cl
    return n, ents
def header(url, ent, chunk=1<<20):
    meth, csz, usz, off = ent
    lh = get(url, off, off+29); nl, el = struct.unpack('<HH', lh[26:30]); pos = off+30+nl+el; end = pos+csz
    d = zlib.decompressobj(-15) if meth == 8 else None; buf = b''; lines = []
    while pos < end:
        c = get(url, pos, min(end, pos+chunk)-1); pos += len(c)
        buf += d.decompress(c) if d else c
        *full, buf = buf.split(b'\n')
        for l in full:
            if l.startswith((b'MODULE', b'INFO', b'FILE', b'INLINE_ORIGIN')): lines.append(l.decode('utf-8','replace'))
            else: return lines
    return lines
if __name__ == '__main__':
    url = sys.argv[1]; want = sys.argv[2] if len(sys.argv) > 2 else 'libxul.so'
    t = time.time(); n, ents = cdir(url)
    syms = [k for k in ents if k.endswith('.sym')]
    print('zipsize', n, 'entries', len(ents), 'sym', len(syms))
    print('top-level modules', sorted(set(k.split('/')[0] for k in syms)))
    exts = {}
    for k,(m,c,u,o) in ents.items():
        e = k.rsplit('.',1)[-1] if '.' in k.split('/')[-1] else '(none)'; exts[e] = exts.get(e,0)+c
    print('compressed bytes by ext', exts)
    k = [k for k in syms if k.split('/')[0] == want][0]; print('entry', k, ents[k])
    lines = header(url, ents[k])
    out = sys.argv[3] if len(sys.argv) > 3 else None
    if out: open(out,'w').write('\n'.join(lines)+'\n')
    files = [l for l in lines if l.startswith('FILE')]
    print('MODULE/INFO', [l for l in lines if not l.startswith(('FILE','INLINE'))])
    print('FILE records', len(files)); 
    import collections; pref = collections.Counter()
    for l in files:
        nm = l.split(' ',2)[2]
        m = re.match(r'^(hg:[^:]+|git:[^:]+|s3:[^:]+|/[^/]+/[^/]+/[^/]+|[a-zA-Z]:\\[^\\]+\\[^\\]+|[^/]*)', nm); pref[m.group(1) if m else nm[:30]] += 1
    print('prefixes', pref.most_common(12))
    print('samples', [f.split(' ',2)[2] for f in files[:3]] + [f.split(' ',2)[2] for f in files if 'third_party/rust' in f][:2])
    print('bytes', BYTES, 'requests', REQS, 'secs', round(time.time()-t,1))
