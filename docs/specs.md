Build a dataset of all the verbatim of the plenary sessions of the EU parliament 
for instance
https://www.europarl.europa.eu/doceo/document/CRE-10-2026-10-05-ITM-012_EN.html

Using the API https://data.europarl.europa.eu/en/developer-corner/opendata-api

The /speeches endpoint returns the text with include-output=xml_fragment

output format : json in folder /data
decide how to split the json files. with a day prefix seems adequate.

json file includes all relevant content

for each MEP we need nationality, first name and last name. 
you can use 

Also use  /meps endpoint for enrichment with person ID joins to retrieve the nationality, first name and last name. 
as well as the parliamentary group of the person


I want the original language of each speaker speech 

note : There's API cap at 500 requests per 5 minutes.

write a cli script in python that takes parameters:
- a unique date 
if there was no planery sesssion on a given date, output message and do not create a json file 
- or a from_date to_date (both included )

Add the readme, .gitignore etc 
use uv 
log all interactions with API in /logs

<notes>

This is info from a previous claude chat session

What works
- Endpoint: GET https://data.europarl.europa.eu/api/v2/speeches, with include-output=xml_fragment, language-filter=mul and format=application/ld+json. Without include-output you get metadata only, no text.
- Text and speaker: each speech carries its text in the original language under recorded_in_a_realization_of[0]["api:xmlFragment"]. The XML contains the speaker name, group and paragraphs, with word-level timestamps you can strip.
- Linking to a debate: is_part_of holds the agenda item, for example eli/dl/doc/CRE-10-2026-10-05-ITM-012, the humanitarian situation in Ukraine. Filter on it to get one debate.
- Other fields: speaker ID (person/256944), group (org/ESN), original language and start time are all in the record. The person ID joins to /meps for enrichment.
- Speed: a page of 50 speeches with text takes about 6 seconds.

What doesn’t work yet
sitting-date-start and sitting-date-end seem to be ignored: paginating returned speeches from 2019–2024. The next things to test are adding parliamentary-term=10, or using /plenary-session-documents-items?parent-id=CRE-10-2026-10-05-ITM-012, which may list a debate’s speeches directly.
</notes>
