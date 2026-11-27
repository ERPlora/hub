"""What the assistant's model reads of a record's amount: in the business's currency, as the screen shows it.

A record keeps its total in cents (``total_amount`` 121 is 1.21 €) and the model, which never sees a result's schema,
told the owner a test ticket of 1.21 € was «por 121,00 €».
"""

import json

from live import assistant as shared
from live.operations import get

from apps.verifactu.tests.conftest import HUB_DB, ctx_for
from apps.verifactu.tests.test_services import create, ticket
from base.models import Hub
from base.tenancy.tests.business import A

pytestmark = HUB_DB


def test_a_records_total_reaches_the_model_as_the_screen_shows_it(issuer):
    Hub.objects.update_or_create(slug=A.key, defaults={"name": "Bar A", "country": "ES"})
    record = create(ticket(price=100)).record
    call = {"call_id": "c1", "name": shared.tool_name("verifactu.record.get"), "arguments": json.dumps({"record_id": str(record.id)})}
    asked = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "c1", "type": "function", "function": {"name": call["name"], "arguments": call["arguments"]}}],
    }
    turn = get("base.assistant.turn")
    data = {"messages": [{"role": "user", "content": "¿De cuánto es el tique?"}, asked], "pending": [call]}
    plan = turn(ctx_for("hub_owner", language="es"), turn.input.model_validate(data)).model_dump(mode="json")
    [result] = plan["append"]
    assert json.loads(result["content"])["total_amount"] == "1,21\xa0€"
