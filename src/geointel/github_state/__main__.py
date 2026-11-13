"""Read-only GitHub metadata CLI. Supply an existing read-scoped GITHUB_TOKEN via environment."""

import argparse
import json
import os
from types import SimpleNamespace

import httpx

from geointel.github_state.api import Reader, digest, utcnow
from geointel.github_state.collector import collect, compatibility, empty_snapshot
from geointel.github_state.models import Snapshot


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", action="store_true", help="print output schema without network")
    args = parser.parse_args(argv)
    if args.schema:
        print(json.dumps(Snapshot.model_json_schema(), indent=2, sort_keys=True))
        return 0
    try:
        reader = Reader(os.environ.get("GITHUB_TOKEN"))
    except (httpx.HTTPError, ValueError, TypeError, OSError):
        report = empty_snapshot(SimpleNamespace(clock=utcnow, mode="https-github-rest"))
        report.issues = ["TRANSPORT_CONFIGURATION_ERROR"]
        report.manager_v01 = compatibility(report)
        report.content_digest = digest(report.model_dump(exclude={"content_digest"}))
    else:
        try:
            report = collect(reader)
        finally:
            reader.close()
    print(json.dumps(report.model_dump(), indent=2, sort_keys=True))
    return 0 if report.observations_complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
