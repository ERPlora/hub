"""How a staff member is named: by the id, or by the name as a person says it; a terminated record is gone."""

import uuid

import pytest
from live.errors import Conflict, NotFound

from apps.staff.queries.reads import resolve_member
from apps.staff.schemas.fields import MemberRefIn

from .conftest import HUB_DB, TERMINATED, make_member, run

pytestmark = HUB_DB


def test_detail_of_a_terminated_or_missing_record_is_not_found():
    terminated = make_member(status=TERMINATED)
    for member_id in (terminated.id, uuid.uuid7()):
        with pytest.raises(NotFound) as excinfo:
            run("staff.member.detail", MemberRefIn(id=member_id))
        assert (excinfo.value.status, excinfo.value.code) == (404, "not_found")


def test_a_member_by_name_for_the_assistant():
    ana = make_member("Ana", "López")
    make_member("Bea", "Ruiz")
    make_member("Ana", "Gone", status=TERMINATED)
    for spoken in ("ana lópez", "Ana", "lópez"):
        assert run("staff.member.detail", MemberRefIn(member=spoken)).id == ana.id


def test_an_exact_name_wins_over_partial_matches():
    ana = make_member("Ana", "López")
    make_member("Mariana", "López")
    assert run("staff.member.detail", MemberRefIn(member="Ana López")).id == ana.id


def test_an_ambiguous_name_names_the_candidates():
    make_member("Ana", "López")
    make_member("Ana", "Ruiz")
    with pytest.raises(Conflict) as excinfo:
        run("staff.member.detail", MemberRefIn(member="ana"))
    assert (excinfo.value.status, excinfo.value.code) == (409, "staff.ambiguous_member")
    assert "Ana López" in excinfo.value.message and "Ana Ruiz" in excinfo.value.message


def test_an_unknown_name_is_not_found():
    with pytest.raises(NotFound):
        resolve_member(None, "Nobody")
