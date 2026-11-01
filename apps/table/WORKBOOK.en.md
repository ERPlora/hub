<!-- generated from WORKBOOK.md sha256:87ae36b4eef9ac46c0343d99f15cf986db941331103d193167c62b143a455493 -->

## What it is for and who it is for

Tables is the **floor plan of the restaurant or bar**: the zones of the room (dining room, terrace,
bar), the tables of each zone with their capacity, their shape and their spot on the plan, and the
**checks seated at each table**. It says, live, which table is free, occupied, reserved or out of
service, how many guests there are, since when and who serves them, and it knows which Sales check is at
which table.

Who uses it:

- The floor **manager** draws the plan: creates zones and tables, places them by dragging them and
  changes their capacity, their shape or their status.
- The **administrator** and the **owner**, besides, delete tables, zones and checks from the history and
  change the room settings.
- The **employee** (server, cashier) seats people, moves a check to another table, joins or splits
  checks, corrects the guests, takes the table away from a check and closes a table by hand.

Tables does not charge (that is Sales: the table takes you to the till with its check), does not take
bookings (that is Reservations: Tables only sets the table aside on the plan) and is not the kitchen
screen.

## Reference adopted

ERPlora does not invent flows: it adopts the ones the market has already proven.

- **Zones, tables placed on a plan, guests per table and occupancy in sight**, with the time a check has
  been open in amber and in red:
  [Square — floor plans](https://squareup.com/help/us/en/article/6427-building-your-floor-plan).
- **Several checks at one table** (split); the lines are shared out by Sales:
  [Lightspeed — splitting a bill](https://resto-support.lightspeedhq.com/hc/en-us/articles/226405708-Splitting-a-bill),
  [Square — split by item](https://squareup.com/help/gb/en/article/8421-new-order-and-pay-capabilities-with-square-for-restaurants).
- **Asking for the guests when seating, transferring and joining checks, taking a table out of service**
  and the list of closed checks with their amount (Toast and Lightspeed).
- **A table with its check open is not freed by hand**: it is charged, moved to another table or the
  check is deleted (Toast, Square, Lightspeed and Odoo; tables#124 of the current product).
- **Seating at a reserved table is allowed and spends the booking; going over the capacity warns but does
  not prevent it.**
- **A reserved table is painted Reserved only close to the time of its booking** (market decision on
  question 1 of the current product). Before that the table stays Available and shows the next booking
  with its time. This is how they do it:

  | Product | How it solves it | Source |
  |---|---|---|
  | Toast Tables | The service floor plan shows on each table the time of its next booking | [support.toasttab.com](https://support.toasttab.com/en/article/Using-Toast-Tables-Waitlist?lang=en_US) |
  | TouchBistro Reservations | The table's status (reserved or occupied) is that of the time slot being looked at, in 15-minute steps | [TouchBistro — list and floor plan](https://cdn.touchbistro.com/help/articles/reservations-ipad-app-using-the-reservation-list-and-floorplan) |
  | Tablein | The table with the next booking beyond the length of a booking carries a "Next" label and stays free | [help.tablein.com](https://help.tablein.com/floor-plan) |
  | TablesReady | The table changes colour when the assigned booking is near and the party has not arrived | [support.tablesready.com](https://support.tablesready.com/article/155-how-to-use-table-management) |
  | Lightspeed K-Series | The booking has statuses (Scheduled, Seated…) and is assigned to a table of the plan | [k-series-support](https://k-series-support.lightspeedhq.com/hc/en-us/articles/37718296880411-Understanding-the-settings-for-reservation-integrations) |
  | Odoo (table booking module) | The plan marks the tables with a booking in the current service window and warns before seating someone else | [ecosire.com](https://ecosire.com/apps/odoo/pos-restaurant-table-reservation) |
  | Square for Restaurants | The table's status follows that of the integrated OpenTable booking | [squareup.com](https://squareup.com/gb/en/point-of-sale/restaurants/features/table-management-system) |
  | Tabit | The table's upcoming bookings can be seen from it | [support-us.tabit.cloud](https://support-us.tabit.cloud/hc/en-us/article_attachments/4408025435794) |

  **Wins:** Reserved from **60 minutes before** the booking's time until its window ends; before that,
  the table stays Available with "Ana · 21:00". **Why not the old way** (Reserved from the moment it is
  confirmed, even a week ahead): it blocked the table the whole service and a party seated at noon
  "spent" the evening's booking.
- **A deactivated table or zone leaves service** (decision on question 7): it is not painted on the
  service plan and cannot be seated; it stays in "Edit plan", in **Tables** and in **Zones**, like
  [Lightspeed — deactivating a table](https://k-series-support.lightspeedhq.com/hc/articles/1260804656729),
  [Toast — removing a table from the service area](https://support.toasttab.com/article/Creating-Service-Areas-and-Table-Setup-1493049150430)
  and the Active / Inactive status of the floor plans of [Poster](https://knowledge-base.joinposter.com/en/how-to-edit-a-table-layout-or-hide-the-floor-plan)
  and [MultiPOS](https://docs.devdiggers.com/multipos-point-of-sale-for-woocommerce/configuration/tables/).

## Before you start

- Tables needs **Sales** (the check of each table is an open check of Sales) and **Customers** (the
  customer of a table and forgetting their name). They are switched on with it and are not switched off
  while Tables is on.
- The times (opening, closing, bookings) are the business's: in this phase, **Europe/Madrid**.

Initial setup, step by step:

1. In **Tables → Zones** (or with the "+" of the **Floor plan**) create the zones of the room (TABLE-F01).
2. In **Tables → Floor plan**, in "Edit plan", add the tables of each zone with the "+" (TABLE-F02).
   Until a table is in use, the Home reminds you with "Your tables".
3. Drag them until the plan looks like the room and set the capacity and the shape of each one
   (TABLE-F03, TABLE-F04).
4. In **Tables → Settings** (the administrator only) decide whether the guests are asked when seating
   and after how many minutes an open check turns amber and red (TABLE-F08).
5. In **Floor plan**, "Service", tap a free table and seat it: its check opens in Sales.

## Screens

The **Tables** menu has five tabs: **Floor plan**, **Zones**, **Tables**, **Sessions** and
**Settings** (this one only for whoever can change them). No other one is hidden by permission; the
buttons the profile cannot use do not show.

### Floor plan
Menu **Tables → Floor plan**. At the top, a single row: the strip of zones (it slides sideways on the
phone and fades out at the edge when there are more zones), the **Service / Edit plan** switch (only for
whoever can draw the plan) and, in "Edit plan", a "+" ("Add zone or table") and a pencil ("Edit zone").
Below, the plan of the chosen zone, with the tables at their real size: if it does not fit in width
(phone, tablet) it slides sideways and the edge with tables behind fades out; if it does not fit in
height, it grows and the page scrolls down.

Each table is a tile with its number, its status written with its icon and colour (Available, Occupied,
Reserved, Blocked), the capacity ("4 pax") or, if it is occupied, the guests and the minutes they have
been there ("3 pax · 35 min", which move forward by themselves) and who serves it; if it has a booking
today, the name and the time of the booking ("Deleted customer" if that customer's data were erased) on
one line: a name that does not fit is cut with "…" and the time is always seen whole ("Maximiliana F… ·
20:00"); the full name goes in the table's title. Round tables are painted round and the rectangular
one, wider than tall. The plan **is live**: it changes by itself when somebody seats, charges, moves or
edits a table.

- **Service** (at first): nothing is dragged. Tapping a table opens its **Table N** window:
  - free or reserved: the guests question ("Guests at table N · 4 pax", "−" and "+", shortcuts from 1
    to 8 that seat in one tap, the warning "Above the table capacity (4)" and "Seat N"), and the
    optional customer ("Assign customer"). With the guests setting off, "Seat" seats with the capacity
    (or the booking's guests).
  - occupied: guests, since when, who serves, the check's customer (assign or remove) and the actions
    **Charge** (takes you to the till with the check), **Transfer**, **Merge**, **Split check**,
    **Guests**, **Remove table** and **Close table**. With two checks at the table, which one is chosen
    first ("Check 1", "Check 2").
  - blocked: "Table out of service: it cannot be seated until it is unblocked.".
  - Transfer and Merge put the plan in destination mode: "Transfer N to…" / "Pick a free table" (or
    "Merge N with…" / "Pick an occupied table") and "Cancel"; only the tables that are valid can be
    tapped.
- **Edit plan**: each table is dragged to its spot (also with the keyboard: arrows, 8 px; with Shift,
  32 px) and it is saved when it is dropped. Tapping a table opens **Edit table** (Number, Capacity,
  Name (optional), Shape, Status (Available or Blocked), Zone, Active; footer with "Delete" and "Save");
  the "+" opens **Add** (Zone field and "Add zone"; "Table number" field, which if left empty is
  "Auto-numbered", and "Add table"); the pencil opens **Edit zone** (Name, Description (optional);
  "Delete zone" and "Save"). Below, the help "Drag to position · click a table to edit or delete it.
  Changes are saved instantly.". In "Edit plan" the deactivated tables and zones are also seen, in grey.

The windows cover the whole screen on the phone and are centred on tablet and computer.

### Zones
Menu **Tables → Zones**. Table: Name (with its colour), Tables, Free ("free / total"), Order, Status
(Active, Inactive); search box "Search zone…", column filters behind the funnel, table or cards view.
The "+" (only for whoever can create zones) opens the panel with Name, Description, Colour (Blue, Cyan,
Purple, Green, Amber, Red, Grey), Order and "Add zone"; per row "Edit" (the same panel with the
"Active" switch and "Save changes") and "Delete" (the administrator only), which asks for confirmation
in "Delete zone?" and leaves "Delete zone" off if the zone has tables.

### Tables
Menu **Tables → Tables**. Table in natural order (2 before 10): Number, Name, Zone, Capacity, Status;
search box "Search table…" (number and name), column filters behind the funnel (zone, status, shape,
capacity), table or cards view. The "+" opens the panel with Number, Capacity, Zone and "Add table".
Per row, "Edit" (Number, Name, Capacity, Shape, Zone, Status and Active) and "Delete" (the
administrator only, with confirmation).

### Sessions
Menu **Tables → Sessions**: the checks of the room. Tabs "Open", "Closed" and "All". Table: Table ("No
table (parked)" if it has none), Charged and Closed (they do not show in Open), Zone, Server, Guests,
Opened, Time, Status (Open, Closed, Transferred, Merged, Parked); the time of an open check turns amber
and red according to the Settings. Search box "Search table…", filters behind the funnel by zone, server
and status. Per row "Details" (window with zone, server, status, guests, opening, closing, time, charged
and notes), on the open ones "Close session" (with confirmation), on the parked ones "Seat again" (pick
the free table) and, on the finished ones, "Delete" (the administrator only). The times are in the
business's time. What was charged goes in the currency it was charged in: the business's (its country's,
with its decimals), never in euros if the business charges in another.

### Settings
Menu **Tables → Settings**: "Ask for the guests when seating a table", "Amber warning (minutes)" and
"Red warning (minutes)", and "Save". Only whoever can change them sees it (by default, the owner and the
administrator).

## States of each screen

| Screen | Loading | Empty | Error |
|---|---|---|---|
| Floor plan | "Loading…" | No zones: "Create a zone to start placing tables."; zone without tables: "No tables in this zone. Tap “Add table”." | On loading: notice with "Retry"; on saving, inside the open window (or above the plan if there is none) |
| Zones | The table loading | "No zones. Tap «+» to create the first one (Dining room, Terrace, Bar…)." | The table's, with "Retry"; the saving one, inside the panel |
| Tables | The table loading | "No tables." | The table's, with "Retry"; the saving one, inside the panel |
| Sessions | The table loading | "No sessions. Seat a party from the floor plan and it will show up here." | The table's, with "Retry"; the closing one, in its confirmation |
| Settings | "Loading…" | — | Per field (422) and above the form |

In all of them: "Reconnecting…" while the live connection is recovered (what is drawn stays), "This app
is not active in this business" and "You do not have permission".

## Flows

| ID | Flow | Status |
|---|---|---|
| TABLE-F01 | Create and order the zones of the room | done |
| TABLE-F02 | Add tables | done |
| TABLE-F03 | Place the tables on the plan | done |
| TABLE-F04 | Edit or delete a table | done |
| TABLE-F05 | Take a table out of service (block it) and bring it back | done |
| TABLE-F06 | Rename or delete a zone | done |
| TABLE-F07 | Create many tables at once | done |
| TABLE-F08 | Set up the room: guests when seating and time warnings | done |
| TABLE-F09 | See how the room is | done |
| TABLE-F10 | Seat a party at a free or reserved table | done |
| TABLE-F11 | Go back to an occupied table and charge it | done |
| TABLE-F12 | Take a check that is already open to a table | done |
| TABLE-F13 | Take the table away from a check (park it) | done |
| TABLE-F14 | Correct the guests of an occupied table | done |
| TABLE-F15 | Move the check to another table (transfer) | done |
| TABLE-F16 | Join the checks of two occupied tables (merge) | done |
| TABLE-F17 | Split the check of a table | done |
| TABLE-F18 | Free the table when the whole check is charged | done |
| TABLE-F19 | Void a charge of a table | done |
| TABLE-F20 | Delete the open check of a table in Sales | done |
| TABLE-F21 | Close a table by hand | done |
| TABLE-F22 | Look up the checks of the room (open and closed) | done |
| TABLE-F23 | Delete a closed check from the history | done |
| TABLE-F24 | Seat a parked check again | done |
| TABLE-F25 | Hold the table of a confirmed booking | done |
| TABLE-F26 | Move or release the hold when the booking changes | done |
| TABLE-F27 | Release the table when the booking is cancelled or a no-show | done |
| TABLE-F28 | Spend the hold when the booking is seated | done |
| TABLE-F29 | Expire the holds that are due | done |
| TABLE-F30 | Hold or release a table by hand | done |
| TABLE-F31 | Forget the name of a customer whose data are erased (GDPR) | done |
| TABLE-F32 | Put or remove the customer of a table | done |

### TABLE-F01 Create and order the zones of the room
Status: done
Actor: manager, administrator
Screen: Zones
Steps:
1. In **Tables → Zones** tap "+".
2. Type the Name (Dining room, Terrace, Bar…), choose the Colour and the Order (the next one comes filled in).
3. Tap "Add zone".
4. The zone shows in the list with 0 tables and, in that order, as a tab of the **Floor plan**. It is
   also created from the "+" of the plan in "Edit plan" (Zone field and "Add zone"): it goes last and
   stays chosen.
In: the name, the description, the colour and the order.
Out: the zone (announces: `table.zone.created`).
If it fails: without a name, the button does not turn on. A name another zone already has: "There is
already a zone with that name.". An employee does not see the "+"; if they ask for it through the API,
it is refused for lack of permission.
Involved: TABLE-F06, TABLE-F09

### TABLE-F02 Add tables
Status: done
Actor: manager, administrator
Screen: Home, Floor plan (Edit plan), Tables
Steps:
1. On the **Home**, while no table is in use, "Finish setting up your business" brings "Your tables"
   ("Add the tables of your dining room: without them there is no order per table, no split and no
   transfer."), "Recommended", to whoever may create tables. "Set up" leads to **Tables → Tables**
   (step 6).
2. In **Floor plan → Edit plan**, choose the zone and tap "+".
3. In "Table number" type the number or name (S1, Terrace A) or leave it empty: "Auto-numbered", with
   the first free number of that zone.
4. Tap "Add table" (off while there is no zone).
5. The table appears in the zone, in the first free spot, square, for 4 and Available.
6. Another door: in **Tables → Tables**, "+" with Number, Capacity and Zone and "Add table"; it is also
   born in the first free spot of its zone.
In: number (or none), and in the list also capacity and zone.
Out: the table (announces: `table.table.created`). With a table in use, "Choose table" of the till stops
saying "There are no tables yet. Set them up in Tables → Floor plan." (`table.floor.status`), and "Your
tables" is "Done" on the Home without a reload. An occupied or blocked table still counts; if they are
all switched off or deleted (TABLE-F04), the step goes back to pending by itself. A zone without tables
does not tick it.
If it fails: a number repeated in the zone (regardless of case and spaces), through any door: "There is
already a table with that number in this zone.". A zone deleted in the meantime: "That zone does not
exist in this business.".
Involved: TABLE-F03, TABLE-F04, TABLE-F07, BASE-F01

### TABLE-F03 Place the tables on the plan
Status: done
Actor: manager, administrator
Screen: Floor plan (Edit plan)
Steps:
1. In **Floor plan → Edit plan**, choose the zone.
2. Drag each table to its spot (only the table catches the gesture; sliding over the empty plan scrolls
   it). With the keyboard: tab to the table and move it with the arrows (8 px; with Shift, 32 px).
3. When it is dropped it is saved at once. The table does not leave the edge of the plan.
4. On reloading, each table is still where it was left.
In: the new position.
Out: the table's position (announces: `table.table.updated`).
If it fails: "Could not save the position" above the plan; the table goes back to its saved spot.
Involved: TABLE-F02, TABLE-F09

### TABLE-F04 Edit or delete a table
Status: done
Actor: manager, administrator
Screen: Floor plan (Edit plan), Tables
Steps:
1. In **Edit plan**, tap the table (or in **Tables**, "Edit" in its row): "Edit table" opens.
2. Change Number, Capacity, Name (optional), Shape (Square, Round, Rectangular), Status (Available or
   Blocked), Zone or Active.
3. Tap "Save": the window closes and the plan changes by itself (if it changed zone, it appears in the
   other tab in the same spot).
4. To remove it, tap "Delete" (the administrator only) and confirm it: it disappears from the plan and
   from the list; its history of checks is kept.
In: the chosen table.
Out: the changed table (announces: `table.table.updated`) or the deleted one (announces:
`table.table.deleted`).
If it fails: inside the window: "The table number is required", "There is already a table with that
number in this zone.", "That table does not exist in this business."; deleting a table with an open
check: "That table has an open check. Close it or move it before deleting the table.".
Involved: TABLE-F02, TABLE-F05, TABLE-F21

### TABLE-F05 Take a table out of service (block it) and bring it back
Status: done
Actor: manager, administrator
Screen: Floor plan (Edit plan), Tables
Steps:
1. Open "Edit table" and in "Status" choose "Blocked"; tap "Save".
2. The table shows Blocked (grey) on the plan and cannot be seated: "Table out of service: it cannot be
   seated until it is unblocked.".
3. To bring it back, set "Available" and save.
4. Blocking an occupied table does not touch its check: it stays Occupied until it is charged and then
   it stays Blocked. A booking does not paint a Blocked table Reserved.
In: the chosen table.
Out: the table's status (announces: `table.table.updated`).
If it fails: as in TABLE-F04. Seating at a blocked table (assistant, API) is refused for the same
reason.
Involved: TABLE-F04, TABLE-F10, TABLE-F25

### TABLE-F06 Rename or delete a zone
Status: done
Actor: manager, administrator
Screen: Zones, Floor plan (Edit plan)
Steps:
1. In **Tables → Zones**, "Edit": change Name, Description, Colour, Order or "Active" and tap "Save
   changes". On the plan, the pencil ("Edit zone") changes Name and Description.
2. To delete it (the administrator only): "Delete" opens "Delete zone?" with "N tables in this zone. A
   zone with tables cannot be deleted: move or delete its tables first." (with just one, "1 table in
   this zone. … move or delete it first."); with tables, "Delete zone" comes out off.
3. Without tables, "Delete zone" removes it from the list and from the plan.
In: the chosen zone.
Out: the changed zone (announces: `table.zone.updated`) or the deleted one (announces:
`table.zone.deleted`).
If it fails: "That zone still has tables. Move them to another zone or delete them first." or "That zone
does not exist in this business.".
Involved: TABLE-F01, TABLE-F04

### TABLE-F07 Create many tables at once
Status: done
Actor: manager, assistant
Screen: assistant and API (the current product had no screen for this either)
Steps:
1. Ask the assistant "create 12 tables on the Terrace, from T1 to T12, for 4".
2. They are created at once (from 1 to 100), numbered with the prefix and the starting number that are
   said (1 if not), with the capacity (4) and the shape (square) that are said, in the first free spots
   of the zone.
In: zone (by id or by name), how many, prefix, starting number, capacity and shape.
Out: the tables (announces: `table.table.created`).
If it fails: if the zone does not exist, none is created. If any number already exists in the zone,
none is created and it says which ones.
Involved: TABLE-F02

### TABLE-F08 Set up the room: guests when seating and time warnings
Status: done
Actor: administrator
Screen: Settings
Steps:
1. In **Tables → Settings**, tick or untick "Ask for the guests when seating a table".
2. Set "Amber warning (minutes)" and "Red warning (minutes)" (from 1 to 600; the red one cannot be lower
   than the amber one).
3. Tap "Save".
4. Unticked, tapping a free table seats it with its capacity (with the booking's guests if it is
   Reserved). In **Sessions**, the time of an open check turns amber and red from those minutes. Without
   ever saving: it asks, 60 and 90 minutes.
In: the three values.
Out: the room settings (announces: `table.settings.updated`).
If it fails: a value out of range shows in its field.
Involved: TABLE-F10, TABLE-F22

### TABLE-F09 See how the room is
Status: done
Actor: manager, employee
Screen: Floor plan
Steps:
1. Open **Tables → Floor plan** and choose the zone: its plan shows at once, without waiting to load.
   All its tables in use are seen, at their real size.
2. Each table says its status in writing, with icon and colour: Available, Occupied, Reserved or Blocked.
3. An occupied table says the guests and the minutes they have been there ("3 pax · 35 min") and who
   serves it; the minutes move forward by themselves. A table with a booking today says the name and the
   time.
4. The plan changes by itself when somebody seats, transfers, joins, splits, charges or voids: there is
   no need to leave and come back, and the window you have open (split, guests, close, "Edit table")
   stays at the step you were at, with whatever you typed. And with the clock: a table turns Reserved an hour before its booking and goes back to
   Available when the booking ends, without anybody touching anything.
In: the tables, their open checks, their holds and the status of their checks in Sales.
Out: nothing.
If it fails: a failure on loading shows with "Retry".
Involved: TABLE-F10, TABLE-F25, TABLE-F29, SALE-F19

### TABLE-F10 Seat a party at a free or reserved table
Status: done
Actor: employee, manager
Screen: Floor plan (Service)
Steps:
1. In **Floor plan → Service**, tap an Available or Reserved table. "Guests at table N" is asked, with
   the capacity (or the booking's guests) already set.
2. Tap a shortcut from 1 to 8 (it seats in one tap) or adjust with "−" and "+" and tap "Seat N". More
   than the capacity warns "Above the table capacity (4)" and lets you seat. With the guests setting
   off, "Seat" seats with the capacity.
3. If you want, before seating "Assign customer" puts the card on the check (TABLE-F32).
4. The table turns Occupied and its open check is born in Sales with the title "Table N" (**Open
   checks** of the till sees it). Whoever seats is the server of the check.
In: the table and the guests; on a Reserved one, the booking's guests.
Out: the table check opened with its guests, the time and the server (announces:
`table.session.opened`); its check in Sales (announces: `sale.order.opened`); the bookings held at that
table that were already Reserved, spent (TABLE-F28; from Reservations, only that booking's).
If it fails: if another device has just taken it, "Another device has just taken that table. The floor
plan has been refreshed." and the table is not seated. **Two servers who seat the same table at the
same time leave a single check**: the second one gets that same warning. A blocked, deactivated or
deleted table is not seated. Seating is done on the floor, with the party in front: an automation
cannot do it.
Involved: TABLE-F08, TABLE-F28, TABLE-F32, SALE-F19, FLOW-F12

### TABLE-F11 Go back to an occupied table and charge it
Status: done
Actor: employee, manager
Screen: Floor plan (Service)
Steps:
1. In **Floor plan → Service**, tap an Occupied table: its window opens with guests ("1 guest", "3
   guests"), since when, server and customer.
2. **Charge** takes you to **Sales → Sell** with that check on screen (`/sale/pos?order=<id>`); there
   rounds are added and it is charged.
3. With two checks at the table (split), the check is chosen first ("Check 1", "Check 2").
In: the tapped table and its open check.
Out: nothing in Tables.
If it fails: if the check was already charged or voided from somewhere else, Sales warns on arrival
"That check is not open any more (charged, voided or gone): the till carries on as it was.".
Involved: TABLE-F18, SALE-F19

### TABLE-F12 Take a check that is already open to a table
Status: done
Actor: employee, manager, assistant
Screen: Sales → Sell ("Choose table", SALE-F19); assistant
Steps:
1. In **Sales → Sell**, with a check on screen (a bar one, with its rounds), tap the table button in the
   check's header ("Assign table"; only with Tables active and permission to seat): "Choose table"
   opens, with a search box and the tables in service in the colour of their status, their seats and,
   if they have it, today's booking ("Marta · 21:00").
2. Tap an Available or Reserved table: the check becomes that table's, with everything it had, and
   takes the title "Table 4". The guests are not asked: the booking's and, if there is none, the table's
   seats. Without a check yet, Tables opens one with the table's title and the till puts it on screen
   (TABLE-F10).
3. The check's header shows its table ("Table 4"), followed live. In the same window, "Remove from
   table" parks it (TABLE-F13), and a parked check is seated again by tapping another table
   (TABLE-F24).
4. With the assistant: "put Ana's check at table 4".
In: the check (open) and the table.
Out: the table check opened and linked to that check (announces: `table.session.opened`).
If it fails: those of TABLE-F10, inside the window and with these words; a check already charged or
voided: "That check is no longer open in Sales."; a check that is already at another table: "That check
is already at table N.". The Occupied and Blocked tables cannot be tapped. Taking a check to a table
is done with the party in front: an automation cannot do it.
Involved: TABLE-F10, TABLE-F13, TABLE-F24, SALE-F19, FLOW-F12

### TABLE-F13 Take the table away from a check (park it)
Status: done
Actor: employee, manager
Screen: Floor plan (Service); also in Sales → Sell, "Choose table" → "Remove from table" (SALE-F19)
Steps:
1. In the window of the occupied table tap "Remove table".
2. The table stays Available for others; the table check turns "Parked", without a table, keeping
   guests, server and time; the check stays open in Sales (**Open checks**).
3. To carry on with it at a table, **Sessions → Seat again** (TABLE-F24).
In: the table check.
Out: the parked check (announces: `table.session.parked`) and the table free if it has no other check
left. If Sales then charges it whole or voids it, the table check stays "Closed" (without a table).
If it fails: "That check is not open: it does not exist in this business, or it has already been
closed, transferred, merged or parked.".
Involved: TABLE-F24, SALE-F19

### TABLE-F14 Correct the guests of an occupied table
Status: done
Actor: employee, manager
Screen: Floor plan (Service)
Steps:
1. In the window of the occupied table tap "Guests".
2. The question comes with the current guests; change them with a shortcut or with "−" / "+" and "Save".
3. The table shows the new guests. On a split table the chosen check is corrected.
In: the open check of the table.
Out: the check's guests (announces: `table.session.updated`).
If it fails: a check already closed, transferred, merged or parked is not corrected (the message of
TABLE-F13). Always at least 1.
Involved: TABLE-F10, TABLE-F17

### TABLE-F15 Move the check to another table (transfer)
Status: done
Actor: employee, manager
Screen: Floor plan (Service)
Steps:
1. In the window of the occupied table tap "Transfer".
2. The plan says "Transfer N to…" and "Pick a free table": only the Available and Reserved ones can be
   tapped. "Cancel" undoes it.
3. Tap the destination table.
4. The check is the same one, now at the destination table, with its guests, its server, its notes, its
   arrival time and its new title in Sales ("Table M"); the origin one stays free if it has no other
   check left, and the destination one, Occupied (if it was Reserved, it spends the booking).
In: the origin check and the destination table.
Out: the origin check "Transferred" and a new table check at the destination with the same Sales check
(announces: `table.session.transferred`).
If it fails: "Another device has just taken that table. The floor plan has been refreshed." if the
destination is no longer free; "That check is not open…" if someone else already moved it.
Involved: TABLE-F28, SALE-F25

### TABLE-F16 Join the checks of two occupied tables (merge)
Status: done
Actor: employee, manager
Screen: Floor plan (Service)
Steps:
1. In the window of the table that is going to be joined tap "Merge".
2. The plan says "Merge N with…" and "Pick an occupied table": only the Occupied ones can be tapped (the
   table itself only if it has another check: that is how a split is undone).
3. Tap the table that stays.
4. The origin table stays free if it has no other check left and its table check, "Merged". In Sales,
   the uncharged lines of the origin check go to the one of the table that stays and the empty one is
   voided, **in the same operation**: either everything is joined, or nothing is. What the origin check
   had already charged stays in its "Charged". The till that had the origin check on screen (on this
   device or another) moves to the check of the table that stays and says "That check was joined with
   another one: the screen shows the joined check." (SALE-F24).
In: the two checks.
Out: a single open check at the table that stays (announces: `table.session.merged` and
`sale.order.merged`).
If it fails: "That table has no other open check to merge with." if the destination is free or is the
same table without another check.
Involved: TABLE-F17, SALE-F24

### TABLE-F17 Split the check of a table
Status: done
Actor: employee, manager
Screen: Floor plan (Service)
Steps:
1. In the window of the occupied table tap "Split check".
2. Mark the lines that go to the new check (those of its check in Sales, each with its amount in the
   business's currency) and tap "Split". With nothing marked, the new one is born empty.
3. Tables opens a second check at the same table (1 guest) and Sales moves the marked lines to it, in
   the same operation. Charging one closes only that one: the table stays Occupied with the other. It
   can be split even if the table is blocked or deactivated: nobody new is seated.
In: the open check of the table and the lines that move.
Out: two open table checks at the same table, the new one hanging from the original (announces:
`table.session.split` and `sale.order.opened`).
If it fails: if another device is charging that check, Sales refuses it ("The check changed…") and
nothing is split. Splitting is done at the table, with the party in front: an automation cannot do
it.
Involved: TABLE-F16, TABLE-F18, SALE-F23, FLOW-F12

### TABLE-F18 Free the table when the whole check is charged
Status: done
Actor: system
Screen: Sales: Charge
Steps:
1. In Sales the check of a table is charged, whole or in parts.
2. What is charged shows in "Charged" of **Sessions**, also with each partial charge.
3. Charged whole, the table check stays "Closed" and the table free if it has no other open check left;
   on a split table the other check stays seated.
4. With a partial charge the check stays open and the table, Occupied.
In: from Sales, the status of the check and its sales.
Out: the table check "Closed" with the time of the charge; the table free. A sale without a table (bar,
takeaway) leaves nothing.
If it fails: nothing to see: the plan and Sessions read it from Sales on every read.
Involved: TABLE-F17, TABLE-F22, SALE-F22

### TABLE-F19 Void a charge of a table
Status: done
Actor: system
Screen: Sales: Sales
Steps:
1. In Sales, a manager voids a charged sale that belonged to a table.
2. Tables stops counting it in "Charged" ("—" shows if no live charge is left).
3. The table check and the table do not change: voiding a sale neither reopens nor closes the check in
   Sales.
In: from Sales, the voided sale.
Out: nothing new; "Charged" goes down.
If it fails: as TABLE-F18.
Involved: TABLE-F22, SALE-F30

### TABLE-F20 Delete the open check of a table in Sales
Status: done
Actor: manager
Screen: Sales: Open checks
Steps:
1. In **Sales → Open checks** the check of a table is deleted.
2. The table check stays "Closed" and the table free if it has no other check left.
In: from Sales, the voided check.
Out: the table check closed; the table free.
If it fails: as TABLE-F18.
Involved: TABLE-F21, SALE-F18

### TABLE-F21 Close a table by hand
Status: done
Actor: employee, manager
Screen: Sessions, Floor plan (Service)
Steps:
1. In **Tables → Sessions → Open**, "Close session" (or "Close table" in the table's window).
2. Confirm in "Close the session?": "Table N · N guests. The table is freed and the session moves to
   the history. If its bill is still open in Sales, first charge it, move it to another table or delete
   it from the till." (with just one, "1 guest").
3. If its Sales check is empty (nobody ordered anything), Tables voids it and closes the table: a party
   that gets up without ordering does not need a manager.
4. If its check has something ordered, nothing is closed: it is charged (TABLE-F18), moved to another
   table (TABLE-F15) or deleted in Sales (TABLE-F20).
In: the open table check and the status of its check in Sales.
Out: the table check "Closed" with its time (announces: `table.session.closed`).
If it fails: "This table's bill is still open in Sales: charge it, move it to another table or delete it
from the till."; "This table's bill has changed. Reload the list and try again." (another device
changed its check); "That check is not open…" (someone else already closed it).
Involved: TABLE-F18, TABLE-F20

### TABLE-F22 Look up the checks of the room (open and closed)
Status: done
Actor: manager, employee
Screen: Sessions
Steps:
1. Open **Tables → Sessions**: it starts in "Open", the most recent first.
2. "Closed" shows the closed ones with "Charged" (in the currency it was charged in: the business's) and
   "Closed"; "All", also the transferred, merged and parked ones.
3. Filter by zone, server or status, or search by table number.
4. "Details" shows zone, server, status, guests, opening, closing, time, charged and notes.
In: the table checks and what was charged in Sales.
Out: nothing.
If it fails: the table's error with retry. Refunds do not subtract from "Charged".
Involved: TABLE-F18, TABLE-F19, TABLE-F23

### TABLE-F23 Delete a closed check from the history
Status: done
Actor: administrator, assistant
Screen: Sessions
Steps:
1. In **Sessions → Closed** (or **All**), "Delete" on a finished check and confirm it.
2. It disappears from **Sessions**; it stays stored as deleted and its trail through the tables is kept.
In: the table check.
Out: the deleted check (announces: `table.session.deleted`).
If it fails: an open or parked check is not deleted: "That check is still open: close it before
deleting it.".
Involved: TABLE-F22

### TABLE-F24 Seat a parked check again
Status: done
Actor: employee, manager, assistant
Screen: Sessions; also in Sales → Sell, by tapping a table in "Choose table" with the check on screen (SALE-F19)
Steps:
1. In **Sessions → All**, "Seat again" on a parked check and pick a free table.
2. The table check goes back to "Open" at that table, with its guests, its server and its opening time,
   and its Sales check takes the table's title; the table turns Occupied and, if it was Reserved, it
   spends the booking.
In: the parked check and the table.
Out: the seated table check (announces: `table.session.restored`).
If it fails: "That check is not parked: it does not exist in this business, or it is already seated at
a table."; the table has to be free as when seating (TABLE-F10). Seating it again is done with the
party in front: an automation cannot do it.
Involved: TABLE-F13, TABLE-F28, SALE-F19, FLOW-F12

### TABLE-F25 Hold the table of a confirmed booking
Status: done
Actor: system
Screen: none (it is seen on the Floor plan)
Steps:
1. In Reservations, a booking with a table becomes Confirmed (or is born already confirmed).
2. In that same operation, Tables sets that table aside for the booking from its date and time (the business's) until its length
   ends (120 minutes if it brings none), with its guests, its name and its customer card. The night the clocks change the
   length is the real one: a 90-minute booking sets the table aside for 90 minutes, not an hour more nor an hour less. A time
   that repeats (02:30 on the October night) is the first one, still on summer time; one that does not exist (02:30 on the
   March night) becomes 03:30.
3. From 60 minutes before its time the table shows Reserved; before that, Available with "Ana · 21:00".
4. A table can have several bookings held; the plan shows today's earliest.
In: from Reservations, the booking with its table, date, time, length, guests, name and card.
Out: the hold (announces: `table.table.held`). If the confirmation arrives twice, there is still a
single hold.
If it fails: a deleted, deactivated or out-of-service table is not held, and Reservations does not confirm the booking
(everything is undone).
Involved: RESERVATION-F07, TABLE-F09, TABLE-F28

### TABLE-F26 Move or release the hold when the booking changes
Status: done
Actor: system
Screen: none (it is seen on the Floor plan)
Steps:
1. In Reservations the table, the date, the time, the length, the guests or the name of a held booking
   is changed.
2. In that same operation, Tables moves the hold to the new table and to the new time, with the same real length (also
   the night the clocks change); if the booking's table is taken away, it releases the hold.
In: from Reservations, the changed booking.
Out: the hold moved or released (announces: `table.table.held` or `table.table.hold_released`).
If it fails: a new table that is deleted, deactivated or out of service does not receive the hold:
Reservations does not save the change and the booking stays held at the old one.
Involved: RESERVATION-F08, TABLE-F25

### TABLE-F27 Release the table when the booking is cancelled or a no-show
Status: done
Actor: system
Screen: none (it is seen on the Floor plan)
Steps:
1. In Reservations, a booking is cancelled, marked as a no-show or deleted.
2. In that same operation, Tables releases its hold (without the name): the table goes back to Available if it has no other booking
   nor people seated.
3. A hold that was already spent (the people sat down) is not touched.
In: from Reservations, the booking cancelled, no-show or deleted.
Out: the released hold (announces: `table.table.hold_released`).
If it fails: if it is asked twice, nothing changes.
Involved: RESERVATION-F09, RESERVATION-F10, RESERVATION-F20, TABLE-F25

### TABLE-F28 Spend the hold when the booking is seated
Status: done
Actor: employee, manager
Screen: Floor plan (Service)
Steps:
1. The booking's party arrives: the table is Reserved. Tap it; the guests question comes with the
   booking's. Tap "Seat N" (TABLE-F10).
2. The table turns Occupied and its hold is spent. Transferring or splitting a check to that table, or
   seating a parked one there again, also spends it.
3. Seating another party at that table hours before the booking (the table still Available) does
   **not** spend the evening's booking.
4. When seating from Reservations ("Seat" on the booking, RESERVATION-F11) only that booking's hold is
   spent: with Ana at 19:00 and Bea at 21:00 at table 5, seating Ana at 20:10 leaves Bea's alive, and
   when Ana leaves the table shows Reserved for Bea again. If Reservations seats a party more than an
   hour before its booking (its hold does not paint the table yet), it releases that hold when seating
   it: the table does not show Reserved again for whoever already sat down. From the plan it is not
   known which booking the party belongs to, and all those that already painted it Reserved are spent.
In: the Reserved table (and, from Reservations, the booking that is seated).
Out: the holds that painted it Reserved (from Reservations, only its own), spent and without a name.
If it fails: those of TABLE-F10.
Involved: RESERVATION-F11, TABLE-F10, TABLE-F25

### TABLE-F29 Expire the holds that are due
Status: done
Actor: system
Screen: none
Steps:
1. A hold whose window has already passed stops painting the table at that same moment (it is compared
   with the real time, with its zone).
2. Every hour, Tables marks them as expired and erases their name.
In: the time.
Out: the expired holds, without a name (announces: `table.table.hold_released` once per expired hold,
with its table; nothing if none expired).
If it fails: it is repeated on the next sweep; if the hub was stopped, it does a single one on coming
back.
Involved: TABLE-F09, TABLE-F25

### TABLE-F30 Hold or release a table by hand
Status: done
Actor: manager, employee, assistant
Screen: assistant and API (the current product had no screen for this either)
Steps:
1. Ask the assistant to set a table aside ("keep table 6 for Pedro from 21:00 to 23:00, 4 people").
2. From an hour before, the table shows Reserved, with the name and the time; asking for it again with
   the same reference changes the same hold.
3. To release it, ask to release it with the same reference.
In: table, reference, from, until, guests and name.
Out: the hold (announces: `table.table.held`) or its release, which erases the name (announces:
`table.table.hold_released`).
If it fails: "That table does not exist in this business."; releasing a hold that is no longer there:
"That hold is not there any more: it was released, it expired, or that booking never held a table.".
Involved: TABLE-F09, TABLE-F28

### TABLE-F31 Forget the name of a customer whose data are erased (GDPR)
Status: done
Actor: system
Screen: Floor plan
Steps:
1. In **Customers** the personal data of a card are erased (also of the ones merged into it).
2. At once, all the table holds of that customer, live or finished, are left without her name, and the
   check of a table where she is seated stops showing it.
3. The table stays set aside at its time: where the name was, "Deleted customer · 21:00" is read.
In: the notice `customer.customer.erased` with the card's id.
Out: holds without the customer's name (announces: `table.table.held`, and the plan repaints itself). It
does not release any table.
If it fails: repeating it changes nothing; a notice without an id does not touch the holds without a card.
Involved: CUSTOMER-F16, CUSTOMER-F13, RESERVATION-F22

### TABLE-F32 Put or remove the customer of a table
Status: done
Actor: employee, manager
Screen: Floor plan (Service)
Steps:
1. When seating, or in the window of an occupied table, tap "Assign customer" and search the card by
   name or phone (the search box of Customers, the same one as the till's).
2. The check of the table stays with that card: Sales gets it back when charging. "Remove customer" lets
   it go.
3. The assistant can also seat with a customer: "seat Ana García at table 4, there are 3 of us".
In: the card, from Customers.
Out: the check ↔ customer link, which Customers keeps (announces: `customer.order.linked`).
If it fails: the reason of Customers; the table is seated anyway.
Involved: CUSTOMER-F17, CUSTOMER-F19, TABLE-F10

## Tables: what goes in and what comes out

Everything can be asked for through the screens, the assistant (by voice or by text, with the person's
own session) and the API, with the same rules and the same permissions. Designed for voice: a table is
named by its id or by its number ("table 4"), with the zone if the number is repeated ("table 4 on the
terrace"); a zone by its id or by its name; a customer by their id, their name or their phone. If a name
matches several, it is refused saying which ones (409 `*_ambiguous`).

Before changing anything, the assistant asks for confirmation and says by its name, never by a code, what
each change touches: the table with its zone, like 5 (Terrace), because the number is repeated across
zones; the zone; the check by where it is (its table with its zone, or "Parked"); the Sales check by its
title; the customer by their card; the booking by the name it paints on the table, and each line that moves
when splitting by its name. What the person cannot see (the Sales check, without permission in Sales) does
not show.

### What it offers: queries (they read and change nothing)

| What it gives | Who can | Flows | Service |
|---|---|---|---|
| The zones with their tables and the free ones, search, filters, order and pages (up to 100) | view zones | F01, F06 | `table.zone.list` |
| A zone | view zones | F06 | `table.zone.get` |
| The tables with their live status (guests, since when, server, customer, booking), in natural order, with search, filters and pages | view tables | F02, F09 | `table.table.list` |
| A table with its open checks and its name with the zone, like 5 (Terrace) | view tables | F09–F17 | `table.table.get` |
| The checks of the room (open, closed, all), with charged, filters and pages | view checks | F22 | `table.session.list` |
| A table check and where it is: its table with the zone, or "Parked" | view checks | F21, F22 | `table.session.get` |
| The table checks of a Sales check (for the till: the table of the check on screen) | view checks | F12, F13, F24 | `table.session.by_order` |
| A line of the Sales check of a table, with its name and its quantity, as "Split check" lists them | view checks | F17 | `table.session.line` |
| The hold a booking keeps on its table, while it holds it, with the name it paints | view tables | F10, F28 | `table.hold.by_reservation` |
| The servers who have opened checks (for the filter) | view checks | F22 | `table.waiter.list` |
| Whether the plan is set up (tables in use and zones), for "Choose table" of the till and the "Your tables" step of the Home | view tables | F02 | `table.floor.status` |
| The room settings | view settings | F08 | `table.settings.get` |

The zones, the tables, the checks, the servers, the status of the plan and the settings can be followed
live.

### What it offers: actions (they change data)

| What it does | Who can | Flows | Service |
|---|---|---|---|
| Creates, changes and deletes zones | create / change / delete zones | F01, F06 | `table.zone.create`, `.update`, `.delete` |
| Creates a table, many at once, changes it, moves it or deletes it | create / change / delete tables | F02–F07 | `table.table.create`, `.bulk_create`, `.update`, `.move`, `.delete` |
| Seats a party at a table (with a new check or one already open, and its customer) | open checks | F10, F12, F32 | `table.session.open` |
| Closes a table check by hand | change checks | F21 | `table.session.close` |
| Moves a check to another table | transfer checks | F15 | `table.session.transfer` |
| Joins the check of a table with that of another one | transfer checks | F16 | `table.session.merge` |
| Splits the check of a table | change checks | F17 | `table.session.split` |
| Corrects the guests | change checks | F14 | `table.session.set_guests` |
| Takes the table away from a check (park) and seats it again | change checks | F13, F24 | `table.session.park`, `.restore` |
| Links a Sales check to the check of a table | open checks | F12 | `table.session.link_order` |
| Deletes a finished check from the history | delete checks | F23 | `table.session.delete` |
| Holds or releases a table by hand | change checks | F30 | `table.hold.place`, `.release` |
| Saves the room settings | settings | F08 | `table.settings.update` |

For the platform only (without a route in the API, as the system): `table.session.close_by_order`
(reaction to Sales), `table.hold.expire` (scheduled task), `table.hold.sync_reservation` and
`table.hold.move_reservation` (Reservations calls them inside its operation) and
`table.hold.forget_customer` (reaction to Customers).

### What it announces

| Notice | When | What it carries |
|---|---|---|
| `table.zone.created`, `.updated`, `.deleted` | Creating, changing or deleting a zone | `id` |
| `table.table.created`, `.updated`, `.deleted` | Creating (also many at once), changing, moving or deleting a table | `id` (`ids` at once) |
| `table.table.held`, `table.table.hold_released` | Holding or releasing a table (also on expiring) or forgetting the name of an erased customer | `table_id`, `source`, `source_ref` |
| `table.session.opened` | Seating | `id`, `table_id`, `order_id`, `guests_count` |
| `table.session.closed` | Closing by hand or by Sales | `id`, `table_id`, `order_id` |
| `table.session.transferred` | Transferring | `id` (the new one), `from_id`, `from_table_id`, `table_id`, `order_id` |
| `table.session.merged` | Merging | `id`, `into_id`, `table_id`, `order_id` |
| `table.session.split` | Splitting | `id` (the new one), `from_id`, `table_id`, `order_id` |
| `table.session.updated` | Guests or linked check | `id` |
| `table.session.parked`, `table.session.restored` | Parking, seating again | `id`, `table_id` |
| `table.session.deleted` | Deleting from the history | `id` |
| `table.settings.updated` | Saving the settings | the changed fields |

No notice carries names or free notes: only ids and numbers.

### What it reacts to

| Notice | From | What it does | Service |
|---|---|---|---|
| `sale.order.completed` | Sales | Closes the table checks of that check (F18) | `table.session.close_by_order` |
| `sale.order.voided` | Sales | Closes the table checks of that check (F20) | `table.session.close_by_order` |
| `customer.customer.erased` | Customers | Erases the name from their holds (F31) | `table.hold.forget_customer` |

The reactions arrive in the background, shortly after, and repeating them changes nothing. What Sales
says is also read on every read and on every write: a table check whose Sales check is charged or voided
is painted and treated as closed. Reservations is not listened to: it calls Tables inside its own
operation (F25 to F28), and its notices, received afterwards, would replay a booking as it was (an old
"confirmed" would hold again the table of a party already seated).

Load the reactions expect (of each notice only this is read; the rest is ignored):

- `sale.order.completed`, `sale.order.voided`: `order_id`.
- `customer.customer.erased`: `id` (the card).

What Reservations sends when it calls (the same names as its notices `status_changed` and `updated`):

- `table.hold.sync_reservation`: `id` (the booking), `status` (`confirmed` holds; `cancelled`,
  `no_show` or `deleted` release), `table_id`, `date` and `time` (wall-clock, the business's),
  `duration_minutes` (120 if it does not come), `party_size`, `guest_name` and `customer_id`.
- `table.hold.move_reservation`: `id` and the fields that changed; `table_id` sent empty (`null`) = the
  booking was left without a table.

### What it needs from other apps

- **Sales** (requirement): opens the check of each table (`sale.order.open`), sets its title
  (`sale.order.set_label`), splits it (`sale.order.split`), joins it (`sale.order.merge`) and voids the
  empty check of a table that is closed (`sale.order.void`), always calling its operations with the
  session of whoever is in the room and in the same transaction. It reads from its models the status of
  each check, its lines and what was charged.
- **Customers** (requirement): the customer of the check (`customer.order.link`, its model `OrderLink`
  to paint it) and the search by name or phone (`find_customer`).

### Who uses it

| App | What for | Service |
|---|---|---|
| Sales & POS | "Choose table" of the till (SALE-F19): the tables and their status, seating or seating again the check on screen, taking its table away and following the table of a check | `table.table.list`, `table.floor.status`, `table.session.open`, `table.session.restore`, `table.session.park`, `table.session.by_order` |
| Reservations | Holding, moving and releasing the table of a booking and seating it, inside its operation | `table.hold.sync_reservation`, `table.hold.move_reservation`, `table.hold.release`, `table.session.open` |
| Platform (Home) | The "Your tables" step of "Finish setting up your business" (TABLE-F02) | `table.floor.status` |

Kitchen does not call Tables: the ticket carries the title of its check, the one Tables sets in Sales
("Table 4"). Reservations, besides, repaints its screens with the notices of the tables and the zones
(`table.table.created`, `.updated`, `.deleted`, `table.zone.updated`, `.deleted`), and Automations
hears every notice of Tables, like those of any app.

### Who can do what

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| View zones | yes | yes | yes | yes | `table.view_zone` |
| Create zones | yes | yes | yes | no | `table.add_zone` |
| Change zones | yes | yes | yes | no | `table.change_zone` |
| Delete zones | yes | yes | no | no | `table.delete_zone` |
| View tables | yes | yes | yes | yes | `table.view_table` |
| Create tables | yes | yes | yes | no | `table.add_table` |
| Change and move tables | yes | yes | yes | no | `table.change_table` |
| Delete tables | yes | yes | no | no | `table.delete_table` |
| View table checks | yes | yes | yes | yes | `table.view_session` |
| Seat (open checks) | yes | yes | yes | yes | `table.add_session` |
| Change checks (close, split, guests, park, hold) | yes | yes | yes | yes | `table.change_session` |
| Transfer and merge checks | yes | yes | yes | yes | `table.transfer_session` |
| Delete checks from the history | yes | yes | no | no | `table.delete_session` |
| View settings | yes | yes | yes | yes | `table.view_settings` |
| Change settings | yes | yes | no | no | `table.manage_settings` |

The roles arrive from the SaaS with a prefix (`hub_owner`, `hub_admin`, `hub_manager`, `hub_employee`);
the cashier of the current product is an employee. Seating, splitting and joining also ask for "Build the
check" of Sales (`sale.add_sale`), which the four roles have.
