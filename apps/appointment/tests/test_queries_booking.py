"""What a booking is made of: its services, its professional and the lines it freezes."""

from apps.appointment.queries.booking import lines_for

from .conftest import HUB_DB, assign

pytestmark = HUB_DB


def test_a_line_keeps_the_professionals_own_price_and_length_and_without_one_the_services(salon):
    assign(salon.cut, salon.ana, price=2500, duration=45)

    def frozen(member):
        lines = lines_for(member, [salon.cut, salon.colour])
        return [(line["name"], line["price"], line["duration_minutes"], line["position"]) for line in lines]

    assert frozen(salon.ana) == [("Haircut", 2500, 45, 0), ("Colour", 4500, 60, 1)]
    assert frozen(None) == [("Haircut", 2000, 30, 0), ("Colour", 4500, 60, 1)]
