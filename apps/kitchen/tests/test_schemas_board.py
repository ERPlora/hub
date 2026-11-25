"""The input schemas of the board and of the all-day count: every station, one of them or the dishes with none."""

from apps.kitchen.schemas.board import AllDayIn, BoardIn

from .test_schemas_fields import refuses


def test_the_board_and_the_all_day_count_read_every_station_one_or_none():
    assert BoardIn.model_validate({}).station is None
    assert BoardIn.model_validate({"station": "none"}).station == "none"
    assert AllDayIn.model_validate({"station": "grill"}).station == "grill"
    assert refuses(BoardIn, station="g" * 121)
    assert refuses(AllDayIn, colour="red")
