<!-- generated from WORKBOOK.md sha256:c77d7e53dbe95cdea21e86f09fbe2a01e5fa68c230869dba2ba11f0e0d6446ab -->

## What it is for and who it is for

Tasks is the **team's to-do list**: "clean the storeroom", "order blonde dye", "check the cold room".
Each task has a title, a priority, a due date and a team member who takes care of it; they are grouped
in **projects** ("Opening the shop", "Summer refurbishment"), split into **subtasks** and carry a thread
of **comments**.

It is for the staff, not for the customers: a customer's complaint is not a task.

Who uses it:

- The **owner**, the **administrator** and the **manager** see and change **every** task, assign them,
  delete them and run the projects.
- The **employee** sees and changes **their own**: the ones assigned to them and the ones they created.
  They can create tasks (also for a colleague), start them, complete them, comment on them and add
  subtasks to them.
- **Automations** creates tasks when the business allows it: for example, the automations that come
  with **Appointments** (a customer cancels and a task is left to fill the gap) and **Online booking**
  (a booking comes in and a task is left to check it).

The assistant uses it by voice or by text with the session of whoever is speaking: "create a task clean
the storeroom for tomorrow and assign it to Ana", "what tasks do I have?", "complete the task clean
storeroom", "what is left of the opening project?".

## Reference adopted

**Who a task is assigned to and what the employee sees** (skill `market-decision`, 2026-10-14). In the
current product the person in charge was a text reference to a user of the hub, with no link to Staff,
and everyone saw and changed everything.

| Product | How it solves it | Source |
|---|---|---|
| Homebase | The manager assigns tasks to people, roles or the team, with a due date; each employee sees theirs in the app | https://www.joinhomebase.com/industry/restaurant-task-management-app |
| 7shifts (7tasks) | A task goes to **one** employee; if they leave the shift, the task is unassigned and goes back to the team; only the manager creates and edits lists | https://kb.7shifts.com/hc/en-us/articles/32167431828243 |
| Deputy | "Task for someone else": title, team member, optional due date; task groups are created only by the manager | https://help.deputy.com/hc/en-au/articles/4689381399823 |
| Connecteam | Tasks to one or several employees; the manager handles their team's and is notified when they are seen and completed | https://connecteam.com/task-management-app/ |
| Todoist | A single assignee per task, chosen among the project's members | https://todoist.com/help/articles/how-to-collaborate-with-others |
| Jira | The assignee is a user; it can be limited so that each one sees only what is assigned to them or what they reported | https://support.atlassian.com/jira/kb/limit-users-to-only-browse-issues-assigned-to-reported-by-them-in-jira-cloud/ |
| Odoo Project | By default a user sees every task of the project; limiting it to "mine" is asked for in the forum and solved by third-party modules | https://odoo.com/es/forum/ayuda-1/show-task-to-assigned-user-only-in-odoo-v15-199206 · https://apps.odoo.com/apps/modules/17.0/project_task_own_access |
| Business Central | A project's work is assigned to resources (people) in the planning lines | https://docs.staedean.com/business-central/docs/bc-create-resource-tasks |
| Square (forum) | A list "for everyone" is done by nobody: each task needs someone in charge | https://community.squareup.com/t5/Food-and-Beverage/What-is-everyone-using-for-managing-team-tasks/m-p/636031 |
| Asana (forum) | Deleting a parent task deletes its subtasks | https://forum.asana.com/t/automatically-deleting-subtasks-when-a-parent-task-is-deleted/627538 |

**Wins:** a task has **one** assignee, who is **a team member** (their Staff record), as in Homebase,
7shifts, Deputy, Todoist and Business Central; whoever leaves the team leaves their open tasks
unassigned (7shifts). The **employee sees and changes their own** (assigned to them or created by
them) and the **manager, all of them**, which is what the floor and salon team apps do (Homebase,
7shifts, Deputy, Connecteam) and what Odoo and Jira end up configuring by hand.
**Why not the others:** the account's user does not work, because a professional without an account (the
normal case in a salon) could not have tasks; "everyone sees everything" leaves no one as the owner of the
task (Square forum); several assignees per task complicates the list without any product of this size
asking for it.

## Before you start

1. Tasks needs **Staff**: tasks are assigned to team records. Add the people in **Staff** and, if they
   are going to sign in to the Hub, link their record to their account: that way each one sees "My
   tasks".
2. If you want to group them, create the **projects** in **Tasks → Projects** (TASK-F12).
3. "Today" (overdue, due today, the number of the day) is the business's day: in phase 1, the Hub's
   time zone, **Europe/Madrid**.

## Screens

Tasks opens from the **Tasks** menu and has two tabs: **Tasks** and **Projects**. What a person cannot
do does not show, and the app refuses it even if they try through the API or the assistant.

### Tasks
At the top, the **All / My tasks** selector ("My tasks" only shows to whoever has a linked record).

**All**: table with the search box "Search no. or title…" (number, title, description, assignee or
project), columns **No., Title, Status, Priority, Due** and **Assignee**; **Project** exists
but is hidden. It sorts by any column (by default, the newest first) and filters
by No., Title, Status, Priority (both choosing from their list), Due (a day), Assignee and
Project: the filters wait behind the funnel of the bar, which turns coloured with the number of
filters set; 50 per page. The employee only sees their own.

- The **priority** shows as a coloured tag with its name: Low (grey), Medium (blue), High
  (amber), Urgent (red).
- **Due** shows in the language's format (`01/09/2026`): in red and with the text "Overdue" if it has
  already passed, in amber with "Due today" if it is today; a done or cancelled task never shows as overdue. Without
  a date, a dash.
- Row actions: **Detail**, **Start** (only if it is to do or blocked) and **Complete**
  (only if it is still open). Start and complete confirm with a brief notice. Tapping the row opens the
  task.
- **+** opens **New task**: **Title** (required), **Description**, **Priority** (Medium by
  default), **Due**, **Assigned to**, **Project** and **Tags**.

**My tasks**: the **open** tasks assigned to me, first the ones with a date (the nearest one
at the top) and then the ones without, the newest first. Starting, assigning or commenting does not move the
card. The one I complete from its card stays in its place, as done and without actions, until I
change tab.

### Task (sheet)
It opens over the list with: **TSK-YYYYMMDD-NNNN — Title**, its status and its priority; the description;
**Due**, **Completed**, **Assigned to** ("Unassigned"), **Project**, **Created** and **Created by**.

- **Status**: selector with To Do, In Progress, Blocked, Done and Cancelled; **Complete**.
- **Assign to**: the search box of active team members, by name, and **Assign**; **Assign to me**
  (if I have a record and it is not mine) and **Unassign** (if it has an assignee).
- **Edit** opens the task's form; **Delete** asks for confirmation (only whoever can delete).
- **Subtasks ({n})**, each with its number, title, status and **Open**, which goes into it with **Back**
  and the path of numbers at the top; below, "New subtask…" and **Add subtask**.
- **Comments ({n})**, the newest at the top, each with its author and its date; below, "Add
  comment…" and **Comment**. The box empties as soon as the comment is accepted; if it is refused, the
  text stays next to the reason.

### Projects
Table with the search box "Search code or name…", columns **Code, Name, Color** and **Active** (Yes /
No, list filter; Code, Name and Color filter by "contains"; the filters, behind the funnel of the
bar); sort by any column, 50 per page. A project's task counters count only the ones whoever is looking can see. **+** opens **New project**:
**Code** (required, unique: "q3-audit"), **Name** (required) and **Color** (optional,
#RRGGBB). Row action **Open**; tapping the row does the same. Creating, editing and deleting is for the
manager; the employee sees the list.

### Project (sheet)
**Name** with its colour, **Active / Inactive** and the **Code**; **Name** and **Color** editable with
**Save** (the code does not change: it is the project's key); **Deactivate / Activate** (does not send what was
typed without saving); **Delete** with confirmation; **Tasks in this project ({n})**, the 50 most
recent with "Showing {x} of {n}. Find the rest in Tasks."; "New task…" and **Add task**, which
creates it inside the project.

## States of each screen

| State | What the person sees |
|---|---|
| Loading | "Loading…" while the first result arrives. |
| Empty | "No tasks.", "No open tasks assigned to you.", "No subtasks.", "No comments.", "No projects." or "No tasks in this project yet."; with a search or a filter, "No results". |
| Error | The table's notice with "Retry". A form's refusal shows inside the form, without losing what was typed; a row action's, above the table; the sheet's, inside the sheet. |
| Reconnecting | What is painted stays; a strip warns "Reconnecting…". |
| App inactive | "This app is not active in this business". |
| No permission | What they cannot do does not show; if they arrive through another door, "You do not have permission". |

## Flows

| ID | Flow | Status |
|---|---|---|
| TASK-F01 | Create a task | done |
| TASK-F02 | See and search the tasks | done |
| TASK-F03 | See my tasks | done |
| TASK-F04 | Open a task | done |
| TASK-F05 | Start or change the status | done |
| TASK-F06 | Complete a task | done |
| TASK-F07 | Assign, reassign or unassign | done |
| TASK-F08 | Edit a task | done |
| TASK-F09 | Add a subtask | done |
| TASK-F10 | Comment on a task | done |
| TASK-F11 | Delete a task | done |
| TASK-F12 | Create a project | done |
| TASK-F13 | Open and change a project | done |
| TASK-F14 | Delete a project | done |
| TASK-F15 | When someone leaves the team | done |

### TASK-F01 Create a task
Status: done (server and screen)
Actor: owner, administrator, manager, employee, assistant, an automation with permission
Screen: Tasks
Steps:
1. In **Tasks**, tap **+**: **New task** opens.
2. Type the **Title** (required, up to 255 characters). If you want: Description (up to 5000),
   Priority (Low, Medium, High, Urgent; Medium by default), Due (a day), Assigned to (an
   active team member), Project (the selector offers the active ones) and Tags (up to 20, of
   up to 50 characters, separated by commas).
3. Tap **Create task**: the task shows in the list as **To Do**, without a completion date and with its number
   `TSK-AAAAMMDD-NNNN` (the business's day and a counter of the day that leaves no gaps).
In: the form. The assistant names the project by its code or its name, the parent task by its
number or its title and the assignee by their name. A date with a time is taken as its day in the business's
time zone. Creator: whoever creates it, always from the session.
Out: the task; Tasks announces there is a new one (`task.task.created`).
If it fails: under each field and without creating anything or spending a number: empty title, a priority that does not
exist, a date that is not one, "That project does not exist in this business.", "That task does not exist in
this business." (the parent), "That staff member does not exist in this business.", "That person is not
active in the team." or, by name, several people or projects that match (it says which).
Involved: Staff (the assignee's record)

### TASK-F02 See and search the tasks
Status: done (server and screen)
Actor: everyone; the employee sees only their own
Screen: Tasks → All
Steps:
1. Open **Tasks**: the table shows with the newest first.
2. Search, sort by any column or tap the funnel, choose the filters and tap **Apply**.
In: search and filters: number, title, status, priority, open or closed, overdue, project (id,
code or name), assignee (id or name), unassigned, parent task, only the top-level ones,
tag, and ranges of due date, of completion and of creation. Up to 100 per page.
Out: the tasks with their project, their parent, their assignee, their creator, how many subtasks and
comments they have and whether whoever is looking can change them.
If it fails: a filter that does not exist, "422".
Involved: Staff (the assignee's name)

### TASK-F03 See my tasks
Status: done (server and screen)
Actor: whoever has a record linked to their account, assistant
Screen: Tasks → My tasks
Steps:
1. Tap **My tasks**.
2. My **open** tasks show (to do, in progress and blocked): with a date first, the nearest
   at the top; then without a date, the newest first.
3. The one I complete from its card stays in its place as done until I change tab.
In: optionally, "the ones due in the next N days" (only the ones with a date).
Out: the tasks, as in TASK-F02. Without a linked record, the list is empty.
If it fails: nothing of its own.
Involved: Staff (my record)

### TASK-F04 Open a task
Status: done (server and screen)
Actor: whoever sees it
Screen: Task (sheet)
Steps:
1. Tap the row (or **Detail**): the sheet opens with the header, the description and the details.
2. Below, its subtasks and its comments. **Open** on a subtask goes into it; **Back** leaves.
In: the task, by id or, from the assistant, by its number or its title.
Out: the task, its subtasks and its comments; everything is followed live.
If it fails: "That task does not exist in this business." (also if it belongs to another person and the employee does not
see it); several tasks that match the title: it says which.
Involved: none

### TASK-F05 Start or change the status
Status: done (server and screen)
Actor: whoever can change it (the employee, their own)
Screen: Tasks (action **Start**), Task (selector **Status**)
Steps:
1. **Start** puts it **In Progress**; the selector takes it to any of the five statuses.
2. Moving to **Done** stamps the completion date; leaving **Done** clears it; the other changes do not
   touch it.
In: the task and the new status.
Out: the task (`task.task.status_changed`; on reaching Done, also `task.task.completed`).
Choosing the status it already has changes nothing and announces nothing.
If it fails: "That task does not exist in this business." (also another person's, which the employee does not see);
whoever sees every task but can only change their own, "You can only change your own tasks.".
Involved: none

### TASK-F06 Complete a task
Status: done (server and screen)
Actor: whoever can change it
Screen: Tasks (action **Complete**), Task (button **Complete**)
Steps:
1. On the task's row, or on its sheet, tap **Complete**.
2. The task moves to **Done** with the date of now: the list says so at once and it no longer shows as
   overdue.
In: the task.
Out: the task (`task.task.status_changed` and `task.task.completed`).
If it fails: if it was already done or cancelled, "That task is already closed, so it was left as it
was." (409 `task.task_already_closed`): a cancelled one is not "finished" by mistake; to reopen it,
the status is changed.
Involved: none

### TASK-F07 Assign, reassign or unassign
Status: done (server and screen)
Actor: whoever can change it
Screen: Task
Steps:
1. Open the task, search for the person by their name in **Assign to** and tap **Assign**; or tap
   **Assign to me**.
2. To leave it without an assignee, tap **Unassign**: the sheet says "Unassigned".
In: the task and the person (id, name or "me"); without a person, it is unassigned. Only active
people or people on temporary leave; never a record that has been terminated or is inactive.
Out: the task (`task.task.assigned`, with the new assignee or empty). Assigning to whoever already has it
changes nothing and announces nothing.
If it fails: "That staff member does not exist in this business.", "That person is not active in the
team.", "You have no staff record: you cannot be assigned tasks." (assign to me without a record).
Involved: Staff

### TASK-F08 Edit a task
Status: done (server and screen)
Actor: whoever can change it
Screen: Task → **Edit**
Steps:
1. Open the task and tap **Edit**: "Editing task — TSK-…" opens with its details.
2. Change the title, the description, the priority, the due date, the project or the tags and
   tap **Save**: only what changed is sent.
In: what is sent; empty in Due or Project removes them.
Out: the task (`task.task.updated`). Saving without changes announces nothing.
If it fails: the same refusals as when creating.
Involved: none

### TASK-F09 Add a subtask
Status: done (server and screen)
Actor: whoever can create tasks and sees the parent
Screen: Task
Steps:
1. Open the task, type the title in "New subtask…" and tap **Add subtask**: it shows in the
   list at once, with its number, in the parent's project.
2. **Open** on the subtask goes into it, with the path of numbers at the top; **Back** goes out to the parent.
In: the title and the parent.
Out: the subtask (`task.task.created`).
If it fails: the reason inside the sheet; the typed title stays.
Involved: none

### TASK-F10 Comment on a task
Status: done (server and screen)
Actor: whoever can change it
Screen: Task
Steps:
1. Open the task and type in "Add comment…".
2. Tap **Comment**: the comment goes in at the top of the thread with my name and the time; the box empties
   (what I typed while it was being sent stays).
In: the task and the text (required, up to 5000). The author always comes from the session.
Out: the comment (`task.comment.added`). The thread is a record: it is neither edited nor deleted.
If it fails: empty text; "That task does not exist in this business.".
Involved: none

### TASK-F11 Delete a task
Status: done (server and screen)
Actor: owner, administrator, manager, assistant (with reinforced confirmation)
Screen: Task → **Delete**
Steps:
1. Open the task and tap **Delete**: confirmation is asked for.
2. Tap **Delete** in the notice: the task disappears **with its subtasks and its comments**.
In: the task.
Out: `task.task.deleted`.
If it fails: "That task does not exist in this business.".
Involved: none

### TASK-F12 Create a project
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Projects
Steps:
1. Tap **+**, type **Code** (up to 40, unique without telling capitals apart) and **Name** (up to
   200); if you want, **Color** (#RRGGBB). Through the API or the assistant, also an owner (a team
   member).
2. Tap **Create project**: the project shows as **Active**.
In: the code, the name and, if you want, the colour; through the API or the assistant, also the owner.
Out: the project (`task.project.created`).
If it fails: "There is already a project with that code." under the field; a colour that is not #RRGGBB.
Involved: Staff (the owner)

### TASK-F13 Open and change a project
Status: done (server and screen)
Actor: everyone opens it; the owner, the administrator and the manager change it
Screen: Project (sheet)
Steps:
1. Tap the row (or **Open**): the sheet shows with its name, its status, its code and its tasks.
2. Change name or colour and **Save**; **Deactivate** takes it out of use (it is no longer offered when creating
   tasks, its tasks stay); **Activate** brings it back.
3. **Add task** creates a task inside the project.
In: the project, by id or, from the assistant, by its code or its name.
Out: the project (`task.project.updated`). Saving without changes announces nothing.
If it fails: "That project does not exist in this business." inside the sheet, which stays open; an empty
name is not sent.
Involved: none

### TASK-F14 Delete a project
Status: done (server and screen)
Actor: owner, administrator, manager, assistant (with reinforced confirmation)
Screen: Project → **Delete**
Steps:
1. Open the project and tap **Delete**: confirmation is asked for.
2. Tap **Delete** in the notice: the project disappears; **its tasks stay**, without a project.
In: the project.
Out: `task.project.deleted`.
If it fails: "That project does not exist in this business.".
Involved: none

### TASK-F15 When someone leaves the team
Status: done
Actor: system
Screen: none
Steps:
1. A manager terminates in **Staff** a person who has open tasks (STAFF-F06).
2. In a few seconds, their **open** tasks (to do, in progress or blocked) are left **unassigned**;
   the done and the cancelled ones keep their name.
3. In **Tasks** they show as "Unassigned", and the manager hands them out (TASK-F07).
In: the person's termination in Staff.
Out: one `task.task.assigned` (empty assignee) per task.
If it fails: if the person had no open tasks, nothing is done; a second delivery of the same notice
does not change anything either.
Involved: Staff (STAFF-F06), TASK-F07

## Services: what goes in and what comes out

Everything can be asked for through the screens, the assistant (by voice or by text, with the session of whoever
speaks) and the API, with the same rules and the same permissions. A task is named by its id, its number
or its title; a project by its id, its code or its name; a person by their id or their name. If a
name fits several, it says which and asks to choose (`task.ambiguous_task`,
`task.ambiguous_project`, `staff.ambiguous_member`).

### What it offers: queries (they read and change nothing; all of them can be followed live)

| What it gives | Who can | Flows | Service |
|---|---|---|---|
| The tasks, with search, filters and sorting, in pages of up to 100 (the employee, their own) | view | F02 | `task.task.list` |
| My open tasks, by due date | view | F03 | `task.task.mine` |
| A task | view | F04 | `task.task.detail` |
| A task's subtasks, in the order they were added | view | F04, F09 | `task.task.subtasks` |
| A task's comments, the newest first | view | F04, F10 | `task.comment.list` |
| The projects, with search, filters, sorting and how many tasks they have | view | F12, F13 | `task.project.list` |
| A project | view | F13 | `task.project.detail` |

### What it offers: actions (they change data)

| What it does | Who can | Flows | Service |
|---|---|---|---|
| Creates a task or a subtask | create | F01, F09, F13 | `task.task.create` |
| Changes a task (only what is sent) | change | F08 | `task.task.update` |
| Changes the status | change | F05 | `task.task.set_status` |
| Completes an open task | change | F06 | `task.task.complete` |
| Assigns, reassigns or unassigns | change | F07 | `task.task.assign` |
| Deletes a task with its subtasks and comments | delete | F11 | `task.task.delete` |
| Comments on a task | change | F10 | `task.comment.add` |
| Creates a project | projects | F12 | `task.project.create` |
| Changes a project (name, colour, active, owner) | projects | F13 | `task.project.update` |
| Deletes a project (its tasks stay) | projects | F14 | `task.project.delete` |
| Unassigns the open tasks of whoever leaves the team | the platform only | F15 | `task.task.release_member` |

### What it announces

| Notice | When | What it carries | Service |
|---|---|---|---|
| New task | Creating a task or a subtask | `id`, `number`, `project_id`, `parent_id`, `assigned_to_id` | `task.task.created` |
| Task changed | Editing with some change | `id` | `task.task.updated` |
| Status changed | Changing the status or completing | `id`, `from`, `to` | `task.task.status_changed` |
| Task completed | Reaching Done by any path | `id` | `task.task.completed` |
| Assignee changed | Assigning, reassigning, unassigning or the person's termination | `id`, `assigned_to_id` (or empty) | `task.task.assigned` |
| Task deleted | Deleting | `id`, `number` | `task.task.deleted` |
| New comment | Commenting | `id`, `task_id` | `task.comment.added` |
| New project | Creating a project | `id`, `code` | `task.project.created` |
| Project changed | Saving, activating or deactivating with some change | `id` | `task.project.updated` |
| Project deleted | Deleting a project | `id`, `code` | `task.project.deleted` |

The notices carry no titles, descriptions or comments (free text that can name a
customer or a colleague).

### What it reacts to and what it needs from other apps
- **Staff** (`requires = ["staff"]`): the assignee and a project's owner are Staff
  records; Tasks reads their names and, when someone is terminated (`staff.member.terminated`), unassigns
  their open tasks (TASK-F15: the notice is handed to it by the worker's outbox relay, once per
  termination). The screens search for people with `staff.member.list` and
  "Assign to me" reads one's own record with `staff.member.mine`.
- From the platform: the account of whoever acts (creator and author of the comments) and the business's
  time zone (the "today").
- Who else uses it: **Automations** calls `task.task.create` by its name, with the permission the
  business grants it; its factory automations from Appointments and Online booking leave a task
  (FLOW-F33). Tasks knows nothing of them.

### Who can do what

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| See one's own tasks (assigned or created) and the projects | yes | yes | yes | yes | `task.view` |
| See every task | yes | yes | yes | no | `task.view_all` |
| Create tasks and subtasks | yes | yes | yes | yes | `task.add` |
| Change, assign, complete and comment on one's own | yes | yes | yes | yes | `task.change` |
| Change, assign, complete and comment on any | yes | yes | yes | no | `task.change_all` |
| Delete tasks | yes | yes | yes | no | `task.delete` |
| Create, change and delete projects | yes | yes | yes | no | `task.manage_project` |
