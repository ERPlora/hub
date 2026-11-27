"""No name of ``components/schemas`` in ``/api/openapi.json`` stands for two different data: each route cites its own.

django-ninja writes the schemas of every route into one ``components/schemas`` by name, and a second schema with a name
already taken silently replaces the first, so every route of either would show the same fields. These tests build the
whole document and record, for each name, which classes and which bodies were written under it.
"""

import json
import re
from collections import defaultdict

import pytest
from ninja.openapi.schema import OpenAPISchema
from pydantic.json_schema import GenerateJsonSchema

from config.api import api


@pytest.fixture
def written(monkeypatch) -> tuple[dict, dict[str, set[str]], dict[str, set[str]]]:
    """The whole document, and per component name the classes and the bodies written under it while building it."""
    classes: dict[str, set[str]] = defaultdict(set)
    bodies: dict[str, set[str]] = defaultdict(set)
    remap = GenerateJsonSchema._build_definitions_remapping
    add = OpenAPISchema.add_schema_definitions

    def remap_recording(generator):
        remapping = remap(generator)
        for defs_ref in generator.definitions:
            core_ref, _mode = generator.defs_to_core_refs[defs_ref]
            classes[remapping.remap_defs_ref(defs_ref)].add(core_ref)
        return remapping

    def add_recording(document, definitions):
        for name, body in definitions.items():
            bodies[name].add(json.dumps(body, sort_keys=True))
        return add(document, definitions)

    monkeypatch.setattr(GenerateJsonSchema, "_build_definitions_remapping", remap_recording)
    monkeypatch.setattr(OpenAPISchema, "add_schema_definitions", add_recording)
    return api.get_openapi_schema(), classes, bodies


def readable(core_ref: str) -> str:
    """A class's reference without the ids that tell two classes apart: ``apps.table.schemas.settings.SettingsOut``."""
    return re.sub(r":\d+", "", core_ref)


def test_the_record_sees_every_schema_of_the_document(written):
    document, classes, bodies = written
    assert set(classes) == set(bodies) == set(document["components"]["schemas"])


def test_no_component_name_stands_for_two_classes(written):
    _, classes, _ = written
    shared = {name: sorted(map(readable, refs)) for name, refs in classes.items() if len(refs) > 1}
    assert shared == {}


def test_no_component_name_is_written_with_two_different_bodies(written):
    _, _, bodies = written
    assert sorted(name for name, written_bodies in bodies.items() if len(written_bodies) > 1) == []
