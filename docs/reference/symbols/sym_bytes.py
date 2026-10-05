# Attribute machine-code bytes in a Breakpad .sym (read from stdin) to source language via line records.
import sys, collections, os
def lang(name):
    p = name.rsplit(':',1)[0] if name.startswith('git:') else name.rstrip(':')
    pl = p.lower()
    if pl.endswith('.rs'): l='Rust'
    elif pl.endswith('.c'): l='C'
    elif pl.endswith(('.cc','.cpp','.cxx','.hxx','.hpp','.hh','.ipp','.tcc','.inl','.mm','.inc')): l='C++'
    elif pl.endswith('.h'): l='H'
    elif pl.endswith(('.s','.asm')): l='Asm'
    elif '.' not in os.path.basename(pl): l='C++'  # libstdc++ headers like <vector>
    else: l='other'
    if name.startswith('git:github.com/mozilla-firefox/firefox:'):
        path = p[len('git:github.com/mozilla-firefox/firefox:'):]
        origin = 'third_party/' if (path.startswith('third_party/') or '/third_party/' in path) else 'in-tree'
    elif name.startswith('git:github.com/rust-lang/rust:') or '/rustc' in name or name.startswith('/rust/'): origin='rust-toolchain'
    elif name.startswith('s3:gecko-generated-sources'): origin='generated'
    elif 'sysroot' in name: origin='sysroot'
    else: origin='other'
    return l, origin
files = {}; by_lang = collections.Counter(); by_origin = collections.Counter(); funcs = collections.Counter(); func_bytes = collections.Counter()
nofile = 0; cur = collections.Counter(); resolved = collections.Counter()
def flush():
    global cur
    if cur:
        h = cur.pop('H', 0)
        if cur:
            dom = max(cur, key=cur.get)
            for k,v in cur.items(): resolved[k]+=v
            resolved[dom]+=h
        else: resolved['H-only']+=h
    cur = collections.Counter()
for line in sys.stdin:
    c = line[0]
    if c in '0123456789abcdef':
        parts = line.split(' ', 4)
        if len(parts) >= 4 and parts[3].strip().isdigit() and line.count(' ')==3:
            size = int(parts[1],16); fn = int(parts[3])
            l, o = files.get(fn, ('unknown','unknown'))
            by_lang[l]+=size; by_origin[(o,l)]+=size; cur[l]+=size
        continue
    if line.startswith('FILE '):
        _, n, name = line.rstrip('\n').split(' ',2); files[int(n)] = lang(name)
    elif line.startswith('FUNC '):
        flush()
        parts = line.split(' ')
        if parts[1]=='m': parts = parts[1:]
        size = int(parts[2],16); funcs['n']+=1; func_bytes['total']+=size
        name = line.rstrip('\n').split(' ', 5 if line.startswith('FUNC m') else 4)[-1]
        # Rust v0 / legacy mangled demangled names - crude heuristic
        if '::' in name and ('<' in name or '{' in name or 'h' in name): pass
flush()
tot = sum(by_lang.values())
print('header bytes folded into dominant language of enclosing function:')
for k,v in resolved.most_common(): print(f'  {k:8s} {v:12d} {100*v/tot:5.1f}%')
print('func_bytes_total', func_bytes['total'], 'line_bytes_total', tot)
for k,v in by_lang.most_common(): print(f'  {k:8s} {v:12d} {100*v/tot:5.1f}%')
print('by origin:')
for (o,l),v in sorted(by_origin.items(), key=lambda x:-x[1])[:20]: print(f'  {o:15s} {l:6s} {v:12d} {100*v/tot:5.1f}%')
