# Symbol file lists of the expiring releases

`<version>.txt` lists the repository source files compiled into the Linux x86_64 binaries of one Firefox release: sorted
repository paths, one per line. They come from the `FILE` records of the Breakpad symbol files on the symbol server
(`symbols.mozilla.org`), which drops them about two years after the build. For these releases there is no
`crashreporter-symbols.zip` on `archive.mozilla.org`, so once the symbols expire the lists cannot be made again. See
`../../docs/reference/symbols/README.md` for the method and `../../docs/implementation-plan.md` (Task 0).

Captured 2026-10-05 with:

```sh
dev/artifact-files --raw ~/artifact-raw --out data/artifact-files 131.0.2 131.0.3 132.0 ... 143.0.4
```

For each version the tool streams `firefox-<version>.tar.{xz,bz2}` from `archive.mozilla.org/pub/firefox/releases/`,
reads the GNU build id of every ELF file in it, turns it into the symbol-server debug id (first 16 bytes as a GUID with the
first three fields byte-swapped, plus `0`), and reads only the `FILE` header of `<module>/<debug id>/<module>.sym` with
gzip range requests (a few hundred KB per module). The unfiltered headers are kept outside the repository in the raw
directory (`<raw>/<version>/<module>.files.gz` plus `manifest.json` with the tar path, build id, debug id and status of
every ELF file); `--derive-only --force` rebuilds the lists from it without the network.

## What is kept

- Kept: `hg:hg.mozilla.org/<repo>:<path>:<rev>` records (all releases here are from the hg era), as `<path>`.
- Dropped: `s3:gecko-generated-sources:` (generated code, about 3,200 records per release), other repositories
  (`git:github.com/rust-lang/rust:` Rust standard library), absolute paths (compiler, sysroot and Rust crate sources
  under `/builds/worker/fetches`, `/rust/deps`, `/cargo/registry`, glibc, and objdir files under
  `/builds/worker/workspace/obj-build`), `obj-*` and `<...>` pseudo-paths.

## Checks

- Every path of every list exists in the git tree of the release tag in `mozilla-firefox/firefox` (direct check of the
  `.txt` file against `git ls-tree -r` of the tag), and `docs/reference/symbols/checkpaths.py`, run on the raw headers,
  finds the same number of paths and 0 missing. The clone used was blobless and shallow (`--depth 1` per tag), which is
  enough: both checks only read the tag's tree.
- The hg revision in the `libxul.so` records equals the hg node of the release tag (`json-rev` on `hg-edge.mozilla.org`,
  `mozilla-release` or `mozilla-esr140`) for every release.
- checkpaths' own `symrev==hgtag` column prints `False` for most releases. That is expected: the symbol server keeps one
  file per debug id, and a module that comes out byte-identical from another build (an earlier or later point release,
  beta, ESR or the end-of-branch build) carries that build's revision. For example in 131.0.2, `libxul.so` names
  `a96578797b9a` (the 131.0.2 tag) but the codec libraries name `e69783530d6d` (the 131.0.3 tag). The paths still exist
  at the release's own tag (checked above).

## Gaps

- No release is lost: all 45 were still on the symbol server on 2026-10-05.
- Modules skipped: `crashreporter`, `glxtest` and `vaapitest` are never on the symbol server; `minidump-analyzer` is
  missing for 132.0, 132.0.1 and 132.0.2 (404, checked twice); `libonnxruntime.so` (141.0 and later) has no GNU build id
  (it is a prebuilt library), so it has no symbol-server entry to look up.
- 136.0.4 has no git tag (it was built from the hg relbranch `FIREFOX_136_0_X_RELBRANCH`, which the git repository does
  not carry), so checkpaths cannot run on it. On hg, 136.0.4 is 136.0.3 plus two commits that only modify
  `browser/config/version.txt`, `browser/config/version_display.txt`, `config/milestone.txt` and
  `ipc/chromium/src/chrome/common/ipc_channel_win.cc`; its list was checked against the 136.0.3 tree instead (0 missing),
  and its `libxul.so` revision is the 136.0.4 tag's hg node.
- There is no 140.0.1esr; the ESR releases in range are 140.0esr, 140.1.0esr, 140.2.0esr, 140.3.0esr and 140.3.1esr.

## Per release

"Skipped" are ELF files of the tarball not read: not on the symbol server unless a reason is given. "libxul rev = tag":
the hg revision in `libxul.so`'s records equals the tag's hg node (shown).

| Version | Paths | ELF files | Modules read | Skipped | `libxul.so` debug id | libxul rev = tag | checkpaths: paths / missing | Direct check: missing |
|---|---:|---:|---:|---|---|---|---|---:|
| 131.0.2 | 16,924 | 29 | 26 | crashreporter, glxtest, vaapitest | `4CF815C463F6367F0E0432563847F4FE0` | yes (`a96578797b9a`) | 16924 / 0 | 0 |
| 131.0.3 | 16,923 | 29 | 26 | crashreporter, glxtest, vaapitest | `E9E1B198822655C44939CD0B2B0435380` | yes (`e69783530d6d`) | 16923 / 0 | 0 |
| 132.0 | 16,904 | 29 | 25 | crashreporter, glxtest, minidump-analyzer, vaapitest | `B4D51E77635980016B71FF4E84771BC80` | yes (`0e15e2edd460`) | 16904 / 0 | 0 |
| 132.0.1 | 16,904 | 29 | 25 | crashreporter, glxtest, minidump-analyzer, vaapitest | `B8F8041C1BED0D36E3EB378CF36A028B0` | yes (`99c7a0bf814d`) | 16904 / 0 | 0 |
| 132.0.2 | 16,904 | 29 | 25 | crashreporter, glxtest, minidump-analyzer, vaapitest | `4DBBA12F8B7A2C4BC24F0DD5887388210` | yes (`60f8744af504`) | 16904 / 0 | 0 |
| 133.0 | 16,954 | 28 | 25 | crashreporter, glxtest, vaapitest | `FEE9C03B59A0CE2D9D079D152F6F74760` | yes (`8141aab3ba85`) | 16954 / 0 | 0 |
| 133.0.3 | 16,954 | 28 | 25 | crashreporter, glxtest, vaapitest | `5F5982ED2CE71592B49E7E2CB2F85EA90` | yes (`7ed49fe90e84`) | 16954 / 0 | 0 |
| 134.0 | 16,992 | 28 | 25 | crashreporter, glxtest, vaapitest | `A65A00EFD31093EABA21AEB71A0C8D040` | yes (`b8005f63d9eb`) | 16992 / 0 | 0 |
| 134.0.1 | 16,993 | 28 | 25 | crashreporter, glxtest, vaapitest | `F3125CD41277E9D4F9EF668FF3EB54680` | yes (`497a35d032e4`) | 16993 / 0 | 0 |
| 134.0.2 | 16,992 | 28 | 25 | crashreporter, glxtest, vaapitest | `880017EAB4D46DF36051253401AA5D370` | yes (`33bb8362cc38`) | 16992 / 0 | 0 |
| 135.0 | 17,170 | 28 | 25 | crashreporter, glxtest, vaapitest | `9232AD55B79599CEF7A9C95DA9B1C0890` | yes (`17c38d56ca55`) | 17170 / 0 | 0 |
| 135.0.1 | 17,170 | 28 | 25 | crashreporter, glxtest, vaapitest | `0544A55913938623ED3436A6B8380D7A0` | yes (`7c2ff1aa3394`) | 17170 / 0 | 0 |
| 136.0 | 17,194 | 28 | 25 | crashreporter, glxtest, vaapitest | `141D515449A1105224776C2B14000E8C0` | yes (`2da0b1797683`) | 17194 / 0 | 0 |
| 136.0.1 | 17,193 | 28 | 25 | crashreporter, glxtest, vaapitest | `58C6592D186D423FC5B03C3B0D0C3F0D0` | yes (`e7956a4db6c5`) | 17193 / 0 | 0 |
| 136.0.2 | 17,193 | 28 | 25 | crashreporter, glxtest, vaapitest | `464544A3EC60668CF6216BC3938D4D930` | yes (`b229b31b23a7`) | 17193 / 0 | 0 |
| 136.0.3 | 17,193 | 28 | 25 | crashreporter, glxtest, vaapitest | `97480F6AC0E608686C5AA2C61B84B0020` | yes (`766166837564`) | 17193 / 0 | 0 |
| 136.0.4 | 17,194 | 28 | 25 | crashreporter, glxtest, vaapitest | `521BB5B23C722B08C8A486622248324C0` | yes (`338dbe214b58`) | no git tag; see note | 0 (vs 136.0.3 tree) |
| 137.0 | 17,255 | 26 | 23 | crashreporter, glxtest, vaapitest | `620D9ADA1F0F2CDAFC186B6FE4F855F20` | yes (`618475773011`) | 17255 / 0 | 0 |
| 137.0.1 | 17,255 | 26 | 23 | crashreporter, glxtest, vaapitest | `219351246BBFE7603DB0BE6D926233C20` | yes (`6d422ce74c0a`) | 17255 / 0 | 0 |
| 137.0.2 | 17,256 | 26 | 23 | crashreporter, glxtest, vaapitest | `A6EE711BDE276F620841279EA5D8AB1C0` | yes (`5d1d0e27dc3a`) | 17256 / 0 | 0 |
| 138.0 | 17,302 | 26 | 23 | crashreporter, glxtest, vaapitest | `C0D594F59F417AA12138AEA6CA69CBB20` | yes (`c3bba5162c98`) | 17302 / 0 | 0 |
| 138.0.1 | 17,300 | 26 | 23 | crashreporter, glxtest, vaapitest | `518FB593DC25B856A0BF046A6D8510F90` | yes (`faa00cfdb8e8`) | 17300 / 0 | 0 |
| 138.0.3 | 17,300 | 26 | 23 | crashreporter, glxtest, vaapitest | `87A3DA3485D8F59B89AC5F83F2EDB4970` | yes (`e02f927a94c7`) | 17300 / 0 | 0 |
| 138.0.4 | 17,300 | 26 | 23 | crashreporter, glxtest, vaapitest | `1BBCF59B4A53235283385FCB1C431CB20` | yes (`e97029d1cfe4`) | 17300 / 0 | 0 |
| 139.0 | 17,577 | 27 | 24 | crashreporter, glxtest, vaapitest | `0534B46E9F3A1AFAF149567CAF7AC9060` | yes (`268ce4ad24a2`) | 17577 / 0 | 0 |
| 139.0.1 | 17,577 | 27 | 24 | crashreporter, glxtest, vaapitest | `5FD33226A0F97401A8DCCE88BB6DD79E0` | yes (`e7720952908c`) | 17577 / 0 | 0 |
| 139.0.4 | 17,576 | 27 | 24 | crashreporter, glxtest, vaapitest | `D7C6D4E68C3EFB05CEFFC3CC4DADCA8B0` | yes (`3825afc77e5b`) | 17576 / 0 | 0 |
| 140.0 | 17,612 | 27 | 24 | crashreporter, glxtest, vaapitest | `2C6F85F28E6A40BD969E9735A548EF560` | yes (`687d5aa108e0`) | 17612 / 0 | 0 |
| 140.0esr | 17,612 | 27 | 24 | crashreporter, glxtest, vaapitest | `271AFA665C91C45C9B00CD62933B1FD70` | yes (`c2cc55e4c6ab`) | 17612 / 0 | 0 |
| 140.0.1 | 17,612 | 27 | 24 | crashreporter, glxtest, vaapitest | `7D82EEBE82C762D42C5FEA78B6B29B210` | yes (`2d40c1dc62aa`) | 17612 / 0 | 0 |
| 140.0.2 | 17,613 | 27 | 24 | crashreporter, glxtest, vaapitest | `26B6F68C5F7FF8871E0AC526C20EFD660` | yes (`b27c61d0860f`) | 17613 / 0 | 0 |
| 140.0.4 | 17,612 | 27 | 24 | crashreporter, glxtest, vaapitest | `146892B98A1DD66264D123A18D5630620` | yes (`65c832029a47`) | 17612 / 0 | 0 |
| 140.1.0esr | 17,612 | 27 | 24 | crashreporter, glxtest, vaapitest | `B457F95CFB20D8903F4A199B79D9A4BA0` | yes (`0c53463d0e61`) | 17612 / 0 | 0 |
| 140.2.0esr | 17,614 | 27 | 24 | crashreporter, glxtest, vaapitest | `BF67099C972B817676CBA1F86A5D73FC0` | yes (`a511f36cca85`) | 17614 / 0 | 0 |
| 140.3.0esr | 17,617 | 27 | 24 | crashreporter, glxtest, vaapitest | `795DD7AF3857FEE080B25C64F8603CAA0` | yes (`21285e5fdf03`) | 17617 / 0 | 0 |
| 140.3.1esr | 17,618 | 27 | 24 | crashreporter, glxtest, vaapitest | `622940D0D6758BC73147562F1F11049E0` | yes (`0b8c16d258d0`) | 17618 / 0 | 0 |
| 141.0 | 17,803 | 28 | 24 | crashreporter, glxtest, libonnxruntime.so (no-build-id), vaapitest | `5AD192DABEC253BCA29EBF66BE04FBA70` | yes (`985915ed555f`) | 17803 / 0 | 0 |
| 141.0.2 | 17,802 | 28 | 24 | crashreporter, glxtest, libonnxruntime.so (no-build-id), vaapitest | `71CC894945C430C0F4F4EA6478792BAE0` | yes (`45460851be2c`) | 17802 / 0 | 0 |
| 141.0.3 | 17,803 | 28 | 24 | crashreporter, glxtest, libonnxruntime.so (no-build-id), vaapitest | `CBF36929234534D94F8390413B2C48F20` | yes (`f3e8f920d752`) | 17803 / 0 | 0 |
| 142.0 | 17,882 | 28 | 24 | crashreporter, glxtest, libonnxruntime.so (no-build-id), vaapitest | `9518F3AE922AF14FE119138B105356E50` | yes (`62f1dc921820`) | 17882 / 0 | 0 |
| 142.0.1 | 17,881 | 28 | 24 | crashreporter, glxtest, libonnxruntime.so (no-build-id), vaapitest | `4419C960A04A4950FF380A9B010462030` | yes (`179e4da8d58f`) | 17881 / 0 | 0 |
| 143.0 | 18,040 | 28 | 24 | crashreporter, glxtest, libonnxruntime.so (no-build-id), vaapitest | `8BCC8F884102EBC7BCECD1166487A8990` | yes (`62b30a28e7a4`) | 18040 / 0 | 0 |
| 143.0.1 | 18,041 | 28 | 24 | crashreporter, glxtest, libonnxruntime.so (no-build-id), vaapitest | `6D7F63728C46570024749AE71832DF740` | yes (`644b498d5178`) | 18041 / 0 | 0 |
| 143.0.3 | 18,041 | 28 | 24 | crashreporter, glxtest, libonnxruntime.so (no-build-id), vaapitest | `498EAA877DF182B39C882BE64CA366C50` | yes (`d4dc6995f3ff`) | 18041 / 0 | 0 |
| 143.0.4 | 18,041 | 28 | 24 | crashreporter, glxtest, libonnxruntime.so (no-build-id), vaapitest | `EDF3FA004C15CC6C6A44051571334E8D0` | yes (`08388fb6b18c`) | 18041 / 0 | 0 |
