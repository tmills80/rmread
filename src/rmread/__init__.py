"""rmread — read-only access to RootsMagic SQLite databases."""

from .db import RMDatabase, SchemaError, open_database
from .person import Name, Person, find_by_surname, load_alt_names

__all__ = [
    "RMDatabase",
    "SchemaError",
    "open_database",
    "Name",
    "Person",
    "find_by_surname",
    "load_alt_names",
]
