"""Reading what the AEAT answers (VERIFACTU-F15, F27, F28), on the AEAT's own answers.

Every case is a real answer of the AEAT's preproduction kept by the current engine
(hub ``crates/plugins/verifactu/tests/fixtures``): accepted, accepted with errors (2007), a duplicate (3000)
of a record the AEAT already had, a SOAP fault (4104) and two queries.
"""

import datetime as dt
from pathlib import Path

import pytest

from apps.verifactu import aeat
from apps.verifactu.envelope import InvoiceRef
from apps.verifactu.tests.conftest import paged

FIXTURES = Path(__file__).parent / "fixtures"


def answer(name: str) -> aeat.SubmissionAnswer:
    return aeat.parse_submission(FIXTURES.joinpath(name).read_text(encoding="utf-8"))


def test_a_clean_acceptance():
    result = answer("desglose_mixed_2026-09-22.xml")
    assert result.fault_code == ""
    assert result.csv == "A-82F5RTZ2AQ9N59"
    assert result.submission_state == "Correcto"
    assert result.wait_seconds == 60
    [line] = result.lines
    assert (line.issuer_nif, line.number, line.issue_date) == (
        "B27593136",
        "DESG-20260922-195855-mixed",
        dt.date(2026, 9, 22),
    )
    assert line.operation == "Alta"
    assert line.status == "accepted"
    assert (line.code, line.message) == ("", "")


REHEARSALS = sorted(
    path.name
    for path in FIXTURES.glob("*_2026-09-2*.xml")
    if "_sent_" not in path.name
    and "consult" not in path.name
    and path.name.split("_")[0] in ("desglose", "foreign", "non", "rotation", "unlisted")
) + ["play_reviewer_answer_2026-09-23.xml"]


@pytest.mark.parametrize("name", REHEARSALS)
def test_every_rehearsal_the_aeat_took_reads_as_accepted(name):
    result = answer(name)
    assert [line.status for line in result.lines] == ["accepted"]
    assert result.csv


def test_there_are_eighteen_rehearsal_answers():
    assert len(REHEARSALS) == 18


def test_accepted_with_errors_keeps_the_aeats_code():
    result = answer("alta_2007_aceptado_con_errores_2026-08-02.xml")
    assert result.submission_state == "ParcialmenteCorrecto"
    [line] = result.lines
    assert line.status == "accepted_with_errors"
    assert line.code == "2007"
    assert line.message.startswith("No debe informarse como primer registro")


def test_a_duplicate_of_a_record_the_aeat_already_registered_is_that_record_accepted():
    # Verified against preproduction (2026-08-02): resending a record the AEAT holds answers 3000 with the
    # original's state; the old engine marked it «Rejected» and broke the chain that followed.
    result = answer("alta_3000_duplicado_tras_rechain_2026-08-02.xml")
    assert result.submission_state == "Incorrecto"
    [line] = result.lines
    assert line.status == "accepted_with_errors"
    assert line.code == "2007"
    assert line.duplicate is True


def test_a_duplicate_of_a_cancelled_record_stays_rejected():
    body = FIXTURES.joinpath(
        "alta_3000_duplicado_tras_rechain_2026-08-02.xml"
    ).read_text(encoding="utf-8")
    result = aeat.parse_submission(body.replace("AceptadaConErrores", "Anulada"))
    [line] = result.lines
    assert line.status == "rejected"
    assert line.code == "3000"


def test_a_rejection_keeps_the_aeats_code_and_message():
    body = FIXTURES.joinpath("alta_2007_aceptado_con_errores_2026-08-02.xml").read_text(
        encoding="utf-8"
    )
    result = aeat.parse_submission(
        body.replace(">AceptadoConErrores<", ">Incorrecto<").replace(">2007<", ">1189<")
    )
    [line] = result.lines
    assert line.status == "rejected"
    assert line.code == "1189"


def test_a_soap_fault_is_read_with_its_code_and_is_permanent_when_the_aeat_says_so():
    result = answer("play_reviewer_seeded_answer_2026-09-23.xml")
    assert result.lines == []
    assert result.fault_code == "4104"
    assert "ObligadoEmision" in result.fault_message
    assert result.permanent_fault is True


def test_another_fault_is_to_retry():
    body = (
        '<?xml version="1.0"?><env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/"><env:Body>'
        "<env:Fault><faultcode>env:Server</faultcode><faultstring>Codigo[2000].Servicio no disponible</faultstring>"
        "</env:Fault></env:Body></env:Envelope>"
    )
    result = aeat.parse_submission(body)
    assert result.fault_code == "2000"
    assert result.permanent_fault is False


@pytest.mark.parametrize("body", ["<html>maintenance</html>", "not xml", "", "<x/>"])
def test_an_answer_that_is_no_aeat_answer_cannot_be_read(body):
    with pytest.raises(aeat.UnreadableAnswer):
        aeat.parse_submission(body)


def test_several_lines_answer_several_records():
    body = FIXTURES.joinpath("desglose_mixed_2026-09-22.xml").read_text(
        encoding="utf-8"
    )
    start = body.index("<tikR:RespuestaLinea>")
    end = body.index("</tikR:RespuestaLinea>") + len("</tikR:RespuestaLinea>")
    line = body[start:end]
    second = line.replace("DESG-20260922-195855-mixed", "DESG-2").replace(
        ">Correcto<", ">Incorrecto<", 1
    )
    second = second.replace(
        "</tikR:EstadoRegistro>",
        "</tikR:EstadoRegistro><tikR:CodigoErrorRegistro>1100</tikR:CodigoErrorRegistro><tikR:DescripcionErrorRegistro>Valor no permitido</tikR:DescripcionErrorRegistro>",
        1,
    )
    result = aeat.parse_submission(body[:end] + second + body[end:])
    assert [(line.number, line.status, line.code) for line in result.lines] == [
        ("DESG-20260922-195855-mixed", "accepted", ""),
        ("DESG-2", "rejected", "1100"),
    ]


# The query (VERIFACTU-F27, F28)


def test_the_query_reads_each_record_and_never_its_previous_ones_fields():
    page = aeat.parse_query(
        FIXTURES.joinpath("consulta_preproduccion_2026-08-01.xml").read_text(
            encoding="utf-8"
        )
    )
    assert (page.more, page.after) == (False, None)
    records = page.records
    assert len(records) == 4
    first = records[0]
    assert first.number == "PRU-20260801-0004"
    assert first.issue_date == dt.date(2026, 8, 1)
    # Encadenamiento/RegistroAnterior carries the previous record's Huella under the same tag: never this one's.
    assert (
        first.fingerprint
        == "3056799E8B154276ED2F71108D8570168FD8FE345428C5270459C90AEFBF3696"
    )
    assert first.state == "Correcto"
    assert first.generated_at == dt.datetime(2026, 8, 1, 18, 38, 11, tzinfo=dt.UTC)
    assert first.issuer_nif == "B27593136"


def test_the_latest_record_is_by_generation_time_not_by_position():
    records = aeat.parse_query(
        FIXTURES.joinpath("rotation_consult_2026-09-22.xml").read_text(encoding="utf-8")
    ).records
    assert len(records) == 44
    latest = aeat.latest(records)
    assert latest.generated_at == max(record.generated_at for record in records)
    assert aeat.latest(list(reversed(records))).generated_at == latest.generated_at


def test_without_records_there_is_no_latest():
    assert aeat.latest([]) is None


def test_a_query_refused_by_the_aeat_is_an_error_not_an_empty_list():
    with pytest.raises(aeat.AeatFault) as refused:
        aeat.parse_query(
            FIXTURES.joinpath("play_reviewer_seeded_answer_2026-09-23.xml").read_text(
                encoding="utf-8"
            )
        )
    assert refused.value.code == "4104"


def test_a_query_page_says_that_more_follow_and_after_which_record():
    body = FIXTURES.joinpath("consulta_preproduccion_2026-08-01.xml").read_text(encoding="utf-8")
    page = aeat.parse_query(paged(body, ("B27593136", "PRU-20260801-0001", "01-08-2026")))
    assert len(page.records) == 4
    assert page.more is True
    assert page.after == InvoiceRef("B27593136", "PRU-20260801-0001", dt.date(2026, 8, 1))


def test_more_pages_without_the_key_to_ask_for_them_is_unreadable():
    body = FIXTURES.joinpath("consulta_preproduccion_2026-08-01.xml").read_text(encoding="utf-8")
    body = body.replace(
        "<tikLRRC:IndicadorPaginacion>N</tikLRRC:IndicadorPaginacion>",
        "<tikLRRC:IndicadorPaginacion>S</tikLRRC:IndicadorPaginacion>",
    )
    with pytest.raises(aeat.UnreadableAnswer, match="ClavePaginacion"):
        aeat.parse_query(body)
