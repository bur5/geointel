"""Runner for the protest-history workflow (network code; parsing lives in protest_history).

    python -m geointel.risk.sources.protest_history_run carnegie <spreadsheet URL> <out.json>
    python -m geointel.risk.sources.protest_history_run label <max USD> <out.json>

``label`` with max USD 0 is a dry run: it collects candidates and prints the cost estimate
without calling the language model. A paid run stops when the spend reaches the cap.
"""

from __future__ import annotations

import json
import os
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

from geointel.risk.countries import resolve_country_name
from geointel.risk.sources import protest_history as ph

LABEL_YEARS = range(2016, 2026)
SAMPLE_SEED = 20261128  # hand-check sample (docs/protest-history.md, written before any run)


def _mass_mobilization(client: httpx.Client) -> dict:
    from geointel.risk.sources import protests

    meta = client.get(protests.DATASET).json()
    f = protests.pick_file(meta)
    text = client.get(protests.FILE.format(id=f["id"])).content.decode("utf-8", "replace")
    return protests.parse(text)


def _category(client: httpx.Client, title: str) -> tuple[list[str], list[str]]:
    pages, subcats, cont = [], [], {}
    while True:
        r = client.get(
            ph.WIKI_API,
            params={
                "action": "query",
                "list": "categorymembers",
                "cmtitle": title,
                "cmlimit": "500",
                "cmtype": "page|subcat",
                "format": "json",
                **cont,
            },
        ).json()
        for m in r.get("query", {}).get("categorymembers", []):
            (subcats if m["ns"] == 14 else pages).append(m["title"])
        if "continue" not in r:
            return pages, subcats
        cont = r["continue"]


def _extracts(client: httpx.Client, titles: list[str]) -> dict[str, str]:
    out = {}
    for i in range(0, len(titles), 20):
        r = client.get(
            ph.WIKI_API,
            params={
                "action": "query",
                "prop": "extracts",
                "exintro": "1",
                "explaintext": "1",
                "titles": "|".join(titles[i : i + 20]),
                "format": "json",
                "redirects": "1",
            },
        ).json()
        for page in r.get("query", {}).get("pages", {}).values():
            if page.get("extract"):
                out[page["title"]] = page["extract"]
    return out


def label(max_usd: float, out: Path) -> int:
    headers = {"User-Agent": "GeoIntel research (github.com/bur5/geointel)"}
    with httpx.Client(timeout=60, follow_redirects=True, headers=headers) as client:
        mm = _mass_mobilization(client)
        members: dict[int, list[str]] = {}
        for year in LABEL_YEARS:
            pages, subcats = _category(client, f"Category:{year} protests")
            for sub in subcats:
                pages += _category(client, sub)[0]
            members[year] = pages
        cands = ph.candidate_titles(members)
        texts = _extracts(client, [t for _, t in cands])
        estimate = ph.estimate_cost(texts.values())
        print(f"[protests] candidates {len(cands)}, with text {len(texts)}; estimate {estimate}")
        if max_usd <= 0:
            out.write_text(json.dumps({"dry_run": True, "estimate": estimate}))
            print("[protests] dry run: no model calls")
            return 0
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise SystemExit("ANTHROPIC_API_KEY is not set")
        spent, events = 0.0, []
        for year, title in cands:
            text = texts.get(title)
            if not text:
                continue
            if spent >= max_usd:
                print(f"[protests] stopped at the cap: {spent:.2f} USD")
                break
            r = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                json=ph.request_body(title, text),
            )
            if r.status_code != 200:
                print(f"[protests] {title}: HTTP {r.status_code}")
                continue
            body = r.json()
            usage = body.get("usage") or {}
            spent += (
                usage.get("input_tokens", 0) * ph.PRICE_IN
                + usage.get("output_tokens", 0) * ph.PRICE_OUT
            ) / 1e6
            reply = "".join(b.get("text", "") for b in body.get("content", []))
            item = ph.parse_label(reply, text, resolve_country_name)
            if item:
                events.append({**item, "title": title, "category_year": year})
    years = ph.big_years(events)
    result = {
        "source": "Wikipedia protest articles labelled by a language model",
        "built": datetime.now(UTC).date().isoformat(),
        "spent_usd": round(spent, 2),
        "last_year": max(LABEL_YEARS),
        "years": years,
        "events": events,
        "check": ph.check(years, mm["years"], mm["covered"], ph.CHECK_YEARS["label"]),
        "hand_check": {},
        "hand_sample": _sample(events),
    }
    out.write_text(json.dumps(result, ensure_ascii=False))
    print(f"[protests] spent {spent:.2f} USD; check {result['check']}")
    return 0


def _sample(events: list[dict]) -> list[dict]:
    """50 events labelled "yes" and 50 "no", fixed seed, for a hand check by another chat."""
    rng = random.Random(SAMPLE_SEED)
    yes = [e for e in events if e["big"] and e["against_government"]]
    no = [e for e in events if not (e["big"] and e["against_government"])]
    return rng.sample(yes, min(50, len(yes))) + rng.sample(no, min(50, len(no)))


def carnegie(url: str, out: Path) -> int:
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        mm = _mass_mobilization(client)
        payload = client.get(url).content
    rows = ph.rows_from_bytes(payload, url.split("?")[0])
    events = ph.carnegie_events(rows, resolve_country_name)
    years = ph.big_years(events)
    unknown = sum(1 for e in events if e["big"] is None)
    print(f"[protests] Carnegie events {len(events)}, size unknown {unknown}")
    result = {
        "source": "Carnegie Global Protest Tracker (with Carnegie's permission)",
        "built": datetime.now(UTC).date().isoformat(),
        "last_year": max((e["year"] for e in events), default=2020),
        "years": years,
        "events": events,
        "check": ph.check(years, mm["years"], mm["covered"], ph.CHECK_YEARS["carnegie"]),
        "hand_check": {},
        "hand_sample": _sample([{**e, "against_government": True} for e in events]),
    }
    out.write_text(json.dumps(result, ensure_ascii=False))
    print(f"[protests] check {result['check']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    mode, arg, out = argv if argv is not None else sys.argv[1:]
    if mode == "carnegie":
        return carnegie(arg, Path(out))
    if mode == "label":
        return label(float(arg), Path(out))
    raise SystemExit(f"unknown mode {mode}")


if __name__ == "__main__":
    raise SystemExit(main())
