import argparse
import json

from geointel.api.app import connectors
from geointel.config import Settings
from geointel.providers.registry import public_capabilities
from geointel.providers.runtime import FailureCategory, sanitize_text


def _check_live(provider: str) -> dict:
    """Perform one explicitly requested, non-persistent, tightly bounded collection."""
    settings = Settings(
        provider_max_pages=1, provider_max_records=1, provider_max_response_bytes=1_000_000
    )
    row = next(item for item in public_capabilities(settings) if item["provider"] == provider)
    result = {
        "provider": provider,
        "mode": row["integration_mode"],
        "configured": row["configured"],
        "authentication_configured": row["authentication_configured"],
        "persisted": False,
        "alerts_created": False,
    }
    if not row["enabled"]:
        result.update(
            ok=False,
            failure_category=FailureCategory.DISABLED.value,
            message="provider is disabled",
        )
        return result
    connector = next(item for item in connectors(settings) if item.connector_name == provider)
    try:
        records = connector.collect("__GEOINTEL_CONNECTIVITY_CHECK__", 1)
        audit = getattr(connector, "last_audit", None)
        result.update(
            ok=True,
            failure_category=None,
            message="authentication, connectivity, and response schema validated",
            records_validated=min(len(records), 1),
            collection_audit=audit.public() if audit else None,
        )
    except Exception as exc:
        result.update(
            ok=False,
            failure_category=getattr(
                getattr(exc, "category", None), "value", FailureCategory.UNKNOWN.value
            ),
            message=sanitize_text(str(exc), 300),
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Secret-safe provider diagnostics")
    parser.add_argument("command", choices=("status", "capabilities", "check", "check-live"))
    parser.add_argument("provider", nargs="?", choices=("UCDP", "ACLED", "VIEWS", "CAST", "GDELT"))
    args = parser.parse_args()
    if args.command == "check-live":
        if not args.provider:
            parser.error("check-live requires a provider")
        print(json.dumps(_check_live(args.provider), indent=2, sort_keys=True))
        return 0
    rows = public_capabilities()
    if args.command == "check":
        if not args.provider:
            parser.error("check requires a provider")
        rows = [row for row in rows if row["provider"] == args.provider]
    print(json.dumps(rows, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
