<!-- generated from WORKBOOK.md sha256:68a8f4962634bea157331c8d8b86ba36f187e40840a7049a8c3ad334bff9ae35 -->

## What it is for and who it is for

Printing is where the business **adds its printers, says what comes out of each one and sees whether the
paper is coming out**. Each printer has a name ("Till", "Kitchen"), its connection (network, USB,
Bluetooth or the system printer), its paper width (58 or 80 mm) and its **role**: receipts,
kitchen, bar or labels. The other apps (Sales when charging, Cash register when closing the shift, Inventory for
the labels) **ask** Printing for their printouts, and Printing puts them in the business's **print queue**;
the device with the ERPlora app installed next to the printer turns them into paper and
confirms. Only **devices set up** with their printers print: a session on any other
device does not take anybody's paper. If something does not come out, the queue says so and lets you retry or cancel it.

Who uses it:

- The **owner** and the **administrator**: everything; they also retry and cancel stuck jobs.
- The **manager**: adds and changes printers, the devices that print and the settings, and asks for
  printouts.
- The **employee**: sees printers, settings and the queue, and asks for printouts (a test, a receipt).

It serves the hair salon and the restaurant alike: both print the receipt and the labels; the kitchen and
bar order is the restaurant's only.

Printing **does not compose** what is printed (the receipt belongs to Sales, the invoice to Invoicing, the
shift report to Cash register, the label to Inventory) and **does not talk to the printer**: the device's app
does. A browser does not reach the printers.

## Reference adopted

ERPlora does not invent flows: it adopts the ones the market has already proven.

- [Square — receipt, order and label printers](https://squareup.com/help/us/en/article/5530-set-up-a-printer):
  each printer is added in the point of sale with its name, its connection and what it prints
  (receipts, kitchen tickets, labels); one test print per printer.
- [Toast — printing and kitchen stations](https://doc.toasttab.com/doc/platformguide/platformKDSWorkflowUsingCourses.html):
  each document comes out of its station's printer; the kitchen order is not diverted to the receipt printer.
- [Toast — offline mode](https://doc.toasttab.com/doc/platformguide/platformOfflineMode.html) and
  [Square — offline mode](https://squareup.com/help/es/es/article/7777-process-card-payments-with-offline-mode):
  a job that cannot come out **waits** and it is flagged; recovering it does not duplicate it.
- Epson TM and Star (manuals of the 58 and 80 mm thermal printers): the paper width belongs to each
  printer, not to the business.
- Lightspeed and Odoo POS: the print queue with retry and "open drawer on checkout" through the
  receipt printer.
- [AEAT — SIF and VERI*FACTU](https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu.html):
  the receipt carries the verification QR and the reprint is a copy ("DUPLICATE"); the table's bill carries
  no number, QR or payment, and warns that it is not an invoice. Whoever composes the document puts that in.

## Before you start

- **Switch Printing on** in the business. It needs no other app.
- **The ERPlora app installed** on the device next to the printer (on its network, with its
  USB cable or paired by Bluetooth). That device takes the paper out of the queue; from a browser
  the printers cannot be reached.
- A **thermal printer** (ESC/POS) for receipts, orders and labels, switched on; for A4 (a
  full invoice), the computer's system printer.

Initial setup, step by step:

1. Open **Printing → Printers** and press "Add printer". Type its name, choose the connection,
   type its address (the IP from its configuration sheet, the Bluetooth MAC or the name of the USB
   queue), the paper width and its role (PRINTING-F03, PRINTING-F04).
2. On the device next to the printer, open **Printing → Devices**, press "Print
   from this device", give it a name and tick the printers it reaches (PRINTING-F18). Until it
   reaches a receipt printer, Home reminds you with "Set up your printer" (PRINTING-F01).
3. Press "Test" on the printer's row and check that the test page comes out (PRINTING-F05).
4. In **Printing → Settings** decide whether the receipt comes out on its own when charging, whether the drawer
   opens with it, how many copies and, if you have several printers with the same role, which one is each role's
   (PRINTING-F06).
5. The receipt header and footer are written in the Sales settings, not here.
6. Charge a test sale and check in **Printing → Queue** that the job comes out and ends up "Printed"
   (PRINTING-F07, PRINTING-F01).

## Screens

Four tabs at the bottom, the same as the menu: **Printers**, **Devices**, **Queue** and **Settings**.

### Printers
Menu **Printing → Printers**. Title "Printing" and the sentence "Add the business's printers, say what each one
prints and check that paper comes out.". Two areas, in this order:

- **Print queue**: one card for each role that has a printer or jobs
  waiting (a new business sees none), with its name ("Receipt", "Kitchen", "Bar",
  "Label"), its state ("Ready", "Waiting, no printer", "No device", "Device off", "With errors"), "Waiting: N · the
  oldest has waited 3 min" or "Nothing waiting", the failed ones ("Failed: N") and which printer it comes out of now:
  "Prints on: Till." (the one chosen in the settings or, if none, the first active one with that role). If
  it has jobs waiting that no device set up can take out, "No device" shows with
  "No device set up here prints it: set one up in Devices.". If the device is set up
  but has given no sign for 90 s and some job has already waited a minute, "Device off" shows with "The device
  that prints it is not responding: switch it on and open the ERPlora app on it.". A
  role with jobs waiting more than a minute and no active printer raises the orange warning
  "3 print jobs for Kitchen have been waiting 3 min. No active printer has this
  role: add one below or give this role to one of them." ("1 print job … has been waiting …" if there is one). With
  everything empty: "All clear: nothing is waiting in the queue.". Read error: "Could not read the print
  queue." with "Retry".
- **Printers**: the table (or cards on the phone) with Name, Role, Connection, Address, Paper,
  Status and Active. The status is "Ready", "Waiting" (it has jobs that have not come out for more than a
  minute), "With errors" (the last attempt failed: underneath, "Last error: …") or "Inactive". Per row:
  "Edit", "Test" and "Deactivate"/"Activate". At the top, "Search printers" (PRINTING-F02) and "Add
  printer". Empty: "No printers yet. Add the one at your till by its address.". A note reminds that the paper is
  taken out by the ERPlora app on the device next to the printer; in a browser it adds "a browser cannot reach
  printers", and inside the app it does not talk about browsers.

The **New printer / Edit printer** window has "Name", "Connection" ("Network", "USB", "Bluetooth",
"System printer (A4)"), "IP address or name" and "Port" (network; 9100 from the factory), "Bluetooth
MAC" (Bluetooth), "USB queue name" (USB), "Paper width" (80 mm or 58 mm; not on the system
one; underneath, "Kept with the printer: the ERPlora app prints 32 characters a line for now,
whatever the paper."), "Role" and "Active", with "Save" and "Cancel".

The **Search printers** window lists what the device's app finds (name, connection and
address), each one with "Add" or "Already added", with "Search again", "Add by its address" and
"Close"; while it searches, "Searching for printers…".

Whoever cannot change printers does not see "Search printers", "Add printer", "Edit" or
"Deactivate"; whoever cannot print does not see "Test".

### Devices
Menu **Printing → Devices**. Title "Devices that print" and the sentence "Only the devices set up here
print the queue, with anybody’s session: set up the one next to the printers from that
device.". Underneath, a note about the device it is being looked at on: "This device prints for: Till,
Kitchen." (in green); if it is not set up, to whoever manages the printers "This device does not print yet:
«Print from this device» sets it up with the printers it reaches." and to everybody else "This device does not
print here: someone who manages the printers sets it up from it.".

The table (or cards on the phone), by name: Name (with "This device" on its own), Printers (an
inactive one, "Kitchen (inactive)"), Last seen ("3 min ago" or "Never") and Set up by. Whoever manages
the printers sees "Print from this device" at the top (only if this one is not set up) and on each row
"Edit" and "Retire". Empty: "No device prints yet. Set up the one next to the printers
from that device.". Error when loading: "Could not load the devices." with "Retry".

The **Print from this device / Edit device** window explains "Only the devices set up here print, with
anybody’s session. Choose the printers this device reaches: on its network, by
its cable or paired by Bluetooth." and has "Device name" and "Printers it reaches" (one
checkbox per active printer, "Till · Receipt"), with "Save" and "Cancel". Without a name: "Type its name."; without
printers: "Choose the printers this device reaches."; with no active printer at all: "There is no
active printer yet: add one in Printers first.". "Retire" asks "Retire Counter till?"
with "It will print nothing more, and the jobs it has go back to the queue. To print from it again, set it
up again from it.", "Yes, retire" and "Back".

### Queue
Menu **Printing → Queue**. Title "Print queue". The table of jobs, from the most recent to the
oldest, 50 per page: Document ("Receipt T-000123", or "Receipt · 14/10/26 23:05" if it carries no number),
Role, Printer, Status ("Pending", "Sent", "Printed", "Failed", "Cancelled"), Attempts, Asked on
and Detail ("Last error: …", "No answer from the device", "Cancelled by Ana · Reason: …", "Sent again
by Ana"). Filters by status, role and printer, and a search by document number. Whoever may
manage the queue sees on each row "Try again" and "Cancel" on a job that is waiting, failed, or sent and
without an answer once its time is up; "Cancel" opens a window with "Reason (optional)", "Yes, cancel" and
"Back". Empty: "No print jobs.". Error when loading: the message with "Retry".

### Settings
Menu **Printing → Settings**. A card "Ticket settings" with "Print receipt on checkout", "Open drawer on
checkout" and "Receipt copies" (1, 2 or 3); another "Printer of each role" with a dropdown per
role ("Receipt", "Kitchen", "Bar", "Label"): "The first active one of this role" or one of its
active printers. The note "The receipt header and footer are part of your till settings,
where the ticket is printed from." with the link "Open the receipt settings" (if Sales is switched on). "Save settings" saves what
changed and says "Settings saved.". Whoever cannot change them sees them locked with "You do not have permission
to change these settings.". Loading: "Loading settings…". Error: "Could not load the
settings." with "Retry"; when saving, "Could not save the settings." with the reason.

## States of each screen

| State | What the person sees |
|---|---|
| Loading | "Loading…" (in Settings, "Loading settings…") while the first result arrives. |
| Empty | Printers: "No printers yet. Add the one at your till by its address."; Devices: "No device prints yet. Set up the one next to the printers from that device."; Queue: "No print jobs."; the state of printing, "All clear: nothing is waiting in the queue.". |
| Error | The warning of its screen with "Retry"; a refused action shows in its window, next to its field, or in a notice. |
| Reconnecting | What is drawn stays; a strip warns "Reconnecting…" until the connection comes back. |
| App inactive | "Printing is not active in this business." |
| No permission | What they cannot do does not appear (in Devices, neither "Print from this device", nor "Edit", nor "Retire"); the settings show locked with "You do not have permission to change these settings.". |

## Flows

| ID | Flow | Vertical | Status |
|---|---|---|---|
| PRINTING-F01 | See how printing is going | common | done |
| PRINTING-F02 | Find a network printer without typing its address | common | discarded — on a network without internet access the device's app does not go through the network (app#17) |
| PRINTING-F03 | Add a printer by its address | common | done |
| PRINTING-F04 | Assign what comes out of each printer | common | done |
| PRINTING-F05 | Do a test print | common | done |
| PRINTING-F06 | Choose how the business prints | common | done |
| PRINTING-F07 | Print the receipt when charging | common | done |
| PRINTING-F08 | Reprint a receipt or an invoice | common | done |
| PRINTING-F09 | Print the table's bill | restaurant | done |
| PRINTING-F10 | Print the order in the kitchen and at the bar | restaurant | done |
| PRINTING-F11 | Reprint an order | restaurant | done |
| PRINTING-F12 | Print a barcode label | common | done |
| PRINTING-F13 | Open the drawer when charging | common | done |
| PRINTING-F14 | Get a print job unstuck | common | done |
| PRINTING-F15 | Take the old receipt text to Sales | common | done |
| PRINTING-F16 | Send to print from the assistant | common | done |
| PRINTING-F17 | Print the cash register closing | common | done |
| PRINTING-F18 | Take the paper out: the device picks up and confirms the jobs | common | done |
| PRINTING-F19 | See the state of a printer | common | done |
| PRINTING-F20 | How long the hub keeps the print jobs | common | done |

### PRINTING-F01 See how printing is going
Status: done
Actor: administrator, manager, employee
Screen: Home, Printers, Queue
Steps:
1. On **Home**, while no device set up reaches an active receipt printer,
   "Finish setting up your business" brings "Set up your printer" ("Register the device that
   prints your customers' receipts, so the first sale comes out on paper."), "Recommended", to
   whoever manages the printers. "Set up" leads to **Printing → Devices** (PRINTING-F18); the
   step is "Done" as soon as that device is set up, switched on or not.
2. If a role has jobs that have been waiting a minute or more and no switched-on device can take
   them out (none set up reaches its printer, or they wait for a printer and none reaches one of its role,
   or the one that reaches it has given no sign for 90 s: it is off or without the ERPlora app open), the bell of
   everybody who sees Printing shows one row per role: "Nothing is printing “Receipt”" (or "Kitchen", "Bar",
   "Label") with how many are waiting. Tapping it opens **Printing → Printers**, where the card of that
   role says why: "No device" and "No device set up here prints it: set one up in
   Devices.", "Device off" and "The device that prints it is not responding: switch it on and open the
   ERPlora app on it." or "Waiting, no printer" if it has no active printer.
3. Open **Printing → Printers**: the role cards say whether each one has a printer and which one
   prints it, how many are waiting and since when.
4. Open **Printing → Queue** to see each job with its status, its attempts and its last
   error.
5. If a role shows "Waiting, no printer" or there is an orange warning, the paper is not coming
   out: go on with PRINTING-F04 (give the role to a printer) or PRINTING-F14 (get the job
   unstuck).
In: the business's queue, printers and devices.
Out: nothing saved. What depends on the clock (how long it has been waiting, the orange warning, "Waiting",
"Device off" on the role's card and a sent job that did not answer in time) is recalculated on its own every
30 s, without waiting for another change or reloading; "All
clear" requires nothing waiting, sent without confirmation or failed. The screens refresh on their own when a job is queued, sent, printed, fails,
is retried or is cancelled. The Home step and the bell rows change on their own, without
reloading, when a job is queued, fails or is cancelled, when a
device is set up, changed or retired and when a printer changes; what the clock moves (a job that
reaches the minute, a device that stops giving signs or comes back) is picked up on its own every 30 s by the bell, like
the old Hub's, and by the role's card while something is waiting (a read that fails keeps the last one). The row goes away on its own
when a switched-on device can take out what is waiting (there is no "mark as read").
If it fails: "Could not read the print queue." with "Retry"; "All clear" is not drawn when
the read fails. A device that is set up but switched off does make the bell ring, once the minute has passed: the Home
step stays "Done" (being set up is enough), but nobody is printing. A job that has waited less than a
minute does not make it ring (a device that restarts is not an alarm).
Involved: PRINTING-F14, PRINTING-F18, CASH_REGISTER-F08, BASE-F01

### PRINTING-F02 Find a network printer without typing its address
Status: discarded — the search is in Printers and the ERPlora app on the device does it for the
business opened from it at erplora.com, but on a network without internet access the app does not go
through the network and only finds the printers that announce themselves; that printer is added by its address (PRINTING-F03)
(app#17)
Actor: administrator, manager
Screen: Printers
Steps:
1. In **Printing → Printers**, press "Search printers".
2. The device's app searches the network (on the phone, also the paired Bluetooth ones; on the
   computer, its USB queues) and lists what it finds: name, connection and address. The ones the business
   already has say "Already added"; office printers (A4) are not offered.
3. Press "Add" on the one you want: "New printer" opens with its name, connection, address and
   paper already filled in; choose its "Role" and press "Save" (PRINTING-F03).
4. If it does not show up, "Search again" or "Add by its address".
In: what the device's app finds.
Out: the printer added to the business, as in PRINTING-F03.
If it fails: from a browser, "A browser cannot search for printers: add it by its
address."; without permission for the local network, "The app is not allowed to search the local network: allow it
in the device’s settings and search again." (never an empty list); with the app not linked, "This
app is not linked to this business: open the business from the app to search for its printers."; if the search
fails, "Could not search for printers."; with no results, "No printer found. Check
that it is on and on the same network, or add it by its address.".
Involved: PRINTING-F03

### PRINTING-F03 Add a printer by its address
Status: done
Actor: administrator, manager
Screen: Printers
Steps:
1. Press "Add printer".
2. Type the "Name" ("Till", "Kitchen"), choose the "Connection" and type its address: the IP (or the
   network name) and the port for a network one (the IP is on the configuration sheet the printer prints
   when you switch it on with the feed button held down); the MAC for a paired Bluetooth one; the
   name of the system queue for a USB one. The "System printer (A4)" carries no address: it is
   the computer's.
3. Choose the "Paper width" and the "Role", and press "Save".
4. "Printer added" shows and it appears in the table.
In: the name, the connection, the address, the paper and the role.
Out: the business's printer (announces: `printing.printer.created`).
If it fails: the field marked with the reason: "There is already a printer with that name.", "Type a valid IP or
network name (for example 192.168.1.100).", "The port goes from 1 to 65535.", "Type the MAC
as AA:BB:CC:DD:EE:FF.", "Type the print queue's name as the system gives it (no
spaces, slashes or #).", "The system printer prints A4 pages: give it the Receipt role.". Without
a name, "Give the printer a name.".
Involved: PRINTING-F04, PRINTING-F05

### PRINTING-F04 Assign what comes out of each printer
Status: done
Actor: administrator, manager
Screen: Printers, Settings
Steps:
1. When adding or editing a printer, choose its "Role": "Receipt" (receipt, invoice, the table's
   bill, cash register report, delivery note), "Kitchen" (orders), "Bar" (bar orders) or "Label"
   (barcode labels).
2. If there are several printers with the same role, in **Settings → Printer of each role** choose the
   one that prints it; if you do not choose, it comes out of the first active one with that role (by name).
3. "Deactivate" leaves a printer out without deleting it: it gets no new jobs and its jobs that are
   waiting keep waiting (retrying them sends them to whichever printer fits then).
In: each printer's role and, if there are several, the chosen one.
Out: each document comes out of the printer of its role. A printer is not deleted: the queue names it.
If it fails: if no active printer has the role, the job **waits** in the queue without a
printer ("Waiting, no printer") and comes out as soon as one has it. In settings, a printer of another
role or an inactive one is refused: "That printer does not have this role.", "That printer is inactive.".
Involved: PRINTING-F01, PRINTING-F06, INVENTORY-F25

### PRINTING-F05 Do a test print
Status: done
Actor: administrator, manager, employee
Screen: Printers
Steps:
1. Press "Test" on the printer's row.
2. "Test page sent to the queue of Till." shows and "Test page" appears in the queue.
3. The device that prints for that printer, with the ERPlora app open, takes it out right away
   (PRINTING-F18): the business's name (the one Invoicing has; without Invoicing or without permission to read it,
   "ERPlora"), "Printer OK", the date and the printer's address. A system printer prints the page in
   A4 with the same. In the queue, the page ends up "Printed".
In: the printer.
Out: a "Test page" job for that printer (announces: `printing.job.queued`).
If it fails: an inactive printer is not tested: "That printer is inactive: activate it to test it.".
If the paper does not come out, the page goes back to the queue with the device's error and, after 5 attempts, ends up "Failed"
(PRINTING-F14).
Involved: PRINTING-F18

### PRINTING-F06 Choose how the business prints
Status: done
Actor: administrator, manager
Screen: Settings
Steps:
1. Open **Printing → Settings**.
2. Switch "Print receipt on checkout" and "Open drawer on checkout" on or off, choose the "Receipt
   copies" and, if you want, the printer of each role.
3. Press "Save settings". What you changed is saved; the rest stays as it was.
In: the business's decisions.
Out: the print settings, a single row (announces: `printing.settings.updated`). Without saving,
the factory ones always hold: receipt on checkout on, drawer off, one copy, no printer chosen.
If it fails: "Could not save the settings." with the reason. If the read fails, the screen does not
show values and offers "Retry". Without permission, locked and without "Save settings".
Involved: PRINTING-F07, PRINTING-F13

### PRINTING-F07 Print the receipt when charging
Status: done
Actor: employee
Screen: Sell (from Sales)
Steps:
1. The employee charges in **Sales → Sell**.
2. Together with the charge, Sales asks Printing for the receipt: the simplified receipt or the full invoice,
   with the VeriFactu QR.
3. If "Print receipt on checkout" is on, the receipt goes into the queue of the Receipt role
   with the copies from the settings and, if "Open drawer on checkout" is on and cash came in, with the
   order to open the drawer (PRINTING-F13); the device takes it out (PRINTING-F18). After charging, Sales says
   which printer it went to.
4. With Printing not switched on, without an active receipt printer or with the fiscal document still pending,
   nothing is queued: the receipt comes out through the device's dialog, as before. Repeating the same charge
   does not print another receipt.
In: the receipt composed by Sales.
Out: a job in the queue, or nothing if the business does not print when charging.
If it fails: a sale **never fails** because of printing: if Printing is not switched on, refuses the receipt or
fails, Sales charges anyway and the receipt comes out through the device's dialog. A job that does not come out stays in
the queue (PRINTING-F14).
Involved: SALE-F08, PRINTING-F13, PRINTING-F18

### PRINTING-F08 Reprint a receipt or an invoice
Status: done
Actor: administrator, manager, employee
Screen: Sales, Invoices (from those apps)
Steps:
1. On the sale's or the invoice's card, press "Print" ("Print / PDF" in Invoices).
2. Sales asks Printing for the receipt (or the full invoice) marked as a copy ("DUPLICATE"); Invoicing
   asks for the invoice's A4 page, in the language of whoever prints and with its VeriFactu QR, for the
   system printer. The screen says which printer it went to.
3. With Printing not switched on, without a printer that accepts it (a receipt one for the receipt; a system one for the
   A4 page) or with the fiscal document still pending, nothing is queued: it comes out through the device's
   dialog, as before.
In: the document marked as a copy.
Out: a job in the Receipt queue; an A4 invoice goes to the system printer. Each press, one
paper.
If it fails: as in F07.
Involved: SALE-F31

### PRINTING-F09 Print the table's bill
Status: done
Actor: employee
Screen: Sell (from Sales)
Steps:
1. With the bill open, press "Print bill".
2. Sales asks for the bill (no number, no QR, no payment and with the warning that it is not an invoice) and the screen
   says which printer it went to; with Printing not switched on or without an active receipt printer, it comes out through the
   device's dialog, as before.
In: the bill with its lines.
Out: a job in the Receipt queue. Each press prints one bill.
If it fails: "A bill has lines to charge for: this one has none.".
Involved: SALE-F15

### PRINTING-F10 Print the order in the kitchen and at the bar
Status: done
Actor: employee
Screen: Sell (from Sales)
Steps:
1. In **Sales → Sell**, with the bill open, the waiter presses "Send order" (or "Send
   RUSH").
2. Kitchen opens the order and asks Printing for one sheet per printer: the dishes of each station, by their
   role ("Kitchen" or "Bar") or by the station's own printer (KITCHEN-F08).
3. Each sheet goes into the queue of the printer of its role with the table, the number, the round, the
   waiter and its dishes, each one with its extras (one line each) and its note; the device
   takes it out (PRINTING-F18).
In: the order from Kitchen (table, waiter, round and dishes).
Out: one job per printer in the Printing queue.
If it fails: the order is not diverted to the receipt printer: without a printer of its role, it waits in the
queue ("Waiting, no printer") and comes out as soon as one has it. Paper never blocks the waiter.
Involved: KITCHEN-F08, KITCHEN-F18, PRINTING-F04, PRINTING-F18

### PRINTING-F11 Reprint an order
Status: done
Actor: employee, manager
Screen: Tickets (from Kitchen)
Steps:
1. In **Kitchen → Tickets**, on the order's row, "⋮ → Reprint".
2. Kitchen asks Printing for another sheet for each printer of its dishes, marked as a copy (KITCHEN-F09).
In: the order.
Out: a new job with another key each time, in the queue of the printer of its role.
If it fails: as in PRINTING-F10; if Printing refuses it, Kitchen says its reason.
Involved: KITCHEN-F09, PRINTING-F10

### PRINTING-F12 Print a barcode label
Status: done
Actor: administrator, manager, employee
Screen: Product card (from Inventory) and Printers
Steps:
1. In **Inventory → Products**, open the product's card and press "Print barcode"
   (INVENTORY-F25).
2. Inventory asks Printing for the label: it goes into the queue of the printer with the "Label" role,
   with the product's name, its SKU as the barcode and its price. The printer draws the code
   and the device that picks up that printer's jobs takes it out (PRINTING-F18).
3. In **Printing → Printers**, the "Label" card of "Print queue" says how many are waiting and which
   printer they come out of.
In: the product's name, its SKU (the barcode) and its price in the business's currency.
Out: a job in the Label queue. Each press prints one label.
If it fails: without a printer with the "Label" role, the label **waits** in the queue (it never comes out of the
receipt printer) and the "Label" card says so: "Waiting, no printer" and "Waiting: N". As soon as
a printer has that role, the card names it ("Prints on: …") and turns "Ready" if a set-up device
reaches it (if not, "No device"); that device takes out the labels that were waiting, from the
oldest to the newest.
Involved: INVENTORY-F25, PRINTING-F01, PRINTING-F04, PRINTING-F18

### PRINTING-F13 Open the drawer when charging
Status: done
Actor: employee
Screen: Sell (from Sales)
Steps:
1. With "Open drawer on checkout" on in **Printing → Settings**, charge in **Sales → Sell** with
   cash (alone or in a mixed payment).
2. The charge (F07) asks for the receipt with the order to open the drawer connected to the receipt printer; with
   the receipt switched off, a drawer-only job. A charge without cash (card, Bizum…) does not open the drawer,
   as in Square, Toast, Odoo, Shopify and Lightspeed: there is nothing to put in it.
3. The device that prints the receipts takes out the receipt and, afterwards, opens the drawer (PRINTING-F18).
In: the setting and whether the charge carried cash.
Out: the order to open the drawer, in the same job as the receipt; the device sends it to the drawer
when it takes out the job (PRINTING-F18).
If it fails: if the receipt does not come out, the drawer does not either; the job goes back to the queue (PRINTING-F14). If the receipt comes out and the
drawer does not answer (the printer was switched off, or the drawer is not connected to it), the device's screen says so:
"The cash drawer did not open: check that “Till” is on and connected.", and the receipt, which already came out, is not
printed again; the drawer is opened by hand. A drawer-only job that does not open warns the same way and goes back to the queue with
the device's error.
Involved: PRINTING-F06, PRINTING-F07

### PRINTING-F14 Get a print job unstuck
Status: done
Actor: owner, administrator
Screen: Queue
Steps:
1. In **Printing → Queue**, find the "Failed" job, the "Sent" one that did not answer ("No answer from the
   device") or the one still "Pending".
2. "Try again" sends it back to the queue with the attempts at zero, towards whichever printer fits now:
   "Sent back to the queue: the next device to connect will print it.".
3. "Cancel" asks for a reason (optional) and withdraws it: "Job cancelled. It will not be printed.". It stays in
   the queue with who, when and why.
In: the job and, when cancelling, the reason.
Out: the job waiting again or cancelled (announces: `printing.job.retried`, `printing.job.cancelled`); nobody
deletes it by hand: the queue forgets it 30 days after it finished (PRINTING-F20).
If it fails: "Only a pending or failed job, or a sent one that did not answer, goes back to the queue; this one is
…", "A job that is printing or has printed is not cancelled; this one is …". Without permission the
buttons are not seen.
Involved: PRINTING-F01

### PRINTING-F15 Take the old receipt text to Sales
Status: done — there is no old text to take: the receipt header and footer live in the
Sales settings from the start, and the Settings note leads there
Actor: administrator
Screen: Settings
Steps:
1. Open **Printing → Settings**.
2. The header and footer note leads, with "Open the receipt settings", to the Sales settings,
   where the receipt text is written.
In: nothing.
Out: nothing: the receipt text is saved in the Sales settings.
If it fails: with Sales switched off, the note shows without the link.
Involved: SALE-F02

### PRINTING-F16 Send to print from the assistant
Status: done
Actor: administrator, manager, employee
Screen: Assistant
Steps:
1. Ask the assistant "Print a test on the kitchen one", "retry the failed label
   jobs" or "how is the till's printer doing?".
2. The assistant does the same as the screens, naming the printer by its name and the job by
   its number, and answers with what it has done. Before changing something, its confirmation card says the
   printer and the device by their name, the job as the queue titles it (its document and its number) and
   the document of a new job with the queue's word, never by an identifier; what whoever
   asks cannot see, or what is no longer there (a retired device), does not show on the card.
In: the request.
Out: the same as the screen.
If it fails: the same as the screen, with the server's words.
Involved: PRINTING-F05, PRINTING-F14, PRINTING-F19

### PRINTING-F17 Print the cash register closing
Status: done
Actor: employee
Screen: Session detail (from Cash register)
Steps:
1. In the session detail, "Print".
2. Cash register asks Printing for the X report (open session) or the Z report (closed) for the Receipt role, and says which
   printer it went to.
3. With Printing not switched on or without an active receipt printer, nothing is queued: the device's dialog
   prints it, as before.
In: the report (session, cashier, float, closing and movements).
Out: a job in the Receipt queue; each press, one paper.
If it fails: as in F07.
Involved: CASH_REGISTER-F16

### PRINTING-F18 Take the paper out: the device picks up and confirms the jobs
Status: done
Actor: the owner, the administrator or the manager (they set up the device) and the device's app
(it picks up)
Screen: Printing → Devices
Steps:
1. On the device next to the printers, whoever manages the printers opens **Printing →
   Devices**, presses "Print from this device", gives it a name ("Counter till") and ticks the
   printers it reaches. From that moment that device prints with anybody's session: the list
   marks it "This device" and the note says "This device prints for: …". If whoever manages the printers
   prints from a new device on some active printer, it is also set up, as "Device 1",
   with the active printers it uses.
2. With the ERPlora app open on that device —on any screen and with anybody's session—, the app
   connects to Printing to print: it says which device it is and which are the printers of its setup, and from there on
   it takes out on its own the paper of its active printers as soon as it reaches the queue, without anybody touching anything. In a browser
   it does not connect: no printer can be reached from it.
3. The device asks for the next job of its printers. Printing gives it the oldest one waiting (for that
   printer, or without a printer and of its role), marks it "Sent" with a 90 s deadline, adds one attempt and notes
   which device has it, by its name. While it prints one, it does not ask for another of the same role:
   when it finishes it, it asks for the next one, until the queue is empty.
4. The device prints it —the first copy as the original and the others of a receipt or an invoice
   as "DUPLICATE"— and confirms: "Printed". If it could not, it reports the error: it goes back to the queue up to 5 attempts and
   then ends up "Failed". After a failure, the device does not ask for that role again until another
   job arrives, somebody presses "Try again" in the queue or the app connects again: a printer without paper does not use up
   the 5 attempts in a moment.
5. If the device goes down without answering, once the deadline has passed the job goes back to the queue and the
   devices are told. If the connection drops, the app connects again on its own, waiting a little longer each time (up to
   30 s), and the first thing it does is confirm what it printed and did not get to confirm, so that it does not come out twice.
   If the session ends, the business is cancelled or suspended, Printing is switched off or the device stops
   printing for any printer, it stops trying.
6. While the ERPlora app on the device is connected to print, it says it is there when it connects and in
   each heartbeat (every 30 s), with the session of whoever uses it, an employee's too; setting it up from it and
   asking for a job also count. The list shows it in "Last seen". If 90 s pass without signs, it
   counts as switched off: its jobs make the bell ring once the minute has passed (PRINTING-F01).
7. From any device, whoever manages the printers changes in the list the name or the printers of
   a device ("Edit") or retires it ("Retire", after confirming it): the app on that device notices it
   at once, prints for its new printers or stops printing, and the jobs it had go back to the queue when
   their deadline expires. A retired device does not receive jobs again, not even with
   the session of whoever manages the printers: it has to be set up again from it ("Print from this
   device").
In: the device's name and the printers it reaches; when asking, its printers; when confirming, the
result.
Out: the device set up, changed or retired (announces: `printing.device.registered`,
`printing.device.updated`, `printing.device.retired`) and the job with its status (announces: `printing.job.claimed`,
`printing.job.printed`, `printing.job.failed`). That the device is there announces nothing to anybody: each heartbeat every
30 s would wake up every screen; the bell looks at the clock.
If it fails: a device nobody set up, or a retired one, picks up nothing even if the session can print: "This
device is not set up to print here: someone who manages the printers sets it up in Printing →
Devices.", and the queue does not change; printing from a retired device does not set it up again, nor
does printing from a new one only on inactive printers set it up. Asking
for jobs of a printer the device does not have is refused ("This device does not print for “Kitchen”…").
Confirming twice is one confirmation. A late confirmation from the same device (a slow printer with
copies goes past the 90 s and the job had already gone back to the queue) is accepted: the paper came out and it is not printed
again. A confirmation or a failure from another device, or from a hand-out that is not its own, is refused and changes
nothing. Setting up without a name or without active printers warns in its field, and it is only set up from the
device itself. The queue and the list name each device by its name, never by its identifier: with it
anybody could pretend to be the till.
Involved: PRINTING-F05, PRINTING-F07, PRINTING-F14

### PRINTING-F19 See the state of a printer
Status: done
Actor: administrator, manager, employee
Screen: Printers
Steps:
1. The "Status" column of each printer says "Ready", "Waiting", "With errors" or "Inactive", with
   its last error.
2. The assistant answers it by the printer's name.
In: the printer.
Out: its state, how many jobs are waiting and since when, when it last printed and its last
error.
If it fails: "There is no printer with that name.".
Involved: PRINTING-F01

### PRINTING-F20 How long the hub keeps the print jobs
Status: done
Actor: system
Screen: none
Steps:
1. A job stays in the queue while it waits, while the device prints it and after it
   finishes ("Printed", "Cancelled" or "Failed"), with its number, its role, its printer and its stamps; when
   it is printed or cancelled it already lets go of the document.
2. Every hour, the queue forgets the jobs that finished more than 30 days ago; one waiting or sent is never
   touched.
3. From that moment it no longer shows in **Printing → Queue** nor counts in the state of printing.
In: nothing: the platform does it on its own.
Out: the jobs finished more than 30 days ago, deleted (announces: `printing.job.pruned`, with
how many). Asking for the same document again afterwards puts it back in the queue.
If it fails: if one hour cannot clean up, the next one does; a job is never deleted before its
time.
Involved: PRINTING-F01, PRINTING-F14

## Services: what goes in and what comes out

The other apps and the assistant use Printing through these operations, by their name; never its tables.

### What it offers: queries (they read, they change nothing)

| What it gives | Who may | Flows | Service |
|---|---|---|---|
| The print settings (the factory ones if they were never saved) | view | F06 | `printing.settings.get` |
| The printers, with search by name, filters (role, connection, active) and pages, each one with its state | view | F03, F04, F19 | `printing.printer.list` |
| A printer by id or by name | view | F04 | `printing.printer.get` |
| The devices that print, by name, with their printers, who set them up, when they were last seen and which one is the one asking | view | F18 | `printing.device.list` |
| A device that prints, by its setup id, with its printers (a retired one is no longer there) | view | F16, F18 | `printing.device.detail` |
| The device set up with an identifier, with its printers (for the device's channel, when it connects; with no route or assistant) | print | F18 | `printing.device.get` |
| The state of a printer (by id or name) | view | F19 | `printing.printer.status` |
| The queue, from the most recent to the oldest, with search by document, filters (status, role, printer) and pages | view | F01, F14 | `printing.job.list` |
| A queue job by id or by its document's number (the most recent one), with its title as the queue puts it | view | F14, F16 | `printing.job.get` |
| The queue summary per role, with the printer each one comes out of, how many jobs no device set up can take out and how many have waited a minute without a switched-on device | view | F01 | `printing.job.summary` |
| Whether a role has a set-up device that prints it, switched on or not (the Home step), and how many of its jobs have waited a minute or more in the queue without a switched-on device to take them out (the bell) | view | F01 | `printing.device.coverage` |

### What it offers: actions (they change data)

| What it does | Who may | Flows | Service |
|---|---|---|---|
| Saves the settings (only what is sent) | settings | F06 | `printing.settings.update` |
| Adds a printer | settings | F03 | `printing.printer.create` |
| Changes a printer, or deactivates and activates it | settings | F04 | `printing.printer.update` |
| Queues a printer's test page | print | F05 | `printing.printer.test` |
| Queues a document (idempotent by its key) | print | F07–F13, F16, F17 | `printing.job.create` |
| Sets up the device it is asked from, with its name and its printers | settings | F18 | `printing.device.register` |
| Changes the name or the printers of a device | settings | F18 | `printing.device.update` |
| Retires a device: it no longer prints | settings | F18 | `printing.device.retire` |
| Notes that the device set up with an identifier is there (for the device's channel, when it connects and in each heartbeat; with no route, no assistant and no notice) | print | F01, F18 | `printing.device.seen` |
| Gives the set-up device the next job of its printers | print | F18 | `printing.job.claim` |
| Confirms a printed job | print | F18 | `printing.job.complete` |
| Reports that a job did not come out | print | F18 | `printing.job.fail` |
| Sends a failed or unanswered job back to the queue | queue | F14 | `printing.job.retry` |
| Cancels a job | queue | F14 | `printing.job.cancel` |

### What it announces

| Notice | When | What it carries | Service |
|---|---|---|---|
| Settings saved | Saving the settings | Which fields changed | `printing.settings.updated` |
| New printer | Adding a printer | Which one | `printing.printer.created` |
| Printer changed | Editing it, deactivating it or activating it | Which one and which fields | `printing.printer.updated` |
| Job waiting | Queuing (also retrying) | The job, its role and its printer | `printing.job.queued` |
| Job sent | A device picks it up | The job and its printer | `printing.job.claimed` |
| Job printed | The device confirms | The job | `printing.job.printed` |
| Job failed | The device reports the error | The job and whether it is no longer retried | `printing.job.failed` |
| Job sent back to the queue | Retrying | The job | `printing.job.retried` |
| Job cancelled | Cancelling | The job | `printing.job.cancelled` |
| Jobs forgotten | The hourly clean-up deletes what finished more than 30 days ago | How many | `printing.job.pruned` |
| Device set up | Setting it up (or whoever manages the printers printing from it for the first time) | Which one (its record, never its identifier) | `printing.device.registered` |
| Device changed | Changing its name or its printers (or whoever manages the printers printing from it on another printer) | Which one | `printing.device.updated` |
| Device retired | Retiring it | Which one | `printing.device.retired` |

The notices do not carry the document (it may have a customer's name or tax ID): only ids.

### What it reacts to

Nothing. The apps that print call `printing.job.create` by its name, inside their own
transaction (the sale's, the closing's), and do not wait for a notice.

### What it needs from other apps

Nothing (`requires = []`). It reads nobody's models: whoever prints sends the document already composed.

### Who uses it

| App | What for | Service |
|---|---|---|
| Sales | Receipt when charging (with the drawer if cash came in), reprint and the table's bill | `printing.job.create` |
| Invoicing | An invoice's A4 page, for the system printer | `printing.job.create` |
| Cash register | X and Z report | `printing.job.create` |
| Inventory | Barcode label | `printing.job.create` |
| Kitchen | Each station's order and its reprint | `printing.job.create` |
| `base` (`/ws/print`) | Hand out and confirm jobs | `printing.job.claim`, `printing.job.complete`, `printing.job.fail` |
| `base` (Home and bell) | "Set up your printer" and "Nothing is printing “…”" | `printing.device.coverage` |

### Who may do what

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| View printers, settings and queue | yes | yes | yes | yes | `printing.view_settings` |
| Printers, devices that print and settings | yes | yes | yes | no | `printing.manage_settings` |
| Print (ask, test and, from a set-up device, pick up and confirm) | yes | yes | yes | yes | `printing.print` |
| Retry and cancel jobs | yes | yes | no | no | `printing.manage_jobs` |
