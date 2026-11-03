#!/bin/sh
# Checks t3code-wal against every palette in tests/palettes.json. Needs jq and awk.

set -eu

cd "$(dirname "$0")"
tool=$PWD/../t3code-wal
work=${TMPDIR:-/tmp}/t3code-wal-test.$$
mkdir "$work"
trap 'rm -rf "$work"' EXIT

failures=0
fail() {
  printf 'FAIL %s\n' "$1"
  failures=$((failures + 1))
}

palette() {
  jq --arg name "$1" '.[$name]' palettes.json >"$work/palette.json"
}

# Every palette keeps the theme guarantees.
jq -r 'keys_unsorted[]' palettes.json >"$work/names"
cases=0
while IFS= read -r name; do
  cases=$((cases + 1))
  palette "$name"
  if ! "$tool" --colors "$work/palette.json" --stdout >"$work/theme.json"; then
    fail "$name: t3code-wal failed"
    continue
  fi
  jq -r '"appearance \(.appearance)", "seed \(.accent)", (.colors | to_entries[] | "\(.key) \(.value)")' "$work/theme.json" |
    LC_ALL=C awk -v name="$name" -f check.awk || failures=$((failures + 1))
done <"$work/names"

# Colors that already work stay exactly as pywal gave them, on any awk.
for name in purple light; do
  palette "$name"
  "$tool" --colors "$work/palette.json" --stdout | diff "expected/$name.json" - >/dev/null ||
    fail "$name: differs from expected/$name.json"
done

# Anything but a complete palette is refused, and publishes nothing.
palette purple
for edit in \
  '{}' \
  '.special = "broken"' \
  'del(.special.foreground)' \
  'del(.colors.color7)' \
  '.special.background = "#000"' \
  '.colors.color3 = "not a color"' \
  '.colors.color3 = "#aaaaaa\n"' \
  '.colors.color3 = 7'; do
  jq "$edit" "$work/palette.json" >"$work/broken.json"
  if "$tool" --colors "$work/broken.json" --themes-dir "$work/refused" 2>/dev/null; then
    fail "accepted a broken palette: $edit"
  fi
  [ ! -e "$work/refused" ] || fail "published a broken palette: $edit"
done
printf 'not json' >"$work/broken.json"
if "$tool" --colors "$work/broken.json" --themes-dir "$work/refused" 2>/dev/null; then fail 'accepted invalid JSON'; fi
if "$tool" --colors "$work/missing.json" --themes-dir "$work/refused" 2>/dev/null; then fail 'accepted a missing palette'; fi
[ ! -e "$work/refused" ] || fail 'published without a palette'
if "$tool" --unknown 2>/dev/null; then fail 'accepted an unknown flag'; fi

# Publishing leaves one regular file the server can read, and replaces the last one.
themes=$work/userdata/themes
palette purple
"$tool" --colors "$work/palette.json" --themes-dir "$themes" >/dev/null
palette light
"$tool" --colors "$work/palette.json" --themes-dir "$themes" >/dev/null
[ "$(ls -A "$themes")" = wal.json ] || fail 'publishing left more than wal.json behind'
if [ ! -f "$themes/wal.json" ] || [ -L "$themes/wal.json" ]; then fail 'wal.json is not a regular file'; fi
[ "$(wc -c <"$themes/wal.json")" -le 32768 ] || fail 'wal.json is over the 32KB server limit'
[ "$(jq -r .appearance "$themes/wal.json")" = light ] || fail 'wal.json was not replaced'

# The defaults follow the environment.
mkdir "$work/cache"
cp "$work/palette.json" "$work/cache/colors.json"
PYWAL_CACHE_DIR=$work/cache T3CODE_HOME=$work/home "$tool" >/dev/null
[ -f "$work/home/userdata/themes/wal.json" ] || fail 'ignored PYWAL_CACHE_DIR or T3CODE_HOME'

if [ "$failures" -gt 0 ]; then
  printf '%s failures\n' "$failures"
  exit 1
fi
printf 'ok: %s palettes\n' "$cases"
