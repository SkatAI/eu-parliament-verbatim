# eu-verbatim

Builds a JSON dataset of the **verbatim reports (CRE) of European Parliament plenary sittings**, from the
[European Parliament Open Data API v2](https://data.europarl.europa.eu/en/developer-corner/opendata-api).

The dataset has one file per sitting day (`data/YYYY-MM-DD.json`). Each speech is in the **original language
of the speaker** and is linked to its agenda item (debate). Each speaker is enriched with first name, last name,
nationality, political group and national party.

Example source page: <https://www.europarl.europa.eu/doceo/document/CRE-10-2026-10-05-ITM-012_EN.html>

## Install

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Usage

```bash
# a single day
uv run eu-verbatim 2026-10-05

# a range of days (both included)
uv run eu-verbatim --from 2026-10-05 --to 2026-10-08
```

* Days without a plenary sitting print `no plenary session, no file written`, and no file is created.
* Days that already have a JSON file are skipped. Use `--overwrite` to rebuild them.
* Other options: `--data-dir`, `--logs-dir`, `--cache-dir`, `--no-cache` and `--max-requests` (see `--help`).

### Sitting days of a year

`eu-sittings` lists the plenary sitting days of a year, from `GET /meetings?year=YYYY`. It gives the weekday, the
location (Strasbourg or Brussels) and a status:

* `held` when the API has minutes or a verbatim record attached to the sitting;
* `scheduled` for a sitting still on the calendar.

```bash
uv run eu-sittings 2026                       # table of all sittings, held and scheduled
uv run eu-sittings 2026 --held --dates-only   # one date per line, held sittings only
uv run eu-sittings 2026 --json sittings.json  # also write the list to a JSON file
```

For 2026 (as of 2026-10-11), it lists 54 sitting days: 40 held and 14 scheduled.

### Last N sittings

`scripts/fetch_last_sessions.sh` builds the dataset for the last N held sitting days (10 by default):

```bash
scripts/fetch_last_sessions.sh            # last 10 sittings
scripts/fetch_last_sessions.sh 20         # last 20 sittings
DRY_RUN=1 scripts/fetch_last_sessions.sh  # only print the dates and commands
```

* **Dates:** they come from `eu-sittings --held --dates-only` and are cached in `.cache/sittings/<year>.txt`. The
  current year's list is refreshed after a day; past years are kept. Earlier years are added when the current year
  has fewer than N sittings.
* **API cap:** each `eu-verbatim` run rate-limits itself, but that limiter ends with the process. So after each
  day the script reads the number of API requests the run made and sleeps `requests × 300 / 450` seconds, keeping
  the pace under the cap of 500 requests per 5 minutes.
* **Cost:** a day with a cold MEP cache makes about 190 requests and is followed by a pause of about 2 minutes.
  Later days are cheaper, because MEPs are cached.
* **Progress:** a progress bar shows how many of the days to download are done, with the elapsed time. During
  each API cap pause, a second bar counts down the seconds left. When the output is not a terminal (a pipe or a log
  file), each update is printed on its own line.
* **Re-runs:** a sitting that is already in `data/<date>.json` is skipped before calling `eu-verbatim`, so it
  makes no API request and triggers no pause. The script can be re-run safely; to rebuild a day, delete its file
  or run `uv run eu-verbatim <date> --overwrite`.

## How it works

1. **Speeches.** `GET /speeches?sitting-date=D&sort-by=number:asc&include-output=xml_fragment&language-filter=mul`.
   * The ids for the day are listed first, using cheap metadata-only pages. Text pages are then fetched, and any
     record still missing is fetched individually through `GET /speeches/{id}`.
   * `sort-by` is required. Without it, pagination is unstable: on 2026-10-06 only 500 of the 519 records were
     reachable.
   * The API returns `204 No Content` when there was no sitting that day.
2. **Original language.** Each record carries its text in all languages under
   `recorded_in_a_realization_of[0]["api:xmlFragment"]`. Only the original-language version is the verbatim; the
   others are machine translations, marked `xml:lang="xx-t-yy-mtec"`.
   * The fragment under `originalLanguage` is used.
   * A speech that switches language mid-way uses the `mul` fragment instead. Each paragraph then keeps its own
     `lang`.
   * Word-level `<time>` timestamps are stripped.
3. **Speakers.** The `person/{id}` of each speech is joined to `GET /meps/{id}`:
   * `givenName` and `familyName` give the first and last name.
   * `citizenship` gives the nationality.
   * The memberships that are active on the sitting date give the `EU_POLITICAL_GROUP` and the
     `NATIONAL_POLITICAL_GROUP`.
   * Group and party labels come from `GET /corporate-bodies/{id}`.
   * People who are not in the MEP database (some Commissioners, Council representatives) keep the name found in
     the transcript.
   * MEP and organisation responses are cached in `.cache/`.
4. **Rate limit.** The API allows 500 requests per 5 minutes. The client uses a sliding-window limiter (480 per
   5 minutes by default) and retries on `429` and `5xx` errors, honouring `Retry-After`.
   * A typical sitting day costs about 120–300 requests with a cold cache, and only a handful once MEPs are cached.
   * The limiter only sees the current process, so do not run several instances in parallel.
5. **Logs.** Every HTTP request is logged to `logs/api_<timestamp>.log`, one file per run, with the URL, status,
   size, duration and attempt number.

## Output format

`data/2026-10-05.json`:

```jsonc
{
  "date": "2026-10-05",
  "parliamentary_term": 10,
  "url": "https://www.europarl.europa.eu/doceo/document/CRE-10-2026-10-05_EN.html",
  "generated_at": "2026-10-11T07:48:35+00:00",
  "source": { "api": "...", "endpoints": [...], "speeches_params": {...} },
  "stats": { "agenda_items": 19, "interventions": 199, "speakers": 115, "words": 31157 },
  "agenda_items": [
    {
      "id": "CRE-10-2026-10-05-ITM-012",
      "item_number": 12,
      "sub_item_number": null,               // e.g. 7 for CRE-...-ITM-009-07 (votes)
      "title": "Humanitarian situation in Ukraine (debate)",
      "titles": { "en": "...", "fr": "...", "pl": "...", ... },
      "url": "https://www.europarl.europa.eu/doceo/document/CRE-10-2026-10-05-ITM-012_EN.html",
      "interventions": [
        {
          "id": "MTG-PL-2026-10-05-OTH-2017097780034",
          "speech_id": "2017097780034",
          "document_id": "CRE-10-2026-10-05-OTH-2017097780034",
          "agenda_item_id": "CRE-10-2026-10-05-ITM-012",
          "number": "1-0056-0000",
          "order": 42,                         // position in the day's verbatim
          "activity_type": "PLENARY_DEBATE_SPEECH",   // or PROCEEDING_ACTIVITY, MEETING_NAME_CHAIR
          "statement_type": "speech",          // speech | question | answer (blue card) | communication
          "participation_role": "SPEAKER",     // SPEAKER | CHAIR
          "start_time": "2026-10-05T17:48:07.999+02:00",
          "end_time": "2026-10-05T17:49:56.57+02:00",
          "speaker_person_id": "256944",
          "speaker_label": "Hans Neuhoff, im Namen der ESN-Fraktion.",
          "speaker_name_in_transcript": "Hans Neuhoff",
          "speaker_role_in_transcript": "im Namen der ESN-Fraktion",
          "speaker_process_in_transcript": null,      // e.g. "blue card reply"
          "on_behalf_of_group": "ESN",          // set when speaking for a political group
          "original_languages": ["de"],
          "text_source": "de",                  // xmlFragment key used ("mul" = several languages)
          "paragraphs": [{ "lang": "de", "text": "Frau Präsidentin, ..." }],
          "text": "Frau Präsidentin, ...",          // paragraphs joined by blank lines
          "speaker": {
            "person_id": "256944",
            "in_mep_database": true,
            "is_mep_on_date": true,
            "first_name": "Hans",
            "last_name": "Neuhoff",
            "full_name": "Hans Neuhoff",
            "gender": "MALE",
            "nationality": { "code": "DEU", "name": "Germany" },
            "political_group": { "id": "7151", "label": "ESN", "name": "Sovereignists" },
            "national_party": { "id": "6802", "label": "AfD", "name": "AfD" }
          }
        }
      ]
    }
  ]
}
```

Chair announcements (`IN THE CHAIR: ...`) and procedural notes (`(The sitting was suspended)`) are kept as
interventions with `statement_type: "communication"`.

## Tests

```bash
uv run pytest -m "not live"   # offline
uv run pytest                 # also runs live tests against the API (~250 requests)
DRY_RUN=1 scripts/fetch_last_sessions.sh   # check which dates the shell script would build
```

* `tests/test_parse.py` compares the API records of `CRE-10-2026-10-05-ITM-012`, stored in `tests/fixtures/`,
  with the text of the official HTML page, also stored as a fixture. The test checks:
  * the number of interventions;
  * the speaker labels, from the first intervention (*"Przewodnicząca. – Kolejnym punktem porządku…"*) to the last
    (*"Przewodnicząca. – Zamykam debatę."*);
  * every paragraph.
* `tests/test_live.py` builds 2026-10-05 from the live API and runs the same comparison. It also checks the speaker
  enrichment, and that 2026-10-04 (a Sunday) returns no session.
* `tests/test_sittings.py` checks how `eu-sittings` reads held and scheduled sittings. A live test checks that the
  2026 list is sorted and includes the 5–8 October sitting week.

The HTML fixture was extracted with a browser, because europarl.europa.eu blocks non-browser clients.

## Validation

| Sitting    | Speeches in HTML verbatim | Speeches in dataset | Per-item counts |
|------------|---------------------------|---------------------|-----------------|
| 2026-10-05 | 185                       | 185                 | identical, same speaker order |
| 2026-10-06 | 481                       | 481                 | identical for all 29 items    |

For ITM-012 on 2026-10-05, the full text is identical to the HTML page, paragraph by paragraph.
