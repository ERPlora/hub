<!-- generated from WORKBOOK.md sha256:512fd03b23a46220f82d419f451a91f8182f620705f1f7a718474e5929ad77b7 -->

## What it is for and who it is for

It is the business's **working-day record**. Each person on the team clocks in on arrival and clocks out
on leaving, with their breaks in between, with one tap and without choosing anything: whoever clocks is
the person of the session, through the Staff record linked to their account. The manager sees the
working days of the whole team, corrects the wrong ones (always with a reason, which stays in the
history) and exports the month in CSV for the accountant or the Labour Inspectorate.

In Spain every business with employees must record the start and the end of each working day, keep it
for four years and make it available to the worker, their representatives and the Inspectorate (art.
34.9 of the Workers' Statute, Royal Decree-law 8/2019). That is why:

- **No working day is ever deleted**, and a working day only changes with a **correction with a reason**,
  which leaves a new row in its history that is never deleted or edited either.
- **The worker sees their own working days** and who corrected them, when and why.

Who uses it:

- The **employee** clocks in, clocks out and takes their breaks, sees their working days, their
  correction history and the settings (without being able to change them), and exports their working
  days in CSV.
- The **manager**, the **administrator** and the **owner** also see the working days of the whole team
  and who is in right now, correct working days with a reason, clock someone else in or out (through the
  assistant or the API: "clock Ana out") and change the settings.

## Reference adopted

- **Odoo Attendances, Square Team, Toast and Lightspeed**: a working day is one person's clock-in and
  clock-out, with breaks inside; only one open working day per person.
- **Toast and Square**: the manager edits a working day with a trail (before, after, who and why).
- **Square, Factorial and Homebase**: the workplace radius is required only from personal devices; the
  counter POS never asks for the location, and clocking out is never blocked.
- **Homebase and Deputy**: the manager can clock someone on their team in or out, and who did it is
  kept.
- The time clock does not calculate payroll or overtime: on the market, that is another product.

## Before you start

1. The **Staff** app turned on: a clocking belongs to a **Staff record** (Time clock needs it and turns
   it on with it).
2. Each person who is going to clock has their record in **Staff** **linked to their account** ("Hub
   user", STAFF-F03). An account without a linked record sees "Your user is not linked to any staff
   record" and cannot clock.
3. To require the phone to be at the workplace, a manager turns it on in **Settings** and sets the
   workplace location (ATTENDANCE-F04), and an administrator chooses "Personal — a device only you use"
   on each person's phone, from that same phone, in **Settings › This device** (BASE-F62). By default no
   location is asked for.

## Screens

### Clock in
Reached from the app's menu, "Clock in". At the top, "Hello, <name>" and "It is <time>"; in the middle,
the state ("You are clocked out", "Clocked in since 09:00", "On break since 13:00"), the time since the
clock-in, which runs by itself, and the big button of the moment: "Clock in", or "Start break" / "End
break" and "Clock out". On the right (below on a phone), "Today" (Worked and Breaks, which run by
themselves) and "Recent days" (the last ten, with their status: "Open", "Closed" or "Needs review", as in
Records). Anyone on the team can open it.

### Records
Reached from the app's menu, "Records". A table of the working days of the chosen month: Date, Person,
Clock-in, Clock-out, Breaks (min), Worked, Status and Location, with the actions "Correct" and "History"
on each row; on a phone, cards. An employee sees only their own (without the Person column, with
"History"); the manager sees those of the whole team with the filters "Person" (with a search box),
"Month" and "Status", and above the table "Clocked in now": how many people have their working day open
and who, since what time and whether they are on a break. At the top, "Export CSV". On a narrow screen,
"Location" and "Breaks (min)" give way first (they stay in the cards and in "Columns"); each person's
name and their status read in full.

### Home panel
The Hub's **Home** shows the "Clocked in now" panel by default, grouped as "Time clock" in **Customize
panel**: the number of people who have their working day open right now, the same one "Clocked in now"
says above Records. Only whoever sees the working days of the whole team has it; an employee does not.

### Settings
The app's "Settings" tab. "Require location when clocking in from a personal device" (below it, where a
device is marked as personal), "Allowed radius", "Workplace location" (Latitude, Longitude and "Use my
current location") and "Flag for review after (hours)". Only a manager or an administrator can save;
everyone else sees it read-only with "Only a manager or an administrator can change these settings.".

## States of each screen

| Screen | Loading | Empty | Error |
|---|---|---|---|
| Clock in | "Loading…" | "No working days yet" in Recent days; without a linked record, "Your user is not linked to any staff record" | "The time clock could not be loaded…" and "Retry" |
| Records | "Loading working days…" | "No working days this month." (or "Nothing matches your search or filters.") | "The working days could not be loaded." and "Retry" |
| History | "Loading history…" | "This working day has never been corrected." | "The history could not be loaded." |
| Settings | loading indicator | — | the notice and "Retry" |
| Home "Clocked in now" panel | a grey bar where the number goes | "0" if nobody is in | "Unavailable" on the panel; the others carry on |

On all three pages: "Reconnecting…" while the live connection recovers (what is painted stays), "This
app is not active in this business" if it is turned off and "You do not have permission" if the role
does not reach.

## Flows

| Flow | What | Vertical | Status |
|---|---|---|---|
| ATTENDANCE-F01 | Clock in on arrival and clock out on leaving | common | done |
| ATTENDANCE-F02 | Take a break without leaving the working day | common | done |
| ATTENDANCE-F03 | Clock in from a phone when the business asks for the location | common | done |
| ATTENDANCE-F04 | Set the workplace location and when a forgotten working day is reviewed | common | done |
| ATTENDANCE-F05 | Flag for review a working day nobody closed | common | done |
| ATTENDANCE-F06 | See my working days of the month and who corrected them | common | done |
| ATTENDANCE-F07 | See the working days of the whole team | common | done |
| ATTENDANCE-F08 | Correct a wrongly clocked working day, with its reason | common | done |
| ATTENDANCE-F09 | See who changed a working day, when and why | common | done |
| ATTENDANCE-F10 | Export the month in CSV for the accountant or the Inspectorate | common | done |
| ATTENDANCE-F11 | See who is clocked in now | common | done (server, screen and Home panel) |
| ATTENDANCE-F12 | Clock someone else in or out | common | done (assistant and API) |
| ATTENDANCE-F13 | Close the open working day of whoever is terminated | common | done (reaction through the outbox relay) |

### ATTENDANCE-F01 Clock in on arrival and clock out on leaving
Status: done (server and screen)
Actor: owner, administrator, manager, employee
Screen: Clock in
Steps:
1. Open Time clock → "Clock in". You see "You are clocked out" and the "Clock in" button.
2. Tap "Clock in". You see "Clocked in at 09:00.", "Clocked in since 09:00" and the time since the
   clock-in, which runs by itself.
3. When you finish, tap "Clock out". You see "Clocked out at 17:00." and the "Clock in" button comes
   back.
4. "Today" shows the time worked and "Recent days" the working day, "Closed".
5. A working day that crosses midnight (from 22:00 to 06:00) is a single one and counts whole on the day
   it started (the business's day, not the device's).
In: the person of the session and their Staff record.
Out: the working day saved with the server's time, open on clocking in and closed on clocking out; the
clock-in and clock-out notices; "Clocked in now" goes up and down.
If it fails: clocking in with a working day already open is refused with "You already have an open
working day: clock out before clocking in again." and the screen shows the open working day (two taps at
once leave a single working day); without a linked record, "Your user is not linked to any staff record:
ask a manager to link it in Staff."; with the record inactive or on leave, "That staff record is not
active (inactive or on leave), so it cannot clock in." (clocking out still works); without a connection,
the error and "Retry".
Involved: STAFF-F03, ATTENDANCE-F05, ATTENDANCE-F11

### ATTENDANCE-F02 Take a break without leaving the working day
Status: done (server and screen)
Actor: owner, administrator, manager, employee
Screen: Clock in
Steps:
1. With the working day open, tap "Start break". You see "Break started at 13:00." and "On break since
   13:00"; the button becomes "End break".
2. On returning, tap "End break". You see "Break ended at 13:30.".
3. You can take as many breaks as you like, one after another.
4. If you tap "Clock out" in the middle of a break, the break ends at that very moment.
5. In "Today", "Breaks" adds up the break time and "Worked" already discounts it.
In: the person's open working day (ATTENDANCE-F01).
Out: each break saved inside its working day; the break started and ended notices.
If it fails: without an open working day, "There is no open working day: clock in first."; with a break
already running, "A break is already running."; ending a break that does not exist, "There is no running
break to end."; on a forgotten working day (ATTENDANCE-F05), "This working day has been open more than 12
hours and is waiting for review…".
Involved: ATTENDANCE-F01, ATTENDANCE-F05

### ATTENDANCE-F03 Clock in from a phone when the business asks for the location
Status: done (server and screen)
Actor: owner, administrator, manager, employee
Screen: Clock in
Steps:
1. The business has "Require location when clocking in from a personal device" turned on
   (ATTENDANCE-F04) and the person uses their own phone or laptop, on which an administrator chose
   "Personal — a device only you use" from that same device, in Settings › This device (BASE-F62). If
   they change it with Clock in open, the screen follows it without reloading.
2. Under the button you see "Your location is checked when you clock in from this device.". Tap "Clock
   in". You see "Getting your location…"; the first time, the phone asks for permission.
3. Inside the radius, you clock in as always and the working day keeps the position, the accuracy and the
   distance to the workplace, which **the Hub calculates** (it does not trust the one the device says).
4. Outside the radius you do not clock in and it says so: "You are 850 m from the workplace, outside the
   allowed 100 m. Move closer to clock in, or clock in at the counter.".
5. Clocking out is never blocked: the position is kept if it can be read and, if not, you clock out
   anyway.
6. On the counter POS (a shared device) the location is never asked for, even with the setting turned
   on; nor in a browser in which nobody has signed in with their account, which clocks like the counter.
7. That the device is personal is known by the Hub, never said by whoever clocks: neither the screen, nor
   the assistant, nor the API.
In: the location settings (ATTENDANCE-F04) and the mode of the device clocking (BASE-F62).
Out: the working day with the distance, the accuracy and whether it was inside the radius, only at the
moment of clocking; the exact coordinates, only when the business asks for the location and the device
is personal (they are never kept if nobody asked for them). They are kept as long as the working day:
four years. In Records, the "Location" column shows inside or outside.
If it fails: with the permission denied, "Location access is denied…"; without the workplace location
set, "The workplace location is not set yet…"; without a position, "Your location is needed to clock in
from this device…" (also when the assistant is asked from a personal device, which does not send the
position); if the GPS takes more than 15 seconds, "Getting your position took too long. Try again.". In
every case you do not clock in and you can clock in at the counter.
Involved: ATTENDANCE-F04, ATTENDANCE-F12, BASE-F62

### ATTENDANCE-F04 Set the workplace location and when a forgotten working day is reviewed
Status: done (server and screen)
Actor: owner, administrator, manager
Screen: Settings
Steps:
1. Open Time clock → "Settings".
2. Turn on "Require location when clocking in from a personal device" and choose the "Allowed radius":
   50, 100, 250, 500 or 1000 m. Below it you read "Only a device marked as personal is asked for its
   location; the counter POS never is. Each device is marked shared or personal on the device itself, in
   Settings › This device." (ATTENDANCE-F03).
3. From the workplace itself, tap "Use my current location": the latitude and the longitude are filled
   in and you see the accuracy read. You can also type them by hand.
4. In "Flag for review after (hours)" put from 1 to 24 hours (12 if you leave it).
5. Tap "Save" and you see "Settings saved.". Only what changed is sent.
In: nothing from other apps; without saved settings, the default values show.
Out: the settings that Clock in (ATTENDANCE-F03) and the working-day review (ATTENDANCE-F05) read; the
settings changed notice.
If it fails: a latitude or longitude out of range, only one of the two, or hours that are not a whole
number from 1 to 24 are pointed out in their field; with the location required and the workplace not
set, it warns "Set the workplace location or nobody on a personal device will be able to clock in.";
with the location denied, "Use my current location" keeps what was typed and warns, under the button,
"Location access is denied. Allow location in this browser to read the workplace position, or type the
coordinates." (in the installed app, which has no browser, "Location access is denied. Allow location in
your device settings to read the workplace position, or type the coordinates."); whoever is not a
manager sees the settings read-only.
Involved: ATTENDANCE-F03, ATTENDANCE-F05

### ATTENDANCE-F05 Flag for review a working day nobody closed
Status: done (server, worker task and screen)
Actor: system
Screen: none (the "Needs review" badge shows in Clock in and in Records)
Steps:
1. A working day open longer than the hours set in Settings (12 by default) is a forgotten working day:
   the person forgot to clock out. From that moment "Needs review" shows everywhere (Clock in, Records,
   the CSV), without time worked, and it does not count as "Clocked in now". The scheduled task (every 15
   minutes, in the worker) flags it in the database; the Hub also flags it when that person clocks in
   again.
2. No clock-out time is invented: neither "Clock out" nor the breaks close it (it answers "This working
   day has been open more than 12 hours and is waiting for review: a manager corrects it. Clock in to
   start a new day."); a manager sets it with a correction (ATTENDANCE-F08).
3. The person can clock in again without waiting for that correction: Clock in offers them "Clock in".
In: the hours of ATTENDANCE-F04.
Out: the working day in "Needs review" status; the working day flagged notice (only for those flagged).
If it fails: if the task does not run, the working day shows "Needs review" anyway and is flagged when the
person clocks in again.
Involved: ATTENDANCE-F04, ATTENDANCE-F08

### ATTENDANCE-F06 See my working days of the month and who corrected them
Status: done (server and screen)
Actor: employee (and anyone, for their own)
Screen: Records
Steps:
1. Open Time clock → "Records": you see your working days of the current month, without choosing a
   person.
2. In "Month" you can choose any of the last four years.
3. The open working day shows "Open", with the time worked so far marked "In progress"; the one still to
   be closed, "Needs review".
4. A corrected working day shows with the new times; "History" shows who corrected it, when, the before
   and the after and the reason.
In: their working days and their breaks.
Out: nothing; it only reads.
If it fails: "The working days could not be loaded." and "Retry".
Involved: ATTENDANCE-F09, ATTENDANCE-F10

### ATTENDANCE-F07 See the working days of the whole team
Status: done (server and screen)
Actor: owner, administrator, manager
Screen: Records
Steps:
1. Open Time clock → "Records": you see the month's working days of the whole team, with each person's
   full name (also of whoever was already terminated: their working days are kept four years).
2. Filter by "Person" (search by name), "Month" and "Status" ("Open", "Closed", "Needs review"), and sort
   by date, clock-in, clock-out, person or status.
3. In "Location" you see whether the clock-in and the clock-out were inside the workplace radius, or "No
   location recorded".
In: everyone's working days and breaks; the names, from the Staff records.
Out: nothing; it only reads.
If it fails: "The working days could not be loaded." and "Retry".
Involved: STAFF-F06, ATTENDANCE-F08, ATTENDANCE-F09, ATTENDANCE-F10, ATTENDANCE-F11

### ATTENDANCE-F08 Correct a wrongly clocked working day, with its reason
Status: done (server and screen)
Actor: owner, administrator, manager
Screen: Records
Steps:
1. In "Records", on the wrongly clocked working day, tap "Correct".
2. In "Correct working day" you see the clock-in and the clock-out in the business's time. Change the
   wrong one; leaving "Clock-out (empty = still open)" empty reopens the working day.
3. Write the "Reason" (required, at least 3 characters) and tap "Save correction".
4. You see "Working day corrected."; the row shows the new times and the recalculated time worked.
5. A "Needs review" working day is closed this way: it gets the clock-out and becomes "Closed". A break
   that was still running ends at the new clock-out.
In: the working day (ATTENDANCE-F07).
Out: the working day with the new times and a new entry in its history (ATTENDANCE-F09), which is never
deleted; the working day corrected notice; "Clocked in now" updates.
If it fails: "The clock-out must be after the clock-in." under the clock-out; "These hours overlap another
working day of this person." (touching is not overlapping: a working day can start at the instant the
previous one ended); "That person already has another open working day: this one cannot be reopened.";
a future time, "The time cannot be in the future."; without a reason, "Write a reason of at least 3
characters.". A refused correction changes nothing and leaves no trace. "Correct" only shows to whoever
can correct.
Involved: ATTENDANCE-F05, ATTENDANCE-F09, ATTENDANCE-F11

### ATTENDANCE-F09 See who changed a working day, when and why
Status: done (server and screen)
Actor: owner, administrator, manager; the employee, for their own
Screen: Records
Steps:
1. In "Records", on a working day, tap "History".
2. In "Correction history" you see each change, from the most recent to the oldest: who (or "System"),
   when, "Before" → "After" and the "Reason".
3. If nobody has corrected it, you see "This working day has never been corrected.".
In: the corrections of ATTENDANCE-F08 and ATTENDANCE-F13.
Out: nothing; the history cannot be edited or deleted.
If it fails: "The history could not be loaded.".
Involved: ATTENDANCE-F08, ATTENDANCE-F13

### ATTENDANCE-F10 Export the month in CSV for the accountant or the Inspectorate
Status: done (server and screen)
Actor: everyone (the employee, only their working days)
Screen: Records
Steps:
1. In "Records", choose the month (and, as a manager, the person and the status).
2. Tap "Export CSV"; meanwhile you see "Exporting…".
3. `attendance-2026-10.csv` downloads with one line per working day of the filter, all of them, not only
   those that fit on the screen: date, person, clock-in, clock-out, break minutes, minutes worked, status
   and whether the clock-in and the clock-out were inside the radius.
4. The file opens with the accents right in a spreadsheet.
In: the working days of the filter (ATTENDANCE-F06, ATTENDANCE-F07).
Out: the file downloaded on the device; nothing is saved in the Hub.
If it fails: a month without working days downloads only the header and warns "There are no working days
for this filter: the file only has the header."; if the download fails, "The CSV could not be exported.
Try again.".
Involved: ATTENDANCE-F06, ATTENDANCE-F07

### ATTENDANCE-F11 See who is clocked in now
Status: done (server, screen and Home panel)
Actor: owner, administrator, manager
Screen: Records ("Clocked in now") and Home
Steps:
1. Open "Records". Above the table, "Clocked in now" says how many people have their working day open
   and who, since what time and whether they are on a break.
2. On the **Home**, the "Clocked in now" panel shows by default with the same number.
3. Both change by themselves as soon as someone clocks in or out, starts or ends a break, or a working
   day is corrected.
4. A "Needs review" working day (or an already forgotten one) does not count: nobody knows whether that
   person is still in. A terminated record does not either (its open working day closes by itself,
   ATTENDANCE-F13). Whoever is on a break does count.
In: the open working days (ATTENDANCE-F01, ATTENDANCE-F08).
Out: nothing; it only reads.
If it fails: the error notice in its place, without covering the table; on the **Home**, the panel says
"Unavailable" and the others carry on.
Involved: ATTENDANCE-F01, ATTENDANCE-F02, ATTENDANCE-F08

### ATTENDANCE-F12 Clock someone else in or out
Status: done (assistant and API)
Actor: owner, administrator, manager
Screen: none (assistant and API)
Steps:
1. The manager tells the assistant "clock Ana in" or "clock Ana out" (or calls the API with the person
   by their id or their name).
2. Before clocking, the assistant asks for confirmation and says whom, in "Person", by their name (Ana
   López), never by a code; the manager confirms.
3. The Hub clocks Ana with the server's time, as if she did it, and keeps who did it. It never asks for
   the location, even if the business asks for it and the manager is on their personal phone: the manager
   vouches for her, and the manager's position is not kept on Ana's working day.
In: that person's Staff record.
Out: the same as ATTENDANCE-F01 and ATTENDANCE-F02.
If it fails: an employee cannot clock someone else ("You can only clock yourself in and out."); if the
name fits several people, it says which and asks to choose; if it does not exist, "That person does not
exist in Staff.".
Involved: STAFF-F01, ATTENDANCE-F01, ATTENDANCE-F02

### ATTENDANCE-F13 Close the open working day of whoever is terminated
Status: done (reaction through the outbox relay)
Actor: system
Screen: none
Steps:
1. A manager terminates a person in Staff (STAFF-F06) while they have their working day open.
2. Within a few seconds, Time clock closes that working day (and its running break) at that time, with a
   "System" correction whose reason is "Day closed when the person was terminated in Staff.".
3. In "Records" the working day shows "Closed", with that correction in its "History", and the person no
   longer counts in "Clocked in now".
In: the Staff notice `staff.member.terminated`.
Out: the working day closed, with its entry in the history; the working day corrected notice.
If it fails: if the person had no open working day, nothing is done (nor on a second delivery of the
notice).
Involved: STAFF-F06, ATTENDANCE-F08, ATTENDANCE-F09

## Services: what goes in and what comes out

Everything can be asked for through the screens, the assistant (by voice or by text, with the session of
whoever speaks) and the API, with the same rules and the same permissions. A person is named by their id
or by their name ("clock Ana out"); "my working day today" is `attendance.record.current`. Times travel in
ISO 8601 with their zone; durations, in seconds.

### What it offers: queries (they read and change nothing; all but the export can be followed live)

| What it gives | Who can | Flows | Service |
|---|---|---|---|
| My working day today: my record, whether I am in or on a break and since when, what I worked and the breaks of today and my last ten working days | clock | F01, F02 | `attendance.record.current` |
| The working days, with search by person, filters (person, mine, status, dates) and sorting, in pages (up to 100); the employee, only their own | clock | F06, F07 | `attendance.record.list` |
| A working day with its breaks and the position when clocking (someone else's, only with seeing the team or correcting); its name, the person and the day (Ana López · 6 Oct 2026) | clock | F07, F08 | `attendance.record.detail` |
| The CSV of the working days of the filter (the employee, only their own) | clock | F10 | `attendance.record.export` |
| The correction history of a working day (or of all), from the most recent to the oldest; the employee, of their own | clock | F09 | `attendance.correction.list` |
| Who is clocked in now (how many and who), with search | see the team | F11 | `attendance.presence.list` |
| How many are clocked in now (the Home "Clocked in now" panel) | see the team | F11 | `attendance.presence.count` |
| The people that can be filtered (Staff records, also the terminated ones with working days), with search | see the team | F07 | `attendance.person.list` |
| One of those people by their id, with their name and the status of their record: their own for whoever clocks; anyone for whoever sees the team, clocks others or corrects | clock | F01, F02, F12, F13 | `attendance.person.detail` |
| The settings | clock | F03, F04 | `attendance.settings.get` |

### What it offers: actions (they change data)

| What it does | Who can | Flows | Service |
|---|---|---|---|
| Clocks in (mine, or another person with "clock others") | clock | F01, F03, F12 | `attendance.record.clock_in` |
| Clocks out (and ends the running break) | clock | F01, F12 | `attendance.record.clock_out` |
| Starts a break | clock | F02, F12 | `attendance.break.start` |
| Ends the running break | clock | F02, F12 | `attendance.break.end` |
| Corrects a working day with a reason (high risk) | correct | F08 | `attendance.record.correct` |
| Saves the settings (only what is sent) | settings | F04 | `attendance.settings.update` |
| Flags the forgotten working days for review (scheduled task, system) | system | F05 | `attendance.record.review_stale` |
| Closes the open working day of a terminated person (reaction, system) | system | F13 | `attendance.record.close_for_terminated` |

There is no action to delete a working day, on purpose: the law asks to keep them four years.

### What it announces

| Notice | When | What it carries | Service |
|---|---|---|---|
| Clocked in | Clocking in | The working day (`id`) and the person (`member_id`) | `attendance.record.clocked_in` |
| Clocked out | Clocking out | The working day and the person | `attendance.record.clocked_out` |
| Break started | Starting a break | The break (`id`), the working day (`record_id`) and the person | `attendance.break.started` |
| Break ended | Ending a break (also when clocking out on a break) | The break, the working day and the person | `attendance.break.ended` |
| Working day corrected | A correction, by the manager or by the system | The working day, the person and the correction (`correction_id`) | `attendance.record.corrected` |
| Working day flagged for review | Only those the review flags | The working day and the person | `attendance.record.flagged` |
| Settings changed | Saving with some change | Nothing | `attendance.settings.updated` |

The notices never carry the position or the reason of a correction (personal data).

### What it reacts to and what it needs from other apps

- **Staff** (`requires = ["staff"]`): the working day belongs to a Staff record (`staff.Member`), and the
  person of the session is found through the record linked to their account. It reads the records'
  names (also the terminated ones) for the table, the CSV and the filter.
- `staff.member.terminated` → `attendance.record.close_for_terminated` (ATTENDANCE-F13), delivered by the
  worker's outbox relay once per notice.
- `staff.member.updated` and `staff.member.terminated` repaint the lists (a person's name or status).
- From the platform: the session and the business's time zone (phase 1: `Europe/Madrid`).

### Who can do what

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| Clock, see mine, my history, the settings and export mine | yes | yes | yes | yes | `attendance.clock` |
| See the working days of the whole team and who is in | yes | yes | yes | no | `attendance.view_all` |
| Correct working days | yes | yes | yes | no | `attendance.correct` |
| Clock someone else in, out or on a break | yes | yes | yes | no | `attendance.clock_others` |
| Change the settings | yes | yes | yes | no | `attendance.manage_settings` |
