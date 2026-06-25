from __future__ import annotations

import argparse

from .dl24 import find_candidates


def main() -> None:
    parser = argparse.ArgumentParser(description="proto-dyno utility commands")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="list serial ports and likely DL24 candidates")
    args = parser.parse_args()

    if args.command == "list":
        candidates = find_candidates()
        if not candidates:
            print("No serial ports found.")
            return
        for candidate in candidates:
            print(candidate.label())


if __name__ == "__main__":
    main()
