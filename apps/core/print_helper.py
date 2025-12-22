"""
Print Helper

Utility functions to make it easy for modules to request printing
without knowing anything about printers configuration.

Usage example in any module:
    from apps.core.print_helper import print_receipt, print_kitchen_order

    # Print a receipt (module doesn't care which printer)
    print_receipt(
        receipt_id='SALE-123',
        items=[...],
        total=50.00,
        payment_method='Cash'
    )

    # Print kitchen order (automatically routes to kitchen printer if configured)
    print_kitchen_order(
        order_number='#42',
        table='Table 5',
        items=[...]
    )
"""

from apps.core.signals import print_ticket_requested


def print_receipt(receipt_id, items, total, **kwargs):
    """
    Print a sales receipt.

    The printers module will automatically route this to the configured
    receipt printer (or default printer if none configured).

    Args:
        receipt_id (str): Unique receipt identifier
        items (list): List of items with name, quantity, price, total
        total (float): Total amount
        **kwargs: Additional data (payment_method, paid, change, customer_name, etc.)

    Example:
        print_receipt(
            receipt_id='SALE-123',
            items=[
                {'name': 'Product A', 'quantity': 2, 'price': 10.00, 'total': 20.00},
                {'name': 'Product B', 'quantity': 1, 'price': 30.00, 'total': 30.00},
            ],
            total=50.00,
            payment_method='Cash',
            paid=50.00,
            change=0.00
        )
    """
    data = {
        'receipt_id': receipt_id,
        'items': items,
        'total': total,
        **kwargs
    }

    print_ticket_requested.send(
        sender='sales',  # Can be dynamic if needed
        ticket_type='receipt',
        data=data,
        priority=8  # High priority (receipts should print fast)
    )


def print_delivery_note(note_id, items, **kwargs):
    """
    Print a delivery note (albarán).

    Routes to delivery note printer if configured, otherwise default.

    Args:
        note_id (str): Delivery note identifier
        items (list): List of items with name, quantity, price
        **kwargs: Additional data (customer_name, delivery_address, etc.)

    Example:
        print_delivery_note(
            note_id='DN-456',
            items=[...],
            customer_name='John Doe',
            delivery_address='123 Main St'
        )
    """
    data = {
        'receipt_id': note_id,
        'items': items,
        'is_delivery_note': True,
        **kwargs
    }

    print_ticket_requested.send(
        sender='sales',
        ticket_type='delivery_note',
        data=data,
        priority=7
    )


def print_invoice(invoice_id, items, subtotal, tax_amount, total, **kwargs):
    """
    Print an invoice.

    Routes to invoice printer if configured, otherwise default.

    Args:
        invoice_id (str): Invoice identifier
        items (list): List of items
        subtotal (float): Subtotal before tax
        tax_amount (float): Tax amount
        total (float): Total including tax
        **kwargs: Additional data (customer details, payment terms, etc.)

    Example:
        print_invoice(
            invoice_id='INV-789',
            items=[...],
            subtotal=100.00,
            tax_amount=21.00,
            total=121.00,
            customer_name='ACME Corp',
            vat_number='B12345678'
        )
    """
    data = {
        'receipt_id': invoice_id,
        'items': items,
        'subtotal': subtotal,
        'tax_amount': tax_amount,
        'total': total,
        'is_invoice': True,
        **kwargs
    }

    print_ticket_requested.send(
        sender='sales',
        ticket_type='invoice',
        data=data,
        priority=7
    )


def print_kitchen_order(order_number, items, **kwargs):
    """
    Print a kitchen order ticket.

    Routes to kitchen printer if configured. Kitchen orders have
    highest priority to ensure fast food preparation.

    Args:
        order_number (str): Order identifier
        items (list): List of food items to prepare
        **kwargs: Additional data (table, notes, priority, etc.)

    Example:
        print_kitchen_order(
            order_number='#42',
            table='Table 5',
            items=[
                {'name': 'Burger', 'quantity': 2, 'notes': 'No onions'},
                {'name': 'Fries', 'quantity': 1, 'notes': 'Extra crispy'},
            ],
            waiter='John'
        )
    """
    data = {
        'receipt_id': order_number,
        'items': items,
        'is_kitchen_order': True,
        **kwargs
    }

    print_ticket_requested.send(
        sender='restaurant',  # Or 'sales' depending on module
        ticket_type='kitchen_order',
        data=data,
        priority=10  # Highest priority
    )


def print_barcode_label(product_name, barcode, **kwargs):
    """
    Print a barcode label.

    Routes to label printer if configured.

    Args:
        product_name (str): Product name
        barcode (str): Barcode value
        **kwargs: Additional data (price, sku, etc.)

    Example:
        print_barcode_label(
            product_name='Product A',
            barcode='1234567890123',
            price=19.99,
            sku='SKU-001'
        )
    """
    data = {
        'receipt_id': f'LABEL-{barcode}',
        'product_name': product_name,
        'barcode': barcode,
        **kwargs
    }

    print_ticket_requested.send(
        sender='inventory',
        ticket_type='barcode_label',
        data=data,
        priority=5  # Normal priority
    )


def print_cash_session_report(session_id, opening_balance, closing_balance, transactions, **kwargs):
    """
    Print a cash session report.

    Routes to report printer if configured.

    Args:
        session_id (str): Session identifier
        opening_balance (float): Opening cash amount
        closing_balance (float): Closing cash amount
        transactions (list): List of transactions during session
        **kwargs: Additional data (cashier, duration, etc.)

    Example:
        print_cash_session_report(
            session_id='SESSION-123',
            opening_balance=100.00,
            closing_balance=550.00,
            transactions=[...],
            cashier='John Doe',
            started_at='2025-01-01 09:00',
            ended_at='2025-01-01 17:00'
        )
    """
    data = {
        'receipt_id': session_id,
        'opening_balance': opening_balance,
        'closing_balance': closing_balance,
        'transactions': transactions,
        **kwargs
    }

    print_ticket_requested.send(
        sender='cash_register',
        ticket_type='cash_session_report',
        data=data,
        priority=5  # Normal priority
    )


def print_custom(sender, ticket_type, data, priority=5):
    """
    Print a custom document type.

    Use this for custom document types not covered by the helper functions above.

    Args:
        sender (str): Module name emitting the signal
        ticket_type (str): Custom document type
        data (dict): Document data
        priority (int): Priority 1-10 (10=highest, 1=lowest)

    Example:
        print_custom(
            sender='my_module',
            ticket_type='gift_certificate',
            data={'certificate_id': 'GC-123', 'amount': 50.00},
            priority=6
        )
    """
    print_ticket_requested.send(
        sender=sender,
        ticket_type=ticket_type,
        data=data,
        priority=priority
    )
