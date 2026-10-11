The sitting-date filter works, but 199 records drop to 196 unique ones, so I'll need to handle that paging issue. Next, I'll compare the ITM-012 debate against the HTML page.

Paging without text works reliably (199 unique IDs), but paging with text causes duplicates, so I'll grab the IDs first and fetch any missing ones individually. Since curl gets blocked, I'll check the reference page directly in the browser instead.

The page has loaded. I'm pulling its text out so I can compare it with the API.

The HTML page's 10 interventions match the 10 API records, so now I'll check if Python can fetch the HTML directly to automate the comparison.

A bot challenge blocks Python, so I'll pull the per-speech text out through the browser and save it as a test fixture.

I have the HTML reference text. Next I'll check the API's original-language fragments for the same 10 speeches.

I'll use the `mul` key for multilingual speeches and the `originalLanguage` key otherwise, noting machine translations are tagged `-mtec`. Next, I'll check the other record types and the /meps endpoint.

Since group affiliation only shows on speeches made for a group, I'll pull it from the MEP's memberships on the sitting date, then check how Commissioners and other non-MEP speakers resolve.

Speakers who aren't MEPs (Várhelyi) return 404 from /meps, so I'll fall back to the name in the XML. Next I'm checking single-speech lookup, which I'll use to fill the gaps left by paging.

I've settled on a design: paginate speech IDs, batch-fetch text with gap-filling, select original-language fragments, and enrich speakers via /meps and /corporate-bodies with caching and rate limiting. Now scaffolding the uv project.

Next I'm creating the test fixtures: the raw API records for ITM-012, and the HTML reference text taken from the browser.

The page's security policy blocks posting to localhost. Instead I'll write the fixture from the extracted text, then check it against SHA-256 hashes computed in the browser to rule out copy errors.

The fixture matches the live page exactly; all 10 hashes agree. Next I'm writing the tests, then the implementation.

Now the offline tests, which compare the API fixture with the HTML reference:

The tests fail as expected. Now the parser and the language-code table:

All 7 offline tests pass, confirming the API's original-language text matches the HTML page for every speaker in ITM-012. Next I'll build out the API client (rate limiter, logging, retries, cache), MEP enrichment, the day builder, and the CLI.

The output looks right: ITM-012 is enriched correctly (Kopacz, Halicki with PPE and KO, and so on). One inspection line was buggy, so I'm re-running the rest:

Nine records have empty text. Investigating:

Blue-card exchanges use `<question>`/`<answer>` elements instead of `<speech>`. I'll add a failing test for that, then generalize the parser.

Now updating the parser to handle every statement type under `<oralStatements>`:

Live tests next: these call the real API for the spec date.

All 13 tests pass, including the live check of ITM-012 against the HTML. I'll rebuild the data file, then cross-check the whole day against the full-day HTML page.

The full-day HTML has 185 speeches, the same as the API's 185 speech records. Now I'll check that the speaker order matches one-for-one:

The whole day matches too: all 185 speeches appear in the HTML in the same order as in the API. Now I'm testing range mode:

The 2026-10-06 file has exactly 500 interventions, the same as my page size, which is suspicious. Checking:

I hit a 429 rate limit from my own rapid test/CLI runs (500+ requests in 5 minutes), but the client already handles that via Retry-After. While waiting it out, I'll check the log for 500 errors.

Found a bug—the second ID page (offset 500) returned only duplicates. I'll wait out the rate-limit window, then compare `meta.total` against results from different page sizes.

The reported total of 519 doesn't match since all paging combos return the same 500 unique IDs, suggesting 19 duplicate index rows. I'll verify by comparing 2026-10-06 against its full-day HTML page to confirm nothing's missing.

I'm comparing the 2026-10-06 speech count and speaker order with its full-day HTML page.

The HTML has 481 speeches but the API returned 465, so I'll align the two lists to find the 16 missing ones.

Found two issues for 2026-10-06: sub-item sorting (easy fix) and a bigger problem where duplicate rows in the sitting-date index push 16 real speeches out of paging range. I'll check the API's OpenAPI spec for other filter or sort options to work around this.

I'm looking for the API spec to find another way to list speeches, so the missing ones can be recovered.

There's a `sort-by` parameter. Unsorted paging is probably what makes the results unstable. I'll read the exact format, then test it.

Sorting fixes it: with `sort-by` every page is stable and all 519 records come back unique. I'll add sorting to both listing calls and fix the sub-item ordering, with a test.

Rebuilding 2026-10-06 and comparing per-item speech counts with the HTML:

Both days now match the HTML exactly (481/481 on 10-06, 185/185 on 10-05) with no empty texts. Next I'll rebuild 10-05 with sorted paging, then add the README, .gitignore, and folder placeholders.

I'll run the full test suite one last time, including the live tests:

The CLI is built and tested on 2026-10-05: the text it gets from the API matches the verbatim web page. All 14 tests pass, 5 of which call the live API.

```bash
uv run eu-verbatim 2026-10-05
```
```bash
uv run eu-verbatim --from 2026-10-05 --to 2026-10-08
```

**Check against the web page**
- **The ITM-012 debate:** I compared the API text with the official page, paragraph by paragraph. All 10 interventions are identical, from "Przewodnicząca. – Kolejnym punktem porządku…" to "Przewodnicząca. – Zamykam debatę.". The page blocks scripts, so I copied its text into a test file through the browser and checked the copy against the live page.
- **Whole days:** on 2026-10-05 the API gives 185 speeches, the same 185 as the page, in the same speaker order. On 2026-10-06 it gives 481 out of 481, with matching counts for every agenda item.
- **No session:** 2026-10-04 (a Sunday) prints "no plenary session" and writes no file.

**Problems I found and fixed**
- **Missing speeches:** paging through a day's speeches without a sort order is unreliable. On 2026-10-06 only 500 of 519 records came back. The script now sorts by speech number, lists IDs before fetching text, and fetches any speech still missing one by one.
- **Original language:** the API returns every speech in all 24 languages, and all but the original are machine translations. The script keeps only the original. When a speaker switches language mid-speech (Halicki goes from English to Polish), the mixed-language version is used and each paragraph keeps its own language tag.
- **Blue-card exchanges:** these use a different tag in the XML and were coming out empty. They're handled now.

**Output, one file per day in `data/`:** agenda items with their titles, then each intervention with:
- the text in the original language;
- timestamps;
- the speaker's first and last name and nationality;
- the speaker's political group and national party on that date.

Commissioners who were never MEPs aren't in the /meps endpoint, so they keep the name printed in the transcript and have no nationality or group.

**Rate limit:** the API caps you at 500 requests per 5 minutes. The script stays at 480 and waits when the API says to. A day costs about 120–300 requests the first time and only a few once MEP details are cached in `.cache/`. Don't run two copies at once: I hit the cap myself while testing, because each copy counts only its own requests.

Every API request is logged in `logs/`. I also built 2026-10-06 while checking, so `data/` holds two files. Nothing is committed yet. The README covers usage, the output format and how it was checked.

Files are in `/Users/alexis/work/sciencespo/eu-verbatim`:
- [README.md](README.md)
- [cli.py](src/eu_verbatim/cli.py)
- [parse.py](src/eu_verbatim/parse.py)
- [client.py](src/eu_verbatim/client.py)
- [test_parse.py](tests/test_parse.py)
- [2026-10-05.json](data/2026-10-05.json)
