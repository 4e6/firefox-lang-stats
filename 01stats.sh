#!/bin/bash

REPODIR=${1:-.}   # default to . if first argument is not set
SCRIPTDIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
BUILDDIR=$(readlink -f "${2:-$SCRIPTDIR}")

[[ -d $BUILDDIR ]] || { echo "$BUILDDIR dir does not exist"; exit 1; }

(cd "$REPODIR" || exit

  echo "unshallow $REPODIR"
  git fetch --unshallow

  echo "writing $BUILDDIR/commits-per-day.txt"
  git log --date=short --format="%cd" --reverse --topo-order |
    uniq -c > "$BUILDDIR"/commits-per-day.txt

  echo "writing $BUILDDIR/extensions.txt"
  "$SCRIPTDIR"/dev/git-file-stats > "$BUILDDIR/extensions.txt"
)