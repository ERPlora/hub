## What it is for and who it is for
<!-- from WORKBOOK.md sha256:52c5c00036d6 -->

Staff is your team: who works, with which role, on which schedule each week, when they are away and how much they earn
per hour and in commission. The manager adds the records, approves time off and sees in Commissions what each
professional has earned; each employee sees their own record, what they have earned in Commissions and asks for their
time off. Appointments, Services, Time
clock, Tasks and the till read from here who works and who serves.

### In detail
<!-- from WORKBOOK.md sha256:e001308578e1 -->

Staff is the **business's team as a working resource**: who works, which catalogue role they have
("stylist", "waiter"), which schedule they work each week, when they are away, how much they earn per hour
and which commission they take. It answers "**who works and serves**", not "who gets in":

- The **access accounts**, their permission role (owner, administrator, manager, employee) and the PIN
  belong to the platform, not to Staff. Staff creates no accounts and grants no permissions.
- A professional's **record** can **hang** from an account of the business ("Hub user"), and that link is
  optional both ways: a professional without an account only shows in the agenda, and an account without a
  record does not serve. Deactivating an account does not touch the record.
- The **Staff role** is a catalogue label and **grants no permissions**: the account's role does.

Who uses it:

- The **owner** and the **administrator** do everything, deactivating and terminating included.
- The **manager** adds and edits records, roles, schedules and settings, sees the hourly rate, the
  commission, the HR notes and what each professional has earned in **Commissions**, registers time off
  and approves, rejects or cancels it.
- The **employee** sees the directory, the schedules and who is away (never the rate nor the reason of
  someone else's time off), sees their own record and their time off, **asks for their time off** and
  withdraws the requests that are still pending. In **Commissions** they see only their own row: what they did and
  what is due to them.

Appointments (and with it Online booking) reads from here who is bookable, their schedule and their
approved time off; Services, who can perform each service; Time clock, whose each clock-in is; Tasks, who
each task is assigned to; and the till reads the directory to name who serves (and with it, the kitchen
ticket). At the end of the day, **Commissions** gives what each professional has sold and earned.

## Reference adopted
<!-- from WORKBOOK.md sha256:cc9f63767917 -->

- **Salon (Fresha, Vagaro, Mangomint, Square Appointments)**: the professional as a resource of the agenda
  with their weekly schedule and their time off, bookable or not, and their commission.
- **Odoo Employees and Dynamics 365 Business Central**: the termination keeps date and reason on the
  record; the job position ("Job Position") is a label that is created, renamed, retired and not
  repeated.
- **Factorial, Personio, BambooHR, Deputy, Homebase and Square Team**: the employee **asks for** their time
  off and the manager approves or rejects it; pending → approved or rejected, pending or approved →
  cancelled; rejected and cancelled do not go back. A morning half day and an afternoon half day on the
  same day are compatible.
- **Which schedule rules a day** (Fresha "regular shifts" + exceptions): the schedule with dates beats the
  usual one, and a one-day schedule is the way to give an exception.

## Before you start
<!-- from WORKBOOK.md sha256:dc5a8400f706 -->

1. The accounts of whoever will get into the till are created in the SaaS (members of the business); they
   are only needed if you want to link their record.
2. In **Staff → Roles**, create the business's catalogue roles (STAFF-F04). A role is not a permission.
3. In **Staff → Staff**, add each professional (STAFF-F01), mark them **Bookable** if they will take
   appointments and link their account if they have one (STAFF-F03). For many at once, the assistant adds
   them in one go (STAFF-F07).
4. In **Staff → Schedules**, create each professional's weekly schedule (STAFF-F13). Without a schedule,
   Appointments does not restrict by schedule: only approved time off prevents the booking (STAFF-F16).
5. Time off is asked for or registered in **Time Off** (STAFF-F17, STAFF-F24) and only counts for the
   agenda once it is **Approved** (STAFF-F18).
6. The business's time zone decides what "today" is for "On leave today", for the Deactivate block and for
   the last day of a termination.
7. In **Staff → Settings**, the **default working day** (start, end and break) is the one a new schedule
   proposes (STAFF-F22 and STAFF-F13); untouched, from 09:00 to 18:00 with a one-hour break.

## Screens
<!-- from WORKBOOK.md sha256:6813f534c038 -->

Staff has five tabs: **Staff**, **Roles**, **Time Off**, **Schedules** and **Commissions** (this one,
only for whoever sees the pay), plus **Settings**; **Roles** and **Settings**, only for whoever can save the
settings. What a person cannot do does not show, and the app refuses it even if they try through the API or
the assistant.

### Staff
<!-- from WORKBOOK.md sha256:07c5b1795255 -->
Here is your team: one row per person with their name, their role, their email (for whoever sees the team's contact
details) and their status (**Active**, **Inactive** or **On leave**) and, for whoever sees the pay, their hourly rate. Above it, three figures: **Active
staff**, **On leave today** and **Pending time off**. **+** adds a person and a row opens their record to edit it; the
owner and the administrator also deactivate or terminate them from the row. Whoever has their account linked to a
record sees it in **My record**.

#### Detail
<!-- from WORKBOOK.md sha256:42ee105f94b3 -->
Above the table, three figures: **Active staff**, **On leave today** and **Pending time off**
(STAFF-F23). Below, the table with the search "Search member…" (first name, last name, employee ID or role, and
email and phone for whoever sees the team's contact details), columns **Name, Role, Email, Status** and, only for
whoever can see the pay, **Rate/h**; **Phone** exists but starts hidden. **Email** and **Phone** only show to whoever
sees the team's contact details (the owner, the administrator and the manager; BASE-F119): an employee sees the table
without those two columns, with no gaps. It sorts by any column but Email, Phone and Rate/h, and filters by First name,
Last name, Email and Phone (whoever sees the team's contact details), Role, Status (**Active**, **On leave**,
**Inactive**), Bookable, hire date, color and user; 50 per page. Terminated records do not show.

The **+** button opens **New**; a row opens **Edit · {name}**. Form: **First name, Last name, Email,
Phone, Employee ID, Role** ("No role"), **Hub user** ("No Hub access"), **Status** (only when editing:
Active, Inactive, On leave), **Bookable**, **Booking buffer (min)**, **Hire date**,
**Color**, **Specialties**, **Bio** and, for whoever can see the pay, **Hourly rate** and **Commission
(%)**. Row actions for the owner and the administrator: **Deactivate** and **Terminate**, both with a
confirmation. The rate (in the column, in the form and in "My record") is in the business's currency, its
country's in Settings → Business (euros in Spain, złoty in Poland), with its decimals (the yen has none) and
its symbol at the end of the field; while the business has not answered, an amount is "—", never euros or guessed
decimals.

#### Home panels
<!-- from WORKBOOK.md sha256:24d5a8acdba3 -->
The Hub's **Home** shows the five panels of Staff, grouped as "Staff" in **Customize panel**. By default
"Active staff" (how many people are **Active**), "On leave today" (different people with approved time off
that covers today) and "Today’s time off" (who is away today, full days first and then by name, with the
type of time off under each name) show; "Pending time off" (how many requests are waiting for an answer) and
"Staff by role" (a bar per role with its **Active** people, the role with the most first and ten at most;
each bar has its role's colour, and the one of a role without a colour, the panel's) are added from
**Customize panel**. Whoever does not see the time off does not get the three time-off ones,
and whoever does not see the team, neither "Active staff" nor "Staff by role". They change by themselves,
without reloading. The same figures stay inside Staff: the three above the Staff table, "Today’s time off"
above the Time Off one and the "Members" column of Roles (STAFF-F20 and STAFF-F23).

### Roles
<!-- from WORKBOOK.md sha256:304aab01fb91 -->
Table with the search "Search role…" and columns **Role, Description, Members** (how many **Active**
people hold it). **+** opens **New** (**Role name, Description, Color**); a row opens **Edit**, where the
role is also **retired** (it stops being offered) or turned active again.

### Time Off
<!-- from WORKBOOK.md sha256:d6cfe7b14c36 -->
Above the table, **Today’s time off**: who is away today, with the type and, if it is only part of the
day, its hours. Below, the table with a search by name and columns **Member, Type, From, To,
Status**, with filters by member, type, status and dates. Row actions: **Approve**, **Reject** and
**Cancel**, where they apply. **+** opens the form: **Member** (only for whoever manages time off; the
employee asks for it for themselves), **Type** (Vacation, Sick leave, Personal, Training or Other),
**From, To, Full day** (if it is turned off, **From (time)** and **To (time)**) and **Reason**. The reason
and the notes are only seen by whoever has the permission and by the person themselves.

### Schedules
<!-- from WORKBOOK.md sha256:2a68d9950069 -->
**Member** selector and the table of their schedules: **Schedule, Default, From, To, Active, Hours** (the
week summed up). Row actions: **Edit**, **Activate / deactivate** and **Delete** (with a confirmation).
**+** opens **New**: **Schedule** (name; empty, "Regular schedule"), **Effective from, Effective until,
Default** and one row per weekday with **Start, End, Break start, Break end** (or "Off"), with the default
working day of **Settings** already in place.

### Commissions
<!-- from WORKBOOK.md sha256:5e65cbd410a2 -->
Here you see what each professional has sold in a period and what is due to them in commission: "Today" on entering,
or "Yesterday", "This week", "This month" or "Custom", with its "From" and "To" dates. At the top, the total of
**Production** and of **Commissions**; below, one row per person with their role, what they have sold, their
"Commission %" and their "Commission", in the business's currency. The owner, the administrator and the manager see
one row per person on the team; an employee sees only their own, with everything they did. It updates by itself when a
sale is charged, voided or refunded.

#### Detail
<!-- from WORKBOOK.md sha256:c7a5ec353712 -->
At the top, the period: "Today" (on entering), "Yesterday", "This week" (since Monday), "This month"
(since the 1st) or "Custom", which opens "From" and "To" with the days that were on screen; next to it,
the days it counts. On a phone, the period is chosen in the "Period" drop-down, with the same options.
Below, two figures: **Production** and **Commissions** of the period, in the business's currency, like every
amount of the list. Then the list with the search "Search
professional…" and columns **Name, Role, Production, Commission %** and **Commission**: each person who can earn
a commission (Active or On leave), also without sales and with commission 0, and whoever sold in the
period even if they are no longer here ("No longer works here" or "Inactive" next to the name). It sorts by
name, role, production or commission. On a phone, one card per person. It updates by itself when a sale is
charged, voided or refunded and when a record changes.

### Settings
<!-- from WORKBOOK.md sha256:59f2453475ad -->
"Default working day", with "A new schedule proposes this working day from Monday to Friday, with the
break in the middle of the day.": "Working day starts (HH:MM)", "Working day ends (HH:MM)", "Break
duration (minutes)" and **Save**. While the business has never saved, the proposed values show.

## States of each screen
<!-- from WORKBOOK.md sha256:6af320578005 -->

| State | What the person sees |
|---|---|
| Loading | "Loading…" while the first result arrives; each figure shows "…". |
| Empty | "No staff members.", "No roles defined.", "No time-off requests." or "This member has no schedules yet."; with a search or a filter, "No results". "Today’s time off" with nobody: "Nobody is away today."; on the **Home**, a panel with nothing to show says "No data". Commissions with nobody who can earn one: "No one on the team can earn a commission yet."; without Sales in the business, "Commissions come from the sales" and "Turn on Sales to see what each professional earned.", without a list. |
| Error | The table's notice with "Retry"; in Settings, "The settings could not be loaded" with "Retry" and no form. The figures say "The figures could not be loaded" and "Today’s time off", "Who is away today could not be loaded", and the table keeps working; on the **Home**, the panel that cannot be read says "Unavailable" and the others go on. A refusal of a form shows inside the form, without losing what was typed, and each refused field says its reason under it and loses it as soon as that field is corrected, even if another one says the same (hub#888), the search pickers too (**Role**, **Hub user** and the **Member** of a time off), as soon as another one is chosen. The refusal of a row action shows above the table. |
| Reconnecting | What is painted stays; a strip warns "Reconnecting…". |
| App inactive | "This app is not active in this business". |
| No permission | What they cannot do does not show; if it arrives through another door, "You do not have permission". |

## Unsaved changes on Android
<!-- from WORKBOOK.md sha256:8bbcfe6718c8 -->

In this app's create and edit windows, the phone's Back button asks "Discard changes?" when something typed
or chosen has not been saved: "Keep editing" keeps it and "Discard changes" closes the window without saving.
With the window as it opened, Back closes it without asking (BASE-F05).

## Flows
<!-- from WORKBOOK.md sha256:d6c6af115722 -->

| ID | Flow | Status |
|---|---|---|
| STAFF-F01 | Add a professional | done (server and screen) |
| STAFF-F02 | Edit a professional's record | done (server and screen) |
| STAFF-F03 | Link the record to an account of the business | done (server and screen) |
| STAFF-F04 | Create, edit and retire a role | done (server and screen) |
| STAFF-F05 | Deactivate a professional | done (server and screen) |
| STAFF-F06 | Terminate a professional | done (server and screen) |
| STAFF-F07 | Add several professionals at once | done (assistant and API) |
| STAFF-F08 | See my own record and my time off | done (server and screen) |
| STAFF-F09 | Give the team to other apps | done (the other apps read it) |
| STAFF-F13 | Create a professional's weekly schedule | done (server and screen) |
| STAFF-F14 | Edit a schedule | done (server and screen) |
| STAFF-F15 | Activate, deactivate or delete a schedule | done (server and screen) |
| STAFF-F16 | Know when a professional can work | done (Appointments reads it) |
| STAFF-F17 | Register time off | done (server and screen) |
| STAFF-F18 | Approve or reject time off | done (server and screen) |
| STAFF-F19 | Cancel time off | done (server and screen) |
| STAFF-F20 | See who is away today | done (server and screen) |
| STAFF-F21 | Give each professional's rate and commission | done (server and screen) |
| STAFF-F22 | Change the Staff settings | done (server and screen) |
| STAFF-F23 | See the figures of the staff and by role | done (server and screen) |
| STAFF-F24 | Ask for my own time off | done (server and screen) |

The services each professional performs are in the Services app (SERVICE-F31, F32 and F33).

### STAFF-F01 Add a professional
<!-- from WORKBOOK.md sha256:641e2339816b -->
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Staff
Steps:
1. In **Staff**, tap **+**: **New** opens (without Status: the person is born **Active**).
2. Write First name and Last name (required, up to 100 characters). If you want, Email, Phone, Employee
   ID, Role, Hub user, Hire date, Color (#RRGGBB), Specialties, Bio, Booking buffer and, with the pay
   permission, Hourly rate and Commission (%). **Bookable** comes on.
3. Tap Save: the person shows in the table as **Active**, with their email and phone for whoever sees the team's
   contact details.
In: the form; the active roles (STAFF-F04), by id or by their name. The rate is typed in the business's
currency and saved in its smallest unit (cents in euros; in yen, whole yen); the commission is a percentage
from 0 to 100 with two decimals. Through the API or the assistant the initial
status and the HR notes can also be given.
Out: the record; Staff announces there is a new record (`staff.member.created`).
If it fails: under each field and without saving anything: first name or last name empty, an email that
is not one, a color that is not #RRGGBB, a negative rate, a commission outside 0–100, "That role is not
available: it does not exist in this business, or it has been deleted or retired.", "That Hub user has no
access to this business." or the account already linked to another record. Whoever cannot see
the pay cannot send it: the notice says which permission they lack. Two records with the same name, email or
employee ID are accepted. From the assistant, a role the business does not have (or that has been retired)
is checked before the confirmation card: no card shows, the assistant says that role is not available and
which ones there are, and nothing is created. Save (also when editing) is grey while the business has not yet said its
currency, because the hourly rate is read in it (without it, "1500" yen would be saved as 150,000). If the currency cannot be read, the window says so ("The business's currency could not be read", with the
reason) and offers "Retry", which asks for it again; as soon as it arrives, Save lights up.
Involved: BASE-F97, BASE-F119

### STAFF-F02 Edit a professional's record
<!-- from WORKBOOK.md sha256:11d2b90a469c -->
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Staff
Steps:
1. Tap the row: **Edit · Ana García** opens (the assistant names it by its name) with what the row already
   says, and "Loading…" while the whole record arrives; Save waits in grey until then.
2. Change what is needed, also before the record arrives: what was typed or chosen stays, and the record,
   when it arrives, fills only what has not been touched. **Status** offers Active, Inactive and
   On leave (the final termination is done with **Terminate**, in the row). "No role" removes the role, "No Hub access" unlinks the
   account, and the Hire date can be **cleared**.
3. Save: only what was sent changes.
In: the record (its email and phone, to whoever sees the team's contact details; with the permission, its rate,
commission and notes).
Out: the changed record (`staff.member.updated`). Saving without changing anything does not announce.
Setting Inactive here does not turn Bookable off; going back to Active does not turn it on
either.
If it fails: the same refusals as when adding; "That staff member does not exist in this business." if it
is no longer there (also if it was terminated); setting **Inactive** with pending or approved time off not
yet ended: "That staff member has pending or approved time off that has not ended yet. Resolve it
first.".
Involved: BASE-F119

### STAFF-F03 Link the record to an account of the business
<!-- from WORKBOOK.md sha256:cc6a704c4d8b -->
Status: done (server and screen)
Actor: owner, administrator, manager
Screen: Staff
Steps:
1. In the form, open "Hub user": "No Hub access" and the accounts with access to this business show.
2. Choose that person's account, or "No Hub access" to unlink, and save.
In: the active accounts with access to this business, only their identifier and their name
(`staff.account.list`; whoever can add or edit records reads them).
Out: the link. With it, the person sees their own record (STAFF-F08) and asks for their time off
(STAFF-F24). It changes no permission nor the commission: a sale counts for whoever was chosen when it was
charged (STAFF-F21). Terminating the record frees the account.
If it fails: "That Hub user is already linked to Ana García. A Hub user can belong to only one staff member:
unlink it there first, or pick another user.", also if two people link it
at the same time; "That Hub user has no access to this business.".
Involved: ATTENDANCE-F01, TASK-F03

### STAFF-F04 Create, edit and retire a role
<!-- from WORKBOOK.md sha256:98ba31251444 -->
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Roles
Steps:
1. In **Roles**, tap **+**, write the Name (required, up to 100) and, if you want, Description and Color,
   and save: the role shows with 0 members and can already be chosen in a record.
2. To change it, tap its row, change the name, the description, the color or the order, or turn
   **Active** off to retire it, and save.
In: what was typed.
Out: the role (`staff.role.created` or `staff.role.updated`). A retired role stops being offered in the
records; the ones that already carry it keep it. "Members" counts only **Active** people. A role grants
no permissions.
If it fails: "A role with that name already exists." (case-insensitive); "That
role does not exist in this business.".
Involved: none

### STAFF-F05 Deactivate a professional
<!-- from WORKBOOK.md sha256:094392549505 -->
Status: done (server and screen)
Actor: owner, administrator, assistant
Screen: Staff
Steps:
1. In the row, tap **Deactivate** and confirm "Take Ana García off the floor? They stop being bookable;
   nothing is deleted.".
2. The row turns **Inactive** and stops being bookable.
In: the record and its pending or approved time off that has not ended (with the business's "today").
Out: status Inactive and Bookable off (`staff.member.deactivated`). It does not touch schedules, time off,
account or appointments. To come back: STAFF-F02.
If it fails: "That staff member has pending or approved time off that has not ended yet. Resolve it
first." (it is rejected or cancelled in **Time Off**); "That staff
member is already inactive."; "That staff member does not exist in this business.".
Involved: none

### STAFF-F06 Terminate a professional
<!-- from WORKBOOK.md sha256:982571aabf24 -->
Status: done (server and screen)
Actor: owner, administrator
Screen: Staff
Steps:
1. In the row, tap **Terminate**: the dialog asks for "Last day (today if empty)" and "Reason
   (optional)", up to 500 characters.
2. Confirm: the person disappears from the table and from the directory.
In: the date (empty, today in the business's day) and the reason.
Out: the record **Terminated**, without Bookable, with its date and its reason, and its account freed
(`staff.member.terminated`; the notice does not carry the reason). It is final: it is not edited nor
reopened. Its schedules stop counting and its time off stops showing in the lists and in the figures. A
person who is Inactive or has time off can be terminated. Within a few seconds, the apps that depend on
Staff do their part with that notice: Appointments moves their future appointments to "Unassigned",
Services removes them from the services they performed, Time clock closes their open working day and Tasks
leaves their open tasks unassigned (their flows, in "Involved").
If it fails: "That staff member does not exist in this business." if it was already terminated.
Involved: APPOINTMENT-F25, SERVICE-F32, ATTENDANCE-F13, TASK-F15

### STAFF-F07 Add several professionals at once
<!-- from WORKBOOK.md sha256:34b070c0893f -->
Status: done (assistant and API)
Actor: assistant, API
Screen: assistant
Steps:
1. Whoever can add asks the assistant to add several people (up to 100 at once) with their name and, if
   they want, email, phone, role, hire date, rate, bookable, bio and specialties.
2. An **Active** record is created for each valid row.
3. The answer says which records were created and which rows were skipped with their reason.
In: the rows of the batch; the business's active roles.
Out: one record per valid row and one `staff.member.created` notice for each (none if none goes in).
If it fails: a row with a blank name, an email that is not one, a badly written date, a negative rate or a
role that is not the business's is skipped with its reason (`name_required`, `invalid_email`,
`invalid_hire_date`, `negative_hourly_rate`, `role_not_found`) and the others go in. More than 100 rows is
refused whole.
Involved: none

### STAFF-F08 See my own record and my time off
<!-- from WORKBOOK.md sha256:81805f096696 -->
Status: done (server and screen)
Actor: employee (and any person with a linked record), assistant
Screen: Staff (own view), Time Off
Steps:
1. A person with their account linked to their record taps **My record** in **Staff**, or opens **Time Off**.
2. They see their record with **their own** rate and commission (without the HR notes) and their own email and
   phone, even if they do not see the rest of the team's contact details, and their time off with its reason and its
   notes.
3. The record is read-only: a single button, **Close**.
In: the account they get in with (it cannot be faked).
Out: nothing changes. Without a linked record, the answer comes empty.
If it fails: without a record or without time off, empty.
Involved: none

### STAFF-F09 Give the team to other apps
<!-- from WORKBOOK.md sha256:9e06efb5b422 -->
Status: done (the other apps read it)
Actor: system
Screen: none
Steps:
1. An app that needs to name the team (the till in "Who is serving this check", and with it the kitchen
   ticket; Appointments, Services, Tasks) asks for the directory, with its permission to see the team.
2. It receives, per person: name, email and phone (empty if whoever asks does not see the team's contact details),
   employee ID, role, account, status, bookable, hire date and color; **never** the rate nor the commission. Up to 100 per page; it filters, among others, by user (to
   go from an account to its record).
In: nothing; it is a read.
Out: the directory of the records that are not terminated (also the Inactive and On leave ones).
If it fails: each app handles it its own way.
Involved: SALE-F16, APPOINTMENT-F01, SERVICE-F33, TASK-F07

### STAFF-F13 Create a professional's weekly schedule
<!-- from WORKBOOK.md sha256:cef9e38cdac3 -->
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Schedules
Steps:
1. Choose the person and tap **+**: **New** opens with a proposed week: from Monday to Friday, the default
   working day of **Settings**, with the break in the middle of the day and its start on the
   previous quarter of an hour; with the settings untouched, from 09:00 to 18:00 with a break from 13:00 to
   14:00. A day off proposes the same hours if it is ticked.
2. Set the name (empty, "Regular schedule"), the validity if it only applies on some dates, "Default" if it
   is the usual one and, day by day, Start, End and, if there is a pause, Break start and Break end.
3. Tap **Create schedule**.
In: the person (by id or by name) and the week. A day is an interval with an optional break.
Out: the schedule (`staff.schedule.created`). If it is "Default", the person's others stop being so.
**Which schedule rules a day**: of the active schedules in force that day, the one that is **not**
"Default" wins; among several, the one with the most recent "Effective from" and then the newest; if none
applies, that day has no schedule and Appointments does not restrict by schedule.
If it fails: under each field: "A schedule needs at least one working day with hours.", "The start time
must be before the end time.", "The break needs a start and an end, or neither.", "The break must fall
inside the working hours.", "Each weekday can appear only once.", "The schedule's validity ends before it
starts."; "That staff member does not exist in this business.". A shift that crosses midnight is not
accepted. "A schedule needs at least one working day with hours." shows on top of the week and goes away
as soon as any day changes (ticked, unticked, or an hour picked), without saving again. A day's
reason shows under that day and goes away as soon as that day changes (ticked, unticked, or one of its hours
picked), without saving again; the other days' reasons stay until those days change.
Involved: none

### STAFF-F14 Edit a schedule
<!-- from WORKBOOK.md sha256:aff27bb3664e -->
Status: done (server and screen)
Actor: owner, administrator, manager
Screen: Schedules
Steps:
1. Tap the schedule's row: **Edit · Regular schedule** opens with its week.
2. Change the name, the validity, "Default" or the days; a day you untick becomes "Off". Save: **the whole
   week is replaced**; the rest you do not send stays as it was and an empty date removes that validity.
In: the schedule and its whole week.
Out: the changed schedule (`staff.schedule.updated`), with the same "Default" rule and the same rule of
which schedule rules as when creating it.
If it fails: the same refusals as when creating, which go away the same way when what was refused
changes, or "That schedule does not exist in this business.".
Involved: none

### STAFF-F15 Activate, deactivate or delete a schedule
<!-- from WORKBOOK.md sha256:72aa25ddf1c9 -->
Status: done (server and screen)
Actor: owner, administrator, manager
Screen: Schedules
Steps:
1. **Activate / deactivate** changes at once: an inactive schedule rules no day.
2. **Delete** asks to confirm "Delete the schedule "Regular schedule"? Its hours stop counting for availability." and
   deletes it with its hours.
In: the schedule.
Out: `staff.schedule.updated` or `staff.schedule.deleted`. Deleting the "Default" one does not make
another one "Default".
If it fails: "That schedule does not exist in this business.".
Involved: none

### STAFF-F16 Know when a professional can work
<!-- from WORKBOOK.md sha256:759249ec6db0 -->
Status: done (Appointments reads it)
Actor: system (Appointments), assistant
Screen: none
Steps:
1. Whoever books asks about a person (by id or by name) and a range of days (up to 731; a single day is
   fine).
2. Staff chooses, for each day, the schedule that rules (STAFF-F13) and splits it by the break.
3. It answers, per day: which schedule rules (none = "no schedule"), its intervals, the **approved** time
   off that covers it (full day or with its hours, without the type nor the reason) and what is left free:
   the intervals minus that time off.
In: the person and the dates, in business days.
Out: read only. Pending, rejected or cancelled time off does not count.
If it fails: "That staff member does not exist in this business." (also if it was terminated); a range
backwards or of more than 731 days is refused in the field.
Involved: APPOINTMENT-F01, APPOINTMENT-F02, APPOINTMENT-F04, APPOINTMENT-F13

### STAFF-F17 Register time off
<!-- from WORKBOOK.md sha256:bf0bc72c8790 -->
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Time Off
Steps:
1. In **Time Off**, tap **+**, choose the Member, the Type (Vacation comes), From and To, "Full day" (or
   its hours) and, if you want, the Reason.
2. Tap Save: the time off shows as **Pending**.
3. Through the assistant, the confirmation card puts first whose it is, the kind and its days as one period ("Dec
   21 – 31, 2026"; with its hours if it is part of the day).
In: the person (any record that is not terminated, an Inactive one too; by id or by name) and the time
off, with optional reason and notes. With hours, the same ones apply each day of the range.
Out: the Pending time off (`staff.time_off.created`; the notice does not carry the reason). It does not
change the agenda yet: it only counts when it is approved (STAFF-F18). It does not notify the person.
If it fails: under each field: "The end date cannot be before the start date.", "A half-day absence needs
a start and an end time.", "The start time must be before the end time."; "That staff member already has
pending or approved time off in those dates.": they overlap if they share
any day and, when both are by hours, also any hour (a morning one and an afternoon one on the same day do
**not** clash); rejected and cancelled ones do not count. "That staff member does not exist in this
business.".
Involved: none

### STAFF-F18 Approve or reject time off
<!-- from WORKBOOK.md sha256:7915f2306130 -->
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Time Off
Steps:
1. Find the **Pending** time off (the Status filter helps).
2. Tap **Approve** or **Reject**: the row turns **Approved** or **Rejected**.
In: the time off and the person's other approved ones.
Out: the new status and, when approving, who approved and when (`staff.time_off.approved` or
`staff.time_off.rejected`). **Approved** takes those hours off the availability (STAFF-F16) and counts in
"On leave today"; Rejected changes nothing. It does not notify the person nor look at their appointments.
Whoever manages time off can also approve their own.
If it fails: "That staff member already has approved time off in those dates." (when approving); "That
time-off request cannot change to that status from its current one."; "That
time-off request does not exist in this business.".
Involved: none

### STAFF-F19 Cancel time off
<!-- from WORKBOOK.md sha256:f22dfea997a0 -->
Status: done (server and screen)
Actor: owner, administrator, manager; the employee, only their own pending one
Screen: Time Off
Steps:
1. In the row of a **Pending** or **Approved** time off, tap **Cancel** and confirm.
2. The row turns **Cancelled**; if it was approved, its hours are available again.
In: the time off.
Out: the Cancelled status (`staff.time_off.cancelled`), which is final; it keeps who approved it.
If it fails: "That time-off request cannot change to that status from its current one."; an employee who
tries to cancel someone else's or one of their own that is no longer pending (also if it gets approved
while they cancel it): "You can only cancel your own pending requests.".
Involved: none

### STAFF-F20 See who is away today
<!-- from WORKBOOK.md sha256:3ca068cd8e6d -->
Status: done (server and screen)
Actor: everyone
Screen: Time Off, Staff, Home
Steps:
1. Open **Time Off**: above the table, "Today’s time off" lists whoever has **approved** time off that
   covers today (in the business's day), full days first and then by name, with the type and, if it is only
   part of the day, its hours, and says how many they are.
2. In **Staff**, the "On leave today" figure counts the different people who are away today.
3. On the **Home**, the "Today’s time off" and "On leave today" panels show by default: the same list, with
   the type of time off under each name, and the same figure.
4. For the detail, the **Time Off** table with its filters.
In: the approved time off and the records.
Out: read only; without the reason. It changes by itself when time off is approved or cancelled.
If it fails: without time off, "Nobody is away today." (on the **Home**, "No data"); if it cannot be read, "Who
is away today could not be loaded" in its place (on the **Home**, "Unavailable"), and the table keeps working.
Involved: none

### STAFF-F21 Give each professional's rate and commission
<!-- from WORKBOOK.md sha256:bf44b7507bac -->
Status: done (server and screen)
Actor: owner, administrator, manager (the whole team); employee (their own row of Commissions)
Screen: Staff (Rate/h column and form), Commissions
Steps:
1. Whoever can see the pay sees the rate, the commission and the HR notes of each record.
2. **Commissions** shows each person who can earn a commission (Active or On leave) with their name, their
   role and their commission, also without sales or with commission 0, and whoever sold in the period even
   if they are no longer here ("No longer works here" or "Inactive" next to the name). That is the list of whoever
   sees the pay and the business's totals (the owner, the administrator and the manager); whoever lacks either, like
   the employee, sees only their own row, also without sales, and without a record in Staff sees none.
3. To know what each professional has earned, open the **Commissions** tab. "Today" shows: what each person
   has sold in the business's day, with what was refunded already taken off, without the vouchers they sold
   and with what the voucher sessions they did are worth added, their commission and what is
   due to them (sold × commission ÷ 100, rounded to the smallest unit of the business's currency, the cent
   in euros, only once per person; half a unit rounds up). At the top, the total sold and the total of
   commissions.
4. For another period, choose "Yesterday", "This week", "This month" or "Custom" and set "From" and "To".
5. It counts what was attributed to each person in Sales: the line they did (an appointment's, to the
   appointment's professional) or, if the line does not say who, whoever served the check. With «Me» at
   the till, that is whoever was signed in, if their account has a record in Staff; otherwise that sale
   counts for nobody. Each person's row counts everything they did, also on a sale someone else charged or that
   was attributed to a colleague, even if they cannot open that sale: the employee sees on their own row the same
   as the manager sees of them.
In: each record's rate and commission and, from Sales, each professional's production in the period (refunds
already taken off: what comes back goes to whoever sold it; the vouchers they sold left out and the value of
their voucher sessions added). Sales is optional.
Out: read only.
If it fails: without the permission to see the team, its address says "No access"; without Sales, "Commissions come
from the sales"; with "To" before "From", "The end date cannot be before the start date." under "To";
with only one day, "A period of your own needs its first and its last day."; with more than two years,
"Ask for at most 731 days at a time.".
Involved: SALE-F16, SALE-F27, SALE-F28

### STAFF-F22 Change the Staff settings
<!-- from WORKBOOK.md sha256:2496eb28df18 -->
Status: done (server and screen)
Actor: owner, administrator, manager
Screen: Settings
Steps:
1. Open **Settings**: the saved default working day shows or, if it was never saved, the proposed one (from
   09:00 to 18:00 with a 60-minute break).
2. Pick the start and the end times (the end, after the start: a schedule's day does not cross
   midnight) and change the break, from 0 (no break) to 480 minutes and shorter than the working day.
3. Tap **Save**.
   What is changed while it is saving is not lost: it stays on screen, still to save.
In: what was sent; the rest stays as it was.
Out: the business's settings (`staff.settings.updated`), with the hours always in HH:MM. From that moment,
a new schedule proposes that working day from Monday to Friday, with the break in the middle of the day
(STAFF-F13).
If it fails: a value outside its range shows under its field and nothing is saved. A working day that ends
before it starts says "The start time must be before the end time." under "Working day ends (HH:MM)"
(under "Working day starts (HH:MM)" if only the start was changed), and a break that does not fit in the
working day, "The break must fall inside the working hours." under the break; nothing is saved. As in the form
windows, the notice goes as soon as something is changed and a field's reason as soon as that field is
corrected; both come back if the next try is refused too. A refusal that names no field stays until the next
try. If the settings cannot be read, "The settings could not be loaded" with "Retry", without a
form: values that are not the business's are never offered to be saved.
Involved: none

### STAFF-F23 See the figures of the staff and by role
<!-- from WORKBOOK.md sha256:40b9fc328dd0 -->
Status: done (server and screen)
Actor: everyone
Screen: Staff, Roles, Home
Steps:
1. Open **Staff**: above the table three figures show: "Active staff" (how many people are **Active**), "On
   leave today" (different people with approved time off that covers today) and "Pending time off" (how
   many requests are waiting for an answer). On a phone they go on a single line, so that the table can
   still be seen below.
2. The figures change by themselves, without reloading, when someone adds, deactivates or terminates a
   record or asks for, approves, rejects or cancels time off.
3. "Members" of **Roles** gives how many **Active** people each role has.
4. On the **Home**, "Active staff" and "On leave today" show by default, and "Pending time off" and "Staff by
   role" (a bar per role, the one with the most **Active** people first and ten at most) are added from
   **Customize panel**; they give the same figures and change the same way, without reloading.
In: the records, the roles and the time off. Through the assistant or the API, the figures also give how
many records there are and how many are **On leave** and **Inactive**.
Out: read only. The terminated records and their time off do not count.
If it fails: without data, zeros; if they cannot be read, "The figures could not be loaded" in their place,
and the table keeps working. While they arrive, each figure shows "…".
Involved: none

### STAFF-F24 Ask for my own time off
<!-- from WORKBOOK.md sha256:7869dfa45891 -->
Status: done (server and screen)
Actor: employee (and any person with a linked record), assistant
Screen: Time Off
Steps:
1. In **Time Off**, tap **+**: the form does not ask for the Member, the time off is yours.
2. Choose the Type, the dates, "Full day" (or its hours) and, if you want, the Reason, and save.
3. It shows as **Pending** until a manager approves or rejects it; while it is pending you can
   withdraw it with **Cancel**.
In: your record, through your linked account (STAFF-F03).
Out: the Pending time off, with the same notice as STAFF-F17 (`staff.time_off.created`).
If it fails: the same refusals as when registering time off; without a linked record: "Your user is not linked to
any staff member: ask a manager to link it.".
Involved: none

## Services: what goes in and what comes out
<!-- from WORKBOOK.md sha256:399b20f641b0 -->

Everything can be asked for through the screens, the assistant (by voice or by text, with the session of
whoever speaks) and the API, with the same rules and the same permissions. A person is named by their id or
by their name; if the name fits several, it says which ones and asks to choose
(`staff.ambiguous_member`). Before changing anything, the assistant asks for confirmation with its card (BASE-F97),
which names each record as the screens name it, never by its id: a person and a role by their name, a schedule by
whose it is and what it is called ("Ana López · Regular schedule") and a time-off request by whose it is, its type and
its days ("Ana López · Vacation · Nov 2, 2026 – Nov 5, 2026"). What the person asking cannot see is left out.

### What it offers: queries (they read and change nothing; all but the accounts and the session's record can be followed live)
<!-- from WORKBOOK.md sha256:ccc5c3cbea76 -->

| What it gives | Who can | Flows | Service |
|---|---|---|---|
| The directory, with search, filters and sorting by any column but the email and the phone, in pages (up to 100); the email and the phone, empty for whoever does not see the team's contact details, who neither searches nor filters by them | see | F01, F02, F09 | `staff.member.list` |
| A person's record (without pay; the email and the phone, empty for whoever does not see the team's contact details) | see | F02 | `staff.member.detail` |
| My record, with my rate, my commission, my email and my phone | see | F08 | `staff.member.mine` |
| The record of whoever holds the session, only its id and name: Sales attributes «Me» to it | anyone signed in | SALE-F16 | `staff.member.current` |
| Rate, commission and HR notes, with the directory's filters, sorting and pages (the Rate/h column reads the same rows) | see the pay | F21 | `staff.member.compensation` |
| The commission sheet: who can earn a commission, with their record, their account and their commission | see the pay | F21 | `staff.commission.summary` |
| What each professional earned in a period (today, yesterday, this week, this month or two days): sold with refunds taken off, commission and totals; it says if the business has no Sales | see: one's own row; with seeing the pay and the business's totals, the whole team's | F21 | `staff.commission.report` |
| The figures: records, active, on leave, inactive, away today and pending requests | see | F23 | `staff.member.stats` |
| The roles with their active members, with filters and sorting | see | F04, F23 | `staff.role.list` |
| A role by its id, also a retired one: what the assistant's card reads to name it (BASE-F97) | see | F01, F02, F04, F07 | `staff.role.detail` |
| A person's schedules with their week | see | F13–F15 | `staff.schedule.list` |
| A schedule with its week and the `label` the assistant's card names it by (BASE-F97) | see | F14, F15 | `staff.schedule.detail` |
| A person's availability by days | see | F16 | `staff.availability.for_member` |
| The time off, without reason, with filters and sorting | see time off | F17–F19 | `staff.time_off.list` |
| One time off with its reason, its notes and who approved it | see the time-off detail | F18 | `staff.time_off.detail` |
| One time off without its reason and with the `label` the assistant's card names it by (BASE-F97) | see time off | F18, F19 | `staff.time_off.get` |
| Who is away today, with the type of each time off in the language of whoever asks | see time off | F20 | `staff.time_off.today` |
| My time off, with its reason and its notes | see time off | F08 | `staff.time_off.mine` |
| The settings | see | F22 | `staff.settings.get` |
| The active accounts with access to the business, for "Hub user" (id and name, with search or by user: the account of a record that no longer has access does not show and the screen says "No access to this business") | add or edit | F03 | `staff.account.list` |

### What it offers: actions (they change data)
<!-- from WORKBOOK.md sha256:d63e8740eb72 -->

| What it does | Who can | Flows | Service |
|---|---|---|---|
| Adds a record | add | F01, F03 | `staff.member.create` |
| Adds up to 100 records at once | add | F07 | `staff.member.bulk_create` |
| Changes a record (only what was sent) | edit | F02, F03 | `staff.member.update` |
| Deactivates a record | deactivate and terminate | F05 | `staff.member.deactivate` |
| Terminates a record, with date and reason | deactivate and terminate | F06 | `staff.member.terminate` |
| Creates a role | settings | F04 | `staff.role.create` |
| Changes or retires a role | settings | F04 | `staff.role.update` |
| Creates a schedule with its week | settings | F13 | `staff.schedule.create` |
| Changes a schedule and replaces its week | settings | F14 | `staff.schedule.update` |
| Activates or deactivates a schedule | settings | F15 | `staff.schedule.set_active` |
| Deletes a schedule | settings | F15 | `staff.schedule.delete` |
| Registers anyone's time off | manage time off | F17 | `staff.time_off.create` |
| Asks for one's own time off | ask for time off | F24 | `staff.time_off.request` |
| Approves time off | manage time off | F18 | `staff.time_off.approve` |
| Rejects time off | manage time off | F18 | `staff.time_off.reject` |
| Cancels time off (one's own pending one, or any with manage time off) | ask for time off | F19 | `staff.time_off.cancel` |
| Saves the settings (only what was sent) | settings | F22 | `staff.settings.update` |

### What it announces
<!-- from WORKBOOK.md sha256:805577874c98 -->

| Notice | When | What it carries | Service |
|---|---|---|---|
| New record | Adding (one per record in the batch add) | Which one (`id`) | `staff.member.created` |
| Record changed | An edit with some change | Which one (`id`) | `staff.member.updated` |
| Record deactivated | Deactivating | Which one (`id`) | `staff.member.deactivated` |
| Record terminated | Terminating | Which one (`id`), without the reason | `staff.member.terminated` |
| New role | Creating a role | Which one (`id`) | `staff.role.created` |
| Role changed | Editing or retiring a role with some change | Which one (`id`) | `staff.role.updated` |
| New schedule | Creating a schedule | The schedule (`id`) and the person (`member_id`) | `staff.schedule.created` |
| Schedule changed | Editing it, or activating or deactivating it with a change | The schedule and the person | `staff.schedule.updated` |
| Schedule deleted | Deleting it | The schedule and the person | `staff.schedule.deleted` |
| New time off | Registering it or asking for it | The time off (`id`) and the person (`member_id`), without the reason | `staff.time_off.created` |
| Time off approved | Approving | The time off and the person | `staff.time_off.approved` |
| Time off rejected | Rejecting | The time off and the person | `staff.time_off.rejected` |
| Time off cancelled | Cancelling | The time off and the person | `staff.time_off.cancelled` |
| Settings changed | Saving with some change (or the first save) | Nothing | `staff.settings.updated` |

### What it reacts to and what it needs from other apps
<!-- from WORKBOOK.md sha256:c8931d92aa73 -->
It reacts to no notice and requires no app. For **Commissions** it asks **Sales**, if the business has it,
for what each professional sold in the period, with refunds already taken off (`sale.sale.by_staff`, read as
the platform: which rows each person sees is Staff's to say), and it updates with its notices of a sale charged,
voided or refunded (`sale.sale.completed`, `sale.sale.voided`, `sale.sale.refunded`). Without Sales,
Commissions says so and lists nobody. From the platform it uses the business's accounts (to link a record)
and the business's time zone (for "today").

Who uses it: Appointments, Services, Time clock, Tasks and Online booking need it (turning one on turns
Staff on, and Staff cannot be turned off while one of them is still on). Appointments, Services, Time clock
and Tasks react to a person's termination (`staff.member.terminated`, STAFF-F06); the four update with the
changes to the records, and Appointments also with those to schedules and time off. The Sales till reads
the directory for "Who is serving this check" without needing Staff, and Automations offers the template
"The checklist of someone new in the team" on the adding of a record (`staff.member.created`).

### Who can do what
<!-- from WORKBOOK.md sha256:b1fa6877083d -->

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| See the team, roles, schedules, availability, figures, settings and one's own row of Commissions | yes | yes | yes | yes | `staff.view` |
| See the team's email and phone (a data permission of the platform) | yes | yes | yes | no | `base.view_team_contact` |
| See rate, commission and HR notes, and in Commissions the rows of the whole team (with the business's totals) | yes | yes | yes | no | `staff.view_compensation` |
| Add records | yes | yes | yes | no | `staff.add_member` |
| Edit records | yes | yes | yes | no | `staff.change_member` |
| Deactivate and terminate | yes | yes | no | no | `staff.delete_member` |
| See time off (without reason) | yes | yes | yes | yes | `staff.view_time_off` |
| See the reason and the notes of any time off | yes | yes | yes | no | `staff.view_time_off_detail` |
| Register anyone's time off, approve, reject and cancel it | yes | yes | yes | no | `staff.manage_time_off` |
| Roles, schedules and settings | yes | yes | yes | no | `staff.manage_settings` |
| Ask for one's own time off and withdraw one's own pending requests | yes | yes | yes | yes | `staff.request_time_off` |
