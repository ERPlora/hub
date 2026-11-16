"""How the card of a write says a record a person names by its name, and the start checks of its marks."""

from uuid import UUID

import pytest
from django.core import checks
from live.errors import Conflict, NotFound
from live.operations import Operation, registry
from ninja import Field, Schema

from base import assistant
from base.schemas import names, unless_given
from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.card_values import ADMIN, ctx, reference_errors, values

__all__ = ["in_business_a"]


# ── A record said by its name inside another, and words that cannot be read (hub#1245) ────────────────────────────────
# A course is found by its name inside its menu, a choice inside its course: its mark names the data of its own object
# the read takes beside it (``within``), never all of them (the ``id`` of a write on a course is the course, which the
# menu's read would take as a menu's). A datum a person says in words (``as_said``) that cannot be read — several fit,
# none does, nobody is at hand — is said as said, never left out: the words are theirs, never an id.

#: The dishes of the test by their menu: «postres» fits one in «Vegano» and two in «Infantil».
DISHES = {
    "Vegano": {"D-1": "Postres caseros", "D-2": "Primeros"},
    "Infantil": {"D-3": "Postres de fruta", "D-4": "Postres lácteos"},
    "Degustación": {"D-5": "Sorpresa"},
}
#: A dish its read answers with no name.
NAMELESS = {"D-5"}
#: A dish said by its name, read with its menu beside it.
A_DISH = {"refers": {"read": "demo.item.dish", "by": "dish", "name": ["name"], "within": ["menu"], "as_said": True}}


class DishIn(Schema):
    id: str | None = None
    menu: str | None = None
    dish: str | None = None


class DishOut(Schema):
    id: str
    name: str


def dish_of(read: list) -> Operation:
    def dish(ctx, data):
        read.append(data.model_dump(exclude_none=True))
        menu = DISHES.get(data.menu or "", {})
        fits = [(key, name) for key, name in menu.items() if data.dish and data.dish.lower() in name.lower()]
        if len(fits) > 1:
            raise Conflict("Several dishes fit.", code="demo.dish_ambiguous")
        if not fits:
            raise NotFound("There is no such dish.")
        key, name = fits[0]
        return {"id": key, "name": "" if key in NAMELESS else name}

    return Operation(
        name="demo.item.dish",
        kind="query",
        permission="demo.view",
        input=DishIn,
        output=DishOut,
        expose_api=False,
        ai={"description": "A dish by its name inside its menu."},
        fn=dish,
    )


@pytest.fixture
def dish_reads(monkeypatch) -> list:
    """The dish's read registered as an app's would be: what it was asked, in order."""
    read: list = []
    op = dish_of(read)
    monkeypatch.setitem(registry, op.name, op)
    return read


def serving(mark: dict = A_DISH) -> Operation:
    """A write on a table (``id``) that serves a dish of a menu, on top and on a line of its own."""

    class ServedLineIn(Schema):
        menu: str | None = None
        dish_id: str | None = None
        dish: str | None = Field(None, json_schema_extra=mark)

    class ServeIn(Schema):
        id: str | None = None
        menu: str | None = None
        dish_id: str | None = None
        dish: str | None = Field(None, json_schema_extra=mark)
        line: ServedLineIn | None = None

    return Operation(
        name="demo.item.serve",
        kind="command",
        permission="demo.manage",
        input=ServeIn,
        output=ServeIn,
        expose_api=False,
        ai={"description": "Serves a dish of a menu."},
        fn=lambda ctx, data: data,
    )


SERVER = {*ADMIN, "demo.view", "demo.manage"}


def served(arguments: dict, permissions=SERVER, *, person: bool = True, found: list | None = None, mark=A_DISH) -> dict:
    card = assistant.cards.card(serving(mark), arguments, "es", ctx=ctx(permissions) if person else None, found=found)
    return values(card)


def test_names_marks_the_data_a_record_is_read_with_and_words_said_as_said():
    assert names("demo.item.dish", by="dish", within=("menu",), as_said=True) == A_DISH
    # Without them, a mark is what it always was.
    assert names("demo.item.dish") == {"refers": {"read": "demo.item.dish", "by": "id", "name": ["name"]}}


@HUB_DB
def test_a_record_said_by_its_name_inside_another_is_read_with_the_data_its_mark_names(dish_reads):
    assert served({"menu": "Vegano", "dish": "postres"}) == {"menu": "Vegano", "dish": "Postres caseros"}
    assert dish_reads == [{"menu": "Vegano", "dish": "postres"}]


@HUB_DB
def test_only_the_data_its_mark_names_go_with_it(dish_reads):
    """The table's ``id`` stays out of the dish's read, though that read takes an ``id`` of its own."""
    served({"id": "T-9", "menu": "Vegano", "dish": "postres"})
    assert dish_reads == [{"menu": "Vegano", "dish": "postres"}]


@HUB_DB
def test_inside_an_object_the_data_beside_it_are_those_of_its_own_object(dish_reads):
    shown = served({"menu": "Infantil", "line": {"menu": "Vegano", "dish": "postres"}})
    assert shown["line"] == {"menu": "Vegano", "dish": "Postres caseros"}
    assert dish_reads == [{"menu": "Vegano", "dish": "postres"}]


@HUB_DB
def test_inside_an_object_a_datum_takes_nothing_from_the_object_around_it(dish_reads):
    """A line that names no menu is read with none, though the write around it names one: it is said as said."""
    shown = served({"menu": "Vegano", "line": {"dish": "postres"}})
    assert shown["line"] == {"dish": "postres"}
    assert dish_reads == [{"dish": "postres"}]


@HUB_DB
@pytest.mark.parametrize(
    "arguments",
    [{"menu": "Infantil", "dish": "postres"}, {"menu": "Vegano", "dish": "helados"}, {"dish": "postres"}],
    ids=["several fit", "none does", "without its menu"],
)
def test_words_that_cannot_be_read_are_said_as_said(dish_reads, arguments):
    found: list = []
    assert served(arguments, found=found)["dish"] == arguments["dish"]
    assert found == []


@HUB_DB
def test_words_nobody_may_read_or_with_nobody_at_hand_are_said_as_said(dish_reads):
    arguments = {"menu": "Vegano", "dish": "postres"}
    assert served(arguments, ADMIN)["dish"] == "postres"
    # Refused before it reads: the person may not see the dishes.
    assert dish_reads == []
    assert served(arguments, person=False)["dish"] == "postres"
    # Without the person at hand (an automation's card) the read is not run for anybody.
    assert dish_reads == []


@HUB_DB
def test_the_record_found_by_its_name_goes_in_what_the_yes_is_for(dish_reads):
    found: list = []
    served({"menu": "Vegano", "dish": "postres"}, found=found)
    assert found == ["D-1"]


@HUB_DB
def test_a_record_found_that_has_no_name_is_said_as_said_and_goes_in_what_the_yes_is_for(dish_reads):
    found: list = []
    assert served({"menu": "Degustación", "dish": "sorpresa"}, found=found)["dish"] == "sorpresa"
    assert found == ["D-5"]


@HUB_DB
def test_without_as_said_words_that_cannot_be_read_are_left_out(dish_reads):
    """``as_said`` is the mark's to say: a datum that names a record otherwise is left out, as ever."""
    mark = names("demo.item.dish", by="dish", within=("menu",))
    assert "dish" not in served({"menu": "Infantil", "dish": "postres"}, mark=mark)


#: A dish said by its name, which the write does not use when the dish comes by its id (hub#1250).
UNLESS_ITS_ID = {"refers": {**A_DISH["refers"], "unless": ["dish_id"]}}


def test_names_marks_the_data_that_leave_a_name_unread():
    assert names("demo.item.dish", by="dish", within=("menu",), as_said=True, unless=("dish_id",)) == UNLESS_ITS_ID


def test_unless_given_is_a_mark_left_unread_beside_those_data_and_leaves_the_mark_as_it_was():
    """One mark, declared once, left unread beside a different datum in each object that carries it."""
    assert unless_given(A_DISH, "dish_id") == UNLESS_ITS_ID
    assert "unless" not in A_DISH["refers"]


@HUB_DB
def test_a_name_beside_the_record_the_write_takes_instead_is_neither_read_nor_shown(dish_reads):
    """The write takes the dish by its id and never looks at the name beside it: the card says no other dish."""
    found: list = []
    shown = served({"menu": "Vegano", "dish_id": "D-2", "dish": "postres"}, found=found, mark=UNLESS_ITS_ID)
    assert "dish" not in shown
    assert (dish_reads, found) == ([], [])


@HUB_DB
@pytest.mark.parametrize("dish_id", [None, ""], ids=["none", "empty"])
def test_without_the_record_that_leaves_it_unread_a_name_is_read_as_ever(dish_reads, dish_id):
    shown = served({"menu": "Vegano", "dish_id": dish_id, "dish": "postres"}, mark=UNLESS_ITS_ID)
    assert shown["dish"] == "Postres caseros"


@HUB_DB
def test_inside_an_object_only_its_own_record_leaves_its_name_unread(dish_reads):
    shown = served(
        {"dish_id": "D-2", "line": {"menu": "Vegano", "dish": "postres"}}, mark=UNLESS_ITS_ID
    )
    assert shown["line"] == {"menu": "Vegano", "dish": "Postres caseros"}
    shown = served({"line": {"menu": "Vegano", "dish_id": "D-2", "dish": "postres"}}, mark=UNLESS_ITS_ID)
    assert "dish" not in shown["line"]


def beside(refers: object, *, kind: type = str) -> Operation:
    class BesideIn(Schema):
        menu: str | None = None
        table: str | None = None
        dish: kind | None = Field(None, json_schema_extra={"refers": refers})

    return Operation(
        name="demo.item.beside",
        kind="command",
        permission="demo.manage",
        input=BesideIn,
        output=BesideIn,
        expose_api=False,
        ai={"description": "Serves a dish of a menu."},
        fn=lambda ctx, data: data,
    )


def test_a_mark_read_with_the_data_beside_it_is_sound(monkeypatch, dish_reads):
    write = beside(A_DISH["refers"])
    monkeypatch.setitem(registry, write.name, write)
    assert reference_errors() == []


@pytest.mark.parametrize(
    ("refers", "kind", "why"),
    [
        ({**A_DISH["refers"], "within": ["table"]}, str, "takes no table"),
        ({**A_DISH["refers"], "within": ["id"]}, str, "is read with id, which its own object does not have"),
        (A_DISH["refers"], UUID, "is said as said, but it is an id"),
        ({**A_DISH["refers"], "within": "menu"}, str, "is not a read, by and name"),
        ({**A_DISH["refers"], "as_said": "yes"}, str, "is not a read, by and name"),
        (
            {**A_DISH["refers"], "unless": ["dish_id"]},
            str,
            "is left unread with dish_id, which its own object does not have",
        ),
        ({**A_DISH["refers"], "unless": "table"}, str, "is not a read, by and name"),
        ({**A_DISH["refers"], "unless": [1]}, str, "is not a read, by and name"),
    ],
    ids=[
        "a datum its read does not take",
        "one its object does not have",
        "an id said as said",
        "no list",
        "no yes",
        "left unread with a datum its object does not have",
        "unless no list",
        "unless a list of no names",
    ],
)
def test_a_mark_read_with_the_data_beside_it_is_checked_at_start(monkeypatch, dish_reads, refers, kind, why):
    write = beside(refers, kind=kind)
    monkeypatch.setitem(registry, write.name, write)
    [error] = reference_errors()
    assert write.name in error.msg and why in error.msg


# ── A name a person says, checked at start (base.E014) ────────────────────────────────────────────────────────────────


def naming(of: object, *, kind: type = str, optional: bool = False) -> Operation:
    """A write whose lines carry a record by its id, one by another text its mark reads (``refers``), a note, and a
    datum marked as the name a person says of the record ``of`` names (``name_of``), of the type ``kind``; beside them,
    at the top, a customer by her id. ``optional``: the lines may not come at all, as the services of a booking's
    update."""

    class NamedLineIn(Schema):
        thing_id: UUID | None = None
        person: str | None = Field(
            None, json_schema_extra={"refers": {"read": "base.person.detail", "by": "person", "name": "name"}}
        )
        note: str | None = None
        thing: kind | None = Field(None, json_schema_extra={"name_of": of})

    lines_of = list[NamedLineIn] | None if optional else list[NamedLineIn]

    class NamedIn(Schema):
        customer_id: UUID | None = None
        lines: lines_of = None if optional else []

    return Operation(
        name="demo.item.named",
        kind="command",
        permission="demo.manage",
        input=NamedIn,
        output=NamedIn,
        expose_api=False,
        ai={"description": "Books demo items by their names."},
        fn=lambda ctx, data: data,
    )


def name_errors() -> list:
    return [error for error in checks.run_checks(tags=["base"]) if error.id == "base.E014"]


def test_the_name_marks_of_every_app_are_sound():
    """Positive control: Citas marks the name of a booking's service (hub#860), and it is sound."""
    assert name_errors() == []


@pytest.mark.parametrize("of", ["thing_id", "person"])
def test_a_name_of_a_record_of_its_own_line_is_sound(monkeypatch, of):
    """A record by its id, or marked ``refers``: the card says the line by the name when the record is not there."""
    write = naming(of)
    monkeypatch.setitem(registry, write.name, write)
    assert name_errors() == []


@pytest.mark.parametrize(
    ("write", "why"),
    [
        (naming(["thing_id"]), "lines[].thing is not the name of a datum"),
        (naming("thing_ids"), "lines[].thing names no thing_ids of its own object"),
        (naming("customer_id"), "lines[].thing names no customer_id of its own object"),
        (naming("note"), "lines[].thing names note, which is no record"),
        (naming("thing"), "lines[].thing names thing, which is no record"),
        (naming("thing_id", kind=int), "lines[].thing is no text"),
        (naming("thing_id", kind=UUID), "lines[].thing is no text"),
        (naming("thing_ids", optional=True), "lines[].thing names no thing_ids of its own object"),
    ],
)
def test_a_name_mark_that_names_no_record_of_its_own_object_is_said_at_start(monkeypatch, write, why):
    """A mark that names a datum the line does not carry (a typo, a record of the write's top), one that is no record
    or a datum that is no text (a number; an id, which a card never says) would leave the line in «1 elemento» with
    nothing said: it is said at start, also in lines that may not come at all."""
    monkeypatch.setitem(registry, write.name, write)
    [error] = name_errors()
    assert write.name in error.msg and why in error.msg
