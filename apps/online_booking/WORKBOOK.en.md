<!-- generated from WORKBOOK.md sha256:556d15fc34f43b859550f5a1d367abeacb5d00ab53268bc2b898a5f506a81997 -->

## What it is for and who it is for

Online booking is **the door through which a customer asks for an appointment on her own, from outside,
without calling**: she picks the service, the professional (or "No preference"), the day and a free time,
leaves her name and her phone, and the appointment goes **into the Appointments diary**, like any other,
with the origin "Online booking". If the business confirms by hand, it is born **Pending** and waits in
the **Bookings inbox**; if it confirms by itself, it is born **Confirmed**. The customer gets an
appointment number and a personal link with which she sees her booking and cancels it within the
business's policy.

Who uses it:

- The **customer**, on the business's booking page (no account and no password).
- The **employee** sees in the inbox the online bookings of **their own diary**.
- The **manager** sees every online booking and confirms, completes, marks as no-show or cancels them.
- The **owner** and the **administrator**: besides, they delete them and set up the booking page.
- The **assistant** (by voice or by text, with the session of the person speaking) does the same: "confirm
  Ana's booking for tomorrow", "which online bookings are pending?", "cancel booking APT-20261016-0003".

## Reference adopted

**Fresha, Treatwell, Booksy, Square Appointments, Vagaro, Mindbody, Odoo Appointments and SimplyBook.me**
(table and links in "Market decisions"): the online booking **is an appointment of the diary** from the
very first moment (it takes the slot), with a setting for automatic or manual confirmation; the page asks
for name and mobile; the customer manages her booking with the link of the confirmation, and cancelling
from there respects the business's notice.

## Before you start

1. Online booking switches on with it **Appointments**, **Customers**, **Services** and **Staff** (and,
   through Appointments, **Schedules**), and they cannot be switched off while it is on.
2. In **Services**, leave **Allow online booking** ticked on the services the customer can book (also from
   this app's Settings). An archived service, or one that cannot be booked in the diary, does not show.
3. In **Staff** and **Schedules**, the same the diary asks for: bookable professionals, their hours and the
   business's. The page offers only the times the diary would give the customer.
4. Open **Online booking → Settings**, switch on **Public page on** and press **Save**. While it is off,
   the page says that the business does not take online bookings.
5. Every time is on the **business's clock** (in phase 1, Europe/Madrid).

## Screens

Online booking opens from the **Online booking** menu and has two tabs: **Bookings** and **Settings** (the
latter only for whoever can change them). What a person cannot do shows greyed out or does not appear, and
the app refuses it even if they try through the API or the assistant.

### Bookings (inbox)
A table of 50 rows per page with a search box ("Search no., customer, phone, service…") and filters by
column behind the filter button of the bar, as in the current product: No., Customer, Service,
Professional, Date (one day) and Status. Columns: **No.** (`APT-…`), **Customer** (with her
phone), **Service**, **Professional**, **Date**, **Time**, **Status** and **Booked** (when she asked for it).
Most recent first; sorted by column. List or cards.

Per row: **Confirm**, **Complete**, **No-show**, **Cancel** and **Delete** (Delete only for whoever can
delete). The one that does not apply to the status shows greyed out; it is not hidden. **Cancel** asks for
confirmation with an optional reason; **Delete** asks for confirmation. Empty: "No online bookings yet."
(with filters: "No booking matches the search."). It refreshes by itself when an online appointment changes
in the diary.

### Settings
Title "Booking page settings". Three blocks and a **Save** button:

- **Public page**: "Public page on", "Page title", "Welcome message", "Primary colour"
  (`#RRGGBB`), "Logo URL", "Email required", "Upcoming bookings per mobile" (1 to 50),
  "Let the customer choose the professional", "Allow notes", "Confirmation message" and "Cancellation policy"
  (the text the customer reads).
- **Booking rules** (they are the rules of Appointments, shared with WhatsApp): "Minimum booking notice
  (minutes)", "Book at most this far ahead (days)" (0 = no limit), "Slot interval
  (minutes)", "Confirm the customer's bookings automatically", "Let the customer cancel her booking"
  and "Minimum notice to cancel (hours)".
- **Services booked online**: the services on offer, each with a switch carrying its name (on, it is booked
  online; it is saved when touched, in Services); the one that cannot be booked in the diary says so ("Not
  bookable in the diary").

On saving: "Settings saved."; a refusal shows under its field ("Could not save").

### Booking preview (development only)
Page `/online_booking/preview`, only on the development server: it walks the public page's flow
(service → professional → day and time → details → book → see and cancel with the link) with the same
operations that the public page of `base` will call. It is not part of the production version.

## States of each screen

| State | What the person sees |
|---|---|
| Loading | "Loading…" in the table; "Loading settings…" in Settings. |
| Empty | "No online bookings yet."; with filters, "No booking matches the search."; in Settings without services, "No services yet. Add them in Services.". |
| Error | The table's notice with "Retry"; the refusal of a row action, in its confirmation or above the table; a refusal in Settings, under its field, without losing what was typed. |
| Reconnecting | What is drawn stays; a strip warns "Reconnecting…". |
| App inactive | "This app is not active in this business". |
| No permission | What they cannot do does not appear; if they get there another way, "You do not have permission". |

Dates and times show on the business's clock and in the format of the language of whoever looks.

## Flows

| ID | Flow | Status |
|---|---|---|
| ONLINE_BOOKING-F01 | The customer books from the booking page | done (operations and preview; the public page is `base`'s) |
| ONLINE_BOOKING-F02 | Confirm a booking | done |
| ONLINE_BOOKING-F03 | Complete a booking | done |
| ONLINE_BOOKING-F04 | Mark that she did not show up | done |
| ONLINE_BOOKING-F05 | Cancel a booking | done |
| ONLINE_BOOKING-F06 | Delete a booking | done |
| ONLINE_BOOKING-F07 | Set up the booking page | done |
| ONLINE_BOOKING-F08 | See and search the bookings | done |
| ONLINE_BOOKING-F09 | Follow the customer when two cards are merged | done (Appointments does it; the inbox reflects it) |
| ONLINE_BOOKING-F10 | The customer sees her booking with her link | done (operation; the page is `base`'s) |
| ONLINE_BOOKING-F11 | The customer cancels her booking with her link | done (operation; the page is `base`'s) |
| ONLINE_BOOKING-F12 | Erase a customer's data (GDPR) | done |

### ONLINE_BOOKING-F01 The customer books from the booking page
Status: done (operations and preview; the public page is `base`'s)
Actor: customer (no session)
Screen: public booking page (`base`); in development, the preview
Steps:
1. She opens the business's page: title, welcome message, logo and colour from the Settings.
2. She picks one or several services (up to 5) among those **booked online**, with their price and their
   duration if Services shows them ("Show prices", "Show duration").
3. If the business allows it, she picks a professional among those who do all those services, or "No
   preference".
4. She picks the day: the **free times** the diary would give the customer show (business hours, the
   professional's shift and absences, blocks and other appointments; never inside the minimum notice,
   beyond the maximum, in the past or on top of another appointment).
5. She writes her name, her **mobile** (required), her email (if the business asks for it) and, if allowed,
   a note.
6. She presses **Book**: the appointment goes into the diary with the origin "Online booking", **Confirmed**
   or **Pending** depending on "Confirm the customer's bookings automatically" (and always Pending if a
   service has "Requires confirmation" in Services), and the customer sees her appointment number (`APT-…`),
   the confirmation message and her **personal link**.
In: the services booked online (Services), the professionals who do them (Services and Staff),
the free times and the booking rules (Appointments), the cards of Customers.
Out: the appointment (`appointment.appointment.created` and, if it is born confirmed, `appointment.appointment.confirmed`),
the customer's card **linked by her phone** or created if it does not exist (`customer.customer.created`, with
origin "web"), and the notice `online_booking.booking.created`. If the card has no email, the one she wrote
stays as the appointment's contact (the card is not touched). With "No preference", the appointment goes to
the first professional (by name order) who has that time free. Nothing the page answers tells the name
of the card of that mobile. Whoever opens the preview from inside (owner or administrator) books with
the same rules as the customer: never with the front desk's exceptions.
If it fails: nothing is written. The page switched off ("This business does not take online bookings right now."); a
service that is not booked online; picking a professional when the business does not allow it; the time is no longer
free or does not meet the rules (the reason from Appointments); the mobile that is not a valid number; the required
email missing; a note when the business does not take them; **anti-abuse limits**: more than 5 bookings in an hour
from the same device ("…Try again later, or call the business.") or more than 100 in an hour in the
business ("…Try again in a few minutes."), or more
upcoming online bookings with the same mobile than the Settings allow (3 out of the box: "This mobile already
has upcoming bookings…", without saying how many). Two customers who book the same time of the same
professional at once: one gets in and the other gets "That time is no longer free".
Involved: APPOINTMENT-F02, APPOINTMENT-F18, APPOINTMENT-F19, CUSTOMER-F10, CUSTOMER-F11, SERVICE-F10

### ONLINE_BOOKING-F02 Confirm a booking
Status: done
Actor: manager, owner, administrator, assistant
Screen: Bookings
Steps:
1. On a **Pending** booking, press **Confirm** (or say "confirm Ana's booking for tomorrow").
2. The appointment becomes **Confirmed** in the diary and its history says "Confirmed".
In: a pending online booking (the page with automatic confirmation off, or a service that
requires confirmation).
Out: `appointment.appointment.confirmed`.
If it fails: "This appointment can no longer be confirmed: it is not pending any more."; if the name fits several
bookings, they are listed and the number is asked for.
Involved: APPOINTMENT-F03

### ONLINE_BOOKING-F03 Complete a booking
Status: done
Actor: manager, owner, administrator, assistant
Screen: Bookings
Steps:
1. On a **Confirmed** or **In progress** booking, press **Complete**.
2. The appointment becomes **Completed**. It does not charge: charging is the diary's, in the POS.
In: a confirmed or in-progress online booking.
Out: `appointment.appointment.completed`.
If it fails: "This appointment cannot be completed in its current state."
Involved: APPOINTMENT-F08, APPOINTMENT-F17

### ONLINE_BOOKING-F04 Mark that she did not show up
Status: done
Actor: manager, owner, administrator, assistant
Screen: Bookings
Steps:
1. Once the booking's time has passed, on a **Pending** or **Confirmed** one, press **No-show**.
2. The appointment becomes **No-show** and the slot is free again.
In: a pending or confirmed online booking whose time has already passed.
Out: `appointment.appointment.marked_no_show`.
If it fails: before its time, "It is not the appointment's time yet…"; in another status, "This appointment cannot be
marked as a no-show in its current state."
Involved: APPOINTMENT-F09

### ONLINE_BOOKING-F05 Cancel a booking
Status: done
Actor: manager, owner, administrator, assistant
Screen: Bookings
Steps:
1. Press **Cancel** on a pending, confirmed or no-show booking.
2. "Cancel Lucía's booking (Tuesday 14, 10:00)?" with the optional reason; press **Cancel the booking**.
3. The appointment becomes **Cancelled**, the slot is free again and the history keeps who and the reason.
In: a pending, confirmed or no-show online booking, not charged.
Out: `appointment.appointment.cancelled`. Declining a pending booking is cancelling it (the market: the
"decline" of a request frees the slot all the same).
If it fails: "This appointment can no longer be cancelled in its current state."; inside the dialog.
Involved: APPOINTMENT-F05

### ONLINE_BOOKING-F06 Delete a booking
Status: done
Actor: owner, administrator
Screen: Bookings
Steps:
1. Press **Delete** and confirm "Delete booking APT-…? It is better to cancel it, which keeps its history.".
2. The booking disappears from the inbox and from the diary (soft delete: the data is not lost).
In: an online booking that is not in progress, completed or charged.
Out: `appointment.appointment.deleted`.
If it fails: an appointment in progress, completed or charged is not deleted ("This appointment cannot be deleted…").
Involved: APPOINTMENT-F11

### ONLINE_BOOKING-F07 Set up the booking page
Status: done
Actor: owner, administrator
Screen: Settings
Steps:
1. Change the fields of **Public page** and of **Booking rules** and press **Save**: "Settings
   saved.". Only what changes is saved, all together or nothing.
2. In **Services booked online**, touch a service's switch: it is saved at once in
   Services.
In: the saved settings (or the out-of-the-box ones: page off, email not required, 3 upcoming bookings per
mobile, choosing a professional and notes allowed) and the rules of Appointments.
Out: `online_booking.settings.updated` (if something of the page changes) and `appointment.settings.updated` (if
a rule changes); a service's switch, `service.service.updated`.
If it fails: a colour that is not `#RRGGBB`, a URL that is not `http(s)://…`, a number out of range or a text
too long, under its field; nothing is saved.
Involved: APPOINTMENT-F19, SERVICE-F02

### ONLINE_BOOKING-F08 See and search the bookings
Status: done
Actor: employee (those of their diary), manager, owner, administrator, assistant
Screen: Bookings
Steps:
1. Open **Bookings**: the appointments with origin "Online booking", most recent first.
2. Search by number, name, phone, email, service or professional; filter by column from the filter button
   of the bar; sort. A long name ends in "…" inside its column.
3. A specific booking is given by the assistant or the API by its number, or by the customer and the day.
In: the appointments of Appointments with origin "Online booking" that the person can see.
Out: nothing is written. The row opens nothing by itself: what is done with a booking are its actions.
If it fails: "The bookings could not be loaded" with **Retry**.
Involved: APPOINTMENT-F27

### ONLINE_BOOKING-F09 Follow the customer when two cards are merged
Status: done (Appointments does it; the inbox reflects it)
Actor: system
Screen: none (it shows in Bookings)
Steps:
1. In **Customers**, two cards are merged.
2. Appointments moves the appointments of the absorbed card to the one kept (APPOINTMENT-F23); the inbox shows the booking with
   the card kept and the name the customer wrote when booking. This app does not keep the customer's
   card: nothing more to do, and her link keeps working.
In: the Customers notice with the card kept and the absorbed one, delivered by the worker's relay.
Out: nothing of its own (the Appointments notice, `appointment.appointment.reassigned`).
If it fails: Appointments is never left halfway and the relay retries on its own.
Involved: APPOINTMENT-F23, CUSTOMER-F13

### ONLINE_BOOKING-F10 The customer sees her booking with her link
Status: done (operation; the page is `base`'s)
Actor: customer (no session)
Screen: her booking's page (`base`); in development, the preview
Steps:
1. She opens the link of her confirmation.
2. She sees the number, the status, the day and the time, the services, the professional, the cancellation policy and whether
   she can still cancel and until when. Never the card's name: whoever has the link does not find out
   whom a mobile belongs to.
In: the link she got when booking; the cancellation rules of Appointments.
Out: nothing is written. The link stays valid even if the business switches the page off.
If it fails: a link that does not exist, revoked or of a deleted booking: "That booking does not exist or its link is no
longer valid.".
Involved: APPOINTMENT-F06

### ONLINE_BOOKING-F11 The customer cancels her booking with her link
Status: done (operation; the page is `base`'s)
Actor: customer (no session)
Screen: her booking's page (`base`); in development, the preview
Steps:
1. From her link she presses **Cancel the booking** (optional reason).
2. The policy of Appointments applies: "Let the customer cancel her booking" and "Minimum notice to
   cancel". The appointment becomes **Cancelled**, with "requested by the customer" in its history. The policy applies
   the same when the team tries the link from the preview.
In: the link of a pending or confirmed booking, not charged.
Out: `appointment.appointment.cancelled`.
If it fails: "Online cancellation is not available. Please contact the business."; "This appointment can only
be cancelled online N hours ahead…"; one already cancelled or completed, the reason from Appointments.
Involved: APPOINTMENT-F06, APPOINTMENT-F19

### ONLINE_BOOKING-F12 Erase a customer's data (GDPR)
Status: done
Actor: system
Screen: none (it shows in Bookings)
Steps:
1. In **Customers**, the personal data of a card is erased.
2. Appointments empties her appointments (APPOINTMENT-F24); this app **revokes her links** (they stop working) and forgets the
   trace of the device she booked with. Doing it again changes nothing more.
In: the Customers notice with the erased card, delivered by the worker's relay.
Out: nothing of its own: the booking stays nameless in the inbox and its link no longer opens anything.
If it fails: the relay retries the reaction on its own; it is never left halfway.
Involved: APPOINTMENT-F24, CUSTOMER-F16

## Services: what goes in and what comes out

Everything can be asked for through the screens, the assistant (by voice or by text, with the session of the person speaking) and the
API, with the same rules and permissions. A booking is named by its id, its number (`APT-…`) or **the way a
person says it**: the customer (name, phone or email) and the day ("Ana's for tomorrow"); with no day, her next
online booking. If it fits several, they are listed and the number is asked for.

### What it offers: queries

| What it gives | Who can | Flows | Service |
|---|---|---|---|
| The online bookings, with search, filters and sorting, in pages (up to 100) | view bookings | F08 | `online_booking.booking.list` |
| One booking | view bookings | F08 | `online_booking.booking.get` |
| The page's settings and the booking rules | view bookings | F07 | `online_booking.settings.get` |
| Page, services, free times and booking by link (public) | `online_booking.public` | F01, F10 | `online_booking.public.page`, `.services`, `.slots`, `.booking` |

### What it offers: actions

| What it does | Who can | Flows | Service |
|---|---|---|---|
| Confirms | confirm bookings (+ change appointments) | F02 | `online_booking.booking.confirm` |
| Completes | change bookings (+ change appointments) | F03 | `online_booking.booking.complete` |
| Marks as no-show | change bookings (+ change appointments) | F04 | `online_booking.booking.no_show` |
| Cancels, with a reason | change bookings (+ change appointments) | F05 | `online_booking.booking.cancel` |
| Deletes | delete bookings (+ delete appointments) | F06 | `online_booking.booking.delete` |
| Saves the settings (and the rules of Appointments) | settings (+ Appointments settings for the rules) | F07 | `online_booking.settings.update` |
| Books and cancels from the page (public) | `online_booking.public` | F01, F11 | `online_booking.public.book`, `.cancel` |

No-show, cancel and delete are **high risk** for the assistant: it asks for confirmation first. The actions of
the inbox are done by Appointments with the permission of whoever acts: it takes this app's **and** Appointments'.

### What it announces

| Notice | When | What it carries |
|---|---|---|
| `online_booking.booking.created` | A customer books from the page | The appointment (`appointment_id`), its number, the customer and the time; never notes |
| `online_booking.settings.updated` | Saving the settings with some change of the page | Nothing |

The rest of the facts (confirmed, cancelled, completed, no-show, deleted) are the notices of Appointments.

### What it reacts to

| Notice of another app | What it does | Flows |
|---|---|---|
| `customer.customer.erased` (Customers) | Revokes the links of that card's bookings and forgets the device's fingerprint | F12 |

### Who can do what

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| View bookings (those of their diary, if they only see their own in Appointments) | yes | yes | yes | yes | `online_booking.view_booking` |
| Change bookings (complete, no-show, cancel) | yes | yes | yes | no | `online_booking.change_booking` |
| Confirm bookings | yes | yes | yes | no | `online_booking.confirm_booking` |
| Delete bookings | yes | yes | no | no | `online_booking.delete_booking` |
| Set up the page | yes | yes | no | no | `online_booking.manage_settings` |
| Try the public page (preview) | yes | yes | no | no | `online_booking.public` |
