<!-- generated from WORKBOOK.md sha256:bb0348a63487c043f0db53fa77e906389ddd4d555a1d81e3d69ec6fdc52e5ff3 -->

## What it is for and who it is for

Invoicing turns every charged sale into a **numbered fiscal document** and keeps it forever: the
**ticket** (simplified invoice, F2) of every charge, the **full invoice** (F1) when the customer gives
their tax ID, the **full invoice that replaces a ticket** (F3) the customer already took away, and the
**rectifying invoice** (R1–R5) when money is refunded, a sale is voided or a document was wrong. It is
the link between Sales and VeriFactu in the Spanish fiscal chain (sale → invoice → VeriFactu record
→ AEAT): this is where the series number that later travels to the tax agency is born. It serves the
restaurant and the hair salon alike: nothing in it belongs to one vertical.

Who uses it:

- The **employee** looks at the invoices, prints them, issues an invoice by hand, turns a ticket into a
  full invoice and marks an invoice as paid.
- The **manager**, besides, rectifies and keeps the numbering series.
- The **owner** and the **administrator**, besides, set up the **issuer** (the business's tax identity
  that appears on every invoice).
- The **system**, with nobody in front, invoices every charge and rectifies every refund and every void.

It does not charge or refund money (that is Sales), it sends nothing to the AEAT and does not compute the
fingerprint (that is VeriFactu), and it does not keep the payment method.

## Reference adopted

Here the official specification prevails over the market:

- [RD 1619/2012 (Invoicing Regulation)](https://www.boe.es/buscar/act.php?id=BOE-A-2012-14696):
  full invoice (art. 6: number and series, issue date and operation date if different, name, tax ID
  and address of issuer and recipient, description, base, rate and quota per rate), simplified invoice
  (art. 7), replacement of the ticket by a full invoice, and rectifying invoice with its own series, the
  reference to the invoice it corrects and the correction made (art. 15). Correlative series, a separate
  one for rectifying invoices, as the
  [AEAT](https://sede.agenciatributaria.gob.es/Sede/ayuda/consultas-informaticas/presentacion-declaraciones-ayuda-tecnica/aplicacion-gratuita-verifactu-aeat/emision-facturas.html)
  reminds.
- [SIF / VERI*FACTU](https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu.html)
  (RD 1007/2023, Order HAC/1177/2024): types F1, F2, F3 and R1–R5, rectification by differences
  (`TipoRectificativa` "I") with negative amounts, immutability of the issued document.
- Numbering, checked against Odoo, Business Central, NetSuite, Sage 50, Holded, Lightspeed, Toast,
  Shopify, WooCommerce and Square: the number is assigned in the same operation that saves the document,
  one series per code and year that goes back to 1 every 1 January, a format template that freezes with
  the first number, a preview of the next number without using it up, and the proof that there are no
  gaps.
- The type of rectifying invoice as in Odoo's `l10n_es_edi_verifactu`: R5 for a ticket, R1 ("error
  fundado en derecho y art. 80 Uno, Dos y Seis LIVA", the refund) by default for a full invoice, and
  R2–R4 to choose when rectifying by hand.
- The fiscal number is used up when **charging**, never when opening the bill: the open bill and the
  pre-bill carry no series number.

## Before you start

- Turning Invoicing on also turns on **Sales**, **Taxes** and **Customers** (it requires them).
  **VeriFactu** does not turn on by itself, but in Spain it is needed for every invoice to reach the AEAT.
- **The issuer** (legal name, tax ID and address of the business) is mandatory: **without it no document
  is issued** (Invoicing → Issuer, INVOICE-F21); until then, Home asks for it in "Finish setting up your
  business" with the step "Your business details" and the pill "Needed to invoice", and the banner "You
  cannot issue invoices yet" warns about it above the other screens, **Invoices** and **Series** too,
  with "Set up". The issuer is typed here, by hand: receiving it from the ERPlora account
  (INVOICE-F22) is not in yet.
- **"Today" is Madrid time** in phase 1 (the Hub does not keep the business's time zone yet): it decides
  the date of each document and, with it, the year of its series. A charge at 00:30 on 1 January numbers
  in the new year's series.
- The series are created by themselves the first time they are used in the year: "TICKET" (tickets, F2),
  "FACT" (full and replacing invoices, F1 and F3) and "RECT" (rectifying invoices, R1–R5), with the code
  as prefix (`TICKET-2026-000001`). The one of a new year inherits the name, the prefix and the format of
  the previous year's one with the same code. The sale **always** numbers in those three; a series with
  another code is for invoices made by hand (INVOICE-F12). While the business has no series, Home
  recommends reviewing them with the step "Your invoice numbering" (INVOICE-F14).

Initial setup, step by step:

1. In **Invoicing → Issuer**, type the legal name, the tax ID and the address of the business and save.
2. If you want another prefix, another format or to continue the numbering of another system, create
   **before the first sale of the year** the series `TICKET` (Ticket F2), `FACT` (Invoice F1) and `RECT`
   (Rectifying R1) of the current year with their "Next number" (INVOICE-F12). Check the "Next number"
   when editing them (INVOICE-F13).
3. Make a test sale and check in **Invoicing → Invoices** that its ticket appears with the expected
   number (INVOICE-F01, INVOICE-F16).

## Screens

### Invoices
Menu **Invoicing → Invoices**. Table paginated 50 at a time (table or card view; on the phone, cards
with the number as title) with "Number", "Customer", "Total", "Status", "Date" and "Type"; every column
sorts. Search box "Search invoices…" (number, name or tax ID of the customer) and filters for "Status",
"Type", "Series", "Source", "Date" (between two days) and "Total" (between two amounts, in the business's
currency). Unsorted, the latest issued comes on top. While the issuer is not set up, on top comes, once,
"You cannot issue invoices yet", the banner of every screen ("No ticket or invoice can be issued until
this is set up:", "Your business details" and "Set up", which opens **Issuer**; to whoever cannot change
the issuer, instead of "Set up", "An administrator has to set this up."), with no other identical warning
below. Per row: "View" (also when tapping the row), "Mark as paid" (only on those "Issued" that are not
rectifying invoices) and "Rectify" (only on those that are not rectifying invoices and are neither
cancelled nor replaced). The **+** button opens "New manual invoice" (INVOICE-F03); without permission to
issue it does not appear, nor does "Mark as paid". The list updates by itself when an invoice is issued,
rectified or paid on any device.
Empty: "No invoices yet.". Loading: "Loading…". Error: the message with "Retry". A refusal of a row
action shows as a notice above the table.

### Invoice detail
Opens from a row of **Invoices** (`/invoice/invoices/<id>`). On top, "Invoice {number}" with the status
tag and the buttons "Print / PDF" and "← Back". If it is a full invoice, or a rectifying invoice of a full
invoice, without the customer's tax ID, the notice "This invoice has no customer tax ID: the ticket
printer cannot print it as a full invoice.". Below, "Type", "Series", "Issue date", "Operation date" (if
it is another), "Customer", "Customer tax ID", "Address", "Issuer", "Source" ("POS sale", "Manual",
"Replaces a simplified invoice", "Rectification", "Sale refund", "Sale void"), "Sale" (its number),
"Rectifies" (the number of the original, which opens it), "Replaces" / "Replaced by" (links), "Rectifying
invoices" (those that correct it), "Paid on" and "Notes". The lines: "#", "Description", "Qty", "Price",
the rate with the name of the tax the invoice declares ("VAT %", "IGIC %" or "IPSI %"; "Tax %" if it mixes
taxes), "Base", "Tax", "Total" (on the phone, each line as a block); without lines, "No detail lines.".
The breakdown per rate ("VAT 21%", "Equivalence surcharge 5.2%", "Exempt (E1)", "Not subject",
"Reverse charge") with its base and its quota, and the totals "Base", "Taxes" and "Total". The buttons
"Mark as paid", "Rectify" and "Full invoice" (only on a ticket that has not been replaced) with the same
rule as on the row. A refusal shows right above those buttons. With **VeriFactu** on and permission to
see its records, below, the card "VeriFactu receipt": the status of the record at the AEAT ("Pending",
"Sent, no answer", "Accepted", "Accepted with errors" or "Rejected"; "Testing (AEAT test)" if it is from
the test environment), the "CSV" once the AEAT has answered, the QR and "Check at the tax agency ↗".
Without VeriFactu, without a record yet or without permission, the card does not show.
Error when opening: "Invoice not found" or the message of the failure, with "← Back".

### Rectify
Window opened by "Rectify", from the row or from the detail. Title "Rectify {number}", the note "A
rectifying invoice (RECT series) will be issued with the amounts negated and the original invoice will be
cancelled. This cannot be undone.", the "Type of rectifying invoice" (R1 to R4; on a ticket, always R5,
no choice), the field "Reason" (mandatory), "Issue rectifying invoice" (with a spinning wheel while it
goes) and "Cancel". Three endings inside the same window: the translated refusal, the document that
cannot be rectified ("A rectifying invoice cannot be rectified.", "The invoice is already cancelled.")
and the result "Rectifying invoice {number} issued. {original} is cancelled.", each with "Close".

### Full invoice (replace a ticket)
Window opened by "Full invoice" on the detail of a ticket. Title "Full invoice of ticket {number}", the
customer search of Customers (it fills in the details) and "Name or company name", "Country", "Document
type" (only outside Spain), "Tax ID" and "Address", all mandatory except the type. "Issue full invoice"
and "Cancel". On issuing, the window closes and the detail opens the new F3.

### New manual invoice
Window with the "Series" (the active ones of the year that issue F1 or F2; at first, the default one or
FACT), the customer search of Customers, "Customer", "Customer tax ID", "Address", "Country", "Notes" and
the lines: "Description", "Qty" (1 at first; it takes decimals), "Price" (without tax, in the business's
currency and with its decimals; its symbol or its code around the figure do not count, as in 12,50 zł)
and the rate, with the name of the tax of the business's tax territory: "VAT %" (21 at first), "IGIC %"
in the Canary Islands or "IPSI %" in Ceuta and Melilla, which start at the general rate of its rule in
Taxes and are empty if the territory has no rule for its tax yet. "+ Line" adds another and the cross
removes it. "Issue invoice" (with a spinning wheel while it goes) is grey until every line has a
description, quantity, price and rate. A refusal shows above the buttons, per field when it is about a
field.

### Series
Menu **Invoicing → Series** (only with permission to keep the series). The intro "Each series sets the
prefix, the format and the counter of the numbering of one invoice type and one year…" and a table with
"Code", "Name", "Type", "Year", "Prefix", "Format" (empty reads `PREFIX-YYYY-NNNNNN`), "Current no.",
"Active" and "Default"; search box "Search code, name…". Below 1280 px it opens as cards. **+** opens
"New numbering series"; "Edit" (or tapping the row) opens "Edit series {code}" (INVOICE-F12,
INVOICE-F13). Without an issuer, the same banner "You cannot issue invoices yet" as in **Invoices**, once.
Empty: "No series yet. Create the first one to number your invoices.". Loading: "Loading series…".
Error: "Could not load the series" with "Retry".

### Issuer
Menu **Invoicing → Issuer**. "Legal name", "Tax ID", "Address", "Postal code", "City", "Province" and
"Country", and "Save". On top, if it is not complete yet, "Without the issuer no invoice can be issued.";
if the ERPlora account sent it, "Received from your ERPlora account on {date}.". Only the owner and the
administrator change it; the rest see it without being able to edit.

## States of each screen

| State | What the person sees |
|---|---|
| Loading | "Loading…" (or "Loading series…") while the first result arrives. |
| Empty | "No invoices yet." / "No series yet…" (or "No results" with a search or filter), with **+** if they can create. |
| Error | The table's notice with "Retry"; a refusal in a window shows inside it, next to its field if it is about a field. |
| Reconnecting | What is painted stays; a banner warns "Reconnecting…". |
| App inactive (`app_inactive`) | "This app is not active in this business". |
| No permission | What they cannot do does not appear; if they arrive through another door, "You do not have permission". |

## Flows

| ID | Flow | Status |
|---|---|---|
| INVOICE-F01 | The ticket (simplified invoice) born when charging | done — Sales asks for it within the same charge |
| INVOICE-F02 | The full invoice when charging a customer with a tax ID | done — Sales asks for it within the same charge |
| INVOICE-F03 | Issue an invoice by hand | done |
| INVOICE-F04 | The customer asks for the full invoice of their ticket | discarded — the public page where the customer types their details and the ticket's code that opens it belong to the platform and to Sales; Invoicing already issues the full invoice that page will ask for, as in INVOICE-F05 (hub#500) |
| INVOICE-F05 | Turn a ticket into a full invoice at the counter | done |
| INVOICE-F06 | A charged sale that could not be invoiced | done |
| INVOICE-F07 | Void a charged sale that already has its ticket | done — Sales asks for it within the same void |
| INVOICE-F08 | Rectify an invoice by hand | done |
| INVOICE-F09 | The rectifying invoice when refunding a whole sale | done — Sales asks for it within the same refund |
| INVOICE-F10 | The rectifying invoice by differences when refunding part of a sale | done — Sales asks for it within the same refund |
| INVOICE-F11 | Number each document in its series and its year | done |
| INVOICE-F12 | Create a numbering series | done |
| INVOICE-F13 | Change a series | done |
| INVOICE-F14 | Know whether the year's numbering is ready | done |
| INVOICE-F15 | Check that the numbering has no gaps | done |
| INVOICE-F16 | Find an invoice | done |
| INVOICE-F17 | View an invoice | done |
| INVOICE-F18 | Print or save an invoice as PDF | done |
| INVOICE-F19 | Mark an invoice as paid | done |
| INVOICE-F20 | Give other apps the invoice of a sale | done |
| INVOICE-F21 | Set up the issuer | done |
| INVOICE-F22 | Receive the issuer from the ERPlora account | discarded — the ERPlora account does not send the business's tax identity with the hub's data and the platform does not hand it to Invoicing; Invoicing already keeps it when it arrives (hub#501) |
| INVOICE-F23 | Issue ERPlora's invoices (platform hub) | discarded — the Invoicing part is done and tested, but the platform hub is not set up until it is born with its own database, like every business (hub#502) |

### INVOICE-F01 The ticket (simplified invoice) born when charging
Status: done — Sales asks for it within the same charge
Actor: system
Screen: none
Steps:
1. The cashier charges a sale in Sales as a ticket, which is the usual thing at the bar and in the salon.
2. On charging, Sales asks Invoicing for its simplified invoice (F2), within the same charge: it comes in
   the year's "TICKET" series, dated the business day, with the charge's operation date, the sale's lines
   and the customer if the sale had one. The invoice is born **"Paid"** (the money is already in the
   till), with the time of the charge, and the Sales ticket already carries its number.
3. The invoice appears in **Invoicing → Invoices** as "Ticket", "Paid", with "Source" "POS sale".
4. It is checked by opening it: the lines and the "Total" are those of the Sales ticket, to the cent.
In: the charged sale from Sales (`sale.sale.completed`), read from the sale itself: its lines with base
and quota already computed, whether the prices included VAT, the frozen tax rule of each line and the
document type; the configured issuer.
Out: the F2 with its number, the description of the operation ("Venta {sale number}", in Spanish, the
AEAT's language), its lines (each with its unit price without VAT and before discounts, and the discount
apart, without VAT) and the breakdown per tax key (tax, regime, qualification, rate and surcharge),
closed **once per key**: what was charged does not change by a cent, but with VAT included the base and
the quota of each rate are recomputed on the total charged at that rate (base by division, quota by
difference) and spread over the lines, which still add up to what was charged. Announces
`invoice.invoice.issued`: VeriFactu creates its record and Sales can put the number on its ticket.
If it fails: asking again for the document of the same sale creates no other and uses no number (one
invoice per sale, also with two requests at once): it answers with the one the charge issued. If
VeriFactu refuses its record (it could not be declared), the ticket is not issued: the charge stays with
its document "pending", the reason in sight and "Issue now" in Sales. Without a configured issuer, or if
the amounts do not add up (a quota that does not match its rate, a quota on a line that is not subject),
Invoicing writes nothing and uses no number; Sales charges anyway with the document "pending", in sight,
until "Issue now" (INVOICE-F06). A sale that no longer exists is not invoiced. The ceiling of the
simplified invoice (€3,000) is watched by Sales when charging.
Involved: SALE-F01, SALE-F04, TAX-F18, TAX-F19

### INVOICE-F02 The full invoice when charging a customer with a tax ID
Status: done — Sales asks for it within the same charge
Actor: system
Screen: none
Steps:
1. The cashier charges in Sales choosing "Invoice", with the customer's name, tax ID and address (Sales
   does not let you charge as an invoice without the three).
2. On charging, Sales asks for the full invoice (F1), within the same charge: it comes in the year's
   "FACT" series, with the customer's name, tax ID, address, country and document type copied from the
   charge (or, if the charge does not bring them, from the customer's card), and each line with its price
   without VAT and its discount apart (RD 1619/2012, art. 6.1.f).
3. It appears in **Invoices** as "Invoice", "Paid", "POS sale", and the detail shows "Customer tax ID"
   and "Address".
In: the sale charged as an invoice (`sale.sale.completed` with invoice document type) and the customer's
tax details that travel in the notice.
Out: the F1 (announces `invoice.invoice.issued`). It is a copy: editing the customer's card afterwards
does not change it. A customer from outside Spain is declared by their country and their document type.
If it fails: as in INVOICE-F01. Without the customer's name, tax ID and address, "A full invoice needs
the customer's name, tax ID and address." and nothing is issued. The recipient is read as in any other
document: a Spanish tax ID that does not validate, or a foreign tax ID without its document type, is
refused under its field (422) and nothing is issued. On a **ticket** (F2) the recipient is optional: if
the tax ID of the card or of the charge does not validate, the ticket goes out anyway with the name and
without the tax ID (it stays in the application's log), so that it never stays "pending" because of that.
Involved: SALE-F04, CUSTOMER-F17

### INVOICE-F03 Issue an invoice by hand
Status: done
Actor: employee, manager, administrator
Screen: Invoices, New manual invoice
Steps:
1. In **Invoices**, tap **+**: "New manual invoice" opens.
2. Choose the "Series" (the active ones of the year that issue invoices, F1, or tickets, F2, and always
   "FACT" and "TICKET" even if the year has not opened them yet; it starts at the default one or at
   "FACT") and, if you want, look the customer up in Customers: it fills in name, tax ID, address and
   country. Type or correct "Customer", "Customer tax ID", "Address" and "Notes".
3. Fill in each line: "Description", "Qty" (1 at first; up to three decimals), "Price" without tax and in
   the business's currency, and the rate, which carries the name of the tax of the business's tax
   territory: "VAT %" (21 at first), "IGIC %" in the Canary Islands or "IPSI %" in Ceuta and Melilla. It
   starts at the general rate of its rule in Taxes (in the Canary Islands, that of the Canary Islands
   rule); if the territory has no rule for its tax yet, it is empty: type it yourself. "+ Line" adds
   another, with the same starting rate, and the cross removes it.
4. Tap "Issue invoice"; it is grey until every line has a description, quantity, price and rate. The
   window closes and the invoice appears in the list with its number, "Issued" and "Source" "Manual".
In: what the person types; the configured issuer. Through the API or the assistant a line can also carry
the tax category of Taxes: then its rate and its qualification are those of the rule in force today, not
the typed rate. The typed rate belongs to the tax of the business's tax territory (Taxes → Settings,
TAX-F11): in the Canary Islands it is declared as IGIC and in Ceuta and Melilla as IPSI.
Out: the invoice (F1 in an invoice series, F2 in a ticket series) with the tax computed on top of the
price, closed once per rate and spread over the lines by largest remainder (the items add up to the
printed total), and as the description of the operation its items ("Curso de corte, Kit de tinte", up to
500 characters); announces `invoice.invoice.issued`.
If it fails: inside the window, above the buttons: "A full invoice needs the customer's name, tax ID and
address.", "That tax ID is not valid." (under the field), "Line {n}: the price is not an amount…", a line
with a price that comes to 0.00, a series that is inactive, does not issue invoices or belongs to another
year ("That series numbers another year…"), a ticket above the Sales limit ("Above €3,000.00 a ticket
cannot be issued…", RD 1619/2012 art. 4), or the missing issuer. Nothing is issued, no number is used,
and what was typed is kept. If the tax territory cannot be read, the rate is called "Tax %", comes empty
and warns "Could not read the business’s tax territory: type the rate of each line."; the invoice is
issued anyway, with the territory's tax.
Involved: TAX-F18, CUSTOMER-F17, TAX-F11

### INVOICE-F04 The customer asks for the full invoice of their ticket
Status: discarded — the public page where the customer types their details and the ticket's code that opens it belong to the platform and to Sales; Invoicing already issues the full invoice that page will ask for, as in INVOICE-F05 (hub#500)
Actor: customer
Screen: public page of the platform (it does not exist yet)
Steps:
1. The ticket Sales prints carries a code to ask for the invoice.
2. The customer opens it on their phone, without signing in, and types their tax details.
3. Invoicing issues the replacing full invoice (F3), as in INVOICE-F05.
In: the ticket (F2) and the details the customer types.
Out: the F3 (announces `invoice.invoice.issued`).
If it fails: as in INVOICE-F05.
Involved: SALE-F29, INVOICE-F05

### INVOICE-F05 Turn a ticket into a full invoice at the counter
Status: done
Actor: employee, manager, administrator
Screen: Invoice detail, Full invoice
Steps:
1. The customer comes back with their ticket and asks for the invoice in their name.
2. In **Invoices**, look for the ticket (by its number) and open it.
3. Tap "Full invoice", look the customer up or type their details (name, country, tax ID and address)
   and tap "Issue full invoice".
4. The new F3 opens: "Invoice", "Source" "Replaces a simplified invoice" and "Replaces" with the ticket's
   number; the ticket says "Replaced by" with the F3's.
In: the ticket (F2) being replaced and the customer's tax details.
Out: the F3 in the year's "FACT" series, with the ticket's lines and amounts copied to the cent (same
operation) and the same operation date; the ticket is not touched. If the ticket was paid, the F3 is born
paid. Announces `invoice.invoice.issued`. From then on, rectifying or refunding that sale rectifies the
F3, not the ticket.
If it fails: without name, tax ID or address, refusal; a Spanish tax ID that is not valid, "That tax ID
is not valid."; a document that is not a ticket, "Only a ticket (simplified invoice) can be replaced by a
full invoice.". If the ticket already has its F3, it answers with it without issuing another or using a
number.
Involved: INVOICE-F04

### INVOICE-F06 A charged sale that could not be invoiced
Status: done
Actor: system, employee, manager, administrator, assistant
Screen: none
Steps:
1. A sale is charged and Invoicing cannot issue its document when charging: the issuer is missing,
   whoever charges cannot issue invoices or the amounts do not add up. Sales charges anyway and leaves its
   document "pending": in **Sales** the sale carries "Document pending" and its document warns "Fiscal
   document pending" above the paper.
2. The hub tries again by itself, each time further apart (a few minutes in total, up to 8 times); an
   attempt that fails writes nothing and uses no number. If meanwhile the cause is fixed (for example,
   the issuer is set up, INVOICE-F21), the next attempt issues the document and the sale is no longer
   pending.
3. Once the attempts are over, or without waiting for them, whoever fixes the cause taps "Issue now" on
   that sale: its document comes out and the sale is no longer pending. Through the API or the assistant
   it is asked the same way, by the sale's number, of Sales or of Invoicing: in both cases the sale carries
   its document as soon as it is issued.
4. If it still cannot be done, "Issue now" says why and changes nothing.
In: the sale waiting for its document.
Out: that of INVOICE-F01 or INVOICE-F02, dated the day it is finally issued (the operation date is still
that of the charge); the sale carries its number from that very moment (announces
`invoice.invoice.issued`).
If it fails: voiding or refunding a sale whose document is waiting asks for it first, in the same
operation; if it still cannot, the void or the refund goes ahead and both documents stay "pending": the
hub retries them and "Issue now" issues them in order (INVOICE-F07, INVOICE-F09). Asking Invoicing for
the rectifying invoice of that void or that refund also leaves it in Sales at once. Asking again for a
document that already came out issues no other and uses no number.
Involved: SALE-F01, SALE-F29

### INVOICE-F07 Void a charged sale that already has its ticket
Status: done — Sales asks for it within the same void
Actor: system
Screen: none
Steps:
1. Someone voids in Sales a sale charged as a ticket, with its reason (Sales does not let you void a sale
   charged as an invoice nor one with refunds).
2. On voiding, Sales asks for the rectifying invoice of the whole ticket, within the void: R5 (rectifying
   a simplified invoice) in the year's "RECT" series, negative, with the reason of the void. If the ticket
   had already been replaced by an F3, it rectifies the F3 (R1).
3. The ticket becomes "Cancelled"; the rectifying invoice comes out with "Source" "Sale void".
In: the sale's void (`sale.sale.voided`), resolved from the sale itself.
Out: the rectifying invoice and the cancelled original (announces `invoice.invoice.issued` and
`invoice.invoice.rectified`); VeriFactu records it. The repeated notice issues no other.
If it fails: if the sale's ticket is still waiting, Sales asks for it first, in the same void; if it still
cannot, the void goes ahead and both stay "pending", in sight, until "Issue now" (INVOICE-F06).
Involved: SALE-F30

### INVOICE-F08 Rectify an invoice by hand
Status: done
Actor: manager, administrator, assistant
Screen: Rectify
Steps:
1. In **Invoices** (row) or on the detail, tap "Rectify" on an invoice that is not a rectifying invoice
   and is neither cancelled nor replaced; or ask the assistant ("rectifica la factura FACT-2026-000003
   porque el precio estaba mal") and go on at step 4.
2. Choose the "Type of rectifying invoice" (R1 at first: error founded in law and art. 80 One, Two and Six
   LIVA; R2 insolvency proceedings; R3 bad debts; R4 others; a ticket always R5), type the "Reason" and
   tap "Issue rectifying invoice" (a second click issues no other).
3. The window says "Rectifying invoice {number} issued. {original} is cancelled.". On closing it, the
   original shows "Cancelled" and the list has a new "Rectifying" dated today, with the original's
   amounts and lines negated and the note "Rectifies invoice {number}. Reason: {reason}".
4. With the assistant, before issuing anything it shows you the rectifying invoice about to be born: the
   invoice it rectifies (number, date and customer), the type (R1 at first, R5 if it is a ticket), the
   reason, the next number of the year's "RECT" series (it is not reserved: it takes it when issued),
   today's date, its lines and the base, the taxes and the total, negative; if the invoice already had
   rectifying invoices by differences, also what is left to rectify of it.
5. Then "Run this action?" comes with the invoice's "Number" and the "Reason" and, in "What will happen",
   the rectifying invoice about to be born: the "Type of rectifying invoice", the series' "Next number"
   (not reserved either) and the "Tax base", the "Tax" and the "Total", negative, in the business's
   currency. Type "CONFIRM" and tap "Run". That same rectifying invoice is issued, in your name, just as
   from the window: in **Invoices** the original shows "Cancelled" and there is a new "Rectifying" dated
   today.
6. If you tap "Cancel", nothing is issued: the invoice stays "Issued" and the assistant says it was not
   done.
In: the chosen invoice, the type and the reason, in the window or told to the assistant. The server sets
the date: the business day.
Out: the rectifying invoice numbered in the year's "RECT" series, with the original's issuer and
customer, its breakdown negated and its lines negated (the quantity carries the sign; the price does
not); the original becomes "Cancelled" (announces `invoice.invoice.issued` and
`invoice.invoice.rectified`). It moves no money nor till. If the original already had rectifying invoices
by differences (partial refunds), this one rectifies exactly what is left, with one line per tax key at
its own rate.
If it fails: inside the window, translated. A date that is not today's (API or assistant): "A rectifying
invoice is dated the day it is issued…" and nothing is issued. On a rectifying invoice or a cancelled
one, the window only says why. On a replaced ticket, "This ticket was already replaced by a full invoice:
rectify the full invoice.". Two rectifications of the same invoice at once: the second waits for the
first and is refused without using a number. Without permission the action does not appear. To the
assistant, on a rectifying invoice, a cancelled one or a replaced ticket, it tells you why with those
same notices and the confirmation does not come; if another rectifying invoice is issued between the
preview and your confirmation, yours takes the next number; if another device rectifies that invoice
before you confirm, no other is issued: "The invoice is already cancelled." comes.
Involved: SALE-F31

### INVOICE-F09 The rectifying invoice when refunding a whole sale
Status: done — Sales asks for it within the same refund
Actor: system
Screen: none
Steps:
1. Someone refunds in Sales a whole charged sale, at once.
2. On refunding, Sales asks for the rectifying invoice, within the refund: the invoice of that whole sale
   negated, in the year's "RECT" series, dated the business day, with the original's lines negated and
   the reason of the refund. R5 if the original is a ticket; R1 if it is a full invoice.
3. The original becomes "Cancelled"; the rectifying invoice appears in **Invoices** with "Source" "Sale
   refund" and "Rectifies" the original.
In: the refund from Sales (`sale.sale.refunded`), read from the refund document itself: the sale, the
amount and whether it closes the sale. The original invoice is looked up by the sale (its F3 if the
ticket was replaced), never by what the notice says.
Out: the rectifying invoice and the cancelled original (announces `invoice.invoice.issued` and
`invoice.invoice.rectified`).
If it fails: the same refund twice is a single document, a single number. If the sale's document is still
waiting, Sales asks for it first, in the same refund; if it still cannot, the refund goes ahead and both
stay "pending", in sight, until "Issue now" (INVOICE-F06).
Involved: SALE-F31

### INVOICE-F10 The rectifying invoice by differences when refunding part of a sale
Status: done — Sales asks for it within the same refund
Actor: system
Screen: none
Steps:
1. Someone refunds in Sales a part of a charged sale.
2. On refunding, Sales asks for a rectifying invoice by differences for the refunded amount: negative, in
   the year's "RECT" series. If articles came back, the amount is spread **only among their tax keys**
   (returning the shampoo at 21% does not touch the menu at 10%); if only money came back, among all the
   keys in proportion. It carries **one line per key**, at its own rate, with what came back of that key
   ("2 × Champú, 1 × Cera") or, without articles, the reason. The original stays "Paid" or "Issued".
3. Each following refund issues its own on what is left; the one that closes the sale takes exactly what
   is left, and then the original becomes "Cancelled".
4. With the sale refunded whole, the original and its rectifying invoices add up to zero to the cent,
   rate by rate.
In: the refund from Sales (`sale.sale.refunded`), as in INVOICE-F09.
Out: one rectifying invoice per refund document; the original is cancelled only when it is left at zero.
If it fails: the same refund twice is a single document, and never more than what is left of the
original is rectified.
Involved: SALE-F31

### INVOICE-F11 Number each document in its series and its year
Status: done
Actor: system
Screen: none
Steps:
1. Every time a document is issued (ticket, invoice, replacing or rectifying invoice), Invoicing takes the
   series of its code and of the year of the business day; if it does not exist, it creates it at that
   moment with the counter at 0, inheriting name, prefix and format from the previous year's one with
   that code (or, the first time, with the code as prefix).
2. It raises that series' counter by one and writes the number with the series' format (without format,
   `TICKET-2026-000001`) in the same operation that saves the document.
3. On 1 January, at the business's time, the next document opens the new year's series and goes back to
   1 (or to the "Next number" set for it).
In: the series code that applies (TICKET for tickets, FACT for full and replacing invoices, RECT for
rectifying invoices; in the manual entry, the chosen series) and the business day.
Out: the document's number. The number goes into VeriFactu's chained fingerprint.
If it fails: if the issue is refused or fails, nothing is saved and the counter does not go up: no gap is
left. Two charges at once in the same series wait for each other and get consecutive numbers; two
documents of the same series cannot carry the same number ("The number {number} already exists in series
{code}…": it happens if a series of another year uses a format without the year).
Involved: none

### INVOICE-F12 Create a numbering series
Status: done
Actor: manager, administrator
Screen: Series
Steps:
1. In **Invoicing → Series**, tap **+**: "New numbering series" opens.
2. Type "Code" (capitals, digits, hyphen or underscore), "Name", "Invoice type" (from F1 to R5), "Year"
   (at first, the business's), "Prefix" (empty = the code), if you want "Number format" (placeholders
   `{prefix}`, `{code}`, `{year}`, `{seq}` and `{seq:01d}`…`{seq:09d}`; empty is `PREFIX-YYYY-NNNNNN`)
   and "Next number" (1 at first; another to continue the numbering of another system). Choose "Active"
   and "Default series".
3. Tap "Create series". The window closes and the series appears with "Current no." one less than the
   next number.
In: what the person types.
Out: the series; if it was marked default, the one that was default that year stops being so. For sales
and refunds to use it, the code has to be TICKET, FACT or RECT; with another code, it is for the manual
entry (if its type is F1 or F2).
If it fails: an empty code or one with another shape, a format without the year or without a sequence
placeholder, with a line break, or a prefix or format with accents or symbols such as º or ª, show under
their field (the number is VeriFactu's `NumSerieFactura`: printable ASCII only); numbers that with the
widest sequence would go over 60 characters, "The numbers of this series would not fit in 60
characters…" under the prefix or the format; a code that already exists that year, "There is already a
series with that code that year.".
Involved: none

### INVOICE-F13 Change a series
Status: done
Actor: manager, administrator
Screen: Series
Steps:
1. In **Series**, tap "Edit" on the row (or the whole row): "Edit series {code}" opens.
2. Change "Name", "Active", "Default series" and, while the series has issued nothing, "Prefix", "Number
   format" and "Next number". "Code", "Invoice type" and "Year" are locked.
3. Look at "Next number": it is exactly the number the next document will carry, computed by the server
   without using it up.
4. Tap "Save"; the window closes and the table updates.
In: the chosen series and the changes.
Out: the changed series; the numbers already issued do not change. An inactive series is no longer
offered (and is refused) in the manual entry; sales keep numbering in TICKET, FACT and RECT.
If it fails: with the series already used, prefix, format and next number are locked and "This series has
already issued invoices, so its prefix, its format and its next number can no longer change: the number
is part of the VeriFactu chain. Create a new series if you need others." says so.
Involved: none

### INVOICE-F14 Know whether the year's numbering is ready
Status: done
Actor: owner, manager, administrator, assistant
Screen: Home, Series
Steps:
1. On Home, while the business has no series, "Finish setting up your business" shows the step "Your
   invoice numbering" with the pill "Recommended": "Before your first sale, check the prefix your invoice
   numbers will carry. If you are coming from another system, continue its numbering instead of starting
   again at 1.". Only whoever keeps the series sees it.
2. "Set up" opens **Invoicing → Series**. If you want another prefix, another format or to continue the
   numbering of another system, create the year's series there (INVOICE-F12); if not, there is nothing to
   do: the series are created by themselves with the first document.
3. As soon as the business has its first series, created by hand or born with the first document, the step
   becomes "Done" without reloading, and stays done in the following years (a new year's series inherits
   the previous one's).
4. The assistant or the API also ask whether the year's numbering is ready: the answer says the
   business's year and how many ordinary series (F1, F2, F3), rectifying series (R1–R5) and default series
   it has that year, how many it has in total, and whether it is ready (at least one ordinary and one
   rectifying).
In: the business's series.
Out: nothing; it only reads (neither Home nor the question creates any series).
If it fails: nothing to fail; a newly created business has the step pending and answers that it is not
ready.
Involved: none

### INVOICE-F15 Check that the numbering has no gaps
Status: done
Actor: employee, manager, administrator, assistant
Screen: none (assistant or API)
Steps:
1. Ask the assistant whether the numbering has gaps, or for the number book of a series.
2. Without gaps, the answer is that none is missing; with gaps, it says the series, the year, the last
   number that is there and how many are missing in a row.
3. The book says which number was given to which document and when.
In: the issued documents.
Out: nothing; it only reads.
If it fails: the book is the invoice itself (the number is assigned in the same transaction that saves
it, so a number without a document cannot exist). The gap you see is that of a "Next number" that skipped
numbers, or one that was never used; before the first number of a series it does not count as a gap.
Involved: none

### INVOICE-F16 Find an invoice
Status: done
Actor: employee, manager, administrator
Screen: Invoices
Steps:
1. Open **Invoicing → Invoices**.
2. Type in "Search invoices…" a number, a customer's name or a tax ID; or filter (status, type, series,
   source, date, total); or tap a column to sort.
3. The table shows the matching ones, 50 at a time; the latest issued, on top.
4. Tap "View", or the row, to open it (INVOICE-F17).
In: the hub's invoices.
Out: nothing; it only reads.
If it fails: without results, "No results"; with an error, the message and "Retry". A total that is not an
amount says "Type an amount, like 12.50" under its field, and an end date before the start date, "The end
date cannot be before the start date."; neither of the two filters.
Involved: none

### INVOICE-F17 View an invoice
Status: done
Actor: employee, manager, administrator
Screen: Invoice detail
Steps:
1. In **Invoices**, open the invoice.
2. Read the header, the lines (with their "Price" without VAT and before discounts and, if any has one, the
   "Disc." column with the discount without VAT), the breakdown and the totals.
3. With **VeriFactu**, read below the "VeriFactu receipt": the status of the record at the AEAT, its
   "CSV" once the AEAT has answered and the QR, which can be scanned or opened with "Check at the tax
   agency ↗".
4. "Rectifies", "Replaces", "Replaced by" and the rectifying invoices open the linked document.
5. "← Back" goes back to the list.
In: the invoice and its lines and, with VeriFactu, its record.
Out: nothing; it only reads. The detail updates by itself if meanwhile it is paid, rectified or the AEAT
answers.
If it fails: "Invoice not found" or the reason of the failure. Without VeriFactu, without a record yet or
without permission to see it, the detail shows without the receipt card.
Involved: VERIFACTU-F19

### INVOICE-F18 Print or save an invoice as PDF
Status: done
Actor: employee, manager, administrator
Screen: Invoice detail
Steps:
1. On the detail, tap "Print / PDF".
2. With **Printing** and an active system printer with the Receipt function, the A4 invoice goes to that
   printer, with the VeriFactu QR if it has its record, and "Sent to <printer>." reads (PRINTING-F08).
3. If not (without Printing turned on, without a system printer, or if its VeriFactu record could not be
   read for that printer), the browser's print dialog opens with the A4 invoice (with VeriFactu, on top
   the record's QR with "QR tributario:" and "VERI*FACTU", fixed in Spanish by the AEAT; issuer, "Bill
   to", lines, breakdown per rate, totals and the note of what it rectifies), from where it can be saved
   as PDF. While the record arrives, "Print / PDF" waits: the paper never goes out without its QR.
4. Always in the language of whoever prints. A document of a sale comes out as "Copy" (the original was
   the paper of the charge); one issued from Invoicing, as the original.
In: the invoice and its lines.
Out: the paper; the invoice does not change. Each tap, one paper.
If it fails: "Could not print the invoice", also if the VeriFactu record of an invoice that has one cannot
be read (it is not printed without its QR).
Involved: PRINTING-F08, VERIFACTU-F19

### INVOICE-F19 Mark an invoice as paid
Status: done
Actor: employee, manager, administrator
Screen: Invoices, Invoice detail
Steps:
1. In **Invoices** (row) or on the detail, tap "Mark as paid" on an "Issued" invoice.
2. Confirm in "Mark {number} as paid?" ("The payment is recorded with the current date and time.") with
   "Mark as paid", or go back with "Cancel".
3. The invoice becomes "Paid" and the detail shows "Paid on" with the date and the time.
In: the chosen invoice.
Out: the status "Paid" and the payment date (announces `invoice.invoice.paid`). No amount changes and the
till is not touched.
If it fails: if meanwhile someone paid it or rectified it, "This invoice cannot be marked as paid: only an
issued invoice that is not paid yet can be. Nothing was changed.". The invoices born from a sale are
already born paid and a rectifying invoice is not paid: they do not offer the action.
Involved: none

### INVOICE-F20 Give other apps the invoice of a sale
Status: done
Actor: system
Screen: none
Steps:
1. Another app asks which invoice was born from a sale.
2. Invoicing answers with the sale's current document (its F3 if the ticket was replaced): number, type,
   series, date, issuer, customer, total and status.
In: the sale (its id or its number).
Out: the invoice's data; it only reads.
If it fails: if the invoice does not exist yet, it answers that there is none.
Involved: SALE-F29

### INVOICE-F21 Set up the issuer
Status: done
Actor: owner, administrator
Screen: Home, Invoices, Series, Issuer
Steps:
1. While there is no issuer, Home shows in "Finish setting up your business" the step "Your business
   details" with the pill "Needed to invoice": "Legal name, tax ID and address: without them you cannot
   issue an invoice.". Everyone sees it; "Set up" only whoever can change the issuer, and to the others it
   says "An administrator has to set this up.".
2. Tap "Set up" on that step, open **Invoicing → Issuer**, or tap "Set up" on the banner "You cannot issue
   invoices yet" that shows above the other screens while there is no issuer, **Invoices** and **Series**
   too, only once (to whoever cannot change the issuer, the banner says "An administrator has to set this
   up.", without "Set up").
3. Type "Legal name", "Tax ID", "Address", "Postal code", "City", "Province" and choose the "Country"
   (Spain at first).
4. Tap "Save": "Issuer saved." comes, the banner disappears from every screen, **Invoices** and **Series**
   too, and the Home step becomes "Done", without reloading and on the other devices too.
In: what the person types.
Out: the issuer, which is copied into every document issued from now on (those already issued do not
change); announces `invoice.issuer.updated`.
If it fails: without legal name, tax ID or address, under its field; a Spanish tax ID that is not valid,
"That tax ID is not valid.".
Involved: none

### INVOICE-F22 Receive the issuer from the ERPlora account
Status: discarded — the ERPlora account does not send the business's tax identity with the hub's data and the platform does not hand it to Invoicing; Invoicing already keeps it when it arrives (hub#501)
Actor: system
Screen: Issuer
Steps:
1. When the ERPlora account sends the hub's data with the business's tax identity, the platform hands it
   to Invoicing with the version of that data.
2. Invoicing saves the issuer and **Issuer** says "Received from your ERPlora account on {date}.".
In: the business's tax identity the account sends (legal name, tax ID, address, postal code, city,
province and country) and its version.
Out: the issuer (announces `invoice.issuer.updated`). Data older than the saved one is ignored.
If it fails: an incomplete issuer or one with an invalid tax ID is refused and the previous one stays.
Involved: none

### INVOICE-F23 Issue ERPlora's invoices (platform hub)
Status: discarded — the Invoicing part is done and tested, but the platform hub is not set up until it is born with its own database, like every business (hub#502)
Actor: system (the ERPlora account)
Screen: none (nobody enters the platform hub)
Steps:
1. A customer pays their subscription; the ERPlora account numbers its invoice (`ERP-2026-00123`, credit
   notes in `ERPR`) and sends it, signed, to ERPlora's platform hub.
2. Invoicing issues it as it arrives, with the account's number and date (no series of the hub counts for
   it), with ERPlora as issuer and that day's payer as recipient, and VeriFactu seals its record in the
   same operation. It answers "issued" with its QR.
3. The account then asks how it is going: "issued" while the record goes to the AEAT, and "accepted",
   "accepted with errors" or "rejected" when it answers (with its code and its message).
4. The PDF is the same A4 as in INVOICE-F18 in the payer's language, with the VeriFactu QR ("QR
   tributario:", "VERI*FACTU") only once the AEAT has accepted it, as in the old account.
In: the account's invoice: its number, its date, its amounts, how it is taxed, the payer, its lines and,
in a credit note, the invoice it corrects.
Out: the invoice, with the account's reference (announces `invoice.invoice.issued`; a credit note, also
`invoice.invoice.rectified`), and its VeriFactu record.
If it fails: the same invoice again (or two deliveries at once) answers what there already is, without
writing anything; a credit note of an invoice that did not arrive is refused; above €400 without the
payer's tax ID it is refused; an invoice that does not follow the contract is refused with its reason; a
VeriFactu refusal undoes the whole invoice.
Involved: VERIFACTU-F13

## Services: what goes in and what comes out

Everything can be asked for through the screens, the assistant (by voice or by text, with the person's own
session) and the API, with the same rules and the same permissions. Designed for voice: an invoice is named
by its number (`FACT-2026-000012`), a sale by its number of the day (`20261014-0003`), a customer by their
name, their phone or their email (as in Customers) and a series by its code.

### What it offers: queries (they read, they change nothing)

| What it gives | Who can | Flows | Service |
|---|---|---|---|
| The invoices, with search, filters, sorting and pages (up to 100) | view | F16 | `invoice.invoice.list` |
| An invoice with its lines, breakdown and links, by its id or its number | view | F17 | `invoice.invoice.get` |
| The current invoice of a sale | view | F20 | `invoice.invoice.by_source` |
| The printable document (A4 HTML) of an invoice | view | F18 | `invoice.invoice.document` |
| The rectifying invoice that rectifying an invoice would issue, without issuing it or using a number (what the assistant shows before its confirmation and inside it) | rectify | F08 | `invoice.invoice.rectification_preview` |
| The rate a typed line starts with: the territory's general rate, from its own rule in Taxes (empty without it) | issue | F03 | `invoice.invoice.line_defaults` |
| The series, with search, filters and pages | view | F12, F13 | `invoice.series.list` |
| The next number of a series, without using it up | view | F13 | `invoice.series.peek_next` |
| A series, by its id or its code, and how it is named outside its screen: its code, its year and its name | view | F13 | `invoice.series.get` |
| A refund from Sales, by its id: the sale it refunds, what was refunded and the number of its rectifying invoice | view | F09, F10 | `invoice.refund.get` |
| Whether the year's numbering is ready | view | F14 | `invoice.numbering.status` |
| The gaps of the numbering | view | F15 | `invoice.numbering.gaps` |
| The book of numbers given | view | F15 | `invoice.numbering.allocations` |
| The issuer | view | F21, F22 | `invoice.issuer.get` |
| How an ERPlora invoice is going (by the SaaS's `id`) | only the system | F23 | `invoice.invoice.platform_status` |
| The A4 of an ERPlora invoice, in its language | only the system | F23 | `invoice.invoice.platform_document` |
| Whether the platform hub can issue now | only the system | F23 | `invoice.invoice.platform_health` |

All of them can be followed live.

### What it offers: actions (they change data)

| What it does | Who can | Flows | Service |
|---|---|---|---|
| Issues an invoice by hand | issue | F03 | `invoice.invoice.create` |
| Issues the invoice of a charged sale (also the reaction to its charge) | issue | F01, F02, F06 | `invoice.invoice.create_from_sale` |
| Replaces a ticket by a full invoice | issue | F04, F05 | `invoice.invoice.substitute` |
| Marks an issued invoice as paid | issue | F19 | `invoice.invoice.mark_paid` |
| Rectifies an invoice | rectify | F08 | `invoice.invoice.rectify` |
| Issues the rectifying invoice of a refund (also the reaction to it) | rectify | F09, F10 | `invoice.invoice.rectify_from_refund` |
| Issues the rectifying invoice of a voided sale (also the reaction to it) | rectify | F07 | `invoice.invoice.rectify_from_void` |
| Creates a series | keep the series | F12 | `invoice.series.create` |
| Changes a series | keep the series | F13 | `invoice.series.update` |
| Saves the issuer | set up the issuer | F21 | `invoice.issuer.update` |
| Sends the A4 page of an invoice to the Printing queue (or says it was not queued: the device prints it) | view | F18 | `invoice.invoice.print` |
| Saves the issuer the ERPlora account sends | only the system | F22 | `invoice.issuer.sync` |
| Issues an ERPlora invoice with its VeriFactu record | only the system | F23 | `invoice.invoice.issue_platform` |

### What it announces

| Notice | When | What it carries | Service |
|---|---|---|---|
| Document issued | Every new F1, F2, F3 and R1–R5 | `invoice_id`, `number`, `series`, `invoice_type`, `total`, `source_type`, `sale_id`, `source` (`{type, sale_id, refund_id, void}`: which Sales charge, refund or void it comes from), `rectifies_id`, `substitutes_id` | `invoice.invoice.issued` |
| Invoice rectified | A rectifying invoice corrects an invoice | `invoice_id` (the original), `number`, `status`, `rectification_id`, `rectification_number`, `remaining` | `invoice.invoice.rectified` |
| Invoice paid | Mark as paid | `invoice_id`, `number`, `paid_at` | `invoice.invoice.paid` |
| New series | Create a series | `id`, `code`, `year` | `invoice.series.created` |
| Series changed | Change a series | `id`, `code`, `year`, `fields` | `invoice.series.updated` |
| Issuer changed | Save or receive the issuer | `source` | `invoice.issuer.updated` |

Contract of the source with Sales: `source.type` is the document's `source_type` (`sale`, `manual`,
`substitution`, `rectification`, `refund`, `void`); `source.sale_id` the sale it comes from (also in its F3
and in its rectifying invoices), `source.refund_id` the refund of a rectifying invoice by refund, and
`source.void` is `true` in that of a void. With it `sale.sale.record_invoice` links to its charge, its
refund or its void a document that stayed "pending" and was issued later: Invoicing asks for it by name in
the same operation that issues it (also with "Issue now", the API, the assistant or a retry of the hub), so
the sale and its document match when it ends; Sales' reaction to this notice, when it arrives later, no
longer changes anything.

What each notice refreshes: the list, the detail, the invoice of a sale and the document, with "issued",
"rectified" and "paid"; the series, the next number, the status of the numbering, the gaps and the book,
with "issued" and those of the series; the issuer, with "issuer changed".

### What it reacts to

| Notice | From | What it does | Service |
|---|---|---|---|
| Sale charged (`sale.sale.completed`) | Sales | Issues its F2 or its F1 (F01, F02) | `invoice.invoice.create_from_sale` |
| Sale refunded (`sale.sale.refunded`) | Sales | Issues the rectifying invoice of the refund (F09, F10) | `invoice.invoice.rectify_from_refund` |
| Sale voided (`sale.sale.voided`) | Sales | Issues the rectifying invoice of the whole ticket (F07) | `invoice.invoice.rectify_from_void` |

Each reaction runs as the system, in its own transaction, and is idempotent: one per sale, one per refund
and one per void. Sales asks for the document first within its charge, its void or its refund; the hub's
notice delivery hands it these notices afterwards and, if that one stayed "pending", retries it at 2, 4,
8… seconds up to 8 times; after that, it comes out with "Issue now" (INVOICE-F06).

### What it needs from other apps

- **Sales** (requirement): the sale, its lines, its refunds and its void, read from its rows; and
  `sale.sale.record_invoice`, by name and with the platform's permission, to give the sale, its void or
  its refund the document it was waiting for (INVOICE-F06).
- **Taxes** (requirement): the rule frozen in each line of the sale (tax, regime, qualification, rate and
  surcharge) and, in the manual entry by category, the rule in force today (`resolve_tax`, in the
  business's tax territory); the tax of a territory (`tax_kind_of`, `business_tax_kind`) for what has no
  rule: the line with a typed rate (the business's territory) and that of a sale whose rule no longer
  exists (the territory the line froze when it was charged); rounding half up (`round_half_up`). The
  name of the tax of the rate of a typed line ("VAT %", "IGIC %", "IPSI %") is read by the screen from
  `tax.settings.get` (`tax_kind`, with `useTaxKind()` of Taxes), the only source:
  `invoice.invoice.line_defaults` only gives the general rate and does not repeat the tax (round
  2026-10-17 of PLAN-HUB). What has already been issued is labelled by what it declared (the tax of its
  breakdown; "Tax %" if it mixes), never by today's territory: the same rule as the Sales tax figure
  (SALE-F28), which says the tax of the period's sales, "Taxes" if they mix, and the territory's only
  without sales.
- **Customers** (requirement): the customer's card (name or company, tax ID, address and country) that
  fills in the tax details in the manual entry, in the replacement and in the F1 of a sale that does not
  bring them.
- **Platform**: the business's currency (`base.business.get`, that of its country), which the invoice you
  make by hand keeps.
- **Printing** (by name, without requirement): `printing.job.create` with the A4 page of an invoice for
  the system printer (F18), in a savepoint of its own; without Printing turned on, without a system
  printer or if it refuses it, nothing is queued and the device prints it.
- **VeriFactu** (by name, without requirement): `verifactu.record.by_invoice`, the QR that A4 page carries.

### Who uses it

| App | What for | Service |
|---|---|---|
| VeriFactu | Record every issued document and chain its fingerprint | `invoice.invoice.issued` + the invoice (requires `invoice`) |
| VeriFactu | Its "Create test invoice" | `invoice.invoice.create` |
| Sales | Issue the document of its charge, its void and its refund, within them | `invoice.invoice.create_from_sale`, `invoice.invoice.rectify_from_void`, `invoice.invoice.rectify_from_refund` |
| Sales and Printing | The issuer of their papers | `invoice.issuer.get` |
| Platform (Home) | The steps "Your business details" (F21) and "Your invoice numbering" (F14) of "Finish setting up your business" | `invoice.issuer.get`, `invoice.numbering.status` |

### Who can do what

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| View invoices, series, numbering and issuer; print | yes | yes | yes | yes | `invoice.view_invoice` |
| Issue by hand, invoice a sale, replace a ticket, mark as paid | yes | yes | yes | yes | `invoice.add_invoice` |
| Rectify (by hand, by refund and by void) | yes | yes | yes | no | `invoice.rectify_invoice` |
| Create and change series | yes | yes | yes | no | `invoice.manage_series` |
| Set up the issuer | yes | yes | no | no | `invoice.manage_issuer` |

The roles arrive from the SaaS with a prefix (`hub_owner`, `hub_admin`, `hub_manager`, `hub_employee`).
Receiving the issuer from the SaaS (`invoice.sync_issuer`) belongs to no role: only to the system.
