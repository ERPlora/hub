## What it is for and who it is for
<!-- from WORKBOOK.md sha256:b6d18775c177 -->

Schedules says when your business is open: each weekday's hours, the public holidays and the days with other hours,
and a run of dates with other hours or closed, such as your vacation. Appointments and Reservations read it so as not to give
a time or a table while the business is closed. These are the premises' hours; each professional's are kept in Staff.

### In detail
<!-- from WORKBOOK.md sha256:53a0304d4aca -->

Schedules says **when the business is open**:

- the **usual week**: for each day, closed, open 24 hours or one or more intervals (split shift, or an
  interval that runs past midnight, such as 22:00–02:00);
- the **special days**: a closed holiday or a day with other hours, which can repeat every year
  (Christmas);
- the **temporary changes**: a run of dates with other hours or closed (the business's holidays, summer
  hours, building works).

These are the **business's** hours. They are not each professional's shift nor their time off (that is
**Staff**'s), nor the hours that can be booked (that is decided by **Appointments**, crossing both).

### Who uses it and what each one does
<!-- from WORKBOOK.md sha256:e7d83aa8e466 -->

- The **owner**, the **administrator** and the **manager** set the week, add, correct and delete special
  days and temporary changes, and change the settings.
- The **employee** does not open Hours (by its address, "No access" (BASE-F118)); appointments and bookings follow its hours.

Appointments reads it to offer free hours and to refuse an appointment while the business is closed (also
the ones that come through Online booking); Reservations, so as not to give a table while the business is
closed; the assistant answers with it "are you open on Saturday at six?".

## Reference adopted
<!-- from WORKBOOK.md sha256:4ce969cee876 -->

**What belongs to Schedules and what to Staff** (skill `market-decision`, 2026-10-14). All the products in
the table keep two different things: the premises' opening hours (what the customer sees and what closes
the business on a holiday) and each professional's shift (when they can be booked). The appointment book
books inside the professional's shift and, with the premises closed (holiday, holidays), offers nothing.

| Product | How it solves it | Source |
|---|---|---|
| Fresha | The premises' opening hours apart from the team's shifts; bookings go inside the shift; when the hours change it offers to carry them over to the shifts | https://www.fresha.com/help-center/knowledge-base/workspace-settings/588-update-your-business-opening-hours · https://www.fresha.com/help-center/knowledge-base/calendar/252-schedule-and-update-team-shifts |
| Square Appointments | The premises' "Business hours" and per-person "Staff hours", independent; bookings follow the professional's | https://community.squareup.com/t5/Payments-Troubleshooting/How-can-I-adjust-my-Square-Appointments-open-hours/m-p/144439 |
| Vagaro | The business's hours fixed in the profile, apart from each employee's hours | https://www.vagaro.com/pro/updates/business-hours |
| Google Business Profile | Weekly hours with several intervals a day, "open 24 hours" and special hours by date (holidays, closures) | https://support.google.com/business/answer/6303076?hl=en |
| Odoo | The company's working hours with its holidays ("Public holidays") that the employees inherit; each employee, their own hours | https://www.odoo.com/documentation/19.0/applications/hr/time_off/public_holidays.html |
| Business Central | A base calendar with non-working days, also recurring every year, assigned to the company or to the warehouse | https://learn.microsoft.com/bg-bg/dynamics365/business-central/across-how-to-assign-base-calendars |
| Toast | The restaurant's hours and its services (breakfast, lunch, dinner) by weekday, with no gaps or overlaps | https://support.toasttab.com/article/Setup-Restaurant-Hours-and-Services |
| Shopify | It has no store hours in the POS; the forum complains that in-store pickup ignores the weekend closure | https://community.shopify.com/t/feedback-bug-pickup-from-store-availability-does-not-account-for-store-hours-or-weekend-closures/553038 |

**Wins:** two sets of hours in two apps. Schedules keeps the business's (week, special days, temporary
changes); Staff, each professional's and their time off. Appointments books only if the appointment fits
**whole** in an open interval of the business **and** in the professional's availability. It is what all
the salon products and the ERPs do, and the Shopify case shows what happens when the premises' hours are
missing.
**Why not the others:** making the business's hours the union of the shifts (an option in Vagaro) leaves
no way to close on a holiday; putting the professional's shift in Schedules duplicates what Staff already
does.

That is why, of what the brief asked to look at, **everything "per person" is covered by Staff**: each
professional's weekly hours (STAFF-F13 to F15), their time off (STAFF-F17 to F20, F24) and their
availability (`staff.availability.for_member`, STAFF-F16). Schedules knows nobody in the team and does not depend on Staff.

Adopted from the market:

- **Google Business Profile**: several intervals a day, "open 24 hours" as 00:00–00:00 and special hours
  by date.
- **Square, Fresha and Google Business Profile**: seven fixed rows; a day is edited, never "added".
- **Odoo, Google Calendar, Microsoft Bookings, Business Central and Lightspeed Reservations**: the default
  week, Monday to Friday from 09:00 to 18:00 without a break and the weekend closed.
- Without a rule for a day, the business is **not** taken as open (code `no_hours`).

And this is decided here (same comparison):

- **An interval belongs to the day it opens** (Google Business Profile): a Saturday 22:00–02:00 is still
  open on Sunday at 01:00, whether it comes from the week, a special day or a temporary change, even if
  Sunday is a closed day.
- **A special day and a temporary change can be corrected** (Google, Fresha, Square edit them).

## Before you start
<!-- from WORKBOOK.md sha256:7eedc0a45ac8 -->

1. Turn on **Schedules** (it comes with the hair salon and the restaurant). It already has a default week
   (SCHEDULE-F12): Monday to Friday from 09:00 to 18:00, Saturday and Sunday closed.
2. The business's time zone is the Hub's (SCHEDULE-F09): the whole schedule is read with that clock.
3. In **Schedules → Hours**, tap **Yes, these are my hours** if the default week is yours
   (SCHEDULE-F03), or edit the days that change (SCHEDULE-F02). Until you do, the Home reminds you with
   "Confirm your opening hours".
4. In **Special days**, add the holidays and closures (SCHEDULE-F04) and, for several days in a row, a
   temporary change (SCHEDULE-F05).
5. If you want the week to start on Sunday, change it in **Settings** (SCHEDULE-F08).

## Screens
<!-- from WORKBOOK.md sha256:cffd3397a615 -->

Schedules opens from the **Schedules** menu and has three tabs: **Hours**, **Special days** and
**Settings**. What a person cannot do does not show, and the app refuses it even if they try through the
API or the assistant.

### Hours
<!-- from WORKBOOK.md sha256:fb236108f460 -->
Here is your week: one row per day with its hours (for example "10:00–14:00 · 17:00–20:00", "Open 24 hours" or
"Closed") and whether you open that day. Tap a day to change it: close it, open it 24 hours or give it one or more
intervals, such as a split shift or an interval that runs past midnight. While the week is the one we set by default, a
yellow notice asks you to check it and confirm it with "Yes, these are my hours".

#### Detail
<!-- from WORKBOOK.md sha256:1b4cc0990a7a -->
A table of **seven fixed rows**, one per weekday, with the columns **Day**, **Hours** and **Status**; there
is no add button: a day is edited. **Hours** says, for example, "10:00–14:00 · 17:00–20:00", "Open 24
hours", "Closed" or "Not set"; **Status** says "Open", "Closed" or "—" (not set); above it, **Columns** and
the switch between table and cards. The hours come in the language's clock (24 hours in Spanish, AM/PM in
English). The row action **Edit** (or tapping the row) opens "Edit hours — {day}" with: **Day**,
**Closed**, **Open 24 hours**, one line per interval (**Opens**, **Closes** and **Remove interval**),
**+ Add interval**, the hint "Split shifts: one line per interval (10:00–14:00 and 17:00–20:00). A closing
time earlier than the opening one runs past midnight (22:00–02:00)." and **Save day**. While nobody has
saved or confirmed the week, the yellow notice "These are default opening hours we set up for you. Check
they match your business — appointments outside them are refused." shows above the table with the button
**Yes, these are my hours** (the button, only for whoever can change the
hours). On a phone the table is painted as cards.

### Special days
<!-- from WORKBOOK.md sha256:ea1729ecba6e -->
Here go the exceptions to your week. In "Special days" you note a single day, closed or with other hours, such as a
holiday, which can repeat every year, like Christmas. In "Overrides" you note a run of dates with other hours or
closed, such as your vacation or summer hours. A special day wins over an override, and both win over the week. Tap a
row to correct it, or tap **Delete** on it to remove it.

#### Detail
<!-- from WORKBOOK.md sha256:6fa95797b305 -->
Two tables, one under the other, each with its title.

- **Special days**: columns **Date**, **Name**, **Status** ("Closed" or its hours, interval by interval)
  and **Yearly** ("Yes"/"No"); the search box "Search special day…", the funnel "Special day filters" with
  date (from–to), name, status and yearly, sort by column and 50 per page. **+** opens **New special
  day**: **Date**, **Name** ("Name (e.g. Christmas)"), **Status** ("Closed" or "Open (with hours)"; it
  starts on Closed), the same interval editor, **Repeats every year**, **Notes** and **Add day**. Row
  actions: **Edit** (or tapping the row; the same form, "Edit · {name}", with **Save**) and **Delete**.
- **Overrides** (the temporary changes): columns **From**, **To**, **Reason** and **Status**; the search
  box "Search override…", the funnel "Override filters" with dates, reason and status, and the same
  controls. Each table names its funnel and its view buttons, so they are not mistaken for the other's.
  **+** opens **New override**: **From**, **To**, **Reason**, **Status**, the interval editor and **Add
  override**. Row actions: **Edit** and **Delete**.
- Delete asks for confirmation: "Delete" · "«{name}» will be deleted. This cannot be undone." with
  **Cancel** and **Delete**.

### Settings
<!-- from WORKBOOK.md sha256:cd0b8c68ae3e -->
Here you choose whether the week starts on Monday or on Sunday, which only changes the order of the days in Hours. At
the top you see the business's time zone, the Hub's, with which all the hours are read. Whoever cannot change the
settings sees them without being able to save them.

#### Detail
<!-- from WORKBOOK.md sha256:07c45a57a555 -->
At the top, read-only, **Business timezone** with its name (for example, Europe/Madrid) and the note "It
is the Hub's, and the single clock the schedule is read with.". Below, **Week starts** (Monday or Sunday)
and **Save**, which confirms with "Saved". Whoever cannot change the settings sees the value without being
able to change it and without **Save**.

## States of each screen
<!-- from WORKBOOK.md sha256:bba133ae1b6c -->

| State | What the person sees |
|---|---|
| Loading | "Loading…" while the first result arrives; the week is not painted until the settings are there too (otherwise it would be sorted wrong). |
| Empty | "No special days." or "No overrides."; with a search or a filter, "No results". The week always has seven rows. |
| Error | The table's notice with "Retry", which says which one did not load ("The opening hours could not be loaded.", "The special days could not be loaded.", "The overrides could not be loaded." or "The settings could not be loaded.") and then the cause. A form's refusal shows inside the form, without losing what was typed, and each refused field (date, name, reason, notes) says its reason under it and loses it as soon as that field is corrected, even if another one says the same (hub#888); a row action's (delete, confirm the week, save the settings), above the table or the form. With the settings unread, **Week starts** is not shown, so as not to save a value that has not been read. |
| Reconnecting | What is painted stays; a strip warns "Reconnecting…". |
| App inactive | "This app is not active in this business". |
| No permission | What they cannot do does not show; if they arrive through another door, "You do not have permission". |

## Unsaved changes on Android
<!-- from WORKBOOK.md sha256:383184c7ac50 -->

In "Edit hours" of a day, "New special day", "New override" and their correction ("Edit · …"), the phone's Back
button asks "Discard changes?" when something typed or chosen has not been saved: "Keep editing" keeps it and
"Discard changes" closes the window without saving. With the window as it opened, Back closes it without asking
(BASE-F05).

## Flows
<!-- from WORKBOOK.md sha256:318f41e9b1d2 -->

| ID | Flow | Status |
|---|---|---|
| SCHEDULE-F01 | See the week's hours | done (server and screen) |
| SCHEDULE-F02 | Set a day's hours | done (server and screen) |
| SCHEDULE-F03 | Confirm the default week | done (server and screen) |
| SCHEDULE-F04 | Add a special day | done (server and screen) |
| SCHEDULE-F05 | Add a temporary change | done (server and screen) |
| SCHEDULE-F06 | Delete a special day or a temporary change | done (server and screen) |
| SCHEDULE-F07 | Load several special days at once | done (assistant and API) |
| SCHEDULE-F08 | Choose which day the week starts on | done (server and screen) |
| SCHEDULE-F09 | See the time zone the schedule is read with | done (server and screen) |
| SCHEDULE-F10 | Ask whether the business is open at a moment | done (assistant and API) |
| SCHEDULE-F11 | Give Appointments the hours of some days | done (Appointments and Reservations read it) |
| SCHEDULE-F12 | Start from a default week when turned on | done (when the tables are created) |
| SCHEDULE-F13 | Correct a special day or a temporary change | done (server and screen) |

### SCHEDULE-F01 See the week's hours
<!-- from WORKBOOK.md sha256:33ace6cd56d9 -->
Status: done (server and screen)
Actor: everyone
Screen: Hours
Steps:
1. Open **Schedules**; the **Hours** tab shows the seven days.
2. Read each day's intervals, "Open 24 hours", "Closed" or "Not set".
3. If the week starts on Sunday (you choose it in **Settings**), the table opens on Sunday; only the order changes.
In: the business's week and the "Week starts" setting.
Out: nothing; read only.
If it fails: the table says "The opening hours could not be loaded." with **Retry**; until both the week
and the settings are there not a single row is painted, so as not to show seven "Not set" that would look
like a business without hours.
Involved: none

### SCHEDULE-F02 Set a day's hours
<!-- from WORKBOOK.md sha256:973a199da7fa -->
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Hours
Steps:
1. In **Hours**, tap **Edit** on the day (or tap the row): "Edit hours — Monday" opens (with the day you
   tapped). The **Day** selector changes the day without closing.
2. Choose one of three things: **Closed**; **Open 24 hours**; or one line per interval with its opening
   and its closing (10:00–14:00 and 17:00–20:00 for a split shift; 22:00–02:00 runs past midnight).
3. Tap **Save day**: the form closes and the row shows the new summary.
In: the day (Monday to Sunday; the assistant also understands "el lunes" or "the monday") and its
intervals, up to 12. The order does not matter: they are saved sorted. 00:00–00:00 is "open 24 hours"; any
other interval with the same opening and closing is not valid.
Out: the day's intervals, which **replace** the previous ones (they do not pile up), and the notice
`schedule.week.updated`. The week becomes confirmed (SCHEDULE-F03): whoever saves a day has already seen it.
If it fails: under the intervals and without saving anything: "An open day needs at least one opening
interval.", "An interval cannot open and close at the same time; 00:00–00:00 is open 24 hours.", "Two
intervals overlap (or one runs past midnight into another); adjust the times so they do not clash.", "At
most 12 intervals a day.". A half-filled line is not sent: "Enter opening and closing times, or mark it as
closed".
Involved: Appointments and Reservations (they read the hours on the next booking)

### SCHEDULE-F03 Confirm the default week
<!-- from WORKBOOK.md sha256:431216219319 -->
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Home, Hours
Steps:
1. On the **Home**, while the week is the default one, "Finish setting up your business" brings "Confirm
   your opening hours" ("Check that the week's hours are your business's: if they are, confirm them in
   one tap; if not, edit the days that differ — bookings outside your opening hours are refused."),
   "Recommended", to whoever may change the hours. "Set up" leads to **Hours**.
2. With the yellow notice "These are default opening hours…" in sight, check that the days are your
   business's.
3. Tap **Yes, these are my hours**; the button is disabled while it works.
4. The notice disappears.
In: the week that is already saved; no hour is sent, so nobody confirms hours they have not been shown.
Out: the week marked as confirmed, without changing a single hour, and a notice `schedule.week.updated`. From
then on the week also governs table reservations (SCHEDULE-F12). Confirming twice changes nothing and
announces nothing. "Confirm your opening hours" is "Done" on the Home without a reload; also if, instead
of confirming, a day is saved (SCHEDULE-F02), even as closed. Changing "Week starts", a special day or
a temporary change does not confirm the week. The done step stays on the list with the same line, which
names no day and no hour: the assistant says it is done and, asked which hours there are, reads them in
Schedules (SCHEDULE-F01), never from the step (BASE-F12).
If it fails: above the table: "There are no weekly opening hours to confirm." if no day is saved (it cannot be
reached from the screen: the notice only shows when there is a week).
Involved: BASE-F01, BASE-F12

### SCHEDULE-F04 Add a special day
<!-- from WORKBOOK.md sha256:fcea507009e8 -->
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Special days
Steps:
1. In **Special days**, tap **+** (New special day).
2. Pick the **Date** in the calendar and type the **Name** (both required).
3. Leave **Closed** (what it comes with) or choose "Open (with hours)" and pick the times of one or more
   intervals, as when editing a day in **Hours**.
4. Tick **Repeats every year** if it falls on the same day and month every year (Christmas); if you want,
   **Notes**.
5. Tap **Add day**: the form closes and the day shows in the list.
In: date (a real one: 31 February is not valid), name (up to 200), closed or intervals, yearly and notes
(up to 1000). Through the assistant, the card says on its line the name, the date and its hours, or that it is
closed ("Create in Schedules: Christmas Eve · Date: Dec 24, 2027 · Opening intervals: 10:00 AM · 2:00 PM"; closed,
"Closed: Yes"): intervals of a day left closed are not saved, and the card does not say them.
Out: the special day (`schedule.special_day.created`). It beats everything else that day (SCHEDULE-F10,
F11). A yearly day applies **every year**, also the ones before its date; the one on 29 February only
exists in leap years.
If it fails: "There is already a special day on that date." under the date (also if two people create it at
the same time); intervals that are not valid, with the same reasons as when editing a day in **Hours**; an empty
name or one of only spaces, under the name. A date that had a deleted special day can be used again.
Involved: Appointments, Reservations

### SCHEDULE-F05 Add a temporary change
<!-- from WORKBOOK.md sha256:65cdd7daaa65 -->
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Special days
Steps:
1. In the "Overrides" table, tap **+** (New override).
2. Pick **From** and **To** in the calendar and type the **Reason** (all three required).
3. Leave **Closed** (the business's holidays) or choose "Open (with hours)" and pick the times of the
   intervals that apply on those dates (summer hours).
4. Tap **Add override**.
In: the two dates (both included), the reason (up to 200) and closed or intervals: the change applies to
every day of the range with the same hours. Through the assistant, the card says on its line the reason, its dates
together and its hours, or that it is closed ("Create in Schedules: Summer hours · When: Jul 1 – Aug 31, 2027 ·
Opening intervals: 8:00 AM · 3:00 PM").
Out: the temporary change (`schedule.override.created`). It beats the week, but loses against a special
day on that date (there is no warning that it overrides it: precedence settles it).
If it fails: "The end date cannot be before the start date." under To; "Those dates overlap the temporary
change “Vacation” (08/01/2026 – 08/15/2026)." under From: two changes do not cover the same day, so that the
answer does not depend on which one is read first; intervals that are not valid, with the same reasons as when
editing a day in **Hours**.
Involved: Appointments, Reservations

### SCHEDULE-F06 Delete a special day or a temporary change
<!-- from WORKBOOK.md sha256:2d7f84c39b99 -->
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Special days
Steps:
1. In the row, tap **Delete**.
2. On "«Christmas» will be deleted. This cannot be undone." (with its name) tap **Delete** (or **Cancel**).
3. The row disappears; the week (or the temporary change) rules those dates again.
In: the special day (by id, by its name or by its date; a yearly one answers for its day and month of any
year) or the temporary change (by id, by its reason or by a date it covers). The assistant: "delete the
Christmas holiday".
Out: the row and its intervals deleted in the same operation (`schedule.special_day.deleted`,
`schedule.override.deleted`). Its date becomes free.
If it fails: if someone else already deleted it, "That special day does not exist in this business." or "That
temporary change does not exist in this business.", without deleting anything else. If you ask the assistant with a
name that fits several, it tells you which ones and asks you to choose one; if you do not say which, it asks for its
name or its date.
Involved: Appointments, Reservations

### SCHEDULE-F07 Load several special days at once
<!-- from WORKBOOK.md sha256:0e2d8dfb0285 -->
Status: done (assistant and API)
Actor: assistant, API
Screen: assistant
Steps:
1. Ask the assistant to load a list of holidays with their date and their name (up to 366).
2. Each one is closed unless it says `is_closed: false` with its intervals; it can be marked yearly.
3. The answer says which days were created and which were not, with their reason.
In: the list. Each day carries a date and a name and, if it opens, its intervals with the rules of
SCHEDULE-F02.
Out: a special day and a notice `schedule.special_day.created` for each valid day (none if none gets in).
If it fails: a day whose date is already taken or repeated inside the list (`already_exists`), or open
without intervals or with intervals that are not valid (`invalid_hours`), is skipped with its reason and
the others get in. An empty list, one of more than 366 days, or one with a day without a real date or
without a name, is refused whole (422) before creating anything.
Involved: none

### SCHEDULE-F08 Choose which day the week starts on
<!-- from WORKBOOK.md sha256:4e6d5a82319c -->
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Settings
Steps:
1. In **Settings**, choose Monday or Sunday in **Week starts**.
2. Tap **Save**.
3. The **Hours** table opens on the chosen day.
In: the start day (the screen offers Monday or Sunday; the server accepts from 1, Monday, to 7, Sunday,
and the table rotates with any of them).
Out: the setting (`schedule.settings.updated`, only if it changes). It only moves the order of the rows:
it changes no hour nor what SCHEDULE-F10 answers.
If it fails: if it cannot be saved, the reason shows under the field and nothing changes.
Involved: none

### SCHEDULE-F09 See the time zone the schedule is read with
<!-- from WORKBOOK.md sha256:92b84971149c -->
Status: done (server and screen)
Actor: everyone
Screen: Settings
Steps:
1. Open **Settings**; at the top, "Business timezone" shows with its name (Europe/Madrid).
2. Read the note "It is the Hub's, and the single clock the schedule is read with.": the week, the special
   days, the temporary changes and what the assistant answers when you ask whether the business is open are read
   with that clock.
In: the Hub's zone.
Out: nothing; read only. Schedules keeps no zone of its own: the hours are wall-clock hours (10:00 is
10:00 before and after the clocks change, without touching anything).
If it fails: nothing to fail; the zone always comes from the server.
Involved: none

### SCHEDULE-F10 Ask whether the business is open at a moment
<!-- from WORKBOOK.md sha256:54ba4e906a23 -->
Status: done (assistant and API)
Actor: assistant, API
Screen: none
Steps:
1. A moment is asked about: with a zone (`2026-08-18T08:00:00Z`) it is moved to the business's clock;
   without a zone (`2026-08-18T10:00`, "tomorrow at ten" that the assistant writes like that) it is read
   as it is; with nothing, it answers for now.
2. It answers: open or closed, the rule that decided, the zone used, the local day and time and a stable
   code of the reason.
In: only the moment; the hours are read by this business's server, never sent by whoever asks.
Out: nothing saved. `is_open`, `code` (`exception_closed`, `exception_hours`, `open_interval`,
`closed_today`, `overnight_open`, `outside_hours` or `no_hours`), `source` (`special_day`, `override`,
`weekly` or `none`), `rule_id`, the intervals that explain it, `timezone`, `today`, `current_time` and, if
there is one, `reason` (the name of the special day or the reason of the change that won). Order: special
day of the exact date, yearly special day of the same day and month, temporary change covering the date,
week, nothing. It is open from the opening and stops being so right at the closing (at 18:00 sharp it is
already closed). The early hours of an interval that ran past midnight the day before count as open
(`overnight_open`), whatever rule it comes from. A day without a rule answers `no_hours`: it is not open.
If it fails: a moment that is not a real date and time: "That date and time are not valid."; one outside
1900–2200: "Choose a date between 1900 and 2200." (both, 422 under `when`).
Involved: none

### SCHEDULE-F11 Give Appointments the hours of some days
<!-- from WORKBOOK.md sha256:21d859e1adf2 -->
Status: done (Appointments and Reservations read it)
Actor: system (Appointments and Reservations), assistant
Screen: none
Steps:
1. Appointments (or Reservations) asks for the hours of a range of days (up to 366; a single day is fine).
2. Schedules picks for each day the rule that governs it (the same precedence as SCHEDULE-F10) and
   answers it.
3. Appointments books only if the appointment fits **whole** in an open interval (that day's or the
   past-midnight tail of the day before) and in the professional's availability that Staff gives
   (`staff.availability.for_member`, STAFF-F16).
In: the dates, in the business's days.
Out: read only (contract in "For whoever maintains it"). The end of the appointment can coincide with the
closing.
If it fails: under its field (422): "The end date cannot be before the start date.", "At most 366 days at
once." or, with a date outside 1900–2200, "Choose a date between 1900 and 2200.".
Involved: Appointments, Reservations

### SCHEDULE-F12 Start from a default week when turned on
<!-- from WORKBOOK.md sha256:dba10d6ca06d -->
Status: done (when the tables are created)
Actor: system
Screen: none
Steps:
1. When the Schedules tables are created in a business, Monday to Friday from 09:00 to 18:00 and Saturday
   and Sunday closed are planted.
2. The week comes out as **not confirmed**: the yellow notice of Hours (SCHEDULE-F03).
In: nothing from the person; the week is the market's, not the business's.
Out: seven days. Only once: an update never brings back days the business changed. While it stays
unconfirmed, the week governs appointments (also the ones from Online booking), but not table
reservations, which only apply it once the business saves or confirms it; special days and temporary
changes always govern.
If it fails: there is no screen; if there were no week, Appointments would see `no_hours`.
Involved: none

### SCHEDULE-F13 Correct a special day or a temporary change
<!-- from WORKBOOK.md sha256:50ac47c046ae -->
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Special days
Steps:
1. Tap the row (or **Edit**): "Edit · Christmas" opens (with its name, or an override's reason) with what was
   saved.
2. Change the date, the name or the reason, the status, the intervals, "Repeats every year" or the notes.
3. Tap **Save**.
In: the special day or the temporary change (by id or by name) and what is sent; what is not sent stays as
it was, and if the intervals are sent they are **all replaced**.
Out: the corrected day or change (`schedule.special_day.updated`, `schedule.override.updated`). Saving
without changing anything announces nothing.
If it fails: the same refusals as when creating it (another special day's date, another change's range) and, if
someone else deleted it meanwhile, "That special day does not exist in this business." or "That temporary change
does not exist in this business.".
Involved: Appointments, Reservations

## Services: what goes in and what comes out
<!-- from WORKBOOK.md sha256:2099f80e580d -->

Everything can be asked for through the screens, the assistant (by voice or by text, with the session of
whoever speaks) and the API, with the same rules and the same permissions. A weekday is named by its number
(0 = Monday) or by its name ("lunes", "monday"); a special day, by its id, its name or its date; a temporary
change, by its id, its reason or a date it covers. If a name fits several, it says which ones and asks to
choose (`schedule.ambiguous_reference`). Before correcting or deleting a special day or a temporary change, the
assistant asks for confirmation with its card (BASE-F97), which names the record as the screens name it, never by its
id: the special day by its name ("Special day: Christmas") and the temporary change by its reason ("Override: Summer
hours"). What the person asking cannot see is left out.

### What it offers: queries (they read and change nothing; all of them, except the assistant card's two, can be followed live)
<!-- from WORKBOOK.md sha256:3fb3727ac190 -->

| What it gives | Who can | Flows | Service |
|---|---|---|---|
| The week: the seven days in the order of "Week starts", each one closed, not set or with its intervals, and whether it is confirmed | view | F01, F03 | `schedule.week.get` |
| The special days with their intervals, with search, filters, sorting and pages (up to 100) | view | F04, F06, F13 | `schedule.special_day.list` |
| The temporary changes with their intervals, with search, filters, sorting and pages (up to 100) | view | F05, F06, F13 | `schedule.override.list` |
| The settings and the business's time zone, and whether the week is confirmed (the "Confirm your opening hours" step of the Home) | view | F03, F08, F09 | `schedule.settings.get` |
| Is it open at a moment? | view | F10 | `schedule.business.is_open` |
| The hours of each day of a range | view | F11 | `schedule.hours.for_range` |
| A special day by its id, with its intervals: what the assistant's card reads to name it (BASE-F97); not an assistant tool and no route in the API | view | F06, F13 | `schedule.special_day.get` |
| A temporary change by its id, with its intervals: what the assistant's card reads to name it (BASE-F97); not an assistant tool and no route in the API | view | F06, F13 | `schedule.override.get` |

### What it offers: actions (they change data)
<!-- from WORKBOOK.md sha256:4e16834c6e58 -->

| What it does | Who can | Flows | Service |
|---|---|---|---|
| Sets the intervals of a weekday | change the hours | F02 | `schedule.week.set_day` |
| Confirms the saved week | change the hours | F03 | `schedule.week.confirm` |
| Creates a special day | add | F04 | `schedule.special_day.create` |
| Creates up to 366 special days at once | add | F07 | `schedule.special_day.bulk_create` |
| Corrects a special day | change the hours | F13 | `schedule.special_day.update` |
| Deletes a special day | delete | F06 | `schedule.special_day.delete` |
| Creates a temporary change | add | F05 | `schedule.override.create` |
| Corrects a temporary change | change the hours | F13 | `schedule.override.update` |
| Deletes a temporary change | delete | F06 | `schedule.override.delete` |
| Saves the settings (only what is sent) | settings | F08 | `schedule.settings.update` |

### What it announces
<!-- from WORKBOOK.md sha256:2cb00a6291d8 -->

| Notice | When | What it carries | Service |
|---|---|---|---|
| Week changed | Saving a day; confirming the week | The day (`weekday`) or nothing when confirming | `schedule.week.updated` |
| New special day | Creating it (one per day in the bulk load) | Which one (`id`) and its date | `schedule.special_day.created` |
| Special day corrected | Correcting it with some change | Which one (`id`) and its date | `schedule.special_day.updated` |
| Special day deleted | Deleting it | Which one (`id`) | `schedule.special_day.deleted` |
| New temporary change | Creating it | Which one (`id`) and its dates | `schedule.override.created` |
| Temporary change corrected | Correcting it with some change | Which one (`id`) and its dates | `schedule.override.updated` |
| Temporary change deleted | Deleting it | Which one (`id`) | `schedule.override.deleted` |
| Settings changed | Saving them with some change | Nothing | `schedule.settings.updated` |

The notices do not carry a special day's name nor a change's reason: they are free text where the
business can write people's names.

### What it reacts to and what it needs from other apps
<!-- from WORKBOOK.md sha256:fd9f5d4bb6b8 -->
Nothing: Schedules depends on no app (`requires = []`) and listens to no notice. From the platform it uses
the business's time zone.

Who uses it: **Appointments** (the appointment book and each appointment, also the ones from Online
booking) and **Reservations** (each table reservation) read the hours of a range of days (SCHEDULE-F11)
and catch up with every Schedules notice. Reservations always counts the special days and the temporary
changes, but the week only once the business saves or confirms it (SCHEDULE-F03): the default week,
unconfirmed, does not limit it. Both say their days in the same form that Schedules gives ("Tuesday, March
5, 2030"). Schedules knows nothing of them. The platform (the Home) reads whether the week is confirmed for
the "Confirm your opening hours" step of "Finish setting up your business" (SCHEDULE-F03).

### Who can do what
<!-- from WORKBOOK.md sha256:2ee7901293b1 -->

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| See the week, the special days, the changes, the settings and whether it is open | yes | yes | yes | yes | `schedule.view` |
| Add special days and temporary changes | yes | yes | yes | no | `schedule.add` |
| Set the week, confirm it and correct special days and changes | yes | yes | yes | no | `schedule.change` |
| Delete special days and temporary changes | yes | yes | yes | no | `schedule.delete` |
| Change the settings | yes | yes | yes | no | `schedule.manage_settings` |
