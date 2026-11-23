"""What the assistant reads of ERPlora's route, where ERPlora files on a business's behalf once its signed
authorisation is approved: the route only exists on a server that keeps it open, and the tool that offers the
authorisation's model has to say so, because a turn that asks «I'd rather you send the invoices for me» is offered
that tool and the Home's checklist (``base.setup.status``) but not ``verifactu.config.get``. The model answered with a
«second route» that the screen does not show where the route is closed.

Nothing here runs an operation: the tests read what the model is told of each tool.
"""

import json
from pathlib import Path

from django.utils import translation
from live.assistant import tool_spec
from live.operations import registry

from apps.verifactu import erplora_route
from apps.verifactu.apps import VerifactuConfig

MODEL = "verifactu.representation.model"
LOCALE = Path(__file__).resolve().parents[1] / "frontend" / "locale" / "en.json"


def told_of_model() -> str:
    return tool_spec(registry[MODEL])["description"]


def screen_label(key: str) -> str:
    """A label of VeriFactu's screens in English, by its dotted key in the app's catalogue."""
    node = json.loads(LOCALE.read_text(encoding="utf-8"))
    for part in key.split("."):
        node = node[part]
    return node


def test_the_authorisation_is_offered_only_where_erplora_files_for_businesses():
    """Where the route is closed the model gets the answer the screen and the tool give, and the two signals a turn
    carries of it: the Home's step, which then asks only for the business certificate, and the configuration's
    ``erplora_route_available``."""
    with translation.override("en"):
        refused = str(erplora_route.UNAVAILABLE)
        step = str(next(step.title for step in VerifactuConfig.setup if step.key == "sending_route"))
    told = told_of_model()

    assert refused == "ERPlora does not file on behalf of businesses for now: file with your own certificate."
    assert f"«{refused}»" in told
    assert f"«{step}» (base.setup.status)" in told
    assert "erplora_route_available" in told
    assert f"«{screen_label('verifactu.config.own')}»" in told


def test_where_the_route_is_open_it_says_where_the_signed_form_goes():
    """The model explains the whole way, as VeriFactu → Configuration shows it: the tab and the button by their names
    on the screen."""
    told = told_of_model()

    assert f"«{screen_label('verifactu.config.erplora')}»" in told
    assert f"«{screen_label('verifactu.grant.submit')}»" in told
