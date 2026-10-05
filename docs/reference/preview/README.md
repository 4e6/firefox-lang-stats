# Design preview

`history-designs.html` is a single self-contained page (d3 7.8.5 from cdnjs, IBM Plex from Google Fonts, data embedded as
`const D = ...`). It was published as a private artifact for review. Open it in a browser to see the intended look and
behaviour. It is a mock-up: its "Browser artifact (dummy)" series is made up.

## The four views to build, in this order

In the file they are tabs: B, D, A, C (the original tab letters are kept in the code and the file also has a tab E that
is **not** wanted).

1. **Composition** (tab B): stacked areas by language. Controls: view (All tracked files, Non-test files, Browser artifact),
   scale (Share, Lines), clicking a language in the legend isolates it. Direct labels at the right edge for bands tall
   enough; crosshair with a tooltip listing every language (share and lines) for the release under the pointer.
2. **Small multiples** (tab D): one small area-and-line chart per language, each with its own vertical scale starting at 0
   and labelled with its peak. Controls: view, scale (Share, Lines). Hovering any panel moves a shared crosshair and shows
   every language's value for that release in the panel headers.
3. **Language share** (tab A): pick a language and a scale (Share, Lines); draws three lines at once, one per view
   (non-test thick, all files thin, browser artifact dashed), with direct labels at the right edge, a crosshair and a
   tooltip. There is no view switch on this tab.
4. **Pie + scrubber** (tab C): the pie for one release with a slider and Play, a legend table with share, lines and change
   against the previous release in percentage points. Controls: view.

Every view has a "Show the data as a table" disclosure, so every value is reachable without hovering.

## Data shape used by the page (replace with `history.json`)

```js
D = { v: [46, 47, ...],                       // release numbers, ascending
      views: { all: {...}, nontest: {...}, shipped: {...} } }   // "shipped" is the browser artifact
// each view: { 'C++': [lines per release], Rust: [...], C: [...], JavaScript: [...], HTML: [...], Python: [...],
//              Java: [...], Assembly: [...], total: [...] }   // null entries mean "no data"
```

In the mock-up `C` and `C++` already contain their share of header lines (2/3 to C++, 1/3 to C). The product stores raw
`h` and applies the ratio from the file's `header_split` metadata when it builds this structure. Totals are sums over the
language columns.

## Look and feel

- Light and dark themes, from CSS tokens on `:root` with `prefers-color-scheme` and `data-theme` overrides. The page
  background is an explicit token. Colours are the validated categorical slots in fixed order: C++ blue, Rust orange, C
  aqua, JavaScript yellow, HTML/CSS magenta, Python green, Java violet, Assembly red. The 8-colour set passes the
  lightness, chroma, colour-blind separation and normal-vision checks in both themes; in light mode three colours (aqua,
  yellow, magenta) are below 3:1 against the background, which is why every chart has direct labels, a legend and a
  table view.
- IBM Plex Sans for text and IBM Plex Mono for numbers and axes. Thin marks, 1.5px surface-coloured gaps between
  stacked areas, crosshair tooltips with values first, labels second.
- Keyboard: the line charts take focus and respond to the left and right arrow keys.

## Changes needed before it can ship

1. Remove tab E (line + pie), the dummy-data banner and the "What each design needs stored" table (design notes).
2. Load the real data (`data.json` next to the page) instead of the embedded `D`; hide the Browser artifact option while no
   release has artifact data.
3. Handle `null` values in the middle of a series in all four views. Only Language share does today. Composition turns
   null into zero, Small multiples breaks the line, and the pie's "change since previous release" computes against
   nothing.
4. Show the Browser artifact as "Linux x86-64" in its label once real data exists, and drop "(dummy)".
5. Check phone width and light mode in a browser (only dark mode at desktop width was looked at). Re-render Pie and
   Small multiples on resize if needed.
6. Pin the d3 version with a subresource-integrity hash, or vendor it.
