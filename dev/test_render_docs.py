"""Tests for dev/render_docs.py (no network). Run: python3 -m unittest discover -s dev"""
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import render_docs as rd  # noqa: E402

PAGE = os.path.join(ROOT, 'site', 'index.html')
DOC = os.path.join(ROOT, 'docs', 'methodology.md')
TOKENS = '/* tokens:begin */\n:root { --bg: #fff; }\n@media (prefers-color-scheme: dark) { :root { --bg: #000; } }\n/* tokens:end */'


def body(md):
    return rd.render_body(md)[0]


class Inline(unittest.TestCase):
    def test_code_is_opaque_and_escaped(self):
        self.assertEqual(rd.inline('`FIREFOX_<n>_0_RELEASE` and `*_test.rs`'),
                         '<code>FIREFOX_&lt;n&gt;_0_RELEASE</code> and <code>*_test.rs</code>')
        self.assertEqual(rd.inline('`**not bold** [x](y)`'), '<code>**not bold** [x](y)</code>')

    def test_underscores_and_single_star_stay_literal(self):
        self.assertEqual(rd.inline('a_b_c and 2 * 3 and *x*'), 'a_b_c and 2 * 3 and *x*')

    def test_text_is_escaped(self):
        self.assertEqual(rd.inline('a & b "c" 1 < 2'), 'a &amp; b &quot;c&quot; 1 &lt; 2')

    def test_bold_and_links(self):
        self.assertEqual(rd.inline('**All files** see [the page](https://example.org/a?b=1&c=2)'),
                         '<strong>All files</strong> see <a href="https://example.org/a?b=1&amp;c=2">the page</a>')
        self.assertEqual(rd.inline('[`x`](#in-short)'), '<a href="#in-short"><code>x</code></a>')

    def test_rejects(self):
        for bad in ('an `open code span', '**unclosed bold', '[rel](docs/x.md)', 'raw <b>html</b>',
                    '[js](javascript:alert(1))'):
            with self.subTest(bad=bad), self.assertRaises(rd.RenderError):
                rd.inline(bad)


class Blocks(unittest.TestCase):
    def test_headings_paragraphs_lists(self):
        out, heads = rd.render_body('# Title\n\nOne\ntwo.\n\n## A "b"\n\n- x\n  continued\n- y\n\n1. one\n2. two\n')
        self.assertEqual(out, '<h1 id="title">Title</h1>\n<p>One two.</p>\n'
                              '<h2 id="a-b">A &quot;b&quot;</h2>\n<ul><li>x continued</li><li>y</li></ul>\n'
                              '<ol><li>one</li><li>two</li></ol>')
        self.assertEqual([(lv, i) for lv, i, _ in heads], [(1, 'title'), (2, 'a-b')])

    def test_duplicate_heading_ids(self):
        _, heads = rd.render_body('# T\n\n## X\n\n## X\n')
        self.assertEqual([i for _, i, _ in heads], ['t', 'x', 'x-2'])

    def test_table(self):
        out = body('# T\n\n| A | B |\n|---|---:|\n| `a|b` | 1 |\n| **c** | 2 |\n\nafter\n')
        self.assertIn('<div class="tw"><table><tr><th>A</th><th style="text-align:right">B</th></tr>'
                      '<tr><td><code>a|b</code></td><td style="text-align:right">1</td></tr>'
                      '<tr><td><strong>c</strong></td><td style="text-align:right">2</td></tr></table></div>', out)

    def test_fence(self):
        out = body('# T\n\n```sh\necho "<x>" && a_b\n\n*y*\n```\n')
        self.assertIn('<pre><code class="language-sh">echo &quot;&lt;x&gt;&quot; &amp;&amp; a_b\n\n*y*</code></pre>', out)

    def test_rejects(self):
        cases = {
            'no title': 'text\n',
            'second h1': '# A\n\n# B\n',
            'h4': '# A\n\n#### deep\n',
            'nested list': '# A\n\n- x\n  - y\n',
            'indented code': '# A\n\n    code\n',
            'quote': '# A\n\n> quoted\n',
            'rule': '# A\n\n---\n',
            'setext': '# A\n\nTitle\n===\n',
            'star list': '# A\n\n* x\n',
            'unterminated fence': '# A\n\n```\ncode\n',
            'cell count': '# A\n\n| a | b |\n|---|---|\n| 1 |\n',
            'bad separator': '# A\n\n| a | b |\n| x | y |\n',
            'table then text': '# A\n\n| a |\n|---|\n| 1 |\ntext\n',
            'ordered from 2': '# A\n\n2. two\n',
            'fence in list': '# A\n\n- x\n  ```\n',
        }
        for name, md in cases.items():
            with self.subTest(name), self.assertRaises(rd.RenderError):
                rd.render_body(md)

    def test_error_names_the_line(self):
        with self.assertRaisesRegex(rd.RenderError, 'line 5'):
            rd.render_body('# A\n\nok\n\n> quoted\n')

    def test_hash_inside_text_is_not_a_heading(self):
        self.assertEqual(body('# A\n\nsee pull request\n#17 for more\n'), '<h1 id="a">A</h1>\n<p>see pull request #17 for more</p>')


class Page(unittest.TestCase):
    def test_tokens(self):
        self.assertIn('--bg: #fff', rd.page_tokens('x ' + TOKENS + ' y'))
        for bad in ('no markers', TOKENS + TOKENS, TOKENS.replace('prefers-color-scheme: dark', 'x'),
                    TOKENS.replace('--bg: #fff;', '--bg: url(x);')):
            with self.subTest(bad=bad[:30]), self.assertRaises(rd.RenderError):
                rd.page_tokens(bad)

    def test_site_page_has_tokens(self):
        with open(PAGE, encoding='utf-8') as f:
            css = rd.page_tokens(f.read())
        self.assertIn('--s2:', css)
        self.assertIn(':root[data-theme="dark"]', css)

    def test_page_shell(self):
        out = rd.render_page('# Doc\n\nText.\n\n## One\n\n## Two\n', TOKENS)
        self.assertIn('<title>Methodology — How much Rust in Firefox?</title>', out)
        self.assertIn('<a href="./">← How much Rust in Firefox?</a>', out)
        self.assertIn('<nav class="toc" aria-label="Contents"><ol><li><a href="#one">One</a></li>'
                      '<li><a href="#two">Two</a></li></ol></nav>', out)
        self.assertLess(out.index('<p>Text.</p>'), out.index('<nav'))

    def test_methodology_renders(self):
        """The committed document must render: the Test step catches a construct the renderer rejects."""
        with open(DOC, encoding='utf-8') as f:
            md = f.read()
        with open(PAGE, encoding='utf-8') as f:
            page = f.read()
        out = rd.render_page(md, page)
        self.assertEqual(out, rd.render_page(md, page))                 # deterministic
        self.assertEqual(out.count('<h1'), 1)
        self.assertGreater(out.count('<table>'), 5)
        self.assertIn('<pre><code', out)
        self.assertIn('prefers-color-scheme: dark', out)
        # self-contained: no scripts, stylesheets, images or fonts from anywhere
        self.assertNotRegex(out, r'<script|<img|<link rel="stylesheet"|@import|url\(|src=')
        for href in re.findall(r'href="([^"]*)"', out):
            self.assertRegex(href, r'^(#|\./$|https://|rustacean-orig-noshadow\.ico$)', href)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            src, out = os.path.join(d, 'a.md'), os.path.join(d, 'a.html')
            with open(src, 'w') as f:
                f.write('# A\n\n**ok**\n')
            self.assertEqual(rd.main([src, '--page', PAGE, '--out', out]), 0)
            with open(out, encoding='utf-8') as f:
                self.assertIn('<strong>ok</strong>', f.read())
            with open(src, 'w') as f:
                f.write('# A\n\n> no\n')
            self.assertEqual(rd.main([src, '--page', PAGE, '--out', os.path.join(d, 'b.html')]), 1)
            self.assertFalse(os.path.exists(os.path.join(d, 'b.html')))


if __name__ == '__main__':
    unittest.main()
