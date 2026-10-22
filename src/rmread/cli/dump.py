"""``rm-dump`` — dump everything known about a single Person.

Examples::

    rm-dump Tree.rmtree 7
    rm-dump Tree.rmtree 7 --format json
    rm-dump Tree.rmtree 7 --no-events
"""

from __future__ import annotations

import argparse
import json
import sys

from .. import dump_person, open_database
from ..format import dump_payload


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rm-dump",
        description=(
            "Dump identity, life events, and family links for a single "
            "Person in a RootsMagic (.rmtree) SQLite database. Read-only."
        ),
    )
    p.add_argument("database", help="Path to a .rmtree file.")
    p.add_argument("person_id", type=int, help="RootsMagic PersonID to dump.")
    p.add_argument(
        "--format", choices=("text", "json"), default="text",
        help="Output format (default: text).",
    )
    p.add_argument(
        "--no-events", action="store_true",
        help="Skip the events block.",
    )
    p.add_argument(
        "--no-family", action="store_true",
        help="Skip the parents / spouses / children block.",
    )
    return p


def _dump_to_text(dump) -> str:
    p = dump.person
    lines: list[str] = []
    lines.append(f"Person {p.person_id} ({p.unique_id or 'no-uuid'})")
    lines.append(f"  Name:    {p.display_name or '(unnamed)'}")
    sex_letter = {0: "?", 1: "Male", 2: "Female"}
    lines.append(f"  Sex:     {sex_letter.get(p.sex, '?')}")
    if p.primary_name.birth_year or p.primary_name.death_year:
        b = p.primary_name.birth_year or "?"
        d = p.primary_name.death_year or ""
        lines.append(f"  Years:   {b} \u2013 {d}".rstrip(" \u2013"))
    if p.is_private:
        lines.append("  Privacy: marked private in source RM DB")

    if dump.events:
        lines.append("")
        lines.append(f"Events ({len(dump.events)}):")
        for ev in dump.events:
            primary_tag = " *" if ev.is_primary else ""
            place = f"  at {ev.place}" if ev.place else ""
            lines.append(
                f"  {ev.event_type_name}{primary_tag}: "
                f"{ev.date}{place}"
            )
            if ev.sentence and ev.sentence != (
                f"{ev.event_type_name}: {ev.date}"
            ):
                lines.append(f"      sentence: {ev.sentence}")
            if ev.details:
                lines.append(f"      details:  {ev.details}")

    if dump.parents:
        lines.append("")
        lines.append(f"Parents ({len(dump.parents)}):")
        for par in dump.parents:
            lines.append(
                f"  {par.role:<7} @{par.parent_id}  {par.parent_name}"
            )

    if dump.spouses:
        lines.append("")
        lines.append(f"Spouses ({len(dump.spouses)}):")
        for sp in dump.spouses:
            lines.append(
                f"  family {sp.family_id}  @{sp.spouse_id}  {sp.spouse_name}"
            )

    if dump.children:
        lines.append("")
        lines.append(f"Children ({len(dump.children)}):")
        for ch in dump.children:
            lines.append(
                f"  @{ch.child_id}  {ch.child_name}  (order {ch.child_order})"
            )

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.person_id < 0:
        print(f"error: person_id must be >= 0, got {args.person_id}",
              file=sys.stderr)
        return 2

    try:
        db = open_database(args.database)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except Exception as e:                       # pragma: no cover (any schema error)
        print(f"error: {e}", file=sys.stderr)
        return 2

    try:
        dump = dump_person(
            db.con,
            args.person_id,
            include_events=not args.no_events,
            include_family=not args.no_family,
        )
    finally:
        db.close()

    if dump is None:
        print(
            f"no person with PersonID={args.person_id} in {args.database}",
            file=sys.stderr,
        )
        return 1

    if args.format == "json":
        print(json.dumps(
            dump_payload(
                dump,
                source_path=str(args.database),
                db_version=db.version,
                person_id=args.person_id,
            ),
            indent=2,
            ensure_ascii=False,
        ))
    else:
        sys.stderr.write(
            f"# source: {args.database}\n"
            f"# db version: {db.version}\n"
            f"# person_id: {args.person_id}\n"
        )
        print(_dump_to_text(dump))
    return 0


if __name__ == "__main__":                    # pragma: no cover
    raise SystemExit(main())
