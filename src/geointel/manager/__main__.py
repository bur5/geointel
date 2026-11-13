"""CLI: bounded explicit local input, deterministic JSON stdout, no dispatch or networking."""

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from geointel.manager.engine import blocked, digest, plan
from geointel.manager.models import Plan, PlanningInput

MAX_INPUT_BYTES = 1024 * 1024


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def reject_constant(_value):
    raise ValueError("non-finite number")


def load_input(name: str):
    if name == "-":
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    else:
        path = Path(name)
        if path.suffix != ".json" or path.is_symlink() or not path.is_file():
            raise ValueError("explicit regular JSON snapshot only")
        with path.open("rb") as stream:
            raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("input too large")
    return json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    planning = commands.add_parser("plan", help="emit advisory plan; never execute")
    planning.add_argument("input", help="regular .json snapshot file, or - for stdin")
    planning.add_argument("--expected-snapshot-sha256", help="trusted out-of-band snapshot digest")
    hashing = commands.add_parser("snapshot-digest", help="inspect digest; establishes no trust")
    hashing.add_argument("input")
    schema = commands.add_parser("schema", help="emit generated input/output JSON Schema")
    schema.add_argument("kind", choices=["input", "output"])
    args = parser.parse_args(argv)
    if args.command == "schema":
        model = PlanningInput if args.kind == "input" else Plan
        result = model.model_json_schema()
        code = 0
    else:
        try:
            data = load_input(args.input)
            if args.command == "snapshot-digest":
                validated = PlanningInput.model_validate(data)
                result = {
                    "snapshot_sha256": digest(validated.snapshot.model_dump()),
                    "trust_established": False,
                }
                code = 0
            else:
                output = plan(data, args.expected_snapshot_sha256)
                result = output.model_dump()
                code = 0 if output.state == "CONTRACT_PROPOSED" else 2
        except (OSError, ValueError, TypeError, RecursionError, ValidationError):
            result = blocked("INVALID_INPUT").model_dump()
            code = 2
    print(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
