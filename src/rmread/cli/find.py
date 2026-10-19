"""``rm-find`` — find people by surname in a RootsMagic database.

Examples::

    rm-find Tree.rmtree PlaceholderSurnameThree            # substring match on surname
    rm-find Tree.rmtree 'PlaceholderSurnameThree%'         # explicit LIKE pattern (starts-with)
    rm-find Tree.rmtree '%PlaceholderSurnameThree%'        # contains "PlaceholderSurnameThree"
    rm-find Tree.rmtree 'B_rown'         # single-char wildcard
    rm-find Tree.rmtree PlaceholderSurnameThree --given Ann_
    rm-find Tree.rmtree PlaceholderSurnameThree --exact    # literal match, no wildcards
    rm-find Tree.rmtree PlaceholderSurnameTwo --format json --limit 50
"""

from __future__ import annotations

import argparse
import sys

from .. import find_person, open_database
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
            "Surname pattern. SQL LIKE semantics, case-insensitive. "
            "Use '%%' to match any sequence, '_' to match a single "
            "character. If the pattern contains no wildcards the search "
            "is substring by default (equivalent to %%value%%). "
            "Pass --exact to disable the substring wrap."
        ),
    )
    p.add_argument(
        "--given",
        help=(
            "Optional LIKE pattern for the primary given name. Same "
            "wildcard rules as 'surname'. Substring wrap by default; "
            "pass --exact to disable."
        ),
    )
    p.add_argument(
        "--exact",
        action="store_true",
        help=(
            "Treat 'surname' and '--given' as literal patterns — do not "
            "wrap bare words in %%…%%. Use this when you want exactly "
            "the value you typed, no implicit substring search."
        ),
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


def _to_pattern(value: str, *, exact: bool) -> str:
    """Wrap ``value`` for SQL LIKE if not exact mode and no wildcards."""
    if exact:
        return value
    if "%" in value or "_" in value:
        return value
    return f"%{value}%"


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    surname_pat = _to_pattern(args.surname, exact=args.exact)
    given_pat = (
        _to_pattern(args.given, exact=args.exact)
        if args.given else None
    )

    try:
        db = open_database(args.database)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except Exception as e:                       # pragma: no cover  (any schema error)
        print(f"error: {e}", file=sys.stderr)
        return 2

    try:
        people = find_person(
            db.con,
            surname=surname_pat,
            given=given_pat,
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
            f"# surname: {surname_pat!r}"
            + (f"  given: {given_pat!r}" if given_pat else "")
            + ("  mode: exact" if args.exact else "  mode: substring-or-pattern")
            + f"\n# matches: {len(people)}\n"
        )
        print(to_text(people))
    return 0


if __name__ == "__main__":                    # pragma: no cover
    raise SystemExit(main())
