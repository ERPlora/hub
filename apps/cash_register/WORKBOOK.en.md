<!-- generated from WORKBOOK.md sha256:0eb0aea2d23c7a360f774d057e08b0156f43a6e53f0cd9b4cb18d5a95eeca3a6 -->

## What it is for and who it is for

Cash register keeps track of the **drawer's cash by shifts**. A session is opened with the float that is
in the drawer; during the shift, the charges, voids and refunds from Sales show up by themselves, and the
cash brought in and taken out (change brought from the safe, a payment to a supplier, a drop to the bank)
is recorded by hand; the drawer is counted by notes and coins, and at closing what there should be
(**expected**) is compared with what has been counted: the **difference** is kept for good. It works the
same for the hair salon and for the restaurant.

Who uses it:

- The **employee** acting as cashier: opens, records, counts and closes.
- The **manager**: the same and, besides, sees the expected cash even when the count is blind.
- The **owner** and the **administrator**: everything, and they also set up the cash register and add
  the drawers.

Cash register does not charge (that is Sales), does not open the physical drawer (Printing will) and does
not invoice.

## Reference adopted

ERPlora does not invent flows: it adopts the ones the market has already proven.

- [Toast — shift review](https://doc.toasttab.com/doc/platformguide/platformCompletingShiftReview.html):
  at closing, what is still open is shown and a warning is given without preventing the close; the
  drawer closes at the business day's cut-off (04:00 by default) if nobody closed it; the blind close,
  with a permission that lets the supervisor see the expected cash.
- [Lightspeed — shift checklist](https://resto-support.lightspeedhq.com/hc/en-us/article_attachments/360044738513):
  opening with a float, cash in and out, blind count and closing by shift.
- Square (cash drawer management): "expected in drawer" visible during the shift, cash in and out with a
  reason, a drawer report per session with the breakdown by payment method; partial (X) and closing (Z)
  report.
- Odoo, Shopify POS, Loyverse and Lightspeed Retail: with cash control on, no cash is charged without an
  open session; the opening screen is put in front of the POS.
- From the market in general: the drawer is cash only (cards do not count towards the expected cash), a
  closed shift is not reopened, and whatever is corrected later is corrected with another movement in the
  open shift, never by rewriting the closed one.

## Before you start

- **Sales & POS** is turned on with Cash register and cannot be turned off while Cash register is on: the
  charges, voids and refunds of the shift are those of Sales.
- **Settings**: the default ones apply from day one (count required to close, no negative balance, no
  blind count, no auto-close). They are changed in **Cash register → Settings**.
- **Drawers**: optional. If the business has several (bar and terrace), they are added in **Cash register →
  Settings → Drawers**; when opening the session one is chosen. With only one, it is chosen by itself.
- **Currency**: the business's (today, the euro). The count shows its notes and coins.
- **Time zone**: the business's. In this phase, Madrid time (`Europe/Madrid`) for everyone: the business
  day, the session number and the auto-close time come from it.

Initial setup, step by step:

1. As an administrator, open **Cash register → Settings**, decide on the required float, the required
   count, the negative balance, the blind count and the auto-close, and tap "Save" (CASH_REGISTER-F01).
2. If you have several drawers, add them on the same screen (CASH_REGISTER-F02).
3. In **Cash register**, tap "Open session" and open with the real float (CASH_REGISTER-F03).
4. Charge a small sale in cash in **Sales & POS → Sell** and check in **Cash register** that the expected
   cash goes up.

## Screens

### Cash register
Menu **Cash register**. At the top, the title "Cash register" and the "Open session" button (off while a
session is open: "There is already an open cash session. Close it before opening another one."). Below,
the cash figures: "Current session" and "Recent discrepancies" (CASH_REGISTER-F12). Then the table of
sessions, from the most recent to the oldest, 50 per page: Session, Opened on, Status ("Open", "Closed"),
Opening, Expected, Counted, Difference. Search box "Search session…" (by number), filters (status, number
and the four amounts) and table or card view. Per row: "Detail" always and, in the open session,
"Movement", "Count" and "Close"; tapping the row opens the detail. Each action opens its window:

- **Open cash session**: "Drawer" (optional; only if there are drawers), "Opening float", "Notes", "Open
  session" and "Cancel".
- **Cash movement · S-…**: "Type" ("Cash in" or "Cash out"), "Amount", "Concept", "Register" and
  "Cancel".
- **Cash count · S-…**: "Count type" ("Closing" by default, or "Opening"), "Notes", a box per note and per
  coin under "Bills" and "Coins", and "Total counted" live; with no table for the currency, a single
  "Total counted" field. "Register count" and "Cancel".
- **Close session · S-…**: the shift review, "Expected in the drawer" and "Difference" live (if whoever
  closes may see them), "Counted cash", "Closing notes", "Close session" and "Cancel".

Success shows as a green notice ("Session opened", "Cash-in recorded (…)", "Count recorded · total
counted …", "Session S-… closed · expected … · counted … · difference …"); a refusal, inside the window,
with the server's words and the field marked. Empty: "No cash sessions.". Loading: "Loading…". Error while
loading: the message in the table with "Retry".

Two notices may show above the table:

- "Sale lines in no shift": how many sale lines (charges, voids, refunds) and how much cash fell in no
  shift, with "View" for their list (CASH_REGISTER-F17).
- "Session S-… was due to close by itself at 04:00": the auto-close is on and the session is still open
  from an earlier day; "Open session" turns on and, when opening, the old one closes by itself
  (CASH_REGISTER-F10). That session no longer takes movements, counts or a close: only "Detail" is left
  in its row.

### Session detail
From **Cash register**, "Detail" or tapping a row: it opens as a page, with its back arrow. Title
"Session detail · S-…". A summary
in two columns: Status, Drawer, Opened (when and by whom), Closed (when and by whom, or "Closed by
itself"), Movements (how many), Opening float, Sales (all payment methods) and, below, Cash sales, Card
sales and Sales with other payment methods (this one only if there were any), Refunds, Cash in, Cash out,
Comps, Expected, Counted and Difference, and the opening and closing notes. In an open session Counted
and Difference show "—". Below, two tables, from the most recent to the oldest, 50 per page and as cards
on the phone: **Movements** (When, Type, Amount with its sign, Method, Concept) and **Counts** (When,
Count type, Total counted, Notes). Empty: "No movements in this session." and "No counts in this
session.". The "Print" button prints the report on paper: "Partial report (X)" if the session is open,
"Cash closing (Z)" if it is closed (CASH_REGISTER-F16).

### Cash register settings
Menu **Cash register → Settings**. A "Cash register" card with "Turn on the cash register", "Require an
opening float", "Require a count to close", "Allow a negative balance", "Blind count", "Daily auto-close"
and "Auto-close time" (from 00:00 to 23:00, on the hour), and "Save". Below, the "Drawers" card: the list
of drawers (name, active) with "Add drawer", "Rename" and "Deactivate"/"Activate". Whoever cannot change
the settings sees them locked with "You do not have permission to change these settings.". Loading:
"Loading settings…". Error: "Could not load the settings." with "Retry"; when saving, "Could not save the
settings.". Saved: "Settings saved.".

## States of each screen

| State | What the person sees |
|---|---|
| Loading | "Loading…" (or its screen's text: "Loading settings…", "Loading the cash figures…") while the first result arrives. |
| Empty | "No cash sessions.", "No movements in this session.", "No counts in this session.", "No closed sessions yet.". |
| Error | The notice with "Retry"; the refusal of an action shows inside its window, next to its field. |
| Reconnecting | What is drawn stays; a strip warns "Reconnecting…" until the connection is back. |
| App inactive | "Cash register is not active in this business." instead of the list. |
| No permission | What they cannot do does not show ("Open session", "Movement", "Count", "Close", "Save"); if they get there another way, "You do not have permission". |

## Flows

| ID | Flow | Vertical | Status |
|---|---|---|---|
| CASH_REGISTER-F01 | Set up how the cash register works | common | done |
| CASH_REGISTER-F02 | Add, rename and deactivate a drawer | common | done |
| CASH_REGISTER-F03 | Open the cash shift with the starting float | common | done |
| CASH_REGISTER-F04 | Sell only with the cash register open | common | done |
| CASH_REGISTER-F05 | Record cash in or cash out | common | done |
| CASH_REGISTER-F06 | Count the drawer by notes and coins | common | done |
| CASH_REGISTER-F07 | Blind count: who sees the expected cash | common | done |
| CASH_REGISTER-F08 | Review what is still pending before closing | common | done |
| CASH_REGISTER-F09 | Close the shift: expected, counted and difference | common | done |
| CASH_REGISTER-F10 | Close by itself the drawer forgotten at the end of the day | common | done |
| CASH_REGISTER-F11 | Look up a session and review a discrepancy | common | done |
| CASH_REGISTER-F12 | See the cash register on the home panels | common | done |
| CASH_REGISTER-F13 | Record in the cash register each payment of a sale | common | done |
| CASH_REGISTER-F14 | Offset a voided sale in the cash register | common | done |
| CASH_REGISTER-F15 | Record a refund in the cash register | common | done |
| CASH_REGISTER-F16 | Print the session report (X or Z) | common | done |
| CASH_REGISTER-F17 | See the sale lines in no shift | common | done |

### CASH_REGISTER-F01 Set up how the cash register works
Status: done
Vertical: common
Actor: administrator
Screen: Cash register settings
Steps:
1. Open **Cash register → Settings**.
2. Turn on or off "Turn on the cash register", "Require an opening float", "Require a count to close",
   "Allow a negative balance", "Blind count" and "Daily auto-close" with its time.
3. Tap "Save". What you changed is saved; the rest stays as it was.
4. "Settings saved." shows and, from that moment, the server applies the required float (F03), the
   required count (F09), the negative balance (F05), the blind count (F07) and the auto-close (F10),
   whether the order comes from the screen, the assistant or the API.
In: the administrator's decisions.
Out: the business's cash register settings, a single row (announces: `cash_register.settings.updated`).
Never saved, the default ones apply.
If it fails: "Could not save the settings." with the reason, and the settings stay as they were. If the
reading fails, the screen shows no values (never the default ones as if they were the business's) and
offers "Retry". Without the settings permission, the fields show locked and there is no "Save".
Involved: CASH_REGISTER-F03, F05, F07, F09, F10

### CASH_REGISTER-F02 Add, rename and deactivate a drawer
Status: done
Vertical: common
Actor: administrator, assistant
Screen: Cash register settings
Steps:
1. In **Cash register → Settings → Drawers**, tap "Add drawer", type its name ("Bar") and tap "Save"; or
   ask the assistant ("create a drawer called Bar").
2. To change its name, tap "Rename"; to stop using it, "Deactivate".
3. The active drawer appears in "Drawer" when opening the cash register.
In: the drawer's name.
Out: the drawer (announces: `cash_register.register.created` or `cash_register.register.updated`). A
drawer is never deleted: the sessions name it.
If it fails: without a name, "Type the drawer's name."; with a name another drawer already has (whatever
the case), "There is already a drawer with that name.".
Involved: CASH_REGISTER-F03

### CASH_REGISTER-F03 Open the cash shift with the starting float
Status: done
Vertical: common
Actor: employee, manager, administrator, assistant
Screen: Cash register
Steps:
1. In **Cash register**, tap "Open session".
2. Choose the "Drawer" if there are several (with only one it is chosen by itself), type the "Opening
   float" as it reads ("150.50"; empty is 0) and, if you want, "Notes".
3. Tap "Open session".
4. "Session opened" shows; the session appears at the top of the table as "Open", with its number
   `S-AAMMDD-NNNN` (sequential within the business day, set by the system) and "Open session" turns off.
In: drawer, float and notes; the business's settings.
Out: the open session, in the name of whoever opens it (announces: `cash_register.session.opened`). The
float counts towards the expected cash from that moment.
If it fails: "There is already an open cash session. Close it before opening another one." (one per
business, whatever the drawer; if two devices open at once, only one opens and the other gets this
notice); with the float required and the float empty or zero, "This business requires an opening float:
give the cash the drawer starts with." under the field; a deactivated drawer or one that does not exist,
"That drawer is not available."; an unreadable amount ("This is not an amount. Type a figure, for example
12.50."), a negative or an ambiguous one ("1,250") is stopped before sending.
Involved: CASH_REGISTER-F04, F09

### CASH_REGISTER-F04 Sell only with the cash register open
Status: done — Sales applies it when charging (SALE-F08): it asks Cash register whether the cash register
is open (see "Contract with Sales"). What is charged in cash with no shift because Cash register was off or
did not answer shows in "Sale lines in no shift" (F17), without losing anything.
Vertical: common
Actor: employee, system
Screen: Sell (from Sales)
Steps:
1. With "Turn on the cash register" on and no open session, the cashier tries to charge in cash.
2. Sales refuses it with "The cash register is closed: open a cash session to charge in cash." (409
   `sale.cash_register_closed`); by card, transfer or other it charges. A session open past its cut-off
   (F10) still lets charges through: what is charged shows in F17.
In: "Turn on the cash register" and whether there is an open session (`cash_register.session.current`).
Out: nothing of its own.
If it fails: if Cash register does not answer, Sales charges (the block gives way rather than stopping the
sales) and the charge appears in F17.
Involved: SALE-F08

### CASH_REGISTER-F05 Record cash in or cash out
Status: done
Vertical: common
Actor: employee, manager, administrator, assistant
Screen: Cash register
Steps:
1. In the row of the open session, tap "Movement".
2. Choose "Cash in" (change brought from the safe) or "Cash out" (a payment to a supplier, a drop to the
   bank), type the "Amount" as a positive figure and the "Concept".
3. Tap "Register".
4. "Cash-in recorded (…)" or "Cash-out recorded (…)" shows; in the detail the movement appears (the cash
   out as negative) and the expected cash goes up or down.
In: type, amount and concept. From the screen the method is always cash; the assistant or the API can
also record card, transfer or other, which show in the list and in "Cash in" or "Cash out" but do not
count towards the expected cash.
Out: the movement, in the name of whoever records it (announces: `cash_register.movement.added`). The
sign is set by the system according to the type.
If it fails: "This cash-out would leave the drawer below zero and a negative balance is not allowed." if
the settings do not allow it; a zero, unreadable or negative amount is stopped before sending; the
session closed on another device: "That cash session is closed: a closed session takes no new
movements.". A wrong movement is neither edited nor deleted: the opposite one is recorded with a concept
that says why.
Involved: none

### CASH_REGISTER-F06 Count the drawer by notes and coins
Status: done
Vertical: common
Actor: employee, manager, administrator
Screen: Cash register
Steps:
1. In the row of the open session, tap "Count".
2. Leave "Closing" (at the end of the shift) or choose "Opening" (to check the float); type how many of
   each note and coin there are; "Total counted" adds up as you go. With no table for the currency,
   type the total.
3. Tap "Register count".
4. "Count recorded · total counted …" shows and the count appears in the detail. If it was a "Closing"
   one, "Close session" opens straight away with "Counted cash" already filled in (F09); the count closes
   nothing by itself.
In: the quantities per note and coin, or the total.
Out: the count with its breakdown (announces: `cash_register.count.added`). The total is added up by the
system with the currency's decimals; a total typed by hand (or sent through the API) is stored as it is
and prevails over the breakdown.
If it fails: a closed session, "That cash session is closed: a closed session takes no new movements."; a
note or coin that is not of the business's currency, under the breakdown; with neither breakdown nor
total, "Count the drawer: give its notes and coins or its total.".
Involved: CASH_REGISTER-F09

### CASH_REGISTER-F07 Blind count: who sees the expected cash
Status: done
Vertical: common
Actor: administrator, manager, employee
Screen: Cash register, Session detail
Steps:
1. The administrator turns on "Blind count" and saves (F01).
2. During the shift, in the open session, the employee sees the Expected column empty; in the detail they
   see the float and "—" in Expected, Sales, Refunds, Cash in, Cash out and Comps, and in the list of
   movements only the cash in and out recorded by hand: neither the sales, nor the voids, nor the refunds,
   so there is nothing to add up the expected cash with (Square and Lightspeed hide the expected cash the
   same way in the blind close). The manager, the owner and the administrator see everything: the table,
   the detail, the list and the close window.
3. The cashier counts (F06) and closes (F09) without seeing the expected cash.
4. On closing, expected, counted and difference appear for everyone.
In: the "Blind count" setting and the permission to see the expected cash (manager, owner and
administrator).
Out: nothing new; what each one sees changes. The negative balance rule keeps working with the real
expected cash.
If it fails: nothing of its own.
Involved: CASH_REGISTER-F09

### CASH_REGISTER-F08 Review what is still pending before closing
Status: done
Vertical: common
Actor: employee, manager, administrator
Screen: Cash register
Steps:
1. On opening "Close session", "Checking what is still pending…" shows.
2. If something is left, "Shift review" shows each pending thing: "Open checks: N" and their titles
   (Sales), "Kitchen tickets not served: N" and their tables or numbers (Kitchen: to prepare, being
   prepared or ready to serve) and "Prints not out yet: N" and their uses ("Receipts", "Kitchen", "Bar",
   "Labels"; Printing: what waits in the queue and what failed). With nothing pending nothing shows.
3. The first "Close session" does not close: it warns "The shift will be closed anyway. Press again to
   confirm." and the button becomes "Close anyway".
4. The second click closes (F09).
In: the open checks from Sales, the kitchen tickets in progress from Kitchen and the queue of Printing. If
Kitchen or Printing are not on in the business, they have nothing pending.
Out: nothing; it warns, it never prevents.
If it fails: if a reading cannot be done, "What is still pending could not be checked, so this review may
be incomplete."; if the other readings found something, it shows inside the notice and the confirmation
is asked for anyway; if not, it closes with a single click.
Involved: SALE-F17, SALE-F18, KITCHEN-F31, PRINTING-F01

### CASH_REGISTER-F09 Close the shift: expected, counted and difference
Status: done
Vertical: common
Actor: employee, manager, administrator, assistant
Screen: Cash register
Steps:
1. In the row of the open session, tap "Close" (or arrive from a "Closing" count, F06).
2. Type or check the "Counted cash" (it comes from the last closing count of that session; never from an
   opening one); if you may see the expected cash, "Expected in the drawer" and "Difference" show while
   you type. Add "Closing notes" if you want.
3. Tap "Close session" (twice if the shift review warned, F08).
4. "Session S-… closed · expected … · counted … · difference …" shows; the row becomes "Closed" with the
   three amounts fixed for good and "Open session" turns on again.
In: the counted cash and the notes.
Out: the closed session with expected (float + cash sales and cash in − cash out, refunds and voids in
cash; what is charged or recorded by card, transfer or other does not count), counted and difference
(counted − expected: positive is over, negative is short), in the name of whoever closes (announces:
`cash_register.session.closed`). The Sales lines of the shift are copied into the session: whatever
happens afterwards (a void of a sale from yesterday) goes to the open shift, never to this one.
If it fails: "Type the counted cash to close the session." with the field empty (the screen always asks
for it; the required count setting enforces it on the assistant and the API too); if another device
closed it before, "That cash session is closed: a closed session takes no new movements." (two closes at
once: one closes, the other gets this notice). A session closed by mistake is not reopened: another one
is opened with the real cash as its float.
Involved: CASH_REGISTER-F06, F08

### CASH_REGISTER-F10 Close by itself the drawer forgotten at the end of the day
Status: done — the close is applied when opening the next session, and the Hub makes the pass every 5
minutes on its own
Vertical: common
Actor: system
Screen: none
Steps:
1. The administrator turns on "Daily auto-close" and chooses the time (04:00 by default).
2. Every 5 minutes the Hub checks whether the last cut-off in business time has passed and closes the
   session still open from before that cut-off; one opened after the cut-off is not touched. A Hub that
   was stopped during the cut-off closes it as soon as it is back, and so does whoever opens the cash
   register in the morning: the old one closes by itself before the new one opens.
3. In Cash register the session appears "Closed", with "Closed by itself" in the detail, its expected cash
   at the cut-off and Counted and Difference empty.
In: the setting, the time and the business's time zone.
Out: the session closed at the cut-off time, with no count and no person (announces:
`cash_register.session.closed` once per session). While it is still open past the cut-off, its figures
stop at the cut-off and whatever is charged afterwards already shows as "Sale lines in no shift" (F17),
also in the window to open the next one, to count it in its float; it never goes into the old one or the
new one.
If it fails: with the setting off nothing closes. A session past its cut-off takes no movements, counts or
close: "Session S-… was due to close by itself at 04:00: open a new session (this one closes then)." (409
`cash_register.session_auto_close_due`).
Involved: CASH_REGISTER-F17

### CASH_REGISTER-F11 Look up a session and review a discrepancy
Status: done
Vertical: common
Actor: manager, administrator, employee
Screen: Session detail
Steps:
1. In Cash register, tap "Detail" or tap the row of any session, open or closed.
2. Read the summary: who opened and closed, the drawer, the float, the sales by payment method, refunds,
   cash in, cash out, comps apart (they are a cost, not cash), expected, counted, difference and the
   notes.
3. Go over Movements: each sale is named by its document ("Ticket …", "Invoice …"), a refund "Refund of …"
   and a void "Void of …"; a movement recorded by hand shows its concept. And go over Counts.
4. Tap "Back".
In: the chosen session; the number and the document of each sale, from Sales.
Out: nothing; it is read-only.
If it fails: "Could not load the session detail" or the error of each table with "Retry".
Involved: SALE-F28

### CASH_REGISTER-F12 See the cash register on the home panels
Status: done — inside **Cash register**, above the table of sessions (the Hub's Home is the grid of apps,
with no panels; the figures of each app go on its own screen, like those of Sales)
Vertical: common
Actor: manager, administrator, employee
Screen: Cash register
Steps:
1. Open **Cash register**: two cards show above the table.
2. "Current session" shows the "Expected in the drawer" of the open session and its number, and moves by
   itself with every charge and every movement; with no open session, "No open session.".
3. "Recent discrepancies" shows the difference of the last eight closed sessions, from the one closed
   latest to the oldest, with its sign and its cents and a bar as long as the difference: red if short,
   green if over. A session closed by itself, with no count, shows "—".
In: the open session, the closed sessions and the business's currency.
Out: nothing.
If it fails: "The cash figures could not be loaded." with "Retry". With the blind count, whoever cannot
see the expected cash sees "—" (F07). With no closed sessions, "No closed sessions yet.".
Involved: CASH_REGISTER-F07, F09

### CASH_REGISTER-F13 Record in the cash register each payment of a sale
Status: done
Vertical: common
Actor: system
Screen: Cash register, Session detail
Steps:
1. The cashier charges in **Sales & POS → Sell**.
2. Without anyone typing anything, the open session gets a "Sale" line for each payment method of the
   charge: with a split payment, one in cash and another one by card.
3. Each line carries what that payment method covered, not what was handed over: the change has already
   left the drawer.
4. Only the cash ones raise the expected cash; the card, transfer or other ones show in the list and in
   "Card sales" or "Sales with other payment methods". The cost of the comps goes apart, once per sale, to
   "Comps".
In: the charges from Sales (the sale, its payment methods with their type and amount, and the cost of the
comps).
Out: the line in the open session, at once (the screen refreshes by itself with the notice
`sale.sale.completed`). A zero-total sale with no comps leaves nothing; an all-comp one leaves a
zero-amount line with its cost.
If it fails: with no open session, the charge is not lost: it shows in F17.
Involved: SALE-F01, SALE-F02, SALE-F03, SALE-F15

### CASH_REGISTER-F14 Offset a voided sale in the cash register
Status: done
Vertical: common
Actor: system
Screen: Cash register, Session detail
Steps:
1. Someone voids in Sales a sale already charged.
2. The session open at that moment gets a "Void of …" for each payment method of the sale; the cash one
   lowers the expected cash. The line of the sale is not touched.
3. It always goes to the shift open when voiding, even if the sale is from a shift already closed: the
   closed one does not move. Voided in the same shift, the sale and its void offset each other and do not
   count.
In: the voided sale and when it was voided (`sale.sale.voided`).
Out: the void line. Each void is recorded only once.
If it fails: with no open session, the void shows in F17. Voiding corrects nothing fiscal: the ticket
stays issued (SALE-F30).
Involved: SALE-F30

### CASH_REGISTER-F15 Record a refund in the cash register
Status: done
Vertical: common
Actor: system
Screen: Cash register, Session detail
Steps:
1. Someone makes in Sales a refund, total or partial, of a sale from today or from another day.
2. The open session gets a "Refund of …" for each payment method the money goes back through.
3. What counts is how the money goes back, not how it was charged: a card sale refunded in cash lowers
   the expected cash; a cash one refunded to the card does not touch it.
In: the refund with its payment methods and amounts (`sale.sale.refunded`).
Out: the refund line. Each payment method of each refund is recorded only once.
If it fails: with no open session, the refund shows in F17.
Involved: SALE-F31

### CASH_REGISTER-F16 Print the session report (X or Z)
Status: done
Vertical: common
Actor: manager, administrator, employee
Screen: Session detail
Steps:
1. In the detail of a session, tap "Print".
2. With **Printing** on and an active receipt printer, the report goes to its queue and "Report sent to
   the printer …" shows (or "Report sent to the receipt printer." if none is chosen); the device with that
   printer prints it on paper. With the session open it is the "Partial report (X)"; closed, the "Cash
   closing (Z)".
3. The paper carries the session number with its X or its Z, who opened it (X) or closed it (Z; "Closed by
   itself" if it closed by itself), the float, the expected cash and, line by line, the sales by payment
   method, refunds, cash in, cash out, comps, the expected cash and, in the Z, the counted cash and the
   discrepancy.
4. With Printing not on or with no active receipt printer, the browser's print dialog shows with the same
   report (in the queue it would wait forever).
In: the summary of the session, the same one the screen shows.
Out: a job in the receipt queue of Printing (or the browser's paper). Each "Print" is a new paper.
If it fails: "Could not print." with the reason from Printing (for example, no permission to print). With
the blind count, whoever cannot see the expected cash does not see "Print" in an open session (the report
carries the expected cash); in a closed one they do.
Involved: CASH_REGISTER-F11, PRINTING-F17

### CASH_REGISTER-F17 See the sale lines in no shift
Status: done
Vertical: common
Actor: employee, manager, administrator
Screen: Cash register
Steps:
1. In Cash register, "Sale lines in no shift: N sale lines fell in no session · … in cash" shows when a
   line from Sales fell in no shift:
   - with the cash register closed: what was charged, voided or refunded since the last shift, with no
     open session;
   - with a session forgotten past its cut-off (F10): what came after the cut-off;
   - with a session open: the stragglers of the previous shift, confirmed while it was being closed (its Z
     no longer picks them up).
2. Tap "View" to see the list (when, type, amount, method and document).
3. When opening the session, count that cash in the float: it is already in the drawer (the opening window
   reminds you).
In: the charges, voids and refunds from Sales that fell in no session.
Out: nothing; it warns. With "Turn on the cash register" off there are no shifts to keep and it does not
warn.
If it fails: nothing of its own.
Involved: CASH_REGISTER-F04, F10, F13

## Services: what goes in and what comes out

Everything can be asked for through the screens, the assistant (by voice or by text, with the person's own
session) and the API, with the same rules and the same permissions. Designed for voice: a session is named
by its number ("S-261014-0001") and, if it is not said which one, the open one is meant ("close the cash
register", "record a cash out of €20"); a drawer, by its name.

### What it offers: queries (they read and change nothing)

| What it gives | Who can | Flows | Service |
|---|---|---|---|
| The cash register settings (the default ones if they were never saved) | view sessions | F01 | `cash_register.settings.get` |
| The drawers, with search by name, an active filter and pages (up to 100) | view sessions | F02, F03 | `cash_register.register.list` |
| The sessions, from the most recent to the oldest (or by when they were closed), with search by number, filters (status, number, drawer, dates and amounts) and pages | view sessions | F03, F09, F12 | `cash_register.session.list` |
| The open session with its expected cash (if whoever asks may see it), whether the cash register is turned on and the sale lines in no shift (how many and their cash) | view sessions | F04, F10, F12, F17 | `cash_register.session.current` |
| A session (by id or number) with its summary: sales by payment method, refunds, cash in, cash out, comps, expected, counted and difference | view sessions | F11, F16 | `cash_register.session.get` |
| The movements of a session (or the sale lines in no shift), with search, filters and pages; with the blind count, to whoever cannot see the expected cash, only those recorded by hand in the open session | view movements | F07, F11, F17 | `cash_register.movement.list` |
| The counts of a session, with pages | view counts | F06, F09, F11 | `cash_register.count.list` |
| The business's currency, its decimals and its notes and coins | view sessions | F06, F12 | `cash_register.currency.get` |

All of them can be followed live.

### What it offers: actions (they change data)

| What it does | Who can | Flows | Service |
|---|---|---|---|
| Saves the settings (only what is sent) | settings | F01 | `cash_register.settings.update` |
| Adds a drawer | settings | F02 | `cash_register.register.create` |
| Changes the name of a drawer or deactivates and reactivates it | settings | F02 | `cash_register.register.update` |
| Opens a session with its float | open | F03, F10 | `cash_register.session.open` |
| Closes a session with the counted cash | close | F09 | `cash_register.session.close` |
| Closes the sessions forgotten at the cut-off of the day | close | F10 | `cash_register.session.auto_close` |
| Records cash in or cash out | record | F05 | `cash_register.movement.add` |
| Registers a count | count | F06 | `cash_register.count.add` |
| Prints the X or Z report of a session on the receipt printer | view sessions | F16 | `cash_register.session.print` |

### What it announces

| Notice | When | What it carries | Service |
|---|---|---|---|
| Settings saved | Saving the settings | Which fields changed | `cash_register.settings.updated` |
| New drawer | Adding a drawer | Which one | `cash_register.register.created` |
| Drawer changed | Renaming, deactivating or activating it | Which one | `cash_register.register.updated` |
| Session opened | Opening | The session, its number, the float and who | `cash_register.session.opened` |
| Session closed | Closing (by hand or by itself) | The session, its number, expected, counted, difference and whether it closed by itself | `cash_register.session.closed` |
| Movement recorded | Recording cash in or cash out | The session, the type, the amount and the method | `cash_register.movement.added` |
| Count registered | Registering a count | The session, the type and the total | `cash_register.count.added` |

### What it reacts to

To nothing: it needs nobody's notices. It reads the lines of Sales from Sales, its requirement, at the
moment they are looked at; the screens refresh with `sale.sale.completed`, `sale.sale.voided` and
`sale.sale.refunded`.

### What it needs from other apps

- **Sales & POS** (requirement): the charges, the voids (the voided sale and when) and the refunds, read
  from Sales; the open checks for the shift review.
- **Kitchen** (no requirement; only if it is on): the kitchen tickets in progress for the shift review
  (KITCHEN-F31).
- **Printing** (no requirement; only if it is on): what waits or failed in the queue, for the shift review
  (PRINTING-F01), and the receipt queue for the X or Z report (PRINTING-F17).
- **Indexes of Sales for these readings** (done, `sale/0005_cash_register_indexes`): partial ones on
  `sale_sale(voided_at)` and `sale_refund(created_at)`, so that the readings of voids and refunds by time
  window do not go through the whole table.

### Contract with Sales (CASH_REGISTER-F04)

Cash register cannot touch Sales, and Sales does not require Cash register (it would be a cycle). The
block on charging in cash with the cash register closed is done by Sales like this (done; tested against
this app with real sales):

1. Before charging with a cash-type method, Sales calls the operation
   `cash_register.session.current` by its name (`live.operations.get`; CLAUDE.md "Apps": the operations
   of another app by name, with its permission and its active app), with the session of whoever charges.
2. If the answer carries `required: true` and `session: null`, it refuses the charge with 409
   `sale.cash_register_closed` ("The cash register is closed: open a cash session to charge in cash.").
   Only cash: card, transfer and others always charge.
3. If Cash register is off in the Hub or the call fails, Sales charges anyway (the block gives way rather
   than stopping the sales).
4. The Sell screen is not replaced: the refusal is read at the charge, with a button that takes you to
   **Cash register** to open the session.

What Sales says about this is in its WORKBOOK (SALE-F08). What is charged in cash with no shift because
Cash register was off or did not answer is seen in CASH_REGISTER-F17.

### Who uses it

| App | What for | Service |
|---|---|---|
| Sales & POS | Knowing whether it can charge in cash (F04) | `cash_register.session.current` |

### Who can do what

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| View sessions, settings, drawers and currency | yes | yes | yes | yes | `cash_register.view_session` |
| Open a session | yes | yes | yes | yes | `cash_register.add_session` |
| Close a session | yes | yes | yes | yes | `cash_register.close_session` |
| View movements | yes | yes | yes | yes | `cash_register.view_movement` |
| Record cash in and cash out | yes | yes | yes | yes | `cash_register.add_movement` |
| View counts | yes | yes | yes | yes | `cash_register.view_count` |
| Register counts | yes | yes | yes | yes | `cash_register.add_count` |
| See the expected cash with the blind count | yes | yes | yes | no | `cash_register.view_expected_totals` |
| Settings and drawers | yes | yes | no | no | `cash_register.manage_settings` |

The roles arrive from the SaaS with a prefix (`hub_owner`, `hub_admin`, `hub_manager`, `hub_employee`);
the cashier of the current product is an employee.
