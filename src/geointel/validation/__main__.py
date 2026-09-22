import argparse
import json

from sqlalchemy.orm import Session

from geointel.domain.database import engine
from geointel.domain.models import Base
from geointel.validation.runner import ValidationRunner


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic offline GEOINTEL validation")
    parser.add_argument("command", choices=["run"])
    parser.add_argument("suite", choices=["five-country-v1"])
    parser.add_argument("--case", dest="case_id")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        output = ValidationRunner(session).run(args.suite, args.case_id)
    if args.as_json:
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        print(f"Suite: {output['suite']}\n")
        for case in output["cases"]:
            print(case["country"])
            for result in case["results"]:
                label = "N/A" if result["status"] == "not_applicable" else result["status"].upper()
                print(f"{label} {result['assertion']}: {result['explanation']}")
            print()
        print("Summary:")
        for status, count in output["summary"].items():
            print(f"{status}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
