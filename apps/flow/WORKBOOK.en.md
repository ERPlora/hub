<!-- generated from WORKBOOK.md sha256:f37b4d83d4e37610d20e3b9b1c8fdcdfeef92521f331a26e3cd0ac38b045eecc -->

## What it is for and who it is for

Automations is where the business writes down rules that carry themselves out: "when a big sale is
charged, add a note to the customer's card", "every morning at 9, leave me the task of going over the
diary", "when someone does not turn up to their appointment, leave me the task of calling them". From here
you pick a ready-made automation from the gallery or build one from scratch, grant it the permissions it
needs, try it without effects, turn it on, run it by hand if needed and read what it did.

An automation is **one column**: at the top, **when it starts** (something that happens in the business, a
schedule, a date or only by hand); below, its **steps**, done in order: **Do something** (an action of
another app, for example creating a task), **Look something up** (reading a piece of data from another
app), **Only continue if…** (a condition: if it is not met, the automation ends there without an error) and
**Wait** (minutes, hours or days). They start on their own when what they wait for happens in the business,
at their time or on their date (FLOW-F21, F22), and also with **Run now**.

Only the **owner** and the **administrator** use it: an automation acts on behalf of the business with
nobody in front of it. The manager and the employee do not see it.

With the Hub's assistant it is used by voice or by text, with the session of whoever speaks: "create a flow
that creates a task for me when a sale over €100 is completed" (it leaves it as a **draft**, off, for you to
review, FLOW-F17), "turn on the welcome automation", "pause the till one", "what automations do I have?",
"run the weekly review now", "why did the welcome one fail?". And an automation can also hand a step to the
assistant, with nobody in front of it: **Ask the assistant** (FLOW-F37 to F39).

## Adopted reference

**With which permissions an automation acts, and whether it can be run by hand while paused** (skill
`market-decision`, 2026-10-15).

| Product | How it solves it | Source |
|---|---|---|
| Salesforce Flow | Automations that start on their own (from a record) run in **system context**, without looking at the permissions of whoever made them | https://trailhead.salesforce.com/content/learn/modules/flow-implementation-2/grant-flow-permissions-and-context |
| HubSpot Workflows | A record is only enrolled by hand if the workflow **is on**; off, nothing new gets in | https://knowledge.hubspot.com/workflows/manually-enroll-objects-into-workflows |
| HubSpot Workflows | Turn off for what is new; what was waiting does not run its actions | https://knowledge.hubspot.com/workflows/turn-off-workflows |
| Power Automate | An automated or scheduled flow runs with **its owner's** connections; if the owner leaves, it has to be changed | https://learn.microsoft.com/power-automate/change-cloud-flow-owner |
| Power Automate (forum) | When the owner's account was deactivated, the automated flows broke; only the manual ones kept going | https://powerusers.microsoft.com/t5/General-Power-Automate/Need-to-use-another-User-s-connections-on-a-Flow/m-p/1507107 |
| Power Automate | A flow in "Deactivated" does not run: it has to be activated again | https://learn.microsoft.com/power-automate/fix-connection-failures |
| Zapier | Each Zap uses its owner's private connections; the owner has to have them to turn it on | https://help.zapier.com/hc/en-us/articles/8496326497037 |
| Zapier (consulting forum) | A Zap made with the account of someone who left keeps running with their credentials | https://alltomate.com/blogs/is-zapier-safe/ |
| Business Central | Queued tasks run with the session of whoever set them ready and need their permissions | https://learn.microsoft.com/en-us/dynamics365/release-plan/2023wave1/smb/dynamics365-business-central/delegated-admins-job-queue-entries-are-run-user |
| Odoo | Automated actions run with elevated access (`sudo`); it is advised not to hide missing permissions with it | https://deploymonkey.com/blog/odoo-sudo-superuser-security |
| Current product (ERPlora) | "An automation acts with its own permissions, never with those of whoever created it"; they are granted one by one; the hub refuses to run a paused one | `modules/flows/WORKFLOW.md`, "Rules that are never broken" and FLOWS-F22 |

**Winner:** the tools **inside the product** (Salesforce, HubSpot, Odoo and the current product) make the
automation run **as the business**, not as the person who created it; the integration ones (Zapier, Power
Automate, Business Central) use the owner's account, and their forums tell what happens when that person
leaves. Our user is a small business whose staff changes, so the automation acts **as the business**, but
**only with the actions the owner has allowed it one by one** (like the current product): without a granted
permission, the step is refused and the history says so. And **running by hand requires it to be on**
(HubSpot, Power Automate and the current product): to see what it would do while off there is **Try it**,
which runs nothing.
**Why not the others:** with the permissions of whoever created it, the automation stops working the day
that person leaves or changes role, which is the repeated complaint in the forums; with all the system's
permissions and no list, a badly written automation could do anything.

From the current product we keep, already checked there against Zapier, Make, Power Automate, Shopify
Flow, Odoo and Business Central (`qa-hub-flows`, ADR-0461): **one column** of steps from top to bottom and
not a canvas of nodes (on the counter's tablet a column is used with a finger); **no branches**: an "Only
continue if…" that is not met ends the automation (that is working, not failing), and two outcomes are two
automations; **starting from a template** of the gallery; and what the assistant writes is born a
**draft**.

## Before you start

1. Only the **owner** or an **administrator** open Automations (menu **Automations**).
2. Automations use **notices and actions of other apps**: the gallery and the drop-downs only offer those of
   the apps that are on in the business. Nine of the ten cards in the gallery create a **task**, so they need
   the **Tasks** app; without it the gallery hides them and says what is missing.
3. Schedules are read in the business's time: in phase 1, **Europe/Madrid**.

Initial setup, step by step:

1. Open **Automations** (FLOW-F01).
2. In the gallery, open a card, read what it will do and tap **Use this one** (FLOW-F04).
3. In the **Permissions** tab tap **Allow everything it needs** (FLOW-F12).
4. Open **Try it** and check what it would do with the last thing that happened in the business (FLOW-F13).
5. Turn on the switch and tap **Save** (FLOW-F14).
6. When it fires, check it in **History** (FLOW-F16).

## Screens

### Automations
Menu **Automations**, a single entry. From top to bottom:

- The **New automation** button, top right; on a phone it is only its **+**, so that the title can be read
  in full.
- **Waiting for your answer** — only if there is some question you can answer: each card, which automation
  it comes from, the question and its details (in a change by the assistant, also, right below the
  question, what it wants to do —"Cancel a reservation"— and each piece of data it would send, in words),
  who it was asked of, what happens if nobody answers and what a no does, **Add a note (optional)**,
  **Approve** and **No** (FLOW-F29). A manager or an employee, who only answer, see only this: "Nothing is
  waiting for your answer." when there is nothing.
- **Proposed by the assistant** — only if there are drafts: "The assistant wrote them when you asked it
  for an automation. They do nothing until you review and turn them on.", and for each one its name, the
  "Draft" label, **Review** and an × ("Discard") (FLOW-F18, FLOW-F19).
- **Your automations** — only if there is some. The search box "Search by name, by what starts it or by
  what it does", the **Showing** filters (on, paused) and **Starts with** (something that happens, a
  schedule, a date, by hand), the order (touched last, name) and the count. Each row: a box to pick it,
  the name, when it starts in words ("When a sale is charged", "Every day at 09:00", "Only when you press
  Run"), the last run, the "Active" or "Paused" label, the switch, **Make a copy** and **Delete**. With
  several picked, **Turn them on** and **Pause them** (FLOW-F02, FLOW-F03).
- **The gallery**, always below: "Pick one and it becomes yours, paused, so you can look at it before it
  does anything.", the **How does this work?** button and the cards in "Any business", "Hair and beauty"
  and "Bars and restaurants"; below, a **Comes with …** section for each app that brings ready-made
  automations (today, "Appointments", "Online booking" and "WhatsApp inbox"), with its cards, their state
  ("Active", "Paused", "New version") and **Turn it on**, **Pause it**, **See it** and **Restore the factory
  one** (FLOW-F33 to F35); at the end, the line of what is missing ("Some automations are hidden: they need
  Tasks.") (FLOW-F04).

### Automation editor
It opens when you tap a row, press **New automation**, use a card or review a draft. Header: ← (back to
the list; if there are unsaved changes, it asks first), the name (empty: "Untitled automation"), the
"Active"/"Paused" label, the switch, **Try it**, **Run now** and **Save** ("Saving…"). Four tabs:

- **Steps**: the trigger's card ("When this happens…"), the steps in a column, each with its handle to
  drag it and × (waits and "Only continue if…" are narrow strips; the rest, cards that unfold when tapped;
  inside, **More options**: "Only if…" and "If it fails, it carries on", FLOW-F25), and the buttons to
  add: **Do something**, **Look something up**, **Only continue if…**, **Wait**, **Send a message**
  (FLOW-F31 and F32, with the WhatsApp inbox), **Call another system** (FLOW-F27), **Ask someone first**
  (FLOW-F28) and **Ask the assistant** (FLOW-F37). With no steps: "No steps yet. Add the first thing this
  automation should do."
- **Try it**: what it would do with the last thing that happened, doing nothing (FLOW-F13).
- **Permissions**: "An automation runs with its own permissions, never with yours. Nothing below happens
  until you allow it.", the "Waiting for your permission" or "Allowed" rows and **Allow everything it
  needs** (FLOW-F12).
- **History**: the runs, the most recent first and those stopped by an error at the top (FLOW-F16); one
  stopped by an error in a step carries **Resume from the step that failed** (FLOW-F24).

### Guide
The gallery's **How does this work?** button. "How automations work", with five sections: "What an
automation is", "Your first automation, step by step", "Permissions: why you have to say yes", "How to
know whether it worked" and "What it cannot do yet". **Back to the automations** goes back (FLOW-F08).

## States of each screen

| State | What is seen |
|---|---|
| Loading | The list with its indicator; the editor, "Loading…" |
| Empty | With no automations, only the gallery; with no steps, "No steps yet…"; with no runs, "It has not run yet." |
| No results | "Nothing here matches that." and **Show them all again** |
| Error | The message in red above, with **Retry** in the list; a failure to save, turn on, copy or delete says what does not fit and changes nothing; if what automations can use (notices and actions) cannot be read, "What automations can use here could not be read." with **Retry** |
| Reconnecting | "Reconnecting…" while the live feed comes back; what is painted stays |
| No permission | "You do not have permission" instead of the screen |
| App inactive | "This app is not active in this business" |

## Flows

| ID | Flow | Status |
|---|---|---|
| FLOW-F01 | Open Automations | done |
| FLOW-F02 | See, search and sort the automations | done |
| FLOW-F03 | Turn on or pause from the list, one or several | done |
| FLOW-F04 | Create an automation from a gallery card | done |
| FLOW-F05 | Reach a card from somewhere else | done |
| FLOW-F06 | Make a copy | done |
| FLOW-F07 | Delete an automation | done |
| FLOW-F08 | Read the guide | done |
| FLOW-F09 | Create an automation from scratch | done |
| FLOW-F10 | Choose when it starts | done |
| FLOW-F11 | Add, order and fill in the steps | done |
| FLOW-F12 | Grant and withdraw the permissions | done |
| FLOW-F13 | Try it without it doing anything | done |
| FLOW-F14 | Save and turn on from the editor | done |
| FLOW-F15 | Run by hand | done |
| FLOW-F16 | See what it did and why it failed | done |
| FLOW-F17 | Ask the assistant for an automation | done |
| FLOW-F18 | Review an assistant's draft and create it | done |
| FLOW-F19 | Discard an assistant's draft | done |
| FLOW-F20 | Another app asks whether an automation is already set up | done |
| FLOW-F21 | When something happens in the business, the automation starts | done |
| FLOW-F22 | When the time comes, the automation starts | done |
| FLOW-F23 | When a wait ends, the automation carries on | done |
| FLOW-F24 | Resume a run from the step that failed | done |
| FLOW-F25 | "Only if…" and "If it fails, it carries on" on each step | done |
| FLOW-F26 | Keep secrets that cannot be read again | done |
| FLOW-F27 | Call another system | done |
| FLOW-F28 | Ask someone first | done |
| FLOW-F29 | Answer what an automation asks | done |
| FLOW-F30 | Close what nobody answered in time | done |
| FLOW-F31 | Send a message to a customer | done |
| FLOW-F32 | Put a photo, a video or a PDF at the top of a WhatsApp | done |
| FLOW-F33 | Turn on an automation another app brings | done |
| FLOW-F34 | Pause an automation another app brings, without deleting it | done |
| FLOW-F35 | Restore the factory version of an automation another app brings | done |
| FLOW-F36 | Repair a set-up automation with a fault its app already fixed | done |
| FLOW-F37 | "Ask the assistant" step | done |
| FLOW-F38 | The assistant does its step inside an automation | done |
| FLOW-F39 | The SaaS serves an automation's AI step | done |

### FLOW-F01 Open Automations
Status: done (server and screen)
Actor: owner, administrator
Screen: Automations
Steps:
1. Open **Automations** in the menu.
2. The assistant's drafts (if any), your automations (if any) and the gallery show up.
In: the session.
Out: nothing saved.
If it fails: without permission, "You do not have permission"; with the app off, "This app is not active in
this business"; any other failure, in red with **Retry**. The owner and the administrator see it; the rest
of the team does not have the entry in the menu.
Involved: FLOW-F02, FLOW-F04, FLOW-F18

### FLOW-F02 See, search and sort the automations
Status: done (server and screen)
Actor: owner, administrator, assistant
Screen: Automations
Steps:
1. In **Your automations** each row says the name, when it starts in words, when it last ran and how it
   ended, and whether it is "Active" or "Paused". A name that does not fit in its row ends in an ellipsis,
   never split mid-word: it can be read in full by resting the pointer on it, on the phone's card and when
   opening it.
2. Type in the search box (name, the notice that starts it or the actions it does) or filter by
   **Showing** and **Starts with**; sort by **Last touched** or **Name**.
3. With no results: "Nothing here matches that." and **Show them all again**.
4. Tap a row to open it in the editor.
In: the business's automations, in pages of up to 100.
Out: nothing saved. The list updates itself when someone changes one or a run ends.
If it fails: if the list cannot be read, the message in red at the top with **Retry**; what was already
painted stays.
Involved: FLOW-F01, FLOW-F03, FLOW-F06, FLOW-F07

### FLOW-F03 Turn on or pause from the list, one or several
Status: done (server and screen)
Actor: owner, administrator, assistant
Screen: Automations
Steps:
1. Move a row's switch: it is saved at once and the label changes to "Active" or "Paused".
2. For several: tick their boxes and press **Turn them on** or **Pause them**.
3. Turning on one that lacks permissions warns: "On, but it still lacks the permissions it asks for: it will
   do nothing until you allow them in its Permissions tab."
In: the automation (by voice, by its name: "turn on the welcome automation"). Before turning it on or
pausing it, the assistant's card names it by its name ("Welcome"), never by its code.
Out: on or paused (`flow.flow.enabled`, `flow.flow.paused`). When paused it stops starting; a run that is
waiting is cancelled when it wakes up if it is still paused (if it is turned on again before, it carries
on). A schedule that is turned on counts from that moment: it does not make up for what happened while it
was paused.
If it fails: the message in red at the top; the row stays as it was.
Involved: FLOW-F12, FLOW-F14, FLOW-F22, FLOW-F23

### FLOW-F04 Create an automation from a gallery card
Status: done (server and screen)
Actor: owner, administrator
Screen: Automations
Steps:
1. In the gallery, tap a card: it unfolds (one at a time) with the sentence of what it will do, "What you
   decide" and "What it will ask permission to do", each permission with its explanation.
2. If there is already an automation turned on that starts with the same notice, it warns: "Careful: "…"
   already starts with the same thing."
3. Press **Use this one** ("It is created paused. Nothing happens until you turn it on.").
4. The editor of the new one opens, paused, on the **Permissions** tab. Carry on with FLOW-F12, FLOW-F13 and
   FLOW-F14.
5. If the business already has it, the card carries "Active", "Paused" or "Unfinished" (without permissions)
   and the first button is **See it**; **Use this one** is still available and creates a second one. A
   schedule card is recognised by its schedule and what it does, even if it was renamed.
In: the ten cards: seven of "Any business", two of "Hair and beauty" and one of "Bars and restaurants". A
card hides if an app it uses is missing, and below the gallery it says which.
Out: a new automation, **paused and without permissions**, with the card's name and values (wait a day,
100,00 €, six people…).
If it fails: the message in red inside the card; nothing is created.
Involved: FLOW-F05, FLOW-F08, FLOW-F12, FLOW-F13, FLOW-F14

The ten cards of the gallery, with their sector, when they start and what they do.

| Card | Sector | Starts | Does |
|---|---|---|---|
| Welcome a new customer | any | A customer card is created | Waits a day and leaves the task of welcoming them |
| Note the big sales on the card | any | A sale is charged | Only if it has a customer and is over 100,00 €: adds a note to their card |
| The checklist of someone new in the team | any | Someone is added in Staff | Leaves the task of preparing their first day |
| Review the till when it closes | any | A till is closed | Leaves the task of reviewing the close |
| Find out when the tax agency rejects a record | any | VeriFactu marks a record as rejected | Leaves an urgent task |
| Review the week on Friday | any | Fridays at 18:00 | Leaves the task of reviewing the week |
| Check the agenda every morning | salon | Every day at 09:00 | Leaves the task of going over the agenda |
| Call whoever did not come | salon | An appointment is marked "No-show" | Leaves an urgent task of calling them |
| Prepare the tables of big groups | restaurant | A reservation comes in | Only if they are six or more: leaves the task of preparing it |
| Hear about big sales | any | A sale is charged | Only if it is over 100,00 €: leaves a task |

### FLOW-F05 Reach a card from somewhere else
Status: done (screen)
Actor: owner, administrator
Screen: Automations
Steps:
1. Open a shortcut to an automation of the gallery (a saved link or one another app offers; today no app of
   the Hub offers one yet): **Automations** opens with that card unfolded and in view.
2. If a shortcut is tapped again with the screen already open, the new card unfolds.
3. A shortcut to a card that does not exist or is hidden shows the gallery without opening anything.
In: the card the shortcut names.
Out: nothing saved.
If it fails: the same as FLOW-F01; a card that cannot be used here does not open.
Involved: FLOW-F04, FLOW-F20

### FLOW-F06 Make a copy
Status: done (server and screen)
Actor: owner, administrator, assistant
Screen: Automations
Steps:
1. In the row, press **Make a copy**.
2. "Copy of …" (or "Copy of … (2)") appears in the list, paused, and the notice "Copied, and the copy is
   paused. It has none of the original's permissions: allow what it needs before turning it on.".
In: the automation being copied (by voice, by its name; the assistant's card names it by its name, never by
its code).
Out: a new automation with the same steps, paused, without permissions and without history
(`flow.flow.created`).
If it fails: the message in red at the top; nothing is created.
Involved: FLOW-F02, FLOW-F12

### FLOW-F07 Delete an automation
Status: done (server and screen)
Actor: owner, administrator, assistant
Screen: Automations
Steps:
1. In the row, press **Delete**.
2. Confirm: "Delete "…"? This cannot be undone. Its history stays." with **Yes, delete it** or **Leave it**.
In: the automation being deleted (by voice, by its name, and always with the confirmation: the assistant's
card names it by its name, never by its code).
Out: the automation stops starting at once and leaves the list; what was waiting is cancelled at once; its
history is kept (`flow.flow.deleted`).
If it fails: the message in red at the top; the row stays.
Involved: FLOW-F02, FLOW-F16, FLOW-F23

### FLOW-F08 Read the guide
Status: done (screen)
Actor: owner, administrator
Screen: Guide
Steps:
1. In the gallery, press **How does this work?**.
2. Read the five sections. "What it cannot do yet" says what is really missing: branches, counting back
   from a date of the notice, that messages to a customer only go by WhatsApp (not by email), and that the
   assistant only writes drafts.
3. **Back to the automations** goes back.
In: nothing; the texts are inside the app.
Out: nothing saved.
If it fails: it reads nothing of the business; without permission, "You do not have permission".
Involved: FLOW-F04, FLOW-F21

### FLOW-F09 Create an automation from scratch
Status: done (server and screen)
Actor: owner, administrator
Screen: Automation editor
Steps:
1. In **Automations** press **New automation**.
2. The empty editor opens: "Untitled automation", "Paused", the trigger "Only when you press Run" and "No
   steps yet…".
3. Write the name, choose when it starts (FLOW-F10) and add the steps (FLOW-F11).
4. Press **Save**: "Saved." appears and the editor stays open on it; permissions can now be granted to it
   (FLOW-F12).
In: what is written in the editor and what the business's automations can use (notices and actions of its
active apps).
Out: a new automation, paused unless the switch was turned on before saving, and without permissions
(`flow.flow.created`). Without a name it is saved as "Untitled automation".
If it fails: what does not fit, in red and next to the step that has it ("Choose what this step does.",
"This notice does not exist in your business.", "That date and time has already passed."…); nothing is
saved.
Involved: FLOW-F10, FLOW-F11, FLOW-F12, FLOW-F14

### FLOW-F10 Choose when it starts
Status: done (server and screen)
Actor: owner, administrator
Screen: Automation editor
Steps:
1. Tap the "When this happens…" card and choose:
   - **Something happens**: in "Choose what happens", the notices of the business's active apps, said in
     words ("a sale is charged", "a customer card is created", "an appointment is marked as a no-show"…) and
     with a search box. Below, **Only when…**: conditions on the notice's data ("the total is greater than
     10000"); without them it starts with every notice, on its own (FLOW-F21).
   - **On a schedule**: "How often" (every day, every week, every month), the day of the week or of the
     month when it applies, and the time, in the business's time. A day of the month that does not exist
     (the 31st in April) is skipped that month.
   - **Once, at a date and time**.
   - **Only by hand**: it does not start on its own (FLOW-F15).
2. The card sums up what was chosen ("When a sale is charged", "Every Friday at 18:00"…).
In: the notices of the active apps.
Out: the trigger, on **Save**.
If it fails: a notice that does not exist in the business, a schedule without a time or a past date are
refused by the server on saving, next to the field. The date is only looked at if it changes: a "Once"
automation that already fired can be renamed or paused.
Involved: FLOW-F21, FLOW-F22, FLOW-F15

### FLOW-F11 Add, order and fill in the steps
Status: done (server and screen)
Actor: owner, administrator
Screen: Automation editor
Steps:
1. Press an add button; the step appears at the end, open. Drag the handle to change the order; × removes
   it.
2. Fill in its form:
   - **Do something**: "What to do" (an action of the active apps, chosen from a list with a search box:
     "Create a task", "Add a note to a customer"…) and "With this information": a field for each piece of
     data the action asks for (the required ones marked) and **Add information** for the optional ones.
   - **Look something up**: "What to look up" (a query of the active apps), its data and "What to keep"
     ("The first row it finds, field by field" or "Only how many there are"). If it finds nothing, the
     automation carries on; to stop it, an "Only continue if…" on "Found something" is added after it.
   - **Only continue if…**: one or several rows "Data", "Is" ("equal to", "not equal to", "one of",
     "present", "contains", "greater than", "greater than or equal to", "less than", "less than or equal
     to") and "Value", with **Add a condition**. The "Value" is typed or, with **Insert data**, is another
     piece of the automation's data (the notice's total against the minimum a query read), and then it
     shows as a pill with "Remove this data". If not all of them are met, the automation ends there
     without an error.
   - **Wait**: "How long" and the unit (minutes, hours or days), counted from the previous step; from one
     minute to 30 days.
3. In each value, **Insert data** opens "Which data?", with the notice's data and a real example from the
   business beside it (the last notice of that kind), and the data the previous steps leave; it is chosen,
   not typed. A chosen piece of data shows as a pill; the rest of the value is text. In what a person reads
   —the question of "Ask someone first" (FLOW-F28) and the message to a customer (FLOW-F31)— each piece of
   data comes out in words, in the language of whoever saved the automation: a yes or a no as "Yes" or
   "No", a date and a time as they are written in that language and at the business's time ("2 Nov 2026,
   10:00"), and an amount a previous step leaves in the business's currency ("120,50 €"); a number the
   notice brings comes out as it is, because the notice does not say whether it is money. What goes to
   another action, to another system or to an "Only continue if…" carries each piece of data as it is.
In: the actions and queries of the active apps, the last real notice of that kind and what the previous
steps leave. Data are named in the screen's language ("Sale number", "Customer phone"), never with their
internal name.
Out: the steps, on **Save**. Each action or query that is named starts asking for its permission
(FLOW-F12).
If it fails: the server refuses on saving an action or a query that does not exist in the business, data of
a step that does not come before, an empty condition or a wait out of range, next to the step.
Involved: FLOW-F12, FLOW-F13, FLOW-F16

### FLOW-F12 Grant and withdraw the permissions
Status: done (server and screen)
Actor: owner, administrator, assistant
Screen: Automation editor
Steps:
1. Open **Permissions** (it opens by itself when creating from the gallery).
2. Read the list, taken from the **saved** steps: each action and each query, said in words. What is missing
   shows as "Waiting for your permission"; what is granted, "Allowed" with **Withdraw**. With unsaved
   changes it warns: "Save it first: what you allow is what is saved.".
3. Press **Allow everything it needs**: "Permissions updated." appears.
In: the saved steps and the permissions it has (by voice, the assistant's card names the automation by its
name, never by its code).
Out: the automation's full list of permissions (`flow.flow.granted`). Before the first save there is
nothing to allow: the tab says so and asks to save.
If it fails: if the list names something that does not exist in the business, or something that needs a
person in front (cancelling, refunding, erasing data, sending to the tax agency, seating a group that
arrives…), it is refused whole and it says what. The only exception is "Cancel a reservation": it is allowed
when an **Ask the assistant** step with "Ask me first" uses it (FLOW-F37), and only then. Nobody grants what
they cannot do themselves: "You cannot allow what you may not do yourself: "…"." (nor an integration with
its key). Each step acts only with the permission it was granted, never with all those of whoever set it
up. Booking with only the name and phone of whoever books finds or creates their customer card without
allowing anything of Customers.
Involved: FLOW-F04, FLOW-F06, FLOW-F11, FLOW-F16, FLOW-F37

### FLOW-F13 Try it without it doing anything
Status: done (server and screen)
Actor: owner, administrator
Screen: Automation editor
Steps:
1. Press **Try it** (header) or the **Try it** tab.
2. At the top: "None of this is real. Nothing is sent, nothing is charged and nothing is written down: this
   is only what your automation WOULD do." and with which data it tries ("With what really happened the
   last time: …") or "This has not happened in your business lately…".
3. Step by step it says what it would do and with which values, and points out: if it would not even start
   because of its "Only when…", what would come out empty, what the action would refuse ("They would refuse
   it: …"), a condition that would stop it ("It would stop here, and that is the automation working"), what
   cannot be known because it comes from a step that has not run, a wait and a step without permission
   ("They would refuse it: you have not allowed it "…" yet").
4. In an **Ask the assistant** step, below "Would ask the assistant: …", each fixed piece of data (FLOW-F37)
   with the value it would have, said as the "Waiting for your answer" card says it (FLOW-F29), read as
   whoever is trying it: a card by its name ("Cancel a reservation › On behalf of the customer" · "Lucía
   Pérez"), a day as its language writes it, an amount in the business's currency, a yes or a no; never an
   id. A card that person cannot see (without permission, or that is gone) is left out, as on the card. If
   one would come out empty, the query or action that would not be used (""…" would not be used: "…", fixed
   by this step, would be empty in this run."), and if it comes from a step that has not run, "Comes from an
   earlier step that has not run: …".
In: what is in the editor, even if it is not saved, and the last real notice of that kind.
Out: nothing: it does not run, it does not save.
If it fails: what does not fit in the document is said next to the step; without permission to read the
real notices, "You do not have permission".
Involved: FLOW-F10, FLOW-F11, FLOW-F12, FLOW-F14

### FLOW-F14 Save and turn on from the editor
Status: done (server and screen)
Actor: owner, administrator
Screen: Automation editor
Steps:
1. Move the header's switch: the label changes to "Active". If it lacks permissions it warns as in
   FLOW-F03; if **Try it** has not been opened, "You have not tried it yet…". It does not prevent turning it
   on.
2. Press **Save** ("Saving…" and then "Saved."): the document is saved and, if the switch changed, it is
   then turned on or paused.
In: what is in the editor and its unsaved changes.
Out: the saved automation (`flow.flow.updated`; `flow.flow.enabled` or `flow.flow.paused` if the switch
changed). Changing the trigger or the steps raises its version: what was already under way carries on with
the version it started with.
If it fails: the message in red, next to the step that does not fit; nothing is saved. A failure the Hub
does not explain (no connection) says "It could not be done right now. Try again in a moment.", never a
technical text; what was written stays in the editor.
Involved: FLOW-F03, FLOW-F12, FLOW-F13, FLOW-F15

### FLOW-F15 Run by hand
Status: done (server and screen)
Actor: owner, administrator, assistant
Screen: Automation editor
Steps:
1. With the automation saved and on, press **Run now**.
2. Confirm: "Run it now? It will really do what its steps say." with **Yes, run it** or **Cancel**.
3. "Run. See it in History." appears; if it stopped by an error, "It ran and stopped by an error: …" in
   red; if it was left waiting, "It ran and is waiting…".
In: the automation (by voice: "run the weekly review now"; the assistant's card names it by its name,
never by its code).
Out: a real run, with all its effects (`flow.run.started`, `flow.run.finished`). Without the data of a
notice, what it reads from the notice comes out empty.
If it fails: paused, "This automation is paused: turn it on to run it."; unsaved, the button does not show;
with unsaved changes it is disabled: "Save it first: "Run now" runs what is saved.".
Involved: FLOW-F14, FLOW-F16, FLOW-F21

### FLOW-F16 See what it did and why it failed
Status: done
Actor: owner, administrator, assistant
Screen: Automation editor
Steps:
1. Open the **History** tab: the runs, the most recent first, 20 at a time with **See more**; it updates
   itself.
2. If any stopped by an error, "Needs somebody" shows at the top with "N runs stopped by a problem".
3. Each run: its state ("Finished well", "Finished: a condition did not hold", "Stopped by an error",
   "Waiting", "Cancelled"), the day and the time, **Copy the reference** and ▾ to see its steps in words
   ("Did: Create a task", "Found 3", "Found nothing, and carried on", "Waited 1 hour", "It stopped here
   because this was not met: Total greater than 10000").
4. One stopped by an error says what happened and what to do, in your language even if the automation was
   saved in another ("It tried to do something you have not allowed it to do ("…"), so it stopped. Open
   Permissions and allow what it needs."); if the error is from the app that did the action, its sentence
   comes out as it is, in the automation's language, with the technical text folded.
In: that automation's runs of the last 90 days, and all those still waiting.
Out: nothing. The history keeps each finished run **90 days** and then forgets it; one that is waiting or
under way is never deleted. What its steps read (a customer's card) is not kept when it ends: only the ids
and the amounts of the notice that started it; one stopped by an error keeps it 7 days, so that it can be
resumed (FLOW-F24).
If it fails: if the history cannot be read, the message in red with **Retry**; with no runs, "It has not
run yet.".
Involved: FLOW-F13, FLOW-F15, FLOW-F21, FLOW-F22, FLOW-F23

### FLOW-F17 Ask the assistant for an automation
Status: done
Actor: owner, administrator, assistant
Screen: assistant
Steps:
1. Open the Hub's assistant and ask it for something that happens on its own, speaking or typing ("create a
   flow that creates a task for me when a sale over €100 is completed").
2. The assistant writes a **draft**: name, when it starts, from one to eight "do something", "only continue
   if" or "wait" steps, and the notes of what it could not decide. Before leaving it, it shows you its card
   and waits for your yes, like any change it asks you for.
3. It tells you it has left it waiting in Automations and repeats its doubts; you review it in **Proposed by
   the assistant** (FLOW-F18).
In: what is asked for, in words, and what the business's automations can use.
Out: a pending draft (`flow.draft.proposed`). It does **not** create any automation, grant permissions or
run anything. Only whoever can manage the automations (owner and administrator) can ask for it.
If it fails: a draft that does not follow the requested shape, or with a step that reads what no previous
step leaves, is refused before it is saved and the assistant says so.
Involved: FLOW-F18, FLOW-F19

### FLOW-F18 Review an assistant's draft and create it
Status: done (server and screen)
Actor: owner, administrator
Screen: Automations
Steps:
1. In **Proposed by the assistant**, press **Review**: it opens in the editor as an automation that does not
   exist yet, with the box "This is a draft the assistant wrote. It is off, has no permissions and nothing
   happens until you turn it on." and "What the assistant could not decide".
2. Correct and complete the steps (FLOW-F10, FLOW-F11).
3. Press **Save**: the automation is created (paused if the switch was not touched) and the draft leaves the
   tray as used, **in the same operation**: it cannot be created twice.
In: the pending draft, as the assistant left it, with its notes. If you ask the assistant for it, its card
names the draft by its name, never by its code.
Out: a new automation without permissions and the used draft, with the link to it (`flow.flow.created`,
`flow.draft.used`). Leaving without saving leaves the draft in the tray.
If it fails: if it does not fit (an action that does not exist here), the message next to the step and
nothing is created; a draft already decided, "That draft was already decided.".
Involved: FLOW-F17, FLOW-F19, FLOW-F12

### FLOW-F19 Discard an assistant's draft
Status: done (server and screen)
Actor: owner, administrator
Screen: Automations
Steps:
1. In **Proposed by the assistant**, press × ("Discard") on the draft that is not wanted.
2. "Discarded." appears and the draft disappears from the tray; the others stay.
In: the pending draft (also by asking the assistant: its card names it by its name, never by its code).
Out: the discarded draft (`flow.draft.dismissed`), which is kept as a record.
If it fails: one already decided cannot be decided again: "That draft was already decided.".
Involved: FLOW-F17, FLOW-F18

### FLOW-F20 Another app asks whether an automation is already set up
Status: done
Actor: another app, assistant
Screen: none
Steps:
1. An app that offers a shortcut to Automations asks with a notice and an action.
2. It receives three numbers: how many automations start with that notice and can do that action, how many
   of them are on and how many listen to that notice but do not have any permission yet (half set up).
In: the notice and the action it asks about; it requires the permission to see automations.
Out: three numbers; no name or content. Today no app uses it yet; the assistant can also ask it.
If it fails: without the permission to see automations, it is refused.
Involved: FLOW-F05

### FLOW-F21 When something happens in the business, the automation starts
Status: done
Actor: the platform
Screen: none (it is seen in History)
Steps:
1. Another app leaves a notice (for example, "a sale is charged").
2. Each automation that is **on**, starts with that notice and whose "Only when…" is met begins a run with
   the notice's data, and does its steps in order.
3. If its "Only when…" can no longer be read (because it was written by hand in the administration or with
   an earlier version), it does not stay silent: it begins a run that stops with "Its "Only when…" can no
   longer be read…", visible in History, and the other automations of that notice carry on.
In: the notice of another app, with its data (ids, amounts and states; never names or texts), which the
platform hands to it a few seconds after it happens, outside the request that left it. A paused automation
does not receive what happened while it was paused.
Out: a run (`flow.run.started`, `flow.run.finished` or `flow.run.parked` if it waits), in the business
where the notice happened. The same notice delivered twice starts **a single** run per automation.
If it fails: each step that fails stops the run with its reason, visible in History; the previous steps
stay done. An automation that would set itself off in a chain is stopped (see "Para quien lo mantiene"). An
"Only continue if…" that can no longer be read stops the run with "This "Only continue if…" can no longer be
read…".
Involved: FLOW-F10, FLOW-F11, FLOW-F15, FLOW-F16

### FLOW-F22 When the time comes, the automation starts
Status: done
Actor: the platform
Screen: none (it is seen in History)
Steps:
1. Every minute, the platform looks at the automations that are on with a schedule or a date.
2. Those that have reached their time (in the business's time) start once and do their steps.
3. The schedule's next time is counted from now; a date starts only once.
In: the schedules and dates of the automations that are on.
Out: a run (`flow.run.started`, `flow.run.finished`); the schedule's next time. If the system was stopped and
several times were missed, it starts **once** and carries on from now. A pass with nothing to do leaves no
notice.
If it fails: a step that fails stops that run with its reason, visible in History; the schedule's next time
still stands.
Involved: FLOW-F03, FLOW-F10, FLOW-F16

### FLOW-F23 When a wait ends, the automation carries on
Status: done
Actor: the platform
Screen: none (it is seen in History)
Steps:
1. Every minute, the platform looks at the runs that were waiting ("Wait").
2. Those whose wait is over go on to the next step, with the version of the automation they started with.
In: the runs that are waiting and the time they wake up.
Out: the run carries on (`flow.run.resumed`) and finishes or waits again. A pass with nothing to do leaves
no notice.
If it fails: if the automation is paused when it wakes up, the run is cancelled ("Cancelled: the automation
was paused while it waited."); if it is deleted, too ("Cancelled: the automation was deleted.").
Involved: FLOW-F03, FLOW-F07, FLOW-F11, FLOW-F16

### FLOW-F24 Resume a run from the step that failed
Status: done
Actor: owner, administrator, assistant
Screen: Automation editor
Steps:
1. In **History**, a run that stopped by an error in one of its steps carries **Resume from the step that
   failed**. First, fix the cause: grant the missing permission, turn the app on again or wait for the other
   system to answer.
2. Press the button and confirm: "Resume it from the step that failed?" with **Yes, resume it** or
   **Cancel**.
3. "Resumed: it finished well." appears (or "…it is waiting"); if it fails again, "It was resumed and stopped
   by an error again: …" next to the run, which can be resumed again. Its steps keep "Resumed here, from the
   step that had failed".
In: the run stopped by an error (by voice, by its reference: "resume the welcome one that failed"). The
assistant's card names it as History does, with its automation in front: "Welcome · 15 Oct 2026, 21:00",
never by its code.
Out: the same run carries on at the step that failed, without repeating those that already took effect and
with the steps it started with, even if the automation changed afterwards (`flow.run.resumed`,
`flow.run.finished`). A run stopped by an error keeps what its steps left **7 days** so that it can be
resumed; after that it forgets it and can no longer be resumed.
If it fails: with the automation paused, "This automation is paused: turn it on to run it."; deleted, "That
automation does not exist in this business."; one that stopped before doing any step (a chain, an
unreadable "Only when…"), at something that needs a person in front or at a call to a private or badly
written address (the same steps would fail again), "This run cannot be resumed…: run it again whole"; after
7 days, "…can no longer be resumed…"; one already resumed, "Only a run that stopped by an error at one of its
steps can be resumed…": it is never resumed twice. None resumes by itself.
Involved: FLOW-F12, FLOW-F15, FLOW-F16

### FLOW-F25 "Only if…" and "If it fails, it carries on" on each step
Status: done
Actor: owner, administrator
Screen: Automation editor
Steps:
1. Open a **Do something**, **Look something up** or **Wait** step and press **More options**.
2. Tick **Only if…** and write its conditions, as in an "Only continue if…" ("Total greater than 10000"):
   "When it does not hold, this step is skipped and the automation goes on.".
3. In **Do something** and **Look something up**, tick **If it fails, carry on with the next steps**: "Its
   failure is written in this step and the next steps can check whether it failed.".
4. Closed, the step says it below its title ("Only if: Total greater than 10000 · If it fails, it carries
   on"). A later step can check, with **Insert data**, whether that step was "Skipped" or "Failed" and its
   "Failure code".
5. Press **Save**.
In: the conditions and the box of each step.
Out: the step with its options, on **Save**. When it runs, a step whose "Only if…" does not hold is not done
and the history says "Skipped: its "Only if…" did not hold (…)"; one that fails with "If it fails, it
carries on" leaves "…: the reason. It carried on with the next steps." and the run finishes well if the rest
goes well. **Try it** says "Would be skipped: its "Only if…" does not hold". Without options, a step that
fails stops the run, as always.
If it fails: an "Only if…" that reads data no previous step leaves, with a comparison that does not exist,
or an "If it fails" on a wait or on an "Only continue if…", is not saved. An "Only if…" that can no longer be
read (written raw in the administration) stops the run with "The "Only if…" of this step can no longer be
read…", and that run is not resumed: the step has to be corrected.
Involved: FLOW-F11, FLOW-F13, FLOW-F16, FLOW-F24

### FLOW-F26 Keep secrets that cannot be read again
Status: done
Actor: owner, administrator
Screen: Automation editor
Steps:
1. Open a **Call another system** step. Below it is **Secrets**: "Keys and passwords of other systems.
   Insert them by name; once saved, nobody can read a value again, not even you.".
2. Write a **Name** (in capitals, like "STRIPE_KEY") and its **Value**, which is typed hidden, and press
   **Save secret**. "STRIPE_KEY saved. Its value can no longer be shown." appears and both fields are
   emptied. Saving the same name again changes its value.
3. The list shows only the names. To use one, in a value of the step press **Insert data** and choose
   "Secret "STRIPE_KEY"" in **Secrets**.
4. To delete it, press its **×** and confirm "Delete STRIPE_KEY?" with **Yes, delete it** or **Keep it**.
In: the name and value of each secret, typed on this screen. The assistant does not keep secrets: a value
said in a conversation would already have gone into the history.
Out: the secret sealed with the server's key (`flow.secret.saved`, `flow.secret.deleted`). Its value is
only opened at the moment of calling and never comes out: not in the list, nor in **Try it** (which shows
"••••"), nor in the history, nor in a failure; whatever the other system answers with the secret inside
also comes out hidden.
If it fails: a name with lower case at the start, digits first or symbols: "Use capitals, digits and _,
starting with a letter (STRIPE_KEY).", and what was written stays; without the server's encryption key, the
box says "This server cannot keep secrets yet: its encryption key is missing." as soon as it opens, instead
of the fields, and does not let anything be saved.
Saving a step that names a secret that does not exist: "There is no secret called "X"." next to the field.
A run whose secret was deleted or can no longer be opened stops before calling, with the reason and what to
do. A secret can only be inserted in **Call another system**: in any other step it is not saved.
Involved: FLOW-F11, FLOW-F13, FLOW-F16, FLOW-F27

### FLOW-F27 Call another system
Status: done
Actor: owner, administrator
Screen: Automation editor
Steps:
1. In **Steps**, press **Call another system**. Its card opens.
2. Choose the **Method** and write the **Address** by hand, starting with "https" and the server's name:
   "This step will ask your permission to call" and that name. After the name, data can be inserted.
3. Add the **Headers** the other system asks for (**Add a header**: **Name** and **Value**) and **What it
   sends**. In any value, **Insert data** offers what the notice brought, what the previous steps left, the
   **Secrets** (FLOW-F26) and the "No-repeat key" of this call.
4. Adjust the **Seconds to wait** (from 1 to 30) and, if you want, **More options** (FLOW-F25).
5. **Save** and, in **Permissions**, grant "Call" that server.
In: the method, the address, the headers, the text it sends and the wait.
Out: **Run now** answers at once, without waiting for the other system: the run stays at "Calling …" with
the server's name and the Hub makes the call in the background, within a few seconds; then the history says
"Called …: it answered 201", and the next steps can read its "State" and its "Text" (up to 1 MiB). If the
process falls over halfway, the call is repeated after 5 minutes with the **same** "No-repeat key", so that
the other system does not do it twice. **Try it** says "Would call … with this" with what it would send and
the secrets hidden, without calling.
If it fails: an address that does not start with "https" and its server, with a user or a password, or with
data before the name, is not saved ("Write the address by hand…"); nor are the headers the system sets
(Host, Content-Length…). When calling: a header with data that cannot be sent (an accent, an "ñ") stops the
run with the reason and the header's name, without calling; an address of a private network, of the server
itself or of the cloud's internal data is not called ("…is inside a private network, so it was not
called."); without permission, "…you have not let it do…"; if it answers an error, does not answer in time
or cannot be reached, the run stops with the reason and what to do, and can be resumed (FLOW-F24) or carry
on with "If it fails, it carries on"; a private address is not resumed: the step has to be changed and the
run started again. While the server cannot keep secrets (FLOW-F26), a call that uses none is saved, tried
and goes out the same; one that uses one stops before calling ("This server cannot use secrets…"). It does
not follow redirects. A run whose automation is deleted while it calls is cancelled.
Involved: FLOW-F12, FLOW-F13, FLOW-F16, FLOW-F24, FLOW-F25, FLOW-F26

### FLOW-F28 Ask someone first
Status: done
Actor: owner, administrator
Screen: Automation editor
Steps:
1. In **Steps**, press **Ask someone first**. Its card opens.
2. Write **The question** and, if you want, **Details (optional)**, with inserted data: they are filled in at
   the moment of asking.
3. In **Who has to answer** choose "Whoever runs the business" (by default), "A manager" or "An employee":
   "Managers answer it in Automations, under "Waiting for your answer"; whoever runs the business can
   too.".
4. Adjust **How long to wait for the answer** (from 1 to 720 hours; by default, 72).
5. In **If they say no**, "Stop the automation here" or "Carry on with the next steps"; in **If nobody answers
   in time**, "Count it as a no", "Stop the automation here" or "Carry on with the next steps". With "Carry
   on", the notice explains how to put an "Only continue if…" on "Approved" afterwards.
6. Press **Save**. This step does not ask for permission.
In: the question, its details, to whom, how long to wait and what to do with a no and with silence.
Out: the step. When it runs, the question waits in "Waiting for your answer" (FLOW-F29) with its text already
filled in, each inserted piece of data in words (FLOW-F11: "Yes", "2 Nov 2026, 10:00"), and the run stops
there (`flow.question.asked`); the history says "Asked managers; waiting for an answer until the …".
Changing the automation afterwards does not change a question already asked. **Try it** says "Would ask …
and wait up to … hours" with the question filled in as it will go out, without asking. A yes to this question
does not open the door to what needs a person in front: the steps after it still cannot cancel, refund or
erase. To cancel a reservation when someone says yes, ask the assistant for it with "Ask me first"
(FLOW-F37, F38).
If it fails: an empty question, or a wait of less than an hour or more than 30 days, is not saved; a
question that names a secret is not either.
Involved: FLOW-F13, FLOW-F16, FLOW-F25, FLOW-F29, FLOW-F30, FLOW-F37, FLOW-F38

### FLOW-F29 Answer what an automation asks
Status: done
Actor: owner, administrator, manager, employee
Screen: Automations
Steps:
1. In **Automations**, **Waiting for your answer** shows each question you can answer, the one that expires
   first at the top: which automation it comes from, the question and its details (with its data in words,
   FLOW-F28), "Asked of managers. Whoever runs the business can answer too.", what happens if nobody answers
   ("If nobody answers before …, it counts as a no.") and what a no does. If it is a change the assistant
   wants to make (FLOW-F38), the card first says what it wants to do: right below the question ("The
   assistant wants to change something in "Reservations""), the action with the name the history gives it
   ("Cancel a reservation", "Book an appointment"), both in your language even if the automation is written
   in another, also in a question that was already waiting. Its details are what it said and, below, each
   piece of data it would send, one per line, as its card in the chat says it (BASE-F97): a date and a time in
   your language and at the business's time ("Starts at: 2 Nov 2026, 10:00"), a value from a closed list with
   the name its app gives it ("Booked by: Counter"), an amount in the business's currency, a yes or a no as
   "Yes" or "No", a list by how many items it carries ("Services: 1 item") and a record by its name only if
   you can see it; if not, it does not show, and never by its code. The step's fixed data (FLOW-F37) come out
   already set, as it will send them ("On behalf of the customer: Lucía Pérez"), even if the assistant asked
   for another. An empty piece of data does not show. It is read when the tray opens, with what each person
   can see.
2. If you want, write in **Add a note (optional)**.
3. Press **Approve** or **No**. "Approved: the automation carries on." or "Answered no." appears and the card
   leaves the tray.
In: the decision and the note (by voice: "approve Ana's refund"), with who answers from their session. The
assistant's card names the question by what it asks, never by its code.
Out: the answer with who, when and the note (`flow.question.answered`). A yes carries on with the next steps,
which can read "Approved", "Note" and "Answered by"; a no does what the step says: it stops the run
("Cancelled: Marta answered no to "…"."; in a change by the assistant, "…" is its action, "Cancel a
reservation", in the language of whoever reads the history) or carries on. The history says "Marta answered
yes: "…"". Whoever runs the business sees all of them; a manager, those of managers and employees; an
employee, those of employees.
If it fails: the card stays with the reason: "Someone already answered this one. Nothing was done twice."
(two people at once: only one wins), "Too late: nobody answered it in time, so it was closed. Nothing was
done.", "This question was asked of someone else: you cannot answer it."; with the automation paused, a yes
(or a no that carries on) is refused in your language with "This automation is paused: turn it on to run
it." and the question waits; a no that stops the run is accepted. Deleting the automation cancels its
questions.
Involved: FLOW-F16, FLOW-F28, FLOW-F30

### FLOW-F30 Close what nobody answered in time
Status: done
Actor: system
Screen: none
Steps:
1. Every minute the Hub goes over the questions whose time is up.
2. It closes them as expired and does what their step says: count it as a no (whatever a no does), stop or
   carry on with the next steps.
In: the questions that are waiting, with their time limit.
Out: the expired question (`flow.question.expired`) and its run cancelled ("Cancelled: nobody answered "…" in
time."; in a change by the assistant, FLOW-F38, "…" is its action, "Book an appointment", in the language of
whoever reads the history) or carried on, with "Expired" for a later "Only continue if…"; the history says
"Nobody answered in time". A second pass does not close anything again.
If it fails: an overdue question the pass has not closed yet can no longer be answered; if the automation is
paused and it was due to carry on, the run is cancelled ("Cancelled: the automation was paused while it
waited."). If someone answers just as the pass closes it, only one wins.
Involved: FLOW-F16, FLOW-F28, FLOW-F29

### FLOW-F31 Send a message to a customer
Status: done
Actor: owner, administrator
Screen: Automation editor
Steps:
1. With the WhatsApp inbox in the business, press **Send a message** among the add buttons of **Steps**: the
   step appears at the end, open, with the title "Send a WhatsApp to a customer".
2. In "To (their phone)" insert the customer's phone with **Insert data** (the one on their card, which is
   already in international format): only the WhatsApp conversation of exactly that international number
   gets it, never a new one. An incomplete number typed by hand reaches nobody.
3. Write the "Message", with inserted data: it goes as it is if the customer wrote to you in the last 24
   hours, with each piece of data in words (FLOW-F11: a yes or a no, a date and a time, an amount of a
   previous step), also in the template's blanks.
4. Choose the "Template" among your templates approved by Meta (its text shows below) and fill in a piece of
   data for each blank: after 24 hours, WhatsApp only lets an approved template through. With no approved
   templates it says so: "You have no approved templates yet: create one in WhatsApp › Settings.". If the one
   you choose carries a photo, a video or a document at the top, it goes with its file (FLOW-F32).
5. **Save** and, in **Permissions**, allow "Send a WhatsApp to a customer" (FLOW-F12).
In: the customer's phone (from a notice or from a previous step), the approved templates of the WhatsApp
inbox and the conversation of that number.
Out: when it runs, the WhatsApp stays in the customer's conversation in the inbox, as one sent from it, and
goes out through the business's number (`whatsapp_inbox.message.sent`); the same notice never sends it
twice.
If it fails: nothing goes out and the reason stays in the automation's history (FLOW-F16): a number that is
not in international format, with "+" and the country prefix (nothing is sent, so that it never reaches
another person), a number with no conversation in this business ("There is no WhatsApp conversation with …
in this business: nothing was sent."), more than 24 hours without a template, the WhatsApp number not
connected or the plan's messages of this month used up. A marketing template only reaches a customer who
has accepted it in Customers. What Meta refuses afterwards is seen in the inbox's conversation ("Not
delivered"). Without the WhatsApp inbox the button does not appear; by email it cannot be done yet (see "Qué
queda fuera").
Involved: FLOW-F11, FLOW-F12, FLOW-F16, FLOW-F32, WHATSAPP_INBOX-F23, WHATSAPP_INBOX-F33

### FLOW-F32 Put a photo, a video or a PDF at the top of a WhatsApp
Status: done
Actor: owner, administrator
Screen: Automation editor
Steps:
1. In a **Send a message** step (FLOW-F31), choose in "Template" one that carries a photo, a video or a
   document at the top: below it shows the file that goes with it and what WhatsApp takes ("JPEG or PNG, up
   to 5 MB.", "MP4, up to 16 MB." or "PDF, up to 25 MB.").
2. If the template already has its file (you made it in WhatsApp › Settings), its name and size show
   ("Photo: carta.jpg · 6.2 KB") and that one goes; to send another, press **Change file**.
3. If it does not (you made it in WhatsApp Manager), "No file chosen" shows with the notice "This template
   goes with a photo at the top: choose it, or WhatsApp will not send it.": press **Choose file** and pick one
   of the kind it asks for.
4. The file is kept at once in the business's files and the step names it. **Save**: when the automation is
   opened again, the step still names its file.
In: the approved template you choose and the file, of this business.
Out: when it runs, the WhatsApp reaches the customer with that file at the top and stays in their
conversation in the inbox, naming the file it went with (WHATSAPP_INBOX-F33). If you change the template, the
step lets go of the chosen file.
If it fails: a file of another kind or heavier than WhatsApp takes is said below and not uploaded ("Choose a
JPEG or PNG photo.", "This file weighs more than 5 MB: choose a lighter one."); if it cannot be kept, "The
file could not be uploaded. Try again.". If the file the step chose is no longer kept, it says so ("The file
this step had chosen is no longer kept: choose it again."); if it cannot be read right now, "The file of this
step could not be read." with **Retry**. Without a file, nothing goes out when it runs and the reason stays
in the automation's history (FLOW-F16); a file of another business is never sent.
Involved: FLOW-F11, FLOW-F16, FLOW-F31, WHATSAPP_INBOX-F29, WHATSAPP_INBOX-F33

### FLOW-F33 Turn on an automation another app brings
Status: done (server and screen)
Actor: owner, administrator, assistant
Screen: Automations
Steps:
1. Below the gallery, in **Comes with "Appointments"** (a section for each app that brings ready-made
   automations), tap a card: "This automation comes with Appointments.", what it does and "What it may do,
   and why", each permission with the sentence that app wrote.
2. Press **Turn it on** ("It starts working now, with only these permissions.").
3. ""…" is on." appears and the card changes to "Active", with **Pause it**, **See it** (opens the automation
   in the editor) and **Restore the factory one**.
4. If it was turned on before, **Turn it on** only turns it on again as you left it: with your name, your
   steps and your permissions. Only if it was left without any permission does it get its app's again.
In: the automations the business's active apps bring, in the language of whoever turns it on. Today: "Fill
the gap when a customer cancels" (Appointments: when a customer cancels their appointment, a high-priority
task to fill the gap; cancellations made by the team do not start it), "Check each booking made online"
(Online booking: when a customer books on the booking page, a task to check the appointment) and "Tell the
customer by WhatsApp when their appointment is confirmed" (WhatsApp inbox: when an appointment is confirmed,
a WhatsApp to the customer with the day, the time, the service and the professional, only to the
conversation of the exact number on their card; WHATSAPP_INBOX-F23).
Out: the first time, a new automation, on, with **exactly** the permissions its app asks for (not one more,
even if whoever turns it on can do more things), in the same operation (`flow.flow.created`,
`flow.flow.granted`, `flow.flow.enabled`): it is never left half on. Pressing twice, or two people at once,
is a single automation.
If it fails: if whoever turns it on cannot do something of what it asks themselves ("You cannot allow what
you may not do yourself: "…"."), nothing is created; one that asks for an app the business does not have
(even if only the assistant of an **Ask the assistant** step uses it) does not show in its section and the
line below says which is missing; the message in red inside the card.
Involved: FLOW-F04, FLOW-F12, FLOW-F21, FLOW-F34, FLOW-F35

### FLOW-F34 Pause an automation another app brings, without deleting it
Status: done (server and screen)
Actor: owner, administrator, assistant
Screen: Automations
Steps:
1. On its card in **Comes with …**, press **Pause it**.
2. ""…" is paused. Nothing was deleted." appears and the card changes to "Paused", with **Turn it on**.
3. In **Your automations** it looks the same, "Paused": pausing it from there is the same thing.
In: the automation that was set up from that card.
Out: paused (`flow.flow.paused`), with its permissions and its history; it stops starting like any other
paused one (FLOW-F03).
If it fails: one that was never turned on, or that was deleted: "This business has not turned that
automation on: there is nothing to change.".
Involved: FLOW-F03, FLOW-F33

### FLOW-F35 Restore the factory version of an automation another app brings
Status: done (server and screen)
Actor: owner, administrator, assistant
Screen: Automations
Steps:
1. If its app now brings a version different from the one that was turned on, the card carries "New
   version" and, when opened, "There is a new version of this automation.".
2. Press **Restore the factory one** (it also serves to undo your tweaks).
3. Confirm with **Restore** ("Your changes to this automation will be replaced by the version its app brings
   today. It stays on or paused as it is now.") or **Keep mine**.
4. "Done: this automation is the factory version again." appears and "New version" disappears.
In: the automation that was set up from that card and the version its app brings today.
Out: the same automation, with its history, with today's name, start, steps and **exactly** today's
permissions (`flow.flow.updated`, `flow.flow.granted`); on or paused as it was. Your tweaks do not mark it as
"New version": only a change by its app does.
If it fails: one that was never turned on, or that was deleted, "This business has not turned that
automation on: there is nothing to change."; if whoever restores cannot do something of what it asks
themselves, nothing changes.
Involved: FLOW-F33, FLOW-F36

### FLOW-F36 Repair a set-up automation with a fault its app already fixed
Status: done (server and screen)
Actor: the platform, owner, administrator, assistant
Screen: Automations
Steps:
1. You do not have to do anything: what its app fixed after you set it up reaches your automation by itself,
   even if you tweaked it, and without any notice above **Your automations**. The card in **Comes with …**
   still says "New version", as with any other change by its app (FLOW-F35).
2. If its app narrowed when it starts, it no longer starts in the cases its app left out: the WhatsApp reply
   set up before its app left out the old messages the inbox brings no longer answers any of them. When it is
   opened, its "Only when…" already says so.
3. If its app fixed a piece of data of its **Ask the assistant** step (FLOW-F37), that step already carries
   it: when opened it shows in its **Fixed data**, and the assistant does not see it nor can change it
   (FLOW-F38). That way, the WhatsApp reply set up before its app fixed the card of whoever writes does not
   cancel or change another person's reservation either, not even after **Approve**.
4. What its app sets is not removed from your automation: in the editor, that condition of the "Only when…"
   and that fixed piece of data say "Set by …: you can change it, not take it off.", with no × and no way to
   choose another piece of data. Your ways out: give it another value (yours counts), remove that query or
   action from **What it may use**, make it start with another notice, or make a copy (FLOW-F06), which is
   entirely yours.
In: the automations set up from a **Comes with …** card, whenever they were set up, whose "Only when…" lacks
what its app sets on it today while they start with the same notice, or that leave to the assistant a piece
of data its app fixes today in that step.
Out: what its app sets today, from the first moment and also in what was already under way: it counts when
deciding whether it starts, goes into what the assistant asks from then on and into a change that was
already waiting for your yes, whose card in **Waiting for your answer** says on whose behalf the yes will do
it. Only what you did not set: a condition you set on the same data and a piece of data you fixed keep
yours, and nothing else of the automation changes; one you made start with another notice gets no condition
from its app. If a fixed piece of data is left empty in a run, that query or action is not done (FLOW-F38).
It reads like this when opened and in **Try it**, and it is written down when you save it or make a copy
(FLOW-F06). A new version that only changes words changes nothing.
If it fails: if its app is no longer active, its automation cannot start with its notices either. A change
that leaves out what its app sets, or leaves empty a piece of data it fixes (asking the assistant or from
another program), is not saved, and nothing changes: next to "Only when…", ""…" puts a condition on "…":
give it another value, start it with something else or make a copy."; next to **Fixed data**, ""…" fixes "…"
of "…": give it another value, take "…" off what it may use or make a copy.".
Involved: FLOW-F06, FLOW-F13, FLOW-F21, FLOW-F29, FLOW-F33, FLOW-F35, FLOW-F37, FLOW-F38

### FLOW-F37 "Ask the assistant" step
Status: done
Actor: owner, administrator
Screen: Automation editor
Steps:
1. In **Steps**, press **Ask the assistant**. Its card opens.
2. In **What to ask it**, write the request ("Find a free slot tomorrow for" and, with **Insert data**, the
   notice's "Customer name"). The data you insert, from the notice or from the previous steps, are filled in
   at the moment of asking.
3. In **What it may use**, choose with **Add a read or an action** what the assistant will be able to look
   up or do (only those the assistant knows how to use show); × removes one. With none, it can only answer
   with words: "Nothing yet: it can only answer with words.". "Cancel a reservation" only shows with "Ask me
   first", and the card warns: "Only after a yes from someone who may do it themselves: "Cancel a
   reservation".".
4. If you want a query or an action to always receive a piece of data the assistant does not decide, in
   **Fixed data** choose with **Fix a datum** which one ("On behalf of the customer", of "Cancel a
   reservation") and fill it in, with **Insert data** if you want (the "Card" a previous step read). It shows
   as "Cancel a reservation › On behalf of the customer"; × removes it, and removing something from **What it
   may use** also removes its fixed data. One fixed by the app of the recipe you set it up from has no ×: it
   says "Set by …: you can change it, not take it off." (FLOW-F36). With none: "None: the assistant fills in
   every datum itself.". The card explains it: "The assistant never sees them nor can change them: they are
   filled in when it is asked, and a tool whose fixed datum is empty is not used.".
5. In **Changes**, choose "Ask me first" (by default) or "On its own". The card explains it: "A change it
   wants waits for a yes in Automations, under "Waiting for your answer". What it only looks up never waits."
   or "It makes the changes on its own, as this automation, with the permissions you gave it.".
6. Adjust **Most turns** (from 1 to 10; by default, 6) and, if you want, **More options** (FLOW-F25).
7. Press **Save** and, in **Permissions**, grant each query or action it may use (FLOW-F12).
In: the request, what it may use, its fixed data, how it makes changes and the turns.
Out: the step. The steps after it can insert "Text", what it answered, and, if a change waited for your
answer, "Approved", "Note" and "Answered by". **Try it** says "Would ask the assistant: …" with the request
filled in, without asking it, and each fixed piece of data with the value it would have, or what would not be
used because it is left empty (FLOW-F13). Each query or action it names starts asking for its permission.
If it fails: an empty request, more than 10 turns, or a request with a secret are not saved; nor is something
the business does not have, that needs a person in front or that the assistant cannot use ("The assistant
cannot use "…"."), next to **What it may use**. With "Cancel a reservation" in and "On its own", neither:
""…" needs a person's yes first: choose "Ask me first".". Next to **Fixed data**, a fixed piece of data of
something it cannot use is not saved (""…" has fixed data but the assistant may not use it: add it to what it
may use or remove its fixed data."), nor one that query or action does not have (""…" is no datum of "…"."),
nor one without a value ("Give "…" of "…" a value, or remove it."), nor one that reads a secret or a later
step, like the request. Nor one its app fixes, left without a value or removed (FLOW-F36).
Involved: FLOW-F11, FLOW-F12, FLOW-F13, FLOW-F17, FLOW-F25, FLOW-F29, FLOW-F38, FLOW-F39

### FLOW-F38 The assistant does its step inside an automation
Status: done
Actor: the platform, assistant
Screen: none (it is seen in History)
Steps:
1. A run reaches an **Ask the assistant** step. **Run now** answers at once: "It ran and the assistant is on
   it: see it in History."; the history says "Asked the assistant; it answers in a moment.".
2. The Hub asks the assistant in the background, with nobody in front, with the request already filled in and
   only what the step names **and** the automation has been granted; never with a person's permissions. The
   step's fixed data (FLOW-F37) are not shown to it: they are filled in with the run's data, like the request,
   and go into each query or action that carries them, over whatever the assistant sends for them or even if
   it sends nothing. That way, the WhatsApp reply only cancels or changes the reservation of whoever writes,
   even if it is asked for another person's. In an automation another app brings, also those its app fixed
   after it was set up (FLOW-F36).
3. What the assistant looks up is done on the spot and nobody is asked; the history says "The assistant used
   "…".".
4. What it wants to change:
   - with "Ask me first", it is not done: it waits in **Waiting for your answer** as "The assistant wants to
     change something in "…"", with what it wants to do right below ("Cancel a reservation"), what it said and
     the data it would send, said in words and in the language of whoever opens it as on the chat's card
     (FLOW-F29), and the run stops there ("The assistant wants to "…": it waits for a yes until …."). It
     waits for one change at a time: if it asks for several at once, those behind the first are not done. A
     yes does it at that moment, as the automation, and the step goes back to the assistant with what
     happened (the change done, or what the action did not accept, and that the others were not done), so
     that it tells it or asks for the next one, which again waits for its yes; the run does not carry on
     until it answers without asking for anything. That return does not spend another message if the yes
     comes within 15 minutes; later it counts as a first turn (a message of the month, FLOW-F39). A no, or
     nobody answering in 72 hours, cancels the run without doing anything, and the history says the action
     that was not done ("Cancelled: Marta answered no to "Cancel a reservation".", FLOW-F29, F30). "Cancel a
     reservation" is only approved by someone who can also cancel reservations: anyone else is told "Only
     someone who may do it themselves can say yes to "Cancel a reservation"." and the question keeps waiting;
   - with "On its own", it is done on the spot, as the automation, with the same checks as its button on the
     screen; if it asks for several at once, they are all done and it gets back what happened with each one.
     Cancelling a reservation is never offered to it this way.
5. When it answers without asking for anything else, the history says "The assistant answered: "…"" and the
   run carries on with the steps after it.
In: the request, what the step names and the automation has been granted, and the run's data.
Out: what it answered in the end, after the changes, for the steps after it and in the history; with "Ask me
first", also the person's last answer. What it looks up or changes notifies as if the automation did it.
If it fails: what you have not granted it is not offered to it and, if it asks for it, it is not done; what
the action refuses ("The assistant tried "…", which did not take it.") is told to the assistant so that it
tells it. If a fixed piece of data is left empty in that run (the card was not found), that query or action
is not done nor waits for a yes: the assistant knows, to tell it, and the history says "The assistant tried
"…", but "…", fixed by this step, was empty: it was not done.". If it reaches the limit of turns without
finishing, it stops: "The assistant took its … turns without finishing, so it stopped.". If erplora.com does
not answer or fails, it tries three times in total (after one second and after three seconds) without
repeating anything of the business and, if it stays the same, it stops with the reason ("The assistant could
not answer now…", "It could not reach the assistant on erplora.com…"); the month's messages used up, or a
business that does not work, are not retried ("The assistant's messages of this month are spent…"). All of
them can be resumed (FLOW-F24) or carry on with "If it fails, it carries on" (FLOW-F25). If the process falls
over while it thinks, it asks again after 5 minutes, from what it had already done. If someone says yes when
the action is no longer granted, it is not done, and the notice names it as the history does: ""…" is no
longer allowed or available, so the assistant's change was not made."; if the action no longer exists, "That
action is no longer allowed or available, so the assistant's change was not made.".
Involved: FLOW-F16, FLOW-F24, FLOW-F25, FLOW-F29, FLOW-F30, FLOW-F37, FLOW-F39

### FLOW-F39 The SaaS serves an automation's AI step
Status: done
Actor: the platform
Screen: none
Steps:
1. Each time the step needs the assistant, the Hub calls erplora.com with the business's key, with no person
   in front, just like a chat turn that is not painted (on erplora.com, ASSISTANT-F13): there is no separate
   door.
2. erplora.com spends the same messages of the month as the chat: the first turn of each step, one; the turns
   that bring back what it looked up or did within the next 15 minutes, none (after that time, for example
   after waiting for a person's yes, the turn counts one).
3. It answers what the assistant says and what it wants to look up or do, and keeps nothing of the
   conversation.
In: the request, what the step may use and, in the following turns, what has already been said.
Out: the answer for the Hub and the business's spending of the month (`assistant.message.claimed`, on
erplora.com's side).
If it fails: it says whether it is worth repeating: the provider down or an internal failure, yes; the
month's messages used up, a business that does not work or a request that does not fit, no. Automations and
the chat share the same allowance of the month.
Involved: FLOW-F37, FLOW-F38

## Services: what goes in and what comes out

Everything can be asked for through the screens, the assistant (by voice or by text, with the session of
whoever speaks) and the API, with the same rules and the same permissions, except saving a secret, which the
assistant does not do (its value is typed on the screen), and what only the platform does, which nobody asks
for. An automation is named by its id or by its name (or part of it); if a name fits several, it says which
(`flow.ambiguous_flow`).

Before changing anything, the assistant asks for confirmation with its card (BASE-F97), which names each
record as the Automations screens name it, never by its code: an automation and a draft, by their name; a
run, by its automation and when it started, as History does ("Welcome · 15 Oct 2026, 21:00"); a question, by
what it asks. A record the person confirming cannot see (a run, for whoever only answers questions; a
question asked of another role) does not show on the card.

### What it offers: queries (they read, they change nothing)

| What it gives | Who may | Flows | Service |
|---|---|---|---|
| The automations, with search, filters, order and their last run, in pages of up to 100 (live) | see | F02 | `flow.flow.list` |
| An automation, with the permissions it needs and those it lacks (live) | see | F09–F16 | `flow.flow.detail` |
| An automation's runs, 20 at a time, and how many failed (live) | see | F16 | `flow.run.list` |
| A run, with the words it is named with (its automation and when it started) | see | F24 | `flow.run.get` |
| The assistant's pending drafts (live) | see | F18, F19 | `flow.draft.list` |
| An assistant's draft, whether pending, used or discarded | see | F18, F19 | `flow.draft.get` |
| The notices and actions of the active apps, with the data each action asks for | see | F10, F11 | `flow.catalog.read` |
| The last real notice of a kind, with its data | manage | F11, F13 | `flow.event.sample` |
| What an automation would do with the last real notice, without running anything | manage | F13 | `flow.flow.test` |
| How many automations of a notice can do an action, how many are on and how many are half set up | see | F20 | `flow.flow.status` |
| The names of the business's secrets, never their value, and whether the server can keep them (live) | manage | F26 | `flow.secret.list` |
| The questions this person is waiting to answer, those that expire first at the top, up to 100, and of each change by the assistant its action and its data in words, read as that person and in their language (live) | answer | F29, F38 | `flow.question.list` |
| A question waiting for an answer, as it shows in "Waiting for your answer", only for whoever can answer it | answer (their role) | F29 | `flow.question.get` |
| The ready-made automations the active apps bring, with what they do, their permissions and why, and the one set up from each (on, "New version", what it would repair); and those the business cannot use, with their reason (live) | see | F33–F36 | `flow.recipe.list` |

### What it offers: actions (they change data)

| What it does | Who may | Flows | Service |
|---|---|---|---|
| Creates an automation (from scratch, from a card or from a draft), paused and without permissions | manage | F04, F09, F18 | `flow.flow.create` |
| Changes the name, the trigger or the steps (the switch is `set_enabled`); it does not let what its recipe's app fixes be removed (`flow.recipe_fixed`) | manage | F10, F11, F14, F36 | `flow.flow.update` |
| Turns on or pauses | manage | F03, F14 | `flow.flow.set_enabled` |
| Makes a copy, paused and without permissions | manage | F06 | `flow.flow.duplicate` |
| Deletes (its history stays) | manage | F07 | `flow.flow.delete` |
| Sets the whole list of actions and queries it can do | manage | F12 | `flow.flow.grant` |
| Runs it now | manage | F15 | `flow.flow.run` |
| Leaves an assistant's draft | manage | F17 | `flow.draft.propose` |
| Discards a draft | manage | F19 | `flow.draft.dismiss` |
| Starts the automations of a notice | only the platform | F21 | `flow.run.react` |
| Starts the scheduled or dated ones that are due | only the platform | F22 | `flow.schedule.fire_due` |
| Carries on the runs whose wait is over | only the platform | F23 | `flow.run.resume_due` |
| Resumes a run stopped by an error at the step that failed | manage | F24 | `flow.run.retry` |
| Saves (or changes) a secret, sealed | manage (never the assistant) | F26 | `flow.secret.set` |
| Deletes a secret | manage | F26 | `flow.secret.delete` |
| Makes, in the background, the call of a run that is waiting for it | only the platform | F27 | `flow.run.call` |
| Takes a run's call to make it | only the platform | F27 | `flow.run.claim_call` |
| Writes down how the call ended and carries the run on | only the platform | F27 | `flow.run.record_call` |
| Answers yes or no, with a note, to an automation's question | answer (their role) | F29 | `flow.question.answer` |
| Closes the questions nobody answered in time | only the platform | F30 | `flow.question.expire_due` |
| Turns on an automation another app brings: the first time it creates it on with exactly its permissions; afterwards it only turns it on | manage | F33 | `flow.recipe.enable` |
| Pauses it, without deleting it | manage | F34 | `flow.recipe.disable` |
| Gives it back the version its app brings today, with its permissions, on or paused as it is | manage | F35 | `flow.recipe.restore` |
| Writes down what its app fixed for it, which already counts: what its "Only when…" lacks and the fixed data of its assistant step (no screen: there is nothing to wait for from the owner) | manage | F36 | `flow.recipe.repair` |

### What it notifies

| Notice | When | What it carries | Service |
|---|---|---|---|
| New automation | Creating or copying | `id` | `flow.flow.created` |
| Automation changed | Saving name, trigger or steps | `id`, `version` | `flow.flow.updated` |
| On | Turning it on | `id` | `flow.flow.enabled` |
| Paused | Pausing it | `id` | `flow.flow.paused` |
| Permissions changed | Granting or withdrawing | `id` | `flow.flow.granted` |
| Deleted | Deleting it | `id` | `flow.flow.deleted` |
| Run started | A run starts | `id`, `flow_id` | `flow.run.started` |
| Run waiting | It reaches a "Wait", a "Call another system" or an "Ask someone first" | `id`, `flow_id`, `resume_at` | `flow.run.parked` |
| Run resumed | The wait ends or it is resumed from the step that failed | `id`, `flow_id` | `flow.run.resumed` |
| Run finished | It finishes well, by a condition, by an error or cancelled | `id`, `flow_id`, `status` | `flow.run.finished` |
| Draft proposed | The assistant leaves a draft | `id` | `flow.draft.proposed` |
| Draft used | The automation is created from it | `id`, `flow_id` | `flow.draft.used` |
| Draft discarded | It is discarded | `id` | `flow.draft.dismissed` |
| Secret saved | Saving or changing a secret | `id` | `flow.secret.saved` |
| Secret deleted | Deleting it | `id` | `flow.secret.deleted` |
| Question asked | A run reaches "Ask someone first" | `id`, `run_id`, `flow_id` | `flow.question.asked` |
| Question answered | Someone answers yes or no | `id`, `run_id` | `flow.question.answered` |
| Question expired | Nobody answered it in time | `id`, `run_id` | `flow.question.expired` |

Notices carry ids, never names or contents.

### What it reacts to and what it needs from other apps
- **To all the notices of the active apps** (FLOW-F21), except its own: it is the only app that listens to
  any notice. It does other apps' actions and queries **by their name** (`task.task.create`), with their
  rules and their messages, never touching their data; that is why it needs no app (`requires` empty): an
  automation that names an app that is off fails with its reason, visible.
- **"Send a message"** (FLOW-F31) is an action of the WhatsApp inbox, `whatsapp_inbox.message.notify`, the
  only sending one an automation can have: only to the live conversation of the exact international number,
  text within the 24 hours and an approved template outside them, with the month's limit; it goes out the
  same way as what is sent from the inbox. The inbox's own send (`whatsapp_inbox.message.send`, to any
  number) still needs a person in front. The "Template" offers those the inbox can fill
  (`whatsapp_inbox.template.list` with `fillable`); the file of a header with a photo, a video or a document
  (FLOW-F32) is kept by the inbox in the business's files (`whatsapp_inbox.template_sample.upload`, with the
  reply permission of whoever edits) and the step keeps only its id (`template.header_sample`), which it reads
  when it opens (`whatsapp_inbox.template_sample.detail`); when it runs, the inbox only sends a file of this
  business.
- **To its own `flow.run.parked`**: when a run waits for "Call another system", the worker makes the call
  (`flow.run.call`, FLOW-F27); never the request that left it waiting.
- From the platform: the business's time zone (the schedules) and the outbox's notices (the last one of a
  kind, for Try it and the examples).

### Who may do what

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| See the automations, their runs and the drafts | yes | yes | no | no | `flow.view` |
| Create, change, turn on, grant, run, delete; try; decide drafts; answer what is asked of whoever runs the business | yes | yes | no | no | `flow.manage` |
| See "Waiting for your answer" and answer what is asked of employees | yes | yes | yes | yes | `flow.answer` |
| Answer what is asked of managers | yes | yes | yes | no | `flow.answer_manager` |
