# firefox-lang-stats

How much Rust in Firefox? See [the chart].

Repository contains scripts collecting language statistics for
[mozilla/gecko-dev] repository. The data is saved as JSON in
[gh-pages] branch along with a pie chart, which is rendered from
`index.mustache` template. The GitHub Pages is updated by weekly
CI job, with the build time recorded in `date` meta tag.

# Build

Build json document with the language details:

```
dev/build-data ~/gecko-dev > data.json
```

Expand mustache template:

```
mustache data.json index.mustache > index.html
```


[mozilla/gecko-dev]: https://github.com/mozilla/gecko-dev
[the chart]: https://4e6.github.io/firefox-lang-stats/
[gh-pages]: https://github.com/4e6/firefox-lang-stats/tree/gh-pages
