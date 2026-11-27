## What it is for and who it is for
<!-- from WORKBOOK.md sha256:fe2d2d29a74b -->

Online orders lets the customer sitting at a table order on their own from their phone: they scan their table's QR,
see the menu and order, and the order reaches the table's check and the kitchen. Payment does not change: it is taken
at the POS as always.

### In detail
<!-- from WORKBOOK.md sha256:22dee05ec0fa -->

- **Every table has its own QR**, with a code nobody can guess. The QR is printed once and left on the table; it does
  not expire or change on its own.
- **Regenerating a table's QR** gives it a new code: the printed QR stops working at that moment and the new one has
  to be printed. It is for when someone has taken a photo of the QR and orders from outside, or when the paper got
  lost.
- **The customer orders without an account or an installed app**: they open their table's page with the phone's
  camera, see the menu (photos, description, allergens, modifiers and menus) and send their order.
- **Orders are only taken while the business is open**, by the opening hours of Schedule.
- **If the table already has an open check**, the order goes into it and on to the kitchen. If not, the first order
  waits for an employee to accept or reject it from the notification centre, unless the business turns off «Accept
  the first order of each table».
- The check is charged at the POS like any other.

### Who uses it and what each one does
<!-- from WORKBOOK.md sha256:dbbf7a81d3b8 -->

- The **owner**, the **administrator** and the **manager** see each table's code and regenerate it.
- The **employee** does not see the tables' codes.
- The **assistant** (by voice or text, with the session of whoever speaks) does the same: «which tables already have
  their ordering QR code?», «regenerate the QR code of table 4 on the terrace». Before regenerating it asks for confirmation with its
  card, which names the table by its number and its zone, as the floor plan names it.

## Reference adopted
<!-- from WORKBOOK.md sha256:e6cabd78c9b0 -->

**Odoo, Square, Toast, Lightspeed, Qamarero, Last.app, SumUp and GloriaFood** (table and links in «Market
decisions»): a fixed QR per table with an identifier impossible to guess, ordering only while the business is open,
and an employee accepting the first order of a table without an open check (Qamarero's «open table», the manual
acceptance of Lightspeed and Toast). Nobody rotates the printed QR over time or uses the phone's location, which asks
for permission and fails indoors; generating a table's QR again is the way out when one should no longer work.

## Before you start
<!-- from WORKBOOK.md sha256:d5b3a5c83295 -->

1. Online orders turns on **Tables** with it (and, through Tables, **Sales** and **Customers**) and **Inventory**, and
   they cannot be turned off while it is on. With **Modifiers** and **Menus** on, the menu also shows each dish's
   modifiers and the set menus.
2. In **Tables**, add the zones and the tables of the premises: each table has its QR.
3. Each table gets its code the first time its QR is generated; from then on the same code works until it is
   regenerated.
4. In **Inventory**, the table's menu shows the products on sale that have "Show on the menu" on, like the Website's
   menu, with their photo, description, allergens and category.

## Screens
<!-- from WORKBOOK.md sha256:cc240824c00d -->

The **Online orders** menu has one tab: **QR codes**. Only those who can see the tables' QR codes see it (the
owner, the administrator and the manager); the buttons to generate and regenerate, only those who can regenerate them.
The **Table page** is not in the menu: it is the one each table's QR opens on the customer's phone, with no account or
session.

### QR codes
<!-- from WORKBOOK.md sha256:7e72bfa0c2af -->
Here you have every table of the venue, in the floor plan's order, each with the address its QR opens and when it was
generated. From here you print the sheet with each table's QR to cut out and leave on it, you print the QR of a single
table and, if a QR should no longer work, you regenerate it.

#### Details
<!-- from WORKBOOK.md sha256:0ac3b4e0a268 -->
Menu **Online orders → QR codes**. List: Table, Zone ("No zone" if it has none), Address and Generated ("No QR
yet" on a table without a code), in table or card view. At the top, **Print sheet**: it opens the device's print dialog
with one card per table with a QR, three per row, each with "Scan to order", the QR, "Table 4" and its zone, and its
dashed edge to cut it out; in the installed app it goes to its print screen. Per row, **Print QR** (that table only)
and **Regenerate QR**, which asks for confirmation ("Regenerate the QR of table 4 (Terrace)?"), or **Generate QR** on a
table that has none yet. If some tables have no QR, a notice says how many are not on the sheet, with **Generate the
missing QR codes**. The QR is drawn on the device itself: the sheet asks nothing of the internet.

### Table page
<!-- from WORKBOOK.md sha256:731fe33e6666 -->
The one the customer sees on their phone when they scan their table's QR: the business's menu, with the table they are
at above it. From here they build their order and send it to the restaurant.

#### Details
<!-- from WORKBOOK.md sha256:35b5c5f75956 -->
Address `/p/<business>/order/<code>`, with no session, in the phone's language (Spanish or English). At the top, the
business's name and "Table 4 · Terrace" (without a zone, just "Table 4"). Below, **Menus** first, with each set menu's
closed price and its courses ("Starters · Mains · Drink"), and then each Inventory category in its order, with its
dishes sorted by name: the photo (if it has one), the name, the description, "Allergens: Gluten, Milk" and the price.
Dishes without a category go last, under "More dishes". Tapping a dish opens its card with the photo in large, the same
as its row, and each modifier group with how many are chosen ("Optional · up to 2", "Choose 1") and each option with
its allergens and what it adds ("+€0.50"); tapping a set menu opens its dishes, course by course, in the same way. On
the card one ticks what they want from each group (in a group of one, ticking another swaps the one chosen; a full
group leaves the rest waiting; what may be repeated has one less and one more with its count), how many and a note for
the kitchen; **Add · €8.00** puts it in the order, and waits while a group lacks what it asks. Below, **View order (3) ·
€25.50** opens the order: each line with what goes with it, its note and its amount, one less and one more (one less on
a line of one takes it out) and the total; **Send order** sends it to the restaurant. Once sent, the page says "Order
sent: the restaurant will confirm it shortly.". The amounts are the menu's; the restaurant prices the order again when
it arrives.

## States of each screen
<!-- from WORKBOOK.md sha256:abefe6887bfb -->

| Screen | Loading | Empty | Error |
|---|---|---|---|
| QR codes | The list loading; **Print sheet**, off until all the tables are in | "No tables yet", with **Go to Tables** for whoever can add them | The list's, with "Retry"; that of generating or regenerating, in a passing notice with its reason; "The sheet could not be printed." |
| Table page | "Loading the menu…"; on a dish's card, "Loading its options…"; while it is sent, **Send order** waits | "No dishes on the menu yet", with "Ask the staff what you can order."; the order with nothing in it, "Your order is empty" with "Add dishes from the menu." | "The menu could not be loaded." with "Retry"; on the card, "Its options could not be loaded." with "Retry"; a QR that no longer works, "This QR is no longer active" with "Ask the staff for help.", with nothing of the business; a refused order, its reason in the order, which stays to be sent again; without a connection, "No connection. Check it and send the order again." |

"Reconnecting…" while the live connection recovers (what is painted stays).

## Flows
<!-- from WORKBOOK.md sha256:312be6f8c8a7 -->

| ID | Flow | Status |
|---|---|---|
| ONLINE_ORDER-F01 | Generate or regenerate a table's QR | done |
| ONLINE_ORDER-F02 | See and print the tables' QR sheet | done |
| ONLINE_ORDER-F03 | The customer opens the menu from their table's QR | done |
| ONLINE_ORDER-F04 | The customer orders from their table | done |
| ONLINE_ORDER-F05 | Accept or reject a table's first order | not done |
| ONLINE_ORDER-F06 | The customer sees whether their order was accepted | not done |
| ONLINE_ORDER-F07 | Set up ordering from the table | not done |
| ONLINE_ORDER-F08 | The check says the order is online | not done |

### ONLINE_ORDER-F01 Generate or regenerate a table's QR
<!-- from WORKBOOK.md sha256:8ca4c9e30385 -->
Status: done
Actor: owner, administrator or manager; the assistant, with the session of whoever speaks
Screen: QR codes
Steps:
1. Choose the table in **QR codes** or, talking to the assistant, by its number and, if the number repeats, by
   its zone ("table 4 on the terrace").
2. Press **Regenerate QR**: the confirmation names the table and warns that the printed QR stops working at that
   moment. The assistant shows the same on its card.
3. On confirming, the table gets a new code: the previous one stops opening the table's page at that moment, and a
   notice asks to print the new one (**Print QR**, ONLINE_ORDER-F02).
4. A table that has no code yet gets its first one with **Generate QR**, without confirmation, because nothing printed
   stops working; **Generate the missing QR codes** gives one, one after another, to every table that has none yet.
In: the table, from Tables.
Out: the table's new code, the address of its page and when it was generated; the notice that it was regenerated.
If it fails: nothing changes on that table, and the notice says why. The table does not exist or was deleted ("That
table does not exist in this business."); the number repeats across zones and no zone is said (Tables asks for the
zone); whoever asks cannot change the tables' QR codes ("You do not have permission"; on screen the buttons do not
show). **Generate the missing QR codes** stops at the first table that fails: the ones before it already have their
QR.
Involved: TABLE-F02, TABLE-F04

### ONLINE_ORDER-F02 See and print the tables' QR sheet
<!-- from WORKBOOK.md sha256:da167843a9cd -->
Status: done
Actor: owner, administrator or manager; the assistant, with the session of whoever speaks, gives the list
Screen: QR codes
Steps:
1. Open **Online orders → QR codes**: each table with its number, its zone and, if it already has a code, the
   address of its page and when it was generated. The tables come in the floor plan's order (2 before 10).
2. Press **Print sheet**: the device's print dialog brings one QR per table with its number and its zone, to cut out
   and leave on each table. The tables with no QR yet are not on it, and the screen says how many there are.
3. For a single table (the one whose QR was regenerated), **Print QR** on its row brings only its own.
In: the tables and their zones, from Tables.
Out: nothing; it only reads and prints.
If it fails: without tables, "No tables yet", with **Go to Tables**; if the device does not print, "The sheet could not
be printed."; whoever cannot see the tables' QR codes does not see the tab ("You do not have permission" through the
API).
Involved: TABLE-F02, WEBSITE-F09

### ONLINE_ORDER-F03 The customer opens the menu from their table's QR
<!-- from WORKBOOK.md sha256:3121c94b9e9a -->
Status: done
Actor: customer (no session)
Screen: Table page
Steps:
1. Scans their table's QR with the phone's camera and the table's page opens, with the business's name and their table
   with its zone ("Table 4 · Terrace").
2. Sees the whole menu: the set menus and the products on sale that are shown on the menu, by category, with their
   photo, description, allergens and price. What is sold out does not show, nor what the business does not show on its
   menu.
3. Taps a dish and sees its modifiers, how many are chosen from each group and what each one adds; taps a set menu and
   sees its dishes, course by course, with their allergens.
In: the menu (Inventory and, if they are on, Modifiers and Menus) and the table (Tables).
Out: nothing; it only reads. The page shows no costs, stock, taxes or anything about the staff.
If it fails: a QR that no longer works (regenerated, or of a deleted table) shows "This QR is no longer active" with
"Ask the staff for help.", and nothing of the business; with no dishes on sale, "No dishes on the menu yet"; if the
menu does not load, "The menu could not be loaded." with "Retry".
Involved: ONLINE_ORDER-F01, INVENTORY-F36, COMBO-F14

### ONLINE_ORDER-F04 The customer orders from their table
<!-- from WORKBOOK.md sha256:ec80a54eef8d -->
Status: done
Actor: customer (no session)
Screen: Table page
Steps:
1. On their table's menu, taps a dish or a set menu, ticks its modifiers or the dishes of each course, chooses how
   many, writes a note for the kitchen if they want and taps **Add**.
2. Taps **View order**: checks each line and the total, changes how many or takes one out.
3. Taps **Send order**: the order is saved at the restaurant as pending, and the page says "Order sent: the restaurant
   will confirm it shortly.". What happens next is ONLINE_ORDER-F05.
In: the menu (Inventory and, when they are on, Modifiers and Menus) and the table (Tables).
Out: the table's pending order, each dish with its modifiers and each set menu with its dishes at the menu's price, and
its notice.
If it fails: nothing is saved and the order stays on the phone to be sent again. A dish or a set menu no longer on the
menu (sold out, hidden or removed while ordering: "This is no longer on the menu: take it out of your order and send it
again."); a modifier group or a course of the set menu without what it asks, or a dish of the set menu sold out
(Modifiers' or Menus' reason); too many orders in a row from the same table or in the business ("Too many orders in a
row. Try again in a few minutes or ask the staff for help."); a QR that no longer works ("This QR is no longer
active"); without a connection ("No connection. Check it and send the order again.").
Involved: ONLINE_ORDER-F03, ONLINE_ORDER-F05

### ONLINE_ORDER-F05 Accept or reject a table's first order
<!-- from WORKBOOK.md sha256:7995c6552019 -->
Status: not done — the pending order and its notice are missing
Actor: employee, manager, administrator or owner
Screen: Notification centre → Orders to accept
Steps:
1. If the table already has an open check, the order goes into it without waiting and is sent to the kitchen with
   everything the check had not sent yet, also what the waiter had entered at the POS.
2. If not, the notification centre shows «Orders to accept» with each pending order: the table, what it asks for and
   when.
3. Tap **Accept**: the table's check opens, the lines go in and are sent to the kitchen; or tap **Reject** and the
   customer sees it on their page.
4. Once the check is charged or voided, that table's next order waits again.
In: the pending order.
Out: the table's check with its lines and the ticket, or the rejected order.
If it fails: another employee already decided it («This order has already been decided.»).
Involved: ONLINE_ORDER-F04, TABLE-F10, TABLE-F18, SALE-F20, KITCHEN-F05

### ONLINE_ORDER-F06 The customer sees whether their order was accepted
<!-- from WORKBOOK.md sha256:886fd7534cbd -->
Status: not done — the order is missing
Actor: customer (no session)
Screen: Table page
Steps:
1. After ordering, the table's page shows their order as pending, accepted or rejected.
2. It updates on its own when an employee decides it.
In: the order.
Out: nothing; it only reads.
If it fails: a QR that no longer works stops showing the order.
Involved: ONLINE_ORDER-F05

### ONLINE_ORDER-F07 Set up ordering from the table
<!-- from WORKBOOK.md sha256:e9ebc39b4837 -->
Status: not done — the settings and ordering only while the business is open are missing
Actor: owner or administrator
Screen: Settings
Steps:
1. Turn on or off «Accept the first order of each table» (on by default). Off, every order goes in on its own and
   opens the table's check if there is none.
2. Tap **Save**.
3. Outside the hours of Schedule, the table's page still shows the menu, but says no orders are taken right now and
   does not let them be sent.
In: the app's settings and the business's opening hours (Schedule), which say whether orders are taken today.
Out: the saved settings.
If it fails: without the business's opening hours, the settings warn that no orders will be taken until they are set.
Involved: SCHEDULE-F02

### ONLINE_ORDER-F08 The check says the order is online
<!-- from WORKBOOK.md sha256:c90248f64d65 -->
Status: not done — the origin and the channel on the Sales check are missing
Actor: waiter or kitchen
Screen: none of its own (it shows on the Sales check and on the Kitchen ticket)
Steps:
1. A check opened by an order from the table carries the origin «Online order».
2. Its ticket comes out in the kitchen as an order to eat on the premises.
In: the customer's order.
Out: the Sales check with its origin and its channel.
If it fails: does not apply; the order itself sets it.
Involved: SALE-F19, KITCHEN-F05

## Services: what comes in and what goes out
<!-- from WORKBOOK.md sha256:573fa44af031 -->

Everything can be asked for on the screen, through the API and the assistant (by voice or text, with the session of
whoever speaks), with the same rules and permissions. A table is named by its id or as a person says it: its number
and, if it repeats, its zone.

### What it offers: queries
<!-- from WORKBOOK.md sha256:a9427e5e9c59 -->

| What it gives | Who can | Flows | Service |
|---|---|---|---|
| The tables in the floor plan's order, each with its zone and, if it already has one, its code, the address of its page and when it was generated, in pages (up to 100) | see the tables' QR codes (+ see tables) | F02 | `online_order.qr_code.list` |
| The menu of a code's table: the business's name, the table's number and zone, the dishes on sale shown on the menu by category and the set menus with their dishes | anyone with the table's QR, without a session | F03 | `online_order.public.menu` |
| The modifier groups of a dish of that menu, with their options | anyone with the table's QR, without a session | F03 | `online_order.public.options` |

The two of the menu and the sending of the order belong to the table's page: its phone calls them through the Hub's
public door, with the code in the call's body, and they are not tools of the assistant.

### What it offers: actions
<!-- from WORKBOOK.md sha256:3012c402a403 -->

| What it does | Who can | Flows | Service |
|---|---|---|---|
| Gives a table a new code; the previous one stops working at once | regenerate the tables' QR codes (+ see tables) | F01 | `online_order.qr_code.regenerate` |
| Saves as pending the order of the table of a code: each dish with its modifiers and each set menu with its dishes, at the menu's price | anyone with the table's QR, without a session | F04 | `online_order.public.send` |

Regenerating is **high risk** for the assistant: the printed QR stops working and it cannot be undone, so its card
asks for confirmation before doing it.

### What it announces
<!-- from WORKBOOK.md sha256:1a6d8d0bc1de -->

| Notice | When | What it carries |
|---|---|---|
| `online_order.qr_code.regenerated` | A table's code is generated or regenerated | The table (`table_id`); never the code |
| `online_order.order.sent` | A table's order arrives | The order (`order_id`), the table (`table_id`) and its total (`total`) |

### What it reacts to
<!-- from WORKBOOK.md sha256:2d292dad27bb -->

No notice of another app.

### Who can do what
<!-- from WORKBOOK.md sha256:6a67cc4d4780 -->

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| See the tables' QR codes | yes | yes | yes | no | `online_order.view_qr_code` |
| Regenerate the tables' QR codes | yes | yes | yes | no | `online_order.change_qr_code` |
| Open a table's ordering page | yes | yes | no | no | `online_order.public` |

Tables are read by Tables with the permission of whoever asks: this app's permission **and** the one to see tables
are needed. The customer who opens their table's page has no account: the public door serves the page with
`online_order.public` and nothing more.
