## What it is for and who it is for
<!-- from WORKBOOK.md sha256:e383045d4138 -->

Tips keeps **the tip the customer leaves when paying**, by card or in cash, and **whose it is**.
A tip is not a sale: it carries no VAT, does not change the ticket and does not reach the AEAT. It is recorded in
the Sales charge itself, with one tap (a suggested percentage, another amount or "keep the change"), goes into the
cash register if it is in cash and is paid later to whoever it belongs to. It serves both businesses:

- In the **restaurant**, the tip belongs to the waiter who serves the table or, if the business decides so, goes
  into a pool shared among the floor, the bar and the kitchen by clocked hours or by points.
- In the **hair salon**, the tip belongs to the professional who served the client.

Who uses it:

- The **employee** who charges: records the tip when charging or afterwards on the ticket, and sees their own.
- The **manager**: also adjusts or voids a tip, defines the distribution, approves it and pays out the
  tips, and sees the report of the whole team.
- The **owner** and the **administrator**: everything, plus the settings.

Tips does not charge (that is Sales), does not balance the cash register (that is Cash register: Tips records
in it what comes in and goes out) and does not do payroll.

## Reference adopted
<!-- from WORKBOOK.md sha256:2254761acdba -->

ERPlora does not invent flows: it adopts the ones the market has already proven (consulted on 2026-11-14).

- **The tip is recorded at the charge, with suggestions and another amount.** Square (in Spain) offers three
  suggestions, "custom amount" and "no tip", in fixed amounts for small bills and in percentages
  for large ones ([Square — settle payments and manage tips](https://squareup.com/help/es/es/article/8375-settle-payments-and-manage-tips));
  Shopify POS, up to three suggestions and a free amount ([Shopify — tips at the POS](https://help.shopify.com/manual/sell-in-person/transactions/tips));
  Odoo, the "Tip" button of the payment screen ([Odoo — tips](https://www.odoo.com/documentation/17.0/applications/sales/point_of_sale/restaurant/tips.html));
  Lightspeed, "Add tip" at payment ([Lightspeed K-Series — tips](https://k-series-support.lightspeedhq.com/hc/articles/4415116773403)).
- **Suggestions by payment method**: Revo XEF asks for a tip depending on the payment method and, since its version
  5.0, suggests tips per method ([Revo — payment methods](https://support.revo.works/es/articles/66),
  [Revo XEF 5.0](https://support.revoxef.works/es/articles/1096)); Ágora lets you set the suggested tip
  when charging by card ([Ágora Payments](https://www.agorapos.com/agora-payments/)).
- **The change, as a tip, if the employee confirms it**: Revo "turns the change into a tip" (also "with
  confirmation"), SumUp offers "Use for tip" when what was paid exceeds the bill
  ([SumUp — tips management](https://help.sumup.com/en-GB/pos/articles/75000112645-tips-management)) and
  Lightspeed works out the tip from what was tendered.
- **The tip belongs to whoever serves or charges**: Square attributes it to whoever processes the payment and, by
  default, "each employee keeps the ones they receive"
  ([Square — tip out team members](https://squareup.com/help/es/es/article/8141-tip-out-team-members-with-square-for-restaurants));
  Toast, to whoever holds the check ([Toast — how Toast handles tips](https://support.toasttab.com/en/article/How-Toast-Handles-and-Distributes-Tips));
  SumUp and Lightspeed, to whoever charges. The pool and the distribution among roles are **optional** (Square and
  Toast turn them on by hand; Toast with its Tips Manager).
- **The cash tip that does not go through the POS is declared when closing the shift**, with a warning if it is low,
  as in Toast ([Toast — declaring cash tips](https://support.toasttab.com/en/article/Declaring-Cash-Tips)).
- **The cash register counts the tip apart**: SumUp puts it in the X and the Z report; Square gives, in the shift
  report, the card tips and the cash owed to the staff
  ([Square — shift report](https://squareup.com/help/es/es/article/8140-run-shift-report-with-square-for-restaurants)).
  And paying out in cash the tips charged by card is recorded as a cash out, or the drawer looks short: it is
  the repeated complaint in the Square forums
  ([Square community — tips and the till](https://community.squareup.com/t5/Archived-Discussions-Read-Only/How-do-I-track-cash-in-my-till-and-pay-out-and-account-for-tips/td-p/2511/page/3))
  and in the Toast ones ([Toast community — deposits and end-of-night tips](https://community.toasttab.com/t5/back-office-team/server-bartender-tip-logs-and-end-of-night-deposits/m-p/3863)).
- **In Spain people leave little**: 63 % of those who tip leave less than 5 % of the bill, 35 % between 5 and
  10 % and only 2 % more (TheFork Lab, in
  [Finantres](https://finantresnoticias.com/negocios-y-autonomos/propina-se-enfria-en-restaurantes-dato-deben-mirar-pequenos-negocios/)).
  Hence the default suggestions: 3 %, 5 % and 10 %.
- **A voluntary tip carries no VAT** (see "Why the tip is not on the ticket" in "For whoever
  maintains it"): [Garrigues — how tips are taxed](https://www.garrigues.com/es_ES/noticia/como-tributan-las-propinas)
  and Ágora's blog ([should we declare tips?](https://www.agorapos.com/blog/debemos-declarar-las-propinas/)).

## Before you start
<!-- from WORKBOOK.md sha256:30c7d764fa51 -->

- **Sales & POS**, **Cash register** and **Staff** are turned on with Tips: the tip goes with its sale, the cash one
  goes into the cash register and it belongs to a person of the team.
- **Settings**: by default, tips are **off** (as in Square, SumUp, Revo or Odoo). They are turned on in
  **Tips → Settings** (TIP-F01).
- **Who serves**: the tip belongs to the person of the check's "Served by" chip (SALE-F16); with "Me", to whoever
  charges. For it to count for someone, that person has to have a record in Staff.
- **Currency**: the business's, with its decimals; a percentage is rounded to the smallest unit of the currency
  (the cent in euros, the whole yen in Japan), half up.

Initial setup, step by step:

1. As administrator, open **Tips → Settings**, turn on "Ask for a tip when charging" and review the
   suggestions of each payment method (TIP-F01).
2. If the business shares out the tips, define the distribution in **Tips → Distribution** (TIP-F08, TIP-F09) and
   look at its preview (TIP-F10). Without a distribution, each tip belongs to whoever served.
3. Make a test charge with a card tip and another one in cash, and check the tip lines in **Cash register**
   (CASH_REGISTER-F18) and, in **Tips**, that they carry the name of whoever served.

## Screens
<!-- from WORKBOOK.md sha256:cbfa55a11cc6 -->

Tips opens from the **Tips** menu and has four entries: **Tips**, **Distribution**, **Report** and
**Settings**. Whoever cannot manage sees only **My tips**.

### "Tip" step in the Charge
<!-- from WORKBOOK.md sha256:dcaa00b16a69 -->
Inside the Sales **Charge** sheet (SALE-F39), only with tips turned on: the "Tip" row with
the three suggestions of the chosen payment method ("3 %", "5 %", "10 %", each with its amount below),
"Other amount" and "No tip"; the one marked by default is "No tip". Below, "For <name>" (whoever
serves). In cash, when what is tendered exceeds the total, the "Keep the change" button. With a tip
set, the big amount says "<total> + <tip> tip".

### Tips
<!-- from WORKBOOK.md sha256:328f530e757a -->
Title "Tips", period ("Today", "7 days", "30 days"), table (Date, Sale, For, Payment method, Amount,
Status) with the search "Search sale or person…", filters (person, payment method, status), table or
card view, 50 per page. **+** "Record tip" and, per row, "Adjust" and "Void" (only while its day is not
distributed). At the top, "Declare shift tips" (TIP-F07). Empty: "No tips yet."; loading:
"Loading tips…".

### Distribution
<!-- from WORKBOOK.md sha256:dfe9877e73a2 -->
The distribution rules (TIP-F08, TIP-F09), one card per rule, with "Preview" (TIP-F10) and, below, the
days and services to approve with "Approve" (TIP-F11) and the approved ones with "Pay" (TIP-F12). Without rules:
"No distribution: each tip belongs to whoever served.".

### Report
<!-- from WORKBOOK.md sha256:4b5061e307bf -->
By person or by shift (TIP-F13): card, cash and declared tips, what they put into the pool and what
they received, paid and pending. Export as CSV.

### My tips
<!-- from WORKBOOK.md sha256:d458d6b48777 -->
The person's own, today's and this week's (TIP-F14), with what is paid and what is pending.

### Settings
<!-- from WORKBOOK.md sha256:84b2cb16920f -->
"Ask for a tip when charging" and, for each active payment method, its three suggestions (each one in "%" or as
an amount), which one comes marked, "Allow other amount" and "Save".

## States of each screen
<!-- from WORKBOOK.md sha256:16a45fbb24f4 -->

| State | What the person sees |
|---|---|
| Loading | "Loading…" (or its screen's text) while the first result arrives. |
| Empty | Its screen's text, with **+** if they can record. |
| Error | The notice with "Retry"; the refusal of an action shows inside its window, next to its field. |
| Reconnecting | What is drawn stays; a strip warns "Reconnecting…" until the connection is back. |
| App inactive | "Tips is not active in this business."; the **Charge** sheet does not paint the step. |
| No permission | What they cannot do does not show; if they get there another way, "You do not have permission". |

## Flows
<!-- from WORKBOOK.md sha256:6a1beadd61ad -->

| ID | Flow | Vertical | Status |
|---|---|---|---|
| TIP-F01 | Set up tips | common | partial — the Settings screen is missing |
| TIP-F02 | Suggest the tip when charging | common | not done |
| TIP-F03 | Record a card tip | common | partial — the Charge and the Tips screen are missing |
| TIP-F04 | Record a cash tip | common | partial — the Charge and the Tips screen are missing |
| TIP-F05 | Put a tip with no ticket into the pool | restaurant | partial — the Tips screen is missing |
| TIP-F06 | Adjust or void a tip | common | partial — the Tips screen is missing |
| TIP-F07 | Declare the cash tips when closing the shift | restaurant | not done |
| TIP-F08 | Define the distribution | restaurant | not done |
| TIP-F09 | Share with another role (tip-out) | restaurant | not done |
| TIP-F10 | See the distribution preview | restaurant | not done |
| TIP-F11 | Approve the distribution of a day or service | restaurant | not done |
| TIP-F12 | Pay out the tips | common | not done |
| TIP-F13 | See the report by person and by shift | common | not done |
| TIP-F14 | See my tips | common | not done |

### TIP-F01 Set up tips
<!-- from WORKBOOK.md sha256:92522ec6f4ea -->
Status: partial — the settings are read and saved through the API and the assistant; the Settings screen is missing (hub#1498)
Vertical: common
Actor: owner, administrator, assistant
Screen: Settings
Steps:
1. Open **Tips → Settings** and turn on "Ask for a tip when charging".
2. In each active payment method (Cash, Card, Bizum…) review its three suggestions: each one is a
   percentage ("5 %") or an amount ("€2.00"). By default, 3 %, 5 % and 10 % in all of them.
3. Choose which one comes marked when the charge opens (by default, "No tip") and whether "Other amount" is allowed.
4. Press "Save". "Settings saved." shows.
In: the payment methods of Sales.
Out: the settings; the next charge already uses them. The percentage is worked out on the check's total before
discounts, as in Toast, and rounded to the currency's unit.
If it fails: an empty, zero or negative suggestion, or one over 100 %, is said below its field and nothing is
saved; two equal suggestions in the same payment method, "That suggestion is already there.". Without permission,
the screen shows locked with "You do not have permission to change these settings.".
Involved: SALE-F37

### TIP-F02 Suggest the tip when charging
<!-- from WORKBOOK.md sha256:b6ac4ccc4a7d -->
Status: not done — Tips does not declare its step on the Charge sheet yet (hub#1498, hub#1500)
Vertical: common
Actor: employee, manager
Screen: Charge
Steps:
1. With tips turned on, press "Charge · <total>": the **Charge** sheet shows the "Tip" row with the
   suggestions of the chosen payment method and their amount below.
2. Tap the one the customer says, or "Other amount" and type the amount, or "No tip". Changing the payment method
   changes the suggestions and keeps the chosen one if it is an amount.
3. The big amount becomes "<total> + <tip> tip" and the button, "Charge <total + tip>".
4. Charge as always (SALE-F01, F02): by card, TIP-F03; in cash, TIP-F04. With "Split the payment"
   (SALE-F03), the row shows for each payment and each one carries its own tip.
In: the check's total, the payment method and whoever serves (SALE-F16).
Out: the sale, the same as without a tip, and the tip saved with its sale, its payment method, its amount and the
person it belongs to (announces: `tip.tip.added`).
If it fails: a negative or unreadable amount is said below its field and it does not charge. If the sale is charged
and the tip is not saved (the network drops), the sheet says "The sale is charged, but the tip has not been
saved." with "Retry"; the retry does not duplicate it, and it can also be recorded afterwards (TIP-F03, TIP-F04).
When whoever serves has no record in Staff, the tip is saved as "Unassigned" and goes into the distribution or is
assigned when it is adjusted (TIP-F06).
Involved: SALE-F39, SALE-F16, CASH_REGISTER-F18

### TIP-F03 Record a card tip
<!-- from WORKBOOK.md sha256:d36d271cbbfc -->
Status: partial — a card tip is recorded on its sale through the API and the assistant and shows apart in the cash
register; recording it at the Charge and on the Tips screen is missing (hub#1498, hub#1500)
Vertical: common
Actor: employee, manager, assistant
Screen: Charge, Tips
Steps:
1. In the card charge, with the tip chosen, the sheet says "Charge <total + tip> on the card terminal, then
   confirm.": the card terminal charges the bill and the tip together.
2. If the customer adds it on the card terminal afterwards (or it was forgotten at the charge), in **Tips** press
   **+** "Record tip", choose the sale by its number, "Card" and the amount the card terminal charged on top, and
   "Save".
In: the sale and what the card terminal charged on top (ERPlora does not talk to the card terminal).
Out: the card tip. In the open cash session it shows as "Tips by card", without touching the expected cash
(CASH_REGISTER-F18).
If it fails: recording it on a voided or fully refunded sale, "That sale is voided: it does not accept a tip."; on
a sale of a day already distributed, "That day is already distributed: reopen it to add tips." (TIP-F11).
Involved: CASH_REGISTER-F18

### TIP-F04 Record a cash tip
<!-- from WORKBOOK.md sha256:9b9c6a93331b -->
Status: partial — a cash tip is recorded on its sale through the API and the assistant and goes into the drawer;
"Keep the change" at the Charge and the Tips screen are missing (hub#1498, hub#1500)
Vertical: common
Actor: employee, manager, assistant
Screen: Charge, Tips
Steps:
1. In the cash charge with a tip, what is tendered has to cover the total plus the tip; the change is what is
   tendered minus both.
2. Or, with no tip chosen, enter what is tendered: if there is some left over, "Keep the change" shows. Press it if
   the customer leaves the change: the tip is the change and the change stays at 0.
3. After the charge, in **Tips**, **+** "Record tip", the sale, "Cash" and the amount.
In: the sale, what is tendered and the tip.
Out: the cash tip, which goes into the drawer: in the open cash session it shows as "Tips in cash" and raises
the expected cash (CASH_REGISTER-F18).
If it fails: with "Turn on the cash register" on and the cash register closed, "The cash register is closed: open a
cash session to record a cash tip."; when what is tendered does not cover the total plus the tip, "The amount
tendered does not cover the total and the tip".
Involved: SALE-F01, CASH_REGISTER-F18

### TIP-F05 Put a tip with no ticket into the pool
<!-- from WORKBOOK.md sha256:e918cceb2aac -->
Status: partial — the pool is recorded through the API and the assistant and goes into the drawer; the Tips screen is
missing (hub#1498)
Vertical: restaurant
Actor: manager
Screen: Tips
Steps:
1. At the end of the service, count the bar's tip jar and, in **Tips**, press **+** "Record tip" and choose
   "Into the pool, no ticket".
2. Type the amount and press "Save".
In: the amount in cash.
Out: a tip with no sale and no person, of the open shift, which goes into the drawer (CASH_REGISTER-F18) and is
shared out with the day's rules (TIP-F08); without rules, it stays "Unassigned" until it is assigned (TIP-F06).
If it fails: with the cash register closed, the same notice as in TIP-F04.
Involved: TIP-F08, CASH_REGISTER-F18

### TIP-F06 Adjust or void a tip
<!-- from WORKBOOK.md sha256:be1e67ef0a75 -->
Status: partial — adjusting and voiding go through the API and the assistant, and voiding or refunding the whole sale
voids its tip by itself; the Tips screen is missing (hub#1498)
Vertical: common
Actor: manager, assistant
Screen: Tips
Steps:
1. In the tip's row, press "Adjust": change the amount or the person and write the "Reason".
2. Or press "Void", write the "Reason" and confirm.
3. Voiding or fully refunding a sale voids its tip by itself: the customer gets back what they paid, tip included.
   A refund of only some lines does not touch it.
In: the tip, the new amount or person and the reason; the voids and refunds of Sales.
Out: the tip adjusted or voided, with who, when and why (announces: `tip.tip.adjusted`, `tip.tip.voided`).
In the open cash session, the difference comes in or goes out in its payment method (CASH_REGISTER-F18): a session
already closed is never touched.
If it fails: with no reason, "Write the reason."; with the day already distributed, "That day is already
distributed: reopen it to change its tips.".
Involved: SALE-F30, SALE-F31, CASH_REGISTER-F18

### TIP-F07 Declare the cash tips when closing the shift
<!-- from WORKBOOK.md sha256:425c3afc39c5 -->
Status: not done — it comes with the distribution (hub#1501)
Vertical: restaurant
Actor: employee
Screen: Tips
Steps:
1. Before clocking out, in **Tips** press "Declare shift tips".
2. Write the cash tips you received in hand (those that did not go through the POS) and what you gave to other
   roles, and press "Declare".
3. If what is declared falls below the minimum percentage of your cash sales that the business sets, a
   warning shows, which does not stop you from declaring.
In: the clocked working day (ATTENDANCE-F01) and that person's cash sales in the shift.
Out: the shift's declaration (announces: `tip.declaration.added`); it counts in the report and in the
distribution, but does not go into the cash register: that money did not go through the drawer.
If it fails: without a clocked working day that day, "You have no clocked working day today."; a negative amount
is said below its field.
Involved: ATTENDANCE-F01

### TIP-F08 Define the distribution
<!-- from WORKBOOK.md sha256:c676d1d01895 -->
Status: not done — it comes with the distribution (hub#1501)
Vertical: restaurant
Actor: manager, administrator
Screen: Distribution
Steps:
1. In **Tips → Distribution**, press **+** "New rule".
2. Choose the roles that contribute and those that receive (the Staff roles), which part of each source goes into
   the pool (card, cash, pool), how it is shared among roles (points or %) and among people (by clocked hours or
   in equal parts), and how often: day, service (lunch, dinner) or ticket.
3. Press "Save".
In: the Staff roles (STAFF-F04) and the clock-ins (ATTENDANCE-F01).
Out: the rule (announces: `tip.rule.created`, `tip.rule.updated`, `tip.rule.deleted`); it applies from that
moment on, never backwards.
If it fails: a rule whose percentages do not add up to 100, "The percentages have to add up to 100."; a role that
contributes and receives at the same time in the same rule, "A role cannot contribute and receive in the same
rule.".
Involved: STAFF-F04, ATTENDANCE-F01

### TIP-F09 Share with another role (tip-out)
<!-- from WORKBOOK.md sha256:9169caa3339f -->
Status: not done — it comes with the distribution (hub#1501)
Vertical: restaurant
Actor: manager, administrator
Screen: Distribution
Steps:
1. In a rule, press "Add a tip-out to another role".
2. Choose the role that gives (waiter), the one that receives (kitchen or bar) and what it gives: a % of its sales
   or of its tips. Press "Save".
In: the sales and the tips of each person of the role that gives.
Out: the rule with its tip-out to another role, which goes into the preview and into the day's distribution.
If it fails: a % over 100 or a negative one is said below its field.
Involved: TIP-F08

### TIP-F10 See the distribution preview
<!-- from WORKBOOK.md sha256:655362e814b7 -->
Status: not done — it comes with the distribution (hub#1501)
Vertical: restaurant
Actor: manager, administrator
Screen: Distribution
Steps:
1. In a rule, press "Preview" and choose a recent day.
2. It shows, per person, what they contributed and what they would receive with that rule, without saving anything.
In: the rule and the day's tips, sales and clock-ins.
Out: nothing; it shows.
If it fails: a day with no tips, "That day has no tips.".
Involved: TIP-F08

### TIP-F11 Approve the distribution of a day or service
<!-- from WORKBOOK.md sha256:03c076fd3380 -->
Status: not done — it comes with the distribution (hub#1501)
Vertical: restaurant
Actor: manager, administrator, assistant
Screen: Distribution
Steps:
1. In **Distribution**, on the day or service to approve, review each person's share and press "Approve".
2. To correct something of an approved day, press "Reopen", correct it and approve it again.
In: the day's tips, declarations, sales and clock-ins and the rules in force that day.
Out: each person's share, fixed (announces: `tip.pool.settled`, `tip.pool.reopened`). Without rules, each tip
already belongs to whoever served and there is nothing to approve.
If it fails: with a clock-in of that day open or pending review, "Some working days of that day are not closed or
are pending review: correct them in Time clock before approving." (ATTENDANCE-F05, ATTENDANCE-F08); a day with tips
already paid out is not reopened: "That day already has tips paid out.".
Involved: ATTENDANCE-F05, ATTENDANCE-F08

### TIP-F12 Pay out the tips
<!-- from WORKBOOK.md sha256:50ccb73e0d0c -->
Status: not done — it comes with the distribution (hub#1501)
Vertical: common
Actor: manager, administrator, assistant
Screen: Distribution, Report
Steps:
1. On a person's pending amount, press "Pay".
2. Choose "In cash, from the cash register" or "Another way" (bank transfer, payroll) and confirm.
In: that person's pending amount (approved or, without a distribution, their own tips).
Out: the payout (announces: `tip.payout.paid`). In cash, it leaves the drawer as "Tips paid out" and lowers the
expected cash (CASH_REGISTER-F18), so that the cash register does not come out unbalanced.
If it fails: in cash with the cash register closed, "The cash register is closed: open a cash session to pay in
cash."; a payout that would leave the cash register negative when that is not allowed, the Cash register notice
(CASH_REGISTER-F05); paying more than what is pending, "You cannot pay more than what is pending.".
Involved: CASH_REGISTER-F05, CASH_REGISTER-F18

### TIP-F13 See the report by person and by shift
<!-- from WORKBOOK.md sha256:a84ebea0920a -->
Status: not done — the report and "My tips" are missing (hub#1498)
Vertical: common
Actor: manager, administrator
Screen: Report
Steps:
1. In **Tips → Report**, choose the period and "By person" or "By shift" (the clocked working day).
2. It shows, per person: card, cash and declared tips, what they put in and received in the distribution,
   what is paid and what is pending. "Export" downloads it as CSV.
In: tips, declarations, distributions, payouts and working days.
Out: nothing; it shows.
If it fails: the loading error with "Retry".
Involved: ATTENDANCE-F01

### TIP-F14 See my tips
<!-- from WORKBOOK.md sha256:8472fd231be5 -->
Status: not done — the report and "My tips" are missing (hub#1498)
Vertical: common
Actor: employee
Screen: My tips
Steps:
1. Open **Tips** (whoever does not manage sees **My tips** straight away).
2. They see their own, today's and this week's, by payment method, what they received from the distribution, what
   is paid and what is pending.
In: the tips and payouts of their Staff record.
Out: nothing; it shows.
If it fails: without a linked Staff record, "Your user is not linked to any Staff record: ask a manager to link it
in Staff.".
Involved: STAFF-F03

## Services: what goes in and what comes out
<!-- from WORKBOOK.md sha256:dca180ea2f2f -->

Everything can be asked for through the screens, the assistant (by voice or by text) and the API, with the same
rules and the same permissions. A tip is named by its sale ("the tip of 20261114-0007") and a person, by their
name.

### What it offers: queries (they read, they change nothing)
<!-- from WORKBOOK.md sha256:b8a5335b486a -->

| What it gives | Who can | Flows | Service |
|---|---|---|---|
| The tips settings | view tips | F01, F02 | `tip.settings.get` |
| The suggestions for a charge: total, payment method and its amount | record | F02 | `tip.suggestion.get` |
| The tips, with search, filters and pages | view tips | F03–F06 | `tip.tip.list` |
| One tip, by its id or by its sale's number (the active one) | view tips | F06 | `tip.tip.get` |
| The distribution rules | manage | F08, F09 | `tip.policy.get` |
| The distribution preview of a day | manage | F10 | `tip.policy.preview` |
| The report by person and by shift | manage | F13 | `tip.report.by_employee`, `tip.report.by_shift` |
| The own tips of whoever asks | view tips | F14 | `tip.report.mine` |

### What it offers: actions (they change data)
<!-- from WORKBOOK.md sha256:d38b06cf1026 -->

| What it does | Who can | Flows | Service |
|---|---|---|---|
| Saves the settings | settings | F01 | `tip.settings.update` |
| Records a tip (of a sale or into the pool) | record | F02–F05 | `tip.tip.add` |
| Adjusts a tip | manage | F06 | `tip.tip.update` |
| Voids a tip | manage | F06 | `tip.tip.void` |
| Declares the shift's cash tips | record | F07 | `tip.declaration.add` |
| Creates, changes or deletes a distribution rule | manage | F08, F09 | `tip.rule.create`, `tip.rule.update`, `tip.rule.delete` |
| Approves or reopens a day's distribution | manage | F11 | `tip.pool.settle`, `tip.pool.reopen` |
| Pays out a person's pending amount | manage | F12 | `tip.payout.add` |

`tip.pool.settle` and `tip.payout.add` are high risk: the assistant shows the full preview before
confirming.

### What it announces
<!-- from WORKBOOK.md sha256:046ef8541eff -->

| Notice | When | What it carries | Service |
|---|---|---|---|
| Settings saved | Saving the settings | What changed | `tip.settings.updated` |
| Tip recorded | Recording it | The sale, the person, the payment method and the amount | `tip.tip.added` |
| Tip adjusted or voided | Adjusting or voiding it | What it was, what it is now and the reason | `tip.tip.adjusted`, `tip.tip.voided` |
| Tips declared | Declaring | The person, the shift and the amounts | `tip.declaration.added` |
| Rule created, changed or deleted | Changing the distribution | The rule | `tip.rule.created`, `tip.rule.updated`, `tip.rule.deleted` |
| Distribution approved or reopened | Approving or reopening | The day or service and each person's share | `tip.pool.settled`, `tip.pool.reopened` |
| Tips paid out | Paying | The person, the amount and the way | `tip.payout.paid` |

### What it reacts to
<!-- from WORKBOOK.md sha256:d68b27d362b9 -->

- `sale.sale.voided` and `sale.sale.refunded` (full refund): voids that sale's tip (F06).
- `attendance.record.clocked_out` and `attendance.record.corrected`: the distribution and report screens
  refresh by themselves.

### What it needs from other apps
<!-- from WORKBOOK.md sha256:55c9ec68b856 -->

- **Sales & POS** (requirement): the tip's sale, who served and its payment methods; the **Charge** sheet paints
  the "Tip" step because Tips declares it (SALE-F39), without Sales knowing about tips.
- **Cash register** (requirement): records in the open session what comes in and goes out in tips
  (`cash_register.movement.add`, CASH_REGISTER-F18).
- **Staff** (requirement): the people and their role, to know whose each tip is and to share out by role.
- **Time clock**: the clocked hours, for the distribution by hours and the report by shift; it is turned on with Tips
  when the distribution and the report arrive.

### Who can do what
<!-- from WORKBOOK.md sha256:307405264216 -->

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| View tips (the employee, only their own) | yes | yes | yes | yes | `tip.view_tip` |
| Record and declare | yes | yes | yes | yes | `tip.add_tip` |
| Adjust, void, distribution, approve, pay out and report | yes | yes | yes | no | `tip.manage` |
| Settings | yes | yes | no | no | `tip.manage_settings` |
