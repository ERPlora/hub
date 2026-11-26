"""What the assistant reads of ERPlora's route, where ERPlora files on a business's behalf once its signed
authorisation is approved: the route only exists on a server that keeps it open, and the tool that offers the
authorisation's model has to say so, because a turn that asks «I'd rather you send the invoices for me» is offered
that tool and the Home's checklist (``base.setup.status``) but not ``verifactu.config.get``. The model answered with a
«second route» that the screen does not show where the route is closed.

Nothing here runs an operation: the tests read what the model is told of each tool.
"""

from live.assistant import tool_spec
from live.operations import registry

MODEL = "verifactu.representation.model"


def told_of_model() -> str:
    return tool_spec(registry[MODEL])["description"]


def test_the_authorisation_is_offered_only_where_erplora_files_for_businesses():
    """Where the route is closed the model gets the answer the screen and the tool give, in its own words (the person
    reads them in their language), and the two signals a turn carries of it: the Home's step, which then asks only for
    the business certificate, and the configuration's ``erplora_route_available``."""
    told = told_of_model()

    assert "Only on a server where ERPlora files on behalf of businesses" in told
    assert "ERPlora does not file on behalf of businesses for now: that is the answer" in told
    assert "the business files with its own certificate" in told
    assert "the authorisation is not offered" in told
    assert "the Home's step to set up VeriFactu (base.setup.status)" in told
    assert "erplora_route_available" in told


def test_where_the_route_is_open_it_says_where_the_signed_form_goes():
    """The model explains the whole way, as VeriFactu → Configuration shows it, in its own words: the tab where ERPlora
    files for the business and sending the form for review."""
    told = told_of_model()

    assert "on VeriFactu › Configuration, in the tab where ERPlora files for the business" in told
    assert "and sends it for review; a person at ERPlora reviews it" in told
