#!/bin/bash
A=https://archive.mozilla.org
ls_() { curl -s "$A$1" | grep -o 'href="[^"]*"' | sed -E 's#href="##;s#"$##'; }
v=$1
builds=$(ls_ /pub/firefox/candidates/$v-candidates/ | grep -oE 'build[0-9]+' | sort -V | uniq)
[ -z "$builds" ] && { echo "$v NO_CANDIDATES"; exit; }
out="$v"
for b in $builds; do
  f=$(ls_ /pub/firefox/candidates/$v-candidates/$b/linux-x86_64/en-US/ | grep -E 'crashreporter-symbols(-full)?\.zip$' | tr '\n' ',')
  out="$out $b:[$( [ -n "$f" ] && for x in ${f//,/ }; do echo -n "$(basename $x | sed 's/.*\.crash/crash/')=$(curl -sI $A$x | tr -d '\r' | awk -F': ' 'tolower($1)=="content-length"{print $2}') "; done)]"
done
echo "$out"
