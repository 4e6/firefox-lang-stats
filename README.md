# firefox-lang-stats

How much Rust in Firefox? You can see the chart [here][gh-pages].

Repository contains scripts collecting the language statistics for
[mozilla/gecko-dev] repository. Gathered data then assembled into a pie chart
`index.mustache`.

Page is updated weekly with a Travis Cron job. See the `date` meta tag for
the exact build time.

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
[gh-pages]: https://4e6.github.io/firefox-lang-stats/
