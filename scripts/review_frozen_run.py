"""Convenience entry point; install this repository before running the script."""
import argparse
import json
from rsi_lab.review import review


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(review(args.run, args.output), indent=2))
