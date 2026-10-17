"""Two people at once: real sessions in threads, real row locks (WORKBOOK «Para quien lo mantiene»).

Two courses with the same name added to one menu at once give one course and a 409; two choices of the
same product added to one course at once give one choice and a 409; a full course takes no one more
however many arrive together. A read that a menu's deletion lands in the middle of answers what it read,
a 404 or the till's 409, never a 500.
"""

import threading
from contextlib import contextmanager

import pytest
from django.db import connection
from live.errors import Conflict, NotFound, OperationError
from live.models import OutboxEvent

from apps.combo.models import ChoiceGroup, ChoiceOption, Combo

from .conftest import FOOD, make_combo, make_group, make_option, make_product, run

pytestmark = pytest.mark.django_db(transaction=True)


def at_once(*calls):
    """Runs every ``call`` in its own thread and session, released together; their results or errors."""
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def worker(index, call):
        try:
            barrier.wait(5)
            results[index] = call()
        except (
            Exception
        ) as error:  # an expected refusal or an unexpected failure, both reported
            results[index] = error
        finally:
            connection.close()

    threads = [
        threading.Thread(target=worker, args=(i, call)) for i, call in enumerate(calls)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


def refused(results) -> list[OperationError]:
    return [result for result in results if isinstance(result, OperationError)]


def test_two_courses_with_the_same_name_at_once_make_one():
    combo = make_combo()
    results = at_once(
        *(
            lambda: run(
                "combo.group.create", {"combo_id": str(combo.id), "name": "Starters"}
            )
            for _ in range(3)
        )
    )
    assert [error.code for error in refused(results)] == ["combo.group_exists"] * 2
    assert ChoiceGroup.objects.filter(combo=combo).count() == 1
    assert OutboxEvent.objects.filter(name="combo.group.created").count() == 1


def test_the_same_product_twice_at_once_in_one_course_makes_one_choice():
    course = make_group(make_combo())
    lentils = make_product("Lentils")
    results = at_once(
        *(
            lambda: run(
                "combo.option.create",
                {"group_id": str(course.id), "product_id": str(lentils.id)},
            )
            for _ in range(3)
        )
    )
    assert [error.code for error in refused(results)] == ["combo.option_exists"] * 2
    assert ChoiceOption.objects.filter(group=course).count() == 1


def test_a_full_course_takes_no_one_more_whatever_arrives_together():
    course = make_group(make_combo())
    for n in range(38):
        make_option(course, make_product(f"Dish {n}"))
    extra = [make_product(f"Extra {n}") for n in range(4)]
    results = at_once(
        *(
            lambda p=p: run(
                "combo.option.create",
                {"group_id": str(course.id), "product_id": str(p.id)},
            )
            for p in extra
        )
    )
    assert [error.code for error in refused(results)] == ["combo.too_many_options"] * 2
    assert ChoiceOption.objects.filter(group=course).count() == 40
    # Two arrived first and went last, one after the other, never on the same place.
    assert sorted(course.options.values_list("sort_order", flat=True))[-2:] == [38, 39]


# Edits and reorders against writes of the same menu: a 409 or a success, never a raw database error
# (review 3). Each case repeats, so a race that only bites now and then still shows.


def unexpected(results) -> list:
    return [result for result in results if isinstance(result, Exception) and not isinstance(result, OperationError)]


@pytest.mark.parametrize("attempt", range(3))
def test_renaming_a_course_while_another_takes_the_name_gives_one_course(attempt):
    combo = make_combo()
    mains = make_group(combo, "Mains")
    results = at_once(
        lambda: run("combo.group.update", {"id": str(mains.id), "name": "Desserts"}),
        lambda: run("combo.group.create", {"combo_id": str(combo.id), "name": "Desserts"}),
    )
    assert unexpected(results) == []
    assert [error.code for error in refused(results)] == ["combo.group_exists"]
    assert ChoiceGroup.objects.filter(combo=combo, name__iexact="desserts").count() == 1


@pytest.mark.parametrize("attempt", range(3))
def test_changing_a_choice_to_a_product_another_adds_gives_one_choice(attempt):
    course = make_group(make_combo())
    option = make_option(course, make_product("Hake"))
    sole = make_product("Sole")
    results = at_once(
        lambda: run("combo.option.update", {"id": str(option.id), "new_product_id": str(sole.id)}),
        lambda: run("combo.option.create", {"group_id": str(course.id), "product_id": str(sole.id)}),
    )
    assert unexpected(results) == []
    assert [error.code for error in refused(results)] == ["combo.option_exists"]
    assert ChoiceOption.objects.filter(group=course, product=sole).count() == 1


@pytest.mark.parametrize("attempt", range(3))
def test_reordering_while_a_choice_is_added_is_a_409_or_a_success(attempt):
    course = make_group(make_combo())
    a, b = make_option(course, make_product("A")), make_option(course, make_product("B"))
    results = at_once(
        lambda: run("combo.option.reorder", {"group_id": str(course.id), "option_ids": [str(b.id), str(a.id)]}),
        lambda: run("combo.option.create", {"group_id": str(course.id), "product_id": str(make_product("C").id)}),
    )
    assert unexpected(results) == []
    assert {error.code for error in refused(results)} <= {"combo.reorder_mismatch"}
    assert ChoiceOption.objects.filter(group=course).count() == 3


@pytest.mark.parametrize("attempt", range(3))
def test_withdrawing_a_menu_while_a_choice_is_added_leaves_nothing_behind(attempt):
    combo = make_combo()
    course = make_group(combo)
    make_option(course, make_product("A"))
    product = make_product("B")
    results = at_once(
        lambda: run("combo.combo.delete", {"id": str(combo.id)}),
        lambda: run("combo.option.create", {"group_id": str(course.id), "product_id": str(product.id)}),
    )
    assert unexpected(results) == []
    assert not Combo.objects.filter(pk=combo.pk).exists()
    assert ChoiceGroup.objects.filter(pk=course.pk).count() == 0
    assert ChoiceOption.objects.filter(group_id=course.pk).count() == 0


# A menu withdrawn while it is being read: the read finds it and then loaded it again by its id, so a
# deletion committed between the two raised DoesNotExist (a 500). Each case lands the deletion there.


@contextmanager
def withdrawn_after_the_first_read_of(combo):
    """Commits ``combo.combo.delete`` of ``combo`` in another session right after the first statement of
    this one that reads the menus: a deletion landing in the middle of a read, every time."""
    table = f'"{Combo._meta.db_table}"'
    deletions: list = []

    def wrapper(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if not deletions and sql.lstrip().upper().startswith("SELECT") and table in sql:
            deletions.extend(at_once(lambda: run("combo.combo.delete", {"id": str(combo.id)})))
        return result

    with connection.execute_wrapper(wrapper):
        yield deletions


def deleted(deletions) -> list[str]:
    return ["ok" if not isinstance(result, Exception) else repr(result) for result in deletions]


def a_menu_with_a_course():
    combo = make_combo("Menu of the day")
    make_option(make_group(combo, "Starters", min_choices=1), make_product("Lentils"))
    return combo


def test_a_menu_withdrawn_while_its_detail_is_read_is_never_a_server_error():
    combo = a_menu_with_a_course()
    with withdrawn_after_the_first_read_of(combo) as deletions:
        detail = run("combo.combo.get", {"id": str(combo.id)})
    assert deleted(deletions) == ["ok"]
    # The menu as it was read: its own row (its courses may already be gone with it).
    assert (detail.id, detail.name, detail.price, detail.tax_category_key) == (combo.id, "Menu of the day", 1350, FOOD)
    # What the deletion's event runs next: not found, and the open detail says so.
    with pytest.raises(NotFound) as error:
        run("combo.combo.get", {"id": str(combo.id)})
    assert (error.value.code, error.value.status) == ("not_found", 404)


def test_a_menu_withdrawn_between_its_name_and_its_detail_is_not_found():
    combo = a_menu_with_a_course()
    with withdrawn_after_the_first_read_of(combo) as deletions:
        with pytest.raises(NotFound) as error:
            run("combo.combo.get", {"combo": "menu of the day"})
    assert (deleted(deletions), error.value.code, error.value.status) == (["ok"], "not_found", 404)


def test_a_menu_withdrawn_while_the_till_prices_it_is_refused_never_a_server_error():
    combo = a_menu_with_a_course()
    line = {"id": str(combo.id), "choices": [{"product": "Lentils"}]}
    with withdrawn_after_the_first_read_of(combo) as deletions:
        with pytest.raises(Conflict) as error:
            run("combo.combo.resolve", line)
    # Read before its courses went: nothing left to pick from, the till's refusal.
    assert (deleted(deletions), error.value.code, error.value.status) == (
        ["ok"],
        "combo.option_not_in_combo",
        409,
    )
    with pytest.raises(Conflict) as error:
        run("combo.combo.resolve", line)
    assert (error.value.code, error.value.status) == ("combo.combo_missing", 409)


def test_a_menu_withdrawn_between_its_name_and_its_price_is_missing_for_the_till():
    combo = a_menu_with_a_course()
    line = {"combo": "menu of the day", "choices": [{"product": "Lentils"}]}
    with withdrawn_after_the_first_read_of(combo) as deletions:
        with pytest.raises(Conflict) as error:
            run("combo.combo.resolve", line)
    assert (deleted(deletions), error.value.code, error.value.status) == (
        ["ok"],
        "combo.combo_missing",
        409,
    )
