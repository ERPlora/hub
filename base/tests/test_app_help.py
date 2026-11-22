"""base/schemas/app_help.py: what the help window asks for (a module's id) and the shape of what it gets back."""

import pytest
from pydantic import ValidationError

from base.schemas.app_help import AppHelpIn, AppHelpOut


def test_it_asks_for_one_module_by_its_id():
    assert AppHelpIn(app="table").app == "table"
    with pytest.raises(ValidationError):
        AppHelpIn(app="x" * 101)
    with pytest.raises(ValidationError):
        AppHelpIn()


def test_a_module_without_a_video_answers_none_and_every_other_field_is_required():
    answer = {"app": "table", "name": "Mesas", "language": "es", "video": None, "purpose": "", "screens": [], "flows": []}
    assert AppHelpOut.model_validate(answer).video is None
    with pytest.raises(ValidationError):
        AppHelpOut.model_validate({key: value for key, value in answer.items() if key != "screens"})


def test_each_flow_names_the_tabs_it_happens_on_and_its_short_videos():
    flow = {"id": "TABLE-F01", "title": "Crear una zona", "screens": ["zones"], "steps": "1. Pulsa «+».", "failure": "",
            "videos": ["L4LipaZOq40"]}
    screen = {"id": "zones", "title": "Zonas", "path": "/table/zones", "text": "Una tabla."}
    answer = AppHelpOut.model_validate(
        {"app": "table", "name": "Mesas", "language": "es", "video": "dQw4w9WgXcQ", "purpose": "", "screens": [screen],
         "flows": [flow]}
    )
    assert (answer.flows[0].screens, answer.screens[0].path) == (["zones"], "/table/zones")
    assert answer.flows[0].videos == ["L4LipaZOq40"]
    with pytest.raises(ValidationError):
        AppHelpOut.model_validate({**answer.model_dump(), "flows": [{k: v for k, v in flow.items() if k != "videos"}]})
