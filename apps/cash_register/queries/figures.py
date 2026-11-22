"""The figures of a session (its X/Z report) and its expected cash, with what a blind count hides."""

from apps.cash_register.models import Movement, Session
from apps.cash_register.queries.lines import CASH, Line, session_lines


def visible_lines(hidden: bool, lines: list[Line]) -> list[Line]:
    """A blind count hides the open session's sale, void and refund lines from whoever counts: only the
    lines written by hand are theirs to see (Square and Lightspeed hide the expected on a blind close)."""
    return [line for line in lines if line.type in Movement.MANUAL] if hidden else lines


def figures(session: Session, lines: list[Line], *, hidden: bool) -> dict:
    """The summary of a session (the X/Z report): totals by type and tender, expected, counted, difference.

    Hidden (a blind count, an open session, a reader without `view_expected_totals`): no total that adds
    up to the expected — only the float, and the lines written by hand counted."""
    # A tender charged and voided in this session cancels out (both stay listed); a void of an earlier one is a refund.
    voids = {line.sale_payment_id for line in lines if line.type == "void"}
    voided_here = voids & {line.sale_payment_id for line in lines if line.type == "sale"}
    counted = [line for line in lines if line.sale_payment_id not in voided_here]
    sales = [line for line in counted if line.type == "sale"]

    def total(of: list[Line]) -> int:
        return sum(line.amount for line in of)

    if hidden:
        return {
            "movement_count": len(visible_lines(True, lines)),
            "opening_balance": session.opening_balance,
            **{
                key: None
                for key in (
                    "total_sales",
                    "cash_sales",
                    "card_sales",
                    "other_sales",
                    "total_refunds",
                    "total_cash_in",
                    "total_cash_out",
                    "total_gifts",
                    "expected_cash",
                )
            },
            "counted": session.closing_balance,
            "difference": session.difference,
        }
    expected = (
        session.expected_balance
        if not session.is_open
        else session.opening_balance + sum(line.cash for line in lines)
    )
    return {
        "movement_count": len(lines),
        "opening_balance": session.opening_balance,
        "total_sales": total(sales),
        "cash_sales": total([line for line in sales if line.method_type == CASH]),
        "card_sales": total([line for line in sales if line.method_type == "card"]),
        "other_sales": total([line for line in sales if line.method_type in ("transfer", "other")]),
        "total_refunds": total([line for line in counted if line.type in ("refund", "void")]),
        "total_cash_in": total([line for line in lines if line.type == "in"]),
        "total_cash_out": total([line for line in lines if line.type == "out"]),
        "total_gifts": sum(line.gift_total for line in sales),
        "expected_cash": expected,
        "counted": session.closing_balance,
        "difference": session.difference,
    }


def expected_now(session: Session) -> int:
    """The real expected cash of an open session (the negative-balance rule reads it, blind or not)."""
    return session.opening_balance + sum(line.cash for line in session_lines(session))
