#!/bin/sh
# Backfill the language history for the major Firefox releases (reference recipe, measured at 8-9 minutes and
# about 3.5 GB on a developer machine; see "History" in docs/shipped-code-research.md).
#
#   usage: backfill.sh WORKDIR OUT.json [--exclude PREFIX]...      e.g.  backfill.sh /tmp/ff history.json --exclude mobile/
#
# Steps: blobless clone with full history -> fetch the major release tags -> list the distinct counted files ->
# fetch them in 4 parallel streams -> count lines per release.
set -eu
WORK=$1; OUT=$2; shift 2
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$WORK/blobs"
cd "$WORK"
[ -d firefox ] || git clone --no-checkout --filter=blob:none --single-branch --branch main \
  https://github.com/mozilla-firefox/firefox.git firefox
# release tags are not reachable from main, so fetch them explicitly
(cd firefox && git fetch -q --filter=blob:none origin \
  '+refs/tags/FIREFOX_*_0_RELEASE:refs/tags/FIREFOX_*_0_RELEASE' \
  '+refs/tags/FIREFOX_*_0_BUILD1:refs/tags/FIREFOX_*_0_BUILD1')
python3 "$HERE/history.py" list-blobs firefox blobs "$@"
# one fetch per parallel stream; per-object lazy fetching is far slower, so always batch with --stdin
for i in 0 1 2 3; do
  (cd firefox && git -c fetch.negotiationAlgorithm=noop fetch -q origin --filter=blob:none --stdin < "../blobs/chunk$i.txt") &
done
wait
python3 "$HERE/history.py" count firefox "$OUT" "$@"
