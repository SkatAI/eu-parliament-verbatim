#!/usr/bin/env bash
# Build the dataset for the last N plenary sitting days that already took place.
#
#   scripts/fetch_last_sessions.sh            # last 10 sittings
#   scripts/fetch_last_sessions.sh 20         # last 20 sittings
#   DRY_RUN=1 scripts/fetch_last_sessions.sh  # only print the dates and commands
#
# Sittings already in data/<date>.json are skipped (no eu-verbatim call, no API request).
# Sitting dates come from `eu-sittings` and are cached in .cache/sittings/<year>.txt
# (refreshed after a day for the current year, kept forever for past years).
# Each eu-verbatim run rate-limits itself, but the limiter does not survive the process,
# so after each day the script sleeps in proportion to the requests that day made,
# keeping the overall pace under the API cap of 500 requests per 5 minutes.
set -euo pipefail

N="${1:-10}"
DRY_RUN="${DRY_RUN:-0}"
CAP_REQUESTS=450   # stay below the 500-request cap
CAP_WINDOW=300     # seconds (5 minutes)

cd "$(dirname "$0")/.."
CACHE_DIR=".cache/sittings"
DATA_DIR="data"
mkdir -p "$CACHE_DIR"

# Print the held sitting dates of a year, using the cache when possible.
held_dates() {
    local year="$1" cache="$CACHE_DIR/$1.txt"
    local current_year
    current_year="$(date +%Y)"
    if [[ -s "$cache" && ( "$year" -lt "$current_year" || -z "$(find "$cache" -mtime +0)" ) ]]; then
        echo "using cached sitting dates for $year ($cache)" >&2
    else
        echo "fetching sitting dates for $year" >&2
        uv run eu-sittings "$year" --held --dates-only > "$cache.tmp"
        mv "$cache.tmp" "$cache"
    fi
    cat "$cache"
}

# Collect dates going back year by year until we have N of them.
year="$(date +%Y)"
dates=""
while [[ "$(printf '%s' "$dates" | grep -c . || true)" -lt "$N" ]]; do
    dates="$(held_dates "$year")
$dates"
    year=$((year - 1))
    if [[ "$year" -lt 1979 ]]; then break; fi   # first elected Parliament
done
dates="$(printf '%s\n' "$dates" | grep . | sort -u | tail -n "$N")"

echo "last $N sitting days:" $dates

# Sittings already downloaded are not fetched again.
todo=""
for d in $dates; do
    if [[ -s "$DATA_DIR/$d.json" ]]; then
        echo "$d: already downloaded ($DATA_DIR/$d.json), skipping"
    else
        todo="$todo $d"
    fi
done
if [[ -z "$todo" ]]; then echo "nothing to fetch"; exit 0; fi
last="$(printf '%s\n' $todo | tail -1)"

[[ "$DRY_RUN" == "1" ]] && { for d in $todo; do echo "would run: uv run eu-verbatim $d"; done; exit 0; }

for d in $todo; do
    output="$(uv run eu-verbatim "$d" | tee /dev/stderr)"
    requests="$(printf '%s\n' "$output" | sed -n 's/.* \([0-9][0-9]*\) API requests.*/\1/p' | tail -1)"
    requests="${requests:-0}"
    if [[ "$d" != "$last" && "$requests" -gt 0 ]]; then
        pause=$(( (requests * CAP_WINDOW + CAP_REQUESTS - 1) / CAP_REQUESTS ))
        echo "$requests API requests -> sleeping ${pause}s to stay under the API cap"
        sleep "$pause"
    fi
done
echo "done"
