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
<!-- from WORKBOOK.md sha256:7c0a118bc9b7 -->

1. Online orders turns on **Tables** with it (and, through Tables, **Sales** and **Customers**), and Tables cannot be
   turned off while it is on.
2. In **Tables**, add the zones and the tables of the premises: each table has its QR.
3. Each table gets its code the first time its QR is generated; from then on the same code works until it is
   regenerated.

## Flows
<!-- from WORKBOOK.md sha256:3116455ead1e -->

| ID | Flow | Status |
|---|---|---|
| ONLINE_ORDER-F01 | Generate or regenerate a table's QR | partial — through the API and the assistant; the button on the QR sheet is missing |
| ONLINE_ORDER-F02 | See and print the tables' QR sheet | partial — the list of tables with their code, through the API and the assistant; the sheet is missing |
| ONLINE_ORDER-F03 | The customer opens the menu from their table's QR | not done |
| ONLINE_ORDER-F04 | The customer orders from their table | not done |
| ONLINE_ORDER-F05 | Accept or reject a table's first order | not done |
| ONLINE_ORDER-F06 | The customer sees whether their order was accepted | not done |
| ONLINE_ORDER-F07 | Set up ordering from the table | not done |
| ONLINE_ORDER-F08 | The check says the order is online | not done |

### ONLINE_ORDER-F01 Generate or regenerate a table's QR
<!-- from WORKBOOK.md sha256:bbcf3dd90c94 -->
Status: partial — done through the API and with the assistant; the «Regenerate QR» button of the QR sheet is missing
Actor: owner, administrator or manager; the assistant, with the session of whoever speaks
Screen: none yet (it will come with the tables' QR sheet)
Steps:
1. Choose the table, by its number and, if the number repeats, by its zone («table 4 on the terrace»).
2. Ask to regenerate its QR: the assistant shows its card with the table and warns that the printed QR will stop
   working.
3. On confirming, the table gets a new code: the previous one stops opening the table's page at that moment. A table
   that had no code yet gets its first one.
In: the table, from Tables.
Out: the table's new code, the address of its page and when it was generated; the notice that it was regenerated.
If it fails: nothing changes. The table does not exist or was deleted («That table does not exist in this business.»); the
number repeats across zones and no zone is said (Tables asks for the zone); whoever asks cannot change the tables' QR codes
(«You do not have permission»).
Involved: TABLE-F02, TABLE-F04

### ONLINE_ORDER-F02 See and print the tables' QR sheet
<!-- from WORKBOOK.md sha256:a8cd3b1a0955 -->
Status: partial — the list of tables with their code and their address is read through the API and with the assistant; the sheet printed from the browser is missing
Actor: owner, administrator or manager
Screen: none yet (it will come as the tables' QR sheet)
Steps:
1. Open the list of tables: each with its number, its zone and, if it already has a code, the address of its page
   and when it was generated. The tables come in the floor plan's order (2 before 10).
2. Print the sheet: one QR per table with its number and its zone, to cut out and leave on each table.
In: the tables and their zones, from Tables.
Out: nothing; it only reads.
If it fails: without tables, the list is empty; whoever cannot see the tables' QR codes does not see it («You do not
have permission»).
Involved: TABLE-F02, WEBSITE-F09

### ONLINE_ORDER-F03 The customer opens the menu from their table's QR
<!-- from WORKBOOK.md sha256:e0c1cc2783a4 -->
Status: not done — the table's public page is missing
Actor: customer (no session)
Screen: Table page
Steps:
1. Scans their table's QR with the phone's camera and the table's page opens, with the business's name and the
   table's number.
2. Sees the whole menu: the products on sale that are shown on the menu, with their photo, description, allergens and
   price, the modifiers of each and the menus. What is sold out does not show.
In: the menu (Inventory, Modifiers, Menus) and the business's opening hours (Schedule).
Out: nothing; it only reads.
If it fails: a QR that no longer works (regenerated) shows «This QR is no longer active; please ask the staff for
help.»; with the business closed, the menu shows but says no orders are taken right now.
Involved: ONLINE_ORDER-F01, INVENTORY-F36, SCHEDULE-F02

### ONLINE_ORDER-F04 The customer orders from their table
<!-- from WORKBOOK.md sha256:ab06dc81f225 -->
Status: not done — the order is missing
Actor: customer (no session)
Screen: Table page
Steps:
1. Adds products, with their modifiers, menus, quantity and a note.
2. Taps **Order**.
3. If the table has an open check, the order goes into it and is sent to the kitchen with everything the check had
   not sent yet, also what the waiter had entered at the POS. If not, the order waits until an employee accepts it
   (ONLINE_ORDER-F05).
In: the menu, the table's check (Tables and Sales) and the business's opening hours.
Out: the lines on the table's check and the ticket in the kitchen, or the pending order with its notice.
If it fails: nothing is written. The business is closed; a product sold out while ordering; too many orders in a row
from the same phone or in the business («Try again in a few minutes or ask the staff for help.»); a QR that no longer
works.
Involved: ONLINE_ORDER-F05, SALE-F20, KITCHEN-F05

### ONLINE_ORDER-F05 Accept or reject a table's first order
<!-- from WORKBOOK.md sha256:6cee11f96c0e -->
Status: not done — the pending order and its notice are missing
Actor: employee, manager, administrator or owner
Screen: Notification centre → Orders to accept
Steps:
1. The notification centre shows «Orders to accept» with each pending order: the table, what it asks for and when.
2. Tap **Accept**: the table's check opens, the lines go in and are sent to the kitchen; or tap **Reject** and the
   customer sees it on their page.
3. Once the check is charged or voided, that table's next order waits again.
In: the pending order.
Out: the table's check with its lines and the ticket, or the rejected order.
If it fails: another employee already decided it («This order has already been decided.»).
Involved: ONLINE_ORDER-F04, TABLE-F10, TABLE-F18

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
<!-- from WORKBOOK.md sha256:3bbbf26d99cf -->
Status: not done — the settings are missing
Actor: owner or administrator
Screen: Settings
Steps:
1. Turn on or off «Accept the first order of each table» (on by default). Off, every order goes in on its own and
   opens the table's check if there is none.
2. Tap **Save**.
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
<!-- from WORKBOOK.md sha256:b1d234af79e4 -->

Everything can be asked for through the API and the assistant (by voice or text, with the session of whoever
speaks), with the same rules and permissions; the screens will come with the QR sheet. A table is named by its id or
as a person says it: its number and, if it repeats, its zone.

### What it offers: queries
<!-- from WORKBOOK.md sha256:3310f0dd2146 -->

| What it gives | Who can | Flows | Service |
|---|---|---|---|
| The tables in the floor plan's order, each with its zone and, if it already has one, its code, the address of its page and when it was generated, in pages (up to 100) | see the tables' QR codes (+ see tables) | F02 | `online_order.qr_code.list` |

### What it offers: actions
<!-- from WORKBOOK.md sha256:6fd3529a003d -->

| What it does | Who can | Flows | Service |
|---|---|---|---|
| Gives a table a new code; the previous one stops working at once | regenerate the tables' QR codes (+ see tables) | F01 | `online_order.qr_code.regenerate` |

Regenerating is **high risk** for the assistant: the printed QR stops working and it cannot be undone, so its card
asks for confirmation before doing it.

### What it announces
<!-- from WORKBOOK.md sha256:5585cdb52d23 -->

| Notice | When | What it carries |
|---|---|---|
| `online_order.qr_code.regenerated` | A table's code is generated or regenerated | The table (`table_id`); never the code |

### What it reacts to
<!-- from WORKBOOK.md sha256:2d292dad27bb -->

No notice of another app.

### Who can do what
<!-- from WORKBOOK.md sha256:72def8cbadcc -->

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| See the tables' QR codes | yes | yes | yes | no | `online_order.view_qr_code` |
| Regenerate the tables' QR codes | yes | yes | yes | no | `online_order.change_qr_code` |

Tables are read by Tables with the permission of whoever asks: this app's permission **and** the one to see tables
are needed.
