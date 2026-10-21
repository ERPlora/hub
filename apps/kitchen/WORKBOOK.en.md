<!-- generated from WORKBOOK.md sha256:2fa82fb3e28dc5433911736fecac2ff3fdfd9dddd0bc2c70d167072389791131 -->

## What it is for and who it is for

Kitchen receives every round the waiter sends from the till, before charging, and turns it into a
**ticket**: it shows it on a kitchen display that reads from a metre away (the **Display**), shares its
dishes out among **stations** (grill, bar, desserts…), lets each station mark them **ready** and the
pass **serve** them, and keeps a **history** of what was done.

Who uses it:

- The kitchen or floor **employee** (cook, waiter): marks dishes ready, recalls them, serves, marks a
  round rush and sends rounds from the till. Only changes states.
- The **manager**: also cancels and deletes tickets, manages the stations and the routing of products
  and categories, and saves the display settings.
- The **administrator** and the **owner**: everything.

Kitchen does not know what a table or a customer is: it receives a **label** ("Table 4"; without a label,
the card says the type: "Dine in", "Takeaway", "Delivery") that it paints and prints as it is. It does not
charge, does not lower stock and does not keep recipes.

## Adopted reference

ERPlora does not invent flows: it adopts the ones the market has already proven (checked against the
current product on 10/08, 15/08, 24/08 and 02/09/2026, and reviewed when porting).

- **Prep stations, pass view (all the stations), mark ready per dish and per ticket, "rush" after
  sending**:
  [Toast — KDS workflow](https://doc.toasttab.com/doc/platformguide/platformKDSWorkflowUsingCourses.html).
  Courses with hold and fire are not adopted (outside the MVP).
- **A dish voided at the till shows in the kitchen, struck through**:
  [Toast — voids](https://doc.toasttab.com/doc/platformguide/adminVoidingOrders.html).
- **Complete a single dish or the whole ticket, and the completed view**:
  [Square KDS](https://squareup.com/help/us/en/article/8171-complete-orders-with-square-kds).
- **Each tap moves the dish forward; a two-step traffic light that counts from when it was sent**:
  [Lightspeed K-Series KDS 2.0](https://k-series-support.lightspeedhq.com/hc/en-us/articles/22708154090267-Using-the-Kitchen-Display-System-2-0).
- **The ticket moves on by itself to the next stage when its last dish is ticked off**:
  [Odoo — preparation display](https://www.odoo.com/documentation/18.0/applications/sales/point_of_sale/preparation.html).
- **A station stops seeing a ticket as soon as it finishes its part; the pass ("All") keeps seeing it
  whole** (Toast prep stations, Square KDS per station, Fresh KDS): market decision on question 1 of the
  current product.
- **Each tablet remembers its station** (Toast, Square and Fresh set each screen to one station): market
  decision on question 4.
- **Print the pass when marking ready, off by default; a single sound switch with volume and a tone from a
  closed list** (Toast, Fresh KDS, MobiPOS).
- **What goes only to a printer does not wait for anyone to mark it**, and **charging does not stop the
  kitchen** (Toast, Lightspeed K, Odoo, LS Central, Simphony): on charging, what nobody is going to mark
  goes out.
- **The ticket names whoever serves the check ("Served by" in the till) and, if it is "Me", whoever sends
  it** (market decision of 21/10/2026; kitchen#82, hub#2033, staff#59). That way the pass knows whom to
  call, even if that person does not sign in to the app.
  - Full-service tills name the waiter who owns the check or the table:
    [Toast](https://support.toasttab.com/en/article/Why-Aren-t-Server-Names-Showing-on-Kitchen-Tickets)
    always prints the waiter, the check belongs to whoever opens it and, when it is transferred,
    [resends the ticket](https://doc.toasttab.com/doc/platformguide/adminTransferringOrders.html);
    [TouchBistro](https://cdn.touchbistro.com/help/articles/using-the-kds) shows the table's waiter,
    who can be [transferred](https://cdn.touchbistro.com/help/articles/table-options);
    [Loyverse](https://help.loyverse.com/help/kitchen-display-system) shows the ticket's waiter;
    [Square](https://community.squareup.com/t5/Questions-How-To/Changing-Employee-Name-on-Printed-Tickets/td-p/273546)
    prints the waiter's name from their team profile.
  - Counter tills show whoever takes the order or holds the session, who on the floor is usually the same
    person:
    [Clover](https://community.clover.com/answers/4424/view.html),
    [Qamarero](https://qamarero.com/comandero-digital/),
    [Odoo (waiter module)](https://apps.odoo.com/apps/modules/17.0/pos_waiter_name) and the
    [Square guide in Spanish](https://squareup.com/es/es/townsquare/restaurant-order-taking).
    That is where the "Me" fallback comes from.
  - [Lightspeed K](https://k-series-support.lightspeedhq.com/hc/articles/4403006478107) lets you choose
    the fields of the ticket.
  - It is also what the current product did and what the till itself promises in "Who is serving this
    check".

## Before you start

- Switching Kitchen on also switches on **Sales** and **Inventory**. **Tables** and **Customers** are not
  needed: without Tables, the ticket carries the check's label or its type.
- For paper to come out you need **Printing** with a printer for the "Kitchen" (or "Bar") function set up
  (PRINTING-F04). Without Printing, Kitchen works with the display only.
- Initial setup, step by step:
  1. In **Kitchen → Stations**, create the real stations (Grill, Bar, Desserts) with their destination
     (screen, paper or both) and their printer (KITCHEN-F01).
  2. In the "Product/category routing → station" panel, send each category to its station and the
     single products that must go to another one (KITCHEN-F04). Whatever has no station shows on the
     display under "No station" and prints on the kitchen printer.
  3. In **Kitchen → Settings**, adjust the amber and red warnings, the sound and, if wanted, the printed
     pass. If nobody in the kitchen is going to mark anything on the display, switch off "The kitchen works
     from the screen" (KITCHEN-F26).
  4. On the kitchen tablet open **Kitchen → Display**, choose its station, press "Full screen" and tap
     the screen once so the browser lets the chime ring (KITCHEN-F16).
  5. Send a test round from the till and check that each dish comes out at its station.

## Screens

### Display
Menu **Kitchen → Display**. The kitchen board. A single bar at the top, fixed while scrolling: the three
views as tabs with their counter ("Tickets" and "Ready"; "All-Day" without a counter), the "Full screen"
button and, if the tickets on the line have dishes from more than one station, the station buttons
("All", each station by its name and with its colour, and "No station"). The chosen station is remembered
on that device. Below, a grid of cards in equal columns (a single one on the phone). Each card: the label
("Table 4"; without a label, the type), "Waiter: <name>", the marks "Rush", "VIP", "Round N" (from the
second one) and "Ready", the clock and the short number "#0012"; the dishes with the quantity in large
type, the name, their modifiers in bold, the note in italics and, in "All", the station; the dishes of a
menu, next to a line under the menu header, which says how many dishes it has ("2 dishes") and, when
tapped, marks its dishes ready; a paper icon if the station is paper only. A dish voided at the till shows
struck through, with "Voided" and the reason in red, and does not respond to a tap. At the bottom,
depending on the permission and the state: "Ready", "Mark rush" / "Remove rush", "Recall" and "Served",
whole and finger-sized on a tablet. The top edge of the card is green, amber or red depending on the time
since it was sent. Empty: "No tickets on the line." (Tickets), "Nothing waiting to be picked up." (Ready),
"Nothing left to cook." (All-Day). Loading: "Loading the display…". Error: "Could not load the kitchen
display" with "Retry". A failure when asking for paper leaves "The pass could not be printed. Check the
printer of the station." or "The urgent notice could not be printed. Tell the kitchen by voice and check
its printer." until a later print comes out fine. It updates by itself with every change, without
reloading.

### Tickets
Menu **Kitchen → Tickets**. Table of all the tickets, newest first, 50 per page (another size is chosen
at the bottom):
Ticket (full number `AAAAMMDD-NNNN`), Destination (the label), Type, Priority, Status, Dishes and Total;
search box "Search ticket or destination…" (by number and label), filters by Type, Priority and Status
(each one a list with its words: "Dine in", "Rush", "To prepare"…), and table or card view. Actions per
row, icon only: "Fire", "Ready", "Served", "Recall" and "Cancel" (in the "⋮" menu, with confirmation and an
optional reason); only the ones the profile can do show up, and the ones the state does not allow are
hidden. Tapping a row opens its detail: the dishes with their menu, their modifiers, their station and
their state. "New ticket" opens the panel (full screen on the phone) with Type, Destination, Notes and
its dishes (product of the catalogue, quantity and note; "Add dish"), and "Create ticket". Empty: "No
tickets.". Loading: the table skeleton. Load error: the table's, with retry; a rejection of an action
shows in its dialog or above the table, and one of the creation, inside the panel.

### Stations
Menu **Kitchen → Stations**. Table: Station (with its colour), Destination ("Screen and paper", "Screen
only", "Paper only"), Printer (the function —"Kitchen", "Bar"— and, if one was chosen, the specific
printer), In progress (dishes to cook at that station) and Active ("Yes"/"No"); search box "Search
station…". "Add station" opens the panel with Name ("e.g. Grill"), Colour, Destination, Printer function,
Printer "(optional)" and Active. Per row: "Edit" (also by tapping the row), "Route" (the routing panel
with that station chosen) and "Delete", which asks "Delete «<name>»?". Below, the "Product/category
routing → station" panel: the list of what goes to each station (Product or Category, its name, the
station) with "Remove" per row, and "Route" opens the panel to choose the station and a product or a
category of the catalogue ("Save routing"). Empty: "No stations." and "Nothing routed yet: everything goes
to «No station».". Loading: the skeleton. Error: the table's, with retry; each rejection inside its form or
its dialog. The actions only show to whoever can manage stations (manager, administrator, owner).

### History
Menu **Kitchen → History**, title "Kitchen history". Table of what happened in the kitchen, latest first,
50 per page (another size is chosen at the bottom): Action, Ticket (the number), Dish, Who (the person's
name or, if they have none, their e-mail; "System" if Kitchen did it by itself), Notes and When (date and
time of the business). Search box "Search ticket or notes…" (a piece of the number or words of the notes);
action filter with the same words as the column ("Received", "Created", "Fired", "Ready", "Dish ready",
"Dish recalled", "Dish voided", "Served", "Recalled", "Cancelled", "Rush", "Rush removed", "Reprinted",
"Deleted"). Empty: "No recent kitchen activity.". Loading: the skeleton. Error: the table's, with retry.

### Settings
Tab **Kitchen → Settings** (only for whoever can save them: manager, administrator, owner). "Show timer",
"Amber warning (minutes)", "Red alert (minutes)", "Colour semaphore", "Sound on a new ticket", "Sound
volume (0-100)", "Sound tone" ("Chime", "Bell", "Buzzer"), "Print the pass when marked ready", "The
kitchen works from the screen" and "Default order type" ("Dine in", "Takeaway", "Delivery"), with "Save"
(it can only be pressed when something changed; on saving, "Settings saved.") and "Test sound". Loading:
"Loading settings…". Error: "Could not load the settings." with retry; a rejection on saving, under the
form with the field marked.

## States of each screen

| Screen | Loading | Empty | Error |
|---|---|---|---|
| Display | "Loading the display…" | "No tickets on the line." · "Nothing waiting to be picked up." · "Nothing left to cook." | "Could not load the kitchen display" + Retry |
| Tickets | table skeleton | "No tickets." (with a search: "No results") | the table's + Retry |
| Stations | table skeleton | "No stations." | the table's + Retry |
| History | table skeleton | "No recent kitchen activity." | the table's + Retry |
| Settings | "Loading settings…" | — | "Could not load the settings." + Retry |

## Flows

| ID | Flow | Status |
|---|---|---|
| KITCHEN-F01 | Create a station | done |
| KITCHEN-F02 | Edit, rename or switch off a station | done |
| KITCHEN-F03 | Delete a station | done |
| KITCHEN-F04 | Send products and categories to a station (and remove them) | done |
| KITCHEN-F05 | Receive the round the till sends | done |
| KITCHEN-F06 | A menu of the day on the ticket | done |
| KITCHEN-F07 | Notes on each dish | done |
| KITCHEN-F08 | The ticket comes out on paper at each station | done |
| KITCHEN-F09 | Reprint a ticket | done |
| KITCHEN-F10 | See the kitchen board | done |
| KITCHEN-F11 | Mark dishes ready | done |
| KITCHEN-F12 | Recall what was marked by mistake | done |
| KITCHEN-F13 | Serve what is ready | done |
| KITCHEN-F14 | Mark a round rush from the kitchen display | done |
| KITCHEN-F15 | See how much is left to cook | done |
| KITCHEN-F16 | Ring when a ticket arrives | done |
| KITCHEN-F17 | Print the pass when marking ready | done |
| KITCHEN-F18 | Send the round from the till, normal or rush | done |
| KITCHEN-F19 | Follow the check's tickets from the till | done |
| KITCHEN-F20 | Mark a round rush from the till | done |
| KITCHEN-F21 | Move a ticket from the Tickets list | done |
| KITCHEN-F22 | Cancel a ticket | done |
| KITCHEN-F23 | Create a ticket by hand | done |
| KITCHEN-F24 | Delete a ticket | done |
| KITCHEN-F25 | Look up the kitchen history | done |
| KITCHEN-F26 | Adjust the kitchen display | done |
| KITCHEN-F27 | Close the rounds when the whole check is charged | done |
| KITCHEN-F28 | Withdraw the rounds of a check deleted or merged into another | done |
| KITCHEN-F29 | Void a dish already sent, with a notice to the kitchen | done |
| KITCHEN-F30 | Move the tickets of a customer merged into another | discarded — the ticket does not keep a customer |
| KITCHEN-F31 | Give Cash register the tickets still under way | done |

### KITCHEN-F01 Create a station
Status: done
Actor: manager, administrator
Screen: Stations
Steps:
1. Press "Add station": the panel opens.
2. Write the name ("e.g. Grill") and choose the colour, the destination ("Screen and paper", "Screen
   only", "Paper only"), the printer function ("Kitchen" or "Bar") and, if you want, a specific printer by
   its name.
3. Press "Create station": the panel closes and the station shows in the table, "Active: Yes", "In
   progress: 0".
In: what whoever creates it writes.
Out: the station (announces: station created).
If it fails: the rejection shows inside the panel. A name that another live station already has is rejected
("There is already a station with that name. Choose a different name."); the name of a deleted one is free
again. Whoever cannot manage stations does not see the button.
Involved: KITCHEN-F02, KITCHEN-F03, KITCHEN-F04, KITCHEN-F08, PRINTING-F04

### KITCHEN-F02 Edit, rename or switch off a station
Status: done
Actor: manager, administrator
Screen: Stations
Steps:
1. Tap the row (or "Edit"): "Edit station · <name>" opens.
2. Change the name, the colour, the destination, the printer or "Active".
3. Press "Save": the table updates.
In: the station and what changes.
Out: the changed station (announces: station changed). Switching it off makes the dishes sent afterwards
look for the station of their category and, if there is none, come out under "No station". What was
already sent does not change station or destination; the name and colour the display paints are the live
ones.
If it fails: inside the form. A repeated name is rejected; saving a station that another device has just
deleted says it no longer exists.
Involved: KITCHEN-F01, KITCHEN-F04, KITCHEN-F10, PRINTING-F04

### KITCHEN-F03 Delete a station
Status: done
Actor: manager, administrator
Screen: Stations
Steps:
1. In the row, "Delete": "Delete «<name>»?" shows with "The station leaves the list and stops receiving
   tickets. Tickets already sent keep it in their history.".
2. Press "Delete station".
In: the station.
Out: the station withdrawn (not erased) and its name free (announces: station deleted).
If it fails: with products or categories routed to it, or with dishes of its own to cook, it is rejected with
"This station cannot be deleted: products or categories are routed to it, or it has dishes to cook. Move
them to another station first.", inside the dialog.
Involved: KITCHEN-F01, KITCHEN-F04, KITCHEN-F10

### KITCHEN-F04 Send products and categories to a station (and remove them)
Status: done
Actor: manager, administrator
Screen: Stations
Steps:
1. In the "Product/category routing → station" panel, press "Route": choose the station and a product or
   a category (by its name, from Inventory's catalogue).
2. Press "Save routing": it shows in the routing list, replacing the one it had.
3. "Remove" on a row of the routing deletes it: what is sent afterwards will go by its category or to "No
   station".
In: the station and Inventory's products and categories.
Out: the routing (announces: routing changed). It only affects what is sent afterwards. On sending, each
dish goes to the station of its product; if it has none, to the one of its category (the one the line
brings from Sales); if not, "No station", which shows on the display and prints on the kitchen printer. A
drink routed to a bar station prints on the bar's printer; if its check has no title or channel, the
ticket is "Dine in", never "Takeaway".
If it fails: routing to an inactive station is rejected ("That station is switched off: switch it on or
choose another one."); a product, a category or a station that does not exist, too. If someone deletes it
at that same moment, the routing is rejected all the same or saved before the deletion: it never gives an
error.
Involved: KITCHEN-F01, KITCHEN-F05, KITCHEN-F08, INVENTORY-F04, INVENTORY-F06, INVENTORY-F07, INVENTORY-F27

### KITCHEN-F05 Receive the round the till sends
Status: done
Actor: system
Screen: none
Steps:
1. The waiter sends the round (KITCHEN-F18) or Sales sends it by itself (through the assistant or the
   API); the one Sales sends by itself reaches Kitchen a moment later, without anyone doing anything.
2. Kitchen opens a ticket with the day's number (`AAAAMMDD-NNNN`, the business day, Madrid time), the
   check's round, the check's label ("Table 4"), the type, the priority and the waiter.
3. Each line that is not a service is a dish, in the order of the check, sent to its station
   (KITCHEN-F04); a menu, one dish for each dish chosen (KITCHEN-F06). Service lines are not cooked.
4. The ticket appears on the display as "To prepare", rings (KITCHEN-F16) and comes out on paper
   (KITCHEN-F08).
In: from Sales, the check's sent lines (their round, their sending time, their product, their quantity,
their note, their modifiers, their category and, if it is a menu, its dishes) and, when Kitchen does the
sending, the priority, the channel and who sends.
Out: the ticket "To prepare" with its dishes and "Received" in the History, at the time of sending
(announces: ticket received).
If it fails: a round of services only does not open a ticket. What was sent before Kitchen existed in the
business does not appear. The same round never opens two tickets, even if it arrives twice. No failure
here blocks the waiter.
Involved: SALE-F20, KITCHEN-F04, KITCHEN-F06, KITCHEN-F07, KITCHEN-F08, KITCHEN-F16, KITCHEN-F18

### KITCHEN-F06 A menu of the day on the ticket
Status: done
Actor: employee
Screen: Display
Steps:
1. At the till, add a menu choosing a dish from each course (SALE-F12) and press "Send order"
   (KITCHEN-F18).
2. On the card the menu header shows (its kitchen name or, if it has none, its name) with how many dishes
   it has ("2 dishes"; "1 dish" if it is one) and, below, next to a line, each dish chosen with the
   quantity multiplied by the menus ordered.
3. Each dish goes to the station of its own product or, if it has none, to the one of its category
   (KITCHEN-F04), never to the menu's: each station sees only its dishes, with the same header above.
4. Tap a dish to mark it ready, or tap the menu header to mark ready at once its dishes still on screen;
   the rest of the ticket does not change.
5. On each station's paper the menu header comes out and, indented below, its dishes (KITCHEN-F08).
In: from Sales, the menu as it was ordered: its dishes chosen (each one with its product and its
category), its kitchen name, how many menus and the menu's note, which shows on each of its dishes.
Out: one dish for each dish of the menu, each at its station, marked ready and served separately; the
menu's amount counts only once in the ticket's total (announces: ticket received).
If it fails: a dish of the menu that is a service is not cooked and does not come out; a menu whose dishes are
all services does not open a ticket. The till does not let you add a menu without choosing anything or one
that is missing a mandatory course, so it never arrives empty or half-done. Voiding the menu at the till
strikes through all its dishes (KITCHEN-F29). What was already sent does not change even if the menu
changes afterwards.
Involved: SALE-F12, SALE-F20, COMBO-F11, KITCHEN-F04, KITCHEN-F08, KITCHEN-F29

### KITCHEN-F07 Notes on each dish
Status: done
Actor: employee
Screen: Display
Steps:
1. At the till, choose the dish's modifiers ("+CHEESE", "no onion", how it is cooked) (SALE-F11) and, if
   needed, write a note on the line (SALE-F13); then send the round.
2. On the card, under the dish's name come its modifiers in bold, separated by commas and in the order
   they were chosen, and below that the note in italics.
3. On paper they come out the same way: each modifier on its own line, indented under the dish, and then
   the note (KITCHEN-F08).
In: from Sales, the modifiers chosen with their kitchen name (if they have none, their name), the
line's note and, if the line is on the house, the reason.
Out: the modifiers and the note frozen on the dish: changing the catalogue afterwards does not change this
ticket.
If it fails: an allergy only exists as text in the note: it is not highlighted or told apart from another
note. A modifier charged on a separate line (another VAT) comes out the same under its dish.
Involved: SALE-F11, SALE-F13, SALE-F20, MODIFIER-F08, KITCHEN-F08

### KITCHEN-F08 The ticket comes out on paper at each station
Status: done
Actor: system
Screen: none
Steps:
1. On receiving the round, Kitchen asks Printing for one sheet per printer: the dishes of each station
   that is not "Screen only", by its function ("Kitchen", "Bar") or by the station's specific printer; a
   dish without a station, by "Kitchen". It is the same for the round the waiter sends (KITCHEN-F18) and
   for the one Sales sends by itself, which prints when it reaches Kitchen.
2. The sheet carries the label, the number, the round, the waiter and each dish with its quantity, its
   modifiers (one per line) and its note, and the dishes of a menu indented under their header
   (KITCHEN-F06, F07); if the round is rush, `!! URGENTE !!`.
In: the dishes with the destination and the printer frozen on receiving.
Out: one job per printer in Printing's queue, only once even if it is asked for twice: the round Kitchen
sent is not printed again when the notice from Sales reaches it.
If it fails: it never blocks the waiter. Without Printing no paper comes out and there is no warning (the
kitchen works with the display). If Printing rejects the job, the ticket stays on the display and can be
reprinted (KITCHEN-F09); at the till, the waiter sees "Order N sent to the kitchen, but it did not print.
Check the kitchen printer in Printing." (KITCHEN-F18).
Involved: KITCHEN-F05, KITCHEN-F06, KITCHEN-F07, KITCHEN-F09, KITCHEN-F18, SALE-F20, PRINTING-F04, PRINTING-F10, PRINTING-F18

### KITCHEN-F09 Reprint a ticket
Status: done
Actor: employee, manager
Screen: Tickets
Steps:
1. In the row, "⋮ → Reprint".
2. Another sheet comes out for each printer of its dishes, marked as a copy. A ticket that never came out
   on paper comes out as its first sheet, without "copy".
In: the ticket.
Out: new jobs in Printing's queue (each reprint is a different job).
If it fails: "The ticket could not be printed: <reason>", with Printing's reason; without Printing, "Printing
is not active in this business.".
Involved: KITCHEN-F08, KITCHEN-F21, PRINTING-F11

### KITCHEN-F10 See the kitchen board
Status: done
Actor: employee, manager
Screen: Display
Steps:
1. Open **Kitchen → Display**. On a tablet, "Full screen" leaves only the board on the screen, without the
   Hub's menu; another tap ("Exit full screen") brings it back.
2. At the top, the tabs "Tickets", "Ready" and "All-Day". In "Tickets" are the ones being cooked: first the
   rush ones, then the VIP ones and then the rest, the oldest first within each group.
3. If there are dishes from more than one station, choose yours: "All" shows every dish (the pass); a
   station shows only its dishes and only the tickets that still have something of its own to cook; "No
   station", the dishes without a route. The choice is remembered on that device.
4. The edge of each card goes from green to amber on reaching "Amber warning" and to red on reaching "Red
   alert", counting from when it was sent; the clock stays red. Without "Colour semaphore" the edge stays
   grey; without "Show timer" there is no clock.
In: the tickets To prepare, Preparing and Ready with their dishes; the settings; the live names and
colours of the stations.
Out: nothing; it only shows. The buttons of each card show whole and are easy to press with a finger on
a tablet.
If it fails: "Could not load the kitchen display" with "Retry", a normal-sized button. Without permission to
change tickets, the display is look-only: no buttons and the dishes do not respond.
Involved: KITCHEN-F11, KITCHEN-F12, KITCHEN-F13, KITCHEN-F14, KITCHEN-F15, KITCHEN-F16, KITCHEN-F26

### KITCHEN-F11 Mark dishes ready
Status: done
Actor: employee, manager
Screen: Display (also the assistant: "mark table 4 ready")
Steps:
1. Tap a dish when it is done: it is struck through with ✓.
2. Or tap the card's header, or "Ready": the dishes of that card that show on your screen and are still
   to cook are marked (at a station, only its own).
3. The first dish marked moves the ticket to "Preparing". When no dish is left to cook, from any station,
   the ticket moves to "Ready": it leaves "Tickets" and appears in "Ready".
In: the dishes of the card.
Out: each dish ready (announces: dish ready; History "Dish ready"), the ticket started ("Fired") or ready
("Ready"); with the pass switched on, it comes out on paper (KITCHEN-F17).
If it fails: two cooks who mark the same dish at the same time mark it once. A dish of a Served or Cancelled
ticket is rejected with "That kitchen ticket is no longer in the state this action requires. Refresh and
try again.".
Involved: KITCHEN-F10, KITCHEN-F12, KITCHEN-F17, KITCHEN-F25

### KITCHEN-F12 Recall what was marked by mistake
Status: done
Actor: employee, manager
Screen: Display
Steps:
1. Tap a struck-through dish: it is to cook again.
2. Or "Recall" on the card (on a tablet, the button shows whole): the struck-through dishes that show on
   your screen come back.
3. A ticket in "Ready" is recalled with "Recall": it goes back to "Preparing" and to "Tickets".
In: the struck-through dishes.
Out: each dish to cook (announces: dish recalled; History "Dish recalled") and, if the ticket was Ready,
"Recalled". Recalling what is already to cook changes nothing.
If it fails: a Served or Cancelled ticket is not recalled.
Involved: KITCHEN-F10, KITCHEN-F11, KITCHEN-F16, KITCHEN-F21, KITCHEN-F25

### KITCHEN-F13 Serve what is ready
Status: done
Actor: employee, manager
Screen: Display, Tickets
Steps:
1. In "Ready", the finished tickets wait for someone to pick them up, the oldest first.
2. When the dish goes out, press "Served": the card disappears.
In: the Ready ticket.
Out: the Served ticket (announces: ticket served; History "Served"). On charging the whole check, the
Ready ones move to Served by themselves (KITCHEN-F27).
If it fails: only a Ready ticket is served.
Involved: KITCHEN-F11, KITCHEN-F21, KITCHEN-F27

### KITCHEN-F14 Mark a round rush from the kitchen display
Status: done
Actor: employee, manager
Screen: Display
Steps:
1. On a card being cooked, "Mark rush": it carries "Rush" and jumps to the start of the board on every
   display, which ring once.
2. The stations that print and still have dishes of that round to cook receive a short notice on paper:
   the ticket's header with `!! URGENTE !!` and no dishes.
3. "Remove rush" undoes it and prints nothing. A VIP round does not offer the button, and through the
   assistant or the API it is rejected ("That ticket is VIP: a rush does not change its priority.").
In: the ticket being cooked.
Out: the rush round (announces: ticket changed; History "Rush"); each switch to rush gives a new notice on
paper.
If it fails: only a ticket To prepare or Preparing is marked rush ("That ticket is no longer being
cooked."). If the notice does not print, the display says so.
Involved: KITCHEN-F10, KITCHEN-F16, KITCHEN-F20, PRINTING-F10

### KITCHEN-F15 See how much is left to cook
Status: done
Actor: employee, manager
Screen: Display (also the assistant: "what is left on the grill")
Steps:
1. Press "All-Day": each dish and the quantity left to cook adding up every ticket being cooked, from most
   to least; in "All", with its station.
2. With a station chosen, only its own.
In: the dishes to cook of the tickets To prepare and Preparing.
Out: nothing.
If it fails: with nothing to cook, "Nothing left to cook.".
Involved: KITCHEN-F10, KITCHEN-F29

### KITCHEN-F16 Ring when a ticket arrives
Status: done
Actor: system
Screen: Display
Steps:
1. With "Sound on a new ticket", the display rings when a ticket it did not have arrives or when one it had
   becomes rush; if several arrive at once, once.
2. It rings with the tone and volume of Settings; on opening the display it does not ring for what was
   already there. Recalling a ticket from "Ready" does not ring again: only new rounds and rushes ring.
In: the tickets of each update and the settings.
Out: the sound; nothing is saved.
If it fails: if the browser does not let it ring until the first tap, that chime is lost. With volume 0 it
does not ring.
Involved: KITCHEN-F05, KITCHEN-F10, KITCHEN-F12, KITCHEN-F14, KITCHEN-F26

### KITCHEN-F17 Print the pass when marking ready
Status: done
Actor: system
Screen: none
Steps:
1. In **Kitchen → Settings**, switch on "Print the pass when marked ready" (off by default) and press
   "Save".
2. Every time a ticket becomes Ready (KITCHEN-F11), the pass comes out on the printer of its dishes'
   station: one sheet per printer with its dishes (not those of screen-only stations), the label, the
   number, the round and the waiter.
In: the ticket that becomes Ready.
Out: jobs in Printing's queue; a ticket recalled and marked ready again prints another pass.
If it fails: the display shows "The pass could not be printed. Check the printer of the station.".
Involved: KITCHEN-F11, KITCHEN-F26, PRINTING-F10

### KITCHEN-F18 Send the round from the till, normal or rush
Status: done
Actor: employee
Screen: Sales: Sell
Steps:
1. In **Sales → Sell**, with the check open, open the "Current order" tab: what is left to send. On adding
   the first product, which opens the check, the till stays on that tab.
2. If the round is in a hurry, tap the flame: the button becomes "Send RUSH (N)". Each tap arms it or
   disarms it.
3. Press "Send order (N)" (or "Send RUSH (N)"): "Order N sent to the kitchen." shows and the flame is
   disarmed.
4. Sales marks the pending lines with a new round (SALE-F20) and Kitchen opens the ticket (KITCHEN-F05),
   rush if the flame was armed, and prints it at each station (KITCHEN-F08).
In: the open check with its unsent lines, its label, the channel, the priority and who serves the check
("Served by", SALE-F16).
Out: the ticket on the kitchen display and on paper, with the name of whoever serves the check, even if
they do not sign in to the app; with "Served by me", the name of whoever sends the round (announces: ticket
received).
If it fails: with nothing new, "There is nothing new to send to the kitchen.": it is not an error and nothing
is sent. If the round is sent but its sheet does not print, the till says "Order N sent to the kitchen, but
it did not print. Check the kitchen printer in Printing.", never the technical reason; the ticket is
already on the kitchen display and can be reprinted (KITCHEN-F09). If Kitchen does not answer, "The order
could not be sent to the kitchen. Try again.". Without Kitchen active, the till has no tab or button.
Involved: SALE-F20, KITCHEN-F05, KITCHEN-F08, KITCHEN-F09, KITCHEN-F19, PRINTING-F10

### KITCHEN-F19 Follow the check's tickets from the till
Status: done
Actor: employee
Screen: Sales: Sell ("Order tickets" sheet)
Steps:
1. In **Sales → Sell**, with Kitchen active and permission to see tickets, the "Check" tab shows "Tickets ·
   N" next to the header of what was sent; press it.
2. The "Order tickets" sheet opens: one card per round, the most recent first, with "Order N", the sending
   time (the business's), its state with the same words as the kitchen ("To prepare", "Preparing",
   "Ready", "Served", "Cancelled"), "Rush" if it is one and its dishes (a voided one, struck through with
   "Voided").
3. The sheet updates by itself while it is open: what the kitchen marks shows without reloading.
In: the tickets of that check, also those that came from a check merged into it.
Out: nothing; it only shows.
If it fails: if they cannot be loaded, "The order tickets could not be loaded." with "Retry". Without
permission to see tickets, or without Kitchen active, the till does not show "Tickets · N".
Involved: SALE-F20, SALE-F24, KITCHEN-F05, KITCHEN-F20, KITCHEN-F28, KITCHEN-F29

### KITCHEN-F20 Mark a round rush from the till
Status: done
Actor: employee, manager
Screen: Sales: Sell ("Order tickets" sheet)
Steps:
1. Open "Order tickets" (KITCHEN-F19).
2. On the card of a round being cooked (To prepare or Preparing), press "Mark rush": the card carries
   "Rush" and, in the kitchen, the round jumps to the start of the board and rings, as from the kitchen
   display (KITCHEN-F14).
3. The stations that print and still have dishes of that round to cook receive the short notice on paper.
4. "Remove rush" undoes it and prints nothing.
In: the round being cooked and whoever marks it, with permission to change tickets (the one of
KITCHEN-F14).
Out: the round rush or back to normal (announces: ticket changed; History "Rush" or "Rush removed").
If it fails: if it cannot be changed, "Could not update the ticket". If the notice on paper does not print,
the sheet says so: "The urgent notice could not be printed. Tell the kitchen by voice and check its
printer.". A Ready, Served, Cancelled or VIP round does not carry the button, nor does whoever cannot
change tickets see it. Without Kitchen active, the till shows none of this.
Involved: SALE-F20, KITCHEN-F14, KITCHEN-F19

### KITCHEN-F21 Move a ticket from the Tickets list
Status: done
Actor: employee, manager
Screen: Tickets
Steps:
1. Search for the ticket or filter by Type, Priority or Status (each filter a list with its words). At the
   bottom, choose how many to see per page: with 25 you see 25.
2. Use the action of its row: "Fire" (To prepare → Preparing), "Ready" (→ Ready, with all its dishes),
   "Recall" (Ready → Preparing; its ready dishes go back to be cooked) or "Served" (Ready → Served).
In: the ticket.
Out: the new state and its entry in the History; the kitchen display and the till update by themselves.
If it fails: if the ticket changed on another screen, "That kitchen ticket is no longer in the state this
action requires. Refresh and try again.".
Involved: KITCHEN-F11, KITCHEN-F12, KITCHEN-F13, KITCHEN-F19, KITCHEN-F22, KITCHEN-F23, KITCHEN-F25

### KITCHEN-F22 Cancel a ticket
Status: done
Actor: manager
Screen: Tickets (also the assistant)
Steps:
1. In the row, "⋮ → Cancel": "Cancel ticket <number>?" shows with "It leaves the kitchen display. The check
   in the till does not change: its dishes stay on it." and an optional reason.
2. Press "Cancel ticket": the ticket and its dishes move to "Cancelled" (a voided dish stays "Voided").
In: the ticket To prepare, Preparing or Ready.
Out: the cancelled ticket (announces: ticket cancelled; History "Cancelled" with the reason). If the round
came out on paper, Kitchen asks Printing for a void slip with what was left to cook ("CANCELLED · Table 4",
the dishes as negatives), so that the kitchen stops preparing it; also when the round is cancelled because
its check is deleted at the till (KITCHEN-F28).
If it fails: a Served or Cancelled ticket is not cancelled. One that never came out on paper prints no slip.
Involved: KITCHEN-F21, KITCHEN-F25, KITCHEN-F28, KITCHEN-F29, PRINTING-F10

### KITCHEN-F23 Create a ticket by hand
Status: done
Actor: employee, manager
Screen: Tickets
Steps:
1. "New ticket": choose the Type (it starts at the one in Settings), write the Destination and some Notes
   if you want, and add its dishes (product of the catalogue, quantity and note).
2. "Create ticket": the panel closes and the ticket shows at the top of the list (even if you were on
   another page, the list goes back to the first) and on the display.
In: the type, the destination, the notes and the dishes.
Out: a ticket To prepare, round 1, without a check, with the name of whoever creates it (announces: ticket
created; History "Created"); its dishes go to their station like those of a round.
If it fails: inside the panel. A ticket without dishes is rejected ("Add at least one dish."). As it hangs
from no check, charging does not close it.
Involved: KITCHEN-F04, KITCHEN-F10, KITCHEN-F21, KITCHEN-F24, KITCHEN-F27, INVENTORY-F27

### KITCHEN-F24 Delete a ticket
Status: done
Actor: manager
Screen: assistant or API
Steps:
1. Ask the assistant to delete the ticket.
2. Only a ticket made by hand that is To prepare or Cancelled is deleted: it is withdrawn (not really
   erased) and disappears from the lists.
In: the ticket.
Out: the withdrawn ticket (announces: ticket deleted; History "Deleted").
If it fails: a ticket of a check from the till, or one under way, is rejected with "That ticket cannot be
deleted: it comes from a check or it is already being cooked. Cancel it instead.". Deleting again one
already deleted answers the same and changes nothing.
Involved: KITCHEN-F22, KITCHEN-F23, KITCHEN-F25

### KITCHEN-F25 Look up the kitchen history
Status: done
Actor: employee, manager, administrator
Screen: History
Steps:
1. Open **Kitchen → History**: what happened, on which ticket and with which dish, who (their name or, if
   they have none, their e-mail), their notes and when, latest first.
2. In "Search ticket or notes…", write a piece of the ticket's number or a few words of the notes; filter
   by action ("Received", "Cancelled"…).
3. At the bottom, change page or choose how many entries to see (25, 50…).
In: the entries Kitchen writes down by itself: received, created, fired, dish ready, recalled or voided
(with the reason), ready, recalled, served, cancelled (with the reason), rush, rush removed, reprinted and
deleted.
Out: nothing; it only shows.
If it fails: if it cannot be loaded, "Could not load the history" with "Retry". Whoever has no permission to
see the history reads "You do not have permission to see this.".
Involved: KITCHEN-F05, KITCHEN-F11, KITCHEN-F12, KITCHEN-F14, KITCHEN-F21, KITCHEN-F22, KITCHEN-F24, KITCHEN-F29

### KITCHEN-F26 Adjust the kitchen display
Status: done
Actor: manager, administrator
Screen: Settings
Steps:
1. Change whatever is needed: "Show timer", "Amber warning (minutes)" (15), "Red alert (minutes)" (30),
   "Colour semaphore", "Sound on a new ticket", "Sound volume (0-100)" (70), "Sound tone" ("Chime"), "Print
   the pass when marked ready" (off), "The kitchen works from the screen" (on) and "Default order type"
   ("Dine in"). The tone and the type are chosen by their words ("Chime", "Bell", "Buzzer"; "Dine in",
   "Takeaway", "Delivery").
2. "Save" can only be pressed when something changed: "Settings saved." shows and the open displays take
   them at once.
In: the values.
Out: the settings (announces: settings changed). "The kitchen works from the screen" applies from the next
charge: what was charged before is served by hand.
If it fails: minutes outside 1–120 or a volume outside 0–100 are rejected; the amber equal to or greater than
the red, too ("The amber warning has to come before the red one."). The rejection shows under the form,
with the field marked, and what was written stays.
Involved: KITCHEN-F10, KITCHEN-F16, KITCHEN-F17, KITCHEN-F23, KITCHEN-F27

### KITCHEN-F27 Close the rounds when the whole check is charged
Status: done
Actor: system
Screen: none
Steps:
1. The cashier charges the whole check; a partial charge does not count.
2. A moment after the charge, without anyone doing anything, the rounds of that check that were already
   Ready move to Served and leave the display. Those To prepare and Preparing **are not touched**:
   charging does not stop the kitchen; when they finish, they go to "Ready" and the pass serves them.
3. Except what nobody is going to mark: with "The kitchen works from the screen" off (since it was
   switched off), every round under way of the check; and, with it on, the round whose dishes all went to
   "Paper only" stations. Those move to Served with their dishes.
In: from Sales, the closed check.
Out: each closed round Served, with its entry in the History. Tickets made by hand are not touched.
If it fails: a charge of part of the check (SALE-F22) closes no round: they stay in the kitchen until the
whole check is charged. With "The kitchen works from the screen" off, what was charged is served on
charging even if nobody marked it; what was charged before switching it off is served by hand
(KITCHEN-F26). A repeated charge notice changes nothing: no round is served twice.
Involved: SALE-F01, SALE-F22, KITCHEN-F13, KITCHEN-F25, KITCHEN-F26

### KITCHEN-F28 Withdraw the rounds of a check deleted or merged into another
Status: done
Actor: system
Screen: none
Steps:
1. A manager deletes in Sales an open check that already sent rounds: a moment later, without reloading,
   Kitchen cancels the ones still under way, with their dishes; they leave the display and stay in the
   History as cancelled. If the round came out on paper, the slip "CANCELLED · Table 4" comes out with
   what was left to cook (KITCHEN-F22).
2. Two checks are joined: the rounds sent from the absorbed one move to the one that stays, like their
   dishes, in the same state and with their label; on charging the one that stays they close like its
   own.
In: from Sales, the voided check or the lines that changed check.
Out: rounds cancelled (announces: ticket cancelled) or of another check.
If it fails: a round already Served or Cancelled is not touched. A check without rounds under way changes
nothing in the kitchen, and neither does a repeated notice: no round is cancelled twice.
Involved: SALE-F18, SALE-F24, KITCHEN-F19, KITCHEN-F22, KITCHEN-F25, KITCHEN-F27

### KITCHEN-F29 Void a dish already sent, with a notice to the kitchen
Status: done
Actor: manager (at the till)
Screen: Sales: Sell
Steps:
1. At the till a line already sent is voided, with its reason (SALE-F20).
2. A moment later, on the kitchen display and without reloading, that dish shows struck through with
   "Voided" and the reason; it cannot be touched, "Ready" no longer includes it and it stops counting in
   "All-Day" and in "In progress".
3. The round goes on with what is left: if nothing live is left, it moves to Cancelled; if what is left is
   already ready, it moves to Ready.
In: from Sales, the voided line and its reason.
Out: the dish Voided (announces: dish voided; History "Dish voided" with the reason). If the round came out
on paper, the slip "VOIDED DISH · Table 4" comes out with that dish.
If it fails: a Served or Cancelled round is not touched.
Involved: SALE-F20, COMBO-F11, KITCHEN-F06, KITCHEN-F10, KITCHEN-F15, KITCHEN-F19, KITCHEN-F25

### KITCHEN-F30 Move the tickets of a customer merged into another
Status: discarded — the ticket does not keep a customer: merging two customer records does not touch Kitchen
Actor: nobody in Kitchen (Customers does the merge)
Screen: none
Steps:
1. In Customers two records of the same person are merged (CUSTOMER-F13) and Sales moves their sales to
   the one that stays (SALE-F33).
2. Nothing happens in Kitchen: the ticket keeps the check's label as text and no customer, so there is
   nothing to move.
In: nothing; the till does not send the customer to Kitchen.
Out: nothing; the tickets do not change.
If it fails: not applicable: Kitchen does nothing that could fail.
Involved: CUSTOMER-F13, SALE-F33

### KITCHEN-F31 Give Cash register the tickets still under way
Status: done
Actor: system
Screen: none
Steps:
1. On pressing "Close session" in Cash register, Cash register asks Kitchen which tickets are still under
   way.
2. Kitchen returns those To prepare, Preparing and Ready with their label, their number and their dishes;
   Cash register shows them in "Shift review" as "Kitchen tickets not served: N" (CASH_REGISTER-F08).
In: the query, with the permission to see tickets of whoever closes.
Out: the list; nothing changes in Kitchen.
If it fails: if whoever closes has no permission to see tickets, Cash register does not list them and warns
that the review may be incomplete ("What is still pending could not be checked, so this review may be
incomplete."). With Kitchen switched off there are no pending tickets. It never prevents closing the cash
register.
Involved: CASH_REGISTER-F08, CASH_REGISTER-F09, KITCHEN-F10, KITCHEN-F13
