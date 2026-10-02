"""Opt-in, offline evaluator for the managed-production Goals metadata check."""

import argparse
import json
from pathlib import Path
import sys

# Import the pure evaluator only, never storage.database or application models.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storage.goals_schema_readiness import METADATA_SQL, evaluate_metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--print-query", action="store_true",
                      help="Print fixed metadata-only SQL; no connection is opened.")
    mode.add_argument("--production-metadata", action="store_true",
                      help="Evaluate a fresh production tool envelope from stdin.")
    args = parser.parse_args()
    if args.print_query:
        print(METADATA_SQL.strip())
        return 0
    try:
        # Metadata is tiny. Bound input; never echo malformed input or exceptions.
        raw = sys.stdin.read(65537)
        if len(raw) > 65536:
            raise ValueError("oversized input")
        snapshot = json.loads(raw)
    except (ValueError, OSError):
        print("UNAVAILABLE: invalid metadata input. Goals data is unknown, not empty.")
        return 2
    code, message = evaluate_metadata(snapshot)
    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())