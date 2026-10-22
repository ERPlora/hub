<!-- generated from WORKBOOK.md sha256:152c790d94031bd461911efc29e164a5df24df3d93dddd1660d47d1127b27997 -->

## What it is for and who it is for

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
  withdraws the requests that are still pending.

Appointments (and with it Online booking) reads from here who is bookable, their schedule and their
approved time off; Services, who can perform each service; Time clock, whose each clock-in is; Tasks, who
each task is assigned to; and the till reads the directory to name who serves (and with it, the kitchen
ticket). At the end of the day, **Commissions** gives what each professional has sold and earned.

## Reference adopted

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

Staff opens from the **Staff** menu and has four tabs: **Staff**, **Roles**, **Time Off** and
**Schedules**, plus **Commissions** (for whoever sees the pay) and **Settings** (for whoever can save
them). What a person cannot do does not show, and the app refuses it even if they try through the API or
the assistant.

### Staff
Above the table, three figures: **Active staff**, **On leave today** and **Pending time off**
(STAFF-F23). Below, the table with the search "Search member…" (first name, last name, email, phone,
employee ID or role), columns **Name, Role, Email, Status** and, only for whoever can see the pay,
**Rate/h**; **Phone** exists but starts hidden. It sorts by any column and filters by First name, Last
name, Email, Phone, Role, Status (**Active**, **On leave**, **Inactive**), Bookable, hire date, color and
user; 50 per page. Terminated records do not show.

The **+** button opens **New**; a row opens **Edit · {name}**. Form: **First name, Last name, Email,
Phone, Employee ID, Role** ("No role"), **Hub user** ("No Hub access"), **Status** (only when editing:
Active, Inactive, On leave), **Bookable**, **Buffer between appointments (min)**, **Hire date**,
**Color**, **Specialties**, **Bio** and, for whoever can see the pay, **Hourly rate** and **Commission
(%)**. Row actions for the owner and the administrator: **Deactivate** and **Terminate**, both with a
confirmation.

### Roles
Table with the search "Search role…" and columns **Role, Description, Members** (how many **Active**
people hold it). **+** opens **New** (**Role name, Description, Color**); a row opens **Edit**, where the
role is also **retired** (it stops being offered) or turned active again.

### Time Off
Above the table, **Today’s time off**: who is away today, with the type and, if it is only part of the
day, its hours (STAFF-F20). Below, the table with a search by name and columns **Member, Type, From, To,
Status**, with filters by member, type, status and dates. Row actions: **Approve**, **Reject** and
**Cancel**, where they apply. **+** opens the form: **Member** (only for whoever manages time off; the
employee asks for it for themselves), **Type** (Vacation, Sick leave, Personal, Training or Other),
**From, To, Full day** (if it is turned off, **From (time)** and **To (time)**) and **Reason**. The reason
and the notes are only seen by whoever has the permission and by the person themselves.

### Schedules
**Member** selector and the table of their schedules: **Schedule, Default, From, To, Active, Hours** (the
week summed up). Row actions: **Edit**, **Activate / deactivate** and **Delete** (with a confirmation).
**+** opens **New**: **Schedule** (name; empty, "Regular schedule"), **Effective from, Effective until,
Default** and one row per weekday with **Start, End, Break start, Break end** (or "Off"), with the default
working day of **Settings** already in place.

### Commissions
At the top, the period: "Today" (on entering), "Yesterday", "This week" (since Monday), "This month"
(since the 1st) or "Custom", which opens "From" and "To" with the days that were on screen; next to it,
the days it counts. On a phone, the period is chosen in the "Period" drop-down, with the same options.
Below, two figures: **Sold** and **Commissions** of the period. Then the list with the search "Search
professional…" and columns **Name, Role, Sold, Commission %** and **Commission**: each person who can earn
a commission (Active or On leave), also without sales and with commission 0, and whoever sold in the
period even if they are no longer here ("No longer works here" or "Inactive" next to the name). It sorts by
name, role, sold or commission. On a phone, one card per person. It updates by itself when a sale is
charged, voided or refunded and when a record changes.

### Staff settings
"Default working day", with "A new schedule proposes this working day from Monday to Friday, with the
break in the middle of the day.": "Working day starts (HH:MM)", "Working day ends (HH:MM)", "Break
duration (minutes)" and **Save**. While the business has never saved, the proposed values show.

### Home panels
The Hub's Home does not show the apps' panels yet. Meanwhile, the five panels of the current product show
inside Staff: **Active staff**, **On leave today** and **Pending time off** above the Staff table,
**Today’s time off** above the Time Off one and **Employees by role** in the "Members" column of Roles
(STAFF-F20 and STAFF-F23).

## States of each screen

| State | What the person sees |
|---|---|
| Loading | "Loading…" while the first result arrives; each figure shows "…". |
| Empty | "No staff members.", "No roles defined.", "No time-off requests." or "This member has no schedules yet."; with a search or a filter, "No results". "Today’s time off" with nobody: "Nobody is away today.". Commissions with nobody who can earn one: "No one on the team can earn a commission yet."; without Sales in the business, "Commissions come from the sales" and "Turn on Sales to see what each professional earned.", without a list. |
| Error | The table's notice with "Retry"; in Settings, "The settings could not be loaded" with "Retry" and no form. The figures say "The figures could not be loaded" and "Today’s time off", "Who is away today could not be loaded", and the table keeps working. A refusal of a form shows inside the form, without losing what was typed; that of a row action, above the table. |
| Reconnecting | What is painted stays; a strip warns "Reconnecting…". |
| App inactive | "This app is not active in this business". |
| No permission | What they cannot do does not show; if it arrives through another door, "You do not have permission". |

## Flows

| ID | Flow | Status |
|---|---|---|
| STAFF-F01 | Add a professional | done (server and screen) |
| STAFF-F02 | Edit a professional's record | done (server and screen) |
| STAFF-F03 | Link the record to an account of the business | done (server and screen) |
| STAFF-F04 | Create, edit and retire a role | done (server and screen) |
| STAFF-F05 | Deactivate a professional | done (server and screen) |
| STAFF-F06 | Terminate a professional | done (server and screen) |
| STAFF-F07 | Add several professionals at once | done (assistant and API, like the current product) |
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

The services each professional performs (STAFF-F10, F11 and F12 of the current product) are in the
Services app: see "Changes from the current product".

### STAFF-F01 Add a professional
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Staff
Steps:
1. In **Staff**, tap **+**: **New** opens (without Status: the person is born **Active**).
2. Write First name and Last name (required, up to 100 characters). If you want, Email, Phone, Employee
   ID, Role, Hub user (STAFF-F03), Hire date, Color (#RRGGBB), Specialties, Bio, Buffer between
   appointments and, with the pay permission, Hourly rate and Commission (%). **Bookable** comes on.
3. Tap Save: the person shows in the table as **Active**.
In: the form; the active roles (STAFF-F04), by id or by their name. The rate is saved in whole cents; the
commission is a percentage from 0 to 100 with two decimals. Through the API or the assistant the initial
status and the HR notes can also be given.
Out: the record; Staff announces there is a new record (`staff.member.created`).
If it fails: under each field and without saving anything: first name or last name empty, an email that
is not one, a color that is not #RRGGBB, a negative rate, a commission outside 0–100, "That role is not
available: it does not exist in this business, or it has been deleted or retired.", "That Hub user has no
access to this business." or the account already linked to another record (STAFF-F03). Whoever cannot see
the pay cannot send it: "Permission “{permission}” is required.". Two records with the same name, email or
employee ID are accepted.
Involved: none

### STAFF-F02 Edit a professional's record
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Staff
Steps:
1. Tap the row: **Edit · {name}** opens (the assistant names it by its name).
2. Change what is needed. **Status** offers Active, Inactive and On leave (the final termination is
   STAFF-F06). "No role" removes the role, "No Hub access" unlinks the account, and the Hire date can be
   **cleared**.
3. Save: only what was sent changes.
In: the record (and, with the permission, its rate, commission and notes).
Out: the changed record (`staff.member.updated`). Saving without changing anything does not announce.
Setting Inactive here does not turn Bookable off, as today; going back to Active does not turn it on
either.
If it fails: the same refusals as when adding; "That staff member does not exist in this business." if it
is no longer there (also if it was terminated); setting **Inactive** with pending or approved time off not
yet ended: "That staff member has pending or approved time off that has not ended yet. Resolve it
first.".
Involved: none

### STAFF-F03 Link the record to an account of the business
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
If it fails: "That Hub user is already linked to {name}. A Hub user can belong to only one staff member:
unlink it there first, or pick another user." (`staff.user_already_linked`), also if two people link it
at the same time; "That Hub user has no access to this business.".
Involved: ATTENDANCE-F01, TASK-F03

### STAFF-F04 Create, edit and retire a role
Status: done (server and screen)
Actor: owner, administrator, manager
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
If it fails: "A role with that name already exists." (case-insensitive, `staff.role_name_taken`); "That
role does not exist in this business.".
Involved: none

### STAFF-F05 Deactivate a professional
Status: done (server and screen)
Actor: owner, administrator
Screen: Staff
Steps:
1. In the row, tap **Deactivate** and confirm "Take {name} off the floor? They stop being bookable;
   nothing is deleted.".
2. The row turns **Inactive** and stops being bookable.
In: the record and its pending or approved time off that has not ended (with the business's "today").
Out: status Inactive and Bookable off (`staff.member.deactivated`). It does not touch schedules, time off,
account or appointments. To come back: STAFF-F02.
If it fails: "That staff member has pending or approved time off that has not ended yet. Resolve it
first." (`staff.active_time_off`; it is rejected or cancelled in STAFF-F18 and STAFF-F19); "That staff
member is already inactive."; "That staff member does not exist in this business.".
Involved: none

### STAFF-F06 Terminate a professional
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
Status: done (assistant and API, like the current product)
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
Status: done (server and screen)
Actor: employee (and any person with a linked record), assistant
Screen: Staff (own view) and Time Off
Steps:
1. A person with their account linked to their record (STAFF-F03) opens what is theirs.
2. They see their record with **their own** rate and commission (without the HR notes), and their time
   off with its reason and its notes.
In: the account they get in with (it cannot be faked).
Out: nothing changes. Without a linked record, the answer comes empty.
If it fails: without a record or without time off, empty.
Involved: none

### STAFF-F09 Give the team to other apps
Status: done (the other apps read it)
Actor: system
Screen: none
Steps:
1. An app that needs to name the team (the till in "Who is serving this check", and with it the kitchen
   ticket; Appointments, Services, Tasks) asks for the directory, with its permission to see the team.
2. It receives, per person: name, email, phone, employee ID, role, account, status, bookable, hire date and
   color; **never** the rate nor the commission. Up to 100 per page; it filters, among others, by user (to
   go from an account to its record).
In: nothing; it is a read.
Out: the directory of the records that are not terminated (also the Inactive and On leave ones).
If it fails: each app handles it its own way.
Involved: SALE-F16, APPOINTMENT-F01, SERVICE-F33, TASK-F07

### STAFF-F13 Create a professional's weekly schedule
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Schedules
Steps:
1. Choose the person and tap **+**: **New** opens with a proposed week: from Monday to Friday, the default
   working day of **Settings** (STAFF-F22), with the break in the middle of the day and its start on the
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
accepted.
Involved: none

### STAFF-F14 Edit a schedule
Status: done (server and screen)
Actor: owner, administrator, manager
Screen: Schedules
Steps:
1. Tap the schedule's row: **Edit · {name}** opens with its week.
2. Change the name, the validity, "Default" or the days; a day you untick becomes "Off". Save: **the whole
   week is replaced**; the rest you do not send stays as it was and an empty date removes that validity.
In: the schedule and its whole week.
Out: the changed schedule (`staff.schedule.updated`), with the same "Default" rule and the same rule of
which schedule rules as when creating it.
If it fails: the same refusals as when creating, or "That schedule does not exist in this business.".
Involved: none

### STAFF-F15 Activate, deactivate or delete a schedule
Status: done (server and screen)
Actor: owner, administrator, manager
Screen: Schedules
Steps:
1. **Activate / deactivate** changes at once: an inactive schedule rules no day.
2. **Delete** asks to confirm "Delete the schedule "{name}"? Its hours stop counting for availability." and
   deletes it with its hours.
In: the schedule.
Out: `staff.schedule.updated` or `staff.schedule.deleted`. Deleting the "Default" one does not make
another one "Default".
If it fails: "That schedule does not exist in this business.".
Involved: none

### STAFF-F16 Know when a professional can work
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
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Time Off
Steps:
1. In **Time Off**, tap **+**, choose the Member, the Type (Vacation comes), From and To, "Full day" (or
   its hours) and, if you want, the Reason.
2. Tap Save: the time off shows as **Pending**.
In: the person (any record that is not terminated, an Inactive one too; by id or by name) and the time
off, with optional reason and notes. With hours, the same ones apply each day of the range.
Out: the Pending time off (`staff.time_off.created`; the notice does not carry the reason). It does not
change the agenda yet: it only counts when it is approved (STAFF-F18). It does not notify the person.
If it fails: under each field: "The end date cannot be before the start date.", "A half-day absence needs
a start and an end time.", "The start time must be before the end time."; "That staff member already has
pending or approved time off in those dates." (`staff.overlapping_time_off`): they overlap if they share
any day and, when both are by hours, also any hour (a morning one and an afternoon one on the same day do
**not** clash); rejected and cancelled ones do not count. "That staff member does not exist in this
business.".
Involved: none

### STAFF-F18 Approve or reject time off
Status: done (server and screen)
Actor: owner, administrator, manager
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
time-off request cannot change to that status from its current one." (`staff.invalid_transition`); "That
time-off request does not exist in this business.".
Involved: none

### STAFF-F19 Cancel time off
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
Status: done (server and screen)
Actor: everyone
Screen: Time Off and Staff
Steps:
1. Open **Time Off**: above the table, "Today’s time off" lists whoever has **approved** time off that
   covers today (in the business's day), full days first and then by name, with the type and, if it is only
   part of the day, its hours, and says how many they are.
2. In **Staff**, the "On leave today" figure counts the different people who are away today.
3. For the detail, the **Time Off** table with its filters.
In: the approved time off and the records.
Out: read only; without the reason. It changes by itself when time off is approved or cancelled.
If it fails: without time off, "Nobody is away today."; if it cannot be read, "Who is away today could not
be loaded" in its place, and the table keeps working.
Involved: none

### STAFF-F21 Give each professional's rate and commission
Status: done (server and screen)
Actor: owner, administrator, manager
Screen: Staff (Rate/h column and form) and Commissions
Steps:
1. Whoever can see the pay sees the rate, the commission and the HR notes of each record.
2. The **commission sheet** gives, for each person who can earn a commission (Active or On leave; not the
   Inactive nor the terminated ones), their record, their account (empty if they have none), name, role
   and commission, also those with commission 0.
3. To know what each professional has earned, open **Staff → Commissions**. "Today" shows: what each person
   has sold in the business's day, with what was refunded already taken off, their commission and what is
   due to them (sold × commission ÷ 100, rounded to the cent only once per person; half a cent rounds up).
   At the top, the total sold and the total of commissions.
4. For another period, choose "Yesterday", "This week", "This month" or "Custom" and set "From" and "To".
5. It counts what was attributed to each person in Sales: the line they did or, if the line does not say
   who, the account they served (in a sale of an appointment, the appointment's professional). What is
   charged without choosing anyone from the team counts for nobody.
In: each record's rate and commission and, from Sales, what each professional sold in the period (refunds
already taken off: what comes back goes to whoever sold it). Sales is optional.
Out: read only.
If it fails: without the pay permission, "You do not have permission"; without Sales, "Commissions come
from the sales"; with "To" before "From", "The end date cannot be before the start date." under "To";
with only one day, "A period of your own needs its first and its last day."; with more than two years,
"Ask for at most 731 days at a time.".
Involved: SALE-F16, SALE-F28

### STAFF-F22 Change the Staff settings
Status: done (server and screen)
Actor: owner, administrator, manager
Screen: Staff settings
Steps:
1. Open **Settings**: the saved default working day shows or, if it was never saved, the proposed one (from
   09:00 to 18:00 with a 60-minute break).
2. Change the start and the end in HH:MM (the end, after the start: a schedule's day does not cross
   midnight) and the break, from 0 (no break) to 480 minutes and shorter than the working day.
3. Tap **Save**.
In: what was sent; the rest stays as it was.
Out: the business's settings (`staff.settings.updated`), with the hours always in HH:MM. From that moment,
a new schedule proposes that working day from Monday to Friday, with the break in the middle of the day
(STAFF-F13).
If it fails: a value outside its range shows under its field and nothing is saved. A working day that ends
before it starts says "The start time must be before the end time." under "Working day ends (HH:MM)"
(under "Working day starts (HH:MM)" if only the start was changed), and a break that does not fit in the
working day, "The break must fall inside the working hours." under the break; nothing is saved. If the
settings cannot be read, "The settings could not be loaded" with "Retry", without a form: values that are
not the business's are never offered to be saved.
Involved: none

### STAFF-F23 See the figures of the staff and by role
Status: done (server and screen)
Actor: everyone
Screen: Staff and Roles
Steps:
1. Open **Staff**: above the table three figures show: "Active staff" (how many people are **Active**), "On
   leave today" (different people with approved time off that covers today) and "Pending time off" (how
   many requests are waiting for an answer). On a phone they go on a single line, so that the table can
   still be seen below.
2. The figures change by themselves, without reloading, when someone adds, deactivates or terminates a
   record or asks for, approves, rejects or cancels time off.
3. "Members" of **Roles** gives how many **Active** people each role has (the "Employees by role" panel of
   the current product).
In: the records, the roles and the time off. Through the assistant or the API, the figures also give how
many records there are and how many are **On leave** and **Inactive**.
Out: read only. The terminated records and their time off do not count.
If it fails: without data, zeros; if they cannot be read, "The figures could not be loaded" in their place,
and the table keeps working. While they arrive, each figure shows "…".
Involved: none

### STAFF-F24 Ask for my own time off
Status: done (server and screen)
Actor: employee (and any person with a linked record), assistant
Screen: Time Off
Steps:
1. In **Time Off**, tap **+**: the form does not ask for the Member, the time off is yours.
2. Choose the Type, the dates, "Full day" (or its hours) and, if you want, the Reason, and save.
3. It shows as **Pending** until a manager approves or rejects it (STAFF-F18); while it is pending you can
   withdraw it (STAFF-F19).
In: your record, through your linked account (STAFF-F03).
Out: the Pending time off, with the same notice as STAFF-F17 (`staff.time_off.created`).
If it fails: the same refusals as STAFF-F17; without a linked record: "Your user is not linked to any staff
member: ask a manager to link it." (`staff.no_member_record`).
Involved: none

## Services: what goes in and what comes out

Everything can be asked for through the screens, the assistant (by voice or by text, with the session of
whoever speaks) and the API, with the same rules and the same permissions. A person is named by their id or
by their name; if the name fits several, it says which ones and asks to choose
(`staff.ambiguous_member`).

### What it offers: queries (they read and change nothing; all but the accounts can be followed live)

| What it gives | Who can | Flows | Service |
|---|---|---|---|
| The directory, with search, filters and sorting by any column, in pages (up to 100) | see | F09 | `staff.member.list` |
| A person's record (without pay) | see | F02 | `staff.member.detail` |
| My record, with my rate and my commission | see | F08 | `staff.member.mine` |
| Rate, commission and HR notes, with the directory's filters, sorting and pages (the Rate/h column reads the same rows) | see the pay | F21 | `staff.member.compensation` |
| The commission sheet: who can earn a commission, with their record, their account and their commission | see the pay | F21 | `staff.commission.summary` |
| What each professional earned in a period (today, yesterday, this week, this month or two days): sold with refunds taken off, commission and totals; it says if the business has no Sales | see the pay (and the Sales figures) | F21 | `staff.commission.report` |
| The figures: records, active, on leave, inactive, away today and pending requests | see | F23 | `staff.member.stats` |
| The roles with their active members, with filters and sorting | see | F04, F23 | `staff.role.list` |
| A person's schedules with their week | see | F13–F15 | `staff.schedule.list` |
| A schedule with its week | see | F14 | `staff.schedule.detail` |
| A person's availability by days | see | F16 | `staff.availability.for_member` |
| The time off, without reason, with filters and sorting | see time off | F17–F19 | `staff.time_off.list` |
| One time off with its reason, its notes and who approved it | see the time-off detail | F18 | `staff.time_off.detail` |
| Who is away today | see time off | F20 | `staff.time_off.today` |
| My time off, with its reason and its notes | see time off | F08 | `staff.time_off.mine` |
| The settings | see | F22 | `staff.settings.get` |
| The active accounts with access to the business, for "Hub user" (id and name, with search or by user: the account of a record that no longer has access does not show and the screen says "No access to this business") | add or edit | F03 | `staff.account.list` |

### What it offers: actions (they change data)

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
It reacts to no notice and requires no app. For **Commissions** it asks **Sales**, if the business has it,
for what each professional sold in the period, with refunds already taken off (`sale.sale.by_staff`, with
the Sales figures permission of whoever is looking), and it updates with its notices of a sale charged,
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

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| See the team, roles, schedules, availability, figures and settings | yes | yes | yes | yes | `staff.view` |
| See rate, commission and HR notes | yes | yes | yes | no | `staff.view_compensation` |
| Add records | yes | yes | yes | no | `staff.add_member` |
| Edit records | yes | yes | yes | no | `staff.change_member` |
| Deactivate and terminate | yes | yes | no | no | `staff.delete_member` |
| See time off (without reason) | yes | yes | yes | yes | `staff.view_time_off` |
| See the reason and the notes of any time off | yes | yes | yes | no | `staff.view_time_off_detail` |
| Register anyone's time off, approve, reject and cancel it | yes | yes | yes | no | `staff.manage_time_off` |
| Roles, schedules and settings | yes | yes | yes | no | `staff.manage_settings` |
| Ask for one's own time off and withdraw one's own pending requests | yes | yes | yes | yes | `staff.request_time_off` |

The cashier of the current product no longer exists as a role: what they saw (the directory) the employee
sees.
