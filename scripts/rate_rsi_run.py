"""Read-only v0.1 cards for an existing completed effect study."""
import argparse
import json
from pathlib import Path

from rsi_lab.review import inventory
from rsi_lab.serialization import digest
from rsi_lab.studies.authorization_study import inspect
from rsi_lab.studies.safety_rating import rate_run, markdown


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, target = args.run.resolve(), args.output.resolve()
    if target.exists() or target.is_relative_to(source):
        parser.error("Choose a new output outside the immutable run")
    before = inventory(source)
    summary = inspect(source)
    result = rate_run(source, summary["rows"])
    if inventory(source) != before:
        raise RuntimeError("Read-only rating changed completed evidence")
    result["source_inventory_sha256"] = digest(before)
    target.mkdir(parents=True)
    (target / "rating.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    (target / "report.md").write_text(markdown(result))
    print(json.dumps({"output": str(target), "api_calls": 0, "analysis": result["analysis"]}))


if __name__ == "__main__":
    main()
