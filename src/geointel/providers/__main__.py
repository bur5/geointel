import argparse
import json

from geointel.providers.registry import public_capabilities


def main() -> int:
    parser = argparse.ArgumentParser(description="Secret-safe provider diagnostics")
    parser.add_argument("command", choices=("status", "capabilities", "check"))
    parser.add_argument("provider", nargs="?", choices=("UCDP", "ACLED", "VIEWS", "CAST"))
    args = parser.parse_args()
    rows = public_capabilities()
    if args.command == "check":
        if not args.provider:
            parser.error("check requires a provider")
        rows = [row for row in rows if row["provider"] == args.provider]
    print(json.dumps(rows, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
