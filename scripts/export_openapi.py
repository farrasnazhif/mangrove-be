"""Export the reviewed frontend contract; --check fails on any schema drift."""

import argparse
import json
from pathlib import Path

from app.main import app

SNAPSHOT = Path(__file__).resolve().parents[1] / "contracts" / "openapi.json"


def rendered_schema() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generated = rendered_schema()
    if args.check:
        if not SNAPSHOT.exists() or SNAPSHOT.read_text(encoding="utf-8") != generated:
            raise SystemExit(
                "OpenAPI drift: review changes, then run python -m scripts.export_openapi"
            )
        print("OpenAPI matches the reviewed contract")
    else:
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(generated, encoding="utf-8")
        print("Exported contracts/openapi.json")


if __name__ == "__main__":
    main()
