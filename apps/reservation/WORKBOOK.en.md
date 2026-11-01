<!-- generated from WORKBOOK.md sha256:1ea9b651641629fe99ba095dc9ffab2eb00820946aaa4d01aadb75aa22f412b6 -->

## What it is for and who it is for

Reservations is the **reservation book of the restaurant or bar**: it decides when and for how many
people reservations are taken (time slots with a maximum of reservations and, if wanted, of guests,
inside the business's opening hours; and blocked days), notes down each reservation with its customer and
its table, takes it from Pending to Completed and keeps on a **waitlist** whoever does not fit.

Who uses it:

- The **employee** who picks up the phone or attends the door (the host or the server) notes down,
  confirms, seats, changes and cancels reservations and keeps the waitlist.
- The floor **manager**, besides, creates the slots, blocks days and changes the rules.
- The **administrator** and the **owner**, besides, delete reservations for good.

Reservations does not paint the floor plan (that is **Tables**: it sets aside the table of each confirmed
reservation), does not charge (that is **Sales**) and is not the appointment book of a hair salon (that is
**Appointments**).

## Reference adopted

ERPlora does not invent flows: it adopts the ones the market has already proven (OpenTable, Resy,
SevenRooms, Toast Tables, Square, Lightspeed, TouchBistro, Tablein, TablesReady, CoverManager, TheFork
Manager, Odoo). The open questions of the current product were resolved like this; the research, with its
sources, is in "Market research", at the end of this manual.

- **Book by day and by service**, with the day's **covers** and how much is left free in the next slot;
  the full slot is seen **dimmed and marked "Full"**, it is not hidden (OpenTable, Resy).
- **Life cycle of the reservation**: pending → confirmed → seated → completed, plus cancelled and
  no-show; there is no going back.
- **The host manages the whole reservation** (question 1): the floor employee confirms, seats, changes,
  cancels and marks no-shows, and keeps the waitlist; what belongs to the manager is the slots, the
  blocks and the rules.
- **The capacity of the slot is counted in reservations and, if wanted, also in guests** (question 2):
  the usual maximum of reservations and an optional maximum of guests; the slot closes with whichever is
  reached first, like ResDiary, OpenTable and HostMe.
- **Seating the reservation seats the table** (question 3): "Seat" opens the check of its table in Tables
  and Sales in the same step. An occupied table is refused (it has to be freed or the reservation moved to
  another table), unless that same party was already seated at it from the floor plan: then only the
  reservation is marked.
- **All the actions are in the list** (question 4): edit (also the table), confirm, seat, complete,
  cancel with a reason, no-show and delete.
- **A table is not booked twice at the same time** (question 5): when picking a table, the ones free at
  that time that fit the party are offered; two reservations at once on the same table and time leave
  one. The market warns and lets the staff overbook the table; here Ioan's brief rules (a single
  reservation per table and time), and it stays flagged as a contradiction. Automatic assignment and
  joining tables are not included (see "What is left out").
- **The waitlist is for a day and a time** (question 6), today or later, in the order in which people
  were added; when there is room it becomes a reservation in one tap. The market separates the door queue
  (with an estimated wait and SMS) from the list for full days; without messaging, here it is one list for
  both things (see "What is left out").
- **The phone is required out of the box on the reservation** (question 7), and always the same (the
  current product did not ask for it until any setting was saved); the email, not. The waitlist asks for
  nothing but the name: the phone only serves to call.
- **The booking rules are for the customer who books by themselves** (question 8): minimum and maximum
  guests, minimum notice, maximum days and the full slot bind the reservations made online or through
  WhatsApp. The staff books from now on (never a past time), any party and any date, and can fill a full
  slot knowingly: the system warns and asks "Book anyway".
- **Table reserved from one hour before** (question 8, decided by Tables, TABLE-F25): before that the
  table stays free and shows "Ana · 21:00".

## Before you start

- Reservations needs **Tables** (the table of each reservation and its hold on the floor plan),
  **Customers** (the card of each customer) and **Schedules** (the business's opening hours). They are
  switched on with it and are not switched off while Reservations is on. Tables brings **Sales** with it.
- The times are the business's: in this phase, **Europe/Madrid**. A reservation keeps its day and its
  wall-clock time ("Thursday at 21:00"), as they are said on the phone.
- **Slots**: without a slot for that weekday nothing can be booked. It is the number one cause of "no
  availability".
- **Business hours**: a reservation has to start with the business open according to Schedules: its
  special days and temporary changes always, and its usual week as soon as the business saves or
  confirms it. The default week of Schedules (Monday to Friday from 09:00 to 18:00), unconfirmed, does not
  limit: otherwise a restaurant that never opened Schedules could not book a single dinner.
- **Factory rules**: a reservation lasts 120 minutes, is born Pending, the phone is required, the email
  is not, and a pending one is released 15 minutes after its time. For reservations made online or
  through WhatsApp, besides: parties of 1 to 20, at least 1 hour of notice and up to 30 days ahead.

Initial setup, step by step:

1. In **Schedules**, set the business's opening hours (if you do not have them already).
2. Open **Reservations → Availability**, section **Time slots**, and create the slots of each service
   day (RESERVATION-F01).
3. In **Blocked dates**, add the days or the hours in which you do not take reservations
   (RESERVATION-F02).
4. If you want other rules, change them in **Reservations → Settings** (RESERVATION-F03, F04).
5. In **Tables**, draw the room: reservations are assigned to its tables.
6. Create a test reservation and check in **Availability → Occupancy** that its slot goes down by one.

## Screens

The **Reservations** menu has three entries: **Reservations**, **Waitlist** and **Availability**. Below,
the tabs of the three plus **Settings** (this one, only for whoever can change them). The buttons the
profile cannot use do not show.

### Reservations
Menu **Reservations → Reservations**. At the top, the **day bar**: "Previous day", the date, "Next day"
and "Today" when on another day; the day in words; and three figures: **covers** (people coming, without
the cancelled ones nor the no-shows), **bookings** and **next slot** (the first one that has not ended,
with how many reservations are "left" or "Full"; or "No more service today", "No service this day",
"Closed this day"). "Today" is the one of the business's clock, not the device's.

Below, the day's table by time: Date, Time, Guest, Phone (as in Customers: the country prefix and the
digits in groups), Party, Table, Status; search box "Search guest, phone or email…" that searches the
**whole** book, also by the digits of the phone without the prefix (results by day and time); filters by
time, guests, table and status; table or cards view. Main action **"New reservation"** and, per row,
according to its status: "Confirm", "Seat", "Complete", "Cancel", "No-show", "Edit" and "Delete" (the
administrator only). Tapping a row opens it to edit it.

Empty: "No reservations this day", with an explanation and "New reservation". Searching without results:
"No reservations match your search" and "Clear filters". Loading: "Loading…" and the figures in grey.
Error: the message and "Retry"; a failure of a row action shows above the table and one of the form,
inside the form.

**Reservation form** ("New reservation" / "Edit reservation"): Customer (the Customers search box, by
name or phone, with "+ New customer"), Guest (the name), Phone, Email, Date, Time, Party, Duration (min),
Table (the free ones at that time, with their capacity and their zone; the ones that do not fit the party,
flagged), Booked through (Phone, In person), Guest notes and Internal notes.

### Waitlist
Menu **Reservations → Waitlist**. Table, in the order in which they were added (by day and preferred
time): Date, Pref. time, Guest, Phone (as in Customers), Party, Contacted, Status (Waiting, Converted);
search box and filters (date, contacted, converted). Main action **"Add guest"** (Customer, Guest, Phone,
Date, Time, Party, Notes → "Add to waitlist"); per row "Contacted", "Convert" and "Remove". Empty:
"Waitlist is empty.". Loading: "Loading…". Error: the table's message with "Retry".

### Availability
Menu **Reservations → Availability**. Three stacked sections:
- **Occupancy**: a date (today by default) and, for each slot of that day, Slot, Reserved, Max, Guests
  and Available; the slot without room is seen dimmed with the "Full" mark, and the one that falls
  outside the business's opening hours, marked "Outside opening hours". Above, the business's opening
  hours for that day and, if the day is blocked, its reason. It refreshes by itself when a reservation
  comes in, changes or is cancelled. Empty: "No service that day (no time slots).".
- **Time slots**: Day, From, To, Max (of reservations), Max guests; "Add slot" (Day, From, To, Max,
  Max guests (optional) → "Create slot") and "Remove" per row. Empty: "No time slots.".
- **Blocked dates**: Date, Reason, Hours (Whole day, or from–to); "Add blocked date" (Date, Reason,
  Whole day, From, Until → "Block date") and "Remove". Empty: "No blocked dates.".
Each section paints its own "Loading…" and its error with retry.

### Settings
Tab **Settings** (only for whoever can change them). Minimum and maximum guests, minimum notice (hours,
for online and WhatsApp), maximum days ahead, default duration, confirm new reservations automatically,
phone required, email required and the minutes after the time to release a pending one. "Save".

## States of each screen

| Screen | Loading | Empty | Error | No permission | App off |
|---|---|---|---|---|---|
| Reservations | "Loading…", figures in grey | "No reservations this day" + "New reservation" | message + "Retry" | notice instead of the table | notice instead of the table |
| Waitlist | "Loading…" | "Waitlist is empty." | message + "Retry" | notice | notice |
| Availability | "Loading…" per section | a text per section | message + "Retry" per section | notice | notice |
| Settings | "Loading…" | — | message + "Retry" | notice | notice |

While the live connection is recovered, "Reconnecting…" on top, without erasing what is painted.

## Flows

| ID | Flow | Status |
|---|---|---|
| RESERVATION-F01 | Create and remove time slots | done |
| RESERVATION-F02 | Block a day or some hours | done |
| RESERVATION-F03 | Adjust the booking rules | done |
| RESERVATION-F04 | Choose whether reservations confirm themselves | done |
| RESERVATION-F05 | Check how much is left free on a day | done |
| RESERVATION-F06 | Take a reservation by hand (phone or counter) | done |
| RESERVATION-F07 | Confirm a reservation | done |
| RESERVATION-F08 | Change a reservation (day, time, guests, table) | done |
| RESERVATION-F09 | Cancel a reservation | done |
| RESERVATION-F10 | Mark that they did not show up | done |
| RESERVATION-F11 | Seat the reservation | done |
| RESERVATION-F12 | Complete the reservation | done |
| RESERVATION-F13 | Release the pending reservations nobody confirmed | discarded |
| RESERVATION-F14 | Put someone on the waitlist | done |
| RESERVATION-F15 | Mark as contacted or remove from the waitlist | done |
| RESERVATION-F16 | Convert a waitlist entry into a reservation | done |
| RESERVATION-F17 | Reservation that comes in through WhatsApp | done |
| RESERVATION-F18 | Change or cancel the reservation through WhatsApp | done |
| RESERVATION-F19 | Tell through WhatsApp when the restaurant confirms | done |
| RESERVATION-F20 | Delete a reservation | done |
| RESERVATION-F21 | Merge the reservations of two customer cards | done |
| RESERVATION-F22 | Erase a customer's personal data (GDPR) | done |
| RESERVATION-F23 | Pick a free table for the reservation | done |

### RESERVATION-F01 Create and remove time slots
Status: done
Actor: manager
Screen: Availability → Time slots
Steps:
1. Tap "Add slot", choose the weekday, from and to, the maximum of reservations and, if you want, the
   maximum of guests. "Create slot".
2. To remove it, "Remove" on its row and confirm. The reservations it already had stay.
In: day, from, to, maximum of reservations, maximum of guests (optional).
Out: the slot (announces: `reservation.time_slot.created`, `reservation.time_slot.deleted`).
If it fails: "To" before or equal to "From": "A slot has to end after it starts."; a slot that overlaps
another one of the same day: "That slot overlaps another one of the same day (13:00–16:00).".
Involved: RESERVATION-F05, RESERVATION-F06

### RESERVATION-F02 Block a day or some hours
Status: done
Actor: manager
Screen: Availability → Blocked dates
Steps:
1. Tap "Add blocked date", type the date and the reason (holiday, closure, private event).
2. Leave "Whole day" ticked or, for some hours, untick it and set from and until.
3. That day (or those hours) no new reservations are taken; the ones already there stay.
4. To lift the block, "Remove" on its row and confirm.
In: date, reason, whole day or from–until.
Out: the block (announces: `reservation.blocked_date.created`, `reservation.blocked_date.deleted`).
If it fails: without hours when it is not the whole day, or "Until" before "From": the field says so;
that day already blocked at that time: "That date is already blocked at that time.".
Involved: RESERVATION-F05, RESERVATION-F06

### RESERVATION-F03 Adjust the booking rules
Status: done
Actor: manager
Screen: Settings
Steps:
1. Change the minimum and maximum guests, the notice, the default duration, the required phone or email
   and the minutes to release a pending one. "Save".
2. The rules apply to new reservations and to changes; the ones already made are not touched.
In: the rules.
Out: the saved rules (announces: `reservation.settings.updated`).
If it fails: minimum guests greater than the maximum: the field says so.
Involved: RESERVATION-F06, RESERVATION-F13, RESERVATION-F17

### RESERVATION-F04 Choose whether reservations confirm themselves
Status: done
Actor: manager
Screen: Settings
Steps:
1. Tick "Confirm new reservations automatically" and save.
2. From then on every new reservation (by hand, from the waitlist, online or through WhatsApp) is born
   Confirmed and holds its table.
In: the switch.
Out: the setting (announces: `reservation.settings.updated`).
If it fails: without permission to change the settings, the tab does not show; a failure on saving is
said above the button and the switch goes back to how it was.
Involved: RESERVATION-F07, TABLE-F25

### RESERVATION-F05 Check how much is left free on a day
Status: done
Actor: employee, manager
Screen: Availability → Occupancy; Reservations (day bar)
Steps:
1. Choose the date (today by default).
2. Each slot says how many reservations it has, its maximum, the guests and how many are left; the full
   one shows dimmed with "Full" and the one that falls outside the business's opening hours, with
   "Outside opening hours".
3. It updates by itself while reservations come in, change or are cancelled.
In: the date.
Out: nothing (query). It counts exactly what the door for new reservations counts.
If it fails: no slots that day: "No service that day (no time slots)."; a failure on reading is said in
the section with "Retry".
Involved: RESERVATION-F01, RESERVATION-F02, SCHEDULE-F02

### RESERVATION-F06 Take a reservation by hand (phone or counter)
Status: done
Actor: employee, manager, assistant
Screen: Reservations → "New reservation"
Steps:
1. Look up the customer by name or phone; if they are not there, type their name and their phone (their
   card is created in Customers, or the one that already has that phone is used).
2. Set the date, the time, the guests and, if you want, the table (RESERVATION-F23), the duration, where
   it was booked through and the notes. "Reserve".
3. The reservation is born Pending (or Confirmed, if they confirm themselves: then it holds its table).
4. By voice: "book for 4 tomorrow at 9 pm under the name Ana, at table 5". Before noting it down, the
   assistant's card says who it is for, by the name of their card, the day and the time ("Create in
   Reservations: Ana García · 15 Oct 2026 · 21:00"), and carries the table by its number, never by a code.
In: customer (or name and phone), date, time, guests, table, duration, booked through, notes. The phone is
saved in international format, as in Customers (`+34` and the digits together, without spaces), also the
one typed with the card already chosen; one written with another country's prefix keeps its own. It is
the number with which WhatsApp finds the customer's conversation (RESERVATION-F19).
Out: the reservation, linked to the customer's card (announces: `reservation.reservation.created`).
If it fails: nothing is saved and what was typed stays; the first reason that applies, in this order: a
phone that is not of its country (Customers' reason, "This is not a valid phone number of its country:
check the digits or write it with its international prefix (+44…).", in the Phone field, before
anything else: never after "Book it anyway?"; the card is not created either); without a phone (or
without an email) when they are required: "This business requires a phone number for every
reservation."; a time that has already passed: "That time has already passed."; only online or through
WhatsApp, guests outside the limits ("That party size is outside the limits of this business (1–20
guests)."), less notice than the minimum ("Reservations have to be made at least 1 h in advance.") or
beyond the maximum days ("Reservations are taken up to 30 days ahead."); blocked day: "That date is
blocked (holiday or closure): no reservations are taken then."; business closed at that time (Schedules):
"The business is closed at that time."; no slot covers that time: "There is no service at that time: no
time slot covers it."; full slot: "That time slot is fully booked for that date." (the staff is asked
"Book it anyway?" and, if they confirm it, the reservation goes in; online or through WhatsApp, never);
table out of service: "Table 5 cannot be booked: it is blocked or out of service."; table already
reserved at that time: "Table 5 already has a reservation from 21:00 to 23:00.". Two reservations at once
on the last place or on the same table and time: one goes in and the other gets its reason (in the full
slot, the staff can then book anyway; on the table, never).
Involved: CUSTOMER-F10, CUSTOMER-F11, SCHEDULE-F02, RESERVATION-F23, TABLE-F25

### RESERVATION-F07 Confirm a reservation
Status: done
Actor: employee, manager
Screen: Reservations (row → "Confirm")
Steps:
1. "Confirm" on a Pending reservation.
2. It becomes Confirmed and, if it has a table, Tables holds it: from one hour before, the table shows
   Reserved on the floor plan with the name and the time (TABLE-F25).
In: the reservation.
Out: the confirmed reservation (announces: `reservation.reservation.status_changed`).
If it fails: from another status: "This reservation is confirmed: it cannot be confirmed."; with its
table out of service (blocked, deactivated, deleted or in a deactivated zone), which could not be held:
"Table 5 (Terrace) cannot be booked: it is blocked or out of service.", and it stays Pending.
Involved: TABLE-F25, RESERVATION-F19

### RESERVATION-F08 Change a reservation (day, time, guests, table)
Status: done
Actor: employee, manager, assistant
Screen: Reservations (row → "Edit", or tap the row)
Steps:
1. Change the day, the time, the guests, the duration, the table (or remove it), the contact or the
   notes. "Save".
2. The change goes through the same door as a new reservation taken by the staff (without counting the
   reservation itself), even if the reservation was born online or through WhatsApp: the staff changes any
   party and fills a full slot with "Book anyway". If it was confirmed, Tables moves its hold to the new
   table and time, or releases it if it is left without a table (TABLE-F26).
3. A seated, completed, cancelled or no-show reservation only changes its notes.
In: the changed fields. The new phone is saved in international format, as on a new reservation; the
same number written another way (with spaces or without the prefix) is not a change.
Out: the changed reservation (announces: `reservation.reservation.updated`).
If it fails: the reasons of RESERVATION-F06, and the first one, a phone that is not of its country:
"This is not a valid phone number of its country: check the digits or write it with its international
prefix (+44…).", in the Phone field, and nothing changes; in another status: "This reservation can no
longer change: only its notes.".
Involved: TABLE-F26, RESERVATION-F06, RESERVATION-F18

### RESERVATION-F09 Cancel a reservation
Status: done
Actor: employee, manager, assistant
Screen: Reservations (row → "Cancel")
Steps:
1. "Cancel" on a Pending or Confirmed reservation; type the reason if you want and confirm.
2. It becomes Cancelled, frees its place and Tables releases its table (TABLE-F27).
In: the reservation and the reason.
Out: the cancelled reservation (announces: `reservation.reservation.status_changed`).
If it fails: from another status: "This reservation is seated: it cannot be cancelled.".
Involved: TABLE-F27, RESERVATION-F18

### RESERVATION-F10 Mark that they did not show up
Status: done
Actor: employee, manager, assistant
Screen: Reservations (row → "No-show")
Steps:
1. "No-show" on a Pending or Confirmed reservation and confirm.
2. It becomes No-show, frees its place and Tables releases its table.
In: the reservation.
Out: the no-show reservation (announces: `reservation.reservation.status_changed`).
If it fails: from another status: "This reservation is seated: it cannot be marked a no-show.".
Involved: TABLE-F27

### RESERVATION-F11 Seat the reservation
Status: done
Actor: employee, manager, assistant
Screen: Reservations (row → "Seat")
Steps:
1. The party arrives: "Seat" on their Pending or Confirmed reservation.
2. It becomes Seated. If it has a table, it is seated in Tables with its guests and its customer: the
   table's check opens in Sales and this reservation's hold is spent, only its own (TABLE-F28): with
   Ana at 19:00 and Bea at 21:00 at table 5, seating Ana at 20:10 leaves the table reserved for Bea,
   which shows Reserved again when Ana leaves.
3. If the party already sat at that table from the floor plan (spending this reservation's hold), only
   the reservation is marked, with the table's check.
In: the reservation.
Out: the seated reservation and, if it could be done, the table's check (announces:
`reservation.reservation.status_changed`; Tables announces `table.session.opened`).
If it fails: from another status: "This reservation is completed: its status can no longer change."; the
table out of service: "Table 5 (Terrace) cannot be booked: it is blocked or out of service."; the table
occupied by others (also by the party of another reservation seated earlier, even if seating it from the
floor plan spent this one's hold): "Table 5 (Terrace) is taken right now: free it, or move the
reservation to another table before seating it."; if Tables or Sales refuse to seat, their reason. In all
of them, the reservation does not change. Seating is done at the door, with whoever receives the party:
an automation cannot do it (it can be authorised to confirm, change, complete and the waitlist, never to
seat).
Involved: TABLE-F10, TABLE-F28, FLOW-F12

### RESERVATION-F12 Complete the reservation
Status: done
Actor: employee, manager
Screen: Reservations (row → "Complete")
Steps:
1. The party leaves: "Complete" on their Seated reservation.
2. It becomes Completed; its table check follows its course in Tables and Sales (it is charged or closed
   there).
In: the reservation.
Out: the completed reservation (announces: `reservation.reservation.status_changed`).
If it fails: without seating it first: "This reservation is confirmed: it cannot be completed before it
is seated.".
Involved: RESERVATION-F11

### RESERVATION-F13 Release the pending reservations nobody confirmed
Status: discarded — the release runs by itself every quarter of an hour and releases the pending ones of
all the businesses, but it announces it at once only in the platform's business: the Reservations screen
of the others sees it in its five-minute refresh; announcing it in each business belongs to the worker's
pass over each business (hub#551)
Actor: system
Screen: none
Steps:
1. Every quarter of an hour, the reservations still Pending once the minutes of the settings (15) have
   passed since their time are cancelled with the reason "Released: never confirmed" and free their place.
2. The confirmed ones, the seated ones and those of other days are not touched.
In: the time.
Out: the released reservations (announces: `reservation.reservation.unconfirmed_released`, only if it
released any).
If it fails: a pass that fails changes nothing and the next one tries again.
Involved: RESERVATION-F03

### RESERVATION-F14 Put someone on the waitlist
Status: done
Actor: employee, manager, assistant
Screen: Waitlist → "Add guest"
Steps:
1. Look up the customer or type their name and, if you want, their phone (with a phone it is linked to
   their card like a reservation), the date, the time they prefer, the guests and the notes.
2. "Add to waitlist": it shows in the list, in the order in which it was added, Waiting.
In: customer (or name and phone), date, preferred time, guests, notes. The phone is saved in
international format, as in a reservation (RESERVATION-F06), also with the card already chosen.
Out: the entry (announces: `reservation.waitlist.created`).
If it fails: without a name nor a customer: the form says so; a phone that is not of its country:
Customers' reason, "This is not a valid phone number of its country: check the digits or write it with
its international prefix (+44…).", in the Phone field, and nobody is added nor is the card created.
Involved: RESERVATION-F16, CUSTOMER-F10

### RESERVATION-F15 Mark as contacted or remove from the waitlist
Status: done
Actor: employee, manager
Screen: Waitlist (row → "Contacted", "Remove")
Steps:
1. "Contacted" when they are called: the row says "Yes".
2. "Remove" (and confirm) when they no longer wait: they leave the list.
In: the entry.
Out: the entry contacted or removed (announces: `reservation.waitlist.updated`,
`reservation.waitlist.deleted`).
If it fails: an entry that is no longer there: "That waitlist entry does not exist in this business.".
Involved: RESERVATION-F14

### RESERVATION-F16 Convert a waitlist entry into a reservation
Status: done
Actor: employee, manager, assistant
Screen: Waitlist (row → "Convert")
Steps:
1. There is room: "Convert". The reservation is created with the data of the entry itself (customer,
   their phone in international format, date, preferred time, guests, notes), with the default duration,
   and the entry becomes Converted.
2. The conversion checks that the time has not passed, the blocked day, the business's opening hours and
   the slot with room: it is the staff who does it, often for right now (without notice, maximum days nor
   guest limits). With the slot full, it warns "Book it anyway?" and offers "Convert anyway".
In: the entry.
Out: the reservation (booked through "Waitlist") and the converted entry (announces:
`reservation.reservation.created`, `reservation.waitlist.converted`).
If it fails: time passed, full slot or blocked day: its reason, and nothing changes; already converted:
"This entry was already converted into a reservation.".
Involved: RESERVATION-F06, RESERVATION-F14

### RESERVATION-F17 Reservation that comes in through WhatsApp
Status: done
Actor: customer, owner, assistant
Screen: Reservations; it is turned on in WhatsApp inbox → Settings and approved in Automations
Steps:
1. In **WhatsApp inbox → Settings → What do you use it for?**, the owner turns on **Book a table**
   (WHATSAPP_INBOX-F15) and chooses whether reservations confirm themselves or they review them first
   (RESERVATION-F04, WHATSAPP_INBOX-F16).
2. The customer writes to the restaurant's WhatsApp ("table for 4 on Saturday at 9 pm"). The assistant
   looks at how much is left free that day and proposes the reservation; the day, the time and the guests
   are said by the customer, never by the assistant (WHATSAPP_INBOX-F24).
3. The reservation waits in **Automations**, in "Waiting for your answer", with the phone of whoever asks
   for it. With "Approve" it goes into Reservations with the rules of the customer who books by themselves
   (guests, notice, maximum days; a full slot, never), linked to the card that already has that phone or
   to a new one with WhatsApp as its source, and with the phone they write from, never another; with the
   name they give in the message or their WhatsApp one and, if none arrives, under their phone.
4. The reservation shows in **Reservations**, on its day and at its time, with its name, its phone and
   its guests, "Pending" for the staff to confirm it (or "Confirmed", if they confirm themselves), and the
   customer receives through WhatsApp what has been booked.
In: the message, the phone and the customer's card.
Out: the reservation, booked through WhatsApp (announces: `reservation.reservation.created`).
If it fails: the reasons of RESERVATION-F06 that bind the customer: they are told them and offered other
times or the waitlist. With "No" in "Waiting for your answer", or if nobody answers in 72 hours, nothing
is booked.
Involved: CUSTOMER-F10, RESERVATION-F04, RESERVATION-F19, WHATSAPP_INBOX-F15, WHATSAPP_INBOX-F16,
WHATSAPP_INBOX-F24

### RESERVATION-F18 Change or cancel the reservation through WhatsApp
Status: done
Actor: customer, owner, assistant
Screen: Reservations; it is approved in Automations
Steps:
1. With **Book a table** on (RESERVATION-F17), the customer writes "we won't be able to make it" or "can
   we come at nine?".
2. Their latest reservation is looked up by the number they write from. The change or the cancellation of
   that same reservation waits in **Automations**, in "Waiting for your answer", named by its customer,
   its day and its time; a cancellation is only approved by whoever can cancel reservations
   (WHATSAPP_INBOX-F25).
3. With "Approve", it is checked that the reservation belongs to whoever writes (their card); if not, it
   is refused without telling anything about it, not even whether it exists. It is changed with the rules
   of the customer who books by themselves; the table, the internal notes and booking anyway are still
   the restaurant's business.
4. In **Reservations** the reservation shows at its new time, or "Cancelled"; the held table moves or is
   released, as when changing or cancelling by hand, and the customer receives through WhatsApp what has
   happened.
In: the message and the customer's card.
Out: the cancelled or changed reservation (announces: `reservation.reservation.status_changed`,
`reservation.reservation.updated`).
If it fails: "That reservation belongs to a different guest, so it cannot be managed on their behalf.";
"The table and the restaurant's internal notes are set by the restaurant: they cannot be changed from
the guest's own booking."; or the reason of the door (RESERVATION-F06): it is explained to them through
WhatsApp and the reservation stays as it was. With "No" in "Waiting for your answer", or if nobody
answers in 72 hours, nothing changes.
Involved: RESERVATION-F08, RESERVATION-F09, RESERVATION-F17, WHATSAPP_INBOX-F25

### RESERVATION-F19 Tell through WhatsApp when the restaurant confirms
Status: done
Actor: manager, customer
Screen: Reservations
Steps:
1. With the automation "Tell the customer by WhatsApp when their reservation is confirmed" turned on in
   Automations (WHATSAPP_INBOX-F26), the staff taps "Confirm" on a Pending reservation, or the reservation
   is born already confirmed because "Confirm new reservations automatically" is on.
2. The reservation gives its day and its time ready to tell the customer ("Tuesday, March 5, 2030",
   "21:30"), in their language and on the business's clock, and its guests.
3. If the reservation's phone (the one of its conversation, if it came through WhatsApp;
   RESERVATION-F17) has a WhatsApp conversation with the business, the customer receives through that
   same WhatsApp that their table is confirmed, with the day, the time and the guests.
In: the confirmation of the reservation and its phone.
Out: the notice of the confirmation (`reservation.reservation.status_changed`) and the message to the
customer, which is seen in their conversation in the WhatsApp inbox.
If it fails: without a phone or without a WhatsApp conversation with that number, nothing is sent and the
reservation stays confirmed; the reason stays in the automation's history.
Involved: RESERVATION-F07, RESERVATION-F17, WHATSAPP_INBOX-F26

### RESERVATION-F20 Delete a reservation
Status: done
Actor: administrator, owner
Screen: Reservations (row → "Delete")
Steps:
1. "Delete" and confirm. Cancelling is better: it keeps the reason.
2. The reservation disappears from the book and Tables releases its table.
In: the reservation.
Out: nothing (announces: `reservation.reservation.deleted` and `reservation.reservation.status_changed`
with the status `deleted`).
If it fails: without permission to delete, "Delete" does not show; a reservation that is no longer there:
"That reservation does not exist in this business.".
Involved: TABLE-F27

### RESERVATION-F21 Merge the reservations of two customer cards
Status: done
Actor: system
Screen: none
Steps:
1. In Customers two cards of the same person are merged.
2. Their reservations and their waitlist entries move to the card that remains; the name they booked
   with does not change.
In: the notice `customer.customer.merged` (`id` the one that remains, `absorbed_id` the absorbed one).
Out: reservations and entries pointed to the new card (announces: `reservation.customer.reassigned`, only
if it moved any). Repeating it changes nothing.
If it fails: it retries by itself; repeating it changes nothing.
Involved: CUSTOMER-F13

### RESERVATION-F22 Erase a customer's personal data (GDPR)
Status: done
Actor: system
Screen: Reservations, Waitlist
Steps:
1. In Customers the personal data of a card are erased.
2. Their reservations are left without name, phone, email, notes, internal notes or cancellation reason,
   and their waitlist entries without name, phone, email or notes (also the removed ones). The screen
   says "Deleted customer".
3. The day, the time, the guests, the table, the status and the link to the card are kept. The name is
   also erased from the notices their reservations left in the notice log (`status_changed` and
   `updated` carry it). Tables forgets the name of its holds on its own (TABLE-F31).
In: the notice `customer.customer.erased` (`id` of the card).
Out: reservations and entries without personal data (announces: `reservation.customer.erased`, only if
it changed any). Repeating it changes nothing.
If it fails: it retries by itself; repeating it changes nothing.
Involved: CUSTOMER-F16, TABLE-F31

### RESERVATION-F23 Pick a free table for the reservation
Status: done
Actor: employee, manager, assistant
Screen: reservation form → Table
Steps:
1. With the date, the time and the guests set, the Table field offers the tables in service that are
   free at that time (without another live reservation that overlaps), first the ones that fit the party,
   with their capacity and their zone; the ones that are too small show flagged, and can be chosen all
   the same.
2. By voice: "at table 5" or "at table 4 on the terrace".
In: date, time, duration, guests.
Out: nothing (query).
If it fails: without free tables at that time, the field offers none and the reservation can be taken
without a table; a table that becomes taken in the meantime is refused by the door (RESERVATION-F06).
Involved: RESERVATION-F06, TABLE-F25

## Reservations: what goes in and what comes out

Everything can be asked for through the screens, the assistant (by voice or by text, with the person's
own session) and the API, with the same rules and the same permissions. Designed for voice: a reservation
is named by its id or by the customer's name or phone with its date ("Ana's reservation tomorrow"); a
table by its id or by its number ("table 5"), with the zone if the number is repeated; a customer by their
id, their name or their phone. If a reference matches several, it is refused saying which ones (409
`*_ambiguous`). Changing and cancelling can also be asked for on behalf of the customer themselves
(`on_behalf_of`, their card; today, from WhatsApp): only their reservation, with their customer rules and
without touching the table, the internal notes nor booking anyway (F18).

Before changing anything, the assistant asks for confirmation with its card (BASE-F97), which names each
record as the Reservations screens name it, never by its code: a reservation, by its customer, its day and
its time ("Ana García · 15 Oct 2026 · 21:00"; without a name, by its phone; with the customer's data
erased, by the day and the time); a waitlist entry, the same; a slot, by its weekday and its hours
("Thursday · 20:00–23:30"); a blocked date, by its day and, if it is not the whole day, its hours; the
customer, by the name of their card, and the table, by its number. A record that whoever confirms cannot
see (for example, the card of a customer, without permission to see customers) does not show on the card.

### What it offers: queries (they read and change nothing)

| What it gives | Who can | Flows | Service |
|---|---|---|---|
| The reservations of some days (or of the whole book when searching), with filters, order and pages (up to 100) | view reservations | F05–F12 | `reservation.reservation.list` |
| A reservation, with the words it is named with | view reservations | F08, F19 | `reservation.reservation.get` |
| A day: covers, reservations, blocks, business hours and occupancy of each slot | view reservations | F05 | `reservation.availability.day` |
| The free tables for a date, time, duration and party | view reservations | F23 | `reservation.availability.tables` |
| The time slots, with filters and pages | view slots | F01 | `reservation.time_slot.list` |
| A slot, by its id or by its weekday and its start, with the words it is named with | view slots | F01 | `reservation.time_slot.get` |
| The blocked dates, with filters and pages | view blocks | F02 | `reservation.blocked_date.list` |
| A blocked date, by its id or by its date, with the words it is named with | view blocks | F02 | `reservation.blocked_date.get` |
| The waitlist, in order of arrival, with search, filters and pages | view waitlist | F14–F16 | `reservation.waitlist.list` |
| A waitlist entry, by its id or by its customer, with the words it is named with | view waitlist | F14–F16 | `reservation.waitlist.get` |
| The rules (with the business's time zone) | view settings | F03, F04 | `reservation.settings.get` |

All of them can be followed live except a single slot, a single blocked date and a single waitlist
entry, which only the assistant's card and the API read.

Each reservation they give (the list, a reservation and the one each action returns) brings, besides its
date and its time, the day and the time ready to say in the language of whoever asks for it ("martes, 5
de marzo de 2030" or "Tuesday, March 5, 2030", and "21:30"): it is what a message that cannot format a
date uses. They are those of the reservation as it was noted down, on the business's clock, without
shifting with the time zone.

### What it offers: actions (they change data)

| What it does | Who can | Flows | Service |
|---|---|---|---|
| Notes down a reservation (`overbook` knowingly fills a full slot, the staff only) | add reservations | F06 | `reservation.reservation.create` |
| Changes a reservation | change reservations | F08 | `reservation.reservation.update` |
| Confirms, seats, completes, cancels or marks a no-show | change reservations | F07, F09–F12 | `reservation.reservation.confirm`, `.seat`, `.complete`, `.cancel`, `.no_show` |
| Deletes a reservation | delete reservations | F20 | `reservation.reservation.delete` |
| Releases the overdue pending ones | change reservations | F13 | `reservation.reservation.release_unconfirmed` |
| Creates or removes a slot | change slots | F01 | `reservation.time_slot.create`, `.delete` |
| Blocks or unblocks a date | change blocks | F02 | `reservation.blocked_date.create`, `.delete` |
| Adds, marks contacted, converts (also knowingly into a full slot) or removes a waitlist entry | change waitlist | F14–F16 | `reservation.waitlist.create`, `.update`, `.convert`, `.delete` |
| Saves the rules | change settings | F03, F04 | `reservation.settings.update` |

For the platform only (without a route in the API, as the system): `reservation.customer.reassign` and
`reservation.customer.erase` (reactions to Customers).

### What it announces

| Notice | When | What it carries |
|---|---|---|
| `reservation.reservation.created` | New reservation (also from the waitlist) | `id`, `status`, `table_id`, `date`, `time`, `party_size` |
| `reservation.reservation.status_changed` | Confirm, seat, complete, cancel, no-show, delete | `id`, `status` (`deleted` on deleting), `previous_status`, `table_id`, `date`, `time`, `duration_minutes`, `party_size`, `guest_name`, `customer_id` |
| `reservation.reservation.updated` | Change | `id` and the fields that changed (`table_id`, `date`, `time`, `duration_minutes`, `party_size`, `guest_name`); `table_id` empty = without a table |
| `reservation.reservation.deleted` | Delete | `id` |
| `reservation.reservation.unconfirmed_released` | Release pending ones | `count` |
| `reservation.time_slot.created`, `.deleted` | Slots | `id` |
| `reservation.blocked_date.created`, `.deleted` | Blocks | `id`, `date` |
| `reservation.waitlist.created`, `.updated`, `.converted`, `.deleted` | Waitlist | `id` (`reservation_id` on converting) |
| `reservation.settings.updated` | Save the rules | the changed fields |
| `reservation.customer.reassigned`, `reservation.customer.erased` | Reactions to Customers | `id` (and `absorbed_id`) |

`status_changed` and `updated` also carry the customer's name and their card (it was the load with which
Tables was going to paint the hold); the others, only ids and numbers. Tables no longer listens to these
notices: it receives the hold through the call of Reservations in the same transaction (TABLE-F25–F28).

### What it reacts to

| Notice | From | What it does | Service |
|---|---|---|---|
| `customer.customer.merged` | Customers | Moves their reservations and entries to the card that remains (F21) | `reservation.customer.reassign` |
| `customer.customer.erased` | Customers | Erases their personal data from reservations and entries (F22) | `reservation.customer.erase` |

### What it needs from other apps

- **Tables** (requirement): the table of each reservation (its tables, to choose it and to check that it
  is in service) and, in the same transaction of each change, the hold of its table:
  `table.hold.sync_reservation` (confirm, cancel, no-show, delete),
  `table.hold.move_reservation` (take the table away from a confirmed one) and `table.hold.release` (seat
  early); seating calls `table.session.open` with the session of whoever seats.
- **Customers** (requirement): the customer's card (`find_customer`), looking it up by phone
  (`customer.customer.by_phone`) and creating it (`customer.customer.create`), on behalf of whoever books
  even if they have no permission in Customers (also an automation that was only authorised to book).
- **Schedules** (requirement): the business's opening hours of each day (`schedule.hours.for_range`),
  read on behalf of whoever books even if they have no permission in Schedules, and the way of saying a
  day (`day_label`), the same one Appointments uses.

### Who uses it

| App | What for | Service |
|---|---|---|
| Tables | Hold, move and release the table of each reservation | none of Reservations: it is Reservations that calls its platform actions, in the same transaction |

### Who can do what

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| View reservations | yes | yes | yes | yes | `reservation.view_reservation` |
| Add reservations | yes | yes | yes | yes | `reservation.add_reservation` |
| Change reservations (and their status) | yes | yes | yes | yes | `reservation.change_reservation` |
| Delete reservations | yes | yes | no | no | `reservation.delete_reservation` |
| View slots | yes | yes | yes | yes | `reservation.view_timeslot` |
| Create and remove slots | yes | yes | yes | no | `reservation.change_timeslot` |
| View blocks | yes | yes | yes | yes | `reservation.view_blockeddate` |
| Block and unblock dates | yes | yes | yes | no | `reservation.change_blockeddate` |
| View the waitlist | yes | yes | yes | yes | `reservation.view_waitlistentry` |
| Change the waitlist | yes | yes | yes | yes | `reservation.change_waitlistentry` |
| View settings | yes | yes | yes | yes | `reservation.view_settings` |
| Change settings | yes | yes | yes | no | `reservation.manage_settings` |

The roles arrive from the SaaS with a prefix (`hub_owner`, `hub_admin`, `hub_manager`, `hub_employee`).
Seating also asks for "Seat" of Tables (`table.add_session`) and "Build the check" of Sales
(`sale.add_sale`). Adding a reservation, or someone to the waitlist, by their phone asks for nothing from
Customers: their card is looked up or created on behalf of whoever adds it, also if it is an automation
that was only authorised to book.
