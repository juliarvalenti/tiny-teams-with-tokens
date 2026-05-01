"""Tiny CLI for local dev tasks: `ttt init-data`."""

import sys

from ttt.db import init_db
from ttt.reports.repo import init_store


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in {"-h", "--help"}:
        print("usage: ttt <command>\n\ncommands:\n  init-data   create local sqlite db and wiki cache dir")
        return 0
    cmd = args[0]
    if cmd == "init-data":
        init_db()
        init_store()
        print("initialized: data/ttt.db and data/wiki/")
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
