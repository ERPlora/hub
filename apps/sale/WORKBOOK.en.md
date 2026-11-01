<!-- generated from WORKBOOK.md sha256:fb4903203aafd7dbe749448d9614f3a90d7fdc2b9393ae5578ca2d0e07ae7a31 -->

## What it is for and who it is for

Sales & POS is the business's **cash register**: the check is built by tapping articles, it is charged
in cash, by card or split across several payment methods, and what remains is a **sale that can no longer
change**, with its number of the day, its VAT line by line and its ticket or its invoice. It serves both
businesses:

- In the **restaurant**, the check stays open while the table eats: rounds are added to it, it is sent to
  the kitchen, the bill is printed for the table, it is charged whole or in parts, it is split or merged.
- In the **hair salon**, each service on the ticket carries the professional who did it and the check is
  charged at the end, with the client set.

Who uses it:

- The **employee** (waiter, receptionist, cashier): builds the check, adds notes, comps a line, applies
  discounts up to the business's maximum, parks and retrieves checks, charges and looks up the sales.
- The **manager**: also sells at an open price, applies discounts above the maximum, voids an open check
  or a line already sent to the kitchen, voids and refunds sales, sees the figures and prepares the quick
  notes, the sections, the payment methods and the POS settings.
- The **owner** and the **administrator**: everything.

Sales does not keep tables or customers in the check (they belong to Tables and Customers), does not
number invoices or talk to the AEAT (it asks Invoicing for them in the same charge; the AEAT belongs to
VeriFactu), does not move stock (Inventory does it when it hears of the sale) and does not balance the
cash register (Cash register reads the sales; Sales only asks it whether the cash register is open before
charging in cash).

## Reference adopted

ERPlora does not invent flows: it adopts the ones the market has already proven.

- **Charge by item and split the payment across methods**, like
  [Square](https://squareup.com/help/gb/en/article/8421-new-order-and-pay-capabilities-with-square-for-restaurants)
  and [Lightspeed](https://resto-support.lightspeedhq.com/hc/en-us/articles/226405708-Splitting-a-bill).
  There is no split by seat.
- **Void before the money moves, refund afterwards**, with a reason and a permission, without mixing the
  two paths: [Toast — voids](https://doc.toasttab.com/doc/platformguide/adminVoidingOrders.html)
  and [refunds versus voids](https://doc.toasttab.com/doc/platformguide/adminRefundsAndVoids.html);
  Lightspeed, Dynamics 365 Business Central, Square and Shopify draw the same line.
- **The kitchen order is born when it is sent, not when it is charged**, in rounds
  ([Toast — kitchen workflow](https://doc.toasttab.com/doc/platformguide/platformKDSWorkflowUsingCourses.html)).
- **An open check is charged at the price it was ordered at** (Square Orders, Oracle Simphony, Odoo,
  Business Central): changing the catalog's price does not reprice a check that is already open.
- Preset **quick notes** applied with one tap (Lightspeed Restaurant K-Series).
- **Each service carries who did it** and the appointment is charged without typing it again (Fresha,
  Vagaro).
- **Ticket or invoice** as the AEAT says: ticket (simplified invoice) up to its limit, full invoice with
  name, tax ID and address above it or on request, copy marked as duplicate
  ([AEAT — simplified invoices](https://sede.agenciatributaria.gob.es/Sede/ayuda/manuales-videos-folletos/manuales-practicos/manual-iva-2025/capitulo-10-obligac-formales-suj-registro/obligaciones-materia-facturacion/facturas-simplificadas.html),
  art. 4 of Royal Decree 1619/2012: €3,000 including VAT in hospitality, retail and hair salons).
- **Nothing in cash from €1,000** in a business in Spain, also when split across methods (Law 7/2012,
  art. 7).
- **Spain's two limits, only in Spain**: the ticket up to €3,000 and cash up to €1,000 apply only to a
  business in Spain, like Odoo's POS, which adds them with its Spanish localization
  ([l10n_es_pos](https://apps.odoo.com/apps/modules/13.0/l10n_es_pos)); outside Spain the law of its
  country rules (in Poland, for example, there is no cash cap for someone buying as a private person).

## Before you start

- **Taxes** and **Customers** are turned on with Sales and cannot be turned off while Sales is on:
  without the VAT rules no sale is closed, and the sale keeps its customer's record.
- **Inventory** is optional. With it, the POS sells its catalog and the sale lowers the stock; without it,
  the POS sells at an open price by section and says so in the grid.
- **Services** is optional (hair salon). With it, the POS sells its services (SALE-F38), at the
  professional's own price if they have one, and a service line can be paid with one of the client's
  vouchers (SALE-F27).
- **Invoicing** is optional. With it, each charge comes out with its ticket (simplified invoice) or its
  invoice numbered in its series in the same charge, and each void or refund with its corrective invoice;
  without it, the sale is a ticket with no fiscal document. Set up the **issuer** in Invoicing first:
  without it the sale is charged anyway and the document stays pending, in sight, until "Issue now"
  (SALE-F29).
- **Cash register** is optional. With "Turn on the cash register" on, nothing is charged in cash without
  an open cash session (SALE-F08); by card and other methods, it is.
- Articles must have a VAT category: otherwise they show marked "VAT missing" and are not sold.
- **Canary Islands, Ceuta and Melilla**: if in **Taxes → Settings** the business is in the Canary
  Islands, Sales says "IGIC" where it says "VAT" ("IGIC missing", "Section (IGIC)", "IGIC charged",
  "Prices include IGIC"…); in Ceuta or Melilla, "IPSI". Changing the territory renames it at once, on
  every open screen. The tax figure of **Sales** is the exception: it says the tax the sales of the period
  were declared with, not today's territory (SALE-F28).
- Out of the box there are two payment methods: **Cash** and **Card**. Bizum, bank transfer or another
  are added with the assistant by saying their type (SALE-F37).
- Selling by weight: typing the quantity (SALE-F10); there is no scale reader.
- **Currency**: the business's, its country's, with its decimals: the euro in Spain, the zloty in Poland,
  the yen (no cents) in Japan. The POS charges, types and writes in it, and each sale keeps its own: a
  sale already charged is seen, reprinted and refunded in the currency it was charged in, even if the
  business's changes. The examples in this manual are in euros, as in Spain.

Initial setup, step by step:

1. POS **Settings**: allowed methods, discounts and maximum discount, required customer, default
   document, ticket header and footer (SALE-F34).
2. **Sections**, if you charge at an open price (greengrocer, miscellaneous) (SALE-F35).
3. **Quick notes**, if the kitchen gets repeated instructions (SALE-F36).
4. Make a test sale with each method and check the ticket and its fiscal QR (SALE-F01, SALE-F02, SALE-F29).

## Screens

Sales & POS opens from the **Sales & POS** menu and has five entries: **Sell**, **Sales**,
**Quick notes**, **Sections** and **Settings**. "Sections" is what the current product called
"Departments": the short word fits in a phone's tab bar with all five in sight.

### Sell
It opens in the application's full screen; the ⋮ menu of the category strip has "Full screen" /
"Exit full screen" (the browser's, when the device allows it) and it closes by tapping outside, with Esc
or with the phone's back button. Two
areas:

- **Catalog**: the strip of Inventory categories with their number of articles, the ones the grid shows,
  sold-out ones included ("All" first and, with Services, "Services" after it), the magnifier that opens
  the search ("Search product…", by name or SKU, on the server; with Services it also searches its
  services), the "Speak" key and the grid: articles with their initials, their unit and their price (what
  is sold out, greyed with "Sold out"), and at the end the "Open price" tile. In "Services", each service
  with its initials, its duration and its price ("From", "Hourly", "Variable" or "Free" if it is not a
  fixed price). The grid asks for 100 at a time, by category, and "Load more" brings the next ones.
- **Check** (on a phone, a drawer opened by the floating button with the total): at the top, the pause
  button "Park this check", the customer one ("Assign customer" or their name), "Open checks" with their
  number, and "Close" on a phone; the editable title ("New check") and the chips for the customer,
  "Served by …" and "Customer required". Each line: name, unit price, discount mark or "Comp", note and
  professional underneath; buttons for discount, note, comp and the quantity selector (a line sent to the
  kitchen only shows its quantity, "Order N" and the ⊗ button "Void this item"; one paid with a voucher,
  "Already paid · <voucher>", 0.00 € and only the button to remove it). Footer: the "Ticket discount" row
  if there is one, "Total" (the one the server works out), the discount button, the printer ("Print
  bill") and "Charge · <amount>".

**Speak** (the strip's microphone key; only for whoever may use the assistant and on a device that can
record): press it and speak. While it records it turns red, is called "Stop" and "Listening…" shows
underneath; press it again to finish (it stops by itself after two minutes). After "Transcribing…",
what was understood lands in the assistant's box, after whatever had been written, and its panel opens:
the person reads what was understood, corrects it if needed and sends it themselves. **Nothing is sent
by itself**, and whatever it asks for goes through the confirmation card like any other request to the
assistant (BASE-F94, BASE-F97). Offline the key shows switched off and, when pressed, says "No
connection: talking to the assistant needs the internet.". With the assistant open alongside on a
tablet, the catalog stays alone and the check becomes the floating button's drawer, as on a phone.

**The phone's back button** (in the installed Android app) first closes what is open on top, one at a
time and starting from the last thing opened (a sheet, "Open checks", the check's drawer, the ⋮ menu),
and the screen stays on Sell; with nothing open, it goes to Home.

Sheets that open on top: open price, amount of a service without a fixed price, note, discount,
"Void «<article>»", "Park check",
"Who is serving this check", "You have a check in progress" and the customer search. Empty: "Tap a
product to add it." and, with no articles, "No products." (or the reason: Inventory is not active).
Notices above the grid: articles without VAT ("N items cannot be sold…" with "Review the catalogue", only
for whoever can fix it). Load error: "Error loading the till" with "Retry".

### Charge
Sheet opened by "Charge". At the top, the big amount (the one the server works out), "Paying N lines of
<total>" if there are marked lines and "Remaining" when splitting. On one side, the summary ("Receipt" /
"Invoice", customer), with "Invoice" the customer's details and, with Services, "Lines paid another
way": each service line of the charge with its voucher slot (SALE-F27). On the other, "Payments taken",
the payment methods (cash, in a business in Spain not available from €1,000, with its reason),
"Tendered", "Change" and the keypad in cash, or "Exact amount" and "Charge <amount> on the card terminal,
then confirm." with another method; "Split the payment" and "Add this payment". Footer: the reason if it
cannot be charged and "Charge <amount>" ("Charging…" while it goes); with the cash register closed and
cash, the refusal and "Open a cash session".

### Open checks
Drop-down of the check's ticket icon: "Park this check" with its explanation, "Open checks" and "Tap a
check to resume it.", and a row per open check of the business (title or amount, time and amount) with
its bin. Empty: "No open checks". A failure is painted above the rows. It closes by tapping outside, with
Esc or with the phone's back button.

### Check (bill)
"Bill" window opened by the footer's printer: the paper taken to the table, with the notice "Bill — this
is not an invoice. The fiscal receipt is issued on payment.", and the print and close buttons.

### Sales
Title "Sales", period ("Today", "7 days", "30 days", "All"), six figures ("Tickets", "Revenue", "Avg.
ticket", "VAT", "Discounts", "Voided") and the table (Date, Number, Customer, Payment, Status, Total) with
the search "Search number or customer…", filters, table or card view, 50 per page. Per row: "Document",
"Reprint", "Void" and "Refund", each where it applies; whoever lacks the permission to void or to refund
also sees them, and a manager approves it for them with their PIN. Empty: "No sales yet."; loading:
"Loading…"; error: the notice with "Retry".

### Sale document
Window with a sale's ticket: the paper as it prints (title "Receipt" or "Invoice", header, the number
Invoicing gave it —"Invoice FACT-2026-000012", "Receipt TICKET-2026-000031"— or, without it, the sale's,
date, lines, one VAT row per tax key, total, payment method, tendered and change, footer), the ✕ and the
printer. Every print from **Sales** comes out with "DUPLICATE". Error: "Error loading the document".

### Refund
Window "Refund sale <number>": explanation, one card per payment method ("Charged", "Already refunded",
"Refundable", "Refund amount" and, if needed, "Give it back through"), "Refund everything", "What goes
back" (the sale's lines with a checkbox each and, on a line of several units, "Units that go back"; the
one paid with a voucher says "Already paid · <voucher>" and, once marked, "The session goes back to
<voucher>."), "Reason" and "Refund <amount>". Loading: "Loading what can be refunded…"; nothing to
refund: "There is nothing left to refund on this sale.".

### Void sale
Window "Void sale <number>": the explanation, the "Reason (required)" and "Void" / "Cancel". A refusal is
read inside the window, which stays open. Without the permission to void, "Void" opens "An approval is
needed" on top (the platform's, BASE-F84).

### Quick notes
Explanation, table (Note, Position) with search, **+** to add and, per row, "Edit" and "Delete". Empty:
"No quick notes yet…"; loading: "Loading quick notes…". Whoever lacks the settings permission sees it
without **+** or actions.

### Sections
Explanation, table (Name, VAT charged, Position), **+** and, per row, "Edit" and "Delete". Empty: "No
sections yet…"; loading: "Loading sections…". Whoever lacks the settings permission sees it without
**+** or actions.

### Settings
Header "Point of sale": a switch or field per setting (SALE-F34) and "Save". Loading: "Loading
settings…"; error: "Could not load settings." with "Retry"; without permission: "You do not have
permission to change these settings. Ask an administrator if you need to.".

## States of each screen

| State | What the person sees |
|---|---|
| Loading | "Loading…" (or its screen's text) while the first result arrives. |
| Empty | Its screen's text, with **+** if they can create. |
| Error | The notice with "Retry"; an action's refusal shows inside its sheet or window, next to its field. |
| Reconnecting | What is painted stays; a band warns "Reconnecting…" until the connection is back. |
| App inactive (`app_inactive`) | "This app is not active in this business". |
| Speaking (Sell) | The "Speak" key, red, says "Stop" and "Listening…" shows underneath; on stopping, "Transcribing…". A notice says what fails: no voice, "Nothing was heard. Try again closer to the microphone."; with the microphone denied, "Microphone access is blocked. Allow it in your browser to speak." (in the installed app, which has no browser, "Microphone access is blocked. Allow it in your device settings to speak."); too long, "The recording is too long: say something shorter."; if it cannot be transcribed, "The audio could not be transcribed. Try again."; offline, "No connection: talking to the assistant needs the internet.". |
| No permission | What they cannot do does not show; if it arrives through another door, "You do not have permission". What a manager can approve with their PIN (voiding and refunding a sale, voiding a sent line, deleting a check with something ordered, the open price and discounts above the maximum) does show and, when pressed, asks "An approval is needed". |

## Flows

| ID | Flow | Vertical | Status |
|---|---|---|---|
| SALE-F01 | Sell and charge in cash | common | done |
| SALE-F02 | Charge by card or another method with no change | common | done |
| SALE-F03 | Split the payment across several payment methods | common | done |
| SALE-F04 | Choose ticket or invoice and the customer's details | common | done |
| SALE-F05 | Charge when the business requires a customer | common | done |
| SALE-F06 | Recover a charge left without an answer | common | done |
| SALE-F07 | The POS warns of what cannot be sold today | common | done |
| SALE-F08 | Charge without the cash register open | common | done |
| SALE-F09 | Sell at an open price by section | common | done |
| SALE-F10 | Sell by weight, typing the quantity | common | done |
| SALE-F11 | Choose an article's modifiers | common | done |
| SALE-F12 | Put together a menu | restaurant | done |
| SALE-F13 | Put a note on a line | common | done |
| SALE-F14 | Apply a discount to a line or to the check | common | done |
| SALE-F15 | Comp a line | common | done |
| SALE-F16 | Attribute the check or a line to whoever serves | common | done |
| SALE-F17 | Park a check and retrieve it | common | done |
| SALE-F18 | Delete an open check | common | done |
| SALE-F19 | Open a table's check and leave it on the table | restaurant | done |
| SALE-F20 | Send the order to the kitchen and void a sent line | restaurant | done |
| SALE-F21 | Print the bill for the table (pre-bill) | restaurant | done |
| SALE-F22 | Charge only part of the check | restaurant | done |
| SALE-F23 | Split a table's check | restaurant | done |
| SALE-F24 | Merge the checks of two tables | restaurant | done |
| SALE-F25 | Move the check to another table | restaurant | done |
| SALE-F26 | Charge an appointment from the calendar | hair salon | done |
| SALE-F27 | Pay a line with a voucher | hair salon | done |
| SALE-F28 | Look up the sales history and figures | common | done |
| SALE-F29 | See and reprint a sale's document | common | done |
| SALE-F30 | Void a charged sale | common | done |
| SALE-F31 | Refund a sale (all of it, part of it or through another method) | common | done |
| SALE-F32 | Give back a voucher's session | hair salon | done |
| SALE-F33 | Merge the sales of two customer records | common | done |
| SALE-F34 | Set up the POS | common | done |
| SALE-F35 | Add and order the open-price sections | common | done |
| SALE-F36 | Prepare the quick notes | common | done |
| SALE-F37 | Add a payment method (Bizum, bank transfer…) | common | done |
| SALE-F38 | Sell a service from Services | hair salon | done |

### SALE-F01 Sell and charge in cash
Status: done
Vertical: common
Actor: employee, manager
Screen: Sell, Charge
Steps:
1. In **Sell**, choose a category in the top strip ("All" shows everything) or press the magnifier and
   search by name or SKU.
2. Tap the article: it goes in as a line of the check. Tapping it again (same professional, no note or
   discount) raises the quantity; the line's selector raises or lowers it, and at 0 the line goes.
3. Press "Charge · <total>" at the foot of the check (on a phone, first open the check with the floating
   button, which shows the total).
4. In the **Charge** sheet, with cash chosen, enter the amount tendered on the keypad; the change shows
   large underneath.
5. Press "Charge <total>".
6. The sheet closes, the check is left empty and the **Sale document** opens with the ticket. With
   **Printing**, the charge asks the queue for the ticket in its very transaction, according to its
   settings (and, if cash came in, the order to open the drawer: PRINTING-F07, PRINTING-F13): "Sent to
   <printer>." is read and the paper on screen is already a copy. Without Printing turned on, without a
   ticket printer or with the fiscal document pending, the ticket is printed from the Sale document, as
   always; a Printing failure never undoes the charge.
In: Inventory's articles and prices; Taxes' VAT rates; the POS settings.
Out: the charged, immutable sale, with number `YYYYMMDD-NNNN` of the business day, its lines, its payment
and its VAT breakdown (one row per tax key, closed only once: the same as the invoice declares), and the
check closed. With Invoicing, its ticket (F2) numbered in the year's series in the same charge
(INVOICE-F01): both or neither. Sales announces the charged sale: Inventory lowers the stock
(INVENTORY-F21) and Customers adds the purchase to the record (CUSTOMER-F20). Each line keeps the
category, rate, country, region and Taxes rule it was charged with.
If it fails: with no amount tendered the button does not charge and "Enter the amount tendered on the
keypad" is read; too little, "The amount tendered does not cover the total". An article without VAT shows
marked "VAT missing" and, when tapped, says "Cannot be sold: no tax category. VAT needs to be set up.";
a sold-out one shows greyed with "Sold out" and, when tapped, says "«…» is sold out." (SALE-F07). A
refusal when charging is painted in the sheet with its sentence (e.g. "A product of the ticket is no
longer in the catalog. Remove the line and add it again.") and the check stays intact. If while charging
another device changes the check (adds, changes, removes, voids or charges a line, sets or removes a
discount, splits it, merges it or closes it), the first one wins: the charge charges nothing, the sheet
says "The check changed while it was being charged: a line was added, changed, removed, voided or
charged, a discount was set or removed, or the check was split, merged or closed. Nothing was charged or
changed: review the lines and try again." and the next "Charge" charges what is there; if the charge
wins, the change that was arriving is refused with the same sentence. A voided or removed line never
goes into the sale, nor is another quantity or another discount charged than the one the check keeps.
Involved: INVENTORY-F21, CUSTOMER-F20, TAX-F18

### SALE-F02 Charge by card or another method with no change
Status: done
Vertical: common
Actor: employee, manager
Screen: Charge
Steps:
1. With the check ready, press "Charge · <total>".
2. In the **Charge** sheet, tap **Card** (or whatever the method is; the active methods the settings
   allow are shown).
3. "Exact amount" and "Charge <amount> on the card terminal, then confirm." are read: charge on the
   card terminal separately.
4. Press "Charge <amount> by card". The result is that of SALE-F01.
In: the business's payment methods.
Out: the sale with one payment for the exact amount and no change; the charged-sale notice carries
each method's type, so that Cash register does not add it to the cash.
If it fails: the POS does not talk to the card terminal: if the card is declined, close the sheet
without confirming. A method the business does not allow or that is no longer active is refused: "That
payment method is not available in this business.".
Involved: none

### SALE-F03 Split the payment across several payment methods
Status: done
Vertical: common
Actor: employee, manager
Screen: Charge
Steps:
1. In the **Charge** sheet, press "Split the payment". "Remaining" appears at the top.
2. Choose a method, enter the "Amount for this payment" (in cash, what is tendered) and press "Add this
   payment". With no amount entered, the payment covers all that is left.
3. The payments taken show in "Payments taken"; the ✕ removes one.
4. When the remainder reaches 0, press "Charge <total>".
In: the payment methods and what the customer hands over.
Out: one sale with one row per method; the change always comes out of the cash and is never split.
If it fails: while money is missing, the button says "<amount> still to cover"; if the payments do not
add up to the total to the cent, the server refuses it: "The payments do not add up to the total of the
sale.". In a business in Spain, a sale of €1,000 or more admits **no** cash payment, not even split: the
cash button shows disabled with its reason and the server refuses "By law, a sale of €1,000.00 or more
cannot be paid in cash, not even in part. Charge it by card, Bizum or bank transfer.". Splitting the
check into several payments (SALE-F22) does not get round it: it counts the whole check (what has
already been charged of it and all that is left), because the law adds up the payments an operation is
split into (Law 7/2012, art. 7.One.1, paragraph 2): on a check of €1,000 or more no partial payment can
carry cash.
Involved: none

### SALE-F04 Choose ticket or invoice and the customer's details
Status: done
Vertical: common
Actor: employee, manager
Screen: Charge
Steps:
1. In the **Charge** sheet, tap "Receipt" or "Invoice". It starts on "Default document", or on "Invoice"
   if "Issue an invoice when the customer has a tax ID" is on and the assigned customer has a tax ID.
2. With "Invoice", underneath it asks for "Name or company name", "Country", "Tax ID" and "Address",
   already filled in if there is an assigned customer. Outside Spain it also asks for the "Kind of
   document" (EU VAT number, Tax ID of their country, Passport, Other document).
3. If the amount goes over the simplified invoice's limit (€3,000 in Spain), there is no "Receipt"
   button: "This sale cannot be a ticket" shows, with the same details.
4. With the three details in, "This sale goes out as a complete invoice" is read and it is charged as
   always.
In: the assigned customer (Customers).
Out: the sale with its document type fixed when charging, which cannot be changed afterwards and, with
Invoicing, its full invoice (F1) numbered in the "FACT" series in the same charge (INVOICE-F02); the
customer's name, tax ID, address, country and document type travel with it and with the charged-sale
notice, and the sale keeps its copy (what a document issued later declares, SALE-F29). The fiscal name
of a record with a company is the **company's** ("Estudio Ana SL", the company name that goes with its
CIF), not the person's; the POS keeps showing the person.
If it fails: without the three details the button says "Enter the customer's details"; an invoice
without those details is refused by the server through any route: "An invoice needs the customer's
name, tax ID and address. Fill them in or charge it as a ticket.". The tax ID is read as Customers reads
it: a Spanish NIF, NIE or CIF that does not add up shows under its box ("That tax ID is not valid.") and
the button says "Check the tax ID"; outside Spain, with no document type, "Say what kind of document a
foreign tax ID is…" (the server refuses it too, 422 on its field; a European VAT number is checked by
the server). A ticket above the limit is also refused by the server through any route: "Above €3,000.00
this sale cannot be a ticket: charge it as an invoice with the customer's details.". The country is an
ISO 3166-1 code (the same list as Invoicing: "UK" or "EL" are not valid, "GB" is): another is refused
with "Enter the country's ISO code, e.g. ES, FR or GB." (422 on `customer_country`), also the one an old
record brings. If Invoicing refuses the details of an invoice's recipient (422), the charge is not
recorded and they are corrected: there is never a "pending" invoice left that could not be issued.
Involved: CUSTOMER-F17, INVOICE-F02

### SALE-F05 Charge when the business requires a customer
Status: done
Vertical: common
Actor: employee, manager
Screen: Sell
Steps:
1. With "Require a customer on every sale" on and no customer, the check shows the "Customer required"
   chip and "Charge" looks blocked.
2. On tapping "Charge" or the chip, "This business requires a customer on every sale. Choose one to
   carry on with the charge." shows and the Customers search opens.
3. Choose or create the customer; the chip changes to their name and "Charge" opens the sheet.
In: the customer chosen in the Customers search.
Out: nothing of its own until charging; the sale carries the customer.
If it fails: the server refuses any charge without a customer: "This business requires a customer on
every sale.".
Involved: CUSTOMER-F17, CUSTOMER-F18

### SALE-F06 Recover a charge left without an answer
Status: done
Vertical: common
Actor: employee, manager
Screen: Charge
Steps:
1. Press "Charge…" and the hub does not answer (it restarts, the network drops).
2. The POS asks by itself (up to twice) whether that charge attempt got recorded.
3. If it was recorded, it closes like a normal charge. If not, "The server isn't responding (it may be
   restarting). Try again in a few seconds and, if it keeps happening, call the manager." shows and
   pressing again does not duplicate the sale.
4. If it could not be known, "We couldn't confirm whether this charge went through. Check it in Sales
   before charging again." shows with the "Check in Sales" button.
In: nothing from other apps.
Out: at most one sale per charge attempt: the attempt's key is born when the sheet opens and is reused
on every retry; the same attempt returns the same sale, also if two devices send it at once (the second
waits and receives the first one's sale, never "not charged"). A key already used for another check,
other lines or another counter sale is refused: "That attempt key was already used for another charge.
Open it again to charge this one.". If that sale's fiscal document had been left pending, the retry asks
Invoicing for it again (without charging again); if it still cannot, it stays pending, in sight
(SALE-F29).
If it fails: see steps 3 and 4; it never says "not charged" without knowing it.
Involved: none

### SALE-F07 The POS warns of what cannot be sold today
Status: done
Vertical: common
Actor: employee, manager
Screen: Sell
Steps:
1. On opening **Sell**, if there are articles without a tax category, "N items cannot be sold: their VAT
   is not set up." shows above the grid and, for whoever can fix it, "Review the catalogue", which leads
   to Inventory.
2. Those articles show in the grid marked "VAT missing" and do not go into the check.
3. What Inventory has marked as sold out shows in the grid and in the search greyed, with "Sold out":
   tapping it does not add it and says "«…» is sold out." with its name. Asking for it through the
   assistant does not add it either. What was already on a check before it sold out is split, merged,
   printed and charged just the same. As soon as it is back on sale, it can be ordered again.
4. If Inventory is not active, the grid explains it and you sell at an open price.
5. With VeriFactu active, if right now it does not allow issuing tickets or invoices (the business
   already invoices in production and its records would have no way to reach the Tax Agency), "Sales
   cannot be charged right now." shows above the grid with the reason VeriFactu gives and, for whoever can
   configure it, "Review VeriFactu". The notice goes away by itself as soon as it is fixed.
In: Inventory's sale catalog (with what is sold out) and VeriFactu's configuration.
Out: nothing.
If it fails: if the catalog does not load, "The catalogue could not be loaded." with "Retry"; the open
price is still available. If VeriFactu cannot be read, there is no notice: the charge itself says why
it does not go through. If an article sells out with **Sell** open and is tapped before the grid greys
it, it does not go into the check and the same "«…» is sold out." shows.
Involved: INVENTORY-F04, INVENTORY-F29, VERIFACTU-F08

### SALE-F08 Charge without the cash register open
Status: done
Vertical: common
Actor: employee, manager
Screen: Charge
Steps:
1. With "Turn on the cash register" on in Cash register and no open cash session, charge in cash (also
   a split payment with a part in cash).
2. The **Charge** sheet charges nothing and says "The cash register is closed: open a cash session to
   charge in cash."; to whoever can open it, it offers "Open a cash session", which leads to **Cash
   register**. The **Sell** screen does not change: the check is still there.
3. With the session open, go back to **Sell** and charge. By card, Bizum or bank transfer it always
   charges, with the cash register open or closed.
In: whether the cash register is turned on and whether there is an open session, which Sales asks Cash
register (`cash_register.session.current`) with the session of whoever charges, only when there is cash.
Out: nothing of its own; the refused charge does not use up a number.
If it fails: if Cash register is not in the business, is off or does not answer (a refusal, a failure),
it charges: the block gives way rather than stopping the sales, and Cash register shows that charge
among the ones in no shift (CASH_REGISTER-F17).
Involved: CASH_REGISTER-F04, CASH_REGISTER-F17

### SALE-F09 Sell at an open price by section
Status: done
Vertical: common
Actor: manager (employee with the open-price permission); cashier, with a manager's approval
Screen: Sell, An approval is needed
Steps:
1. Tap the "Open price" tile, at the end of the grid.
2. Enter the amount on the keypad and choose the section in "Section (VAT)"; each button shows its VAT
   rate.
3. Press "Add <amount>": a line goes in with the section's name and that amount. It is never added to
   another line.
4. If you do not have the open-price permission, pressing "Add <amount>" opens "An approval is needed" on
   top with "Approving: Sell at an open price of {unit_price, money}" (the amount entered, in the
   business's currency): a manager approves it with their PIN (or their badge) on that same device
   (BASE-F84) and the line goes in. If there was no check yet, it opens empty and the line waits for the
   approval.
In: the business's sections (SALE-F35) or, if there are none, Taxes' VAT categories.
Out: a line with no catalog article, with its amount and its VAT category, which is charged like any
other.
If it fails: "Add" cannot be pressed without an amount and a section; with no sections or categories,
"There are no tax categories to choose from. Set up your VAT first, in Taxes.". If "Cancel" is pressed
in "An approval is needed", the line does not go in and the sheet says "This needs a manager's
approval.". Without the permission or the approval, the server refuses the line through any other route
(also when charging directly).
Involved: TAX-F18, BASE-F84

### SALE-F10 Sell by weight, typing the quantity
Status: done
Vertical: common
Actor: employee, manager
Screen: Sell
Steps:
1. Tap an article whose unit is of mass, volume or time (kg, g, l, h…): it goes in as a line with its
   unit.
2. Type the quantity in the line's selector (e.g. 0.532).
3. The amount is worked out again on the server and the line shows the unit ("0.532 kg").
In: the article's unit, its step and the quantity its price refers to, from Inventory.
Out: the line with its quantity and its unit frozen.
If it fails: a quantity that does not fit the unit's step is refused with "The quantity does not fit
the step of the product (…)." and the line stays as it was. There is no scale reader.
Involved: INVENTORY-F26

### SALE-F11 Choose an article's modifiers
Status: done
Vertical: common
Actor: employee, manager
Screen: Sell
Steps:
1. With Modifiers active, tap an article that has modifier groups (its own or its category's): a sheet
   opens with its name. Without groups, the article goes straight in, as always.
2. Each group says its rule: "Choose N" if it asks for exactly N, "Choose N to M" if it asks for a
   minimum and lets you reach a ceiling, "Choose at least N" if it asks for a minimum with no ceiling,
   "Up to N" if it only has a ceiling, "Optional" if not; each option carries its extra charge with its
   sign ("+€1.00", "−€2.00"; nothing if it is free) and the default ones already show marked.
3. Tap the options: in a single-choice group, tapping another changes it and tapping the same one
   removes it; in one with a ceiling, on reaching it the next tap says "«Extras» is full: take one out to
   choose another."; an option that can be repeated carries its counter ("× 2") and its "−".
4. Press "Add · <price>": the line goes in with its modifiers under the name and its price already added
   up. While a required group is not complete, the button says "Choose an option to continue" and tapping
   it points to that group.
5. Charge as always (SALE-F01): the line charges what it was worth when ordered even if the modifier
   changes or is deleted later. A modifier with another VAT rate (the soft drink of the kids' menu, at
   21 % next to the burger at 10 %) shows on the ticket as its own line under the dish ("+ Soft drink"),
   for each dish.
In: Modifiers' groups and options, which checks and prices what was chosen when the line is added.
Out: the line with its modifiers frozen (announces: check changed); the kitchen order carries them under
the dish ("+CHEESE, -ONION", announces: order sent); when charged, the ticket names them under the dish
and each modifier with another VAT is a line of its own with its base and its tax amount; only the dish
lowers the stock.
If it fails: Modifiers' reasons inside the sheet ("Choose at least 1 in «Doneness».", "This option is not
offered with this product."…), also through the assistant or the API, which do not go through the sheet:
a required group left unchosen is refused just the same. If the groups cannot be read, "The options of
this product could not be read. Try again." and nothing goes in. Without Modifiers active, an article
with modifiers ordered through the API is refused ("Modifiers is not active in this business…") and one
without them goes in as always.
Involved: MODIFIER-F06, MODIFIER-F07, MODIFIER-F08

### SALE-F12 Put together a menu
Status: done
Vertical: restaurant
Actor: employee, manager
Screen: Sell
Steps:
1. With Menus and combos active, in "All" the menus on sale show first, each with the "Menu" label and
   its set price. Tap one: a sheet opens with its name and all its courses at once.
2. Each course says its rule ("Choose 1", "Choose 1 to 4", "Up to 2", "Optional") and its choices, with
   the extra charge with its sign if it is not zero ("+€2.00"). On opening nothing is chosen.
3. Choose: in a single-choice course, tapping another changes it; in one with a ceiling, on reaching it
   the next tap says "«Coffee» is full: take one out to choose another."; a choice that can be repeated
   carries its counter and its "−".
4. While something is missing, the button says what ("Choose 1 in «Mains»") and tapping it points to that
   course; when each required course is complete, it says "Add · <total>" with the set price plus the
   extra charges. Press it: the menu goes into the check as one line, with its courses under the name.
   Each menu is a line of its own; its quantity changes by whole units.
5. Charge as always (SALE-F01): the menu charges the amount it had when ordered even if its price goes
   up later, a dish sells out or the menu is withdrawn (also with Menus and combos turned off: it charges
   what it froze). "Eat in" shows on one line at the menu's VAT; "Take away" with dishes of different
   VAT shows one line per dish, with the amount shared out according to each one's catalog price (€6.00
   for sandwich and small beer: €4.15 at 10 % and €1.85 at 21 %), and no menu line with money.
In: Menus and combos' menus; Menus checks the dishes chosen and sets the price when the line is added
and again when charging, with the amount ordered.
Out: the menu line with its dishes and its amount frozen (announces: check changed); the kitchen order
carries it with its kitchen name and each dish with its quantity (announces: order sent); when charged,
the ticket puts the menu's name and under it each dish on its own line, or, split, the name as a header
and each dish with its amount and its VAT; the sale notice carries each dish times the number of menus,
so that Inventory lowers the stock of each dish and never that of the menu (announces: sale charged); a
refund gives back each dish times the menus refunded (announces: sale refunded).
If it fails: Menus' reasons inside the sheet ("The menu still needs a pick in “Mains”: pick 1.", "“Flan”
is sold out."…), also through the assistant or the API, which do not go through the sheet: a half-made
menu does not go into the check, so it never reaches the kitchen without its dishes. A quantity with
decimals: "The quantity does not fit the step of the product (1 ud).". If the menus cannot be read,
above the grid "The menus could not be read. Try again." with "Retry", and the products sell just the
same. Without Menus and combos active, the POS offers no menus and one ordered through the API is refused
("Menus and combos is not active in this business…").
Involved: COMBO-F07, COMBO-F08, COMBO-F09, COMBO-F10, COMBO-F11, INVENTORY-F22

### SALE-F13 Put a note on a line
Status: done
Vertical: common
Actor: employee, manager
Screen: Sell
Steps:
1. On the line, tap the "Note" button.
2. Tap the quick notes shown at the top (they add up separated by commas; tapping them again removes
   them) or type in the box (up to 255 characters).
3. Press "Save": the note shows under the line. "Remove", or leaving the box empty, deletes it.
In: the business's quick notes (SALE-F36).
Out: the note on the line; it travels to the kitchen order and to the printed bill, and stays frozen in
the sale.
If it fails: if the quick notes do not load, "The quick notes could not be loaded — type the note by
hand.". If it is not saved, "That change to the line could not be saved. The line is back as it was.".
A line already sent to the kitchen has no note button.
Involved: none

### SALE-F14 Apply a discount to a line or to the check
Status: done
Vertical: common
Actor: employee, manager; above the maximum, the cashier with a manager's approval
Screen: Sell, An approval is needed
Steps:
1. For a line, tap its price tag ("Line discount"); for the whole check, the tag button in the footer
   ("Ticket discount").
2. Enter the percentage; on the check you can switch to a fixed amount with the button of the business's
   currency ("€", "zł"…).
3. Press "Apply −N %" (or "Apply −<amount>"). "Remove" deletes it. The line shows "−N %" and the footer
   the row "Ticket discount −N %" with what the check's discount takes off, be it a percentage or a fixed
   amount: 10 % on €8.50 says "−€0.85", never "−€0.00". The server works it out (the charge's pricing,
   `ticket_discount_amount`) on the lines already with their own discount.
4. If the discount goes over the maximum the business lets you give without authorization, a manager
   gives it: whoever cannot give it sees "An approval is needed" on top with what is being approved and
   its figure, that of that very discount: "Approving: Discount a line by {discount_percent, percent}"
   (the percentage entered) or, on the check, "Approving: Discount the check by {discount_percent,
   percent}" or, with a fixed amount, "Approving: Discount the check by {discount_amount, money}" (in
   the business's currency), and a manager approves it with their PIN (or their badge) on that same
   device (BASE-F84). With no figure to say (a zero), the usual sentence: "Approving: Discount the check
   above the maximum". The check keeps who authorized it and does not check it again when charging; if,
   when charging, the discount goes over the maximum without authorization, it asks just the same, with
   "Approving: Charge with a discount above the maximum" (a sale with no check, the assistant's, says
   its own: "Approving: Charge with a discount of {discount_percent, percent}" or "Approving: Charge with
   a discount of {discount_amount, money}"). Employees › Approvals keeps what was approved with its figure
   (BASE-F85).
In: "Allow discounts" and the maximum discount of the settings.
Out: the discount on the check or on the line; when charging it is shared out among the lines, the
declared base and VAT already carry it discounted, and the sale keeps the discounted amount.
If it fails: with "Allow discounts" off there are no buttons and the server refuses "This business does
not allow discounts.". Above the maximum, if "Cancel" is pressed in "An approval is needed", the check
stays as it was and "This needs a manager's approval." is read. An amount greater than the check cannot
be applied. When charging a check, the discount goes on the check, never on the charge request: one that
brings it is refused with "The discount of an open check is set on the check itself, not at the
charge." and "An approval is needed" does not say that figure. If another device is charging that
check, the first one wins (SALE-F01).
Involved: BASE-F84, BASE-F85

### SALE-F15 Comp a line
Status: done
Vertical: common
Actor: employee, manager
Screen: Sell
Steps:
1. On the line, tap the gift ("Comp / un-comp line").
2. The line goes to 0 with the "Comp" mark; tapping it again charges it again.
In: nothing from other apps.
Out: the comped line: it adds no money or VAT, but the sale notice carries it so that Inventory lowers
the stock; the sale keeps the cost of what was comped.
If it fails: "That change to the line could not be saved. The line is back as it was.". A line already
sent to the kitchen cannot be comped.
Involved: INVENTORY-F21

### SALE-F16 Attribute the check or a line to whoever serves
Status: done
Vertical: common
Actor: employee, manager
Screen: Sell
Steps:
1. In the check's header, the "Served by me" chip says who it is attributed to. Tap it.
2. In "Who is serving this check", choose the person from the Staff team or "Me (whoever is signed in)".
   If your account has no record in Staff, the sheet warns about it: "Your account has no record in
   Staff: left on «Me», this sale counts for nobody."
3. The lines added from then on are stamped with that person. To correct a line already in, tap the
   name shown under it ("Whose line is this") and choose another person or "The check's professional".
4. Charge. With the chip on "Me", the sale is attributed to your Staff record; a line with its own
   professional (an appointment's, the one you moved) keeps them. Afterwards, the chip goes back to "me".
In: the Staff team (active records) and the record of whoever is signed in.
Out: the sale and each line attributed to that person, for the close by professional and Staff's
commissions (STAFF-F21). With "Me", the sale belongs to the record of whoever charges; without a record,
it counts for nobody. The kitchen order sent carries their name (KITCHEN-F18); with "Me", that of whoever
sends it.
If it fails: "The team could not be loaded. The sale is still attributed to whoever is signed in.";
"The line could not be moved to another professional. It stays with the one it had.". A line sent to
the kitchen is not reassigned.
Involved: STAFF-F21, KITCHEN-F18

### SALE-F17 Park a check and retrieve it
Status: done
Vertical: common
Actor: employee, manager
Screen: Open checks
Steps:
1. With a check in progress, press the pause button ("Park this check") or, in **Open checks**, "Park
   this check".
2. In "Park check" the title comes with the time; change it if you like ("e.g. Ana — terrace") and
   confirm: "Parked as “…”" shows and the screen is left empty, of customer too.
3. To resume it, open **Open checks** (ticket icon with the number of checks) and tap its row; its
   customer comes back with it.
4. If there is another check in front, it asks "You have a check in progress": "Park it and open",
   "Delete it and open" or "Cancel".
5. On reloading the screen, each device goes back to the check it had open.
In: on resuming the check, its customer, from Customers (CUSTOMER-F19).
Out: the check stays open with its title; parking never voids it.
If it fails: "The check could not be parked. It is still on screen.". With "Allow parked tickets" off
there is no park button anywhere.
Involved: CUSTOMER-F19

### SALE-F18 Delete an open check
Status: done
Vertical: common
Actor: manager; an empty check, also the employee; one with something ordered, the cashier with a manager's approval
Screen: Open checks, An approval is needed
Steps:
1. In **Open checks**, tap the check's bin: it changes to "Tap again to delete — this voids the check".
   If it is not tapped within 3 seconds, it disarms.
2. Tap again: the check disappears from the list. It is also deleted with "Delete it and open" when
   switching checks.
3. If the check has something ordered or charged and you do not have the permission to void, "An approval
   is needed" opens on top with "Approving: Delete an open check with something on it": a manager
   approves it with their PIN (or their badge) on that same device (BASE-F84) and the check is deleted.
In: the chosen check.
Out: the check is left voided, not deleted (announces: check voided); what was already charged of it
stays in its sales.
If it fails: "That open check could not be deleted. It is still in the list.". A check already charged
cannot be voided: "That check is no longer open."; voiding it twice does nothing the second time.
Whoever builds checks sees the bin on all of them: an **empty check** (no live lines or payments) they
delete themselves, because a group that leaves without ordering should not force calling a manager (like
Tables when closing an empty table, TABLE-F21); with something ordered or charged it takes the permission
to void or a manager's approval. If "Cancel" is pressed in "An approval is needed", the check stays in
the list and "This needs a manager's approval." is read on top.
Involved: TABLE-F20, TABLE-F21, BASE-F84

### SALE-F19 Open a table's check and leave it on the table
Status: done — without asking for the number of guests in the POS (see "What stays out")
Vertical: restaurant
Actor: employee, manager
Screen: Sell
Steps:
1. With Tables active and the permission to seat, the check's bar has, before the customer, the table
   button (grid, "Assign table"). Tap it: "Choose table" opens, with a search ("Search a table…", on the
   server) and the tables in service as tiles in the colour of their state (Available green, Occupied
   red, Reserved amber, Blocked grey), with the number, the area, the seats ("4 pax"), the state and, if
   it has one, today's reservation ("Marta · 21:00"). With no tables: "There are no tables yet. Set them
   up in Tables → Floor plan.".
2. Tap an Available or Reserved table: the check on screen sits there (TABLE-F12) and takes its name as
   its title ("Table 4"); with no check yet, Tables opens one with that title and the POS puts it on
   screen (TABLE-F10). A check whose table was taken off sits again (TABLE-F24). The Occupied and Blocked
   ones cannot be tapped (their title says why).
3. The check's header shows its table ("Table 4") and the button is painted in colour.
4. "Remove from table", in the same window, releases the table without charging: the table is left free
   and the check stays open in **Open checks** (TABLE-F13).
In: the tables, their state and the check's table, from Tables (`table.table.list`,
`table.floor.status`, `table.session.by_order`), followed live.
Out: nothing of its own; Tables seats (`table.session.open` with the check, `.restore`) or releases
(`table.session.park`) with the session of whoever serves, and retitles the check (`sale.order.set_label`).
If it fails: Tables' refusal inside the window, in its words ("Another device has just taken that
table…", "That check is already at table N."…). Without Tables active, or without the permission to see
its tables and seat, there is no button and Tables is not asked anything.
Involved: TABLE-F10, TABLE-F12, TABLE-F13, TABLE-F24

### SALE-F20 Send the order to the kitchen and void a sent line
Status: done
Vertical: restaurant
Actor: employee (send), manager (void; the cashier, with a manager's approval)
Screen: Sell, An approval is needed
Steps:
1. With Kitchen active, the check has two tabs: "Check", with all its lines, and "Current order", with
   what is still to be sent; the tab says how many items are waiting ("Current order, 2 items to send").
   With nothing pending, "Everything is sent".
2. In "Current order", review quantities and who serves and press "Send order (N)". For it to go out as
   a rush, first arm the flame next to it: the button changes to "Send RUSH (N)". "Order N sent to the
   kitchen." shows; the lines are marked with their round ("Order N") and the time sent, and the flame
   disarms. A double send never sends anything twice.
3. On pressing "Charge" with something pending, it is sent to the kitchen first and then the charge
   opens: nobody pays for a dish that is not going to be made. If the send fails, the charge does not
   open and it says why.
4. A sent line is locked: no quantity, no note, no discount, no comp.
5. To take off a dish already sent, press ⊗ "Void this item" on its line: "Void «<article>»" opens with
   "It was already sent to the kitchen. It comes off the check and the reason is kept. A manager has to
   approve it.", the one-tap reasons ("Ordered by mistake", "Customer changed their mind", "Sold out",
   "Entered twice") and "Or write the reason…". "Void item" cannot be pressed without a reason.
6. If you do not have the permission to void, pressing "Void item" opens "An approval is needed" on top
   with "Approving: Void an item already sent to the kitchen": a manager approves it with their PIN (or
   their badge) on that same device (BASE-F84). "Cancel" keeps the line and the sheet says "This needs a
   manager's approval.".
7. The line comes off the check, the total goes down and the line keeps the reason, who authorized it
   and when.
8. To follow what was sent, in "Check" press "Tickets · N", next to the header of what was sent: "Order
   tickets" opens, one card per round (the most recent on top) with its state in the kitchen, and from it
   a round being cooked is marked as a rush (KITCHEN-F19, KITCHEN-F20).
In: the check's pending lines.
Out: the lines with their round and the kitchen order open in Kitchen, a rush if the flame was armed
(announces: order sent, with the lines, their notes, their modifiers, the dishes of each menu and who
serves); on voiding a sent line, it announces the voided line with its reason.
If it fails: with nothing pending, "There is nothing new to send to the kitchen."; if Kitchen does not
answer, "The order could not be sent to the kitchen. Try again." and nothing is charged. If the order is
sent but its slip does not print, the POS warns "Order N sent to the kitchen, but it did not print.
Check the kitchen printer in Printing.". Asking to remove a line already sent is refused: "That line can
no longer be removed: it was sent to the kitchen (void it with a reason), it is charged or it is no
longer on an open check.". Voiding a line not sent, charged, already voided or without a reason is
refused with "That line cannot be voided…". Without Kitchen active there are no tabs and no sending: the
check is charged as always.
Involved: KITCHEN-F05, KITCHEN-F18, KITCHEN-F19, KITCHEN-F20, KITCHEN-F29, BASE-F84

### SALE-F21 Print the bill for the table (pre-bill)
Status: done
Vertical: restaurant
Actor: employee, manager
Screen: Check (bill)
Steps:
1. With the check on screen, press the footer's printer ("Print bill").
2. "Bill" opens with the lines, notes, discounts, the VAT breakdown, the total and the title, and the
   notice "Bill — this is not an invoice. The fiscal receipt is issued on payment.". With a discount on
   the check, the "Discount" row says what it takes off (the same amount as the POS footer, SALE-F14):
   with prices including VAT, the lines minus the discount give the total.
3. Press the printer at the top: with **Printing** and an active ticket printer, the bill goes to its
   queue and "Sent to <printer>." is read (PRINTING-F09); if not, it goes through the device's print
   dialog.
In: the open check and its total worked out by the server.
Out: a paper with no fiscal number; it uses up no numbering and creates no sale. Each press, one bill.
If it fails: "Bill could not be printed".
Involved: PRINTING-F09

### SALE-F22 Charge only part of the check
Status: done
Vertical: restaurant
Actor: employee, manager
Screen: Sell
Steps:
1. With two or more lines, tap the lines this person pays for (the line, not its buttons): they are
   marked with a circle.
2. Press "Charge": the sheet says "Paying N lines of <total>" and charges only those.
3. After charging, the **Sale document** of that charge opens and, behind it, the check stays open with
   what is left; what was charged does not show again. Charging the last pending line closes the check.
   Whether it is partial or full is said by what was charged (the lines fixed when the sheet opened), not
   by what is marked when finishing.
In: the marked lines.
Out: a sale with those lines (announces: sale charged); the lines are left tied to their sale. The
check's % discount applies to each charge; the fixed-amount one, only to the one that closes it.
If it fails: the same refusals as a normal charge, also that of the check that changed while it was
being charged (SALE-F01): the sheet charges the lines and the version it showed when it opened, never
those of later. If, with the sheet open, another device closes the check, the screen lets it go on
closing the sheet and warns; no ghost check is left.
Involved: none

### SALE-F23 Split a table's check
Status: done — the "Split check" button belongs to Tables' table control (TABLE-F17)
Vertical: restaurant
Actor: employee, manager
Screen: none of its own (the table control belongs to Tables; also through the assistant or the API)
Steps:
1. The lines that move to a new check are chosen and it is split.
2. The lines move whole to the new check with their amount, their VAT and their kitchen round. With no
   lines, the new check is born empty.
In: the check and the lines that move.
Out: two open checks that add up to the same as the original to the cent (announces: check opened).
If it fails: if another device is charging that check, the split waits and, if it charged it, is refused
("The check changed…") without moving anything.
Involved: TABLE-F17

### SALE-F24 Merge the checks of two tables
Status: done — the "Merge" button belongs to Tables' table control (TABLE-F16)
Vertical: restaurant
Actor: employee, manager
Screen: none of its own (the table control belongs to Tables; also through the assistant or the API)
Steps:
1. The check that is absorbed and the one that stays are chosen.
2. The uncharged lines of one move to the other and the empty one is left voided.
In: the two checks.
Out: a single check; the lines are moved without creating them again, so what was already sent to the
kitchen is not sent again. The absorbed one is left voided and says which one it was merged with: the
POS that had it on screen, on this device or another, moves to the one that stays with the notice "That
check was joined with another one: the screen shows the joined check.", never "closed on another
device"; if at that moment it was saving a change on it, it first finishes that change. Repeating it
changes nothing (announces: checks merged, with the absorbed one and the one that stays).
If it fails: if one of the two is no longer open, it is refused without moving anything.
Involved: TABLE-F16, KITCHEN-F28

### SALE-F25 Move the check to another table
Status: done in Tables (TABLE-F15): the check does not change
Vertical: restaurant
Actor: employee, manager
Screen: none
Steps:
1. In the table control (Tables'), press "Transfer".
2. Choose the free table.
In: the destination table, from Tables.
Out: nothing in Sales.
If it fails: Tables will say.
Involved: TABLE-F15

### SALE-F26 Charge an appointment from the calendar
Status: done — the calendar's "Charge" button belongs to Appointments (APPOINTMENT-F17)
Vertical: hair salon
Actor: employee, manager
Screen: Sell
Steps:
1. In the Appointments calendar, "Charge" opens the appointment's check (with one line per service, at
   its booked price and with the professional) and goes to the POS with that check on screen
   (`/sale/pos?order=<id>`).
2. It is charged as in SALE-F01; if it is parked and retrieved, the check stays tied to the appointment.
3. Pressing "Charge" again (or on another device at the same time) goes back to the same open check: an
   appointment has a single open check, never two.
In: the appointment, from Appointments.
Out: the sale with the appointment and the professional (announces: sale charged and sale born from an
appointment, with the appointment, who served and the total).
If it fails: linking an appointment to a check that is no longer open is refused; linking it to another
check when it already has an open one, "That appointment already has an open check: charge that one
(Open checks).". If the address names a check that is no longer open (it was charged, voided) or that
does not exist, the POS says so ("That check is not open any more…") and carries on as it was.
Involved: APPOINTMENT-F17

### SALE-F27 Pay a line with a voucher
Status: done
Vertical: hair salon
Actor: employee, manager
Screen: Charge
Steps:
1. With Services active and the client assigned to the check, press "Charge": "Lines paid another way"
   appears with each service line of the charge and, in its slot, "Pay this line with a voucher": the
   client's vouchers that cover that service, the one that is spent first and why (SERVICE-F22).
2. If the line is of more than one unit ("Haircut × 2"), press "Split into N lines": a voucher pays a
   whole line of one unit, and each one has its slot.
3. Choose the voucher (the one spent first comes chosen) and press "Spend one session": the line goes to
   0.00 € with "Already paid · <voucher>", the charge's amount goes down and the slot says "<voucher>:
   session spent. N left." with "Undo". What the voucher does not pay is charged with its method; if the
   voucher pays everything, 0.00 € is charged with no payment method.
4. Charge: the line shows on the ticket at 0.00 € with "Already paid · <voucher>" and the session is left
   spent.
5. Closing the sheet, parking the check, reloading or charging it on another device changes nothing: the
   check's line keeps the voucher that pays it.
In: the client's vouchers and their balance, from Services.
Out: the check's line paid with a session held in Services (announces: check changed); when charged, the
sale with the line at 0.00 € and the session spent in the same operation (SERVICE-F24). Removing the
line, voiding it or deleting the check releases the session (SERVICE-F23); splitting or merging checks
carries it with its line. A line paid with a voucher does not change quantity, comp or discount: the
voucher is undone first.
If it fails: Services' reasons are read in the slot ("This voucher has no sessions left.", "This voucher
has expired."…). A line that is not a service, a comp or one of several units cannot be paid with a
voucher ("A voucher pays a line of one unit: split the line first."); a fixed-amount check discount
bigger than what would be left to pay is refused ("That discount is bigger than what it comes off.").
When charging, nothing is charged if the session is no longer held (a day went by, SERVICE-F25) or if the
sale is not the voucher holder's: the reason is read in the sheet and the voucher is undone. The maximum
discount without a manager is measured on what is left to pay: a line paid with a voucher does not count.
Without the permission to spend sessions, the slot does not appear. Without Services active in the
business the slot does not appear either and, if it is turned off with lines paid with a voucher,
charging them is refused ("Services is not active in this business…").
Involved: SERVICE-F22, SERVICE-F23, SERVICE-F24, SERVICE-F25

### SALE-F28 Look up the sales history and figures
Status: done
Vertical: common
Actor: employee (history), manager (figures)
Screen: Sales
Steps:
1. Open **Sales & POS → Sales**. At the top, the period ("Today" by default, "7 days", "30 days",
   "All"), counted in the business day.
2. The period's figures: "Tickets", "Revenue", "Avg. ticket", "VAT", "Discounts" and "Voided". "Revenue"
   already takes off what was refunded. The tax figure carries the name of the tax the period's sales
   were declared with: "VAT", "IGIC" if all of them were charged with IGIC (Canary Islands) or "IPSI"
   (Ceuta and Melilla). If in the period there are sales of two taxes (because the business changed
   territory halfway, for example), it is called "Taxes". With no sales in the period, it carries the tax
   of the territory in **Taxes → Settings**, and changes at once if the territory is changed. With "7
   days", under the figures, what was sold on each of those days, from oldest to today ("Wed 14 ·
   €120.50").
3. The table: Date, Number, Customer, Payment, Status (Completed, Voided, Refunded; with "<amount> left to
   refund" if part was refunded) and Total. Search with "Search number or customer…", filter by status,
   payment, date or total, or sort.
4. Tap a row to see its document (SALE-F29). The table reloads by itself when a sale is charged, voided
   or refunded.
5. Today's figures are also on **Home**, on the board, as in the current product: "Today's sales" and
   "Today's tickets" show from the start; "Sales, last 7 days" (one bar per day, from oldest to today) and
   "Recent activity" (the last eight sales, the newest on top, with their number and their customer) are
   added with ⋮ ("Customize panel"). They update by themselves when a sale is charged, voided or refunded,
   without reloading. Whoever lacks the reports permission can only add "Recent activity".
In: nothing from other apps.
Out: nothing saved. What each professional sold in the period (Staff and the assistant ask for it for the
commission) already takes off what was refunded: what goes back, to whoever sold it; the money that goes
back with nothing that is worth anything (only money, a comp or a voucher's session), to everyone on that
sale according to what each one has left to refund after the earlier refunds, so nobody goes below 0.
Each refund counts on its sale's day and is shared out to the cent: with what nobody served, it adds up
to the period's "Revenue".
If it fails: "Error loading metrics" (the figures show as "—"); if the last 7 days cannot be read, "The
last 7 days could not be read.". Empty: "No sales yet.". Whoever lacks the reports permission sees the
table, without the figures. A total that is not an amount says "Type an amount, like 12.50" under its
field, and an end date before the start one, "The end date cannot be before the start date."; neither of
them filters and the period rules. On Home, a panel for a day with no sales says 0, and one that cannot
be read, "Unavailable".
Involved: STAFF-F21, BASE-F06, BASE-F07, BASE-F08

### SALE-F29 See and reprint a sale's document
Status: done
Vertical: common
Actor: employee, manager
Screen: Sale document
Steps:
1. In **Sales**, tap the row or the "Document" action; it also opens by itself after charging, the whole
   check or part of it (SALE-F22).
2. The ticket shows ("Receipt", or "Invoice" if it was charged as an invoice) with its header, the number
   Invoicing gave it when charging ("Invoice FACT-2026-000012", "Receipt TICKET-2026-000031"; without
   Invoicing, or while its document is pending, the sale's number), date, lines, one VAT row per tax key
   (an exempt one says its cause: "Exempt (E1)"), total, payment method, tendered and change, and the
   footer. With **VeriFactu**, before the footer goes the fiscal QR: "Tax QR:" above, "VERI*FACTU" below
   and "Scan it to check this receipt at the AEAT" ("…this invoice…" if it is an invoice); once the AEAT
   has answered, its code ("CSV: …") instead of that sentence. While VeriFactu has no record of that
   document, the paper comes out without a QR. If its fiscal document could not be issued when charging,
   the paper says so under the number ("Fiscal document pending") and, above the paper (outside what is
   printed), the notice
   "Fiscal document pending — Invoicing could not issue it when charging (the issuer is missing, or a
   permission). Once that is fixed, issue it now." with "Issue now".
3. Press the footer's printer to print it, or "Reprint" on the row. With **Printing** and an active
   ticket printer, the paper goes to its queue and "Sent to <printer>." is read (PRINTING-F08); if not (or
   with its fiscal document pending), it goes through the device's print dialog. Every print from
   **Sales** comes out with "DUPLICATE", also with its fiscal QR; only the first paper right after
   charging is the original (and it is a copy if the charge already sent it to the queue).
4. **Document pending**: in the list, a sale with some fiscal document pending (its own, the corrective
   invoice of its void or that of a refund) carries the "Document pending" pill under its status and the
   "Issue now" action (for whoever charges). "Issue now" asks Invoicing, by name and with the session of
   whoever presses it, for everything that is waiting, in order (its ticket or invoice and then the
   corrective invoices) and "Fiscal documents issued." shows. Before that, the hub retries it by itself
   for a few minutes (INVOICE-F06): if the cause is fixed in time, the pill goes away by itself.
In: the sale, with the number of its fiscal document (which Invoicing gave it in the same charge).
Out: the paper; reprinting creates no sale or fiscal document. "Issue now" issues the documents that were
waiting (announces: sale with its document, one per document).
If it fails: "Loading document…" and "Error loading the document" (also if the fiscal QR cannot be read:
the paper never comes out without it). "Could not print". A refused "Issue now" says Invoicing's reason
("Set up the issuer…") and changes nothing; without words from the server, "The documents could not be
issued. Try again.".
Involved: INVOICE-F01, INVOICE-F02, INVOICE-F06, INVOICE-F18, PRINTING-F08, VERIFACTU-F19

### SALE-F30 Void a charged sale
Status: done
Vertical: common
Actor: manager; cashier, with a manager's approval
Screen: Sales, Void sale, An approval is needed
Steps:
1. In **Sales**, on a Completed sale with no refunds, press "Void".
2. "Void sale <number>" opens. Write the "Reason (required)" and press "Void", or "Cancel".
3. If you do not have the permission to void, "An approval is needed" opens on top with "Approving: Void
   a sale": a manager taps their face and types their PIN (or swipes their badge) on that same device
   (BASE-F84). Whoever has the permission does not see this question.
4. "Sale voided" shows, the window closes, the row changes to Voided and the "Voided" figure goes up.
In: the chosen sale.
Out: the sale marked as voided with time, who and reason; it is not deleted (announces: sale voided).
With Invoicing, the corrective invoice of the whole ticket (R5, "RECT" series) in the same void
(INVOICE-F07); if the ticket had been left pending, it is issued first, in the same void. If Invoicing
still cannot, the void goes ahead and both documents are left pending, in sight (SALE-F29, "Issue now").
Inventory puts back the stock (INVENTORY-F23) and Customers takes off the purchase (CUSTOMER-F21).
If it fails: without a reason, "A reason is required to void a sale"; if it was charged as a full
invoice, "This sale carries a full invoice: issue a credit note instead of voiding it."; with refunds,
"This sale already has refunds: refund what is left instead of voiding it."; voided from another device
at the same time, "This sale is already voided.". A refusal is read inside the window, which stays open.
If "Cancel" is pressed in "An approval is needed", nothing is voided and the window says "This needs a
manager's approval.". The approved void does the same as the manager's, only once: the corrective
invoice in the same void, the voucher sessions that go back, the stock and the customer's record; who
approved it stays in **Employees › Approvals** (BASE-F85).
Involved: INVENTORY-F23, CUSTOMER-F21, INVOICE-F07, BASE-F84

### SALE-F31 Refund a sale (all of it, part of it or through another method)
Status: done
Vertical: common
Actor: manager; cashier, with a manager's approval
Screen: Refund, An approval is needed
Steps:
1. In **Sales**, on a Completed sale (also with an invoice), press "Refund".
2. "Refund sale <number>" shows one card for each way it was paid: "Charged", "Already refunded" and
   "Refundable", with a proposal for a full refund already shared out ("Refund everything" puts it back).
3. If the customer returns articles, mark them in "What goes back": the amount is proposed by itself (the
   share of each marked line, without going over what is left). With two or more units to refund, "Units
   that go back" shows to choose how many. A line part of which already came back says "<n> of <m>
   already returned"; one that came back whole shows as "Already returned". Without marking anything only
   money is refunded.
4. Change the "Refund amount" of each method if only part goes back. If the original method is no longer
   available, choose another in "Give it back through".
5. Write the "Reason" and press "Refund <amount>". If you do not have the permission to refund, "An
   approval is needed" opens on top with "Approving: Refund a sale": a manager approves it with their PIN
   (or their badge) on that same device (BASE-F84). Whoever has the permission does not see this question.
6. "Refund recorded." shows; if nothing is left to refund, the sale changes to Refunded; if something is
   left, the row says "<amount> left to refund".
In: what was charged and what was already refunded for each payment method; the sale's lines and the ones
that already came back.
Out: the refund document with one row per payment method, the lines that go back with their units, its
reason and who made it (announces: sale refunded, with the refunded lines and whether it is left fully
refunded) and, with Invoicing, its corrective invoice in the same refund (R5 for a ticket, R1 for an
invoice; by differences, or what is left if it closes the sale: INVOICE-F09, F10).
If it fails: "<method>: <amount> is more than the <amount> still refundable.", "<method>: choose where
this money goes back.", "A refund needs a reason.", "There is no money left to refund on this sale.". If
another refund takes the last of a marked line at the same time: "One of the lines marked already came
back with another refund. Open the refund again to see what is left.". If the hub does not answer,
repeating with the same key does not refund twice. If "Cancel" is pressed in "An approval is needed",
nothing is refunded and the window says "This needs a manager's approval.". The approved refund is the
same, only once, with its corrective invoice and the voucher sessions that go back; who approved it stays
in **Employees › Approvals** (BASE-F85).
Involved: INVENTORY-F24, CUSTOMER-F22, INVOICE-F09, INVOICE-F10, BASE-F84
Customers takes what was refunded off the record's spending on hearing "sale refunded" (CUSTOMER-F22)
and Inventory puts back the units that go back (INVENTORY-F24), once per refund.

### SALE-F32 Give back a voucher's session
Status: done
Vertical: hair salon
Actor: manager
Screen: Refund, Void sale
Steps:
1. In **Sales**, press "Refund" on a sale with lines paid with a voucher (it also shows on one paid
   entirely with a voucher, at 0.00 €, while it has a session left to give back).
2. In "What goes back", the line paid with a voucher says "Already paid · <voucher>". Mark it: "The
   session goes back to <voucher>.".
3. Write the "Reason" and press the button: with money, "Refund <amount>"; only the session, "Give the
   session back".
4. Voiding the sale (SALE-F30) also gives back all its sessions.
In: the sale's lines paid with a voucher and what already came back of each one.
Out: the refund (announces: sale refunded) and the session back on its voucher in the same operation
(SERVICE-F26, SERVICE-F27). The sale changes to Refunded when all the money and all its sessions come
back.
If it fails: "A refund has to give back money or the session of a voucher."; a session already given
back, "One of the lines marked already came back…". If Services is not active in the business, the
refund or the void of a sale with sessions is refused ("Services is not active in this business…").
Involved: SERVICE-F26, SERVICE-F27

### SALE-F33 Merge the sales of two customer records
Status: done
Vertical: common
Actor: system
Screen: none
Steps:
1. In Customers, someone merges two records of the same person (CUSTOMER-F13).
2. The sales of the absorbed record move to the one that stays, in any state.
In: the absorbed record and the one that stays (Customers announces: records merged).
Out: the link of the sales with the record; the printed name, the number and the amounts do not change.
If it fails: there is no screen; repeating it changes nothing.
Involved: CUSTOMER-F13

### SALE-F34 Set up the POS
Status: done
Vertical: common
Actor: manager, administrator
Screen: Settings
Steps:
1. Open **Sales & POS → Settings**; "Point of sale" is read at the top.
2. Change what you need: "Allow cash", "Allow card", "Allow bank transfer", "Show products in the till",
   "Show services in the till", "Require a customer on every sale", "Allow discounts", "Largest discount
   a cashier may give alone, per discount (%)", "Allow parked tickets", "Prices include VAT", "Issue an
   invoice when the customer has a tax ID", "Default document" ("Ticket" or "Invoice"), "Receipt header",
   "Receipt footer", "Footer image (URL)", "Promotional QR URL" and "Promotional QR text".
3. Press **Save**: "Settings saved." shows.
In: nothing from other apps.
Out: the business's settings (one row). The server applies when charging "Allow cash / card / bank
transfer", "Require a customer", "Allow discounts", the maximum discount and prices including VAT; the POS
reads the rest when it opens.
If it fails: "Could not save settings.". Without permission, the fields are locked, there is no "Save"
and "You do not have permission to change these settings. Ask an administrator if you need to." shows.
If every payment method that exists is turned off, the POS and the server go back to accepting every
active method.
Involved: none

### SALE-F35 Add and order the open-price sections
Status: done
Vertical: common
Actor: manager
Screen: Sections
Steps:
1. Open **Sales & POS → Sections**.
2. Press **+**, write the Name ("e.g. Fruit and veg"), choose "VAT charged" and the Position.
3. Press "Add". To change it, tap "Edit", correct it and press "Save"; to remove it, "Delete" and confirm.
4. In **Sell**, the "Open price" tile offers these sections in that order, with their VAT alongside. With
   the list empty it offers the VAT categories as they are.
In: Taxes' VAT categories.
Out: the section (name, VAT category, position). What was already sold keeps the name and the VAT it was
charged with.
If it fails: a VAT category that does not exist is refused next to its field. A section someone else
already deleted: "That section is no longer in this business. Reload the list and try again.".
Involved: TAX-F01

### SALE-F36 Prepare the quick notes
Status: done
Vertical: common
Actor: manager
Screen: Quick notes
Steps:
1. Open **Sales & POS → Quick notes**.
2. Press **+**, write the Note (up to 80 characters, e.g. "no salt") and the Position.
3. Press "Add". To change it, "Edit"; to remove it, "Delete" and confirm.
4. In **Sell**, a line's note sheet paints these notes as buttons, in that order (SALE-F13).
In: nothing from other apps.
Out: the quick note. Deleting it stops offering it; notes already written keep their text.
If it fails: "The quick note could not be saved."; a note that no longer exists: "That quick note is no
longer in this business. Reload the list and try again.".
Involved: none

### SALE-F37 Add a payment method (Bizum, bank transfer…)
Status: done
Vertical: common
Actor: manager, assistant
Screen: none (assistant or API), like the current product
Steps:
1. Ask the assistant to add the method and say what type it is ("add Bizum as a payment method, of type
   other"): with no type it is created as cash.
2. The method appears in the charge sheet the next time **Sell** is opened.
In: the method's name and its type (cash, card, bank transfer or other).
Out: the payment method, active. Out of the box the business only has Cash and Card; "Allow bank
transfer" offers nothing while there is no method of the bank transfer type.
If it fails: a repeated name is refused: "There is already a payment method with that name.".
Involved: none

### SALE-F38 Sell a service from Services
Status: done
Vertical: hair salon
Actor: employee, manager
Screen: Sell
Steps:
1. With Services active and "Show services in the till" on, tap "Services" in the category strip (or
   search for it with the magnifier).
2. Tap the service: it goes in as a line with its price. If it is not a fixed price ("From", "Hourly",
   "Variable", "Free"), "Amount of <service>" opens with its price as a suggestion: enter the amount and
   press "Add <amount>".
3. Charge as in SALE-F01; the line carries the professional like any other (SALE-F16).
4. **The professional's price**: a fixed-price service done by a professional who has their own price in
   Services (Fresha, Phorest and Timely charge theirs) goes in at that price; without their own price, at
   the service's. The price is set when the line is added: changing the professional afterwards
   (SALE-F16) does not change it.
5. **Booked price**: an appointment's check (SALE-F26) charges each service at the price it was booked
   at, even if the catalog says another one today (`booked_price`). Sales checks it with Appointments: the
   appointment exists and whoever charges can see it, it is not cancelled, a no-show or charged, it is the
   sale's client's and it booked that service at that price (a lower one, only whoever can sell at an
   open price). Without Appointments in the business, a booked price is an open price: only for whoever
   has that permission. The booked price rules over the professional's.
In: the services on offer, their rate, their minimum and maximum and their tax category, from Services;
the professional's own price (their assignments, `service.assignment.list`); the appointment and what it
booked, from Appointments (`appointment.appointment.get`).
Out: a service line with the service, its frozen price and the service's tax category; it moves no
stock.
If it fails: a service without a tax category shows "VAT missing" and does not go in ("Cannot be sold: no
tax category. VAT needs to be set up."); an archived one, "That service is no longer offered…"; an amount
outside the service's minimum and maximum, "That amount is outside what the service allows (<minimum> –
<maximum>).". A booked price that does not match the appointment: "That is not the price the appointment
booked for this service: it is cancelled, it is another customer's, it did not book this service or it
booked it cheaper." (409 on its field). Without Services active, "Services" does not show in the strip.
Involved: SERVICE-F09, SERVICE-F03, SERVICE-F31, APPOINTMENT-F17

## What the verticals share

| Shared piece | Flows that use it |
|---|---|
| The charge: the same server price, the same VAT, the same refusals and the same charged-sale notice Inventory and Customers listen to | F01–F06, F22, F26 |
| The open check and its lines: the price is frozen when the line is added; parking, retrieving and appointment are the same check | F09–F18, F22–F24, F26 |
| The **Charge** sheet: methods, keypad, ticket or invoice, customer's details | F01–F05, F22 |
| Marking lines: it serves to charge part and to split the check | F22, F23 |
| The "Served by" chip and the line's stamp | F16, F20, F26 |
| Voiding a sale: a single notice, and each app that reacts decides its effect | F30 |
| The POS settings: the same for both businesses | F34 and every charge flow |

## Services: what goes in and what comes out

Everything can be asked for through the screens, the assistant (by voice or by text, with the person's
own session) and the API, with the same rules and the same permissions. Designed for voice: a product is
named by its id, its SKU or its name; a customer by their id, their name, their phone or their email; a
sale by its id or its number; a section or a quick note by its id or its name; a payment method by its
id, its name or its type ("cash", "card"). If a name matches several, it is refused saying which ones
(409 `*_ambiguous`).

### What it offers: queries (they read and change nothing)

| What it gives | Who can | Flows | Service |
|---|---|---|---|
| The sales, with search by number or customer, filters (status, payment, customer, professional, days, total), sorting and pages (up to 100); each one says whether it has some fiscal document pending | see sales | F28, F29 | `sale.sale.list` |
| A whole sale: header, lines, payments, VAT breakdown and what was refunded | see sales | F29 | `sale.sale.get` |
| The sale recorded with a charge attempt key | see sales | F06 | `sale.sale.by_idempotency_key` |
| The figures of a period of business days, with the tax its sales were declared with (empty if they mix taxes) | reports | F28 | `sale.sale.stats` |
| What was sold today and today's tickets | reports | F28 | `sale.sale.today` |
| What was sold on each of the last 7 days | reports | F28 | `sale.sale.last_7_days` |
| What each professional sold in a period: gross, base, tax, what was refunded of their lines and what is left (what the commission goes on) | reports | F16, F28 | `sale.sale.by_staff` |
| What a check, or some lines, would charge, without charging anything (total, base, VAT, discounts, breakdown and lines) | see sales | F01, F21, F22 | `sale.checkout.preview` |
| The open checks (or of another state), with search by title and pages | see sales | F17 | `sale.order.list` |
| A check with its uncharged lines | see sales | F17, F19 | `sale.order.get` |
| The active payment methods, with the ones the business allows today | see payment methods | F02, F03 | `sale.payment_method.list` |
| The POS settings (to edit them) | settings | F34 | `sale.settings.get` |
| The settings the POS needs to sell | see sales | F01–F05 | `sale.pos_settings.get` |
| The sections, in their order, with today's VAT | see sales | F09, F35 | `sale.department.list` |
| The quick notes, in their order | see sales | F13, F36 | `sale.quick_note.list` |
| Today's business day | see sales | F28 | `sale.business_day.get` |
| For each payment of a sale, what was refunded and what is left, and for each line what already came back | see sales | F31 | `sale.refund.options` |
| A sale's refunds, with the state and the number of their corrective invoice | see sales | F31 | `sale.refund.list` |
| The refund recorded with a key | see sales | F31 | `sale.refund.by_idempotency_key` |

The sales, the figures, the checks, the charge preview, the payment methods, the settings, the sections,
the quick notes and what is refundable can be followed live.

### What it offers: actions (they change data)

| What it does | Who can | Flows | Service |
|---|---|---|---|
| Charges a check (whole or some lines) or some loose lines, with one or several methods; spends the sessions of its lines paid with a voucher; asks Invoicing for its ticket or its invoice in the same charge; in cash, only with the cash register open | charge | F01–F06, F08, F22, F26, F27 | `sale.sale.complete` |
| The same charge, with a discount above the maximum | uncapped discount | F14 | `sale.sale.complete_over_limit` |
| Voids a charged sale with a reason (and gives back its voucher sessions); with its corrective invoice in the same void (and its ticket first, if it was pending) | void | F30, F32 | `sale.sale.void` |
| Issues now a sale's fiscal documents that are waiting ("Issue now"): its ticket or invoice and the corrective invoices of its void and its refunds | charge (and Invoicing's permission for each document) | F29 | `sale.sale.issue_documents` |
| Refunds money from a sale per payment, and the lines that go back (the ones paid with a voucher give back their session); with its corrective invoice in the same refund | refund | F31, F32 | `sale.sale.refund` |
| Opens a check, with or without lines (articles, services —at their booked price or at the professional's— or open price); that of an appointment that already has an open one returns that one (`already`) | build the check | F01, F17, F26, F38 | `sale.order.open` |
| Adds a catalog article to a check | build the check | F01, F10 | `sale.order.add_line` |
| Adds a service from Services to a check | build the check | F38 | `sale.order.add_service_line` |
| Pays a service line with one of the client's vouchers (holds the session) | build the check and spend sessions | F27 | `sale.order.apply_voucher` |
| Undoes a line's voucher (releases the session) | build the check and spend sessions | F27 | `sale.order.remove_voucher` |
| Adds an open-price line | open price | F09 | `sale.order.add_open_line` |
| Changes a line's quantity, comp or note | build the check | F01, F10, F13, F15 | `sale.order.update_line` |
| Changes whose line it is | build the check | F16 | `sale.order.set_line_staff` |
| Splits a line of N units into N lines | build the check | F27 | `sale.order.split_line` |
| Removes an unsent line | build the check | F01 | `sale.order.remove_line` |
| Voids a line already sent to the kitchen, with a reason | void | F20 | `sale.order.void_line` |
| Sends the pending lines to the kitchen | build the check | F20 | `sale.order.fire` |
| Splits a check | build the check | F23 | `sale.order.split` |
| Merges two checks | build the check | F24 | `sale.order.merge` |
| Voids an open check (an empty one, with no live lines or payments, with just building the check) | void; empty: build the check | F18 | `sale.order.void` |
| The same void of a check with something ordered or charged, the one a manager approves with their PIN | void | F18 | `sale.order.void_ordered` |
| Sets the check's discount (and its version above the maximum) | build the check / uncapped discount | F14 | `sale.order.set_discount`, `sale.order.set_discount_over_limit` |
| Sets a line's discount (and its version above the maximum) | build the check / uncapped discount | F14 | `sale.order.set_line_discount`, `sale.order.set_line_discount_over_limit` |
| Sets a check's title (parking) | build the check | F17 | `sale.order.set_label` |
| Links a check to its appointment | build the check | F26 | `sale.order.set_appointment` |
| Creates a payment method | create payment methods | F37 | `sale.payment_method.create` |
| Saves the POS settings | settings | F34 | `sale.settings.update` |
| Creates, changes and deletes sections | settings | F35 | `sale.department.create`, `.update`, `.delete` |
| Creates, changes and deletes quick notes | settings | F36 | `sale.quick_note.create`, `.update`, `.delete` |

### What it announces

| Notice | When | What it carries | Service |
|---|---|---|---|
| Sale charged | Charge | The sale, its number, check, document, amounts in cents, currency, moment, customer and their fiscal copy, who served, appointment, payments and lines (product or service, quantity, whether it is a service, whether a voucher paid it, amounts) | `sale.sale.completed` |
| Sale born from an appointment | Charge a check with an appointment | The sale, the appointment, who served and the total | `sale.sale.created_from_appointment` |
| Sale voided | Void | The sale, its number, reason, who and when, total, customer, check and document | `sale.sale.voided` |
| Sale refunded | Refund | The sale, the refund, the amount, the reason, whether it is left fully refunded, the payments and the refunded lines | `sale.sale.refunded` |
| Sales re-pointed | Merge records | The record that stays and the absorbed one | `sale.sale.reassigned` |
| Sale with its document | A document that could not be issued in the charge, the void or the refund is issued later (the charge's retry, "Issue now" or Invoicing's reaction) | The sale, the document, its number, the refund (`refund_id`) or whether it is the void's (`void`); one per document | `sale.sale.invoiced` |
| Check opened | Open or split | The check | `sale.order.opened` |
| Check changed | Any change of lines, discounts or title | The check | `sale.order.changed` |
| Order sent | Send to the kitchen | The check, its title, the channel, the round, who serves and the lines with their notes | `sale.order.fired` |
| Check closed | Charge the last of a check | The check | `sale.order.completed` |
| Check voided | Void an open check | The check | `sale.order.voided` |
| Checks merged | Merge | The absorbed one and the one that stays | `sale.order.merged` |
| Line removed | Remove or void a line | The check and the line | `sale.order.line_removed` |
| Line voided | Void a sent line | The check, the line and the reason | `sale.order.line_voided` |
| Payment method, settings, section, quick note | Creating or changing them | Which one | `sale.payment_method.created`, `sale.settings.updated`, `sale.department.*`, `sale.quick_note.*` |

### What it reacts to

| Notice | From | What it does | Service |
|---|---|---|---|
| Records merged (`customer.customer.merged`) | Customers | Moves the sales of the absorbed record to the one that stays (F33) | `sale.customer.reassign` |
| Document issued (`invoice.invoice.issued`) | Invoicing | Links by its source (`source = {type, sale_id, refund_id, void}`) a document that was left pending: a refund's corrective invoice goes back to that refund, a void's to the sale, the charge's ticket or invoice to the sale; the rest (manual invoice, F3 that replaces, corrective invoice of an invoice) belongs to Invoicing (F29) | `sale.sale.record_invoice` |

### What it needs from other apps

- **Taxes** (required): the rule and the VAT calculation of each line when charging.
- **Customers** (required): the sale's customer record and its search by name or phone; the link of the
  check with its customer is kept by Customers (`customer.order.link`).
- **Inventory** (optional): the sale catalog, the price, the unit and the tax category of each article,
  read with its own queries when the line is added.
- **Staff** (optional): the team for the "Served by" chip and the record of whoever is signed in
  (`staff.member.current`, without Staff's permission), to which the charge attributes "Me".
- **Services** (optional): its services on offer (`service.service.list_for_sale`, and
  `service.service.get` when the line is added), the client's vouchers for a service
  (`service.grant.tender_options`) and the voucher sessions: it holds, releases, spends and gives them
  back by calling its operations by name (`service.session.hold`, `.release`, `.settle`, `.return`), with
  the session of whoever sells and in the same transaction; a professional's own price
  (`service.assignment.list`).
- **Invoicing** (optional): the ticket (F2) or the invoice (F1) of each charge, the corrective invoice of
  each void (R5) and of each refund (R1/R5), issued by its operations by name
  (`invoice.invoice.create_from_sale`, `.rectify_from_void`, `.rectify_from_refund`) with the session of
  whoever charges and in the same transaction.
- **Cash register** (optional): whether cash can be charged now (`cash_register.session.current`), only
  when the charge carries cash.
- **Tables** (optional): the POS's "Choose table" (F19) talks to Tables only by the name of its
  operations, from the screen and with the session of whoever serves: `table.table.list` and
  `table.floor.status` (the tables), `table.session.by_order` (the check's table), `table.session.open`
  with the check on screen, `.restore` and `.park`. Without Tables active there is no button.
- **Appointments** (optional): a check's appointment and what it booked, to charge its booked price
  (`appointment.appointment.get`).

### Who uses it

| App | What for | Service |
|---|---|---|
| Inventory | Lowers the stock when a sale is charged, puts it back when it is voided and puts back what goes back in a refund | `sale.sale.completed`, `sale.sale.voided`, `sale.sale.refunded` |
| Customers | Adds the purchase to the record, takes it off when it is voided and takes off what was refunded | `sale.sale.completed`, `sale.sale.voided`, `sale.sale.refunded` |
| Services | Does not react to notices: Sales calls its session operations when building, charging, voiding and refunding | `service.session.*` |
| Invoicing | Sales asks it for the document in the same charge, void or refund; its reactions to the notices issue it if it could not then (INVOICE-F06) and it reads the sale, its lines and its refunds (it requires it) | `sale.sale.completed`, `sale.sale.voided`, `sale.sale.refunded` |
| Cash register | Does not react to notices: it reads the sales, voids and refunds of each shift (it requires it); Sales asks it whether the cash register is open | `Sale`, `Refund`, `sale.order.list` |
| Appointments | Marks a sale's appointment as charged and undoes it when it is voided; opens an appointment's check (`sale.order.open`) and takes it to the POS through its address | `sale.sale.created_from_appointment`, `sale.sale.voided` |
| Tables | Opens, retitles, splits and merges its tables' checks and voids the empty one of a table being closed, through Sales' operations with the session of whoever is on the floor; reads each check's state | `sale.order.open`, `.set_label`, `.split`, `.merge`, `.void` |
| Kitchen | Opens the kitchen order of each round sent and brings it up to date when the check is charged in full, voided or one of its lines is voided (KITCHEN-F05, KITCHEN-F27 to KITCHEN-F29) | `sale.order.fired`, `sale.order.completed`, `sale.order.voided`, `sale.order.line_voided` |

### Who can do what

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| See sales, checks, POS settings, sections and quick notes | yes | yes | yes | yes | `sale.view_sale` |
| Build the check (open, add, change, remove, split, merge, send to the kitchen, discount up to the maximum) | yes | yes | yes | yes | `sale.add_sale` |
| Charge | yes | yes | yes | yes | `sale.take_payment` |
| Sell at an open price | yes | yes | yes | no | `sale.sell_open_price` |
| Discounts above the maximum | yes | yes | yes | no | `sale.discount_over_limit` |
| Void sales, open checks with something ordered or charged and sent lines (an empty check is voided by whoever builds the check) | yes | yes | yes | no | `sale.void_sale` |
| Refund | yes | yes | yes | no | `sale.refund_sale` |
| See the payment methods | yes | yes | yes | yes | `sale.view_paymentmethod` |
| Create payment methods | yes | yes | yes | no | `sale.add_paymentmethod` |
| See the figures | yes | yes | yes | no | `sale.view_reports` |
| Settings, sections and quick notes | yes | yes | yes | no | `sale.manage_settings` |

The roles come from the SaaS with a prefix (`hub_owner`, `hub_admin`, `hub_manager`, `hub_employee`); the
current product's cashier is an employee.

What the employee cannot do in the POS they ask for on their own device and a manager approves it with
their PIN or their badge ("An approval is needed", BASE-F84), once and for that very request: voiding and
refunding a sale, voiding a line sent to the kitchen, deleting a check with something ordered, selling at
an open price and discounts above the maximum. The approved action does everything the manager's does
(also what Invoicing and Services move: the corrective invoice and the voucher sessions that go back) and
stays in **Employees › Approvals** (BASE-F85). Seeing the figures, the settings and creating payment
methods are not approved.

What touches a voucher's session also asks for Services' permission, because it is Services that moves
it with the session of whoever sells: paying a line with a voucher, undoing it, removing, voiding or
charging a line paid with a voucher, "Spend sessions" (`service.redeem_package`, all four roles have it);
voiding or refunding a sale with sessions, "Give voucher sessions back" (`service.return_session`: owner,
administrator and manager, the same who void and refund).
