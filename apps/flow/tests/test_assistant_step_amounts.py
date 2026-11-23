"""What the assistant of an «Ask the assistant» step reads of an amount: in the business's currency, as the screens
write it, after a read and after the yes to a change alike; never the cents an app keeps it in."""

import json

from apps.customer.models import Customer
from apps.flow.models import Flow, Question
from base.models import Hub
from base.tests.fake_gateway import gateway

from .conftest import CHAT, HUB_DB, NOON, A, make_flow
from .test_services_assistant_step import said, wants

__all__ = ["gateway"]
pytestmark = HUB_DB

GRANTS = ["customer.customer.stats", "customer.customer.update"]


def told(sent) -> dict:
    """The result the step's last tool sent back to the assistant."""
    [message] = [message for message in sent.body["messages"] if message["role"] == "tool"]
    return json.loads(message["content"])


def asking(worker, gateway, *answers):
    step = {"id": "s1", "kind": "assistant", "prompt": "Customer figures", "tools": GRANTS}
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[step], grants=GRANTS)
    for answer in answers:
        gateway.reply(CHAT, json=answer)
    ran = worker.request("flow.flow.run", {"id": str(flow.id), "input": {}})
    worker()
    return ran


def lucia() -> Customer:
    """A customer who spent 3.60 € in a business in Spain."""
    Hub.objects.update_or_create(slug=A.key, defaults={"name": "Bar A", "country": "ES"})
    return Customer.objects.create(name="Lucía QA", total_purchases=1, total_spent=360)


def test_a_read_tells_the_step_its_amounts_in_the_business_currency(gateway, clock, worker):
    clock(NOON)
    lucia()
    asking(worker, gateway, wants("customer__customer__stats", {}), said("3.60 €"))
    assert told(gateway.sent(CHAT)[1])["total_revenue"] == "3.60 EUR"


def test_after_the_yes_a_change_tells_the_step_its_amounts_in_the_business_currency(gateway, clock, worker):
    clock(NOON)
    card = lucia()
    ran = asking(worker, gateway, wants("customer__customer__update", {"id": str(card.id), "company_name": "QA"}), said("Done"))
    question = Question.objects.get(run_id=ran.id)
    assert question.status == Question.Status.PENDING
    worker.request("flow.question.answer", {"id": str(question.id), "approve": True})
    worker()
    assert told(gateway.sent(CHAT)[1])["total_spent"] == "3.60 EUR"
