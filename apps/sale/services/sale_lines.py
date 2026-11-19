"""What a charge writes: the fiscal copy of each part it charged and what ``sale.sale.completed`` carries."""



from apps.sale.models import OrderLine, Sale, SaleLine
from apps.sale.queries.line_parts import combo_name, dishes_of, folded_names, is_child


def _voucher_value(line: OrderLine, session_values: dict) -> int:
    """What the session paying ``line`` is worth to who does it (SALE-F28): what Services fixed on delivering it. An
    unlimited voucher has no sessions to divide its price by (``None``): the price of the line, as a salon's till counts
    it. A line no voucher pays is worth no session."""
    if line.voucher_session_id is None:
        return 0
    value = session_values[line.voucher_session_id]
    return line.unit_price if value is None else value


def _sale_lines(
    sale: Sale, parts: list[OrderLine], valuation, session_values: dict
) -> list[SaleLine]:
    """The fiscal copy of each part charged (``charge_parts``): a line of the check with the names of the
    options charged inside it, and a child line of an option under the line of its dish."""
    rows: list[SaleLine] = []
    of_line: dict = {}
    for position, (line, out) in enumerate(zip(parts, valuation.lines, strict=True), start=1):
        child = is_child(line)
        row = SaleLine(
            sale=sale,
            position=position,
            order_line_id=line.origin.id,
            parent_line_id=of_line[line.origin.id] if child else None,
            modifiers=[] if child else folded_names(line),
            combo_id=line.combo_id,
            combo_name=combo_name(line),
            components=dishes_of(line),
            product_id=line.product_id,
            department_id=line.department_id,
            name=line.name,
            sku=line.sku,
            is_service=line.is_service,
            category_id=line.category_id,
            unit=line.unit,
            quantity=line.quantity,
            unit_price=line.unit_price,
            price_quantity=line.price_quantity,
            pricing_unit=line.pricing_unit,
            cost=line.cost,
            discount_percent=line.discount_percent,
            is_gift=line.is_gift,
            gift_reason=line.gift_reason,
            notes=line.notes,
            staff_id=line.staff_id,
            service_id=line.service_id,
            voucher_session_id=line.voucher_session_id,
            voucher_grant_id=line.voucher_grant_id,
            voucher_name=line.voucher_name,
            voucher_value=_voucher_value(line, session_values),
            tax_category_key=out.tax_category_key,
            tax_rate=out.tax_rate,
            tax_country_code=out.tax_country_code,
            tax_region_code=out.tax_region_code or "",
            tax_rule_id=out.tax_rule_id,
            net_amount=out.net_amount,
            tax_amount=out.tax_amount,
            line_total=out.line_total,
            tax_components=[
                {
                    **c,
                    "rule_id": str(c["rule_id"]) if c["rule_id"] else None,
                    "rate_pct": str(c["rate_pct"]),
                }
                for c in out.tax_components
            ],
        )
        if not child:
            of_line[line.id] = row.id
        rows.append(row)
    return rows


def _completed_payload(  # noqa: PLR0913, PLR0917
    sale, lines, payments, tax_id, address, country, id_type
) -> dict:
    """What ``sale.sale.completed`` carries: Inventory reads ``items``, Customers the customer and total."""
    return {
        "sale_id": str(sale.id),
        "sale_number": sale.number,
        "order_id": str(sale.order_id) if sale.order_id else None,
        "document_type": sale.document_type,
        "tax_included": sale.tax_included,
        "currency": sale.currency,
        "purchased_at": sale.created_at.isoformat(),
        "business_day": sale.business_day.isoformat(),
        "total": sale.total,
        "subtotal": sale.subtotal,
        "tax_amount": sale.tax_total,
        "discount_amount": sale.discount_amount,
        "gift_total": sale.gift_total,
        "customer_id": str(sale.customer_id) if sale.customer_id else None,
        "customer_name": sale.customer_name,
        "customer_tax_id": tax_id,
        "customer_address": address,
        "customer_country": country,
        "customer_id_type": id_type,
        "staff_id": str(sale.staff_id) if sale.staff_id else None,
        "appointment_id": str(sale.appointment_id) if sale.appointment_id else None,
        "payment_method_name": sale.payment_method_name,
        "payments": [
            {
                "method_id": str(payment.method_id),
                "method_name": payment.method_name,
                "method_type": payment.method_type,
                "amount": payment.amount,
                "tendered": payment.tendered,
                "change": payment.change,
                "reference": payment.reference,
            }
            for payment in payments
        ],
        "items_count": len(lines),
        "items": [
            {
                "line_id": str(line.id),
                "order_item_id": str(line.order_line_id)
                if line.order_line_id
                else None,
                "product_id": str(line.product_id) if line.product_id else None,
                "product_name": line.name,
                "quantity": f"{line.quantity:.3f}",
                "unit": line.unit,
                "unit_price": line.unit_price,
                "tax_rate": str(line.tax_rate),
                "tax_category_key": line.tax_category_key,
                "net_amount": line.net_amount,
                "tax_amount": line.tax_amount,
                "line_total": line.line_total,
                "is_gift": line.is_gift,
                "is_service": line.is_service,
                "service_id": str(line.service_id) if line.service_id else None,
                "paid_by_voucher": line.paid_by_voucher,
                "category_id": str(line.category_id) if line.category_id else None,
                "modifiers": line.modifiers,
                "parent_line_id": str(line.parent_line_id) if line.parent_line_id else None,
                "components": [
                    {
                        "product_id": str(dish["product_id"]),
                        "product_name": dish["product_name"],
                        "quantity": f"{dish['quantity'] * line.quantity:.3f}",
                        "is_service": dish["is_service"],
                    }
                    for dish in line.components
                ],
            }
            for line in lines
        ],
    }
