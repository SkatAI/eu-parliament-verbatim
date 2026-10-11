"""HTTP client for the European Parliament Open Data API (v2).

- Sliding-window rate limiter (the API allows 500 requests per 5 minutes).
- Retries with backoff on 429 / 5xx / network errors.
- Every HTTP interaction is logged to logs/api_<timestamp>.log.
- Optional on-disk cache for slowly-changing resources (MEPs, corporate bodies).
"""

import json
import logging
import time
from collections import deque
from pathlib import Path

import httpx

BASE_URL = "https://data.europarl.europa.eu/api/v2"
JSON_LD = "application/ld+json"
# Without an explicit sort, pagination of /speeches is unstable: pages overlap and some
# records are never returned (e.g. 2026-10-06: 500 unique ids out of 519).
SORT = "number:asc"

log = logging.getLogger("eu_verbatim.api")


class RateLimiter:
    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self.calls: deque[float] = deque()

    def wait(self) -> None:
        now = time.monotonic()
        while self.calls and now - self.calls[0] >= self.period:
            self.calls.popleft()
        if len(self.calls) >= self.max_calls:
            delay = self.period - (now - self.calls[0]) + 0.1
            log.info("rate limit reached (%d calls / %ds), sleeping %.1fs", self.max_calls, self.period, delay)
            time.sleep(delay)
            return self.wait()
        self.calls.append(time.monotonic())


class ApiError(RuntimeError):
    pass


class ApiClient:
    def __init__(
        self,
        base_url: str = BASE_URL,
        max_calls: int = 480,
        period: float = 300,
        timeout: float = 180,
        retries: int = 5,
        cache_dir: Path | None = None,
    ):
        self.base_url = base_url
        self.limiter = RateLimiter(max_calls, period)
        self.retries = retries
        self.cache_dir = cache_dir
        self.http = httpx.Client(
            timeout=timeout,
            headers={"Accept": JSON_LD, "User-Agent": "eu-verbatim/0.1 (research dataset builder)"},
        )
        self.request_count = 0

    def close(self) -> None:
        self.http.close()

    def get(self, path: str, params: dict | None = None) -> dict | None:
        """GET a JSON-LD resource. Returns None on 204 (no content) or 404."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        params = {"format": JSON_LD, **(params or {})}
        for attempt in range(1, self.retries + 1):
            self.limiter.wait()
            self.request_count += 1
            started = time.monotonic()
            try:
                response = self.http.get(url, params=params)
            except httpx.HTTPError as exc:
                elapsed = time.monotonic() - started
                log.warning("GET %s params=%s -> ERROR %r (%.2fs, attempt %d)", url, params, exc, elapsed, attempt)
                time.sleep(min(60, 2**attempt))
                continue
            elapsed = time.monotonic() - started
            log.info(
                "GET %s -> %d (%d bytes, %.2fs, attempt %d)",
                response.url, response.status_code, len(response.content), elapsed, attempt,
            )
            if response.status_code in (204, 404):
                return None
            if response.status_code == 429 or response.status_code >= 500:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else min(120, 5 * 2**attempt)
                log.warning("retrying %s in %.0fs", response.url, delay)
                time.sleep(delay)
                continue
            if response.status_code != 200:
                raise ApiError(f"GET {response.url} -> {response.status_code}: {response.text[:300]}")
            if not response.content.strip():
                return None
            return response.json()
        raise ApiError(f"GET {url} failed after {self.retries} attempts")

    def get_cached(self, kind: str, identifier: str, path: str) -> dict | None:
        """GET with an on-disk JSON cache (also caches 404s as null)."""
        cache_file = self.cache_dir / kind / f"{identifier}.json" if self.cache_dir else None
        if cache_file and cache_file.exists():
            log.debug("cache hit %s/%s", kind, identifier)
            return json.loads(cache_file.read_text())
        data = self.get(path)
        if cache_file:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(data, ensure_ascii=False))
        return data

    # --- endpoints -------------------------------------------------------

    def speech_ids_for_date(self, date: str, page_size: int = 500) -> list[str]:
        """Activity ids of all records of a sitting (metadata only)."""
        ids: list[str] = []
        offset = 0
        while True:
            data = self.get(
                "speeches", {"sitting-date": date, "sort-by": SORT, "limit": page_size, "offset": offset}
            )
            batch = (data or {}).get("data", [])
            ids.extend(r["activity_id"] for r in batch)
            if len(batch) < page_size:
                return list(dict.fromkeys(ids))
            offset += page_size

    def speeches_with_text(self, date: str, page_size: int = 100) -> list[dict]:
        """All records of a sitting, with XML text fragments.

        Ids are listed first (cheap metadata pages); any record missing from the text pages
        is then fetched individually, so a paging glitch cannot silently drop a speech.
        """
        ids = self.speech_ids_for_date(date)
        if not ids:
            return []
        records: dict[str, dict] = {}
        offset = 0
        while offset < len(ids):
            data = self.get(
                "speeches",
                {
                    "sitting-date": date,
                    "sort-by": SORT,
                    "include-output": "xml_fragment",
                    "language-filter": "mul",
                    "limit": page_size,
                    "offset": offset,
                },
            )
            batch = (data or {}).get("data", [])
            for r in batch:
                records.setdefault(r["activity_id"], r)
            if len(batch) < page_size:
                break
            offset += page_size
        missing = [i for i in ids if i not in records]
        if missing:
            log.info("%s: %d records missing from paginated results, fetching individually", date, len(missing))
        for activity_id in missing:
            data = self.get(f"speeches/{activity_id}", {"include-output": "xml_fragment", "language-filter": "mul"})
            for r in (data or {}).get("data", []):
                records[r["activity_id"]] = r
        unknown = set(records) - set(ids)
        if unknown:
            log.warning("%s: ignoring %d records not listed for this date", date, len(unknown))
        return [records[i] for i in ids if i in records]

    def meetings(self, year: int, page_size: int = 500) -> list[dict]:
        """All plenary sittings of a year, held or scheduled."""
        records: dict[str, dict] = {}
        offset = 0
        while True:
            data = self.get("meetings", {"year": year, "limit": page_size, "offset": offset})
            batch = (data or {}).get("data", [])
            for r in batch:
                records.setdefault(r["activity_id"], r)
            if len(batch) < page_size:
                return list(records.values())
            offset += page_size

    def mep(self, person_id: str) -> dict | None:
        data = self.get_cached("meps", person_id, f"meps/{person_id}")
        return (data or {}).get("data", [None])[0]

    def corporate_body(self, org_id: str) -> dict | None:
        data = self.get_cached("corporate-bodies", org_id, f"corporate-bodies/{org_id}")
        return (data or {}).get("data", [None])[0]
