"""
Hub Core Signals

Global events that any module can emit or listen to.
This provides loose coupling between modules - modules can communicate
without direct dependencies on each other.

Example:
    # Module A emits a signal
    from apps.core.signals import print_ticket_requested

    print_ticket_requested.send(
        sender='sales',
        ticket_type='receipt',
        data={...}
    )

    # Module B listens (if active)
    from apps.core.signals import print_ticket_requested

    @receiver(print_ticket_requested)  # noqa: F821
    def handle_print(sender, ticket_type, data, **kwargs):
        # Handle printing
        pass
"""

from django.dispatch import Signal


# ==============================================================================
# PRINTING SIGNALS
# ==============================================================================

print_ticket_requested = Signal()
"""
Request printing of a ticket/receipt/document.

This is a Hub-level signal that any module can emit to request printing.
If the printers module is active, it will handle the request.
If the printers module is not active, the signal is safely ignored.

Emitted by:
    - sales (receipts)
    - cash_register (cash session reports)
    - inventory (barcode labels)
    - restaurant (kitchen orders)
    - etc.

Handled by:
    - printers module (if active)

Arguments:
    sender (str): Name of the module emitting the signal
    ticket_type (str): Type of ticket to print:
        - 'receipt': Sales receipt
        - 'invoice': Invoice
        - 'kitchen_order': Kitchen order ticket
        - 'barcode_label': Barcode label
        - 'cash_session': Cash session report
    data (dict): Data to render in the ticket template
    printer_id (int, optional): Specific printer ID to use (uses default if not provided)
    priority (int, optional): Priority 1-10, lower number = higher priority (default: 5)
        - 10: Kitchen orders (highest priority)
        - 8: Receipts (high priority)
        - 5: Reports (normal priority)
        - 1: Batch prints (lowest priority)

Example:
    from apps.core.signals import print_ticket_requested

    print_ticket_requested.send(
        sender='sales',
        ticket_type='receipt',
        data={
            'receipt_number': '12345',
            'timestamp': timezone.now(),
            'cashier_name': 'John Doe',
            'items': [
                {'name': 'Product A', 'quantity': 2, 'price': 10.00, 'total': 20.00},
            ],
            'total': 20.00,
            'payment_method': 'Cash',
        },
        priority=8
    )
"""


print_completed = Signal()
"""
Notification that a print job completed successfully.

Emitted by:
    - printers module

Can be listened by:
    - Any module that needs to know when printing completed
    - sales (to show confirmation)
    - analytics (to track print volume)

Arguments:
    sender (str): 'printers'
    print_job_id (int): ID of the completed print job
    ticket_type (str): Type of ticket that was printed
"""


print_failed = Signal()
"""
Notification that a print job failed after all retry attempts.

Emitted by:
    - printers module

Can be listened by:
    - Any module that needs to know when printing failed
    - sales (to show error and offer alternatives)
    - monitoring (to alert admin)

Arguments:
    sender (str): 'printers'
    print_job_id (int): ID of the failed print job
    error (str): Error message describing the failure
"""


# ==============================================================================
# FUTURE: OTHER HUB-LEVEL SIGNALS
# ==============================================================================

# These are examples of other signals that could be added as the system grows:

# sale_completed = Signal()
# """
# Emitted when a sale is completed.
#
# Emitted by: sales
# Can be listened by: inventory (update stock), analytics, loyalty programs
# """

# inventory_updated = Signal()
# """
# Emitted when inventory levels change.
#
# Emitted by: inventory
# Can be listened by: sales (low stock warnings), analytics
# """

# session_opened = Signal()
# """
# Emitted when a cash session is opened.
#
# Emitted by: cash_register
# Can be listened by: analytics, monitoring
# """

# session_closed = Signal()
# """
# Emitted when a cash session is closed.
#
# Emitted by: cash_register
# Can be listened by: analytics, accounting modules
# """

# user_login = Signal()
# """
# Emitted when a user logs in.
#
# Emitted by: accounts
# Can be listened by: analytics, audit logs
# """
