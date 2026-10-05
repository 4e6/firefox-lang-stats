# stream a release tarball, stop after libxul.so's ELF build-id; report compressed bytes consumed
import sys, tarfile, struct, urllib.request, lzma, bz2, io, time
url = sys.argv[1]; t=time.time()
class Counting(io.RawIOBase):
    def __init__(s, r): s.r=r; s.n=0
    def readable(s): return True
    def readinto(s, b):
        d = s.r.read(len(b)); s.n += len(d); b[:len(d)] = d; return len(d)
raw = Counting(urllib.request.urlopen(url, timeout=120))
dec = lzma.LZMAFile(io.BufferedReader(raw)) if url.endswith('.xz') else bz2.BZ2File(io.BufferedReader(raw))
tf = tarfile.open(fileobj=dec, mode='r|')
order = []
for m in tf:
    order.append(m.name)
    if m.name.endswith('/libxul.so'):
        f = tf.extractfile(m); data = f.read(1<<20)
        # parse ELF64 section headers is far; use program headers PT_NOTE
        e_phoff, = struct.unpack('<Q', data[32:40]); e_phentsize, e_phnum = struct.unpack('<HH', data[54:58])
        bid = None
        for i in range(e_phnum):
            p = data[e_phoff+i*e_phentsize: e_phoff+(i+1)*e_phentsize]
            typ, = struct.unpack('<I', p[:4]); off, = struct.unpack('<Q', p[8:16]); sz, = struct.unpack('<Q', p[32:40])
            if typ == 4:
                q = off
                while q < off+sz:
                    nsz, dsz, nt = struct.unpack('<III', data[q:q+12]); name = data[q+12:q+12+nsz]
                    dstart = q+12+((nsz+3)&~3); desc = data[dstart:dstart+dsz]
                    if nt == 3 and name.startswith(b'GNU'): bid = desc
                    q = dstart+((dsz+3)&~3)
        g = bid[:16]; did = (g[3::-1]+g[5:3:-1]+g[7:5:-1]+g[8:16]).hex().upper()+'0'
        print('member#', len(order), m.name, 'size', m.size); print('CODE_ID', bid.hex().upper()); print('DEBUG_ID', did)
        break
print('compressed bytes read', raw.n, 'secs', round(time.time()-t,1))
print('members before libxul:', len(order)-1, 'omni.ja seen:', [o for o in order if o.endswith('omni.ja')])
