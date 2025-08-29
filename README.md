# firefox-lang-stats

How much Rust in Firefox? You can see the chart [here][gh-pages].

Repository contains scripts collecting the language statistics for
[mozilla-firefox/firefox] repository. Gathered data then assembled into a pie
chart `index.mustache`.

Page is updated weekly with a Travis Cron job. See the `date` meta tag for
the exact build time.

# Build

Build json document with the language details:

```
dev/build-data ~/firefox > data.json
```

Expand mustache template:

```
mustache data.json index.mustache > index.html
```


[mozilla-firefox/firefox]: https://github.com/mozilla-firefox/firefox
[gh-pages]: https://4e6.github.io/firefox-lang-stats/
