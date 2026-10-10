"""``rm-find`` — find people by surname in a RootsMagic database.

Examples::

    rm-find path/to/Tree.rmtree PlaceholderSurname
    rm-find Tree.rmtree PlaceholderSurname --given PlaceholderGiven
    rm-find Tree.rmtree PlaceholderSurnameTwo --format json --limit 50
"""

from __future__ import annotations

import argparse
import sys

from .. import find_by_surname, open_database
from ..format import to_json, to_text


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rm-find",
        description=(
            "Find people whose primary surname matches a pattern in a "
            "RootsMagic (.rmtree) SQLite database. Read-only."
        ),
    )
    p.add_argument(
        "database",
        help="Path to a .rmtree file (RootsMagic SQLite database).",
    )
    p.add_argument(
        "surname",
        help=(
            "Surname pattern. Case-insensitive substring match by default; "
            "anchor with %% for prefix-only or exact-match."
        ),
    )
    p.add_argument(
        "--given",
        help="Optional substring filter on the primary given name.",
    )
    p.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap on number of rows returned.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        db = open_database(args.database)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except Exception as e:                       # pragma: no cover  (any schema error)
        print(f"error: {e}", file=sys.stderr)
        return 2

    try:
        people = find_by_surname(
            db.con,
            args.surname,
            given=args.given,
            limit=args.limit,
        )
    finally:
        db.close()

    if args.format == "json":
        print(
            to_json(
                people,
                source_path=str(args.database),
                db_version=db.version,
            )
        )
    else:
        sys.stderr.write(
            f"# source: {args.database}\n"
            f"# db version: {db.version}\n"
            f"# matches: {len(people)}\n"
        )
        print(to_text(people))
    return 0


if __name__ == "__main__":                    # pragma: no cover
    raise SystemExit(main())
