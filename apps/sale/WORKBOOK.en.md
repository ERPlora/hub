## What it is for and who it is for
<!-- from WORKBOOK.md sha256:0f9b6fb598e5 -->

Sales is the business's cash register: you tap the articles or the services to build the check and
charge it in cash, by card or across several payment methods. In a restaurant, the check stays open
while the table eats. Each charge becomes a sale with its ticket or its invoice, which you can later
look up, reprint or refund.

### In detail
<!-- from WORKBOOK.md sha256:2e04a75bda08 -->

Sales & POS is the business's **cash register**: the check is built by tapping articles, it is charged
in cash, by card or split across several payment methods, and what remains is a **sale that can no longer
change**, with its number of the day, its VAT line by line and its ticket or its invoice. It serves both
businesses:

- In the **restaurant**, the check stays open while the table eats: rounds are added to it, it is sent to
  the kitchen, the bill is printed for the table, it is charged whole or in parts, it is split or merged.
- In the **hair salon**, each service on the ticket carries the professional who did it and the check is
  charged at the end, with the client set.

### Who uses it and what each one does
<!-- from WORKBOOK.md sha256:d7e3107eae0d -->

- The **employee** (waiter, receptionist, cashier): builds the check, adds notes, comps a line, applies
  discounts up to the business's maximum, parks and retrieves checks, charges and looks up their sales
  and their figures: the ones they charged and the ones attributed to them.
- The **manager**: also sells at an open price, applies discounts above the maximum, voids an open check
  or a line already sent to the kitchen, voids and refunds sales, sees everyone's sales and the whole
  business's figures and prepares the quick
  notes, the sections, the payment methods and the POS settings.
- The **owner** and the **administrator**: everything.

### What it does not do
<!-- from WORKBOOK.md sha256:4327edd821ac -->

Sales does not keep tables or customers in the check (they belong to Tables and Customers), does not
number invoices or talk to the AEAT (it asks Invoicing for them in the same charge; the AEAT belongs to
VeriFactu), does not move stock (Inventory lowers it with each sale) and does not balance the
cash register (Cash register reads the sales; Sales only asks it whether the cash register is open before
charging in cash).

## Reference adopted
<!-- from WORKBOOK.md sha256:c51fc38b9fae -->

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
<!-- from WORKBOOK.md sha256:e3b3fa5865e4 -->

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
<!-- from WORKBOOK.md sha256:f48f162180be -->

Sales & POS opens from the **Sales & POS** menu and has five entries: **Sell**, **Sales**,
**Quick notes**, **Sections** and **Settings**; the last three, only for whoever can change the Sales
settings. "Sections" are the till's departments: the short
word fits in a phone's tab bar with all five in sight.

### Sell
<!-- from WORKBOOK.md sha256:6f0590348f30 -->
This is the till: here you build the customer's check and take the payment. Tap the articles or the
services in the catalogue to add them to the check, change the quantity or give them a note or a discount
if needed, and press **Charge** to choose how they pay. If the customer is not leaving yet, park the
check and pick it up later from **Open checks**; in a restaurant, this is also where you take the check
to a table and send the order to the kitchen.

#### Details
<!-- from WORKBOOK.md sha256:fe52c4bb26a2 -->
It opens in the application's full screen; the ⋮ menu of the category strip has "Full screen" /
"Exit full screen" (the browser's, when the device allows it) and it closes by tapping outside, with Esc
or with the phone's back button. Two areas:

- **Catalog**: the strip of Inventory categories with their number of articles, sold-out ones included
  ("All" first and, with Services, "Services" after it; the rest, in the position the business gave them
  and, at equal position, by name: INVENTORY-F08), the magnifier that opens the search ("Search
  product…", by name or SKU; with Services it also searches its services), the microphone key ("Speak") and the grid:
  articles with their initials, their unit and their price (what is sold out, greyed with "Sold out"),
  and at the end the "Open price" tile. In "Services", each service with its initials, its duration and
  its price ("From", "Hourly", "Variable" or "Free" if it is not a fixed price). With many articles,
  "Load more", at the end of the grid, brings the next ones.
- **Check** (on a phone, a drawer opened by the floating button with the total): at the top, the pause
  button "Park this check", the customer one ("Assign customer" or their name), "Open checks" with their
  number, and "Close" on a phone; the editable title ("New check") and the chips for the customer,
  "Served by …" and "Customer required". Each line: name, unit price, discount mark or "Comp", note and
  professional underneath; buttons for discount, note, comp and the quantity selector (a line sent to the
  kitchen only shows its quantity, "Order N", the gift and the ⊗ button "Void this item"; one paid with a
  voucher, "Already paid · <voucher>", 0.00 € and only the button to remove it). Footer: the "Ticket
  discount" row if there is one, "Total", the discount button, the printer ("Print bill"), all of them icon only, and
  "Charge": the money icon with the amount, called "Charge · <amount>". In the phone's drawer, the top bar and the footer with "Charge" always stay in view, above
  the tab bar, and what is in between (title, chips, tabs and lines) scrolls. The customer button's name
  takes two lines at most (a longer one ends in "…"); on a very narrow phone, the button keeps only its
  icon and the customer chip in the heading already names them.

**Speak** (the strip's microphone key; only for whoever may use the assistant and on a device that can
record; only the icon, called "Speak"): press it and speak. While it records it turns red, changes to the stop
icon, is called "Stop" and "Listening…" shows
underneath; press it again to finish (it stops by itself after two minutes). After "Transcribing…",
what was understood lands in the assistant's box, after whatever had been written, and its panel opens:
the person reads what was understood, corrects it if needed and sends it themselves. **Nothing is sent
by itself**, and whatever it asks for goes through the confirmation card like any other request to the
assistant. Offline the key shows switched off and, when pressed, says "No
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

#### Charge
<!-- from WORKBOOK.md sha256:350843592364 -->
Sheet opened by "Charge". At the top, the big amount, "Paying N lines of <total>" if there are marked
lines and "Remaining" when splitting. On one side, the summary ("Receipt" / "Invoice", customer), with
"Invoice" the customer's details and, with Services, "Lines paid another way": each service line of the
charge with its slot to pay it with a voucher. On the other, "Payments taken", the payment methods (cash,
in a business in Spain not available from €1,000, with its reason) and, in cash, "Tendered", a row with
what the amount lacks ("Enter the amount tendered on the keypad", "The amount tendered does not cover the
total") or, in its place, the large "Change", and the keypad; with another method, "Exact amount" and
"Charge <amount> on the card terminal, then confirm."; "Split the payment" and "Add this payment".
Footer: the reason if it cannot be charged (those of the amount tendered go above the keypad) and
"Charge <amount>" ("Charging…" while it goes); with the cash register closed and cash, the refusal and
"Open a cash session".

#### Open checks
<!-- from WORKBOOK.md sha256:c8b86b18ea91 -->
Drop-down of the check's ticket icon: "Park this check" with its explanation, "Open checks" and "Tap a
check to resume it.", and a row per open check of the business (title or amount, time and amount) with
its bin. Empty: "No open checks". A failure is painted above the rows. It closes by tapping outside, with
Esc or with the phone's back button.

#### Bill (pre-bill)
<!-- from WORKBOOK.md sha256:a4ed89147faf -->
"Bill" window opened by the footer's printer ("Print bill"): the paper taken to the table, with the notice "Bill — this
is not an invoice. The fiscal receipt is issued on payment.", and the print and close buttons.

### Sales
<!-- from WORKBOOK.md sha256:7e1e8640d127 -->
Here are the sales already charged, with the figures for today or for the period you choose. Look a sale
up by its number or by the customer to see its ticket, reprint it, void it or refund it. If you are not
allowed to void or refund, a manager approves it for you with their PIN. An employee sees only their own
sales, the ones they charged and the ones attributed to them; the manager, the owner and the
administrator see everyone's.

#### Details
<!-- from WORKBOOK.md sha256:b4d330fa54ef -->
Title "Sales", period ("Today", "7 days", "30 days", "All"), six figures ("Tickets", "Revenue", "Avg.
ticket", "VAT", "Discounts", "Voided") and the table (Date, Number, Customer, Payment, Status, Total) with
the search "Search number or customer…", filters, table or card view, 50 per page. Per row: "Document",
"Reprint", "Void" and "Refund", each where it applies; whoever lacks the permission to void or to refund
also sees them, and a manager approves it for them with their PIN. Empty: "No sales yet."; loading:
"Loading…"; error: the notice with "Retry".

#### Sale document
<!-- from WORKBOOK.md sha256:c864478bf40c -->
Window with a sale's ticket, which opens on tapping its row or "Document" and, by itself, on charging in
**Sell**: the paper as it prints (title "Receipt" or "Invoice", the business with its tax ID, the number
Invoicing gave it —"Invoice FACT-2026-000012", "Receipt TICKET-2026-000031"— or, without it, the sale's,
date, lines, one VAT row per tax key, total, payment method, tendered and change, footer), the ✕ and the
printer. Every print from **Sales** comes out with "DUPLICATE". Error: "Error loading the document".

#### Refund
<!-- from WORKBOOK.md sha256:f750d9288b7c -->
Window "Refund sale <number>", opened by "Refund": explanation, one card per payment method ("Charged", "Already refunded",
"Refundable", "Refund amount" and, if needed, "Give it back through"), "Refund everything", "What goes
back" (the sale's lines with a checkbox each and, on a line of several units, "Units that go back"; the
one paid with a voucher says "Already paid · <voucher>" and, once marked, "The session goes back to
<voucher>."), "Reason" and "Refund <amount>". Loading: "Loading what can be refunded…"; nothing to
refund: "There is nothing left to refund on this sale.".

#### Void sale
<!-- from WORKBOOK.md sha256:26ecc0973f24 -->
Window "Void sale <number>", opened by "Void": the explanation, the "Reason (required)" and "Void" /
"Cancel". A refusal is read inside the window, which stays open. Without the permission to void, "Void"
opens "An approval is needed" on top, where a manager approves it with their PIN.

### Quick notes
<!-- from WORKBOOK.md sha256:167dc93b52ca -->
Here you set up the notes that come up most often on the lines of a check, such as "no salt". Then, when
you put a note on a line in **Sell**, they show as buttons and you just tap them instead of typing them.

#### Details
<!-- from WORKBOOK.md sha256:7706c765ef37 -->
Explanation, table (Note, Position) with search, **+** to add and, per row, "Edit" and "Delete". Empty:
"No quick notes yet…"; loading: "Loading quick notes…". Whoever lacks the settings permission does not
open it: by its address, "No access" (BASE-F118).

### Sections
<!-- from WORKBOOK.md sha256:a6504a3624b5 -->
Sections are the till's departments for charging something that is not in the catalogue, at an open
price, such as fruit and vegetables. Here you create them, each with the VAT it charges and in the order
they show. When you tap **Open price** in **Sell**, you pick the section and type the amount.

#### Details
<!-- from WORKBOOK.md sha256:e477660c85ac -->
Explanation, table (Name, VAT charged, Position), **+** and, per row, "Edit" and "Delete". Empty: "No
sections yet…"; loading: "Loading sections…". Whoever lacks the settings permission does not open
it: by its address, "No access" (BASE-F118).

### Settings
<!-- from WORKBOOK.md sha256:5308120b74d9 -->
Here you decide how the till charges: which payment methods it takes, whether every sale needs a
customer, whether discounts are allowed and whether it gives a ticket or an invoice by default. You also
write what goes at the top and the bottom of the receipt. Press **Save** for the changes to take effect.

#### Details
<!-- from WORKBOOK.md sha256:614997f0148b -->
Header "Point of sale": a switch or field per setting and "Save". Loading: "Loading
settings…"; error: "Could not load settings." with "Retry"; without permission,
by its address, "No access" (BASE-F118).

## States of each screen
<!-- from WORKBOOK.md sha256:2fa9a3c5cc56 -->

| State | What the person sees |
|---|---|
| Loading | "Loading…" (or its screen's text) while the first result arrives. |
| Empty | Its screen's text, with **+** if they can create. |
| Error | The notice with "Retry"; an action's refusal shows inside its sheet or window, next to its field. |
| Reconnecting | What is painted stays; a band warns "Reconnecting…" until the connection is back. |
| App inactive (`app_inactive`) | "This app is not active in this business". |
| Speaking (Sell) | The microphone key, red, changes to the stop icon and is called "Stop"; "Listening…" shows underneath; on stopping, "Transcribing…". A notice says what fails: no voice, "Nothing was heard. Try again closer to the microphone."; with the microphone denied, "Microphone access is blocked. Allow it in your browser to speak." (in the installed app, which has no browser, "Microphone access is blocked. Allow it in your device settings to speak."); too long, "The recording is too long: say something shorter."; if it cannot be transcribed, "The audio could not be transcribed. Try again."; offline, "No connection: talking to the assistant needs the internet.". |
| No permission | What they cannot do does not show; if it arrives through another door, "You do not have permission". What a manager can approve with their PIN (voiding and refunding a sale, voiding a sent line, deleting a check with something ordered, the open price and discounts above the maximum) does show and, when pressed, asks "An approval is needed". |

## Unsaved changes on Android
<!-- from WORKBOOK.md sha256:8bbcfe6718c8 -->

In this app's create and edit windows, the phone's Back button asks "Discard changes?" when something typed
or chosen has not been saved: "Keep editing" keeps it and "Discard changes" closes the window without saving.
With the window as it opened, Back closes it without asking (BASE-F05).

## Flows
<!-- from WORKBOOK.md sha256:f68cc86f0cbe -->

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
| SALE-F39 | Charge with what another app adds (the tip) | common | partial — what is added to each payment when splitting and on the Sale document are missing |
| SALE-F40 | See a dish's allergens when ordering it | common | done |
| SALE-F41 | Mark the customer's allergy on a line | restaurant | done |
| SALE-F42 | Choose the modifiers of a dish in a menu | restaurant | done |

### SALE-F01 Sell and charge in cash
<!-- from WORKBOOK.md sha256:4e7ab596ec4b -->
Status: done
Vertical: common
Actor: employee, manager
Screen: Sell, Charge
Steps:
1. In **Sell**, choose a category in the top strip ("All" shows everything) or press the magnifier and
   search by name or SKU.
2. Tap the article: it goes in as a line of the check. Tapping it again (same professional, no note or
   discount) raises the quantity; the line's selector raises or lowers it, and at 0 the line goes.
3. Press "Charge" at the foot of the check, the money icon with "€18.50" (on a phone, first open the check with the floating
   button, which shows the total). On a phone on its side, the check takes the whole screen: its bar and
   its foot stay put, with "Charge" in view, and the lines scroll between them.
4. In the **Charge** sheet, with cash chosen, enter the amount tendered on the keypad; the change shows
   large above the keypad, in the row that until then asks for the amount. On a low phone, the whole
   keypad is in view as soon as the sheet opens.
5. Press "Charge €18.50".
6. The sheet closes, the check is left empty and the **Sale document** opens with the ticket. With
   **Printing**, the ticket comes out by itself on the ticket printer, according to its settings (and, if
   cash came in, the drawer opens): "Sent to Bar." is read and the paper on screen is already a
   copy. Without Printing turned on, without a ticket printer or with the fiscal document pending, the
   ticket is printed from the Sale document. A printer failure never undoes the charge.
In: Inventory's articles and prices; Taxes' VAT rates; the POS settings; the check's customer, from
Customers: a check charged without naming the customer (through the assistant or the API) goes to the
customer the check has (CUSTOMER-F19), as at the till when it is picked up again.
Out: the charged, immutable sale, with number `YYYYMMDD-NNNN` of the business day, its lines, its payment
and its VAT breakdown (one row per tax key, closed only once: the same as the invoice declares), and the
check closed. With Invoicing, its ticket (F2) numbered in the year's series in the same charge
(INVOICE-F01): both or neither. Sales announces the charged sale: Inventory lowers the stock
(INVENTORY-F21) and Customers adds the purchase to the record (CUSTOMER-F20). Each line keeps the
category, rate, country, region and Taxes rule it was charged with.
If it fails: while the business has not yet said its currency, **Sell** shows no figures: the total, the lines,
the tiles, the search, the open checks and the floating button say "—", as does the amount of the foot's "Charge"; the **Charge**
sheet stays on "Working out the total…", with no keypad and "Charge" grey. As soon as the business says its
currency, the figures show; if it cannot be read, the sheet says so with "Retry". If the check cannot be valued
(for example, because a VAT rule is missing), the foot says why instead of "—": it names the article and its tax
category and ends with "Create its rule in Taxes › Rules."; the **Charge** sheet says the same. As soon as it can
be valued, the notice clears and the total returns. With no amount tendered, the button does not charge and
"Enter the amount tendered on the keypad" is read above the keypad; if it falls short, "The amount tendered does
not cover the total" (on the button too, which says it when tapped). An article without VAT shows marked "VAT
missing" and, when tapped, says "Cannot be sold: no tax category. VAT needs to be set up."; a sold-out one shows
greyed with "Sold out" and, when tapped, says "«…» is sold out.". A refusal when charging is read in the sheet
with its sentence (e.g. "A product of the ticket is no longer in the catalog. Remove the line and add it
again.") and the check stays intact. If another device changes the check while you charge, nothing is charged
and the sheet says "The check changed while it was being charged…": review the lines and press "Charge" again,
which charges what is there.
Involved: INVENTORY-F21, CUSTOMER-F19, CUSTOMER-F20, TAX-F18

### SALE-F02 Charge by card or another method with no change
<!-- from WORKBOOK.md sha256:90113c8b1041 -->
Status: done
Vertical: common
Actor: employee, manager
Screen: Charge
Steps:
1. With the check ready, press "Charge" (the money icon with "€18.50").
2. In the **Charge** sheet, tap **Card** (or whatever the method is; the active methods the settings
   allow are shown).
3. "Exact amount" and "Charge €18.50 on the card terminal, then confirm." are read: charge on the
   card terminal separately.
4. Press "Charge €18.50 by card". The result is the same as charging in cash: the check is left
   empty and the ticket opens.
In: the business's payment methods.
Out: the sale with one payment for the exact amount and no change; the charged-sale notice carries
each method's type, so that Cash register does not add it to the cash.
If it fails: the POS does not talk to the card terminal: if the card is declined, close the sheet
without confirming. A method the business does not allow or that is no longer active is refused: "That
payment method is not available in this business.".
Involved: none

### SALE-F03 Split the payment across several payment methods
<!-- from WORKBOOK.md sha256:e00404c181a7 -->
Status: done
Vertical: common
Actor: employee, manager
Screen: Charge
Steps:
1. In the **Charge** sheet, press "Split the payment". "Remaining" appears at the top.
2. Choose a method: the "Amount for this payment" (in cash, "Tendered") already shows all that is left.
   To charge only part of it, or if more cash is handed over, type another amount, which replaces the one
   shown. Press "Add this payment".
3. The payments taken show in "Payments taken"; the ✕ removes one.
4. When the remainder reaches 0, press "Charge €18.50".
In: the payment methods and what the customer hands over.
Out: one sale with one row per method; the change always comes out of the cash and is never split.
If it fails: while money is missing, the button says "€5.00 still to cover"; if the payments do not
add up to the total, nothing is charged: "The payments do not add up to the total of the sale.". In a
business in Spain, a sale of €1,000 or more admits **no** cash payment, not even split: cash shows
disabled with its reason ("The law does not allow cash for sales of €1,000.00 or more. Charge it by card
or Bizum."). Charging the check in parts does not get round it: it counts the whole check (what has
already been charged of it and all that is left), because the law adds up the payments a sale is split
into: on a check of €1,000 or more no partial payment can carry cash.
Involved: none

### SALE-F04 Choose ticket or invoice and the customer's details
<!-- from WORKBOOK.md sha256:da588f275c55 -->
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
If it fails: without the three details the button says "Enter the customer's details", and an invoice
without them is not charged: "An invoice needs the customer's name, tax ID and address. Fill them in or
charge it as a ticket.". A Spanish NIF, NIE or CIF that does not add up shows under its box ("That tax
ID is not valid.") and the button says "Check the tax ID"; outside Spain, with no document type, "Say
what kind of document a foreign tax ID is…". A ticket above the limit is not charged: "Above €3,000.00
this sale cannot be a ticket: charge it as an invoice with the customer's details.". The country goes
with its two-letter code ("GB", not "UK"); another is refused with "Enter the country's ISO code, e.g.
ES, FR or GB.", also the one an old record brings. If Invoicing refuses the customer's details, nothing
is charged: they are corrected and the sale is charged again.
Involved: CUSTOMER-F17, INVOICE-F02

### SALE-F05 Charge when the business requires a customer
<!-- from WORKBOOK.md sha256:dfa7590efca7 -->
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
If it fails: without a customer nothing is charged, not from the assistant either: "This business
requires a customer on every sale.".
Involved: CUSTOMER-F17, CUSTOMER-F18

### SALE-F06 Recover a charge left without an answer
<!-- from WORKBOOK.md sha256:27338cb1d165 -->
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
<!-- from WORKBOOK.md sha256:39c6e14950bc -->
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
   printed and charged just the same. As soon as it is back on sale, it can be ordered again, and the
   sold-out notice goes away on its own, without touching anything else (the same for "no tax
   category" as soon as the article has one). On leaving **Sell**, the notice of the last tap goes too.
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
<!-- from WORKBOOK.md sha256:f089ed9cb87b -->
Status: done
Vertical: common
Actor: employee, manager
Screen: Charge
Steps:
1. With "Turn on the cash register" on in Cash register and no open cash session, charge in cash (also
   a split payment with a part in cash).
2. The **Charge** sheet charges nothing and says "The cash register is closed: open a cash session to
   charge in cash."; to whoever can open it, it offers "Open a cash session", which opens **Cash
   register**'s opening window over the charge, with "Drawer", "Opening float" and "Notes".
   The **Sell** screen does not change: the check is still there.
3. Tap "Open session": the window closes, "Session opened" shows and the charge goes on as it was, now
   without the notice; "Charge" charges in cash. By card, Bizum or bank transfer it always charges, with
   the cash register open or closed.
In: whether the cash register is turned on and whether there is an open session, which Sales asks Cash
register (`cash_register.session.current`) with the session of whoever charges, only when there is cash.
Out: nothing of its own; the refused charge does not use up a number.
If it fails: if Cash register is not active in the business or does not answer, the sale is charged just
the same, so as not to stop the sales, and Cash register shows that charge among the ones in no shift. The
opening window gives the same notices as in Cash register: a required float, a session already open on
another device, an unreadable amount; "Cancel" closes it and the charge keeps its notice.
If the window cannot load, "Open a cash session" takes you to **Cash register** to open it there, and the
check stays in **Sell**.
Involved: CASH_REGISTER-F03, CASH_REGISTER-F04, CASH_REGISTER-F17

### SALE-F09 Sell at an open price by section
<!-- from WORKBOOK.md sha256:d43469de6be8 -->
Status: done
Vertical: common
Actor: manager (employee with the open-price permission); cashier, with a manager's approval
Screen: Sell, An approval is needed
Steps:
1. Tap the "Open price" tile, at the end of the grid.
2. Enter the amount on the keypad and choose the section in "Section (VAT)"; each button shows its VAT
   rate.
3. Press "Add €12.50": a line goes in with the section's name and that amount. It is never added to
   another line.
4. If you do not have the open-price permission, pressing "Add €12.50" opens "An approval is needed" on
   top with what is being approved and the amount entered ("Approving: Sell at an open price of
   €12.50"): a manager approves it with their PIN (or their badge) on that same device and the line goes
   in. If there was no check yet, it opens empty and the line waits for the approval.
In: the business's sections (SALE-F35) or, if there are none, Taxes' VAT categories.
Out: a line with no catalog article, with its amount and its VAT category, which is charged like any
other.
If it fails: "Add" cannot be pressed without an amount and a section, nor while the business has not yet
said its currency (what was typed stays and is read as soon as it arrives). If the currency cannot be read,
the sheet says so ("The business's currency could not be read", with the reason) and offers "Retry"; as soon
as it arrives, "Add" lights up. With no sections or categories, "There are no tax categories to choose from.
Set up your VAT first, in Taxes.". If "Cancel" is pressed in "An approval is needed", the line does not go in
and the sheet says "This needs a manager's approval.".
Involved: TAX-F18, BASE-F84

### SALE-F10 Sell by weight, typing the quantity
<!-- from WORKBOOK.md sha256:326c66dabc25 -->
Status: done
Vertical: common
Actor: employee, manager
Screen: Sell
Steps:
1. Tap an article whose unit is of mass, volume or time (kg, g, l, h…): it goes in as a line with its
   unit.
2. Type the quantity in the line's selector (e.g. 0.532).
3. The amount is worked out again and the line shows the unit ("0.532 kg").
In: the article's unit, its step and the quantity its price refers to, from Inventory.
Out: the line with its quantity and its unit frozen.
If it fails: a quantity that does not fit the unit's step is refused with "The quantity does not fit
the step of the product (…)." and the line stays as it was. There is no scale reader.
Involved: INVENTORY-F26

### SALE-F11 Choose an article's modifiers
<!-- from WORKBOOK.md sha256:059162f5c4fa -->
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
4. Press "Add · €9.50": the line goes in with its modifiers under the name and its price already added
   up. While a required group is not complete, the button says "Choose an option to continue" and tapping
   it points to that group.
5. Charge as always: the line charges what it was worth when ordered even if the modifier
   changes or is deleted later. A modifier with another VAT rate (the soft drink of the kids' menu, at
   21 % next to the burger at 10 %) shows on the ticket as its own line under the dish ("+ Soft drink"),
   for each dish.
In: Modifiers' groups and options, which checks and prices what was chosen when the line is added.
Out: the line with its modifiers frozen (announces: check changed); the kitchen order carries them under
the dish ("+CHEESE, -ONION", announces: order sent); when charged, the ticket names them under the dish
and each modifier with another VAT is a line of its own with its base and its tax amount; only the dish
lowers the stock.
If it fails: Modifiers' reasons show inside the sheet ("Choose at least 1 in «Doneness».", "This option is
not offered with this product."…), and a required group left unchosen does not go in when ordered through
the assistant either. If the groups cannot be read, "The options of this product could not be read. Try
again." and nothing goes in.
Involved: MODIFIER-F06, MODIFIER-F07, MODIFIER-F08

### SALE-F12 Put together a menu
<!-- from WORKBOOK.md sha256:e1016f7429f5 -->
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
   course; when each required course is complete, it says "Add · €14.00" with the set price plus the
   extra charges. Press it: the menu goes into the check as one line, with its courses under the name.
   Each menu is a line of its own; its quantity changes by whole units.
5. Charge as always: the menu charges the amount it had when ordered even if its price goes
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
If it fails: Menus' reasons show inside the sheet ("The menu still needs a pick in “Mains”: pick 1.", "“Flan”
is sold out."…). A half-made menu does not go into the check, not through the assistant either, so it never
reaches the kitchen without its dishes. A quantity with decimals: "The quantity does not fit the step of the
product (1 ud).". If the menus cannot be read, above the grid "The menus could not be read. Try again." with
"Retry", and the products sell just the same. Without Menus and combos active, the POS offers no menus.
Involved: COMBO-F07, COMBO-F08, COMBO-F09, COMBO-F10, COMBO-F11, INVENTORY-F22, SALE-F42

### SALE-F13 Put a note on a line
<!-- from WORKBOOK.md sha256:169ff0f5ddb3 -->
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
<!-- from WORKBOOK.md sha256:d71ed1a11dec -->
Status: done
Vertical: common
Actor: employee, manager; above the maximum, the cashier with a manager's approval
Screen: Sell, An approval is needed
Steps:
1. For a line, tap its price tag ("Line discount"); for the whole check, the tag button in the footer
   ("Ticket discount").
2. Enter the percentage; on the check you can switch to a fixed amount with the button of the business's
   currency ("€", "zł"…).
3. Press "Apply −N %" (or "Apply −€2.00"). "Remove" deletes it. The line shows "−N %" and the footer
   the row "Ticket discount −N %" with what the check's discount takes off, be it a percentage or a fixed
   amount: 10 % on €8.50 says "−€0.85", never "−€0.00". The check's discount is worked out on the lines
   already with their own discount.
4. If the discount goes over the maximum the business lets you give without authorization, a manager
   gives it: whoever cannot give it sees "An approval is needed" on top with what is being approved and
   the figure of that very discount ("Approving: Discount a line by 15%", "Approving: Discount the check
   by 15%" or, with a fixed amount, "Approving: Discount the check by €5.00"), and a manager approves it
   with their PIN (or their badge) on that same device. The check keeps who authorized it and it is not
   asked again when charging; if, when charging, the discount goes over the maximum without
   authorization, it asks just the same, with "Approving: Charge with a discount above the maximum".
   Employees › Approvals keeps what was approved with its figure, and also what is given by whoever may give
   it by themselves.
In: "Allow discounts" and the maximum discount of the settings. The assistant only sets one on a check it is
told about (its table or its name): the discount a product or a category gets on every sale is a rule of Price
Lists (PRICING-F11).
Out: the discount on the check or on the line; when charging it is shared out among the lines, the
declared base and VAT already carry it discounted, and the sale keeps the discounted amount.
If it fails: with "Allow discounts" off there are no discount buttons, and the assistant cannot set one
either: "This business does not allow discounts.". A fixed amount cannot be applied while the business has
not yet said its currency; a percentage does not wait for it. With a fixed amount, if the currency cannot be
read, the sheet says so ("The business's currency could not be read", with the reason) and offers "Retry";
as soon as it arrives, "Apply" lights up. Above the maximum, if "Cancel" is pressed in "An approval is
needed", the check stays as it was and "This needs a manager's approval." is read. An amount greater than
the check cannot be applied. If another device is charging that check, whoever gets there first wins, as in
any charge.
Involved: BASE-F84, BASE-F85

### SALE-F15 Comp a line
<!-- from WORKBOOK.md sha256:76404231c9d1 -->
Status: done
Vertical: common
Actor: employee, manager
Screen: Sell
Steps:
1. On the line, tap the gift ("Comp / un-comp line"). Also on a line already sent to the kitchen,
   because what is comped is usually what was already served: the dessert on the house or the dish
   that came out wrong.
2. The line goes to 0 with the "Comp" mark; tapping it again charges it again. A sent line stays on the
   check with its order, and the kitchen gets nothing new.
In: nothing from other apps.
Out: the comped line: it adds no money or VAT, but the sale notice carries it so that Inventory lowers
the stock; the sale keeps the cost of what was comped, which only whoever sees the costs sees: to anyone
else the sale, its charge and the preview of the charge give it empty (BASE-F119).
If it fails: "That change to the line could not be saved. The line is back as it was.".
Involved: INVENTORY-F21, BASE-F119

### SALE-F16 Attribute the check or a line to whoever serves
<!-- from WORKBOOK.md sha256:ca9d61689e0a -->
Status: done
Vertical: common
Actor: employee, manager, assistant
Screen: Sell; assistant
Steps:
1. In the check's header, the "Served by me" chip says who it is attributed to. Who serves is part of the
   check and the Hub keeps it: when you leave the check and come back to it (from the floor plan, from
   "Open checks" or on another device), the chip still says that person. Tap it.
2. In "Who is serving this check", choose the person from the Staff team or "Me (whoever is signed in)".
   If your account has no record in Staff, the sheet warns about it: "Your account has no record in
   Staff: left on «Me», this sale counts for nobody." With the check open it is saved on it at once;
   with no check yet, the check is opened with that person when the first item goes in, and the one
   Tables opens when a table is picked for it is theirs too.
3. The lines added from then on are stamped with that person. To correct a line already in, tap the
   name shown under it ("Whose line is this") and choose another person or "The check's professional".
   A line that arrives with its professional (an appointment's, one of a check built on another device or
   before a reload) also shows their name, the one Staff gives.
4. Charge. With the chip on "Me", the sale is attributed to your Staff record; a line with its own
   professional (an appointment's, the one you moved) keeps them. Afterwards, the chip goes back to "me".
5. With the assistant: "Lucía is serving table 6's check". It stays saved on the check until it is charged,
   also on the new check if it is split: the kitchen order sent carries their name and the sale
   is theirs, whoever charges it; the lines already in keep whoever they had.
In: the Staff team (active records), the record of whoever is signed in and the name of each line's
person.
Out: the sale and each line attributed to that person, for the close by professional and Staff's
commissions (STAFF-F21). With "Me", the sale belongs to the record of whoever charges; without a record,
it counts for nobody. The kitchen order sent carries their name (KITCHEN-F18); with "Me", that of whoever
sends it or, if their account has no name, what goes before the @ of their e-mail, never the whole e-mail
(BASE-F119). In Tables, the table's window and the floor plan say that person serves it (TABLE-F09).
If it fails: "The team could not be loaded. The sale is still attributed to whoever is signed in.";
"Who serves the check could not be changed. It stays with whoever served it.";
"The line could not be moved to another professional. It stays with the one it had.". A line sent to
the kitchen is not reassigned. If Staff cannot say whose a line is (off, no permission or a record that
is gone), the line says "the assigned professional". With the assistant, someone not on the team: "That
staff member does not exist in this business."; without Staff active: "Staff is not active in this
business.".
Involved: STAFF-F21, KITCHEN-F18, TABLE-F09

### SALE-F17 Park a check and retrieve it
<!-- from WORKBOOK.md sha256:abb956f749c2 -->
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
Involved: CUSTOMER-F19, TABLE-F33

### SALE-F18 Delete an open check
<!-- from WORKBOOK.md sha256:0ec519758a80 -->
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
   approves it with their PIN (or their badge) on that same device and the check is deleted.
In: the chosen check.
Out: the check is left voided, not deleted (announces: check voided); what was already charged of it
stays in its sales.
If it fails: "That open check could not be deleted. It is still in the list.". A check already charged
cannot be voided: "That check is no longer open.". Whoever builds checks sees the bin on all of them: an
**empty check** (no lines or payments) they delete themselves, because a group that leaves without
ordering should not force calling a manager; with something ordered or charged it takes the permission to
void or a manager's approval. If "Cancel" is pressed in "An approval is needed", the check stays in
the list and "This needs a manager's approval." is read on top.
Involved: TABLE-F20, TABLE-F21, BASE-F84

### SALE-F19 Open a table's check and leave it on the table
<!-- from WORKBOOK.md sha256:a6d82c6f1f1a -->
Status: done (without asking for the number of guests in the POS: see "What stays out")
Vertical: restaurant
Actor: employee, manager
Screen: Sell
Steps:
1. With Tables active and the permission to seat, the check's bar has, before the customer, the table
   button (grid, "Assign table"). Tap it: "Choose table" opens, with a search ("Search a table…") and
   the tables in service as tiles that draw each table as the floor plan does, with its shape, its
   chairs and the floor plan's colours (Available green, Occupied blue, Reserved yellow, Blocked grey),
   with the number, the area, the seats ("4 pax"), the state and, if it has one, today's reservation
   ("Marta · 21:00"). With no tables: "There are no tables yet. Set them
   up in Tables → Floor plan.".
2. Tap an Available or Reserved table: the check on screen sits there and takes its name as its title
   ("Table 4"); with no check yet, Tables opens one with that title and the POS puts it on screen. A
   check whose table was taken off sits again the same way. The Occupied and Blocked ones cannot be
   tapped (their title says why).
3. The check's header shows its table ("Table 4") and the button is painted in colour.
4. "Remove from table", in the same window, releases the table without charging: the table is left free
   and the check stays open in **Open checks**.
In: the tables, their state and the check's table, from Tables (`table.table.list`,
`table.floor.status`, `table.session.by_order`), followed live.
Out: nothing of its own; Tables seats (`table.session.open` with the check, `.restore`) or releases
(`table.session.park`) with the session of whoever serves, and retitles the check (`sale.order.set_label`).
If it fails: Tables' refusal inside the window, in its words ("Another device has just taken that
table…", "That check is already at table N."…). Without Tables active, or without the permission to see
its tables and seat, there is no button and Tables is not asked anything.
Involved: TABLE-F10, TABLE-F12, TABLE-F13, TABLE-F24, TABLE-F33

### SALE-F20 Send the order to the kitchen and void a sent line
<!-- from WORKBOOK.md sha256:1a2608507bd3 -->
Status: done
Vertical: restaurant
Actor: employee (send), manager (void; the cashier, with a manager's approval)
Screen: Sell, An approval is needed
Steps:
1. With Kitchen active, the check has two tabs: "Check", with all its lines, and "Current order", with
   what is still to be sent; the tab says how many items are waiting ("Current order, 2 items to send").
   With nothing pending, "Everything is sent". While something is waiting, both tabs carry "Send order (N)"
   (the send icon with the number of items) pinned above the total and "Charge".
2. Review quantities and who serves ("Current order" leaves only what is pending) and press "Send order
   (N)" from either tab. For it to go out as a rush, first arm the flame next to it: the button turns red
   and is called "Send RUSH (N)". "Order N sent to the kitchen." shows at the top of the screen, so "Charge" can be
   pressed without waiting for it to go; the lines are marked with their round ("Order N") and the time
   sent, and the flame disarms. A double send never sends anything twice. On a low screen, the check
   scrolls so that at least one whole line can be read.
3. On pressing "Charge" with something pending, it is sent to the kitchen first and then the charge
   opens: nobody pays for a dish that is not going to be made. The order's notice shows at the top here
   too, so the charge keypad can be tapped from the first moment. If the send fails, the
   charge does not open and it says why. A charge through the assistant or the API does the same: what
   the check has not sent yet goes to the kitchen as a new round before the charge, and if Kitchen
   refuses it, nothing is charged and it says why.
4. A sent line is locked: no quantity, no note, no discount. It can still be comped with its gift: it
   stays on the check at 0 and the kitchen gets nothing new.
5. To take off a dish already sent, press ⊗ "Void this item" on its line: "Void «Croquettes»" opens with
   "It was already sent to the kitchen. It comes off the check and the reason is kept. A manager has to
   approve it.", the one-tap reasons ("Ordered by mistake", "Customer changed their mind", "Sold out",
   "Entered twice") and "Or write the reason…". "Void item" cannot be pressed without a reason.
6. If you do not have the permission to void, pressing "Void item" opens "An approval is needed" on top
   with "Approving: Void an item already sent to the kitchen": a manager approves it with their PIN (or
   their badge) on that same device. "Cancel" keeps the line and the sheet says "This needs a
   manager's approval.".
7. The line comes off the check, the total goes down and the line keeps the reason, who authorized it
   and when.
8. To follow what was sent, in "Check" press "Tickets · N", next to the header of what was sent: "Order
   tickets" opens, one card per round (the most recent on top) with its state in the kitchen, and from it
   a round being cooked is marked as a rush.
In: the check's pending lines.
Out: the lines with their round and the kitchen order open in Kitchen, a rush if the flame was armed
(announces: order sent, with the lines, their notes, their modifiers, the dishes of each menu and who
serves); on voiding a sent line, it announces the voided line with its reason.
If it fails: with nothing pending, "There is nothing new to send to the kitchen."; if Kitchen does not
answer, "The order could not be sent to the kitchen. Try again." shows at the top of the screen and nothing
is charged: you can press "Charge" or "Send order" again without waiting for it to go. If the order is sent
but its slip does not print, the POS warns, at the top too, "Order N sent to the kitchen, but it did not
print. Check the kitchen printer in Printing.". A line already sent cannot be removed: "That line can no
longer be removed: it was sent to the kitchen (void it with a reason), it is charged or it is no longer on
an open check.". Voiding a line not sent, charged, already voided or without a reason is
refused with "That line cannot be voided…". Without Kitchen active there are no tabs and no sending: the
check is charged as always.
Through the assistant: its confirmation card says the check (a table's, by its table as Tables says it and in the reader's language, "4 (Dining room)"; any other, or without access to Tables, by its title or, with none, by its amount), the line, the product, the service, the menu and who serves by their name, and the order type in Kitchen's words, never by an id; what the person asking may not see, or what is no longer there, stays off the card (BASE-F97). A product asked for in words shows as the one that will be added: "two coffees" with "Espresso" and "White coffee" on the menu says "2 · White coffee · 4 (Dining room)"; if the words fit several products or none ("two cafés con leche" with "White coffee" on the menu), no card shows: the assistant hears which products fit or that none has those words, and looks it up on the menu or asks which one. Should the refusal come on confirming (the menu changed between the card and the yes, or through the API), nothing is added and it says "There is no product “café con leche”. Say which one.".
Involved: KITCHEN-F05, KITCHEN-F18, KITCHEN-F19, KITCHEN-F20, KITCHEN-F29, BASE-F84, BASE-F97

### SALE-F21 Print the bill for the table (pre-bill)
<!-- from WORKBOOK.md sha256:c1de49a32c77 -->
Status: done
Vertical: restaurant
Actor: employee, manager
Screen: Bill (pre-bill)
Steps:
1. With the check on screen, press the footer's printer ("Print bill").
2. "Bill" opens with the business (name, address and tax ID of the issuer, with its country's prefix if it is
   registered in the ROI, and with the "Receipt header"
   under them; without an issuer, the receipt header stands for the name and address), the lines,
   notes, discounts, the VAT breakdown, the total and the title, and the notice "Bill — this is not an
   invoice. The fiscal receipt is issued on payment.". With a discount on the check, the "Discount" row
   says what it takes off (the same amount as the check's footer): with prices including VAT, the lines
   minus the discount give the total.
3. Press the printer at the top: with **Printing** and an active ticket printer, the bill comes out on
   it and "Sent to Bar." is read; if not, it goes through the device's print
   dialog with the bill alone: the browser's or, in the installed app, its print screen (the system's
   dialog, with the printer or "Save as PDF").
In: the open check and its total worked out by the server.
Out: a paper with no fiscal number; it uses up no numbering and creates no sale. Each press, one bill. Printing it
leaves the check marked as requested, whether it comes out on the receipt printer or through the device's dialog,
until it is charged in full or deleted; printing it again, adding lines or charging part of it does not remove it.
Asked of the assistant ("print the bill for table 4"), it only comes out on the receipt printer: if none takes it,
it is neither printed nor marked, and its receipt says it was not done, with the reason: "No receipt printer takes
this bill: open it in Sales to print it on this device.".
If it fails: while the business has not yet said its currency, "Bill" keeps loading and the printer stays grey:
the paper never goes out with a supposed figure; if the currency cannot be read, it says so with "Retry", as
when the bill cannot be worked out. If it does not print, "Bill could not be printed"; if the installed app does
not open its print screen, the notice says why after a colon: "…: this version of the ERPlora app cannot print; update it", "…: the device's print
service did not open", "…: the document is empty or too large to print" or "…: this app is linked to
another business".
Involved: PRINTING-F09, TABLE-F34, INVOICE-F21, BASE-F97

### SALE-F22 Charge only part of the check
<!-- from WORKBOOK.md sha256:f6b48edff776 -->
Status: done
Vertical: restaurant
Actor: employee, manager
Screen: Sell
Steps:
1. With two or more lines, tap the lines this person pays for (the line, not its buttons): they are
   marked with a circle.
2. With lines marked, the button at the foot shows what it will charge, "€1.80" or "€7.00", and is called
   "Charge 1 line · €1.80" or "Charge 2 lines · €7.00", with what the server works out for those lines, the
   same amount the sheet will charge; while it arrives, a dash. The "Total" row stays the whole check's.
   With nothing marked, the button goes back to the total, "Charge · €12.00".
3. Press "Charge": the sheet says "Paying 2 lines of €12.00" and charges only those.
4. After charging, the **Sale document** of that charge opens and, behind it, the check stays open with
   what is left; what was charged does not show again. Charging the last pending line closes the check.
   The lines charged are those marked when the sheet opened, even if another one is marked later.
In: the marked lines.
Out: a sale with those lines (announces: sale charged); the lines are left tied to their sale. The
check's % discount applies to each charge; the fixed-amount one, only to the one that closes it.
If it fails: if the server cannot work out what is marked, the foot says so in its words and the button
shows a dash, never the whole check's total. When charging, the same refusals as a normal charge, also
that of the check that changed while it was being charged: the sheet charges what it showed when it
opened, never what came later. If, with the sheet
open, another device closes the check, the screen lets it go on closing the sheet and warns; a check that
no longer exists does not stay on screen.
Involved: TABLE-F33

### SALE-F23 Split a table's check
<!-- from WORKBOOK.md sha256:1b8ef0701770 -->
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
<!-- from WORKBOOK.md sha256:f465ee7cdca5 -->
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
<!-- from WORKBOOK.md sha256:dc080a720767 -->
Status: done — in Tables (TABLE-F15): the check does not change
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
<!-- from WORKBOOK.md sha256:668681fa4a91 -->
Status: done (the calendar's "Charge" button belongs to Appointments: APPOINTMENT-F17)
Vertical: hair salon
Actor: employee, manager
Screen: Sell
Steps:
1. In the Appointments calendar, "Charge" opens the appointment's check (with one line per service, at
   its booked price and with the professional), already in the name of the appointment's customer, and
   goes to **Sell** with that check on screen.
2. It is charged as always; if it is parked and retrieved, the check stays tied to the appointment.
3. Pressing "Charge" again (or on another device at the same time) goes back to the same open check: an
   appointment has a single open check, never two.
In: the appointment, from Appointments.
Out: the sale with the appointment, the customer and the professional, and the purchase on the customer's
card (announces: sale charged and sale born from an appointment, with the appointment, who served and the
total).
If it fails: if the appointment's check is no longer open (it was charged or voided), the POS says so
("That check is not open any more…") and carries on as it was.
Involved: APPOINTMENT-F17, CUSTOMER-F19

### SALE-F27 Pay a line with a voucher
<!-- from WORKBOOK.md sha256:010309d0e04f -->
Status: done
Vertical: hair salon
Actor: employee, manager
Screen: Charge
Steps:
1. With Services active and the client assigned to the check, press "Charge": "Lines paid another way"
   appears with each service line of the charge and, in its slot, "Pay this line with a voucher": the
   client's vouchers that cover that service, the one that is spent first and why.
2. If the line is of more than one unit ("Haircut × 2"), press "Split into N lines": a voucher pays a
   whole line of one unit, and each one has its slot.
3. Choose the voucher (the one spent first comes chosen) and press "Spend one session": the line goes to
   0.00 € with "Already paid · 5 haircuts voucher", the charge's amount goes down and the slot says "5 haircuts voucher:
   session spent. 3 left." with "Undo". What the voucher does not pay is charged with its method; if the
   voucher pays everything, 0.00 € is charged with no payment method.
4. Charge: the line shows on the ticket at 0.00 € with "Already paid · 5 haircuts voucher" and the session is left
   spent.
5. Closing the sheet, parking the check, reloading or charging it on another device changes nothing: the
   check's line keeps the voucher that pays it.
In: the client's vouchers and their balance, from Services.
Out: the check's line paid with a session held in Services (announces: check changed); when charged, the
sale with the line at 0.00 € and the session spent in the same operation (SERVICE-F24). The sale's line
keeps what that session is worth when it is charged, for the production of whoever does it (SALE-F28): it
goes into no total or document, and changing the voucher later does not move it. Removing the
line, voiding it or deleting the check releases the session (SERVICE-F23); splitting or merging checks
carries it with its line. A line paid with a voucher does not change quantity, comp or discount: the
voucher is undone first.
If it fails: Services' reasons are read in the slot ("This voucher has no sessions left.", "This voucher
has expired."…). A line that is not a service, a comp or one of several units cannot be paid with a
voucher ("A voucher pays a line of one unit: split the line first."); a fixed-amount check discount
bigger than what would be left to pay is refused ("That discount is bigger than what it comes off.").
When charging, nothing is charged if the session is no longer held (a day went by) or if the
sale is not the voucher holder's: the reason is read in the sheet and the voucher is undone. The maximum
discount without a manager is measured on what is left to pay: a line paid with a voucher does not count.
Without the permission to spend sessions, the slot does not appear. Without Services active in the
business the slot does not appear either and, if it is turned off with lines paid with a voucher,
charging them is refused ("Services is not active in this business…").
Involved: SERVICE-F22, SERVICE-F23, SERVICE-F24, SERVICE-F25, SALE-F28, STAFF-F21

### SALE-F28 Look up the sales history and figures
<!-- from WORKBOOK.md sha256:1ae7f8809d87 -->
Status: done
Vertical: common
Actor: employee (the history and the figures of their sales), manager (everyone's)
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
   €120.50"). They are the whole business's figures for the manager, the owner and the administrator,
   who see everyone's sales and the business totals; whoever lacks those two permissions, like the
   employee, sees those of their own sales, the same ones the table gives them.
3. The table: Date, Number, Customer, Payment, Status (Completed, Voided, Refunded; with "€5.00 left to
   refund" if part was refunded) and Total. A sale charged with several methods shows them all under
   "Payment", once each and in the order they were charged: "Cash + Card". Search with "Search
   number or customer…", filter by status, payment, date or total, or sort; the payment filter finds a
   sale by any of its methods. An employee only sees their own sales: the ones they charged and the ones
   attributed to their Staff record (the "Served by" chip). The manager, the owner and the administrator
   see everyone's.
4. Tap a row to see its document. The table reloads by itself when a sale is charged, voided
   or refunded.
5. Today's figures are also on **Home**, on the board: "Today's sales" and
   "Today's tickets" show from the start; "Sales, last 7 days" (one bar per day, from oldest to today) and
   "Recent activity" (the last eight sales the person sees, the newest on top, with their number and their
   customer) are
   added with ⋮ ("Customize panel"). They update by themselves when a sale is charged, voided or refunded,
   without reloading. The panels count by the same rule as the screen's figures: the whole business or
   their own sales.
In: nothing from other apps.
Out: nothing saved. What each professional sold in the period (the assistant asks for it for the commission)
counts by the same rule: whoever does not see the whole business gets only the lines of their own sales and, of
the voucher sessions spent outside the till, those of their record. Staff asks for it as the platform, so that each
professional's row counts everything they did, and Staff says which rows each person sees (STAFF-F21). It already takes off
what was refunded: what goes back, to whoever sold it; the money that goes
back with nothing that is worth anything (only money, a comp or a voucher's session), to everyone on that
sale according to what each one has left to refund after the earlier refunds, so nobody goes below 0.
Each refund counts on its sale's day and is shared out to the cent: with what nobody served, it adds up
to the period's "Revenue". On top of that, what the **voucher sessions** each professional did are worth
(SALE-F27, SERVICE-F24), fixed as each one is charged; a session of a voucher with no limit, which has
nothing to divide by, counts the price of its line. The ones spent **outside the checkout** saying who did them
count too (SERVICE-F21): they have no line, so Services tells Sales when they are spent and Sales keeps apart what
they are worth, on the checkout's business day (that of a sale charged at that moment); a professional who only did
those sessions shows 0 sales and €0 of money. A session of the checkout is on its line and never apart, so none
counts twice, and both keep counting even if Services is switched off. It is not money of the period (the voucher
was paid when it was sold), so it is not in "Revenue". A session that comes back, by a refund or by voiding the
sale, stops counting. What a line paid for a **voucher sold** (Services says so when granting it, SERVICE-F14) stays in
"Revenue", but it is no production of whoever sold it, never going over what that line has left after refunds.
Their **production**, which the commission goes on, is what is left without those vouchers plus the sessions: a
voucher of 100.00 € in 3 sessions, sold by A and done by B, gives 0 to A and 100.00 € to B, and adds up to the
period's "Revenue". Sales charged before stay as they were: their line counts for whoever sold it and the
sessions of those vouchers count for nobody, so nothing counts twice.
If it fails: "Error loading metrics" (the figures show as "—"); if the last 7 days cannot be read, "The
last 7 days could not be read.". Empty: "No sales yet.". The total filter is written like any amount in the Hub ("1.000,50",
"1,000.50", "2 500" and "12,50 €" filter); one it cannot read says so under its field
in the words of the amount field ("This is not an amount. Type a figure, for example 12.50.", "This amount
cannot be negative." or, with "1.000" in euros, "This amount can be read in two ways…"), and an end date
before the start one, "The end date cannot be before the start date."; neither of them filters and the
period rules. On Home, a panel for a day with no sales says 0, and one that cannot
be read, "Unavailable".
Involved: STAFF-F21, BASE-F06, BASE-F07, BASE-F08, BASE-F119, SALE-F27, SERVICE-F21, SERVICE-F24

### SALE-F29 See and reprint a sale's document
<!-- from WORKBOOK.md sha256:a66effd35f44 -->
Status: done
Vertical: common
Actor: employee (of their sales), manager (of all of them)
Screen: Sale document
Steps:
1. In **Sales**, tap the row or the "Document" action; it also opens by itself after charging, the whole
   check or part of it.
2. The ticket shows ("Receipt", or "Invoice" if it was charged as an invoice). On top, the business: name,
   address and tax ID of the issuer, with its country's prefix if it is registered in the ROI (a duplicate
   says the same as the original, even if the issuer changes later), with the "Receipt header" under them. Without an issuer set up, the header's first line is the
   name and the rest the address. On an invoice, under "Customer", its tax ID and its address. Then, the number Invoicing gave it when charging ("Invoice FACT-2026-000012", "Receipt TICKET-2026-000031"; without
   Invoicing, or while its document is pending, the sale's number), date, lines, one VAT row per tax key
   (an exempt one says its cause: "Exempt (E1)"), total, payment method (charged with several methods,
   all of them: "Cash + Card"), tendered and change, and the footer. With **VeriFactu**, before the
   footer goes the fiscal QR: "Tax QR:" above, "VERI*FACTU" below
   and "Scan it to check this receipt at the AEAT" ("…this invoice…" if it is an invoice); once the AEAT
   has answered, its code ("CSV: …") instead of that sentence. While VeriFactu has no record of that
   document, the paper comes out without a QR. A receipt with its fiscal document (issued or pending)
   carries a second QR after it, the one of the page where the customer asks for the full invoice:
   "Scan to ask for your full invoice" above and the receipt's code below, to type it if the
   camera cannot read it; if it could not be drawn, the whole address goes below instead. An invoice, or a
   sale without Invoicing, carries none. If its fiscal document could not be issued when charging,
   the paper says so under the number ("Fiscal document pending") and, above the paper (outside what is
   printed), the notice
   "Fiscal document pending — Invoicing could not issue it when charging (the issuer is missing, or a
   permission). Once that is fixed, issue it now." with "Issue now".
3. Press the footer's printer to print it, or "Reprint" on the row. With **Printing** and an active
   ticket printer, the paper comes out on it and "Sent to Bar." is read; if not (or
   with its fiscal document pending), it goes through the device's print dialog with the paper alone: the
   browser's or, in the installed app, its print screen (the system's dialog, with the printer or "Save
   as PDF"). Every print from
   **Sales** comes out with "DUPLICATE", also with its QRs; only the first paper right after
   charging is the original (and it is a copy if it already came out on the printer when charging).
4. **Document pending**: in the list, a sale with some fiscal document pending (its own, the corrective
   invoice of its void or that of a refund) carries the "Document pending" pill under its status and the
   "Issue now" action (for whoever charges). "Issue now" issues everything that is waiting, in order (its
   ticket or invoice and then the corrective invoices), and "Fiscal documents issued." shows. Before that,
   the Hub retries it by itself for a few minutes: if the cause is fixed in time, the pill goes away by
   itself.
In: the sale, with the number of its fiscal document (which Invoicing gave it in the same charge), and
Invoicing's issuer, read by name and as the platform: whoever sells prints those details even if they
cannot read Invoicing. The paper does not touch the document or its fiscal record.
Out: the paper; reprinting creates no sale or fiscal document. "Issue now" issues the documents that were
waiting (announces: sale with its document, one per document).
If it fails: "Loading document…" and "Error loading the document" (also if the fiscal QR cannot be read:
the paper never comes out without it). If it does not print, "Could not print"; if the installed app does
not open its print screen, with the reason after a colon, as when printing the bill for the table. A
refused "Issue now" says Invoicing's reason ("Set up the issuer…") and changes nothing; with no reason,
"The documents could not be issued. Try again.". A sale the person does not see (someone else's, for an
employee) is not opened, reprinted or issued: the window says "Error loading the document" and the API or
the assistant, "That sale does not exist.". If the assistant is asked ("reprint the last ticket"), it is only done
if a receipt printer takes the paper; if not, nothing is printed and its receipt says it was not done, with the
reason: "No receipt printer takes this sale's paper: open the sale to print it on this device."; with its fiscal
document pending, "Its fiscal document is still pending: open the sale to issue it.", and if its VeriFactu record
cannot be read, "Its VeriFactu record could not be read, and its paper never prints without its QR.".
Involved: INVOICE-F01, INVOICE-F02, INVOICE-F04, INVOICE-F06, INVOICE-F18, INVOICE-F21, PRINTING-F08, VERIFACTU-F19, SALE-F21, SALE-F34, BASE-F97

### SALE-F30 Void a charged sale
<!-- from WORKBOOK.md sha256:f0831c2c8ad4 -->
Status: done
Vertical: common
Actor: manager; cashier, with a manager's approval
Screen: Sales, Void sale, An approval is needed
Steps:
1. In **Sales**, on a Completed sale with no refunds, press "Void". Before starting one knows whether it will be
   possible: if your role does it "With approval", "A manager will have to approve this void." shows; if your own role
   says "No", "Your role does not let you void a sale. Ask a manager to do it." shows and nothing opens.
2. "Void sale 20261121-0007" opens. Write the "Reason (required)" and press "Void", or "Cancel".
3. If your role voids "With approval", "An approval is needed" opens on top with "Approving: Void
   a sale": a manager taps their face and types their PIN (or swipes their badge) on that same device.
   Whoever has the permission does not see this question, nor does whoever their role says "No" to: no PIN lets them
   void.
4. "Sale voided" shows, the window closes, the row changes to Voided and the "Voided" figure goes up.
In: the chosen sale.
Out: the sale marked as voided with time, who and reason; it is not deleted (announces: sale voided).
With Invoicing, the corrective invoice of the whole ticket (R5, "RECT" series) in the same void
(INVOICE-F07); if the ticket had been left pending, it is issued first, in the same void. If Invoicing
still cannot, the void goes ahead and both documents are left pending, in sight (SALE-F29, "Issue now").
Inventory puts back the stock (INVENTORY-F23) and Customers takes off the purchase (CUSTOMER-F21).
If it fails: without a reason, "A reason is required to void a sale"; a sale the person does not see
(someone else's, for an employee), "That sale does not exist."; if it was charged as a full
invoice, "This sale carries a full invoice: issue a credit note instead of voiding it."; with refunds,
"This sale already has refunds: refund what is left instead of voiding it."; voided from another device
at the same time, "This sale is already voided.". A refusal is read inside the window, which stays open.
If "Cancel" is pressed in "An approval is needed", nothing is voided and the window says "This needs a
manager's approval.". The approved void does the same as the manager's, only once: the corrective
invoice in the same void, the voucher sessions that go back, the stock and the customer's record; who
approved it, or that whoever may do it did it by themselves, stays in **Employees › Approvals**. If the role
becomes "No" with the window open, the void is refused and nothing is voided, even if a manager had already approved it.
Involved: INVENTORY-F23, CUSTOMER-F21, INVOICE-F07, BASE-F84, BASE-F85

### SALE-F31 Refund a sale (all of it, part of it or through another method)
<!-- from WORKBOOK.md sha256:a78b311b17a5 -->
Status: done
Vertical: common
Actor: manager; cashier, with a manager's approval
Screen: Refund, An approval is needed
Steps:
1. In **Sales**, on a Completed sale (also with an invoice), press "Refund". Before starting one knows whether it will be
   possible: if your role does it "With approval", "A manager will have to approve this refund." shows; if your own role
   says "No", "Your role does not let you refund a sale. Ask a manager to do it." shows and nothing opens.
2. "Refund sale 20261121-0007" shows one card for each way it was paid: "Charged", "Already refunded" and
   "Refundable", with a proposal for a full refund already shared out ("Refund everything" puts it back).
3. If the customer returns articles, mark them in "What goes back": the amount is proposed by itself (the
   share of each marked line, without going over what is left). With two or more units to refund, "Units
   that go back" shows to choose how many. A line part of which already came back says "1 of 2
   already returned"; one that came back whole shows as "Already returned". Without marking anything only
   money is refunded.
4. Change the "Refund amount" of each method if only part goes back. If the original method is no longer
   available, choose another in "Give it back through".
5. Write the "Reason" and press "Refund €12.00". If your role refunds "With approval", "An
   approval is needed" opens on top with "Approving: Refund a sale": a manager approves it with their PIN
   (or their badge) on that same device. Whoever has the permission does not see this question, nor does whoever their
   role says "No" to: no PIN lets them refund.
6. "Refund recorded." shows; if nothing is left to refund, the sale changes to Refunded; if something is
   left, the row says "€6.00 left to refund".
In: what was charged and what was already refunded for each payment method; the sale's lines and the ones
that already came back.
Out: the refund document with one row per payment method, the lines that go back with their units, its
reason and who made it (announces: sale refunded, with the refunded lines and whether it is left fully
refunded) and, with Invoicing, its corrective invoice in the same refund (R5 for a ticket, R1 for an
invoice; by differences, or what is left if it closes the sale: INVOICE-F09, F10).
If it fails: a sale the person does not see (someone else's, for an employee), "That sale does not
exist."; "Card: €20.00 is more than the €12.00 still refundable.", "Card: choose where
this money goes back.", "A refund needs a reason.", "There is no money left to refund on this sale.". If
another refund takes the last of a marked line at the same time: "One of the lines marked already came
back with another refund. Open the refund again to see what is left.". If the Hub does not answer,
pressing again does not refund twice. If "Cancel" is pressed in "An approval is needed",
nothing is refunded and the window says "This needs a manager's approval.". The approved refund is the
same, only once, with its corrective invoice and the voucher sessions that go back; who approved it, or that
whoever may do it did it by themselves, stays in **Employees › Approvals**. If the role becomes "No" with the
window open, the refund is refused and nothing is refunded, even if a manager had already approved it.
Involved: INVENTORY-F24, CUSTOMER-F22, INVOICE-F09, INVOICE-F10, BASE-F84, BASE-F85
Customers takes what was refunded off the record's spending on hearing "sale refunded" (CUSTOMER-F22)
and Inventory puts back the units that go back (INVENTORY-F24), once per refund.

### SALE-F32 Give back a voucher's session
<!-- from WORKBOOK.md sha256:21d924c17995 -->
Status: done
Vertical: hair salon
Actor: manager
Screen: Refund, Void sale
Steps:
1. In **Sales**, press "Refund" on a sale with lines paid with a voucher (it also shows on one paid
   entirely with a voucher, at 0.00 €, while it has a session left to give back).
2. In "What goes back", the line paid with a voucher says "Already paid · 5 haircuts voucher". Mark it: "The
   session goes back to 5 haircuts voucher.".
3. Write the "Reason" and press the button: with money, "Refund €15.00"; only the session, "Give the
   session back".
4. Voiding the sale also gives back all its sessions.
In: the sale's lines paid with a voucher and what already came back of each one.
Out: the refund (announces: sale refunded) and the session back on its voucher in the same operation
(SERVICE-F26, SERVICE-F27). The sale changes to Refunded when all the money and all its sessions come
back.
If it fails: "A refund has to give back money or the session of a voucher."; a session already given
back, "One of the lines marked already came back…". If Services is not active in the business, the
refund or the void of a sale with sessions is refused ("Services is not active in this business…").
Involved: SERVICE-F26, SERVICE-F27

### SALE-F33 Merge the sales of two customer records
<!-- from WORKBOOK.md sha256:1552010f8c23 -->
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
<!-- from WORKBOOK.md sha256:85864b490a9e -->
Status: done
Vertical: common
Actor: manager, administrator
Screen: Settings
Steps:
1. Open **Sales & POS → Settings**; "Point of sale" is read at the top.
2. Change what you need: "Allow cash", "Allow card", "Allow bank transfer", "Show products in the till",
   "Show services in the till", "Require a customer on every sale", "Allow discounts", "Largest discount
   a cashier may give alone, per discount (%)", "Allow parked tickets", "Prices include VAT", "Issue an
   invoice when the customer has a tax ID", "Default document" ("Ticket" or "Invoice"), "Receipt header"
   (added under the issuer's name, tax ID and address; without an issuer yet, the first line is the name
   and the rest the address), "Receipt footer", "Footer image (URL)", "Promotional QR URL" and
   "Promotional QR text".
3. Press **Save**: "Settings saved." shows.
In: nothing from other apps.
Out: the business's settings (one row). The server applies when charging "Allow cash / card / bank
transfer", "Require a customer", "Allow discounts", the maximum discount and prices including VAT; the POS
reads the rest when it opens.
If it fails: "Could not save settings." and, if the refusal is of a field, its reason under it. As in the
form windows, the notice goes as soon as something is changed and a field's reason as soon as that field is
corrected; both come back if the next try is refused too. A refusal that names no field stays until the next
try. Without permission, the fields are locked, there is no "Save" and "You do not have permission to
change these settings. Ask an administrator if you need to." shows. If every payment method that exists is
turned off, the POS goes back to accepting every active method.
Involved: none

### SALE-F35 Add and order the open-price sections
<!-- from WORKBOOK.md sha256:6d1c451fbcf9 -->
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
If it fails: a VAT category that does not exist is refused next to its field. A field's reason goes away
as soon as that field is corrected ("VAT charged", by choosing another category). A section someone else
already deleted: "That section is no longer in this business. Reload the list and try again.".
Through the assistant: its confirmation card says the section by its name, never by an id (one that is no longer there
stays off the card), and the VAT it charges with today's rate, as the list does ("Product — generic · 21%") (BASE-F97).
Involved: TAX-F01, BASE-F97

### SALE-F36 Prepare the quick notes
<!-- from WORKBOOK.md sha256:45e837feb484 -->
Status: done
Vertical: common
Actor: manager
Screen: Quick notes
Steps:
1. Open **Sales & POS → Quick notes**.
2. Press **+**, write the Note (up to 80 characters, e.g. "no salt") and the Position.
3. Press "Add". To change it, "Edit"; to remove it, "Delete" and confirm.
4. In **Sell**, a line's note sheet shows these notes as buttons, in that order.
In: nothing from other apps.
Out: the quick note. Deleting it stops offering it; notes already written keep their text.
If it fails: "The quick note could not be saved."; a note that no longer exists: "That quick note is no
longer in this business. Reload the list and try again.". The refusal of a field shows under it and goes
away as soon as that field is corrected.
Involved: none

### SALE-F37 Add a payment method (Bizum, bank transfer…)
<!-- from WORKBOOK.md sha256:905543d23e9e -->
Status: done
Vertical: common
Actor: manager, assistant
Screen: none (assistant or API)
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
<!-- from WORKBOOK.md sha256:ca62f433f92b -->
Status: done
Vertical: hair salon
Actor: employee, manager
Screen: Sell
Steps:
1. With Services active and "Show services in the till" on, tap "Services" in the category strip (or
   search for it with the magnifier).
2. Tap the service: it goes in as a line with its price. If it is not a fixed price ("From", "Hourly",
   "Variable", "Free"), "Amount of Highlights" opens with its price as a suggestion: enter the amount and
   press "Add €45.00".
3. Charge as always; the line carries the professional like any other.
4. **The professional's price**: a fixed-price service done by a professional who has their own price in
   Services goes in at that price; without their own price, at the service's. The price is set when the
   line is added: changing the professional afterwards does not change it.
5. **Booked price**: the check of an appointment charged from the calendar charges each service at the
   price it was booked at, even if the catalog says another one today. The booked price rules over the
   professional's.
In: the services on offer, their rate, their minimum and maximum and their tax category, from Services;
the professional's own price (their assignments, `service.assignment.list`); the appointment and what it
booked, from Appointments (`appointment.appointment.get`); the refused service, while its notice is
showing (`service.service.get`).
Out: a service line with the service, its frozen price and the service's tax category; it moves no
stock.
If it fails: in "Amount of Highlights", the buttons to add and to use the price wait in grey while the business
has not yet said its currency, and the price does not show yet: "Use —", and on the tile "—" or "From —".
If the currency cannot be read, the sheet says so ("The business's currency could not be read", with the
reason) and offers "Retry"; as soon as it arrives, those two buttons light up. A service
without a tax category shows "VAT missing" and does not go in ("Cannot be sold: no tax category. VAT needs to
be set up."); that notice goes away on its own as soon as the service has a category, without touching
anything else, and also on leaving **Sell**. One whose category has no VAT rule in the business's country
goes in, but the check is not charged: the foot says why, with the category's name and where its rule is
made. An archived one, "That service is no longer offered…"; an amount outside the service's minimum and
maximum, "That amount is outside what the service allows (€30.00 – €80.00).". A booked price that
does not match the appointment: "That is not the price the appointment booked for this service: it is
cancelled, it is another customer's, it did not book this service or it booked it cheaper.". Without
Services active, "Services" does not show in the strip.
Involved: SERVICE-F09, SERVICE-F03, SERVICE-F31, APPOINTMENT-F17

### SALE-F39 Charge with what another app adds (the tip)
<!-- from WORKBOOK.md sha256:9eb254e402d2 -->
Status: partial — the Charge sheet paints the steps the apps turned on declare (today, the tip of Tips), charges what they
add with the sale in a charge with a single payment method and, once charged, lets each step save its own part, with "Retry"
when it cannot; what is added to each payment when splitting the charge, which today is charged without the steps
(hub#1500), and the line of what was added on the Sale document (hub#1502) are missing
Vertical: common
Actor: employee, manager
Screen: Charge, Sale document
Steps:
1. With an app turned on that adds a step to the charge (today only Tips, with "Ask for a tip when charging"),
   the **Charge** sheet paints its row between the amount and the payment methods (the Tips one, TIP-F02).
   With none, the sheet is the usual one.
2. What the step adds is charged together with the sale, but outside it: the big amount says "<total> +
   <tip> tip"; by card, "Charge <total + tip> on the card terminal, then confirm." and the button "Charge
   <total + tip>"; in cash, the amount tendered has to cover both and the change takes both off. With "Split
   the payment", each payment carries its own and "Remaining" counts only the sale.
3. Charge. The **Sale document** opens: the ticket is the usual one (lines, VAT and total of the sale) and, in
   the payment block, below "Tendered", the line "Tip <amount>" shows before the "Change".
In: the steps the active apps declare and what each one adds to each payment.
Out: the sale with its base, its VAT and its total **without the tip**: the ticket, Invoicing's invoice and its
VeriFactu record are the same as without it (INVOICE-F01), because a voluntary tip is not a price and carries no
VAT (see "Why the tip is not on the ticket" in the Tips manual). The sale keeps apart, in each payment, what was
charged on top and its name, to square the amount tendered and the change and for the paper, and the sale
charged notice carries it apart; the **Sales** figures (SALE-F28) do not add it. The step's app keeps its own
(TIP-F02).
If it fails: with no app turned on that adds a step to the charge of whoever charges, a charge that brings an added
amount (through the API or the assistant) does not charge: "This business has no app that adds anything to a charge, such as a tip:
charge the sale alone."; if the app is turned on but whoever charges has no permission for its step, "You have no
permission to add anything to a charge, such as a tip: charge the sale alone.". If the step's app is turned off with the sheet open, the row goes away and it charges without
it.
If the sale is charged and the step cannot save its own, the sale stays charged and the sheet says the step's
notice with "Retry" (TIP-F02); the retry uses the same attempt key and never charges twice (SALE-F06), and that
same key with another added amount is another charge: "That attempt key was already used for another charge. Open it
again to charge this one.". An added amount that does not say what it is does not charge: "Say what the amount added
to this payment is (a tip, for instance).". The ticket's cap (€3,000) and the cash cap (€1,000) look at the sale's
total, as always: the tip is no price.
Involved: TIP-F02, TIP-F03, TIP-F04, CASH_REGISTER-F18, INVOICE-F01

### SALE-F40 See a dish's allergens when ordering it
<!-- from WORKBOOK.md sha256:a1dd433981f3 -->
Status: done
Vertical: common
Actor: employee, manager
Screen: Sell
Steps:
1. In **Sell**, tap an item with allergens declared in Inventory. The line goes in as always and,
   under the name, says "Allergens: Gluten, Milk", in the order of the list of the fourteen. An item without
   allergens has no such row.
2. If the item opens its modifiers sheet, the sheet says its allergens under its name, before adding it.
   In the sheet of a menu, each choice says its own next to its name, and on the check each dish of the
   menu carries those of its product.
3. If the customer asks, the waiter reads them on the line; if the dish does not suit them, they remove the line
   like any other before sending it.
4. Send to the kitchen and charge as always: the allergens do not change the price or the payment.
In: from Inventory, each product's allergens, with the till's catalogue (INVENTORY-F27), and from Modifiers, those
of each option chosen (MODIFIER-F07).
Out: the line with its product's allergens and those of its modifiers (MODIFIER-F12) frozen when it is ordered, like
its modifiers: if Inventory or Modifiers change them afterwards, the line keeps the ones it had (announces: check
changed). They travel to Kitchen with the line when the round is sent, where they are crossed with the customer's
allergy (SALE-F41, KITCHEN-F32). They do not show on the ticket, on the invoice or on the printed bill for the table.
If it fails: without Inventory active there are no allergens, and open-price lines and services do not carry them.
An item with no allergens marked says nothing, because the till does not tell "has none" from "none declared": that
is why Inventory's card says "No allergens declared". A modifier adds its allergens to the dish's: "+Cheese" adds
Milk to the line; one that takes something out ("No cheese") takes none away, and if the customer has an allergy, it
is marked on the line as the customer's allergy and Kitchen sees it all the same.
If a menu's sheet cannot read the allergens of its dishes, it says so and offers "Retry": that way a dish with
no row is not taken for a dish without allergens.
Involved: INVENTORY-F27, INVENTORY-F35, SALE-F11, SALE-F12, SALE-F41, KITCHEN-F32, MODIFIER-F12

### SALE-F41 Mark the customer's allergy on a line
<!-- from WORKBOOK.md sha256:3470420bb0e1 -->
Status: done
Vertical: restaurant
Actor: employee, manager
Screen: Sell
Steps:
1. With Kitchen active, the customer mentions an allergy. On the line of their dish, tap "Note": the sheet has at the
   top the "Customer's allergy" block, with the fourteen allergens by their name and none marked, and below it the
   quick notes and the usual box.
2. Tap the customer's allergens, one or several, and tap "Save". The line says, under the name, highlighted and
   before the note, "Allergy: Gluten".
3. If the dish has any of those allergens, on saving the line says it highlighted: "The dish has Gluten".
   It does not stop the order, because the kitchen may prepare it without it: the waiter talks it over with the
   customer and, if needed, removes the line and orders another dish.
4. On a menu, the allergy is marked on the menu's line and counts for each of its dishes; the warning of step 3
   names the dish that has the allergen ("The burger has Gluten").
5. Send the round: the allergy goes with each dish to its station, highlighted. Until it is
   sent, it is changed by going back to the sheet; unmarking them all removes it.
In: the fourteen allergens; the line's frozen allergens (SALE-F40).
Out: the line with the customer's allergy (announces: check changed); when the round is sent, it goes to Kitchen
with the line (announces: order sent) and stays frozen on the dish. It does not show on the ticket, on the invoice,
on the printed bill for the table or on the customer record.
If it fails: if it is not saved, "That change to the line could not be saved. The line is back as it was.", as with
the note. A line already sent has no note button: if the customer mentions it afterwards, the kitchen is told out
loud or the dish is voided with its reason and ordered again with the allergy. Without Kitchen active the
sheet has no block, because there is no kitchen order to carry it, and the note still works. An allergen that is
not on the list is refused, also through the assistant or the API.
Through the assistant: "the burger on table 4 is for someone allergic to gluten" marks the allergy on that line after
the confirmation card, which says the check, the dish and the allergens by their name.
Involved: SALE-F13, SALE-F20, SALE-F40, INVENTORY-F35, KITCHEN-F32

### SALE-F42 Choose the modifiers of a dish in a menu
<!-- from WORKBOOK.md sha256:aa1c4f5d73c2 -->
Status: done
Vertical: restaurant
Actor: employee, manager
Screen: Sell
Steps:
1. With Menus and combos and Modifiers active, open a menu in the POS and choose a dish that has modifier
   groups, its own or its category's, the same ones it asks for when sold on its own (the entrecôte with "Meat
   doneness"): its groups open right there, under the dish, with the rules, the extra charges with their sign, the
   allergens and the default options of the sheet of an article on its own. A dish without groups is chosen as
   always.
2. Choose the options. Removing the dish, or changing it for another in a single-choice course, removes its
   options. A choice that is repeated (two coffees) carries the same options each time.
3. While a required group of a chosen dish is not complete, the button says what is missing ("Choose 1 in «Meat
   doneness»") and tapping it points to that group. With everything complete, "Add · €16.50" adds to the set price
   the menu's extra charges and those of the chosen options.
4. Press it: the menu goes into the check with its dishes under it and, beside each dish, its options ("Entrecôte
   (Rare, Cheese)").
5. Send to the kitchen: each dish carries its options under it, on the screen and on paper, like a dish on its own.
   Charge as always: the ticket names the options beside their dish, under the menu, and
   the menu charges what it was worth when ordered, options included, even if they change or are deleted later.
In: the groups and options of the product of each chosen dish, from Modifiers (MODIFIER-F06). Modifiers checks and
prices the options of each dish (MODIFIER-F07) and Menus adds them to the menu's amount when the line is added and
again when charging, with the amount ordered (COMBO-F08).
Out: the menu line with the options of each dish, their kitchen text and their allergens, frozen when ordered
(announces: check changed). "Eat in", the menu stays on one line at the menu's VAT, with the options inside (art.
91.Uno.2.2º LIVA), an option with another tax category too. "Take away", each option takes part in the menu's
split (COMBO-F09): one without a tax category of its own, or with its dish's, goes with it, and the dish's weight is
its catalog price plus that of those options; one with another tax category goes to its own take-away category,
weighs its catalog price and shows on its own line with its rate under its dish, as on a dish on its own
(MODIFIER-F07). If with the options everything goes to the same category, the menu stays on one line. The options do
not move stock (COMBO-F10).
If it fails: Modifiers' reasons show inside the sheet, under the dish they refer to ("Choose at least 1 in «Meat
doneness»."…), and a menu with a required group left unchosen does not go into the check, not through the assistant
or the API either, so it never reaches the kitchen without the meat doneness. If a dish's groups cannot be read, the
sheet says so under that dish with "Retry" and the menu cannot be added. Without Modifiers active, the dishes are
chosen without options, as today.
Involved: SALE-F11, SALE-F12, SALE-F40, COMBO-F07, COMBO-F08, COMBO-F09, COMBO-F10, COMBO-F11, MODIFIER-F06,
MODIFIER-F07, MODIFIER-F08

## What the verticals share
<!-- from WORKBOOK.md sha256:a9b0896d68e4 -->

| Shared piece | Flows that use it |
|---|---|
| The charge: the same server price, the same VAT, the same refusals and the same charged-sale notice Inventory and Customers listen to | F01–F06, F22, F26 |
| The open check and its lines: the price is frozen when the line is added; parking, retrieving and appointment are the same check | F09–F18, F22–F24, F26 |
| The **Charge** sheet: methods, keypad, ticket or invoice, customer's details and other apps' steps | F01–F05, F22, F39 |
| Marking lines: it serves to charge part and to split the check | F22, F23 |
| The "Served by" chip and the line's stamp | F16, F20, F26 |
| Voiding a sale: a single notice, and each app that reacts decides its effect | F30 |
| The POS settings: the same for both businesses | F34 and every charge flow |

## Services: what goes in and what comes out
<!-- from WORKBOOK.md sha256:ec70e79bef89 -->

Everything can be asked for through the screens, the assistant (by voice or by text, with the person's
own session) and the API, with the same rules and the same permissions. Designed for voice: a product is
named by its id, its SKU or its name; a customer by their id or their name and, for whoever sees the
customers' contact details, also by their phone or their email (to whoever does not see them, those words
only match a name: 404 `customer.customer_unavailable`, BASE-F119); a sale by its id or its number; a
section or a quick note by its id or its name; a payment method by its id, its name or its type ("cash",
"card"). If a name matches several, it is refused saying which ones
(409 `*_ambiguous`).

What reads or touches a charged sale (the list, the sale, its document and its paper, "Issue now", voiding
and refunding) only reaches the sales the person sees: without "See all sales", the ones they charged and
the ones attributed to them. One they do not see does not exist for them (404 `sale.sale_not_found`).

### What it offers: queries (they read and change nothing)
<!-- from WORKBOOK.md sha256:a82dbcf5d08c -->

| What it gives | Who can | Flows | Service |
|---|---|---|---|
| The sales, with search by number or customer, filters (status, payment, customer, professional, days, total), sorting and pages (up to 100); each one says whether it has some fiscal document pending | see sales | F28, F29 | `sale.sale.list` |
| A whole sale: header, customer with its tax ID and address (on an invoice), lines, payments, VAT breakdown and what was refunded | see sales | F29 | `sale.sale.get` |
| The business as the paper names it: name, tax ID and lines (address and receipt header); for a sale, those of its fiscal document | see sales | F21, F29 | `sale.letterhead.get` |
| The sale recorded with a charge attempt key | see sales | F06 | `sale.sale.by_idempotency_key` |
| The figures of a period of business days, with the tax its sales were declared with (empty if they mix taxes) | see sales | F28 | `sale.sale.stats` |
| What was sold today and today's tickets | see sales | F28 | `sale.sale.today` |
| What was sold on each of the last 7 days | see sales | F28 | `sale.sale.last_7_days` |
| What each professional sold in a period: gross, base, tax, what was refunded of their lines, what is left, what paid for vouchers they sold, what the voucher sessions they did are worth and their production (what the commission goes on) | see sales | F16, F28 | `sale.sale.by_staff` |
| What a check, or some lines, would charge, without charging anything (total, base, VAT, discounts, breakdown and lines) | see sales | F01, F21, F22 | `sale.checkout.preview` |
| The steps the apps turned on add to the charge, those whoever charges sees and in their order: which app each one is of and which part of it paints it; with none, the charge takes nothing added | charge | F39 | `sale.checkout.steps` |
| The open checks (or of another state), with search by title and pages | see sales | F17 | `sale.order.list` |
| A check with its uncharged lines | see sales | F17, F19, F40 | `sale.order.get` |
| The active payment methods, with the ones the business allows today | see payment methods | F02, F03 | `sale.payment_method.list` |
| The POS settings (to edit them) | settings | F34 | `sale.settings.get` |
| The settings the POS needs to sell | see sales | F01–F05 | `sale.pos_settings.get` |
| The sections, in their order, with today's VAT | see sales | F09, F35 | `sale.department.list` |
| The quick notes, in their order | see sales | F13, F36 | `sale.quick_note.list` |
| Today's business day | see sales | F28 | `sale.business_day.get` |
| For each payment of a sale, what was refunded and what is left, and for each line what already came back | see sales | F31 | `sale.refund.options` |
| A sale's refunds, with the state and the number of their corrective invoice | see sales | F31 | `sale.refund.list` |
| The refund recorded with a key | see sales | F31 | `sale.refund.by_idempotency_key` |
| The product of a new line as the write that adds it finds it, to check it before the assistant's card; words that are no product, or fit several, draw no card | build the check | F20 | `sale.order_line.check` |
| The name of a record a write of Sales touches, by its id, and that of a refund, by its sale ("Refund of sale 20261014-0007"), by which Services names the one that gives sessions back (SERVICE-F26): only for the assistant's card; what does not exist or the person asking may not read goes unnamed | see sales | F20, F32, F35 | `sale.record.get` |

The sales, the figures, the checks, the charge preview, the payment methods, the settings, the sections,
the quick notes and what is refundable can be followed live.

### What it offers: actions (they change data)
<!-- from WORKBOOK.md sha256:521328cbfe57 -->

| What it does | Who can | Flows | Service |
|---|---|---|---|
| Charges a check (whole or some lines) or some loose lines, with one or several methods; spends the sessions of its lines paid with a voucher; asks Invoicing for its ticket or its invoice in the same charge; in cash, only with the cash register open | charge | F01–F06, F08, F22, F26, F27 | `sale.sale.complete` |
| The same charge, with a discount above the maximum | uncapped discount | F14 | `sale.sale.complete_over_limit` |
| Voids a charged sale with a reason (and gives back its voucher sessions); with its corrective invoice in the same void (and its ticket first, if it was pending) | void | F30, F32 | `sale.sale.void` |
| Issues now a sale's fiscal documents that are waiting ("Issue now"): its ticket or invoice and the corrective invoices of its void and its refunds | charge (and Invoicing's permission for each document) | F29 | `sale.sale.issue_documents` |
| Prints a sale's ticket or invoice again, marked "DUPLICATE", on the receipt printer; if none takes it (or its fiscal document is pending, or its QR cannot be read), it fails and says why, and the screen prints it on the device | see sales | F29 | `sale.sale.print` |
| Refunds money from a sale per payment, and the lines that go back (the ones paid with a voucher give back their session); with its corrective invoice in the same refund | refund | F31, F32 | `sale.sale.refund` |
| Opens a check, with or without lines (articles, services —at their booked price or at the professional's— or open price); that of an appointment that already has an open one returns that one (`already`) | build the check | F01, F17, F26, F38 | `sale.order.open` |
| Adds a catalog article to a check | build the check | F01, F10, F11, F40 | `sale.order.add_line` |
| Adds a service from Services to a check | build the check | F38 | `sale.order.add_service_line` |
| Adds a menu from Menus and combos to a check, with what was picked in each course; Menus checks the choice and sets the price | build the check | F12, F40, F42 | `sale.order.add_combo_line` |
| Pays a service line with one of the client's vouchers (holds the session) | build the check and spend sessions | F27 | `sale.order.apply_voucher` |
| Undoes a line's voucher (releases the session) | build the check and spend sessions | F27 | `sale.order.remove_voucher` |
| Adds an open-price line | open price | F09 | `sale.order.add_open_line` |
| Changes a line's quantity, comp or note | build the check | F01, F10, F13, F15 | `sale.order.update_line` |
| Changes whose line it is | build the check | F16 | `sale.order.set_line_staff` |
| Says who serves an open check (or "me"): the kitchen order carries their name and the sale is theirs | build the check | F16 | `sale.order.set_staff` |
| Marks or takes off the customer's allergy on a line not sent yet | build the check | F41 | `sale.order.set_line_allergy` |
| Splits a line of N units into N lines | build the check | F27 | `sale.order.split_line` |
| Removes an unsent line | build the check | F01 | `sale.order.remove_line` |
| Voids a line already sent to the kitchen, with a reason | void | F20, KITCHEN-F29 | `sale.order.void_line` |
| Sends the pending lines to the kitchen | build the check | F20 | `sale.order.fire` |
| Splits a check | build the check | F23 | `sale.order.split` |
| Merges two checks | build the check | F24 | `sale.order.merge` |
| Voids an open check (an empty one, with no live lines or payments, with just building the check) | void; empty: build the check | F18, TABLE-F20 | `sale.order.void` |
| The same void of a check with something ordered or charged, the one a manager approves with their PIN | void | F18, TABLE-F20 | `sale.order.void_ordered` |
| Sets the check's discount (and its version above the maximum) | build the check / uncapped discount | F14 | `sale.order.set_discount`, `sale.order.set_discount_over_limit` |
| Sets a line's discount (and its version above the maximum) | build the check / uncapped discount | F14 | `sale.order.set_line_discount`, `sale.order.set_line_discount_over_limit` |
| Sets a check's title (parking) | build the check | F17 | `sale.order.set_label` |
| Links a check to its appointment | build the check | F26 | `sale.order.set_appointment` |
| Prints the bill of a table (not an invoice: no number, no payment) on the receipt printer; if none takes it, it fails and says why, and the screen prints it on the device; the table shows "Bill requested" until it is charged in full | see sales | F21 | `sale.order.print_bill` |
| Notes that the device printed a table's bill because no receipt printer took it: the table shows "Bill requested"; the screen only (the assistant does not print on the device) | see sales | F21 | `sale.order.note_bill` |
| Creates a payment method | create payment methods | F37 | `sale.payment_method.create` |
| Saves the POS settings | settings | F34 | `sale.settings.update` |
| Creates, changes and deletes sections | settings | F35 | `sale.department.create`, `.update`, `.delete` |
| Creates, changes and deletes quick notes | settings | F36 | `sale.quick_note.create`, `.update`, `.delete` |

### What it announces
<!-- from WORKBOOK.md sha256:d898ff863395 -->

| Notice | When | What it carries | Service |
|---|---|---|---|
| Sale charged | Charge | The sale, its number, check, document, amounts in cents, currency, moment, customer and their fiscal copy, who served, appointment, payments (each with what another app added to it apart, and its name) and lines (product or service, quantity, whether it is a service, whether a voucher paid it, amounts) | `sale.sale.completed` |
| Sale born from an appointment | Charge a check with an appointment | The sale, the appointment, who served and the total | `sale.sale.created_from_appointment` |
| Sale voided | Void | The sale, its number, reason, who and when, total, customer, check and document | `sale.sale.voided` |
| Sale refunded | Refund | The sale, the refund, the amount, the reason, whether it is left fully refunded, the payments and the refunded lines | `sale.sale.refunded` |
| Sales re-pointed | Merge records | The record that stays and the absorbed one | `sale.sale.reassigned` |
| A line paid for a voucher, or no longer | Services grants or voids a voucher saying its sale | The sale and the line | `sale.sale.voucher_line_changed` |
| A voucher session done outside the checkout | Services spends a session saying who did it | The session and the professional | `sale.voucher_session.recorded` |
| Sale with its document | A document that could not be issued in the charge, the void or the refund is issued later (the charge's retry, "Issue now" or Invoicing's reaction) | The sale, the document, its number, the refund (`refund_id`) or whether it is the void's (`void`); one per document | `sale.sale.invoiced` |
| Check opened | Open or split | The check | `sale.order.opened` |
| Check changed | Any change of lines, discounts or title, and its first printed bill | The check | `sale.order.changed` |
| Order sent | Send to the kitchen | The check, its title, the channel, the round, who serves and the lines with their notes, their product's and their modifiers' allergens (in a menu, each dish's) and the customer's allergy | `sale.order.fired` |
| Check closed | Charge the last of a check | The check | `sale.order.completed` |
| Check voided | Void an open check | The check | `sale.order.voided` |
| Checks merged | Merge | The absorbed one and the one that stays | `sale.order.merged` |
| Check with a new title | Change the title of an open check, also when moving it to another table or seating it again | The check | `sale.order.relabeled` |
| Line removed | Remove or void a line | The check and the line | `sale.order.line_removed` |
| Line voided | Void a sent line | The check, the line and the reason | `sale.order.line_voided` |
| Payment method, settings, section, quick note | Creating or changing them | Which one | `sale.payment_method.created`, `sale.settings.updated`, `sale.department.*`, `sale.quick_note.*` |

### What it reacts to
<!-- from WORKBOOK.md sha256:38cf6ee5d06b -->

| Notice | From | What it does | Service |
|---|---|---|---|
| Records merged (`customer.customer.merged`) | Customers | Moves the sales of the absorbed record to the one that stays (F33) | `sale.customer.reassign` |
| Document issued (`invoice.invoice.issued`) | Invoicing | Links by its source (`source = {type, sale_id, refund_id, void}`) a document that was left pending: a refund's corrective invoice goes back to that refund, a void's to the sale, the charge's ticket or invoice to the sale; the rest (manual invoice, F3 that replaces, corrective invoice of an invoice) belongs to Invoicing (F29) | `sale.sale.record_invoice` |

### What it needs from other apps
<!-- from WORKBOOK.md sha256:272d015e0c61 -->

- **Taxes** (required): the rule and the VAT calculation of each line when charging.
- **Customers** (required): the sale's customer record and its search by name or, for whoever sees the
  customers' contact details, by phone or email; the link of the check with its customer is kept by
  Customers (`customer.order.link`).
- **Inventory** (optional): the sale catalog, the price, the unit and the tax category of each article,
  read with its own queries when the line is added.
- **Staff** (optional): the team for the "Served by" chip, the record of whoever is signed in
  (`staff.member.current`, without Staff's permission), to which the charge attributes "Me", and the name
  of the person of a line not chosen on that screen (`staff.member.detail`).
- **Services** (optional): its services on offer (`service.service.list_for_sale`, and
  `service.service.get` when the line is added and while the notice of a refused one lasts), the client's
  vouchers for a service
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
  with the check on screen, `.restore` and `.park`. Without Tables active there is no button. The
  assistant's card says a table's check by its table with `table.session.by_order`, as the person asking;
  without Tables, or without the right to see its checks, by its title.
- **Appointments** (optional): a check's appointment and what it booked, to charge its booked price
  (`appointment.appointment.get`).

| From | What for | Flows | Service |
|---|---|---|---|
| Inventory | The articles that are tapped or searched for, with what is sold out, those with no VAT and their allergens | F07, F40 | `inventory.product.list` |
| Inventory | The allergens of a menu's dishes | F40 | `inventory.product.get` |
| Modifiers | The groups and options of an article, or of a dish in a menu | F11, F42 | `modifier.group.for_target` |
| Menus and combos | The menus that can be sold, with their courses and choices | F12, F42 | `combo.combo.for_sale` |
| VeriFactu | Whether tickets and invoices can be issued now, and if not, why | F07 | `verifactu.config.get` |

### Who uses it
<!-- from WORKBOOK.md sha256:4722b9a4a381 -->

| App | What for | Service |
|---|---|---|
| Inventory | Lowers the stock when a sale is charged, puts it back when it is voided and puts back what goes back in a refund | `sale.sale.completed`, `sale.sale.voided`, `sale.sale.refunded` |
| Customers | Adds the purchase to the record, takes it off when it is voided and takes off what was refunded | `sale.sale.completed`, `sale.sale.voided`, `sale.sale.refunded` |
| Services | Does not react to notices: Sales calls its session operations when building, charging, voiding and refunding; Services tells it which line paid for a voucher and who did a session spent outside the checkout, through its internal operations | `service.session.*`, `sale.sale.voucher_sold`, `.voucher_unsold`, `sale.voucher_session.record` |
| Invoicing | Sales asks it for the document in the same charge, void or refund; its reactions to the notices issue it if it could not then (INVOICE-F06) and it reads the sale, its lines and its refunds (it requires it) | `sale.sale.completed`, `sale.sale.voided`, `sale.sale.refunded` |
| Cash register | Does not react to notices: it reads the sales, voids and refunds of each shift (it requires it); Sales asks it whether the cash register is open | `Sale`, `Refund`, `sale.order.list` |
| Appointments | Marks a sale's appointment as charged and undoes it when it is voided; opens an appointment's check (`sale.order.open`) and takes it to the POS through its address | `sale.sale.created_from_appointment`, `sale.sale.voided` |
| Tables | Opens, retitles, splits and merges its tables' checks and voids the empty one of a table being closed, through Sales' operations with the session of whoever is on the floor; reads each check's state | `sale.order.open`, `.set_label`, `.split`, `.merge`, `.void` |
| Kitchen | Opens the kitchen order of each round sent and brings it up to date when the check is charged in full, voided or one of its lines is voided (KITCHEN-F05, KITCHEN-F27 to KITCHEN-F29) | `sale.order.fired`, `sale.order.completed`, `sale.order.voided`, `sale.order.line_voided` |

### Who can do what
<!-- from WORKBOOK.md sha256:bbb3ec1467dc -->

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| See sales and their figures, checks, POS settings, sections and quick notes | yes | yes | yes | yes | `sale.view_sale` |
| Build the check (open, add, change, remove, split, merge, send to the kitchen, discount up to the maximum) | yes | yes | yes | yes | `sale.add_sale` |
| Charge | yes | yes | yes | yes | `sale.take_payment` |
| Sell at an open price | yes | yes | yes | no | `sale.sell_open_price` |
| Discounts above the maximum | yes | yes | yes | no | `sale.discount_over_limit` |
| Void sales, open checks with something ordered or charged and sent lines (an empty check is voided by whoever builds the check) | yes | yes | yes | no | `sale.void_sale` |
| Refund | yes | yes | yes | no | `sale.refund_sale` |
| See the payment methods | yes | yes | yes | yes | `sale.view_paymentmethod` |
| Create payment methods | yes | yes | yes | no | `sale.add_paymentmethod` |
| See everyone's sales (without it, only their own: the ones they charged and the ones attributed to them) and, with the business totals (`base.view_business_totals`), the whole business's figures (without both, those of their own sales) | yes | yes | yes | no | `sale.view_all_sales` |
| Settings, sections and quick notes | yes | yes | yes | no | `sale.manage_settings` |

The roles come from the SaaS with a prefix (`hub_owner`, `hub_admin`, `hub_manager`, `hub_employee`).

Two data permissions of the platform (BASE-F119) trim what is seen in Sales: what the comps cost (SALE-F15)
is only seen by whoever sees the costs (owner, administrator and manager), and naming a charge's customer
by their phone or their email is only for whoever sees the customers' contact details (the employee too).
Sales does not show the customer's email or phone: it keeps their name and, on an invoice, their tax ID
and their address, which are tax details that everyone who sees the sale sees.

What the employee cannot do in the POS they ask for on their own device and a manager approves it with
their PIN or their badge ("An approval is needed", BASE-F84), once and for that very request: voiding and
refunding a sale, voiding a line sent to the kitchen, deleting a check with something ordered, selling at
an open price and discounts above the maximum. The approved action does everything the manager's does
(also what Invoicing and Services move: the corrective invoice and the voucher sessions that go back) and
stays in **Employees › Approvals**, like the one the manager does by themselves (BASE-F85). Seeing everyone's
sales, the whole business's figures, the settings and creating payment methods are not approved.

The accountancy firm (`hub_accountant`) only reads: "See sales, checks, POS settings, sections and quick notes",
"See the payment methods" and "See everyone's sales". It does not build checks, charge, void or refund, nobody
approves anything for it and it does not touch the settings.

What touches a voucher's session also asks for Services' permission, because it is Services that moves
it with the session of whoever sells: paying a line with a voucher, undoing it, removing, voiding or
charging a line paid with a voucher, "Spend sessions" (`service.redeem_package`, every role but the accountancy firm has it);
voiding or refunding a sale with sessions, "Give voucher sessions back" (`service.return_session`: owner,
administrator and manager, the same who void and refund). The other way round, saying who did a session spent
outside the checkout (SERVICE-F21) asks for "Build the check" (`sale.add_sale`, every role but the accountancy firm), like saying whose a
line is.
