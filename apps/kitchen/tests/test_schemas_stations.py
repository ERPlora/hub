"""The input schemas of the stations: a name, a hex colour and closed lists."""

from apps.kitchen.schemas.stations import StationIn, StationPatchIn

from .test_schemas_fields import refuses


def test_a_station_has_a_name_a_hex_colour_and_closed_lists():
    data = StationIn.model_validate({"name": " Grill "})
    assert (
        data.name,
        data.color,
        data.destination,
        data.printer_usage,
        data.is_active,
    ) == (
        "Grill",
        "#F97316",
        "both",
        "kitchen",
        True,
    )
    assert refuses(StationIn, name="")
    assert refuses(StationIn, name="Bar", color="orange")
    assert refuses(StationIn, name="Bar", destination="fax")
    assert refuses(StationPatchIn, station="Bar", printer_usage="receipt")
