<!-- generated from WORKBOOK.md sha256:2395aace94513f447da014d5af558ecc1e6b4674263f0ea9826b39789f8ea1ef -->

## What it is for and who it is for

Cart & Checkout is an **internal notebook of carts and orders**. It keeps **carts** — of a person
(their email and their name) or of an anonymous visit, told apart by a **session code** — with their
lines (product, quantity and price), and turns them into **orders** with a number, addresses, a shipping
and a payment method and a status: **Initiated**, **Paid** or **Failed**, and **Completed**.

The most important thing: **it is not the till and nothing it does is fiscal**. An order paid and
completed here does **not** create a sale, an invoice, a VeriFactu record, a cash movement or a stock
movement, and nothing charged here reaches the AEAT. "Paid" is a status that **a person marks** after
charging some other way: the app charges nothing, talks to no payment gateway and asks for no amount or
receipt. To charge at the counter there is **Sales**.

It has no shop and no public page: only staff with a session in the Hub use it.

Who uses it:

- The **employee**: only looks at the carts and the orders.
- The **manager**, the **administrator** and the **owner**: they also create, abandon and delete
  carts, and mark the orders as paid, completed or failed.
- The **assistant**: does the same as the person talking to it and, besides, what the screen does not
  offer: adding and changing lines, emptying a cart, starting an order and expiring the overdue carts.

## Reference adopted

The cart and order model of an online shop (Shopify Checkout, WooCommerce, Odoo eCommerce): a cart
with a session code, an order with a consecutive number and the statuses initiated → paid or failed →
completed. **Only the status model** is adopted: the public shop, the payment gateway, the taxes,
shipping and stock of those references **do not exist here**. No new research: it is the same scope as
the current product.

## Before you start

1. Cart & Checkout does not come turned on with any type of business: it is turned on from the app store.
   It turns on no other app and needs none: it can be turned on and off on its own.
2. It has no settings. The currency of a new cart is the business's (euros while the Hub keeps no
   other), unless whoever creates it through the assistant or the API says another one.
3. A cart may carry an expiry date; without one it never expires.

## Screens

Cart & Checkout opens from the menu and has two tabs, at the bottom: **Carts** and **Orders**. The top
bar says "Cart & Checkout" and the tab you are on. What a person cannot do does not show, and the app
refuses it even if they try it through the API or the assistant.

### Carts

A table with the columns **Session**, **Email**, **Status** (Active, Abandoned, Converted,
Expired), **Items** and **Total**. A search box "Search session or email…" (it searches the session
code, the email and the name), filters per column behind the funnel of the bar, which opens "Filters" —
session and email by a piece of the text, the status from a list, the items and the total "from / to" —,
sorting per column, a list or card view and 50 rows
per page. It is sorted by creation date, the most recent on top. The total shows in the cart's currency;
the Total filter is typed in the business's currency (in euros: "12" is €12.00) and compares the amount
as it is, without converting currencies. It can be pasted with its thousands separators ("1,250.50")
or with the symbol ("€12.50"); an amount that cannot be read ("1,250", which may be €1,250 or €1.25) is
warned under its box, "Type an amount, like 12.50", and does not filter.

The **New cart** button opens the "New cart" form: **Session** (required; "Save" is not enabled
without it), **Email** and **Name**. Each row offers **Abandon** (only an active cart) and
**Delete** (asks for confirmation). **There is no screen for the lines** of a cart nor for adding them:
the assistant or the API does that.

### Orders

A table with **Order** (its number, always whole), **Email**, **Status** (Initiated, Paid, Failed,
Completed), **Payment** (the payment method, as text) and **Total**, in the order's currency. A search box
"Search order or email…", filters per column behind the funnel of the bar (Order, Email, Status, Payment
and Total), sorting per column, a list or card view and 50 rows per page, the most recent on top. A failed order shows its whole reason under the status.

Each row offers the action that fits it: **Mark paid** (Initiated), **Complete** (Paid) and
**Fail** (Initiated or Paid), which opens a form asking for the **reason**. While a row action is
working, its button spins and a second tap does nothing. There is no button to create an order: they are
born from the flow CART_CHECKOUT-F08.

## States of each screen

| State | What the person sees |
|---|---|
| Loading | "Loading…" while the first result arrives. |
| Empty | "No carts." or "No orders."; with a search or a filter, "No results". |
| Error | The table's notice with "Retry". A refusal of a form shows inside the form, each reason under its field, without losing what was typed; that of a row action, above the table. |
| Reconnecting | What is drawn stays; a strip warns "Reconnecting…". |
| App inactive | "This app is not active in this business". |
| No permission | What they cannot do does not show; if they get there another way, "You do not have permission". |

Amounts in the format of the language of whoever looks and in the currency of each row; quantities
without decorative zeros ("2", "0.5").

## Flows

| ID | Flow | Status |
|---|---|---|
| CART_CHECKOUT-F01 | Create a cart | done |
| CART_CHECKOUT-F02 | Add a line to a cart | done |
| CART_CHECKOUT-F03 | Change the quantity of a line or remove it | done |
| CART_CHECKOUT-F04 | Empty a cart | done |
| CART_CHECKOUT-F05 | Abandon a cart | done |
| CART_CHECKOUT-F06 | Delete a cart | done |
| CART_CHECKOUT-F07 | Expire the overdue carts | done |
| CART_CHECKOUT-F08 | Start the order from a cart | done |
| CART_CHECKOUT-F09 | Mark an order as paid | done |
| CART_CHECKOUT-F10 | Record that the payment failed | done |
| CART_CHECKOUT-F11 | Complete an order | done |
| CART_CHECKOUT-F12 | Look up carts, lines and orders | done |
| CART_CHECKOUT-F13 | Tell other apps what happens | done |
| CART_CHECKOUT-F14 | Erase a customer's personal data | done |

### CART_CHECKOUT-F01 Create a cart
Status: done
Actor: manager, administrator, owner, assistant
Screen: Carts
Steps:
1. In **Carts** tap **New cart**.
2. Type the **Session** (the code that tells the visit apart, required) and, if you want, **Email** and
   **Name**.
3. Tap **Save**: the form closes and the cart shows in the list as **Active**, with no lines
   and a zero total.
In: session code (up to 128 characters), email and name, from the person; the assistant or the API
may also give the currency (an ISO 4217 code) and the expiry date.
Out: an active cart in the currency given or, if none is given, the business's
(`cart_checkout.cart.created`).
If it fails: inside the form, under its field: an empty session; a session another cart not deleted
already uses ("There is already a cart with that session."); an email that is not an email; a currency
that does not exist; an expiry that has already passed. What was typed is kept. Without permission, it is refused.
Involved: none

### CART_CHECKOUT-F02 Add a line to a cart
Status: done
Actor: manager, administrator, owner, assistant
Screen: assistant
Steps:
1. Ask the assistant to add a product to a cart, saying the cart (its session, or the customer's email or
   name), the product's reference and name, the quantity and the unit price.
2. Confirm the assistant's card.
3. The line is saved and the cart's totals (items and amount) are recalculated.
In: the cart; the product's reference and name (free text: they are not checked against the
catalogue), optional SKU and variant attributes (size, colour…), a quantity greater than zero and at most
1 000 000 (up to three decimals: "0.5") and a unit price in cents, which **the caller says**.
Out: the line with its total (quantity × price, rounded to the cent, half up), the cart's
totals and its last activity (`cart_checkout.item.added`).
If it fails: a cart that does not exist ("That cart does not exist in this business."); several carts for
what was said (it names them and asks which one); a cart that is not active, also an overdue one ("This
cart no longer takes changes: it is Abandoned."); an empty reference or name, a quantity of zero, negative or over
1 000 000, a negative price: each one in its field; a total of the line, or of the cart with it, above
what fits in a cart (€99,999,999,999.99), under the quantity. Nothing is saved.
Involved: none

### CART_CHECKOUT-F03 Change the quantity of a line or remove it
Status: done
Actor: manager, administrator, owner, assistant
Screen: assistant
Steps:
1. Ask the assistant to change the quantity of a line, or to remove it.
2. Confirm the card.
3. With a quantity greater than zero the line changes and its total is recalculated with the price kept
   in the line; with a quantity of zero the line is removed. There is also the order "remove line", which only removes.
4. The cart's totals are recalculated in the same operation.
In: the line (its id) and the quantity; the Hub reads the price from the line, never from the caller.
Out: the line changed or removed, the cart's totals and its last activity
(`cart_checkout.item.updated`, with `removed: true` when the quantity is zero;
`cart_checkout.item.removed` comes from "remove line").
If it fails: a line that does not exist; a cart that is no longer active; a negative quantity or one over 1 000 000; a
total above what fits in a cart, under the quantity. Nothing changes.
Involved: none

### CART_CHECKOUT-F04 Empty a cart
Status: done
Actor: manager, administrator, owner, assistant
Screen: assistant
Steps:
1. Ask the assistant to empty a cart.
2. Confirm the card.
3. All its lines are removed and the totals go back to zero; the cart stays **Active**.
In: the cart.
Out: the cart with no lines, totals at zero (`cart_checkout.cart.cleared`). Emptying one that was already
empty changes nothing and announces nothing.
If it fails: a cart that does not exist or is not active. Nothing changes.
Involved: none

### CART_CHECKOUT-F05 Abandon a cart
Status: done
Actor: manager, administrator, owner, assistant
Screen: Carts
Steps:
1. In **Carts**, on the row of an active cart, tap **Abandon**.
2. The cart becomes **Abandoned** and keeps its lines. The assistant may give a reason, which stays
   in the cart.
In: the cart and an optional reason (up to 500 characters).
Out: status Abandoned (`cart_checkout.cart.abandoned`).
If it fails: only an active cart is abandoned; in another status it is refused saying which one it is in, above
the table, and nothing changes.
Involved: none

### CART_CHECKOUT-F06 Delete a cart
Status: done
Actor: manager, administrator, owner, assistant
Screen: Carts
Steps:
1. In **Carts**, on the row, tap **Delete**.
2. Confirm "Delete the cart …?" with **Delete**; **Cancel** leaves it as it was.
3. The cart disappears from the list. The assistant asks for a stronger confirmation (a dangerous action).
In: the cart.
Out: the cart deleted in any status, also Converted (`cart_checkout.cart.deleted`). Its
orders still exist and its session is free for another cart.
If it fails: a cart that does not exist (or is already deleted) is refused; nothing changes.
Involved: none

### CART_CHECKOUT-F07 Expire the overdue carts
Status: done
Actor: system (scheduled task), administrator, assistant
Screen: Carts (the status)
Steps:
1. An active cart whose expiry date has already passed **reads as Expired** in the list, in its
   detail and in the status filter, and no longer takes changes or orders.
2. Every fifteen minutes, the app's task stores it as Expired. The assistant or the API can also be asked
   to "expire the overdue carts".
In: nothing; the Hub sets the time.
Out: the overdue carts become Expired and the order says how many
(`cart_checkout.cart.expired`, with the number; with none it announces nothing).
If it fails: with no overdue carts it answers "0" and announces nothing. A cart with no expiry never expires. With the
list already open, a cart that expires at that moment still shows "Active" until the list is read
again: with the next change, when it is opened again or with the Hub's safety re-read (every 5
minutes). When the order is given by someone of the business, through the assistant or the API, the open list
is brought up to date at that moment.
Involved: none

### CART_CHECKOUT-F08 Start the order from a cart
Status: done
Actor: manager, administrator, owner, assistant
Screen: assistant
Steps:
1. Ask the assistant to start the order of a cart and, if you want, the customer's email, the
   shipping and billing addresses, the shipping method, the payment method and some notes.
2. Confirm the card.
3. An **Initiated** order shows in **Orders** with the number `OS-YYYYMMDD-NNNN` (consecutive per day
   of the business, with no gaps) and the cart's total copied at that moment, in its currency.
In: the cart; the customer's email (without it, the cart's); addresses (if the billing one is missing the
shipping one is copied); shipping and payment methods (text) and notes.
Out: an Initiated order with the cart's total at that instant (`cart_checkout.checkout.initiated`).
The cart stays active, so its lines can be changed and another order started, with the
next number; the order's total no longer changes.
If it fails: a cart that does not exist, is not active (also overdue) or has no lines; an email that is missing or
is not an email. No order is created, **no number is used up** and nothing is announced.
Involved: none

### CART_CHECKOUT-F09 Mark an order as paid
Status: done
Actor: manager, administrator, owner, assistant
Screen: Orders
Steps:
1. Charge the customer outside this app.
2. In **Orders**, on the row of an Initiated order, tap **Mark paid**.
3. The order becomes **Paid** with the time of the payment.
In: the order (by its number or its id).
Out: status Paid and time of the payment (`cart_checkout.order.paid`). Nothing is charged and no amount, method
or receipt is asked for, and no sale, invoice, fiscal record, cash movement or stock movement is created. The
assistant asks for a stronger confirmation.
If it fails: only an Initiated order is marked; in another status it is refused saying which one it is in. The
employee cannot.
Involved: none

### CART_CHECKOUT-F10 Record that the payment failed
Status: done
Actor: manager, administrator, owner, assistant
Screen: Orders
Steps:
1. In **Orders**, on the row of an Initiated or Paid order, tap **Fail**.
2. Type the **reason** (required; "Fail order" is not enabled without it) and tap **Fail order**;
   **Keep it** leaves it as it was.
3. The order becomes **Failed** and shows its whole reason under the status.
In: the order and the reason (up to 500 characters).
Out: status Failed, the reason and the time (`cart_checkout.order.failed`). An order already Paid can also
fail, as today: **it leaves no trace of a refund** (there are no refunds in this app). The cart
stays as it was. The assistant asks for a stronger confirmation.
If it fails: a Completed or already Failed order is refused; an empty reason, under its field, without losing
what was written.
Involved: none

### CART_CHECKOUT-F11 Complete an order
Status: done
Actor: manager, administrator, owner, assistant
Screen: Orders
Steps:
1. In **Orders**, on the row of a Paid order, tap **Complete**.
2. The order becomes **Completed** and its cart, **Converted**, in the same operation.
In: the order.
Out: order Completed with its time and cart Converted (`cart_checkout.order.completed`). Nothing
fiscal or of stock. If the cart was already deleted, the order is completed all the same.
If it fails: only a Paid order is completed; in another status it is refused saying which one it is in.
Involved: none

### CART_CHECKOUT-F12 Look up carts, lines and orders
Status: done
Actor: employee, manager, administrator, owner, assistant
Screen: Carts, Orders
Steps:
1. Open **Carts** or **Orders**.
2. Search by session, email or name (carts) or by order number or email (orders) and sort. To filter
   per column, tap the funnel of the bar: it opens "Filters" with a box per column (the Total, as it is
   typed or pasted: "12", "12.50", "1,250.50"); **Apply** filters and closes it, and the funnel counts
   the filters in use.
3. The lines of a cart and the detail of an order (addresses, methods, dates, notes) are read with
   the assistant or the API: a cart by its session or by its customer's email or name, an order
   by its number.
In: the "view carts" permission (the employee has it).
Out: lists of 50 rows (up to 100 per request). Quantities with their decimals, amounts in cents
with the row's currency.
If it fails: a loading error with "Retry"; without permission, "You do not have permission"; a Total amount that
cannot be read, "Type an amount, like 12.50" under its box, without filtering.
Involved: none

### CART_CHECKOUT-F13 Tell other apps what happens
Status: done
Actor: system
Screen: none
Steps:
1. Each change of the previous flows leaves a notice in the Hub's outbox in its same transaction.
2. Both screens update by themselves with what changed.
In: the change that causes it.
Out: thirteen notices: the twelve of the current product (`cart.created`, `cart.abandoned`, `cart.deleted`,
`cart.cleared`, `cart.expired`, `item.added`, `item.updated`, `item.removed`, `checkout.initiated`,
`order.paid`, `order.failed`, `order.completed`) and `customer.erased`, with the prefix `cart_checkout.`.
Only Automations listens to them, and it can start an automation with any of them; no
other app of the Hub listens to them.
If it fails: a refused change leaves neither the change nor the notice.
Involved: FLOW-F21 (Automations starts with any notice of the business)

### CART_CHECKOUT-F14 Erase a customer's personal data
Status: done
Actor: manager, administrator, owner, assistant; the platform staff from the admin
Screen: assistant; the Hub's admin (action "Erase the personal data of their customers")
Steps:
1. A customer asks for their data to be erased (right to erasure, GDPR).
2. Ask the assistant to erase the customer's data with their exact email, or the platform staff
   select their carts or orders in the admin and run the action.
3. Confirm the card (a dangerous action: it cannot be undone).
In: the customer's exact email (case-insensitive).
Out: every cart with that email, also the deleted ones, is left without email, name, notes or
abandon reason; every order with that email or from those carts, without email, addresses, notes or
failure reason. Number, amounts, statuses and dates stay. It says how many carts and orders it changed
(`cart_checkout.customer.erased`, with both numbers and never the email; if there was nothing, it announces nothing).
If it fails: an empty email or one that is not an email, in its field. Without the "manage carts" permission, it is refused.
In the admin, with no hub chosen it does nothing and says so.
Involved: none

## Cart & Checkout: what goes in and what comes out

### What it offers: queries (they read and change nothing)

| Operation | What it gives |
|---|---|
| `cart_checkout.cart.list` | Carts, with search, filters, sorting and pages of up to 100. |
| `cart_checkout.cart.get` | A cart with its lines, by id, session or customer (email or name). |
| `cart_checkout.item.list` | The lines of a cart, with search, filters and pages. |
| `cart_checkout.item.get` | A line by its id. |
| `cart_checkout.order.list` | Orders, with search, filters, sorting and pages of up to 100. |
| `cart_checkout.order.get` | An order with everything (addresses, methods, dates, notes), by id or number. |

### What it offers: actions (they change data)

| Operation | What it does | Permission |
|---|---|---|
| `cart_checkout.cart.create` | Creates a cart | manage carts |
| `cart_checkout.cart.mark_abandoned` | Abandons an active cart | manage carts |
| `cart_checkout.cart.delete` | Deletes a cart (dangerous) | manage carts |
| `cart_checkout.cart.clear` | Empties an active cart | manage carts |
| `cart_checkout.cart.cleanup_expired` | Expires the overdue carts (also the task) | manage carts |
| `cart_checkout.item.add` | Adds a line | manage carts |
| `cart_checkout.item.update` | Changes the quantity (0 removes it) | manage carts |
| `cart_checkout.item.remove` | Removes a line | manage carts |
| `cart_checkout.checkout.initiate` | Starts an order from a cart | check out |
| `cart_checkout.order.mark_paid` | Marks an order paid (dangerous) | check out |
| `cart_checkout.order.fail` | Marks an order failed with its reason (dangerous) | check out |
| `cart_checkout.order.complete` | Completes a paid order and converts its cart | check out |
| `cart_checkout.customer.erase` | Erases a customer's personal data by their email (dangerous) | manage carts |

### What it announces

The thirteen notices of CART_CHECKOUT-F13. They only go out when the change happened.

### What it reacts to and what it needs from other apps

Nothing. It reads and writes nothing in other apps: product, reference, SKU and price are free text and numbers,
with no link to Inventory, and the customer is an email and a name with no link to Customers.

### Who can do what

| Permission | What it lets you do | Who has it |
|---|---|---|
| `cart_checkout.view_cart` | View carts, lines and orders | everyone, also the employee |
| `cart_checkout.manage_cart` | Create, abandon, delete, empty and expire carts; add, change and remove lines; erase a customer's personal data | manager, administrator, owner |
| `cart_checkout.checkout` | Start orders and mark them paid, failed or completed | manager, administrator, owner |
