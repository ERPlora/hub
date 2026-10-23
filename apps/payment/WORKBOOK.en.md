<!-- generated from WORKBOOK.md sha256:ed3044b02e8f28cba83449547543b057b3170825d3c9582d673166aae208237e -->

## What it is for and who it is for

Payments records the **money that goes out** of the business: what is paid to a supplier, a transfer,
a refund that is not a sale's. Each payment carries its own reference (`PAY-YYYYMMDD-NNNN`) and goes
up a ladder of statuses — **Draft**, **Approved**, **Sent**, **Completed** — or is **Cancelled** —,
and keeps who recorded it, who approved it and when each step happened.

It is the opposite of the till's charge. A **payment method** in this app is **where the business pays
from** (its bank account, its company card, the cash in the drawer), not how the customer pays: the
till's tenders (Cash, Card…) belong to **Sales** and have nothing to do with these. **Payments moves no
money**: it talks to no bank, generates no SEPA files and runs no transfers; "Sent" and "Completed" are
marked by a person once the bank has done it.

Who uses it:

- The **employee**: only looks at the list of payments and the list of methods.
- The **manager**, the **administrator** and the **owner**: also record payments, mark them as sent and
  as completed, approve and cancel them, and manage the payment methods.

## Reference adopted

- **The till's tenders are settings of the till; paying suppliers is another piece** (accounts
  payable): Odoo separates the Point of Sale payment methods (Point of Sale → Configuration) from the
  vendor payments with their bank or cash journal; Square, Lightspeed and WooCommerce set up their
  tenders in the checkout settings, and paying supplier bills is a separate product (Toast with xtraCHEF
  Bill Pay, Shopify with Shopify Bill Pay, Holded with its Wallet account). That is why Payments does not
  touch the Sales tenders and Sales does not depend on Payments.
- **Approval by statuses, with separation by permissions** (Odoo, Business Central with its payment
  journal and its approval workflows; xtraCHEF only lets you pay approved bills). The ladder and the
  separation of permissions (record ≠ approve) are copied; there is no bank reconciliation and no
  remittances. **Whoever has both permissions can approve what they recorded**, as in QuickBooks (a bill
  created by its own approver is approved:
  https://quickbooks.intuit.com/learn-support/en-us/help-article/manage-workflows/set-use-bill-approval-and-payment-release-workflows/L1IOLL9hv_US_en_US);
  Odoo has no payment approval out of the box (separate modules provide it, by groups). Blocking it
  would leave a one-person business unable to pay. What always stays is the trail: who recorded, who
  approved and when each step happened.
- **A payment method or a tender is never deleted: it is deactivated** (Lightspeed: the built-in tenders
  are not deleted, they are deactivated; Square: they are moved to "deactivated" and can be recovered).
  The payments that used it keep it.

Research and links in the Spanish WORKBOOK, "Para quien lo mantiene · Decisión: Pagos no es Ventas".

## Before you start

1. Payments is not turned on with any type of business: it is turned on from the app store. It turns on
   no other app and needs none: it can be turned on and off on its own.
2. When it is turned on **there is no payment method**. Go to **Payments → Methods** and create at least
   one (PAYMENT-F01), for example "BBVA account" (Bank transfer) or "Till" (Cash).
3. The currency of the payments is the business's (euros while the Hub keeps no other).

## Screens

Payments opens from the **Payments** menu and has two tabs: **Payments** and **Methods**. What a person
cannot do does not show, and the app refuses it even if they try through the API or the assistant.

### Payments

Title "Outgoing payments". A table with the columns **Reference**, **Date**, **Beneficiary**,
**Amount** and **Status** (and **Method**, which can be shown with the column picker). Search box
"Search reference or beneficiary…" (it also searches the supplier invoice reference), column filters —
reference and beneficiary by a piece of the text, the date "from / to", the amount "from / to" in euros,
the status from a list —, sorting by column, list or card view and 50 rows per page. It is sorted by the
**payment date**, the most recent on top (not by the date it was entered).

Each row offers the action that is due, named after what it does: **Approve** (Draft), **Mark as sent**
(Approved) or **Mark as completed** (Sent), and **Cancel payment** while it is neither completed nor
cancelled. A completed or cancelled payment offers none. A cancelled payment shows its reason under the
status; an approved one (and later sent or completed), who approved it ("Approved by …"). While a row
action is working, its button spins and a second tap does nothing.

The **New payment** button opens the "New payment" form: **Method**, **Date** (today's comes filled
in), **Amount**, **Beneficiary**, **Concept** and, if wanted, **Beneficiary IBAN** and **Supplier
invoice** (its number).

### Methods

A table with **Name**, **Type** (Cash, Bank transfer, Card, SEPA, Cheque or Other), **Account** (the
reference of the bank account, covered except for its last four characters: an IBAN shows as
`ES** **** **** **** **** 1332`; whole when editing the method) and **Status** (Active or Deactivated).
Search box "Search method…", type and status filters, 50 rows per page, sorted by name. **New method**
opens the form; a row (or its **Edit**) opens "Editing method — {name}"; each row offers **Deactivate**
or **Activate**.

## States of each screen

| State | What the person sees |
|---|---|
| Loading | "Loading…" while the first result arrives. |
| Empty | "No payments." or "No payment methods."; with a search or a filter, "No results". |
| Error | The table's notice with "Retry". A refusal of the form shows inside the form, each reason under its field, without losing what was typed; that of a row action, above the table. |
| Reconnecting | What is painted stays; a strip warns "Reconnecting…". |
| App inactive | "This app is not active in this business". |
| No permission | What they cannot do does not show; if they arrive through another door, "You do not have permission". |

Amounts and dates show in the format of the language of whoever looks; the amount, in the payment's
currency.

## Flows

| ID | Flow | Status |
|---|---|---|
| PAYMENT-F01 | Create a payment method | done |
| PAYMENT-F02 | Record a payment | done |
| PAYMENT-F03 | Approve a payment | done |
| PAYMENT-F04 | Mark a payment as sent and as completed | done |
| PAYMENT-F05 | Cancel a payment | done |
| PAYMENT-F06 | Search and review the payments | done |
| PAYMENT-F07 | Announce a completed payment | done |
| PAYMENT-F08 | Edit, deactivate and reactivate a payment method | done |

### PAYMENT-F01 Create a payment method
Status: done
Actor: manager, administrator, owner, assistant
Screen: Methods
Steps:
1. In **Payments → Methods** tap **New method**.
2. Type the **Name**, pick the **Type** (**Bank transfer** comes selected) and, if wanted, the
   **Account** (the reference of the bank account, for example the last digits of the IBAN).
3. Tap **Create method**: the form closes and the method shows in the table as **Active**.
4. From then on it can be picked in the **Method** of "New payment".
In: name, type and account, from the person.
Out: an active method (`payment.method.created`).
If it fails: inside the form, under its field: an empty name; a name that another method already has,
whatever the case ("There is already a payment method with that name. Pick another name."); a type
outside the list. What was typed is kept. With no active method, "New payment" warns "No active payment
methods yet. Create one in Methods before recording a payment.".
Involved: FLOW-F11, FLOW-F21

### PAYMENT-F02 Record a payment
Status: done
Actor: manager, administrator, owner, assistant
Screen: Payments
Steps:
1. In **Payments** tap **New payment**.
2. Pick the **Method** (only the active ones show), leave today's **Date** or set another, type the
   **Amount** as you would write it by hand (12.50; 1,250.00; €12.50), the **Beneficiary** and, if
   wanted, the **Concept**, the **Beneficiary IBAN** and the **Supplier invoice**.
3. Tap **Record payment**.
4. The form closes and the payment shows in the list as **Draft**, with its reference. The list goes by
   the payment date: one with an old date does not show on top.
5. If the connection drops and you tap **Record payment** again in the same form, the payment is
   recorded only once.
In: the form's data; the business's currency. Through the assistant or the API, the method is given by
its id or by its name, the amount goes in cents and, if wanted, an attempt key: repeating the same call
with the same key answers the payment already recorded instead of recording another.
Out: a draft payment with reference `PAY-YYYYMMDD-NNNN` — the date is that of the business day on which
it is recorded, not the payment's; the number counts per day and never repeats — and the notice
`payment.payment.created` (it carries the reference, the beneficiary, the amount and the currency).
If it fails: nothing is saved and no number is spent. Inside the form, under its field: an empty, 0 or
negative amount ("The amount of a payment must be greater than 0."), one that is not a figure ("This is
not an amount. Type a figure, for example 12.50.") or that can be read in two ways ("1.250" can be
€1,250 or €1.25: the decimals must be written); an empty beneficiary; an IBAN that is not valid ("That
IBAN is not valid: check the country, the check digits and the length."); a method that does not exist
("That payment method does not exist in this business.") or is deactivated ("That payment method is
deactivated: pick an active one."). Through the assistant, a method name that matches several says
which ones ("“Till” matches several payment methods: …"). An attempt key that already recorded another
payment is refused ("That attempt key already recorded another payment. Make a new key for each
payment.") and nothing is saved.
Involved: FLOW-F11, FLOW-F21

### PAYMENT-F03 Approve a payment
Status: done
Actor: manager, administrator, owner, assistant
Screen: Payments
Steps:
1. In the row of a payment in **Draft**, tap **Approve**.
2. The row moves to **Approved**.
In: the payment (through the assistant, by its reference).
Out: the status, who approved it and when (the row shows it: "Approved by …"); the notice
`payment.payment.approved`.
If it fails: whoever only records payments (without the approve permission) does not see the action and
the app refuses it. Approving a payment that is no longer a draft changes nothing, tells nobody and says
why ("Only a draft payment can be approved; this one is Approved."), above the table.
Involved: FLOW-F21

### PAYMENT-F04 Mark a payment as sent and as completed
Status: done
Actor: manager, administrator, owner, assistant
Screen: Payments
Steps:
1. In the row of an **Approved** payment, tap **Mark as sent**: it moves to **Sent**.
2. When the bank or the supplier has received it, tap **Mark as completed**: it moves to **Completed**.
In: the payment.
Out: the status; the notices `payment.payment.sent` and `payment.payment.completed`. No money is moved
and no bank is talked to.
If it fails: each step requires the previous one; skipping one changes nothing, announces nothing and
says why ("Only an approved payment can be marked as sent; this one is Draft.", "Only a sent payment can
be marked as completed; …"). A completed or cancelled payment offers no more actions.
Involved: FLOW-F21

### PAYMENT-F05 Cancel a payment
Status: done
Actor: manager, administrator, owner, assistant
Screen: Payments
Steps:
1. In the row of a payment that is neither completed nor cancelled, tap **Cancel payment**.
2. Type the **Cancellation reason** in the form that opens and tap **Cancel payment**.
3. The row moves to **Cancelled** and shows the reason under the status.
In: the payment and the reason (required).
Out: the cancelled status and the reason kept on the payment (nothing is deleted); the notice
`payment.payment.cancelled`.
If it fails: without a reason (or with only spaces) it cannot be tapped; through the assistant, an empty
reason is refused ("Say why this payment is cancelled: the reason stays on the payment."). A completed or
cancelled payment cannot be cancelled ("This payment can no longer be cancelled."), inside the form and
with the reason typed: nothing changes and nothing is announced. An approval is not undone: the payment
is cancelled and another is recorded.
Involved: FLOW-F21

### PAYMENT-F06 Search and review the payments
Status: done
Actor: employee, manager, administrator, owner, assistant
Screen: Payments
Steps:
1. Open **Payments**.
2. Type in the search box a piece of the reference (the last digits, the date), of the beneficiary or of
   the supplier invoice, or use the column filters: the **Date** from one day, up to another or between
   the two; the **Amount** from / to in euros; the **Status** from the list.
3. Sort by the column you need.
In: what the person types.
Out: nothing; read only. The list updates on its own when another person records or changes a payment.
Through the assistant, "the payment PAY-20261014-0003" is read whole, with its method, concept, IBAN and
invoice.
If it fails: if the list does not load, the table says so ("The payments could not be loaded.") with
"Retry", never "No payments.". A filter amount that is not a figure does not filter (never "from 0").
Involved: FLOW-F11

### PAYMENT-F07 Announce a completed payment
Status: done
Actor: system
Screen: none (the automation is created in **Automations**)
Steps:
1. In **Automations**, create an automation that starts with "a payment is completed" (for example, so
   that it leaves you the task of filing the receipt) and turn it on.
2. Mark a payment as **Completed** (PAYMENT-F04).
3. Within a few seconds the automation runs, only once, with that payment's data.
In: the completed payment.
Out: the notice `payment.payment.completed`, with the id, the reference, the status, the amount and the
currency. Each automation waiting for it runs once per payment, even if the notice reaches it twice.
The other steps of a payment (record, approve, send, cancel) and the changes of a method can also be
picked as a trigger.
If it fails: it only goes out when the payment really changes: a refused "complete" announces nothing
and starts nothing. With no automation waiting for it, nothing happens. One business's notice never
starts anything in another. This app listens to no other.
Involved: FLOW-F21

### PAYMENT-F08 Edit, deactivate and reactivate a payment method
Status: done
Actor: manager, administrator, owner, assistant
Screen: Methods
Steps:
1. In **Payments → Methods** tap a row (or its **Edit**): "Editing method — {name}" opens.
2. Change the name, the type or the account and tap **Save**.
3. To stop using it, tap **Deactivate** in its row: it moves to **Deactivated** and no longer shows in
   "New payment". **Activate** brings it back.
In: the method (through the assistant, by its name) and what changes.
Out: the changed method (`payment.method.updated`, `.deactivated`, `.activated`). The payments that
already used it keep it and show its new name.
If it fails: a name that another method already has is refused under Name. Deactivating a deactivated
one or activating an active one changes nothing and says why. A method is never deleted.
Involved: FLOW-F11, FLOW-F21

## Payments: what goes in and what comes out

### What it offers: queries (they read, they change nothing)

| Operation | What it gives | Permission |
|---|---|---|
| `payment.payment.list` | The payments, paginated (≤ 100), with search, filters (reference, beneficiary, concept by a piece; method by id or name, status, currency, IBAN and invoice exact; date and amount by range) and sorting | `payment.view_payment` |
| `payment.payment.get` | A whole payment, by its id or its reference, with its full IBAN | `payment.view_payment` |
| `payment.method.list` | The methods, paginated, with search (name or account), type, status and sorting | `payment.view_payment` |
| `payment.method.get` | A method, by its id or its name, with its full account | `payment.view_payment` |

### What it offers: actions (they change data)

| Operation | What it does | Permission |
|---|---|---|
| `payment.method.create` | Creates an active method | `payment.add_payment` |
| `payment.method.update` | Changes name, type or account (only what is sent) | `payment.add_payment` |
| `payment.method.deactivate` / `.activate` | Takes it out of "New payment" / brings it back | `payment.add_payment` |
| `payment.payment.create` | Records a draft payment with its reference | `payment.add_payment` |
| `payment.payment.approve` | Draft → Approved | `payment.approve_payment` |
| `payment.payment.mark_sent` | Approved → Sent | `payment.add_payment` |
| `payment.payment.mark_completed` | Sent → Completed | `payment.add_payment` |
| `payment.payment.cancel` | Any unfinished one → Cancelled, with a reason | `payment.approve_payment` |

### What it announces

`payment.payment.created`, `.approved`, `.sent`, `.completed`, `.cancelled` and
`payment.method.created`, `.updated`, `.deactivated`, `.activated`; each one in the same transaction as
its change and only if the change happened.

### What it reacts to and what it needs from other apps

Nothing and from nobody: `requires = []`. No other app reads Payments except **Automations**, which
listens to all its notices and offers them as triggers (PAYMENT-F07, FLOW-F21). Its steps can also look
up payments and methods and use the Payments actions that ask for no confirmation (FLOW-F11): record a
payment and create, change, deactivate or activate a method. Approving, marking as sent or completed and
cancelling need a person: an automation does not do them.

### Who can do what

| Role | View | Record, send, complete and manage methods | Approve and cancel |
|---|---|---|---|
| Owner | yes | yes | yes |
| Administrator | yes | yes | yes |
| Manager | yes | yes | yes |
| Employee | yes | no | no |

Whoever has both permissions can approve what they recorded (as today and as QuickBooks; see
"Reference adopted"); the payment keeps who recorded it, who approved it (`approved_by`,
`approved_at`), when it was sent and completed (`sent_at`, `completed_at`) and who cancelled it and when
(`cancelled_by`, `cancelled_at`).
