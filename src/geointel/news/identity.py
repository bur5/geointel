"""Conservative exact identity for reporting artifacts."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def canonicalize_article_url(value: str) -> str:
    """Normalize safe URL representation; never infer identity from headline text."""
    parts = urlsplit(value.strip())
    if parts.scheme.casefold() not in {"http", "https"} or not parts.hostname:
        raise ValueError("article URL must be absolute HTTP(S)")
    scheme, host = parts.scheme.casefold(), parts.hostname.rstrip(".").casefold()
    port = parts.port
    netloc = host if port in {None, 80 if scheme == "http" else 443} else f"{host}:{port}"
    query = [
        (key, val)
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_") and key.casefold() not in TRACKING_QUERY_KEYS
    ]
    return urlunsplit((scheme, netloc, parts.path or "/", urlencode(query), ""))
