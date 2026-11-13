"""Fixed-origin, bounded, GET-only transport. Never log exception text or response bodies."""

import hashlib
import json
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, urlsplit

import httpx

from geointel.github_state.models import Source

ORIGIN = "https://api.github.com"
PREFIX = "/repos/bur5/geointel"
ROUTES = re.compile(
    r"^/repos/bur5/geointel(?:/branches/[A-Za-z0-9%._/-]+"
    r"|/pulls(?:/[1-9][0-9]*(?:/reviews)?)?"
    r"|/actions/workflows/ci\.yml|/actions/workflows/[1-9][0-9]*/runs"
    r"|/actions/runs/[1-9][0-9]*(?:/attempts/[1-9][0-9]*/jobs)?"
    r"|/check-runs/[1-9][0-9]*)?$"
)


def utcnow():
    return datetime.now(UTC)


def stamp(value):
    if value.tzinfo is None:
        raise ValueError("UTC-aware clock required")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


class CollectionError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class Reader:
    """Token scopes must be restricted by the operator; GET-only code cannot prove scopes."""

    def __init__(self, token, *, transport=None, clock=utcnow):
        self.clock = clock
        self.started = clock()
        self.mode = "mock" if transport is not None else "https-github-rest"
        self.sources = []
        self.authenticated = bool(token)
        self.client = httpx.Client(
            transport=transport,
            follow_redirects=False,
            timeout=10,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Cache-Control": "no-cache",
                "User-Agent": "geointel-readonly-collector/0.2",
            },
        )

    def close(self):
        self.client.close()

    def deadline(self):
        age = (self.clock() - self.started).total_seconds()
        if not 0 <= age <= 120:
            raise CollectionError("COLLECTION_DEADLINE_OR_CLOCK_CHANGE")

    def get(self, path, params=None):
        if not self.authenticated:
            raise CollectionError("AUTH_TOKEN_MISSING")
        if not ROUTES.fullmatch(path) or "/../" in path:
            raise CollectionError("ENDPOINT_NOT_ALLOWED")
        if len(self.sources) >= 200:
            raise CollectionError("REQUEST_BUDGET_EXHAUSTED")
        if set(params or {}) - {
            "page",
            "per_page",
            "state",
            "sort",
            "direction",
            "head_sha",
            "event",
        }:
            raise CollectionError("PARAMETER_NOT_ALLOWED")
        expected = {
            "state": "open",
            "sort": "created",
            "direction": "asc",
            "event": "pull_request",
            "per_page": 100,
        }
        for key, value in (params or {}).items():
            if key in expected and (
                type(value) is not type(expected[key]) or value != expected[key]
            ):
                raise CollectionError("PARAMETER_NOT_ALLOWED")
            if key == "page" and (type(value) is not int or not 1 <= value <= 3):
                raise CollectionError("PARAMETER_NOT_ALLOWED")
            if key == "head_sha" and (
                not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value)
            ):
                raise CollectionError("PARAMETER_NOT_ALLOWED")
        self.deadline()
        record = {
            "sequence": len(self.sources) + 1,
            "method": "GET",
            "endpoint": path,
            "page": (params or {}).get("page"),
            "query": dict(params or {}),
            "status_code": 0,
            "request_id": None,
            "server_date": None,
            "received_at": stamp(self.clock()),
            "response_sha256": None,
        }
        try:
            with self.client.stream("GET", ORIGIN + path, params=params) as response:
                record["status_code"] = response.status_code
                request_id = response.headers.get("x-github-request-id", "")
                if re.fullmatch(r"[A-Za-z0-9:_-]{1,100}", request_id):
                    record["request_id"] = request_id
                date = response.headers.get("date")
                if date:
                    server_date = parsedate_to_datetime(date)
                    record["server_date"] = stamp(server_date)
                    if abs((self.clock() - server_date).total_seconds()) > 300:
                        raise CollectionError("STALE_HTTP_RESPONSE")
                if response.status_code == 429 or (
                    response.status_code == 403
                    and (
                        response.headers.get("x-ratelimit-remaining") == "0"
                        or "retry-after" in response.headers
                    )
                ):
                    raise CollectionError("RATE_LIMITED_NO_AUTOMATIC_RETRY")
                if response.status_code != 200:
                    raise CollectionError(f"HTTP_STATUS_{response.status_code}")
                if record["server_date"] is None or record["request_id"] is None:
                    raise CollectionError("MISSING_RESPONSE_PROVENANCE")
                chunks = bytearray()
                for chunk in response.iter_bytes():
                    self.deadline()
                    chunks.extend(chunk)
                    if len(chunks) > 1024 * 1024:
                        raise CollectionError("RESPONSE_SIZE_LIMIT")
                data = json.loads(chunks)
                record["response_sha256"] = digest(data)
                return data, response.headers.get("link", "")
        except CollectionError:
            raise
        except httpx.TimeoutException:
            raise CollectionError("API_TIMEOUT") from None
        except (httpx.HTTPError, ValueError, TypeError, OverflowError):
            raise CollectionError("API_TRANSPORT_OR_JSON_ERROR") from None
        finally:
            self.sources.append(Source.model_validate(record))

    def paginated(self, path, params=None, key=None):
        values = []
        for page in range(1, 4):
            query = {**(params or {}), "per_page": 100, "page": page}
            data, link = self.get(path, query)
            batch = data.get(key) if key and isinstance(data, dict) else data
            if not isinstance(batch, list) or len(batch) > 100:
                raise CollectionError("MALFORMED_PAGE")
            values.extend(batch)
            # Never follow a response URL. Only advance our own fixed-origin numeric page.
            if link:
                parts = link.split(",")
                if not all(re.fullmatch(r'\s*<[^<>]+>; rel="[a-z]+"\s*', part) for part in parts):
                    raise CollectionError("MALFORMED_PAGINATION_LINK")
                for part in parts:
                    url = urlsplit(part.strip().split(">", 1)[0][1:])
                    if (
                        url.scheme != "https"
                        or url.netloc != "api.github.com"
                        or url.path != path
                        or url.fragment
                    ):
                        raise CollectionError("PAGINATION_SOURCE_MISMATCH")
                    if 'rel="next"' in part and parse_qs(url.query).get("page") != [str(page + 1)]:
                        raise CollectionError("PAGINATION_SEQUENCE_MISMATCH")
                has_next = any('rel="next"' in part for part in parts)
            else:
                has_next = False
            if key and isinstance(data, dict):
                total = data.get("total_count")
                if type(total) is not int or total < 0 or total < len(values):
                    raise CollectionError("MALFORMED_TOTAL_COUNT")
                if not has_next and total != len(values):
                    raise CollectionError("INCOMPLETE_PAGINATION")
            if not has_next:
                if len(batch) == 100:
                    raise CollectionError("AMBIGUOUS_FULL_PAGE")
                return values
            if not batch:
                raise CollectionError("EMPTY_PAGE_WITH_NEXT")
        raise CollectionError("PAGINATION_LIMIT")
