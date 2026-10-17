"""Shape of base.session.me, the contract the shell reads (packages/ui src/shell/session.ts)."""

import pydantic
import pytest

from base.schemas import SessionMeIn, SessionMeOut

FULL = {
    "user": {"id": "7", "label": "Ana"},
    "scope": {"kind": "host", "key": "a"},
    "permissions": ["demo.view"],
    "menu": [{"id": "demo", "label": "Demo", "items": [{"path": "/demo/items", "label": "Demo", "icon": "ion:flask-outline"}]}],
    "apps": [{"label": "demo", "state": "on"}],
    "language": "es",
    "demo": None,
}


def test_input_is_empty():
    assert SessionMeIn.model_fields == {}


def test_full_output_round_trips():
    assert SessionMeOut.model_validate(FULL).model_dump(mode="json") == FULL


def test_anonymous_output():
    anonymous = {**FULL, "user": None, "permissions": [], "menu": [], "apps": []}
    assert SessionMeOut.model_validate(anonymous).user is None


@pytest.mark.parametrize("state", ["on", "activating", "off"])
def test_app_states(state):
    SessionMeOut.model_validate({**FULL, "apps": [{"label": "demo", "state": state}]})


def test_unknown_app_state_is_rejected():
    with pytest.raises(pydantic.ValidationError):
        SessionMeOut.model_validate({**FULL, "apps": [{"label": "demo", "state": "broken"}]})


def test_a_demo_s_session_says_when_it_ends():
    # plan 2026-10-17, §1.6: ``demo`` is always there, ``null`` on a business's hub.
    on_a_demo = {**FULL, "demo": {"expires_at": "2026-10-17T18:00:00Z"}}
    assert SessionMeOut.model_validate(on_a_demo).model_dump(mode="json") == on_a_demo
    without = {key: value for key, value in FULL.items() if key != "demo"}
    with pytest.raises(pydantic.ValidationError):
        SessionMeOut.model_validate(without)
