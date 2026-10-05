# Symbol-file prototypes

Tools used to find out which source files ship in a release. The end-to-end extractor built from them is
`dev/artifact-files` (Task 0 of `../../implementation-plan.md`). These scripts are the parts, each run and working during
the research.

| File | What it does |
|---|---|
| `rzip.py URL [module] [out]` | Reads a remote `.zip` (the `crashreporter-symbols.zip` on `archive.mozilla.org`) with HTTP range requests: central directory, then only the head of one `.sym` entry (`MODULE`, `INFO`, `FILE` records). About 1 MB per module for releases up to 105, 2 MB or more for later ones |
| `tecken.py URL [out]` | Same for the symbol server (`https://symbols.mozilla.org/<module>/<debug id>/<module>.sym`, gzip with range support). **Needs `Accept-Encoding: gzip`**: without it the server answers 200 with the whole file decompressed (723 MB for libxul), and the script sets it. Verified live: 18,986 FILE records for 131.0.2 in 2 MB and 1.2 s |
| `omni_loc.py DIR...` | Counts files and lines by type in extracted `omni.ja` directories: the shipped JavaScript, CSS and HTML |
| `buildid.py TARBALL_URL` | Streams a release tarball until `libxul.so` and prints its ELF build id and the symbol-server debug id (GUID byte swap plus a trailing `0`). Costs 0.5-32 MB depending on where `libxul.so` sits in the tar. Only handles `libxul.so`; the other modules need the same logic |
| `survey.sh VERSION` | Lists which `candidates/` builds of a version have a symbols zip, with sizes |
| `checkpaths.py VERSION...` | Checks that the repo paths named in saved `.sym` headers exist in the git tree of the release tag, and that the hg revision matches the tag |
| `sym_bytes.py < FILE.sym` | Attributes machine-code bytes in a full `.sym` stream to a language (used for the libxul byte share) |

## What the extractor has to do (per release)

1. Find the symbols. Versions 49-129 and 144 and later: `archive.mozilla.org/pub/firefox/candidates/<ver>-candidates/build<N>/linux-x86_64/en-US/firefox-<ver>.crashreporter-symbols.zip`
   (highest build number). Versions 131.0.2 to 143 and 140.0esr to 140.3.1esr: only the symbol server, with the debug id
   taken from the release tarball (`archive.mozilla.org/pub/firefox/releases/<ver>/linux-x86_64/en-US/firefox-<ver>.tar.{bz2,xz}`).
2. List the modules that ship: the ELF files in the release tarball (about 28 for 135.0). The zip also holds test binaries
   (109 modules in 60.0), so intersect.
3. Pick the right `libxul.so`: the zip holds two (shipped and gtest). Choose by the build id from the tarball, or by the
   variant without `gtest` file paths.
4. Read the `FILE` records of every module. Some modules are missing on the symbol server (`glxtest`, `vaapitest`,
   `crashreporter`); skip them and note it.
5. Normalise paths by era: 45-56 `hg:hg.mozilla.org/releases/mozilla-release:<path>:<12-char rev>`; 57-146 `hg:...:<path>:<rev>`
   (generated code as `s3:gecko-generated-sources:`); 147+ `git:github.com/mozilla-firefox/firefox:<path>:<sha>`. Keep
   only repository paths: drop `obj-*`, `s3:`, the Rust standard library, sysroot and compiler headers, absolute paths
   and `<...>` pseudo-paths. Check with `checkpaths.py` that the rest exist in the release tag's tree.
6. Deduplicate across modules, sort, write one path per line. This is the file that is committed for the expiring
   releases (`data/artifact-files/<version>.txt`).
7. Count lines of those paths at the release tag with the same counter as the tracked series.

Timing evidence: tarball 53-89 MB streamed in 3 s; symbol headers 1-20 MB. Whole pipeline estimated at 5-15 s of
network per release; not run end to end.
