"""Tests for rmread.family — synthetic in-memory only."""

from __future__ import annotations

from ._schema import full_db


def test_load_parents_returns_records_for_a_child(full_db):
    from rmread import load_parents
    # pid 5 is a child in family 3 → it should have a father (pid 1)
    # and a mother (pid 4) recorded.
    parents = load_parents(full_db.con, 5)
    role_ids = {(p.role, p.parent_id) for p in parents}
    assert ("father", 1) in role_ids
    assert ("mother", 4) in role_ids


def test_load_parents_empty_for_root_ancestor(full_db):
    from rmread import load_parents
    # pid 1 is the synthetic root — no ChildTable row points at it.
    assert load_parents(full_db.con, 1) == []


def test_load_spouses_picks_all_partners(full_db):
    from rmread import load_spouses
    spouses = load_spouses(full_db.con, 1)
    # pid 1 is father in families 1, 2, 3 → three spouses.
    assert len(spouses) == 3
    assert {s.spouse_id for s in spouses} == {2, 3, 4}


def test_load_spouses_empty_for_childless_root(full_db):
    from rmread import load_spouses
    # pid 5 is a child, never a spouse, never a parent.
    assert load_spouses(full_db.con, 5) == []


def test_load_children_ordered_by_child_order(full_db):
    from rmread import load_children
    children = load_children(full_db.con, 1)
    # pid 5 is child_order=1, pid 6 is child_order=2, both in family 3.
    child_orders = [c.child_order for c in children]
    assert child_orders == sorted(child_orders)
    assert {c.child_id for c in children} == {5, 6}


def test_load_children_empty_for_person_with_no_children(full_db):
    from rmread import load_children
    # pid 2 is a mother in family 1 with no children in this fixture.
    assert load_children(full_db.con, 2) == []


def test_child_ref_rel_father_and_mother_propagated(full_db):
    from rmread import load_children
    children = load_children(full_db.con, 1)
    by_id = {c.child_id: c for c in children}
    assert by_id[5].rel_father == 1 and by_id[5].rel_mother == 1
    assert by_id[6].rel_father == 1 and by_id[6].rel_mother == 1


def test_display_name_falls_back_to_pid_when_no_name(full_db):
    """pid 7 is an orphan — no NameTable row. _display_name must not crash."""
    from rmread.family import _display_name
    assert _display_name(full_db.con, 7) == "@pid7"
