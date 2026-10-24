<!-- generated from WORKBOOK.md sha256:b7ae49ea46f01669bd12b58a08efd2245a839c9845096fef9b79e1c2e2ab9c67 -->

## What it is for and who it is for

The Home is the first thing anyone in the business sees on coming in. At a glance:

- **Their apps**, to open the one they need without looking for it in any menu.
- **What the business still lacks** to work fully: each app says which step it needs and the list puts
  them together, in order and with what happens if they are not done; the one that stops invoicing goes
  first and in red.
- **The apps' panels**: figures, lists and charts that move by themselves when something changes in the
  business, without reloading.
- **The activity**: the latest sales.
- **Start with a template** of a business like theirs and, in "Settings", keep a copy of its data or load
  another business's.

Who uses it:

- The **owner** and the **administrator** see everything and are the ones who can complete the
  platform's steps ("Your apps", "Your team"), and in the bell they see the notices between apps that were
  not delivered.
- The **manager** and the **employee** see their apps, the steps that are theirs, the panels they may
  see and the activity. A step that only an administrator can complete is shown to them too, so they know
  why invoicing is not possible, but without a button.

## Reference adopted

It is the Home of ERPlora's old hub, the one businesses already use, with its structure: greeting and
date, app launcher, setup list with a progress bar, board of panels and the "Summary" and "Activity"
tabs. It follows what the market does: the "Setup guide" list of Shopify and Square (steps with their
button, the progress on top and what is done folded away), Odoo's app launcher, the board of panels that
each person picks and orders of Lightspeed and Toast, and the bell with counters of any back office.

## Before you start

- You come in with your ERPlora account; the Hub has no sign-in of its own. On a shared till, after that, each
  person enters with their PIN or their badge.
- What each person sees depends on their role in the business and on the apps the business has on.
- The apps declare their steps, their panels and their counters; the Home only puts them together. While
  an app does not declare its own, nothing of it shows in the list or on the board.
- The example app (Demo) shows in the menu, in "My apps" and with an example step, panel and counter on
  the Home only in development, in the tests and in a demo business: never in a customer's.

## Screens

### Home · Summary
On top, the business's name and "Today" with the long date; while the business has no name, a greeting
by the hour ("Good morning", "Good afternoon", "Good evening"). Below, in this order:

- **"Start with a business like yours"**, only for who administers the business and while the business has
  nothing a template brings: up to four templates with "Use this one", "See all templates" and "Not now".
- **"My apps"**: one tile per app, with its icon and its name; the ones opened most in this browser,
  first. On a phone, with six apps or more, the first four and "View all apps".
- **"Finish setting up your business"**: how many steps are done, a bar and the steps left, each with its
  icon, its explanation, a label ("Needed to invoice", "Important", "Recommended", "Done" or "Not
  available yet") and "Set up". Folded: five steps (two on a phone), with "View all" and "Show less".
  When nothing is left: "Your business is ready".
- **The board of panels**, with "Customize panel" (⋮) at the top right.

### Home · Activity
The table of the latest sales: "Date", "Sale", "Customer", "Method", "Amount" and "Status", with
"Search activity…", the filters funnel (method and status), the order, the cards view and "Columns". It
also opens with the Home's link ending in `#actividad`.

### The bell
At the top right, after "My apps". Its number adds up the pending notices; tapped, one row per notice
("Failed events (2)") that leads to its screen. With nothing: "All caught up. No notifications.".

### "Upgrade plan"
At the foot of the side menu, between the QR code and the brand. It opens this business's plan page on
erplora.com, in a new tab. Only in the browser: the installed app does not have it.

### The user menu
It opens by tapping the person, at the top of the side menu. First "Profile" and, on a shared till of a business
that asks for a PIN, "Switch user"; then, only if they entered with the account (never in a PIN session), "My
account" and "Report a problem", which open those pages on erplora.com (in a new tab; in the installed app, in
the device's browser); last "Theme" (light, dark or the system's) and "Sign out". The erplora.com ones also show
in the installed app: neither sells anything.

### The "You cannot issue invoices yet" strip
Over any screen while a step that stops invoicing is missing: "No ticket or invoice can be issued until
this is set up:" and each step with "Set up" (on the screen that sets it up, only its name). It does not
show on the Home's "Summary" (the list says the same a little further down); on "Activity", it does.

### Apps
From "Apps" in the side menu. Three tabs at the bottom: "My apps" (the apps the business has running), "Add
apps" (every ERPlora app) and "Paid" (the ones subscribed to separately). Each one, a table (or cards) with its
search, the filters funnel, the order and "Columns": "App" (icon and name), "Category" and "Status"; in "Add
apps" and "Paid", also "Description", "Price" and "Comes with". "Open" on the row of an app the person can open.

### The screen of an app that does not open
In the same address as the app's screen, the reason: "Subscription needed" or "This app is not available in
this business", with "Go to Apps" (and "Subscribe on erplora.com" for whoever runs the business, in the
browser).

### System · Plan and limits
From "System" in the side menu, the "Plan and limits" tab: "Your plan's limits" with "Within the limit" or
"Close to the limit", the "People" and "Devices" cards and where plans are managed.

### Settings · Data and backups
From "Settings" in the side menu, the "Data and backups" tab at the bottom, after "General" (the old hub's
other Settings tabs come with their flows). On top, a selector with "Import" (what opens), "Export" and "Reset";
the one chosen stays in the link, so it can be shared and Back leaves Settings.

- **Import**: "Choose what to load", with "Upload from file" and the templates as cards or as a list, with
  "Search templates"; each with its language, its country, its version, what it brings and "Use template".
  Then "Review what it brings" and the "Import report".
- **Export**: the file's name and language, "What is this file for?", the apps with their "App" and "Data"
  boxes, and "Export".
- **Reset**: "Undo an import", with one row per import that can be undone, and "Reset the business", with
  what each section has.

### Access
The way in of a shared till, or of a device whose session another entry closed, with no menu or bar: the logo,
"Enter your business", the notice of what happened if there is one and a card with two tabs, "PIN" (the faces,
the keypad and the badge) and "Account" ("Enter with your account", which leads to erplora.com). In the footer,
"ERPlora · trusted device"; at the top right, the switch between light and dark.

### Create your PIN
After entering with the account on a till: the keypad of circles to choose the PIN and repeat it, and "Not now".

### Switch user
Over the screen in use, with no menu: "The sale stays open. From now on it is in the name of whoever enters
here.", "Who is taking over?" with the faces, the keypad and "Cancel".

### My profile
From "Profile" in the user menu. At the top, the person (face, name and role); below, "Account details" (with the
photo), "Preferences" (language and appearance) and "PIN".

### Settings · General
What "Settings" in the side menu opens: the first tab at the bottom, "General", with "This device", "PIN pad"
and, for whoever runs the business, "Devices".

### Your business is being prepared
The page that shows at the address of a business erplora.com is still preparing; it refreshes by itself.

## States of each screen

| State | What the person sees |
|---|---|
| Loading | Grey tiles in "My apps" ("Loading your apps…" for the screen reader), the list in grey, "Loading widgets…" on the board, each panel's figure in grey and "Loading…" in "Activity"; "Loading…" on the PIN pad, "Loading your profile…" and "Loading the devices…". |
| Empty | "Your apps will show up here. Add the ones your business needs."; with no steps, the list does not show; "Empty panel. Tap ⋮ to add widgets."; a panel without data, "No data"; the bell, "All caught up. No notifications."; "Nobody has entered from any device yet."; in "Switch user", "Nobody here has a PIN yet: give one in My profile or in Employees.". |
| Error | Each zone fails on its own: "Could not load your apps. Reload the page; if it keeps failing, sign in again.", "Could not load what is left to set up" with "Retry", "Could not load the panels" with "Retry", a panel with "Unavailable" (never the figure it had), "Could not load the latest sales" with "Retry" and, in the bell, "Could not check the notifications. They will show up when the connection is back.". In the way in: "Could not load the PIN pad. You can still enter with your account.", "Could not load the profile" with "Retry", "Could not load this device. Check the connection and try again.", "Could not load how the business asks for the PIN. Check the connection and try again." and "Could not load the devices. Check the connection and try again.". |
| No permission | A step the person cannot do: no button and "An administrator has to set this up.". A panel or a counter they may not see does not show. In Settings, whoever does not run the business sees "This device" and "PIN pad" with the controls off ("Only an administrator can change how people enter on this device.", "Only an administrator can change whether it asks.") and, instead of the list, "Only an administrator can see and remove the devices.". |

On the Settings · Data and backups screen:

| State | What the person sees |
|---|---|
| Loading | "Loading templates…"; in "Export" and "Reset", the rows in grey. |
| Empty | "There are no templates for your business yet.", "No template matches your search.", "This business has no app on to export." and "There is nothing to reset: no section has data.". |
| Error | "The templates could not be loaded right now. You can still import a file." with "Retry"; "The apps of this business could not be loaded." and "What each section has could not be worked out.", with "Retry". |
| No permission | "Only an administrator can see and import templates.", "Only an administrator can export the business." and "Only an administrator can undo imports or reset the business."; the Home's templates card does not show. |

## Flows

| ID | Flow | Status |
|---|---|---|
| BASE-F01 | See what the business still has to set up | done |
| BASE-F02 | See the business at a glance on coming in | partial |
| BASE-F03 | Go and set up from the "Set up your business" panel | partial |
| BASE-F04 | See which steps of the list an administrator has to set up | done |
| BASE-F05 | Open an app from "My apps" | partial |
| BASE-F06 | See the apps' panels on the Home | done |
| BASE-F07 | Customize the board of panels | done |
| BASE-F08 | Keep the panels up to date without reloading | done |
| BASE-F09 | Look at the recent activity | done |
| BASE-F10 | See in the bell the notices between apps that were not delivered | partial |
| BASE-F11 | Go to erplora.com to manage or upgrade the plan | partial |
| BASE-F12 | Ask the assistant to go over the setup | partial |
| BASE-F13 | Lose access on a role change or on leaving the business | done |
| BASE-F14 | See the business's apps | done |
| BASE-F15 | Open an app from Apps | done |
| BASE-F16 | Look for an app in the catalogue | done |
| BASE-F17 | Know how much an app costs before having it | done |
| BASE-F18 | Install an app | partial |
| BASE-F19 | Know what else comes with an app | partial |
| BASE-F20 | Try to use an app that needs a subscription | done |
| BASE-F21 | See why an app could not be turned on and try again | partial |
| BASE-F22 | Follow an app being turned on while moving around | partial |
| BASE-F23 | Turn an app off | partial |
| BASE-F24 | Turn an app on | partial |
| BASE-F25 | See an app refuse to be turned off | partial |
| BASE-F26 | Understand why an app does not open | done |
| BASE-F27 | See a paid app blocked | done |
| BASE-F28 | See how much of the plan's limits is in use | done |
| BASE-F29 | Choose a template of the catalogue to import | done |
| BASE-F30 | Upload a file to import | done |
| BASE-F31 | Review and load what the file brings | done |
| BASE-F32 | Read the import report | done |
| BASE-F33 | Come back to the report of an import that did not go in whole and retry | done |
| BASE-F34 | Undo an import | done |
| BASE-F35 | Export a backup or a template | done |
| BASE-F36 | Choose which apps, data and tables travel in the export | done |
| BASE-F37 | Reset the business by sections | partial |
| BASE-F38 | See the Home up to date after importing a template | done |
| BASE-F39 | Enter with the erplora.com account | done |
| BASE-F40 | Enter from the erplora.com panel without typing the password again | done |
| BASE-F41 | Choose the PIN the first time one enters a till | done |
| BASE-F42 | Enter with a PIN | done |
| BASE-F43 | Enter by passing the badge | done |
| BASE-F44 | Lose the session because it was opened on another device | done |
| BASE-F45 | The session ends while working | done |
| BASE-F46 | Close the session of a till nobody touches | done |
| BASE-F47 | Switch user without losing the sale | done |
| BASE-F48 | Sign out | done |
| BASE-F49 | Decide whether this device is shared or personal | done |
| BASE-F50 | Open a hub that is not set up yet | done |
| BASE-F51 | Change my details, photo, language and appearance | done |
| BASE-F52 | Change my PIN from My profile | done |
| BASE-F53 | Choose how many digits the business's PIN has | done |
| BASE-F54 | Decide whether the till asks for a PIN and when it asks again | done |
| BASE-F55 | See the devices someone has entered on | done |
| BASE-F56 | Name a device | done |
| BASE-F57 | Remove a device that was lost | done |
| BASE-F58 | Remove at once the devices nobody uses | done |

### BASE-F01 See what the business still has to set up
Status: done
Actor: owner, administrator, manager, employee
Screen: Home · Summary
Steps:
  1. They come into the Home. In "Finish setting up your business" they see how many steps are done and a
     bar.
  2. Below, the steps left, in the order the apps set: first the ones that stop invoicing ("Needed to
     invoice", in red), then the "Important" ones and last the "Recommended" ones.
  3. The platform's are "Your apps" (turn on at least one business app) and "Your team" (add the people
     who will use the till); the rest come from each app that is on.
  4. A step that only applies to another country, or that the person may not see, does not show. A step
     whose check fails does not show either: what could not be checked is never taken as done nor as
     pending.
  5. While a "Needed to invoice" step is missing, the "You cannot issue invoices yet" strip shows over the
     other screens.
  6. When someone else completes a step on another device, the list updates by itself.
In: the steps each app that is on declares, with their check, their country, their permission and their
screen.
Out: nothing saved.
If it fails: "Could not load what is left to set up" with "Retry". A step that is on us (there is no
business app to turn on) shows as "Not available yet" with "This one is on us: there is nothing on your
side to do yet. We are on it.".
Involved: INVENTORY-F28

### BASE-F02 See the business at a glance on coming in
Status: partial — without the hub's health row (the printer and WhatsApp with "View system")
Actor: owner, administrator, manager, employee
Screen: Home · Summary
Steps:
  1. After coming in, the Home opens (also from "Home" in the side menu).
  2. On top, the business's name (the one on erplora.com) and "Today" with the long date in the app's
     language; while the business has no name, "Good morning", "Good afternoon" or "Good evening".
  3. Below, in this order: "Start with a business like yours" (only while the business is empty and for
     who administers it, BASE-F38), "My apps", "Finish setting up your business" and the board of
     panels.
  4. At the bottom, two tabs: "Summary" (the above) and "Activity".
In: the business's name and the device's date.
Out: nothing saved.
If it fails: a zone that does not load does not bring the others down; each one says its own. On a phone
the zones stack and "My apps" folds.
Involved: none

### BASE-F03 Go and set up from the "Set up your business" panel
Status: partial — each step's "Set up" in the list already leads to its screen; the "Set up your business" panel and its destination (Settings › Data and backups) come with the templates
Actor: owner, administrator, manager
Screen: Home · Summary
Steps:
  1. In "Finish setting up your business", a pending step the person can do carries "Set up".
  2. They tap "Set up": the screen of the app that completes that step opens.
  3. Back on the Home, the list already counts the step as done if it was completed.
In: the screen each step declares.
Out: nothing from here.
If it fails: while that screen does not exist in the hub, the step shows without "Set up" (a button that
leads to "not found" is worse than none).
Involved: none

### BASE-F04 See which steps of the list an administrator has to set up
Status: done
Actor: manager, employee
Screen: Home · Summary
Steps:
  1. A step that stops invoicing and that this person cannot do stays on their list and on the strip,
     with its "Needed to invoice" label.
  2. It carries no "Set up": it says "An administrator has to set this up.".
  3. The steps that do not stop invoicing and that this person cannot do do not show on their list.
In: the person's permissions in this business.
Out: nothing.
If it fails: if that step cannot be checked, it does not show.
Involved: none

### BASE-F05 Open an app from "My apps"
Status: partial — "Add apps" shows as soon as the hub has the Apps screen
Actor: owner, administrator, manager, employee
Screen: Home · Summary
Steps:
  1. In "My apps", one tile per app this person can open, with its icon and its name (if it does not
     fit, the whole name shows on hover).
  2. The ones opened most in this browser go first.
  3. They tap a tile: the app opens. An app that is being turned on says "Activating…" and opens nothing.
  4. On a phone, with six apps or more, the first four show and "View all apps", which shows the rest.
     "Add apps", the last one, leads to Apps.
In: the apps of the person's menu (the same as the bar's "My apps" button).
Out: how many times each app is opened in this browser (only to order them).
If it fails: while loading, grey tiles and "Loading your apps…" for the screen reader. Without apps:
"Your apps will show up here. Add the ones your business needs.". If the list could not be read: "Could
not load your apps. Reload the page; if it keeps failing, sign in again.", never that there are no apps.
Involved: none

### BASE-F06 See the apps' panels on the Home
Status: done
Actor: owner, administrator, manager, employee
Screen: Home · Summary
Steps:
  1. Under the list is the board ("Loading widgets…" while it comes).
  2. Each panel is a card with its title and icon: a figure (with what it counts under it, if its app says
     so), a list with bars, a timeline, a chart or a piece of its app's screen, with its texts in the language
     of whoever is looking.
  3. In a chart of days, each bar has its weekday under it (or its date, if it spans more than a week) and
     above them show the day and its amount: the last bar's until you tap another.
  4. In a timeline, each entry says when it happened, in the device's time: only the time if it was today
     (9:15 AM); if it was yesterday, Yesterday in front (Yesterday 6:10 PM); if not, the short date with the
     time (Oct 20, 6:10 PM), with the year if it is another. Holding the pointer over it shows the whole
     date. With the Home open, today's become yesterday's when the day changes.
  5. At first, the ones each app marks as recommended for the business's sector show.
  6. Only the panels of the apps that are on and that this person may see show.
In: the panels each app that is on declares; each one's data, asked for with the permissions of whoever
is looking.
Out: nothing saved in the hub.
If it fails: a panel without data says "No data"; one whose data cannot be read, "Unavailable", never an
old or made-up figure. If the board cannot be read: "Could not load the panels" with "Retry".
Involved: none

### BASE-F07 Customize the board of panels
Status: done
Actor: owner, administrator, manager, employee
Screen: Home · Summary
Steps:
  1. They tap ⋮ ("Customize panel") over the board.
  2. In "Start from a preset", "Recommended" goes back to the recommended panels.
  3. In "Active · drag to reorder" they order or remove; in "Available" they add.
  4. "Close" leaves the board as it is.
In: the panels this person may put.
Out: the chosen board, kept in this browser: the people who use this device share it and it does not
travel to another one.
If it fails: a kept panel whose app was turned off disappears from the board without notice. Without any
app offering panels: "No installed app offers widgets yet.".
Involved: none

### BASE-F08 Keep the panels up to date without reloading
Status: done
Actor: system
Screen: Home · Summary
Steps:
  1. Each panel says which notices of its app change it (a sale, a cash movement, a count).
  2. When one of those notices happens on any device of the business, the panel gets its new data by
     itself, without emptying meanwhile.
  3. A panel whose data is not followed live is painted once on coming in and does not move until the
     Home is loaded again.
In: the business notices each panel declares.
Out: nothing saved.
If it fails: if the new data does not come, the panel says "Unavailable", not the value it had; when the
connection is back, it updates by itself.
Involved: none

### BASE-F09 Look at the recent activity
Status: done
Actor: owner, administrator, manager, employee
Screen: Home · Activity
Steps:
  1. On the Home, the "Activity" tab.
  2. "Loading…" and then a table with the last 100 sales: "Date" (with the time), "Sale", "Customer",
     "Method", "Amount" (in euros: 1.50 € shows "€1.50") and "Status", with the words of the Sales
     history: "Completed" in green, "Voided" in red, "Refunded" in amber and "Other" in grey for a status
     this screen does not know yet.
  3. They search with "Search activity…" (sale, customer or method), filter by method or status, sort,
     switch to cards or pick columns; 15 per page.
  4. A sale charged on another device shows up by itself, without reloading.
In: the sales of the Sales app, if it is on, with the permissions of whoever is looking. Only sales: the
business's other movements do not show here.
Out: nothing saved.
If it fails: without the Sales app, the empty table. If the sales cannot be read: "Could not load the
latest sales" — "Check the connection and try again." with "Retry", instead of the table; if there were
already sales on screen, they stay under the notice.
Involved: SALE-F28

### BASE-F10 See in the bell the notices between apps that were not delivered
Status: partial — the row does not lead anywhere yet: the System screen, where they are resent or discarded, comes later
Actor: owner, administrator
Screen: The bell
Steps:
  1. A notice between apps (for example, "sale charged" towards Invoicing) ran out of retries.
  2. An administrator's bell goes up at once, without waiting or reloading, and opened it shows "Failed
     events" with how many there are.
  3. When none is left, the row disappears.
In: how many notices of this business were left undelivered, only for whoever runs the business.
Out: nothing.
If it fails: an employee or a manager does not see the row. If it cannot ask, the bell keeps what it
last knew; if it never knew: "Could not check the notifications. They will show up when the connection is
back.".
Involved: none

### BASE-F11 Go to erplora.com to manage or upgrade the plan
Status: partial — a plain link, without the one-time pass, only in the browser (not in the installed app) and without the bar's "erplora.com" button
Actor: owner, administrator, manager, employee
Screen: Side menu
Steps:
  1. At the foot of the side menu, under the QR code and lined up with it, is "Upgrade plan". Any profile
     sees it; what can be done on arriving is decided by erplora.com according to who comes in. With the
     menu folded to its icons (desktop), only its icon stays, which says "Upgrade plan" on hover.
  2. They tap it: this business's plan page on erplora.com opens in a new tab.
In: the business they are in.
Out: nothing saved in the hub.
If it fails: if the hub does not know which business it belongs to, the button does not show (never a
button that does nothing).
Involved: none

### BASE-F12 Ask the assistant to go over the setup
Status: partial — the Hub does not have the assistant's chat yet: the list is already within the assistant's reach, but there is no "Ask the assistant" button
Actor: owner, administrator, manager, employee
Screen: Home · Summary
Steps:
  1. From the assistant, the person asks it to go over the business's setup.
  2. The assistant reads the same list as the Home, with what that person may see, and tells them what is
     missing and where it is done; each step keeps its "Set up" in the list.
In: the list of what is missing, with the permissions of whoever asks.
Out: nothing saved.
If it fails: without the assistant, the steps keep leading to their screen from the list.
Involved: none

### BASE-F13 Lose access on a role change or on leaving the business
Status: done
Actor: owner, administrator, manager, employee
Screen: any screen of the hub
Steps:
  1. At erplora.com, whoever manages the business changes a person's role, removes them from the business
     or hands the ownership over to them.
  2. At that moment that person's session in this business ends, on all their devices: what they have open
     stops updating and the next thing they do asks them to sign in again. Their sessions in other
     businesses stay open.
  3. If they are still in the business, they come back in from erplora.com and already work with their new
     role: what the new role allows appears and what it does not, disappears.
  4. If they were removed, on coming back erplora.com tells them "You don't have access to this hub" and
     they do not get in.
  5. If they change their password, sign out everywhere or delete their account at erplora.com, all their
     sessions of the hub end, in all their businesses.
In: the change erplora.com made (who, in which business and with which role, or that they are no longer
there).
Out: that person's sessions ended; their role in the business, up to date.
If it fails: if the hub does not answer at that moment, erplora.com tries again shortly; meanwhile, the
next time erplora.com passes the business's state to the hub those sessions end too.
Involved: HUBS-F26, HUBS-F27, HUBS-F28

### BASE-F14 See the business's apps
Status: done
Actor: owner, administrator, manager, employee
Screen: Apps
Steps:
  1. They tap "Apps" in the side menu. It opens on the "My apps" tab; "Add apps" and "Paid" have their own
     address too, which can be linked.
  2. While the list arrives: "Loading your apps…". Then one row (or one card, as chosen) for each app the
     business has running, with its icon and its name, its "Category" and its "Status" ("Active").
  3. They search in "Search your apps…" (name, description or category), filter by category with the funnel,
     sort or choose columns.
  4. When the business subscribes to an app on erplora.com or stops having it, the list updates by itself,
     without reloading.
In: the apps the hub brings and what the business has subscribed to on erplora.com.
Out: nothing saved.
If it fails: "We could not read your apps" — "There was no answer, or this session is no longer valid: sign in
again if it keeps happening." with "Retry"; the list there was stays below (a failure never says there are no
apps). With no app at all: "You have no apps yet. Open “Add apps” to see them all.".
Involved: none

### BASE-F15 Open an app from Apps
Status: done
Actor: owner, administrator, manager, employee
Screen: Apps
Steps:
  1. On the row of an app in "My apps", they tap "Open".
  2. The first screen of that app the person can see opens.
In: the app's menu and what the person can see.
Out: nothing saved.
If it fails: an app the person cannot open, or that is not running, has no "Open" (it does not show greyed
out: it does not show). On tapping, it is checked again, in case it just changed: if it is no longer running,
nothing opens.
Involved: none

### BASE-F16 Look for an app in the catalogue
Status: done
Actor: owner, administrator, manager, employee
Screen: Apps
Steps:
  1. In Apps, they tap "Add apps" (every ERPlora app) or "Paid" (only the ones subscribed to separately).
  2. While it arrives: "Loading the catalogue…". Then one row per app with "App", "Category", "Description",
     "Price", "Comes with" and "Status" ("Installed" or "Needs a subscription"), with the names and the
     descriptions in the language of whoever looks.
  3. They search in "Search apps to add…" (in "Paid", "Search paid apps…") by name, description or
     category, and filter by category or by status.
In: the apps the hub brings and what the business has subscribed to on erplora.com.
Out: nothing saved.
If it fails: as in "My apps" (BASE-F14). A search without results: "No apps match your search.".
Involved: APPS-F01

### BASE-F17 Know how much an app costs before having it
Status: done
Actor: owner, administrator, manager, employee
Screen: Apps
Steps:
  1. In "Add apps" or "Paid", the "Price" column says of each app: "Free" (it comes with any plan), "Included
     in your plan", "Subscribed", "Included with" and the app that brings it (a paid one that comes with
     another the business has) or "Paid".
  2. The amount of a "Paid" app is on erplora.com's Store; whoever runs the business opens it from "Subscribe
     on erplora.com" (BASE-F20).
  3. "Paid" gathers only the apps subscribed to separately: a free one never shows there. If none is sold
     separately: "No app is sold separately: every app comes with your plan.".
In: whether each app is subscribed to separately and what the business has subscribed to on erplora.com.
Out: nothing saved. The hub neither charges nor shows amounts: the price and the purchase are erplora.com's.
If it fails: without the list, as in "My apps" (BASE-F14).
Involved: APPS-F01, APPS-F07

### BASE-F18 Install an app
Status: partial — in this phase every ERPlora app already comes running in every business (the paid ones, as soon as they are subscribed to): turning an app on or off per business comes with the activation of apps
Actor: administrator
Screen: Apps
Steps:
  1. The free apps are already in "My apps" and in the menu; a paid one shows in both by itself, without
     reloading, as soon as it is subscribed to on erplora.com (BASE-F20).
  2. In "Add apps", whoever runs the business turns on an app the business does not use: while it is being
     prepared, the row says "Activating…"; then it becomes "Installed" and the app shows in "My apps" and in
     the menu.
In: the chosen app and what the business has subscribed to on erplora.com.
Out: the app running in this business.
If it fails: BASE-F21.
Involved: APPS-F07

### BASE-F19 Know what else comes with an app
Status: partial — Apps already says what each app brings and which app a paid one comes with; the notice on turning it on, which names what was turned on with it, comes with the activation of apps per business
Actor: administrator
Screen: Apps
Steps:
  1. In "Add apps", the "Comes with" column names the apps each one needs (for instance, "Sales & POS" comes
     with "Customers" and "Taxes"): whoever has one also has the ones it brings.
  2. A paid app the business has because another one it subscribed to needs it says "Included with" and the
     name of that other one under "Price".
  3. On turning on an app that needs others, the notice also names the ones turned on with it.
In: what each app needs.
Out: nothing saved.
If it fails: if a paid app brings another paid one that has not been subscribed to, the two are subscribed to
together: until then, "Needs a subscription".
Involved: none

### BASE-F20 Try to use an app that needs a subscription
Status: done
Actor: owner, administrator, manager, employee
Screen: Apps
Steps:
  1. A paid app the business has not subscribed to shows in "Add apps" and in "Paid" with "Needs a
     subscription", and is neither in "My apps" nor in the menu.
  2. Whoever runs the business, in the browser, sees "Subscribe on erplora.com" next to it, which opens this
     business's Store on erplora.com in a new tab: there they see the price and subscribe.
  3. As soon as erplora.com tells the hub, the app becomes "Installed" and shows in "My apps" and in the menu,
     without reloading.
  4. Whoever does not run the business, and anyone in the installed app, sees "Subscribed to on erplora.com,
     from your ERPlora account." and no button: the hub never sells.
In: what the business has subscribed to, as erplora.com passes it to the hub.
Out: nothing saved or charged in the hub.
If it fails: until erplora.com tells the hub, the app keeps "Needs a subscription"; a screen of it that is
opened says why (BASE-F27).
Involved: APPS-F07

### BASE-F21 See why an app could not be turned on and try again
Status: partial — in this phase every ERPlora app already comes running in every business (the paid ones, as soon as they are subscribed to): turning an app on or off per business comes with the activation of apps
Actor: administrator
Screen: Apps
Steps:
  1. Turning an app on does not finish: its data could not be prepared.
  2. Its row says it could not be turned on and offers "Retry", which asks for it again; meanwhile the app does
     not open.
In: the reason the hub gives.
Out: nothing; the app stays as it was.
If it fails: if it fails again, it says so again with its "Retry".
Involved: none

### BASE-F22 Follow an app being turned on while moving around
Status: partial — in this phase every ERPlora app already comes running in every business (the paid ones, as soon as they are subscribed to): turning an app on or off per business comes with the activation of apps
Actor: administrator
Screen: Apps
Steps:
  1. Whoever runs the business turns an app on (BASE-F18) and goes to another screen.
  2. The app shows "Activating…" in "My apps" and in the menu until it is ready; then it opens like any other,
     on every device of the business, without reloading.
In: how the activation is going.
Out: nothing saved.
If it fails: BASE-F21.
Involved: none

### BASE-F23 Turn an app off
Status: partial — in this phase every ERPlora app already comes running in every business (the paid ones, as soon as they are subscribed to): turning an app on or off per business comes with the activation of apps
Actor: administrator
Screen: Apps
Steps:
  1. In "My apps", whoever runs the business turns an app off.
  2. It asks, with the app's name, and names the apps that go off with it because they need it.
  3. They confirm: the app and the ones that need it leave the menu and "My apps". Nothing is deleted: on
     turning it on again it is as it was.
In: the business's apps and what each one needs.
Out: the app turned off in this business, with its data intact.
If it fails: BASE-F25.
Involved: VERIFACTU-F32

### BASE-F24 Turn an app on
Status: partial — in this phase every ERPlora app already comes running in every business (the paid ones, as soon as they are subscribed to): turning an app on or off per business comes with the activation of apps
Actor: administrator
Screen: Apps
Steps:
  1. In "Add apps", whoever runs the business turns on again an app they turned off.
  2. It asks and names the apps that are turned on with it because it needs them; they confirm and the app comes
     back to the menu with the data it had.
In: what the app needs and what the business has subscribed to.
Out: the app running in this business.
If it fails: a paid app not subscribed to cannot be turned on: BASE-F20.
Involved: none

### BASE-F25 See an app refuse to be turned off
Status: partial — in this phase every ERPlora app already comes running in every business (the paid ones, as soon as they are subscribed to): turning an app on or off per business comes with the activation of apps
Actor: administrator
Screen: Apps
Steps:
  1. Whoever runs the business tries to turn off an app another running one needs, or VeriFactu with records
     the AEAT has not accepted yet.
  2. The hub refuses, changes nothing and says why, with what has to be done first.
In: the reason of the app that refuses.
Out: nothing.
If it fails: without a reason of the app's own, a notice that it could not be changed.
Involved: VERIFACTU-F32

### BASE-F26 Understand why an app does not open
Status: done
Actor: owner, administrator, manager, employee
Screen: The screen of an app that does not open
Steps:
  1. They open a screen of an app (from a link, the history or a tab left open) that cannot be used in this
     business now.
  2. Instead of the app, in the same address, while it checks: "Checking why this app does not open…".
  3. Then, the reason: "Subscription needed" (BASE-F27), or "This app is not available in this business" —
     "Look for it in Apps, or open another one from the menu."; both with "Go to Apps".
In: what the business has of each app.
Out: nothing.
If it fails: "We could not check why this app does not open" — "Check the connection and try again." with
"Retry": never a made-up reason. An address that does not exist in the hub says it does not exist, like any
other. An app the person cannot see opens anyway and each screen says they have no permission.
Involved: none

### BASE-F27 See a paid app blocked
Status: done
Actor: owner, administrator, manager, employee
Screen: The screen of an app that does not open
Steps:
  1. The business stops having a paid app (its subscription on erplora.com ends) or someone opens one it has
     not subscribed to.
  2. On opening any of its screens they see "Subscription needed": the app's name and "is disabled because this
     business does not have its subscription. Your data is safe and comes back as soon as it is subscribed
     to.", with "Go to Apps" and, for whoever runs the business in the browser, "Subscribe on erplora.com".
  3. The app leaves the menu and "My apps", and the hub does nothing asked of that app, whether it comes from
     this screen, from another device, from the assistant or from an integration.
  4. If it is subscribed to with the screen open, it changes to the app's name with "is ready" — "It can be
     used now." and "Open" with its name, which opens it up to date.
In: what the business has subscribed to, as erplora.com passes it to the hub.
Out: nothing; the app's data is not touched.
If it fails: if nobody tells the hub when the subscribed period ends, the hub notices by itself when the date
passes. A demo business has every app, the paid ones too, to try them.
Involved: APPS-F07

### BASE-F28 See how much of the plan's limits is in use
Status: done
Actor: owner, administrator
Screen: System · Plan and limits
Steps:
  1. They tap "System" in the side menu: "Plan and limits" opens.
  2. They see "Your plan's limits" with "Within the limit" or "Close to the limit", the "People" card (the
     business's active people against the ones the plan allows, with its bar; or "No limit") and the
     "Devices" one: how many have a session open now ("With a session open now.") and, in its tag, "Up to" and
     the plan's limit, or "No limit".
  3. With every place taken: "You are running out of room in your plan" — "Your plan has every place taken, so
     you cannot add anyone else.", with no button.
  4. Below: "Plans are managed from your ERPlora account, on erplora.com.". It updates by itself when the plan
     or the people change; the devices' figure, on opening the screen.
In: the plan's limits erplora.com passes to the hub, the business's active people and the devices with a session
open on it (the same ones the cap of BASE-F44 counts).
Out: nothing saved.
If it fails: "We could not read your plan" — "Check the connection and try again." with "Retry". Whoever does
not run the business sees "Only whoever runs the business can see the plan and its limits.", without "Retry". While
the hub does not know the plan: "We do not know this business's plan yet: it shows up as soon as erplora.com
sends it.".
Involved: BASE-F44

### BASE-F29 Choose a template of the catalogue to import
Status: done
Actor: owner, administrator
Screen: Settings · Data and backups › Import
Steps:
  1. Open "Settings" in the side menu; in "Data and backups", "Import" is what opens. It says "Load a
     template: it fills your apps with its data — a menu, services, tables — ready to use." and, below,
     "Choose what to load".
  2. While they arrive, "Loading templates…". Then one card per template (or one row, in the list view):
     its name, its description, its "Language" and its "Country" by name, its "Version" and what "It brings"
     (how many categories, products, services, areas or tables). First those of the business's country and,
     among them, those in the person's language.
  3. "Search templates" searches by the name, the description or the apps it brings.
  4. Tap "Use template" on the one that fits: the button spins while it is read and "Review what it brings"
     opens (BASE-F31).
In: the Hub's templates, one per sector and language (today restaurant and hair salon, in Spanish and in
English).
Out: nothing saved until it is loaded.
If it fails: "The templates could not be loaded right now. You can still import a file." with "Retry";
with no templates, "There are no templates for your business yet."; a search with no result, "No template
matches your search."; if the template cannot be read, "The file could not be read: {reason}" and it stays
on the choice. Who does not administer the business reads "Only an administrator can see and import
templates.".
Involved: INVENTORY-F12

### BASE-F30 Upload a file to import
Status: done
Actor: owner, administrator
Screen: Settings · Data and backups › Import
Steps:
  1. In "Import", tap "Upload from file" and choose a .blueprint.zip: a backup of this business or a
     template another one exported.
  2. While it is read, the button spins. Then "Review what it brings" opens (BASE-F31).
  3. After an error the same file can be chosen again.
In: the file, of 5 MB at most.
Out: nothing saved until it is loaded.
If it fails: "The file could not be read: {reason}" with the reason (it is not a .blueprint.zip, it is
damaged, a newer version of ERPlora made it or it is larger than 5 MB) and it stays on the choice.
Involved: none

### BASE-F31 Review and load what the file brings
Status: done
Actor: owner, administrator
Screen: Settings · Data and backups › Import
Steps:
  1. After choosing a template or a file, "Review what it brings" shows: "Name", "Type" ("Template" or
     "Backup"), "Language" and "Country" by name, how many "Apps" and, for a file, when it was made
     ("Created").
  2. Below, one box per app with what it brings (each part and its rows). The ones on in the business come ticked;
     an app that is off says "This app is off in your business: nothing of it will load." and one this
     business does not have, "This business does not have this app: nothing of it will load.". A template's
     customers stay out: "Personal data: it loads only from a backup.". What the Hub never loads (people,
     PINs, fiscal data) shows in "Never loaded here".
  3. Untick the apps not wanted and tap "Import" ("Importing…"), or "Choose another" to go back.
  4. When it ends, the report shows (BASE-F32). What the business already had stays as it was: nothing is
     duplicated nor overwritten.
In: the template or the file and the apps ticked.
Out: in each app ticked, what it brings and was missing, added as if it were added by hand in that app (its
categories, products, services, areas, tables and, from a backup, customers), and the report kept
(`base.blueprint.imported`).
If it fails: "The import failed: {reason}" and it stays on the review; with no app ticked, "Choose at least
one app." and it cannot be imported; if none of its apps is on, "Nothing of this file can load in your
business: none of its apps is on.".
Involved: INVENTORY-F12

### BASE-F32 Read the import report
Status: done
Actor: owner, administrator
Screen: Settings · Data and backups › Import
Steps:
  1. When it ends, "Import report" with how it went: "Everything went in.", "Not everything went in." or
     "Nothing went in.".
  2. One row per app with its label: "Applied", "You had it already", "Applied in part", "Failed", "Nothing
     to copy", "Left out", "App off", "Not in this business" or "Not chosen". Below, for each part, "{created}
     created · {already} already there · {failed} failed" and, of what failed, its name and the reason.
  3. What was left out on purpose shows in "Left out on purpose".
  4. "See the templates" goes back to the catalogue; "Go to Home" leads to the Home.
In: the import's report.
Out: nothing; the report stays kept in the business.
If it fails: a label the screen does not know shows as "Failed" with its own text, never as a success.
Involved: none

### BASE-F33 Come back to the report of an import that did not go in whole and retry
Status: done
Actor: owner, administrator
Screen: Settings · Data and backups › Import
Steps:
  1. On opening "Import", if the last import did not go in whole and was not undone, its report shows first,
     with "This is the report of your last import of {name} ({date}). Not everything went in.".
  2. If it came from a template, tap "Retry what is missing" ("Retrying…"): the same version of the template
     is loaded again and only what was missing goes in; what already went in is neither touched nor
     duplicated. The new report shows.
  3. If it came from a file uploaded by hand, the button shows off with "This import came from a file
     uploaded by hand, so it cannot be retried by itself. Upload the file again and choose only what
     failed."; if that version of the template is gone, with "The version of the template this import used
     is no longer in the catalogue, so it was not retried: another version could load different data.".
  4. "See the templates" leaves that report and opens the catalogue.
In: the last import and its report.
Out: what was missing, if it goes in now, and the new report (`base.blueprint.imported`).
If it fails: "The retry failed: {reason}" and the report stays in sight.
Involved: none

### BASE-F34 Undo an import
Status: done
Actor: owner, administrator
Screen: Settings · Data and backups › Reset
Steps:
  1. In "Reset", "Undo an import" ("Removes only what that import brought. What you created afterwards
     stays."): one row per import that brought something and was not undone, with its name, when, who and
     how many rows it brought, and "Undo".
  2. Tap "Undo": "Undo «{name}»", with "The {n} rows this import brought will be removed. What you created
     afterwards stays.". It asks to type nothing: it can be imported again.
  3. Confirm with "Undo" (or "Cancel").
  4. "Import undone:" shows with one line per app ("{app} — {n} rows removed"); what could not be removed
     (something another app still uses) shows apart with its reason. What each section has gets up to date.
In: the import chosen.
Out: exactly the rows it brought removed; what was created afterwards stays (`base.import.undone`).
If it fails: the reason shows in the dialog itself, which does not close (the old hub said nothing); an
import already undone, "This load was undone already.".
Involved: none

### BASE-F35 Export a backup or a template
Status: done
Actor: owner, administrator
Screen: Settings · Data and backups › Export
Steps:
  1. Open "Export": "Packs this business's apps — and, if you want, their data — into a file you can load in
     another business or keep as a backup.".
  2. Write the "Name" (the business's comes in; without one, its address's) and choose the "Language"; below,
     the file's final name ("File: {file}").
  3. Answer "What is this file for?": "Backup of this business" (the one ticked; it takes the customers too)
     or "Template to share" (it never takes customers).
  4. Choose the apps and their data (BASE-F36) and tap "Export" ("Exporting…").
  5. The file downloads with the browser and "{file} downloaded." shows.
In: the name, the language, what it is for and what is ticked.
Out: a .blueprint.zip with the apps ticked and, of those that take their data, their rows; never people,
PINs nor fiscal data. Nothing is kept in the business.
If it fails: "The export failed: {reason}"; without a name, "Write a name for the file." and it cannot be
exported. Who does not administer the business reads "Only an administrator can export the business.".
Involved: none

### BASE-F36 Choose which apps, data and tables travel in the export
Status: done
Actor: owner, administrator
Screen: Settings · Data and backups › Export
Steps:
  1. In "Export", under "Apps" ("Choose which apps the file registers and whether their data travels with
     it."), one row per app on with two boxes, "App" and "Data". They all come with the app ticked and no
     data; an app with nothing of its own says "Nothing of its own to copy".
  2. Unticking the app unticks its data. "Select all" ticks every app and its data; "Deselect all" unticks
     them all.
  3. Ticking an app's "Data" shows "Data of {app}" below, with one box per part and its rows;
     unticking one leaves it out. In a template the customers cannot be ticked: "Only in a backup".
  4. While no part of an app is unticked, all of it travels, also what that app brings later on.
In: the apps on and how many rows each part has.
Out: nothing saved; what is ticked travels on export.
If it fails: "The apps of this business could not be loaded." with "Retry"; with no app ticked it cannot
be exported.
Involved: none

### BASE-F37 Reset the business by sections
Status: partial — while the business shares its database with other businesses it cannot be emptied: the screen says so and offers no button; it will be possible once each business has its own
Actor: owner, administrator
Screen: Settings · Data and backups › Reset
Steps:
  1. In "Reset", "Reset the business": "Removes for good the data you mark. It cannot be undone: if in
     doubt, export a copy first.", with "Export a copy first", which opens "Export".
  2. It says what is never removed: "Only what each section lists here is removed. Sales, invoices, fiscal
     records, people and their access, files and the business's settings always stay.".
  3. One row per section (an app) that has something, with what it has (each part and its rows) and its total.
  4. With its own database, tick the sections and tap "Reset the business": "This cannot be undone", with
     "{n} rows will be removed for good:" and the breakdown. Type the business's name ("Type «{name}» to
     confirm") and tap "Remove for good" (or "Cancel").
  5. "Business reset:" shows with one line per section ("{app} — {n} rows removed") and the list is worked
     out again.
  6. Today, with the shared database, "Resetting the business is not available yet. Undo an import instead, or
     remove what you want from each app." shows, with no boxes nor button.
In: what each section has and what is ticked.
Out: what is ticked, removed for good (`base.hub.data_reset`).
If it fails: the reason shows in the dialog, which does not close: a name that is not the business's, "The
name does not match.". Who does not administer the business reads "Only an administrator can undo imports
or reset the business.".
Involved: none

### BASE-F38 See the Home up to date after importing a template
Status: done
Actor: owner, administrator
Screen: Home · Summary
Steps:
  1. While the business has nothing a template brings, who administers it sees on top "Start with a business
     like yours" ("Choose the one most like yours and we leave your apps ready with its catalogue in one go.
     Then put in your own details."): up to four templates, one per kind of business and in their language when
     there is one (those of its country first), with their description and "Use this one"; "See all templates" opens "Data and backups" and "Not now"
     closes the card on this device.
  2. Tap "Use this one": "Preparing «{name}»…" while it loads, with no screens in between.
  3. In the same card, "Your apps and your catalogue are ready" ("What is left only you can answer: your
     business's details. They are in the list below.") with "Continue", which closes it.
  4. Without reloading, the Home gets up to date: "Finish setting up your business" counts as done the steps
     the template solved and the panels refresh. The same after loading a template or a file from "Data and
     backups".
In: the templates and whether the business is still empty.
Out: what the template brings, as in BASE-F31 (`base.blueprint.imported`).
If it fails: if not everything went in, "Not everything went in" with "These did not go in: {apps}." (or
"Something else did not go in.") and "See the report"; if it could not be opened, "That template could not
be opened" with "Nothing has changed in your business: {reason}" and "Try again"; if it was cut halfway,
"The setup did not finish" with "Part of it may be in already. Check it in Settings › Data before trying
again." and "See the report", with no retry. If the templates cannot be read, "The templates to start with
could not be loaded." with "Retry" and "Not now".
Involved: BASE-F01, INVENTORY-F12

### BASE-F39 Enter with the erplora.com account
Status: done
Actor: owner, administrator, manager, employee
Screen: Access
Steps:
  1. Opens the business without a session. On a device that does not offer a PIN it goes straight to
     erplora.com's sign-in for this business; on a till that does offer it, **Access** shows and they tap the
     "Account" tab and then "Enter with your account".
  2. At erplora.com they sign in as always: email and password, Google or their verification code.
  3. They come back to the business already in, on the screen they had asked for or on **Home**. If this
     device asks for a PIN, the business already enters its tills with a PIN and the person has none yet, it
     first asks them to choose it (BASE-F41).
In: the account erplora.com checks; this browser.
Out: the person's session in this business and this browser turned into a trusted device of the business (it
shows in "Devices", shared until someone says otherwise). The session lasts a 12-hour shift on a shared device,
30 days on a personal one and 1 hour at most if the business always asks for the PIN.
If it fails: erplora.com says why they do not get in (credentials, verification, "You don't have access to this
hub"); the business keeps nothing until it comes back with the person identified.
Involved: BASE-F13

### BASE-F40 Enter from the erplora.com panel without typing the password again
Status: done
Actor: owner, administrator, manager, employee
Screen: Access
Steps:
  1. At erplora.com, with the session open, they tap enter their business.
  2. The business opens with the person already in, on **Home**, without going through any sign-in screen.
In: the one-time pass erplora.com gives.
Out: the same as BASE-F39: the session and this browser as a trusted device of the business, so it then offers
the PIN pad, shows in "Devices" and its mode can be changed.
If it fails: an expired or already used pass opens nothing: the business asks for erplora.com's sign-in again.
Involved: BASE-F39

### BASE-F41 Choose the PIN the first time one enters a till
Status: done
Actor: owner, administrator, manager, employee
Screen: Create your PIN
Steps:
  1. After entering with the account (BASE-F39) on a shared device of a business that asks for a PIN, where
     someone else already enters with theirs, and if the person has no PIN yet, "Create your PIN" shows — "With
     it you will enter this till without your password.".
  2. They type the PIN on the keypad of circles: "Choose a {n}-digit PIN" (4 or 6, whatever the business says).
  3. They repeat it: "Confirm your PIN". Once it matches it is saved and they go where they were going.
  4. "Not now" leaves it for later: they enter all the same and can choose it in **My profile** (BASE-F52).
In: the session just opened; the business's PIN digits.
Out: the person's PIN, stored encrypted; their face shows in "Switch user" at once and on the PIN pad of
**Access** within a minute.
If it fails: the repetition does not match: "The PINs do not match, try again" and back to the first step.
Repeated or consecutive digits: "That PIN is too easy to guess: avoid repeated digits (1111) and runs (1234).".
Someone else already uses it: "Another active person already has that PIN: choose a different one.". Without a
connection: "Could not save the PIN. Try again.". A business in which nobody has a PIN does not ask for it on
entering: the first one is chosen in **My profile**.
Involved: BASE-F39, BASE-F52

### BASE-F42 Enter with a PIN
Status: done
Actor: owner, administrator, manager, employee
Screen: Access
Steps:
  1. On a shared device of a business that asks for a PIN, **Access** opens on the "PIN" tab: "Enter your PIN",
     "…or pass your badge: no need to choose your name first." and "Choose your user" with a face per person
     (initials and name; never their email). With a single person, they are already chosen.
  2. They tap their name: "PIN of {name}" and the keypad show, with as many circles as the business's PIN has
     digits. The arrow ("Change user") goes back to the faces.
  3. They type the PIN: it enters by itself at the last digit, with no button.
  4. They come in on the screen they had asked for or on **Home**. The footer says "ERPlora · trusted device".
In: the business's people with a PIN, read again every minute and on coming back to the screen: whoever gets a
PIN shows up and whoever leaves disappears without reloading. Only a shared device of the business that would
let them in sees them.
Out: that person's session on this device, for a shift (1 hour at most if the business always asks for the PIN),
in their language from the first moment. It works even if erplora.com does not answer.
If it fails: wrong PIN: the circles empty and "Wrong PIN." shows below. Five wrong PINs in a row for one person,
or too many from the same connection: "Too many wrong attempts." and the minutes they have to wait. A device on
which nobody ever entered with an account, or that an administrator removed: "This device does not work with a
PIN yet. Sign in once here with your account and from then on it will.". Without a connection, "Could not enter.
Check the connection and try again."; if who works here cannot be read, "Could not load the PIN pad. You can
still enter with your account.".
Involved: BASE-F41, BASE-F54

### BASE-F43 Enter by passing the badge
Status: done
Actor: owner, administrator, manager, employee
Screen: Access
Steps:
  1. On the "PIN" tab of **Access** (with a person chosen or without one), they pass the card through the
     reader. No field needs touching.
  2. The screen recognises the reader's burst by its speed (a person typing is never a badge).
  3. They come in as the card's owner.
In: the number the reader reads. It is only listened to on the "PIN" tab of a device that offers the PIN pad and
in **Switch user**; on "Account" or while the PIN is being chosen, it is not.
Out: the same as BASE-F42.
If it fails: a card that is nobody's or whose owner is gone: "That badge opens nothing here. Enter with your PIN
or ask an administrator."; it counts as a failed attempt. The PIN pad stays available.
Involved: BASE-F42

### BASE-F44 Lose the session because it was opened on another device
Status: done
Actor: owner, administrator, manager, employee
Screen: Access
Steps:
  1. The business's plan covers a number of devices at a time (the Free one, one) and someone enters on another.
  2. The session of the device that has gone longest without an entry ends at that moment: what it has open stops
     updating.
  3. Its next screen is **Access**, which says at the top "Session opened on another device" — "Your plan covers
     one device at a time, so entering on another one closed the session on this one. Enter again to use it here,
     or add devices to your plan." with "Upgrade plan".
  4. They can enter again (and it closes the other one's) or go to erplora.com to extend the plan.
In: the devices the plan covers, which erplora.com passes to the business.
Out: the sessions of the devices left over, ended, and the reason kept on each one to tell it.
If it fails: with no limit in the plan nothing ends.
Involved: BASE-F11, BASE-F28

### BASE-F45 The session ends while working
Status: done
Actor: owner, administrator, manager, employee
Screen: Access
Steps:
  1. The session ends: the shift is over (12 hours on a shared device, 30 days on a personal one, 1 hour if the
     business always asks for the PIN), an administrator removes the device or the person leaves the business.
  2. The next thing they open takes them to the way in; if the session ended because the device was removed or
     the person left the business, what they have open finds out at once.
  3. On a till with the PIN pad, **Access** says at the top "Your session has ended" — "It expired or it was
     closed. Enter again." and the next person enters with their PIN. On a device without the PIN pad it goes to
     erplora.com's sign-in, which brings them back in if their session there is still open.
In: the session that no longer exists.
Out: nothing saved; the half-made sale is kept by its app.
If it fails: without a network, the screen does not take the session as ended.
Involved: BASE-F13, BASE-F57

### BASE-F46 Close the session of a till nobody touches
Status: done
Actor: system
Screen: Access
Steps:
  1. The business chose in **Settings › General**, under "Ask again after inactivity", some minutes (1, 5, 10,
     15 or 30) and this device is shared.
  2. Nobody touches the screen (no finger, key or wheel) for those minutes.
  3. The session closes and the till goes back to **Access**, to the PIN pad.
In: the business's minutes, which come with the page itself (there is no separate read that could fail).
Out: the session closed in the business. The open check is kept by its app.
If it fails: with "Until signing out", on a personal device or where no PIN is asked nothing closes; even if the
screen hangs, a session opened while the business always asks for the PIN lasts no more than 1 hour.
Involved: BASE-F54

### BASE-F47 Switch user without losing the sale
Status: done
Actor: owner, administrator, manager, employee
Screen: Switch user
Steps:
  1. On a shared till of a business that asks for a PIN, they open the user card of the menu and tap "Switch
     user" (it does not show in any other case).
  2. **Switch user** opens over the screen in use: "The sale stays open. From now on it is in the name of
     whoever enters here." and "Who is taking over?" with a face per person.
  3. They tap theirs and type the PIN, or pass their badge. The arrow ("Someone else") goes back to the faces;
     "Cancel" goes back without changing anything.
  4. "Now serving {name}" shows and the screen stays where it was, loaded again for whoever entered: what shows
     is what their role allows, and going back no longer leads to the screens of whoever left. The till's open check
     stays on screen, with its lines, and what comes next is in the name of whoever entered.
In: the name and the PIN (or the badge) of whoever enters; the session of whoever leaves.
Out: the session of whoever enters; that of whoever leaves ends only once the new one is open. The appearance of
whoever left is forgotten, and erplora.com is in nobody's name in a PIN session.
If it fails: wrong PIN: "Wrong PIN." and whoever was in stays in. Too many attempts: "Too many wrong attempts."
and the minutes they have to wait. Nobody with a PIN: "Nobody here has a PIN yet: give one in My profile or in
Employees.". Without being able to read who works here: "Could not load who works here. Check the connection and
try again.".
Involved: BASE-F42, BASE-F43

### BASE-F48 Sign out
Status: done
Actor: owner, administrator, manager, employee
Screen: The user menu
Steps:
  1. They open the user card at the top of the side menu (on a phone, first the menu with the bar's button).
  2. They tap "Sign out".
  3. On a till with the PIN pad it goes back to **Access**, ready for the next person. On another device,
     erplora.com's session ends too (erplora.com asks to confirm it).
In: the session.
Out: the session closed in the business.
If it fails: if the business does not answer, the session expires by itself.
Involved: none

### BASE-F49 Decide whether this device is shared or personal
Status: done
Actor: owner, administrator
Screen: Settings · General
Steps:
  1. From the device itself, they open **Settings**; under "This device": "How this device asks who is using it.
     Each device of the business is decided on its own.".
  2. They choose "Shared — a till or tablet several people use" ("It asks for a PIN to enter and forgets it at
     the end of the shift, so every sale is in the name of whoever made it.") or "Personal — a device only you
     use" ("The session stays open and it never asks for a PIN.").
  3. It is saved at once; the mark moves when the business confirms it.
  4. This device's way in changes accordingly: the PIN pad when shared, only the account when personal.
In: the device the request comes from (never another one).
Out: the device's mode, with who chose it and when.
If it fails: whoever does not run the business sees the options off and "Only an administrator can change how
people enter on this device.". A browser in which nobody ever entered with the account: "This browser is not a
device of the business yet: enter once here with your account and you will be able to choose.". Without a
connection: "Could not change this device. Check the connection and try again.".
Involved: BASE-F42

### BASE-F50 Open a hub that is not set up yet
Status: done
Actor: owner, administrator, manager, employee
Screen: Your business is being prepared
Steps:
  1. They open the address of a business erplora.com is still preparing (just created).
  2. "Your business is being prepared" shows — "It takes a few seconds. This page refreshes by itself.".
  3. When it is ready, the page refreshes and they come in as always.
In: the business's state erplora.com passes on.
Out: nothing saved.
If it fails: an address that belongs to no business does not exist; a business that was closed says "This hub
is no longer available.".
Involved: none

### BASE-F51 Change my details, photo, language and appearance
Status: done
Actor: owner, administrator, manager, employee
Screen: My profile
Steps:
  1. They open the user card of the menu and tap "Profile". At the top, their face, their name, "Your identity
     and your personal preferences in this business." and their role.
  2. In "Account details" they change "First name", "Last name" or "Email" ("Only to contact you: it is not the
     email you sign in with.") and tap "Save my details": "Profile saved", and the side menu already says the new name, without reloading.
  3. "Choose image" uploads a JPG, PNG or WebP photo of up to 2 MB ("Photo updated"); "Remove" deletes it
     ("Photo removed").
  4. In "Preferences", "Language" ("Use the business’s language", "Español", "English") and "Appearance" ("Theme
     palette" and "Theme": "System (auto)", "Light", "Dark") are saved on choosing and applied at once; "Use the
     business’s appearance" undoes their own.
In: the profile of whoever has the session.
Out: their name in this business (the one in the side menu, on the faces and in "Devices"), their photo, their language and their
appearance, which follow them on any device they enter. The email is only for contact: it does not change the
erplora.com account.
If it fails: if the profile could not be read, "Could not load the profile" — "Your details stay the same. Check
the connection and try again." with "Retry". On saving: "Could not save the profile"; a refused photo: "Could not
save the photo. Use a JPG, PNG or WebP of up to 2 MB."; preferences: "Could not save your preferences. Check the
connection and try again.".
Involved: none

### BASE-F52 Change my PIN from My profile
Status: done
Actor: owner, administrator, manager, employee
Screen: My profile
Steps:
  1. In **My profile**, the "PIN" card: "The PIN you enter the till with. Change it whenever you want — nobody
     else has to." (without a PIN: "You do not have a PIN yet. Set one to also enter from the till.").
  2. If they already have a PIN, they type "Current PIN".
  3. They type "New PIN" and "Repeat the new PIN" and tap "Change PIN" (or "Set PIN"): "PIN updated".
In: the session; the business's PIN digits.
Out: the new PIN, stored encrypted; the tills accept it at once.
If it fails: a different length: "The PIN must have {n} digits."; the two do not match: "The two PINs do not
match."; easy to guess: "That PIN is too easy to guess: avoid repeated digits (1111) and runs (1234)."; someone
else already uses it: "Another active person already has that PIN: choose a different one."; the current one is
not it: "That is not your current PIN. Type it right to set a new one."; thirty tries in an hour: "Too many tries
to change the PIN." and the minutes they have to wait.
Involved: BASE-F41

### BASE-F53 Choose how many digits the business's PIN has
Status: done
Actor: owner, administrator
Screen: Settings · General
Steps:
  1. With the PIN pad on (BASE-F54), under "PIN digits" they choose "4 digits" or "6 digits".
  2. It is saved at once. Below: "Everyone types the same number of digits, which is what lets the keypad enter
     at the last one instead of asking you to confirm. The PINs in use keep working until their owner changes
     them.".
  3. From then on, the PIN pad, "Create your PIN" and **My profile** ask for that length.
In: the choice.
Out: the length of the business's PIN. It does not touch the PINs there are.
If it fails: "Could not change it. Check the connection and try again.".
Involved: BASE-F54

### BASE-F54 Decide whether the till asks for a PIN and when it asks again
Status: done
Actor: owner, administrator
Screen: Settings · General
Steps:
  1. In **Settings**, under "PIN pad", they see "Show PIN pad": "Whether the PIN pad is shown and who is at the
     till is asked. It holds for the whole business: besides, each device decides on its own, above.".
  2. They turn it on or off. Below, the consequence. On: "Staff choose their name and type their PIN, so every
     sale carries the name of whoever made it.". Off: "Nobody types a PIN. Whoever opened the till in the morning
     is the name of every sale until the shift ends, whoever made them: you will not know who sold what or who
     gave a discount. Staff who only have a PIN and no account will not be able to enter.".
  3. With the PIN pad on, "Ask again after inactivity": 1, 5, 10, 15 or 30 min, or "Until signing out", and
     below what happens ("A till nobody touches for {n} minutes closes the session and shows the PIN pad: the
     next sale carries the name of the next person.").
  4. Each change is saved at once, with no button, and the card shows what the business confirms.
In: how the business asks for the PIN.
Out: whether it asks and when it asks again, for every till of the business. Turning it off and on again goes
back to asking per shift.
If it fails: "Could not change it. Check the connection and try again.". If it cannot be read: "Could not load
how the business asks for the PIN. Check the connection and try again.". Whoever does not run the business sees
the controls off and "Only an administrator can change whether it asks.".
Involved: BASE-F42, BASE-F46

### BASE-F55 See the devices someone has entered on
Status: done
Actor: owner, administrator
Screen: Settings · General
Steps:
  1. In **Settings**, under "Devices": "The devices someone has entered on. If you lose one, remove it here: its
     session closes at once and it can no longer enter with a PIN.".
  2. A row per device, the last used first: the name the business gave it (or "Unnamed device" and what it is,
     for example Chrome · Android), "The one you are using" on the current one, the mode ("Asks for a PIN" or
     "Stays open"), "In use right now" or "Last used {when}", "Its session stays open until {when}" and "Last
     entered: {who}". Never its identifier.
  3. It updates by itself when someone changes, names or removes a device.
In: the business's devices.
Out: nothing saved.
If it fails: whoever does not run the business sees "Only an administrator can see and remove the devices.",
with no list. If it does not arrive: "Could not load the devices. Check the connection and try again.", never
"Nobody has entered from any device yet.", which is only for a truly empty list.
Involved: BASE-F56, BASE-F57, BASE-F58

### BASE-F56 Name a device
Status: done
Actor: owner, administrator
Screen: Settings · General
Steps:
  1. On the device's row, they tap "Name it".
  2. A field shows below: "Name the place: Bar, Kitchen, Office laptop" (up to 60 characters).
  3. They type and tap "Save" (or "Leave it" to close). The row takes that name as its title.
In: the name.
Out: the device's name, the only detail of the row the business decides.
If it fails: "Could not change the name. Check the connection and try again." or "That name is too long. Give it
a shorter one and save again.".
Involved: BASE-F55

### BASE-F57 Remove a device that was lost
Status: done
Actor: owner, administrator
Screen: Settings · General
Steps:
  1. On the device's row, they tap the "Remove this device" icon.
  2. Below shows "Remove this device?" with the consequence: "Its session closes at once. To use it again,
     someone has to enter on it with their account.". If it is the one they are using: "It is the device you are
     using: removing it will close your session and you will have to enter again.".
  3. They confirm with "Remove this device" (or "Leave it"). The row disappears and its session closes at once.
     If it was theirs, they leave the business.
In: the device.
Out: the device forgotten and its sessions ended: the device is cut off, not the person, who can enter on it
again with their account.
If it fails: "Could not remove this device. Check the connection and try again." or "That device is no longer
registered here. Refresh the list."; what was refused never stays as done.
Involved: BASE-F45, BASE-F55

### BASE-F58 Remove at once the devices nobody uses
Status: done
Actor: owner, administrator
Screen: Settings · General
Steps:
  1. If there are devices nobody has used in 30 days (never the one in hand), "Remove the device unused for 30
     days" or "Remove the {n} devices unused for 30 days" shows.
  2. On tapping it, "Remove {n} devices nobody has used for 30 days?" (or "Remove the device nobody has used for
     30 days?") with "They stop showing here and, to use one again, someone will have to enter on it with their
     account. Those used in the last 30 days and the one you are using stay.".
  3. They confirm with "Remove".
In: which devices nobody has used for 30 days.
Out: those devices forgotten, as in BASE-F57.
If it fails: "Could not remove the unused devices. Check the connection and try again.".
Involved: BASE-F57
