#!/usr/bin/env python3
"""Render docs/methodology.md to a self-contained HTML page for the site (build/methodology.html).

  python3 dev/render_docs.py docs/methodology.md --page site/index.html --out build/methodology.html

Standard library only, like the rest of dev/, so the weekly job installs nothing. The renderer is strict: it
supports the Markdown subset the document uses and raises RenderError (exit status 1) on anything else, so a
construct it does not understand fails the workflow's Build step before anything is committed or deployed, instead
of being published garbled.

Supported:
  blocks   # / ## / ### headings (one # heading, first); paragraphs; "- " lists and "1. " lists, one level, with
           indented continuation lines; pipe tables with a |---|---:| separator row; ``` fenced code blocks
  inline   `code` (opaque: nothing inside is interpreted), **bold**, [text](url) with an http(s):// or #anchor url
Rejected: deeper headings, nested lists, block quotes, raw HTML, horizontal rules, setext headings, _ and single *
emphasis (left as literal characters, which keeps names like FIREFOX_<n>_0_RELEASE intact), relative links,
unbalanced backticks or **.

The colours come from the page itself: the CSS between /* tokens:begin */ and /* tokens:end */ in --page (light and
dark tokens) is copied into the output, so both pages share one palette and one dark mode. The output makes no
external requests and carries no timestamp (the same input gives the same bytes).
"""
import argparse
import html
import os
import re
import sys

TITLE = 'Methodology — How much Rust in Firefox?'
BACK = './'
TOKENS_BEGIN = '/* tokens:begin */'
TOKENS_END = '/* tokens:end */'

HEADING_RE = re.compile(r'(#{1,6})\s+(.*\S)\s*$')
UL_RE = re.compile(r'- (.*)$')
OL_RE = re.compile(r'(\d+)\. (.*)$')
FENCE_RE = re.compile(r'```([A-Za-z0-9_-]*)\s*$')
SEP_CELL_RE = re.compile(r':?-{3,}:?$')
INLINE_RE = re.compile(r'`([^`]*)`|\[([^\]]+)\]\(([^)\s]+)\)|\*\*')


class RenderError(ValueError):
    """The document uses Markdown this renderer does not support (with the line number)."""


def esc(s):
    return html.escape(s, quote=True)


# ---------------------------------------------------------------------------------------------------------------
# inline


def inline(text, where=''):
    """HTML of one block's text: code spans, links and bold; everything else escaped literally."""
    out, pos, bold = [], 0, False
    for m in INLINE_RE.finditer(text):
        out.append(_plain(text[pos:m.start()], where))
        pos = m.end()
        if m.group(0) == '**':
            out.append('</strong>' if bold else '<strong>')
            bold = not bold
        elif m.group(0).startswith('`'):
            out.append('<code>%s</code>' % esc(m.group(1)))
        else:
            url = m.group(3)
            if not re.match(r'(https?://|#)', url):
                raise RenderError('%s: link %r is not http(s):// or #anchor (relative links do not work on the site)'
                                  % (where, url))
            out.append('<a href="%s">%s</a>' % (esc(url), inline(m.group(2), where)))
    out.append(_plain(text[pos:], where))
    if bold:
        raise RenderError('%s: unbalanced ** in %r' % (where, text))
    return ''.join(out)


def _plain(s, where):
    if '`' in s:
        raise RenderError('%s: unbalanced backtick in %r' % (where, s))
    if re.search(r'</?[A-Za-z][^>]*>', s):
        # a raw tag would be shown escaped, which is never what the author meant: say so instead
        raise RenderError('%s: raw HTML %r; put it in `code` or rephrase' % (where, s))
    return esc(s)


def slug(text, seen):
    base = re.sub(r'[^a-z0-9]+', '-', html.unescape(re.sub(r'<[^>]+>', '', text)).lower()).strip('-') or 'section'
    s, i = base, 2
    while s in seen:
        s, i = '%s-%d' % (base, i), i + 1
    seen.add(s)
    return s


# ---------------------------------------------------------------------------------------------------------------
# blocks


def split_row(line, where):
    """Cells of a pipe-table row; a | inside a code span is not a separator."""
    s = line.strip()
    if not (s.startswith('|') and s.endswith('|')):
        raise RenderError('%s: a table row must start and end with |' % where)
    cells, cur, code = [], '', False
    for ch in s[1:-1]:
        if ch == '`':
            code = not code
        if ch == '|' and not code:
            cells.append(cur.strip())
            cur = ''
        else:
            cur += ch
    cells.append(cur.strip())
    return cells


def render_body(md):
    """(HTML of the document body, [(level, id, html)] of its headings). Raises RenderError."""
    lines = md.split('\n')
    out, heads, seen = [], [], set()
    para, lst = [], None      # lst: (tag, [item lines...]) where each item is a list of text lines
    i, n = 0, len(lines)

    def where(k):
        return 'line %d' % (k + 1)

    def flush_para():
        if para:
            out.append('<p>%s</p>' % inline(' '.join(t for _, t in para), where(para[0][0])))
            del para[:]

    def flush_list():
        nonlocal lst
        if lst:
            tag, items = lst
            out.append('<%s>%s</%s>' % (tag, ''.join(
                '<li>%s</li>' % inline(' '.join(t for _, t in it), where(it[0][0])) for it in items), tag))
            lst = None

    def flush():
        flush_para()
        flush_list()

    while i < n:
        line = lines[i]
        s = line.strip()
        if not s:
            flush()
            i += 1
            continue
        m = FENCE_RE.match(line)
        if m:
            flush()
            j = i + 1
            while j < n and lines[j].rstrip() != '```':
                j += 1
            if j >= n:
                raise RenderError('%s: unterminated ``` block' % where(i))
            cls = ' class="language-%s"' % m.group(1) if m.group(1) else ''
            out.append('<pre><code%s>%s</code></pre>' % (cls, esc('\n'.join(lines[i + 1:j]))))
            i = j + 1
            continue
        m = HEADING_RE.match(line)
        if m:
            flush()
            level = len(m.group(1))
            if level > 3:
                raise RenderError('%s: heading level %d is not supported (use #, ## or ###)' % (where(i), level))
            if level == 1 and (heads or out):
                raise RenderError('%s: only one # heading, at the top' % where(i))
            h = inline(m.group(2), where(i))
            hid = slug(h, seen)
            heads.append((level, hid, h))
            out.append('<h%d id="%s">%s</h%d>' % (level, hid, h, level))
            i += 1
            continue
        if s.startswith('|'):
            flush()
            head = split_row(line, where(i))
            if i + 1 >= n:
                raise RenderError('%s: table without a separator row' % where(i))
            sep = split_row(lines[i + 1], where(i + 1))
            if len(sep) != len(head) or not all(SEP_CELL_RE.match(c) for c in sep):
                raise RenderError('%s: bad table separator row %r' % (where(i + 1), lines[i + 1]))
            align = ['right' if c.endswith(':') and not c.startswith(':') else
                     'center' if c.startswith(':') and c.endswith(':') else None for c in sep]

            def cell(tag, text, a, k):
                st = ' style="text-align:%s"' % a if a else ''
                return '<%s%s>%s</%s>' % (tag, st, inline(text, where(k)), tag)
            rows = ['<tr>%s</tr>' % ''.join(cell('th', c, a, i) for c, a in zip(head, align))]
            j = i + 2
            while j < n and lines[j].strip().startswith('|'):
                cells = split_row(lines[j], where(j))
                if len(cells) != len(head):
                    raise RenderError('%s: %d cells, the header has %d' % (where(j), len(cells), len(head)))
                rows.append('<tr>%s</tr>' % ''.join(cell('td', c, a, j) for c, a in zip(cells, align)))
                j += 1
            if j < n and lines[j].strip():
                raise RenderError('%s: a table must be followed by a blank line' % where(j))
            out.append('<div class="tw"><table>%s</table></div>' % ''.join(rows))
            i = j
            continue
        indent = len(line) - len(line.lstrip(' '))
        if indent == 0:
            mu, mo = UL_RE.match(line), OL_RE.match(line)
            if mu or mo:
                flush_para()
                tag = 'ul' if mu else 'ol'
                if lst and lst[0] != tag:
                    flush_list()
                if not lst:
                    if mo and mo.group(1) != '1':
                        raise RenderError('%s: an ordered list must start at 1' % where(i))
                    lst = (tag, [])
                lst[1].append([(i, (mu or mo).group(mu and 1 or 2))])
                i += 1
                continue
            if re.match(r'(>|<|\*\*\*|---+\s*$|===+\s*$|\+ |\* )', line):
                raise RenderError('%s: unsupported block %r' % (where(i), line))
            flush_list()
            para.append((i, s))
            i += 1
            continue
        # an indented line: the continuation of a list item, never a nested block
        if not lst:
            raise RenderError('%s: indented line outside a list (indented code is not supported; use ```)' % where(i))
        if UL_RE.match(s) or OL_RE.match(s) or HEADING_RE.match(s) or s.startswith(('```', '|', '>')):
            raise RenderError('%s: nested blocks inside list items are not supported: %r' % (where(i), s))
        lst[1][-1].append((i, s))
        i += 1
    flush()
    if not heads or heads[0][0] != 1:
        raise RenderError('the document must start with a # heading')
    return '\n'.join(out), heads


# ---------------------------------------------------------------------------------------------------------------
# page


def page_tokens(page_html):
    """The token CSS of the site's page: the text between the tokens markers. RenderError if not exactly once."""
    if page_html.count(TOKENS_BEGIN) != 1 or page_html.count(TOKENS_END) != 1:
        raise RenderError('the page must contain %s and %s exactly once' % (TOKENS_BEGIN, TOKENS_END))
    a = page_html.index(TOKENS_BEGIN) + len(TOKENS_BEGIN)
    b = page_html.index(TOKENS_END)
    css = page_html[a:b].strip()
    if b < a or '--bg' not in css or 'prefers-color-scheme: dark' not in css:
        raise RenderError('the tokens block of the page has no --bg or no dark scheme')
    if re.search(r'url\(|@import', css):
        raise RenderError('the tokens block must not load anything')
    return css


STYLE = '''
* { box-sizing: border-box; }
html { background: var(--bg); }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--sans); font-size: 15px; line-height: 1.6;
       padding-inline: 16px; padding-block: 24px 64px; }
main { max-width: 820px; margin: 0 auto; min-width: 0; }
a { color: inherit; text-decoration-color: var(--axis); text-underline-offset: 2px; }
a:hover { text-decoration-color: currentColor; }
:focus-visible { outline: 2px solid var(--s1); outline-offset: 2px; }
.back { font-size: 13px; color: var(--ink2); margin: 0 0 16px; }
h1 { font-size: 26px; line-height: 1.15; margin: 0 0 12px; font-weight: 600; }
h2 { font-size: 19px; margin: 36px 0 8px; font-weight: 600; padding-top: 12px; border-top: 1px solid var(--hair); }
h3 { font-size: 16px; margin: 24px 0 6px; font-weight: 600; }
p, ul, ol { margin: 8px 0; color: var(--ink); }
ul, ol { padding-left: 22px; }
li { margin: 4px 0; }
strong { font-weight: 600; }
code { font-family: var(--mono); font-size: .86em; background: var(--chip); border-radius: 3px; padding: 1px 4px;
       overflow-wrap: anywhere; }
pre { background: var(--chip); border: 1px solid var(--hair); border-radius: 6px; padding: 10px 12px; overflow-x: auto;
      font-size: 12.5px; line-height: 1.5; }
pre code { background: none; padding: 0; font-size: inherit; overflow-wrap: normal; }
.tw { overflow-x: auto; margin: 10px 0; border: 1px solid var(--hair); border-radius: 6px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: left; vertical-align: top; padding: 5px 8px; border-bottom: 1px solid var(--hair);
         font-variant-numeric: tabular-nums; }
tr:last-child td { border-bottom: 0; }
th { font-weight: 500; color: var(--ink2); background: var(--chip); }
nav.toc { font-size: 13px; color: var(--ink2); border: 1px solid var(--hair); border-radius: 6px; padding: 8px 12px;
          margin: 16px 0; }
nav.toc ol { margin: 4px 0; padding-left: 20px; }
nav.toc li { margin: 1px 0; }
.foot { margin-top: 40px; border-top: 1px solid var(--hair); padding-top: 12px; font-size: 13px; color: var(--ink2); }
'''


def render_page(md, page_html, source='docs/methodology.md'):
    """The whole HTML page for document `md`, styled with the tokens of `page_html`."""
    body, heads = render_body(md)
    toc = ''.join('<li><a href="#%s">%s</a></li>' % (hid, re.sub(r'</?a[^>]*>', '', h))
                  for level, hid, h in heads if level == 2)
    nav = '<nav class="toc" aria-label="Contents"><ol>%s</ol></nav>' % toc if toc else ''
    first_h2 = body.find('<h2')
    if nav and first_h2 >= 0:
        body = body[:first_h2] + nav + '\n' + body[first_h2:]
    back = '<a href="%s">← How much Rust in Firefox?</a>' % BACK
    return '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<meta name="description" content="How the numbers on How much Rust in Firefox? are produced, and how far to trust them.">
<link rel="icon" href="rustacean-orig-noshadow.ico" type="image/x-icon">
<!-- generated from %(source)s by dev/render_docs.py; edit the Markdown, not this file -->
<style>
%(tokens)s
%(style)s
</style>
</head>
<body>
<main>
<p class="back">%(back)s</p>
%(body)s
<p class="foot">%(back)s &middot; <a href="https://github.com/4e6/firefox-lang-stats/blob/main/%(source)s">Source of this page</a></p>
</main>
</body>
</html>
''' % {'title': esc(TITLE), 'source': esc(source), 'tokens': page_tokens(page_html), 'style': STYLE.strip(),
       'back': back, 'body': body}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('src', help='the Markdown document (docs/methodology.md)')
    ap.add_argument('--page', required=True, help='the site page whose colour tokens are reused (site/index.html)')
    ap.add_argument('--out', required=True, help='the HTML file to write (build/methodology.html)')
    a = ap.parse_args(argv)
    with open(a.src, encoding='utf-8') as f:
        md = f.read()
    with open(a.page, encoding='utf-8') as f:
        page = f.read()
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        text = render_page(md, page, os.path.relpath(os.path.abspath(a.src), root).replace(os.sep, '/'))
    except RenderError as e:
        print('%s: %s: %s' % (ap.prog, a.src, e), file=sys.stderr)
        return 1
    tmp = a.out + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    os.replace(tmp, a.out)
    print('wrote %s (%d bytes)' % (a.out, len(text.encode('utf-8'))))
    return 0


if __name__ == '__main__':
    sys.exit(main())
