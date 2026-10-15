"""The fiscal arithmetic of a document, pure (no database): the number's format, the breakdown closed once
per fiscal key, the audit that refuses what does not square, and the rectification by differences that
prorates what is left of each key.

Cases taken from the current product's tests (`number_format`, `rectify_from_refund`, `rectify_lines`)
and handler (`invoice#50`, `invoice#65`, the TEAC's four lines of 0.50 € at 21 %).
"""

from decimal import Decimal

import pytest

from apps.invoice import fiscal
from apps.invoice.fiscal import FiscalKey, Line

VAT21 = FiscalKey(
    tax="vat", regime="01", cls="subject", exempt_reason="", rate=Decimal("21.00")
)
VAT10 = FiscalKey(
    tax="vat", regime="01", cls="subject", exempt_reason="", rate=Decimal("10.00")
)
VAT21_RE = FiscalKey(
    tax="vat",
    regime="01",
    cls="subject",
    exempt_reason="",
    rate=Decimal("21.00"),
    surcharge_rate=Decimal("5.20"),
)
EXEMPT = FiscalKey(
    tax="vat", regime="01", cls="exempt", exempt_reason="E1", rate=Decimal("0.00")
)


# The number


@pytest.mark.parametrize(
    ("template", "seq", "expected"),
    [
        ("", 1, "TICKET-2026-000001"),
        ("{prefix}-{year}-{seq:06d}", 42, "TICKET-2026-000042"),
        ("VFT{year}-A-{seq:04d}", 7, "VFT2026-A-0007"),
        # The width is a minimum: the 10,000th invoice with {seq:04d} is written whole.
        ("VFT{year}-A-{seq:04d}", 10000, "VFT2026-A-10000"),
        ("{code}/{seq}", 12, "TICKET/12"),
        # The six-digit fallback survives the millionth invoice.
        ("", 1_000_000, "TICKET-2026-1000000"),
        # An unknown placeholder stays literal.
        ("{prefix}{suffix}{seq:01d}", 3, "TICKET{suffix}3"),
    ],
)
def test_the_number_is_rendered_with_the_series_format(template, seq, expected):
    assert (
        fiscal.render_number(
            template, prefix="TICKET", code="TICKET", year=2026, seq=seq
        )
        == expected
    )


@pytest.mark.parametrize(
    ("template", "valid"),
    [
        ("{prefix}-{year}-{seq:06d}", True),
        ("{year}{seq}", True),
        ("F{year}/{seq:09d}", True),
        (
            "{prefix}-{year}",
            False,
        ),  # every invoice of the series would carry the same number
        ("F{seq:09d}", False),  # next year's series, born from this one, would repeat its numbers
        ("{year}{seq:00d}", False),
        ("{year}{seq:10d}", False),
        ("A\n{year}{seq}", False),
        ("Nº{year}{seq}", False),  # not ASCII: NumSerieFactura refuses it
        ("x" * 50 + "{year}{seq}", False),  # over 60 characters
    ],
)
def test_a_format_needs_the_year_and_a_sequence_on_one_ascii_line(template, valid):
    assert fiscal.format_is_valid(template) is valid


def test_a_series_number_fits_numserie_with_its_widest_sequence():
    assert fiscal.number_fits("", prefix="A" * 20, code="SHOP", year=2026)
    assert not fiscal.number_fits(
        "{prefix}-{prefix}-{prefix}-{year}-{seq}", prefix="A" * 20, code="S", year=2026
    )
    assert not fiscal.number_fits("{prefix}-{year}-{seq}", prefix="Fª", code="S", year=2026)


# Closing what a sale charged: the money never moves


def test_four_lines_of_fifty_cents_vat_included_close_once_for_the_key():
    # The TEAC's case: four 0.50 € lines at 21 % summed per line declared 44 over 200; closed once for
    # the key, 200 charged is base 165 + quota 35, and the lines still add up to what was charged.
    lines = [
        Line(key=VAT21, base=41, tax=9, total=50, category="restaurant.drink")
        for _ in range(4)
    ]
    closed = fiscal.close_charged(lines, tax_included=True)
    assert closed.entries == [fiscal.entry(VAT21, base=165, quota=35)]
    assert [(line.base, line.tax, line.total) for line in closed.lines] == [
        (42, 8, 50),
        (41, 9, 50),
        (41, 9, 50),
        (41, 9, 50),
    ]
    assert (closed.base, closed.tax, closed.total) == (165, 35, 200)


def test_vat_on_top_keeps_the_bases_and_the_charged_quotas():
    # Two categories at the same rate, each closed once by tax at the sale: 0.50 + 0.50 at 21 % charged
    # 11 + 11. Re-rounding the key would declare 21 and invoice a cent less than was charged.
    lines = [
        Line(key=VAT21, base=50, tax=11, total=61, category="product.generic"),
        Line(key=VAT21, base=50, tax=11, total=61, category="service.generic"),
    ]
    closed = fiscal.close_charged(lines, tax_included=False)
    assert closed.entries == [fiscal.entry(VAT21, base=100, quota=22)]
    assert closed.total == 122
    assert closed.tolerance == {VAT21: 2}
    assert (
        fiscal.audit(
            closed.entries, closed.tolerance, base=100, tax=22, invoice_type="F2"
        )
        is None
    )


def test_the_equivalence_surcharge_is_its_own_quota_over_the_same_base():
    lines = [
        Line(key=VAT21_RE, base=1000, tax=262, total=1262, category="product.generic")
    ]
    closed = fiscal.close_charged(lines, tax_included=True)
    assert closed.entries == [
        fiscal.entry(VAT21_RE, base=1000, quota=210, surcharge_quota=52)
    ]
    entry = closed.entries[0]
    assert (entry["rate"], entry["surcharge_rate"]) == ("21.00", "5.20")


def test_each_key_is_one_entry_in_a_stable_order():
    lines = [
        Line(key=VAT10, base=91, tax=9, total=100, category="restaurant.food"),
        Line(key=EXEMPT, base=500, tax=0, total=500, category="service.health"),
        Line(key=VAT21, base=83, tax=17, total=100, category="restaurant.alcohol"),
        Line(key=VAT10, base=91, tax=9, total=100, category="restaurant.drink"),
    ]
    closed = fiscal.close_charged(lines, tax_included=True)
    # vat · 01 · no cause before E1 · subject; inside a key, the higher rate first.
    assert [(entry["qualification"], entry["rate"]) for entry in closed.entries] == [
        ("subject", "21.00"),
        ("subject", "10.00"),
        ("exempt", "0.00"),
    ]
    assert closed.total == 800
    assert sum(line.total for line in closed.lines) == 800


# Closing a manual invoice: VAT on top, computed here


def test_a_manual_key_is_closed_once_and_handed_back_by_largest_remainder():
    # 4 × 2.88 € at 21 %: 60.48 a line, 241.92 the key → 242, printed 61 + 61 + 60 + 60, not 4 × 60.
    lines = [Line(key=VAT21, base=288, tax=0, total=288, category="") for _ in range(4)]
    closed = fiscal.close_manual(lines)
    assert closed.entries == [fiscal.entry(VAT21, base=1152, quota=242)]
    assert [line.tax for line in closed.lines] == [61, 61, 60, 60]
    assert [line.total for line in closed.lines] == [349, 349, 348, 348]
    assert closed.total == 1394


def test_a_manual_surcharge_key():
    closed = fiscal.close_manual(
        [Line(key=VAT21_RE, base=1000, tax=0, total=1000, category="")]
    )
    assert closed.entries == [
        fiscal.entry(VAT21_RE, base=1000, quota=210, surcharge_quota=52)
    ]
    assert (closed.lines[0].tax, closed.lines[0].total) == (262, 1262)


# The audit: nothing is numbered unless it squares


def test_a_quota_that_its_rate_does_not_justify_is_refused():
    failure = fiscal.audit(
        [fiscal.entry(VAT21, base=545, quota=9999)],
        {VAT21: 1},
        base=545,
        tax=9999,
        invoice_type="F1",
    )
    assert failure.code == "invoice.tax_quota_mismatch"


def test_one_cent_of_rounding_per_category_is_honest():
    assert (
        fiscal.audit(
            [fiscal.entry(VAT21, base=100, quota=22)],
            {VAT21: 1},
            base=100,
            tax=22,
            invoice_type="F2",
        )
        is None
    )
    failure = fiscal.audit(
        [fiscal.entry(VAT21, base=100, quota=23)],
        {VAT21: 1},
        base=100,
        tax=23,
        invoice_type="F2",
    )
    assert failure.code == "invoice.tax_quota_mismatch"


def test_only_a_subject_operation_carries_a_quota():
    failure = fiscal.audit(
        [fiscal.entry(EXEMPT, base=500, quota=105)],
        {EXEMPT: 1},
        base=500,
        tax=105,
        invoice_type="F1",
    )
    assert failure.code == "invoice.quota_on_non_subject_class"


def test_the_header_is_the_sum_of_its_breakdown():
    failure = fiscal.audit(
        [fiscal.entry(VAT21, base=1000, quota=210)],
        {VAT21: 1},
        base=1000,
        tax=200,
        invoice_type="F1",
    )
    assert failure.code == "invoice.totals_mismatch"


def test_an_ordinary_document_never_adds_up_below_zero_but_zero_is_honest():
    failure = fiscal.audit(
        [fiscal.entry(VAT21, base=-100, quota=-21)],
        {VAT21: 1},
        base=-100,
        tax=-21,
        invoice_type="F2",
    )
    assert failure.code == "invoice.negative_total"
    assert (
        fiscal.audit(
            [fiscal.entry(VAT21, base=0, quota=0)],
            {VAT21: 1},
            base=0,
            tax=0,
            invoice_type="F2",
        )
        is None
    )
    assert (
        fiscal.audit(
            [fiscal.entry(VAT21, base=-100, quota=-21)],
            {VAT21: 1},
            base=-100,
            tax=-21,
            invoice_type="R1",
        )
        is None
    )


# Rectifying by differences: what is left of each key, prorated


ORIGINAL = [
    fiscal.entry(VAT21, base=1000, quota=210),
    fiscal.entry(VAT10, base=500, quota=50),
]


def test_what_is_left_is_the_original_minus_its_live_rectifications():
    taken = [fiscal.entry(VAT21, base=-500, quota=-105)]
    left = fiscal.remaining(ORIGINAL, [taken])
    assert left == [
        fiscal.entry(VAT21, base=500, quota=105),
        fiscal.entry(VAT10, base=500, quota=50),
    ]


def test_a_partial_refund_is_prorated_over_each_key_and_each_quota_crosses_its_rate():
    part = fiscal.prorate(ORIGINAL, 880)
    assert part == [
        fiscal.entry(VAT21, base=-500, quota=-105),
        fiscal.entry(VAT10, base=-250, quota=-25),
    ]
    assert -sum(e["base"] + e["quota"] + e["surcharge_quota"] for e in part) == 880


def test_two_refunds_that_return_everything_add_up_to_the_original_to_the_cent():
    first = fiscal.prorate(ORIGINAL, 333)
    second = fiscal.prorate(fiscal.remaining(ORIGINAL, [first]), 1760 - 333)
    for key_index in range(2):
        for field in ("base", "quota"):
            assert (
                ORIGINAL[key_index][field]
                + first[key_index][field]
                + second[key_index][field]
                == 0
            )


def test_taking_everything_left_copies_the_figures_without_rounding():
    assert fiscal.prorate(ORIGINAL, 1760) == fiscal.negate(ORIGINAL)


def test_a_refund_of_articles_weighs_only_their_keys_and_never_takes_more_than_is_left():
    left = [
        fiscal.entry(VAT21, base=1000, quota=210),
        fiscal.entry(VAT10, base=1000, quota=100),
    ]
    only_21 = fiscal.prorate(left, 1210, weights=[1210, 0])
    assert [(e["base"], e["quota"]) for e in only_21] == [(-1000, -210), (0, 0)]
    # More money than the articles' key holds: the rest goes to the other key.
    spilled = fiscal.prorate(left, 1500, weights=[1210, 0])
    assert [fiscal.gross_of(e) for e in spilled] == [-1210, -290]
    # No weight at all: by each key's money, as without articles.
    assert fiscal.prorate(left, 1000, weights=[0, 0]) == fiscal.prorate(left, 1000)


def test_a_surcharge_key_is_prorated_with_its_main_rate_first():
    original = [fiscal.entry(VAT21_RE, base=1000, quota=210, surcharge_quota=52)]
    part = fiscal.prorate(original, 631)
    assert part == [fiscal.entry(VAT21_RE, base=-500, quota=-105, surcharge_quota=-26)]


def test_the_key_of_an_entry_survives_the_round_trip():
    assert fiscal.key_of(fiscal.entry(VAT21_RE, base=1, quota=0)) == VAT21_RE
    assert fiscal.key_of(fiscal.entry(EXEMPT, base=1, quota=0)) == EXEMPT


def test_largest_remainder_hands_out_exactly_the_total():
    assert fiscal.allocate(100, [1, 1, 1]) == [34, 33, 33]
    assert fiscal.allocate(0, [5, 5]) == [0, 0]
    assert fiscal.allocate(7, [0, 0]) == [7, 0]
    assert sum(fiscal.allocate(242, [288, 288, 288, 288])) == 242
