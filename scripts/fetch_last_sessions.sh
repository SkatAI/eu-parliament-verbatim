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

# Progress bar: bar <done> <total> <label>
# On a terminal the line is redrawn in place; otherwise (log file, pipe) one line per update.
BAR_WIDTH=30
bar() {
    local done="$1" total="$2" label="$3"
    local filled=$(( done * BAR_WIDTH / total ))
    local hashes dashes
    hashes="$(printf '%*s' "$filled" '' | tr ' ' '#')"
    dashes="$(printf '%*s' $(( BAR_WIDTH - filled )) '' | tr ' ' '-')"
    if [[ -t 1 ]]; then
        printf '\r\033[K[%s%s] %3d%%  %s' "$hashes" "$dashes" $(( done * 100 / total )) "$label"
    else
        printf '[%s%s] %3d%%  %s\n' "$hashes" "$dashes" $(( done * 100 / total )) "$label"
    fi
}
end_bar() { [[ -t 1 ]] && printf '\n' || true; }

# Countdown shown while pausing for the API cap.
wait_with_bar() {
    local seconds="$1" reason="$2" s
    [[ -t 1 ]] || { echo "$reason: sleeping ${seconds}s"; sleep "$seconds"; return; }
    for (( s = 0; s < seconds; s++ )); do
        bar "$s" "$seconds" "$reason: $(( seconds - s ))s left"
        sleep 1
    done
    bar "$seconds" "$seconds" "$reason: done"
    end_bar
}

total="$(printf '%s\n' $todo | grep -c .)"
count=0
started=$SECONDS
for d in $todo; do
    bar "$count" "$total" "day $((count + 1))/$total: downloading $d ..."
    end_bar
    output="$(uv run eu-verbatim "$d")"
    printf '%s\n' "$output" | sed 's/^/    /'
    count=$((count + 1))
    bar "$count" "$total" "$count/$total days downloaded ($(( (SECONDS - started) / 60 ))m$(( (SECONDS - started) % 60 ))s elapsed)"
    end_bar
    requests="$(printf '%s\n' "$output" | sed -n 's/.* \([0-9][0-9]*\) API requests.*/\1/p' | tail -1)"
    requests="${requests:-0}"
    if [[ "$d" != "$last" && "$requests" -gt 0 ]]; then
        pause=$(( (requests * CAP_WINDOW + CAP_REQUESTS - 1) / CAP_REQUESTS ))
        wait_with_bar "$pause" "API cap pause after $requests requests"
    fi
done
echo "done: $total day(s) downloaded in $(( (SECONDS - started) / 60 ))m$(( (SECONDS - started) % 60 ))s"
