#!/bin/bash

REPODIR=${1:-.}   # default to . if first argument is not set
SCRIPTDIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
BUILDDIR=${2:-$SCRIPTDIR}

[[ -d $BUILDDIR ]] || { echo "$BUILDDIR dir does not exist"; exit 1; }

(cd "$REPODIR" || exit

  echo "commits per day.."
  git log --date=short --format="%cd" --reverse --topo-order |
    uniq -c > "$BUILDDIR"/commits-per-day.txt

  echo "git exension stats.."
  "$SCRIPTDIR"/dev/git-file-stats > "$BUILDDIR/extensions.txt"
)
