"""
ERPlora Signal System

Django signals for loose coupling between modules. Signals notify that
something happened - listeners react but cannot modify the original event.

Use signals when:
- You want to notify that something happened (broadcast)
- Listeners should react independently (logging, analytics, side effects)
- The emitter doesn't care if anyone is listening

Use hooks (apps.core.hooks) instead when:
- You want to modify data or behavior
- You need to intercept and potentially block an action

Example - Emitting a signal:
    from apps.core.signals import sale_completed

    def complete_sale(request):
        sale = Sale.objects.create(...)

        # Notify all listeners
        sale_completed.send(
            sender='sales',
            sale=sale,
            user=request.user
        )

        return sale

Example - Listening to a signal:
    from django.dispatch import receiver
    from apps.core.signals import sale_completed

    @receiver(sale_completed)
    def award_loyalty_points(sender, sale, user, **kwargs):
        if sale.customer_id:
            LoyaltyMember.add_points(sale.customer_id, sale.total * 0.01)

    @receiver(sale_completed)
    def update_inventory(sender, sale, **kwargs):
        for item in sale.items.all():
            Product.objects.filter(id=item.product_id).update(
                stock=F('stock') - item.quantity
            )
"""

from django.dispatch import Signal


# ==============================================================================
# PRINTING SIGNALS
# ==============================================================================

print_ticket_requested = Signal()
"""
Request printing of a ticket/receipt/document.

Emitted by: sales, cash_register, inventory, invoicing
Handled by: printers module (if active)

Arguments:
    sender (str): Module name ('sales', 'inventory', etc.)
    ticket_type (str): 'receipt', 'invoice', 'kitchen_order', 'barcode_label', 'cash_session'
    data (dict): Data to render in the ticket template
    printer_id (int, optional): Specific printer ID
    priority (int, optional): 1-10, lower = higher priority
"""

print_completed = Signal()
"""
Notification that a print job completed successfully.

Emitted by: printers
Arguments:
    sender (str): 'printers'
    print_job_id (int): ID of the completed print job
    ticket_type (str): Type of ticket that was printed
"""

print_failed = Signal()
"""
Notification that a print job failed.

Emitted by: printers
Arguments:
    sender (str): 'printers'
    print_job_id (int): ID of the failed print job
    error (str): Error message
"""


# ==============================================================================
# SALES SIGNALS
# ==============================================================================

sale_created = Signal()
"""
Emitted when a new sale is created (before payment).

Emitted by: sales
Arguments:
    sender (str): 'sales'
    sale: Sale model instance
    user: User who created the sale
    cart_data (dict): Original cart data
"""

sale_completed = Signal()
"""
Emitted when a sale is completed (payment successful).

Emitted by: sales
Listened by: inventory (stock), loyalty (points), invoicing, analytics

Arguments:
    sender (str): 'sales'
    sale: Sale model instance
    user: User who completed the sale
    payment_method (str): 'cash', 'card', 'transfer', 'mixed'
"""

sale_cancelled = Signal()
"""
Emitted when a sale is cancelled.

Emitted by: sales
Arguments:
    sender (str): 'sales'
    sale: Sale model instance
    user: User who cancelled
    reason (str): Cancellation reason
"""

sale_refunded = Signal()
"""
Emitted when a sale is refunded (partial or full).

Emitted by: sales, returns
Arguments:
    sender (str): 'sales' or 'returns'
    sale: Original Sale instance
    refund_amount: Decimal amount refunded
    items: List of refunded items (if partial)
    user: User who processed refund
"""


# ==============================================================================
# INVENTORY SIGNALS
# ==============================================================================

product_created = Signal()
"""
Emitted when a new product is created.

Emitted by: inventory
Arguments:
    sender (str): 'inventory'
    product: Product model instance
    user: User who created it
"""

product_updated = Signal()
"""
Emitted when a product is updated.

Emitted by: inventory
Arguments:
    sender (str): 'inventory'
    product: Product model instance
    user: User who updated
    changed_fields (list): List of field names that changed
"""

product_deleted = Signal()
"""
Emitted when a product is deleted.

Emitted by: inventory
Arguments:
    sender (str): 'inventory'
    product_id: ID of deleted product
    product_name (str): Name for reference
    user: User who deleted
"""

stock_changed = Signal()
"""
Emitted when stock level changes.

Emitted by: inventory, sales, returns
Arguments:
    sender (str): Module that caused the change
    product_id: Product ID
    product_name (str): Product name
    old_quantity: Previous stock level
    new_quantity: New stock level
    change_reason (str): 'sale', 'return', 'adjustment', 'reception', 'loss'
    reference_id: ID of related document (sale_id, etc.)
"""

low_stock_alert = Signal()
"""
Emitted when stock falls below minimum level.

Emitted by: inventory
Arguments:
    sender (str): 'inventory'
    product: Product instance
    current_stock: Current quantity
    minimum_stock: Configured minimum
"""


# ==============================================================================
# CUSTOMER SIGNALS
# ==============================================================================

customer_created = Signal()
"""
Emitted when a new customer is created.

Emitted by: customers
Listened by: loyalty (create member), crm, email

Arguments:
    sender (str): 'customers'
    customer: Customer model instance
    user: User who created
"""

customer_updated = Signal()
"""
Emitted when a customer is updated.

Emitted by: customers
Arguments:
    sender (str): 'customers'
    customer: Customer model instance
    user: User who updated
    changed_fields (list): Fields that changed
"""

customer_deleted = Signal()
"""
Emitted when a customer is deleted.

Emitted by: customers
Arguments:
    sender (str): 'customers'
    customer_id: ID of deleted customer
    customer_name (str): Name for reference
    user: User who deleted
"""


# ==============================================================================
# CASH REGISTER SIGNALS
# ==============================================================================

cash_session_opened = Signal()
"""
Emitted when a cash session/shift is opened.

Emitted by: cash_register
Arguments:
    sender (str): 'cash_register'
    session: CashSession model instance
    user: User who opened
    initial_amount: Opening cash amount
"""

cash_session_closed = Signal()
"""
Emitted when a cash session/shift is closed.

Emitted by: cash_register
Listened by: analytics, accounting, hr (shifts)

Arguments:
    sender (str): 'cash_register'
    session: CashSession model instance
    user: User who closed
    final_amount: Closing cash amount
    expected_amount: Expected amount
    difference: Overage/shortage
"""

cash_movement_created = Signal()
"""
Emitted when cash is added or removed from register.

Emitted by: cash_register
Arguments:
    sender (str): 'cash_register'
    movement: CashMovement model instance
    session: Related CashSession
    movement_type (str): 'in' or 'out'
    amount: Movement amount
    reason (str): Reason for movement
"""


# ==============================================================================
# INVOICING SIGNALS
# ==============================================================================

invoice_created = Signal()
"""
Emitted when an invoice is created.

Emitted by: invoicing
Arguments:
    sender (str): 'invoicing'
    invoice: Invoice model instance
    sale: Related Sale (if any)
    user: User who created
"""

invoice_sent = Signal()
"""
Emitted when an invoice is sent to customer.

Emitted by: invoicing
Arguments:
    sender (str): 'invoicing'
    invoice: Invoice model instance
    method (str): 'email', 'print', 'download'
    recipient (str): Email or destination
"""

invoice_paid = Signal()
"""
Emitted when an invoice is marked as paid.

Emitted by: invoicing
Arguments:
    sender (str): 'invoicing'
    invoice: Invoice model instance
    payment_method (str): How it was paid
    payment_date: When it was paid
"""


# ==============================================================================
# SECTIONS (TABLES/AREAS) SIGNALS
# ==============================================================================

table_opened = Signal()
"""
Emitted when a table is opened/occupied.

Emitted by: sections
Arguments:
    sender (str): 'sections'
    table: Table model instance
    area: Area the table belongs to
    guests (int): Number of guests
    user: User who opened the table
"""

table_closed = Signal()
"""
Emitted when a table is closed/freed.

Emitted by: sections
Arguments:
    sender (str): 'sections'
    table: Table model instance
    duration_minutes (int): How long it was occupied
    sale: Related Sale (if any)
"""

table_transferred = Signal()
"""
Emitted when a sale is transferred between tables.

Emitted by: sections
Arguments:
    sender (str): 'sections'
    from_table: Original table
    to_table: Destination table
    sale: Sale being transferred
    user: User who transferred
"""


# ==============================================================================
# LOYALTY SIGNALS
# ==============================================================================

points_earned = Signal()
"""
Emitted when a customer earns loyalty points.

Emitted by: loyalty
Arguments:
    sender (str): 'loyalty'
    member: LoyaltyMember instance
    points (int): Points earned
    sale: Related sale
    reason (str): 'purchase', 'bonus', 'referral'
"""

points_redeemed = Signal()
"""
Emitted when a customer redeems loyalty points.

Emitted by: loyalty
Arguments:
    sender (str): 'loyalty'
    member: LoyaltyMember instance
    points (int): Points redeemed
    reward: Reward claimed (if any)
    discount_amount: Discount applied
"""

tier_changed = Signal()
"""
Emitted when a customer's loyalty tier changes.

Emitted by: loyalty
Arguments:
    sender (str): 'loyalty'
    member: LoyaltyMember instance
    old_tier: Previous tier
    new_tier: New tier
    direction (str): 'upgrade' or 'downgrade'
"""


# ==============================================================================
# USER/AUTH SIGNALS
# ==============================================================================

user_logged_in = Signal()
"""
Emitted when a user logs in to the Hub.

Emitted by: accounts
Arguments:
    sender (str): 'accounts'
    user: LocalUser instance
    method (str): 'pin', 'sso', 'password'
    ip_address (str): Client IP
"""

user_logged_out = Signal()
"""
Emitted when a user logs out.

Emitted by: accounts
Arguments:
    sender (str): 'accounts'
    user: LocalUser instance
    session_duration (int): Session length in seconds
"""


# ==============================================================================
# MODULE LIFECYCLE SIGNALS
# ==============================================================================

module_activated = Signal()
"""
Emitted when a module is activated.

Emitted by: modules_runtime
Arguments:
    sender (str): 'modules_runtime'
    module_id (str): ID of activated module
    module_name (str): Display name
    version (str): Module version
"""

module_deactivated = Signal()
"""
Emitted when a module is deactivated.

Emitted by: modules_runtime
Arguments:
    sender (str): 'modules_runtime'
    module_id (str): ID of deactivated module
    module_name (str): Display name
"""

module_updated = Signal()
"""
Emitted when a module is updated to a new version.

Emitted by: modules_runtime
Arguments:
    sender (str): 'modules_runtime'
    module_id (str): ID of updated module
    old_version (str): Previous version
    new_version (str): New version
"""


# ==============================================================================
# SYNC SIGNALS
# ==============================================================================

sync_started = Signal()
"""
Emitted when sync with Cloud starts.

Emitted by: sync
Arguments:
    sender (str): 'sync'
    sync_type (str): 'full', 'incremental', 'modules'
"""

sync_completed = Signal()
"""
Emitted when sync with Cloud completes.

Emitted by: sync
Arguments:
    sender (str): 'sync'
    sync_type (str): Type of sync
    duration_seconds (float): How long it took
    records_synced (int): Number of records
    errors (list): Any errors encountered
"""

sync_failed = Signal()
"""
Emitted when sync with Cloud fails.

Emitted by: sync
Arguments:
    sender (str): 'sync'
    sync_type (str): Type of sync
    error (str): Error message
    can_retry (bool): Whether retry is possible
"""
