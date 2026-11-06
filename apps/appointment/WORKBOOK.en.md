<!-- generated from WORKBOOK.md sha256:53ed27be3d0ef60d7f063a8d24a719bd5cd6c8e6410a308236389778f442328e -->

## What it is for and who it is for

Appointments is **the agenda of a business that works by appointment** (hair salon, beauty salon, barber
shop). Each appointment joins a customer from **Customers**, one or more services from **Services** (cut +
colour) and a professional from **Staff** at a time, without stepping over the business's opening hours
(**Schedules**), the professional's shift or time off, or another appointment of theirs, and it keeps
everything that happens to it from the moment it is booked until it is attended, charged or called off.

Who uses it:

- The **employee** sees **their own agenda**: books appointments for themselves, confirms them, starts
  them, finishes them, moves them, cancels them and charges them. They do not see their colleagues'
  appointments.
- The **manager** sees and manages the whole team's agenda, and blocks time.
- The **owner** and the **administrator**: they also delete appointments and change the booking settings.
- The **customer** books, moves and cancels on their own when the business allows it (through WhatsApp or
  through online booking, via the API), always with the business's notice rules.
- The **assistant** (by voice or by text, with the session of whoever is speaking) does all of the above:
  "tomorrow at 10 with Ana, a haircut for Lucía", "move Lucía's appointment to Thursday", "cancel the one
  at 12".

## Reference adopted

- **Fresha, Vagaro, Mangomint, Square Appointments, Booksy and Phorest**: the day's agenda by
  professional, dragging the appointment to another time or another professional, week view, several
  services in one appointment, the states booked → confirmed → in progress → completed / cancelled / no
  show, charging the appointment at the till without typing it again, and a cancellation policy that binds
  the customer, not the business.
- **Google Calendar / RFC 5545**: editing a series "only this appointment" or "this one and the following
  ones", never all of them, and the series keeps its wall-clock time when the official time changes.
- **Mindbody/Booker**: the front desk can note down an appointment that has already started.
- Decisions of the current product that rule here: the business's opening hours live only in Schedules,
  charging is done by the till (Appointments only notes which sale it was charged with), the clock is
  always the business's and series are edited with a cut.

## Before you start

1. Appointments turns on with it **Customers**, **Services**, **Staff** and **Schedules**, and they cannot
   be turned off while Appointments is on.
2. In **Services**, add the bookable services with their price and their duration, and assign to each one
   the professionals who perform it. A service with nobody assigned can be performed by the whole bookable
   team (the rule belongs to Appointments).
3. In **Staff**, add the professionals and mark them **Bookable**. If you want the agenda to respect their
   shift, create their weekly schedule; without a schedule, only their approved time off stops them from
   being booked.
4. In **Schedules**, confirm the business's week and set the public holidays. A day without any opening
   hours rule (neither the week nor an exception) lets anyone book at any time.
5. The agenda always paints the **business clock**, in its time zone, never the device's: if the
   device is in another time zone, a notice says so.
6. Check the Appointments **Settings** (notice periods, overlaps, cancellation by the customer, calendar
   window).
7. To charge from the agenda, **Sales** has to be on and you have to be able to sell in it.

## Screens

Appointments opens from the **Appointments** menu and has two tabs: **Agenda** and **Settings** (the latter
only for whoever can change them). What a person cannot do is greyed out or does not appear, and the app
refuses it even if they try through the API or through the assistant.

### Agenda
A bar with the day (‹ date › and **Today**, and the calendar button to jump to a date), **Filter by
status**, the **N to confirm** notice when there are pending bookings made by customers, and the
**List · By professional · Repeating** switch (on a phone, icons only). In **List** and in **By
professional**, also **Day · Week**.

- **List**: columns Time, No., Customer, Service, Professional and Status, the search "Search no., customer
  or service…" and, on each row, **Charge, Edit, Confirm, Start, Complete, No-show, Cancel, History and
  Delete**. The one that does not apply to the appointment's state is greyed out, not hidden; **Charge** is
  greyed out if the appointment is already charged and is called **Go to the check** while its check is
  still open at the till (then No-show, Cancel and Delete are greyed out).
- **By professional · Day**: one row per bookable professional and an "Unassigned" row if there are
  appointments without a professional (two appointments that overlap share the row, each in its own lane);
  the calendar hours run horizontally and what the business has closed
  or blocked is shaded (what is closed, according to Schedules; there you cannot tap to book). A professional who no longer takes appointments (not bookable, inactive, left)
  keeps their row, behind the bookable ones, on the days they still have appointments, and above the grid
  a notice "Ana no longer takes new appointments: their appointments for the day stay on their row so you
  can move them to someone else.". Tapping a free slot opens the new appointment with that professional and
  that time; tapping an appointment opens its card; dragging an appointment moves it to another time or to
  another row (with the mouse, on release; on a touch screen, holding it down before dragging).
- **By professional · Week**: one row per professional and one column per day of the week, with each day's
  appointments in order. Tapping an appointment opens its card; dragging it to another day or another row
  moves it keeping the time.
- **Repeating**: see the [Repeating](#repeating) screen.
- **Add appointment** button → **New appointment**: Customer (search "Search by name, phone, email…"; if they
  are not there, **+ New customer** creates them with name and phone without leaving), Services (one or
  more, in order), Professional (only those who perform all those services), Day, Time (with the **Free
  times** as buttons), Min. (the sum of the durations, changeable), Notes for the customer and Internal
  notes. Min. and the **Total** come with the professional's own duration and price for each service
  (Services, "Professionals who perform it"), or the catalogue's if they have none; it is what the
  appointment books. Amounts are in the business's currency, its country's, with its decimals (BASE-F50:
  "65,00 zł" in a business in Poland; without a symbol while the business has not answered, never in euros by
  default) and are grouped from four digits ("1.234,56 €"; in English, "€1,234.56").
  Notices: "This appointment starts in the past. It will be saved at that time." and the professional who
  does not perform a service.
- **Edit** → **Edit appointment**: Day, Time, Min., Services, Professional, the notes and **Save
  changes**; below, the history. The customer is not changed.
- Dialogs: **Overlapping appointment** (**Book anyway** / **Pick another time**), **Edit repeating
  appointment** (**This appointment only** / **This and all following appointments**), **Cancel the
  appointment** (optional reason) and **Delete the appointment** (confirmation).

### Repeating
Third segment of the Agenda. Table: Customer, Service, Professional, Repeats (for example "Every
week · Monday · 11:00"), Starts, Ends ("No end", "After {n} appointments" or the date) and **Active**
(switch). On each row: **Edit series**, **Book appointments** and **Delete** (asks for confirmation). The
add button opens **New repeating appointment** (Customer, Services, Professional, Repeats, Day of the
week, Starts on, Time, Min., "Ends on (optional)", "Number of appointments (optional)") with **Create
repeating appointment**; editing opens **Edit repeating appointment** with "From" and **Save from this
occurrence on**; the search is "Search customer or service…". After booking, only what happened shows: "{n}
appointments booked" and, if any did not fit, "{n} could not be booked" with each date and its reason (if
they were all there already, "Nothing new to book: its {n} appointments were already booked"), and if dates
are left, "The dates from {date} on are not booked yet: tap «Book appointments» on the series to book
them.".

### Appointment card
When you tap an appointment: number, state, customer, services with their price, professional, time,
notes, whether it is charged and its **History**: each change with its time on the business clock, who
made it ("Requested by the customer" when it was them) and what changed.

### Appointment settings
**Settings** tab (only for whoever can change them): "Default duration (minutes)", "Minimum booking notice
(minutes)" (only for the bookings made by the customer), "Book at most this far ahead (days; 0 = no
limit)", "Allow overlapping appointments (the front desk is warned first)",
"Let customers cancel their appointment", "Minimum cancellation notice (hours)", "Calendar starts at
(hour)", "Calendar ends at (hour)", "Slot interval (minutes)" and "Confirm bookings made by the customer
automatically"; **Save** button.

### Visit history (on the Customers card)
Block at the end of a customer's card in **Customers**, contributed by Appointments: their last 10
appointments, the most recent first, with services, professional, state and notes (the internal one
first).

## States of each screen

| State | What the person sees |
|---|---|
| Loading | "Loading…" while the first result arrives; under Services and Professional, "Loading services…" / "Loading professionals…". |
| Empty | "No appointments for this day.", "No repeating appointments yet."; with no bookable professionals, "No bookable professionals yet."; in the new appointment, "There are no bookable services yet. Add them in Services.". |
| Error | The notice of the table or the grid with "Retry". A refusal of a form shows inside the form, each reason under its field, without losing what was typed; a conflict (409) shows above the button and in a notice. |
| Reconnecting | What is painted stays; a strip warns "Reconnecting…". |
| App inactive | "This app is not active in this business". |
| No permission | What they cannot do does not appear; if it arrives through another door, "You do not have permission". |
| Another time zone | "This device is on a different time zone. The agenda always shows the business clock: {zone}." |

Dates, times and amounts show in the format of the language of whoever is looking and on the business
clock.

## Flows

| ID | Flow | Status |
|---|---|---|
| APPOINTMENT-F01 | Book an appointment from the agenda | done |
| APPOINTMENT-F02 | See which times are still free | done |
| APPOINTMENT-F03 | Confirm a pending appointment | done |
| APPOINTMENT-F04 | Move an appointment or change its professional or services | done |
| APPOINTMENT-F05 | Cancel an appointment from the agenda | done |
| APPOINTMENT-F06 | The customer cancels or moves their own appointment | done |
| APPOINTMENT-F07 | Start the service | done |
| APPOINTMENT-F08 | Complete the appointment | done |
| APPOINTMENT-F09 | Mark that the customer did not show up | done |
| APPOINTMENT-F10 | See an appointment's history | done |
| APPOINTMENT-F11 | Delete an appointment | done |
| APPOINTMENT-F12 | Create a repeating appointment | done |
| APPOINTMENT-F13 | Book the appointments of a series | done |
| APPOINTMENT-F14 | Edit a series from this appointment on | done |
| APPOINTMENT-F15 | Pause, reactivate or delete a series | done |
| APPOINTMENT-F16 | Block time in the agenda | done |
| APPOINTMENT-F17 | Charge the appointment at the till | done |
| APPOINTMENT-F18 | Appointment booked by the customer | done |
| APPOINTMENT-F19 | Adjust the booking rules | done |
| APPOINTMENT-F20 | See a customer's appointments on their card | done |
| APPOINTMENT-F21 | Book several appointments at once (voucher or course) | done |
| APPOINTMENT-F22 | Change the notes or the contact details of an appointment | done |
| APPOINTMENT-F23 | Merge the appointments when two customer cards are merged | done |
| APPOINTMENT-F24 | Empty a customer's data when the card is erased | done |
| APPOINTMENT-F25 | A professional leaves with upcoming appointments | done |
| APPOINTMENT-F26 | A service is archived with appointments or series that use it | done |
| APPOINTMENT-F27 | See the week's agenda | done |
| APPOINTMENT-F28 | Get the system notice of a new or cancelled appointment | done |

Whoever asks for something on behalf of the customer without being a person of the team (a step of an
automation, the WhatsApp conversation, online booking) is judged and answered **as the customer**: they do
not have the front desk's exceptions (a time already past, inside the minimum notice, **Book anyway** over
an overlap, cancelling outside the policy) and they do not read the customer's contact details, the notes
or the reason for a cancellation (APPOINTMENT-F01, F06, F18 and F20). As they are nobody of the team, they have
no appointments of "their own": what they are allowed on them (booking, moving, confirming or editing) counts
for those of any professional, just as the customer books with whoever she likes; what they are not allowed,
they do not do (APPOINTMENT-F01 and F04).

### APPOINTMENT-F01 Book an appointment from the agenda
Status: done
Actor: employee (for themselves), manager, assistant
Screen: Agenda
Steps:
1. Tap **Add appointment**, or in "By professional" tap a free slot (it fills in professional and time).
2. Pick the customer (searched by name, phone or email; if they are not there, **+ New customer** creates
   them with name and phone), one or more services and the professional. With services picked, only the
   professionals who are **Active and Bookable and perform all of them** show; if a service has nobody
   assigned, for that service the whole bookable team counts. "Min." is filled in with the sum of the
   durations (the professional's own if they have one, otherwise the catalogue's).
3. Type the day and tap one of the **Free times** (or type another time).
4. Tap **Add appointment**. If the business allows overlaps and that time clashes with another appointment
   of the professional, answer "Overlapping appointment".
5. The appointment shows as **Confirmed** with its number `APT-YYYYMMDD-NNNN`.
In: the customer's card (Customers), the services with their price and duration (Services), the
professional and who does what (Staff and Services), the business's opening hours (Schedules) and the
professional's shift and time off (Staff).
Out: the appointment with the customer's name, phone and email and each service's name, price and
duration **frozen** (changing the catalogue later does not change the appointment), its "Booked" line in
the history and the appointment-created event (`appointment.appointment.created`), the same for a single
appointment, one of a batch and one of a series.
If it fails: the reason shows inside the panel, without losing what was typed: outside the business's
opening hours, the professional does not work at that time, blocked slot, the professional already has an
appointment (`appointment.slot_taken`), too far ahead, the customer, the service or the professional do
not exist or cannot be booked. From the front desk neither the minimum notice nor a time already past
refuses (the past time only warns before saving); an automation does not have those exceptions. An employee
only books for themselves; an automation allowed to book, with any professional. Two people
who book the same slot of the same professional at once: one gets in and the other gets the refusal.
Involved: CUSTOMER-F11, CUSTOMER-F25, CUSTOMER-F30, SERVICE-F10, SERVICE-F33, STAFF-F16, SCHEDULE-F11

### APPOINTMENT-F02 See which times are still free
Status: done
Actor: employee, assistant, customer
Screen: Agenda (new appointment and editing)
Steps:
1. With services, professional and day picked, the **Free times** appear as buttons.
2. The candidate times come every "Slot interval (minutes)" inside the calendar window ("Calendar starts
   at (hour)", "Calendar ends at (hour)"). Only the one that fits whole shows: inside the business's
   opening hours (Schedules: that day's stretch or the small hours of the day before), inside the
   professional's shift and outside their time off (Staff), with no block and no other appointment of
   theirs; with overlaps allowed, a taken time also shows. The appointment can end exactly at closing time.
3. From the front desk the times inside the minimum notice show too (marked), never those already past; to
   the customer, only those that respect the minimum notice.
4. Without a professional (the assistant: "what times are free tomorrow for a haircut?"), each time says
   which professionals have it free.
5. When asking whether a specific time can be booked, the answer says why not; which appointments it
   clashes with is told only to whoever can see that agenda (to an employee, about a colleague, only
   "already has an appointment").
In: the business's opening hours, the shift and the time off, the blocks, the appointments and the
settings.
Out: the list of times; it saves nothing.
If it fails: "The free times could not be loaded. You can still type a time." with
**Retry**; the typed time is judged when saving. With no times: "No free times that day for this
professional. You can still type a time.".
Involved: SCHEDULE-F11, STAFF-F16, SERVICE-F33

### APPOINTMENT-F03 Confirm a pending appointment
Status: done
Actor: employee (their own), manager, assistant
Screen: Agenda
Steps:
1. Come in from the **N to confirm** notice (you tap it and the list filters the pending ones), from the
   bell in the top bar (its "Appointments to confirm" row opens the Agenda) or search for the **Pending**
   appointment.
2. Tap **Confirm** on its row.
3. The appointment becomes **Confirmed**, the history says "Confirmed" and the **N to confirm** notice
   goes down; the bell too, at once, and it stops counting it.
In: a pending appointment (the one the customer booked with automatic confirmation turned off).
Out: the confirmed appointment, its history line and the `appointment.appointment.confirmed` event.
If it fails: "This appointment can no longer be confirmed: it is not pending any more."; nothing is
written.
Involved: none

### APPOINTMENT-F04 Move an appointment or change its professional or services
Status: done
Actor: employee (their own), manager, assistant
Screen: Agenda
Steps:
1. Tap **Edit** (or tap the appointment in "By professional"): "Edit appointment" opens.
2. Change Day, Time, Min., Services or Professional and tap **Save changes**. If the appointment belongs
   to a series, choose **This appointment only** or **This and all following appointments**
   (APPOINTMENT-F14). From the front desk it can be taken to a time already past (to note down what
   already happened).
3. Shortcut: in "By professional" drag it to another time, another day or another row. Dragging does not
   take it to a time already past (that, from the panel).
4. The appointment keeps its number and the history says "Time changed", "Professional changed" or
   "Service changed".
In: a **Pending** or **Confirmed** appointment.
Out: the moved appointment (new services bring their name and price from the catalogue and their
duration, the professional's own if they have one; a new professional keeps the price and the duration),
its history and the `appointment.appointment.rescheduled` event.
If it fails: the reason in the panel and in a notice; a dragged block goes back to its place. An
appointment in progress, completed, cancelled or no-show does not move (**Edit** is greyed out). An employee
only moves their own; an automation allowed to move them, those of any professional, by the customer's
rules.
Involved: SERVICE-F33, STAFF-F16, SCHEDULE-F11

### APPOINTMENT-F05 Cancel an appointment from the agenda
Status: done
Actor: employee (their own), manager, assistant
Screen: Agenda
Steps:
1. Tap **Cancel** on a pending, confirmed or no-show appointment.
2. "Cancel Lucía's appointment (Tuesday 14, 10:00)? Its time becomes free." with the optional reason; tap
   **Cancel the appointment**.
3. The appointment becomes **Cancelled** (the slot becomes free) and the history says "Cancelled", who
   and the reason.
In: a pending, confirmed or no-show appointment, without its check open at the till.
Out: the `appointment.appointment.cancelled` event.
If it fails: "This appointment can no longer be cancelled in its current state." (in progress, completed
or already cancelled); with its check open at the till, "This appointment has a check open in the till:
charge it or void it there first." (`appointment.check_open`).
Involved: none

### APPOINTMENT-F06 The customer cancels or moves their own appointment
Status: done
Actor: customer (through WhatsApp or online booking)
Screen: none
Steps:
1. The automation asks to cancel or move **on behalf of the customer**, saying who they are.
2. The appointment has to be theirs; if it is not, the answer is the same as if it did not exist (it does
   not let anyone find out which appointments there are).
3. To cancel, the policy applies: "Let customers cancel their appointment" and "Minimum cancellation
   notice (hours)".
4. To move, the minimum notice and the same rules as a booking made by the customer apply.
5. The history keeps "Requested by the customer" with the reason, and also who on the team noted it down.
6. Doing it on behalf of the customer does not give more permissions: whoever notes it down only changes
   the appointments they could already change (an employee, their own, and they do not hand them over to
   a colleague). A person of the team can cancel outside the policy; an automation, never.
7. An automation only cancels if it asks first: an **Ask the assistant** step with "Ask me first" that is allowed to,
   after a yes from someone who can change any professional's appointments; then it works on anyone's appointment,
   under the same policy (FLOW-F28, FLOW-F38). Without that question, it cannot.
In: the customer's appointment and the cancellation and notice settings.
Out: the cancelled or moved appointment, its "Requested by the customer" line and the
`appointment.appointment.cancelled` or `appointment.appointment.rescheduled` event.
If it fails: `appointment.customer_cancellation_disabled`, `appointment.cancellation_notice_required`,
`appointment.too_soon`, `appointment.appointment_not_found` or `permission_denied`.
Involved: FLOW-F28, FLOW-F38

### APPOINTMENT-F07 Start the service
Status: done
Actor: employee (their own), manager
Screen: Agenda
Steps:
1. When the customer arrives, tap **Start** on their pending or confirmed appointment.
2. The appointment becomes **In progress** and the history says "Service started".
In: a pending or confirmed appointment.
Out: the `appointment.appointment.started` event.
If it fails: "This appointment cannot be started in its current state."
Involved: none

### APPOINTMENT-F08 Complete the appointment
Status: done
Actor: employee (their own), manager
Screen: Agenda
Steps:
1. When finished, tap **Complete** on the appointment in progress (or confirmed).
2. The appointment becomes **Completed**. Charging it also completes it (APPOINTMENT-F17).
In: an appointment in progress or confirmed.
Out: the `appointment.appointment.completed` event.
If it fails: "This appointment cannot be completed in its current state."
Involved: none

### APPOINTMENT-F09 Mark that the customer did not show up
Status: done
Actor: employee (their own), manager
Screen: Agenda
Steps:
1. Once the appointment's time has passed, tap **No-show** on a pending or confirmed appointment.
2. The appointment becomes **No-show**, the slot is freed and the history says "Did not show up".
In: a pending or confirmed appointment whose time has already passed.
Out: the `appointment.appointment.marked_no_show` event.
If it fails: before its time, "It is not the appointment's time yet: it cannot be marked as a no-show.";
in another state, "This appointment cannot be marked as a no-show in its current state.";
with its check open at the till, `appointment.check_open`.
Involved: none

### APPOINTMENT-F10 See an appointment's history
Status: done
Actor: employee (their own), manager
Screen: Agenda
Steps:
1. Tap **History** on the row (in any state) or open the appointment's card.
2. Each change with its time on the business clock, who made it ("Requested by the customer" if it was
   them) and what changed (from which professional or service to which, and the new time).
3. It is read-only: a single button, **Close**.
In: an appointment in any state.
Out: nothing (it only reads).
If it fails: "The appointment history could not be loaded."
Involved: none

### APPOINTMENT-F11 Delete an appointment
Status: done
Actor: owner, administrator
Screen: Agenda
Steps:
1. Tap **Delete** and confirm "Delete APT-…? Day to day it is better to Cancel, which keeps the
   record.".
2. The appointment disappears from the agenda (it is archived, not destroyed).
In: a pending, confirmed, cancelled or no-show appointment that is not charged.
Out: the `appointment.appointment.deleted` event.
If it fails: "This appointment cannot be deleted: it is in progress, completed or charged."; with its check
open at the till, `appointment.check_open`.
Involved: none

### APPOINTMENT-F12 Create a repeating appointment
Status: done
Actor: employee (for themselves), manager, assistant
Screen: Repeating
Steps:
1. In **Repeating**, tap **New repeating appointment**.
2. Pick the customer, the services, the professional (only those who perform them), the repetition (every
   day, every week, every two weeks or every month), the day of the week if it applies, the start day, the
   time, the minutes and, if you want, "Ends on (optional)" or "Number of appointments (optional)".
3. Tap **Create repeating appointment**: the series is created and the appointments of its window are
   booked (APPOINTMENT-F13).
In: the customer, the services and the professional (Customers, Services and Staff) and the Appointments
settings.
Out: the active series, its appointments and the `appointment.recurring.created` event.
If it fails: the reason in the panel; if the series was created and some date did not fit, they are listed
with their reason.
Involved: SERVICE-F33

### APPOINTMENT-F13 Book the appointments of a series
Status: done
Actor: employee, manager, assistant
Screen: Repeating
Steps:
1. Tap **Book appointments** on the series' row.
2. The dates of the window (from today to the maximum advance booking; with 0, 90 days) that were not given
   yet are booked, at most 50 per round; the screen goes on by itself with the next round.
3. A date that does not fit (closed, the professional does not work, block, another appointment, past,
   too soon) is skipped and listed with its reason; the others are booked. A date that was cancelled by
   hand is not booked again.
4. The notice says only what happened: "{n} appointments booked" and, if any did not fit, "{n} could not
   be booked" with each date and its reason. If they were all there already: "Nothing new to book: its {n}
   appointments were already booked".
5. If the series still has no date in the window: "Nothing to book yet: the next date of this series,
   {date}, is further ahead than the maximum advance booking. Tap «Book appointments» on the series when
   it gets closer.".
In: an active series and the maximum advance booking of the settings.
Out: the booked appointments, each with its `appointment.appointment.created` event.
If it fails: a paused series asks to reactivate it (`appointment.recurring_inactive`); one without dates,
"This repeating appointment has no dates left to book." (`appointment.recurring_ended`).
Involved: SCHEDULE-F11, STAFF-F16

### APPOINTMENT-F14 Edit a series from this appointment on
Status: done
Actor: employee (their own), manager, assistant
Screen: Repeating, Agenda
Steps:
1. Tap **Edit series**, or move an appointment of the series in the Agenda and choose **This and all
   following appointments**.
2. Change the time, the minutes, the repetition, the day of the week, the professional or the services;
   the panel says from which date it applies, how many appointments it reaches and, if any is charged, how
   many will not be touched.
3. Tap **Save from this occurrence on**.
4. What is before today, what is cancelled, in progress, completed or charged is not touched. The
   appointments that still fall on the pattern are moved; those that no longer fall on it are cancelled;
   those that do not fit stay as they were and are listed; the new dates are booked by themselves (if the
   series is active: editing a paused series leaves it paused; the one that was paused because its
   professional left books again when it is given another one). An appointment cancelled because it no
   longer falls on the pattern frees its date: if the pattern comes back, it is booked again. What has its
   check open at the till is not touched either.
5. The notice says only what happened: how many appointments move, with whom and with which services they
   go now, how many new dates are booked, how many are cancelled and which stay at their time, with their
   date; if no appointment had to change, "Saved: no appointment had to change.".
In: a series and the date from which it changes.
Out: the series split in two (the old one ends the day before) or, if the change starts on its first date,
the same series edited; the `appointment.recurring.updated` event.
If it fails: "Ends on (optional)" before the date of the change or the start of the series, in that field
("The end cannot be before the start.").
Involved: none

### APPOINTMENT-F15 Pause, reactivate or delete a series
Status: done
Actor: employee (their own), manager
Screen: Repeating
Steps:
1. Turn off the **Active** switch so that it stops booking; turn it on to reactivate it.
2. **Delete** asks to confirm "Delete {name}'s repeating appointments?"; the appointments already booked
   are kept.
In: a series.
Out: `appointment.recurring.updated` or `appointment.recurring.deleted`.
If it fails: "The repeating appointment's status could not be changed." and the series stays as it was.
Involved: none

### APPOINTMENT-F16 Block time in the agenda
Status: done
Actor: manager, assistant
Screen: Agenda (it paints it)
Steps:
1. Ask the assistant for a block with title, start and end, type (holiday, vacation, break, maintenance or
   other), whether it is all day and, if it belongs to a professional, which one.
2. From that moment nobody can book in that slot; without a professional, it blocks the whole business. An
   all-day block covers those whole days, in the booking and in the free times.
3. The "By professional" grid paints it striped on its row (or on all of them, if it is the business's).
In: the professional (Staff), if the block is theirs.
Out: `appointment.blocked_time.created` / `appointment.blocked_time.deleted`.
If it fails: "The end cannot be before the start."; removing one that is no longer there,
`appointment.blocked_time_not_found`.
Involved: none

### APPOINTMENT-F17 Charge the appointment at the till
Status: done
Actor: manager, employee (their own appointments), with the right to sell in Sales
Screen: Agenda
Steps:
1. Tap **Charge** on the appointment's row.
2. Appointments opens at the till a check linked to the appointment, titled "{customer} · {appointment
   no.}", with a **service** line for each service of the appointment (as if it were tapped in "Services"
   of the till, SALE-F38), with the professional who performed it and **at the price it was booked at**
   (the professional's own included), even if the catalogue has changed since then, and takes you to
   **Sales** with that check on screen.
3. At the till products or discounts are added, a service
   can be paid with a **voucher** of the customer (SALE-F27) and it is charged like any sale.
4. An appointment has **a single check**: while it is still open, the button is called **Go to the check**
   and goes back to it (it never opens another one, even if it is tapped at the same time on two devices);
   if the check is voided at the till, **Charge** opens a new one. With the check open, the appointment is
   not cancelled, nor marked as no-show, nor deleted: first the check is charged or voided (market
   decision).
5. When it is charged, the appointment is **charged** and, if it was not already, **Completed**; **Charge**
   is greyed out. If the sale is voided, the appointment stops being charged and **Charge** is active
   again.
In: a pending, confirmed, in progress or completed appointment that is not charged.
Out: the check open in Sales (`sale.order.opened`) and here `appointment.appointment.check_opened`; on
charging, the Sales event `sale.sale.created_from_appointment` and here `appointment.appointment.charged`;
on voiding the check, `sale.order.voided` and here `appointment.appointment.check_closed`.
If it fails: a cancelled or no-show appointment is not charged (`appointment.cannot_charge`); already
charged, also if the till has just charged it and the event has not arrived yet
(`appointment.already_charged`); a service without a tax category (`appointment.service_needs_tax_setup`);
Sales turned off (`appointment.sale_unavailable`); a service that is no longer offered or a price that is
not the appointment's, the Sales sentence (`sale.service_not_available`, `sale.booked_price_mismatch`);
without the right to sell, the Sales one.
Involved: SALE-F26, SALE-F27, SALE-F30, SALE-F38

### APPOINTMENT-F18 Appointment booked by the customer
Status: done
Actor: customer (WhatsApp, online booking)
Screen: none
Steps:
1. The automation offers the free times (APPOINTMENT-F02) and books with origin "WhatsApp" or
   "Online booking".
2. With **Confirm bookings made by the customer automatically** turned on (factory setting), it is born
   **Confirmed**; turned off, it is born **Pending** and adds to **N to confirm** and to the bell in the top
   bar ("Appointments to confirm"), on every device of whoever sees that agenda. If a service of the
   appointment has **Requires confirmation** (Services), it is born **Pending** even if the setting is on.
3. Always with the minimum notice, never in the past nor on top of another appointment of the
   professional.
4. The appointment gives its day and its time ready to be told to the customer ("Wednesday, December 2,
   2026", "17:00"), in their language and on the business clock.
In: the free times, the customer's card (the conversation recognises them by their phone) and the
Appointments settings.
Out: the **Confirmed** or **Pending** appointment with its origin and the `appointment.appointment.created`
event.
If it fails: too soon (`appointment.too_soon`), in the past (`appointment.in_past`) or the time already
taken (`appointment.slot_taken`); the automation offers another time.
Involved: CUSTOMER-F26, ONLINE_BOOKING-F01

### APPOINTMENT-F19 Adjust the booking rules
Status: done
Actor: owner, administrator
Screen: Settings
Steps:
1. Open the Appointments **Settings** tab.
2. Change the settings and tap **Save**: "Settings saved." Only what changes is saved.
   What is changed while it is saving is not lost: it stays on screen, still to save (hub#914).
In: the current Appointments settings.
Out: `appointment.settings.updated`.
If it fails: "The settings could not be saved." with each reason under its field, without losing what was
written; a calendar that ends before it starts, "The calendar has to end after it starts.". As in the form
windows, the notice goes as soon as something is changed and a field's reason as soon as that field is
corrected; both come back if the next try is refused too. A refusal that names no field stays until the next
try (hub#854).
Involved: none

### APPOINTMENT-F20 See a customer's appointments on their card
Status: done
Actor: whoever sees the agenda
Screen: Visit history (Customers card)
Steps:
1. Open the card in **Customers**.
2. At the end, the **Visit history** block shows their last 10 appointments, the most recent first, with
   the day and the time, the services, the professional, the state and the notes (the internal one first).
In: the customer's appointments that whoever is looking can see.
Out: nothing (it only reads). An automation reads it without notes or reasons.
If it fails: "The visit history could not be loaded." · empty: "No appointments yet for this customer."
Involved: CUSTOMER-F24

### APPOINTMENT-F21 Book several appointments at once (voucher or course)
Status: done
Actor: manager, assistant
Screen: none
Steps:
1. Ask the assistant for several appointments for the same customer, services and professional (up to
   50).
2. They are all booked or none: if one does not fit, it says which one and why.
In: the customer, the services, the professional and the dates with their time.
Out: the booked appointments, each with its `appointment.appointment.created` event.
If it fails: "{time}: {reason}" of the first one that does not fit; none is booked.
Involved: none

### APPOINTMENT-F22 Change the notes or the contact details of an appointment
Status: done
Actor: employee (their own), manager, assistant
Screen: Agenda (Edit) and assistant
Steps:
1. In "Edit appointment" change the notes, or ask the assistant to correct the phone or the email. **Edit** is
   only on a pending or confirmed appointment that is not charged; the notes of any other one are changed
   through the assistant.
2. Only what is sent changes. The phone is saved in international format, with the country prefix;
   one that is not a valid number is refused (`appointment.phone_invalid`) and nothing is saved.
In: an appointment.
Out: `appointment.appointment.updated` (without a history line if only notes or contact details change).
If it fails: the invalid phone is refused without saving anything; an appointment that does not exist,
`appointment.appointment_not_found`.
Involved: CUSTOMER-F11

### APPOINTMENT-F23 Merge the appointments when two customer cards are merged
Status: done
Actor: system
Screen: none
Steps:
1. In **Customers** two cards are merged (`customer.customer.merged`).
2. All the appointments and series of the absorbed card go to the one that stays; the names saved in each
   appointment do not change. Repeating it changes nothing else.
In: the Customers event with the card that stays and the absorbed one.
Out: `appointment.appointment.reassigned`.
If it fails: it is never left half done (all or nothing) and it retries by itself.
Involved: CUSTOMER-F13, ONLINE_BOOKING-F09

### APPOINTMENT-F24 Empty a customer's data when the card is erased
Status: done
Actor: system
Screen: none
Steps:
1. In **Customers** the personal data of a card are erased (`customer.customer.erased`).
2. Their appointments (in any state, also the deleted ones) are left without name, phone, email, notes and
   cancellation reason; their series without name, and paused; their history without names or reasons.
3. Where the name was, the agenda says "Deleted customer". The appointment, its number, the services, the
   price, the professional, the time, the state and the sale stay.
In: the Customers event with the erased card.
Out: the emptied appointments, series and history.
If it fails: it is never left half done (all or nothing) and it retries by itself.
Involved: CUSTOMER-F16, ONLINE_BOOKING-F12

### APPOINTMENT-F25 A professional leaves with upcoming appointments
Status: done
Actor: system
Screen: none
Steps:
1. In **Staff** someone is marked as having left (`staff.member.terminated`).
2. Their upcoming pending or confirmed appointments go to the **Unassigned** lane, with "Professional left:
   to be reassigned" in their history, and the agenda warns "{n} appointments have no professional: assign
   them by editing or dragging them to a row.". Their series are paused.
3. Deactivating someone or marking them not bookable does not touch their appointments: they stay on their
   row with the notice "… no longer takes new appointments".
In: the Staff event with the professional who left.
Out: `appointment.appointment.unassigned` for each appointment and the paused series.
If it fails: it is never left half done (all or nothing) and it retries by itself.
Involved: STAFF-F06

### APPOINTMENT-F26 A service is archived with appointments or series that use it
Status: done
Actor: system
Screen: none
Steps:
1. In **Services** a service is archived (`service.service.archived`).
2. Nothing is cancelled or changed (the market: Fresha, Phorest, TimeTap): the appointments already booked
   keep it (name, price and duration frozen) and can be charged; it is no longer offered for booking.
3. A series that uses it skips its new dates with the reason "A service of this series can no longer be
   booked." (`service_unavailable`) until it is edited with another service.
4. Before archiving, Services can ask how many upcoming appointments use it
   (`appointment.appointment.count_active_for_service`).
In: the archived service (Services).
Out: nothing changes in Appointments.
If it fails: a new booking with that service is refused (`appointment.service_not_bookable`).
Involved: SERVICE-F04

### APPOINTMENT-F27 See the week's agenda
Status: done
Actor: employee (theirs), manager
Screen: Agenda (By professional · Week)
Steps:
1. In "By professional", tap **Week**: one column per day, from Monday to Sunday, and one row per
   professional; ‹ › moves week by week.
2. Each day's appointments come in order, one below the other. In "List", **Week** shows the appointments
   of the seven days.
In: the week's appointments and the bookable professionals.
Out: nothing (it only reads).
If it fails: "The professionals could not be loaded." with **Retry**, instead of the grid.
Involved: none

### APPOINTMENT-F28 Get the system notice of a new or cancelled appointment
Status: done
Actor: employee (those of their agenda), manager
Screen: System notice and Agenda
Steps:
1. A customer books or cancels by themselves (WhatsApp, online booking).
2. At once, the device with the ERPlora application installed warns about it with a system notice, even
   if nobody is looking at the screen: "New appointment" or "Appointment cancelled" with the customer's
   name and, below, the services, the day and the time, and with whom.
3. What the front desk does is not notified (whoever does it already knows), and an employee only hears
   about their own agenda.
4. Tapping the notice opens the Agenda on that appointment's day.
5. On Android, the first time there is something to notify, the application asks first with a sentence of
   its own, "Let us keep you posted", with "Not now" and "Turn on notices"; then Android asks. After
   "Not now" it does not ask again by itself.
In: the bookings and cancellations the customer made in the last 24 hours.
Out: nothing (it only reads).
If it fails: if the connection drops or the application is opened again, those of the last 24 hours arrive
again and the device does not repeat a notice it already gave; the first day of a device it only learns
the ones that were already there, without notifying them all at once. In a browser there is no system
notice: what is waiting is seen in the Agenda. On Android, with notices denied, none shows. A customer
whose data were erased shows without a name ("New appointment").
Involved: none

## Services: what goes in and what comes out

Everything can be asked for through the screens, the assistant (by voice or by text, with the session of
whoever is speaking) and the API, with the same rules and the same permissions. An appointment is named by
its id or by its number (`APT-…`); a customer, by their id, their name, their phone or their email; a
service and a professional, by their id or their name; a time, as the business's wall-clock date and time
("2026-10-15 10:00"). If a name matches several, it says which ones and asks to choose.

### What it offers: queries (they read, they change nothing)

| What it gives | Who can | Flows | Service |
|---|---|---|---|
| The appointments of a range of days, by professional, state, customer or search, in pages (up to 100) | see appointments (all or their own) | F01–F11, F27 | `appointment.appointment.list` |
| A whole appointment | see appointments | F04, F10 | `appointment.appointment.get` |
| The history of an appointment | see appointments | F10 | `appointment.appointment.history` |
| A customer's last appointments, with notes | see appointments | F20 | `appointment.appointment.list_for_customer` |
| How many upcoming appointments use a service | see appointments | F26 | `appointment.appointment.count_active_for_service` |
| How many customers' bookings are waiting for confirmation | see appointments | F03, F18 | `appointment.appointment.count_to_confirm` |
| What the customer booked or cancelled by themselves in the last 24 hours, the newest first | see appointments (all or their own) | F28 | `appointment.appointment.notices` |
| The rows of the agenda (bookable professionals and those who keep appointments) | see appointments | F01, F04, F25, F27 | `appointment.agenda.lanes` |
| The free times of a day | see availability | F02, F18 | `appointment.availability.slots` |
| Whether a specific time can be booked and why not | see availability | F02 | `appointment.availability.check` |
| The blocks of a range | see availability | F16 | `appointment.blocked_time.list` |
| The series, with search and filters | see appointments | F12–F15 | `appointment.recurring.list` |
| A series with what a change from a date reaches | see appointments | F14 | `appointment.recurring.get` |
| The settings | see appointments | F19 | `appointment.settings.get` |

### What it offers: actions (they change data)

| What it does | Who can | Flows | Service |
|---|---|---|---|
| Books an appointment | book (or book for themselves) | F01, F18 | `appointment.appointment.create` |
| Books up to 50 appointments, all or none | book | F21 | `appointment.appointment.bulk_create` |
| Moves an appointment, changes its professional or services | change appointments (or their own) | F04, F06 | `appointment.appointment.reschedule` |
| Changes notes, contact details (and, if sent, the time) | change appointments | F22 | `appointment.appointment.update` |
| Confirms / starts / completes | change appointments | F03, F07, F08 | `appointment.appointment.confirm`, `.start`, `.complete` |
| Marks as no-show | change appointments | F09 | `appointment.appointment.mark_no_show` |
| Cancels (also on behalf of the customer) | change appointments | F05, F06 | `appointment.appointment.cancel` |
| Deletes an appointment / several | delete appointments | F11 | `appointment.appointment.delete`, `.bulk_delete` |
| Opens the appointment's check at the till | change appointments + sell | F17 | `appointment.appointment.charge` |
| Creates / removes a block | manage blocks | F16 | `appointment.blocked_time.create`, `.delete` |
| Creates a series and books its window | book | F12, F13 | `appointment.recurring.create` |
| Books the dates of a series | book | F13 | `appointment.recurring.materialize` |
| Edits a series from a date | change appointments | F14 | `appointment.recurring.update` |
| Pauses / reactivates / deletes a series | change appointments | F15 | `appointment.recurring.deactivate`, `.activate`, `.delete` |
| Saves the settings (only what is sent) | settings | F19 | `appointment.settings.update` |

Cancelling, marking as no-show, charging and deleting are **high risk** for the assistant: it asks for
confirmation before doing them.

### What it announces

| Event | When | What it carries |
|---|---|---|
| `appointment.appointment.created` | Booking (one per appointment of the batch and of the series) | The appointment, its number, the customer, the professional and its time |
| `appointment.appointment.confirmed`, `.started`, `.completed`, `.marked_no_show`, `.cancelled`, `.deleted` | Each change of state | The appointment |
| `appointment.appointment.rescheduled` | Moving (time, professional or services) | The appointment, the new time and the new professional |
| `appointment.appointment.updated` | Changing notes or contact details | The appointment |
| `appointment.appointment.charged` / `.uncharged` | Sale charged / voided | The appointment and the sale |
| `appointment.appointment.check_opened` / `.check_closed` | **Charge** opens its check / the check is voided at the till | The appointment and the check |
| `appointment.appointment.unassigned` | Its professional leaves | The appointment |
| `appointment.appointment.reassigned` | Merging of cards | The card that stays and the absorbed one |
| `appointment.blocked_time.created`, `.deleted` | Blocks | The block |
| `appointment.recurring.created`, `.updated`, `.deleted` | Series | The series |
| `appointment.settings.updated` | Saving settings with some change | Nothing |

The events carry identifiers, never notes or reasons (they may carry health data).

### What it reacts to

| Event of another app | What Appointments does | Flows |
|---|---|---|
| `customer.customer.merged` (Customers) | Moves appointments and series from the absorbed card to the one that stays | F23 |
| `customer.customer.erased` (Customers) | Empties the customer's data in appointments, series and history | F24 |
| `staff.member.terminated` (Staff) | Their upcoming appointments go to "Unassigned"; their series are paused | F25 |
| `sale.sale.created_from_appointment` (Sales) | Notes the sale on the appointment and completes it (409 if the appointment is cancelled, no-show or deleted, or charged with another sale) | F17 |
| `sale.sale.voided` (Sales) | Removes the charged mark from the appointment of that sale and its check | F17 |
| `sale.order.voided` (Sales) | Releases the voided check: **Charge** opens a new one | F17 |

### Contract with Sales

Sales is not a requirement of Appointments: Appointments uses its operation `sale.order.open` by name, with
the session of whoever charges (their right to sell), and reacts to its events. The check carries
`appointment_id`, the title "{customer} · {no.}" and one service line per service (`service_lines`,
SALE-F38: `service_id`, `staff_id` = the professional and `booked_price` = the booked price, which Sales
checks against `appointment.appointment.get`: `services[].service_id` and `services[].price`), so that a
voucher of the customer can pay for it (`sale.order.apply_voucher`, SALE-F27); never open-price lines.
Charging the check emits `sale.sale.created_from_appointment` with `sale_id` and `appointment_id`; voiding
the sale, `sale.sale.voided` with `sale_id`; voiding the open check, `sale.order.voided` with `order_id`.
The appointment keeps its check (`order_id`) while it is open: charging again looks it up with
`sale.order.get` and, if it is still open, returns it without opening another one (Sales, for its part,
returns the open check of an appointment with `already = true`).

### Who can do what

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| See the whole agenda | yes | yes | yes | no | `appointment.view_appointment` |
| See their own agenda | yes | yes | yes | yes | `appointment.view_own_appointment` |
| Book for anyone | yes | yes | yes | no | `appointment.add_appointment` |
| Book appointments for themselves | yes | yes | yes | yes | `appointment.add_own_appointment` |
| Change any appointment (states, move, cancel, charge, series) | yes | yes | yes | no | `appointment.change_appointment` |
| Change their own appointments | yes | yes | yes | yes | `appointment.change_own_appointment` |
| Delete appointments | yes | yes | no | no | `appointment.delete_appointment` |
| See availability and blocks | yes | yes | yes | yes | `appointment.view_schedule` |
| Block time | yes | yes | yes | no | `appointment.manage_schedule` |
| Settings | yes | yes | no | no | `appointment.manage_settings` |

"Their own" appointments are those of the Staff record linked to their account; an employee without a
linked record sees the agenda empty with the notice "Your account is not linked to any Staff record: there
is no agenda of yours to show.".
