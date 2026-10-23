"""rmread — read-only access to RootsMagic SQLite databases."""

from .db import RMDatabase, SchemaError, open_database
from .event import DEFAULT_EVENT_TYPES, Event, load_events
from .family import (
    ChildRef,
    ParentRef,
    SpouseLink,
    load_children,
    load_parents,
    load_spouses,
)
from .person import (
    Name,
    Person,
    PersonDump,
    dump_person,
    find_by_surname,
    find_person,
    get_person,
    load_alt_names,
)
from .rmtext import (
    Chunk,
    PlainText,
    Span,
    normalize_newlines,
    plain_text,
    tokenize,
)

__all__ = [
    # core
    "RMDatabase",
    "SchemaError",
    "open_database",
    # people
    "Name",
    "Person",
    "PersonDump",
    "dump_person",
    "find_by_surname",
    "find_person",
    "get_person",
    "load_alt_names",
    # events
    "DEFAULT_EVENT_TYPES",
    "Event",
    "load_events",
    # family
    "ChildRef",
    "ParentRef",
    "SpouseLink",
    "load_children",
    "load_parents",
    "load_spouses",
    # markup dialect
    "Chunk",
    "PlainText",
    "Span",
    "normalize_newlines",
    "plain_text",
    "tokenize",
]
