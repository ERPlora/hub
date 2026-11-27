"""The order in which what travels of each app is loaded (``base.blueprint.datasets.every_dataset``)."""

from types import SimpleNamespace

import pytest

from base import activation
from base.blueprint import datasets
from base.blueprint.calls import Dataset


def a_dataset(key: str) -> Dataset:
    return Dataset(key=key, label=key, rows=list, ids=list, count=len, load=print, remove=print)


def an_app(label: str, *requires: str) -> SimpleNamespace:
    return SimpleNamespace(label=label, requires=requires, blueprint_datasets=lambda: [a_dataset(f"{label}.row")])


@pytest.fixture
def installed(monkeypatch):
    """The apps of the deployment are the ones given, in that order, for one test."""

    def install(*configs):
        monkeypatch.setattr(datasets, "module_configs", lambda: configs)
        monkeypatch.setattr(activation, "module_configs", lambda: configs)
        datasets.every_dataset.cache_clear()

    yield install
    monkeypatch.undo()
    datasets.every_dataset.cache_clear()


def test_an_app_s_datasets_load_after_those_of_the_apps_it_requires_even_when_it_is_installed_before_them(installed):
    installed(an_app("bookings", "rooms"), an_app("rooms"))

    order = [dataset.key for dataset in datasets.every_dataset()]

    assert order.index("rooms.row") < order.index("bookings.row")

