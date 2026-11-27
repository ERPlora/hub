"""Every app with data of its own says, kind of row by kind of row, whether it travels in an export of the business
(a dataset of the app) or stays, and why. A new app, or a new kind of row in an app that already travels, cannot be
left out of the backup without anyone seeing it: this check names it."""

from types import SimpleNamespace

import pytest
from live.meta import module_configs

from base.blueprint import datasets
from base.blueprint.calls import STAYS_HOOK, Dataset, Stays


def models_of(config) -> set[str]:
    return {model.__name__ for model in config.get_models()}


def carried_by(app: str) -> set[str]:
    return {model for part in datasets.datasets_of(app) for model in part.models}


def staying_in(config) -> dict[str, str]:
    return dict(getattr(config, STAYS_HOOK, {}))


def undeclared(configs) -> dict[str, list[str]]:
    """Per app, its models that neither travel in one of its datasets nor say why they stay."""
    missing = {}
    for config in configs:
        if names := models_of(config) - carried_by(config.label) - set(staying_in(config)):
            missing[config.label] = sorted(names)
    return missing


def test_every_model_of_every_app_travels_in_a_dataset_or_says_why_it_stays():
    assert undeclared(module_configs()) == {}


def test_a_model_either_travels_or_stays_never_both():
    both = {
        config.label: sorted(carried_by(config.label) & set(staying_in(config)))
        for config in module_configs()
        if carried_by(config.label) & set(staying_in(config))
    }

    assert both == {}


def test_what_a_dataset_carries_and_what_an_app_keeps_are_models_of_that_app():
    foreign = {
        config.label: sorted((carried_by(config.label) | set(staying_in(config))) - models_of(config))
        for config in module_configs()
        if (carried_by(config.label) | set(staying_in(config))) - models_of(config)
    }

    assert foreign == {}


def test_the_reason_a_model_stays_is_one_of_the_known_reasons():
    known = {reason.value for reason in Stays}
    unknown = {
        f"{config.label}.{model}": reason
        for config in module_configs()
        for model, reason in staying_in(config).items()
        if reason not in known
    }

    assert unknown == {}


@pytest.fixture
def installed(monkeypatch):
    """The apps of the deployment are the ones given, for one test."""

    def install(*configs):
        monkeypatch.setattr(datasets, "module_configs", lambda: configs)
        monkeypatch.setattr("base.activation.module_configs", lambda: configs)
        datasets.every_dataset.cache_clear()
        datasets._datasets_by_key.cache_clear()

    yield install
    monkeypatch.undo()
    datasets.every_dataset.cache_clear()
    datasets._datasets_by_key.cache_clear()


def an_app(label: str, models: tuple[str, ...], *, travels: tuple[str, ...] = (), stays: dict | None = None):
    part = Dataset(key=f"{label}.row", label=label, rows=list, count=len, load=print, models=travels)
    return SimpleNamespace(
        label=label,
        requires=(),
        get_models=lambda: [type(name, (), {}) for name in models],
        blueprint_datasets=lambda: [part] if travels else [],
        **{STAYS_HOOK: stays or {}},
    )


def test_the_check_names_a_new_kind_of_row_of_an_app_that_already_travels(installed):
    installed(an_app("bookings", ("Room", "Booking", "Extra"), travels=("Room",), stays={"Booking": Stays.HISTORY}))

    assert undeclared(datasets.module_configs()) == {"bookings": ["Extra"]}


def test_the_check_names_an_app_that_declares_nothing(installed):
    installed(an_app("notes", ("Note",)))

    assert undeclared(datasets.module_configs()) == {"notes": ["Note"]}
