<!-- generated from WORKBOOK.md sha256:02d6342a767b7b882c0f2474afcfdb26280f654ab34ac51b7ecb56c5f17cc968 -->

## What it is for and who it is for

The Home is the first thing anyone in the business sees on coming in. At a glance:

- **Their apps**, to open the one they need without looking for it in any menu.
- **What the business still lacks** to work fully: each app says which step it needs and the list puts
  them together, in order and with what happens if they are not done; the one that stops invoicing goes
  first and in red.
- **The apps' panels**: figures, lists and charts that move by themselves when something changes in the
  business, without reloading.
- **The activity**: the latest sales.

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

- You come in with your ERPlora account; the Hub has no sign-in of its own.
- What each person sees depends on their role in the business and on the apps the business has on.
- The apps declare their steps, their panels and their counters; the Home only puts them together. While
  an app does not declare its own, nothing of it shows in the list or on the board.
- The example app (Demo) shows an example step, panel and counter on the Home only in development, in
  the tests and in a demo business: never in a customer's.

## Screens

### Home · Summary
On top, the business's name and "Today" with the long date; while the business has no name, a greeting
by the hour ("Good morning", "Good afternoon", "Good evening"). Below, in this order:

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

### The "You cannot issue invoices yet" strip
Over any screen while a step that stops invoicing is missing: "No ticket or invoice can be issued until
this is set up:" and each step with "Set up". It does not show on the Home's "Summary" (the list says the
same a little further down); on "Activity", it does.

## States of each screen

| State | What the person sees |
|---|---|
| Loading | Grey tiles in "My apps" ("Loading your apps…" for the screen reader), the list in grey, "Loading widgets…" on the board, each panel's figure in grey and "Loading…" in "Activity". |
| Empty | "Your apps will show up here. Add the ones your business needs."; with no steps, the list does not show; "Empty panel. Tap ⋮ to add widgets."; a panel without data, "No data"; the bell, "All caught up. No notifications.". |
| Error | Each zone fails on its own: "Could not load your apps. Reload the page; if it keeps failing, sign in again.", "Could not load what is left to set up" with "Retry", "Could not load the panels" with "Retry", a panel with "Unavailable" (never the figure it had), "Could not load the latest sales" with "Retry" and, in the bell, "Could not check the notifications. They will show up when the connection is back.". |
| No permission | A step the person cannot do: no button and "An administrator has to set this up.". A panel or a counter they may not see does not show. |

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
Status: partial — without the hub's health row (the printer and WhatsApp with "View system") nor the template proposal, which comes with the templates
Actor: owner, administrator, manager, employee
Screen: Home · Summary
Steps:
  1. After coming in, the Home opens (also from "Home" in the side menu).
  2. On top, the business's name (the one on erplora.com) and "Today" with the long date in the app's
     language; while the business has no name, "Good morning", "Good afternoon" or "Good evening".
  3. Below, in this order: "My apps", "Finish setting up your business" and the board of panels.
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
  2. Each panel is a card with its title and icon: a figure, a list with bars, a timeline, a chart or a
     piece of its app's screen.
  3. At first, the ones each app marks as recommended for the business's sector show.
  4. Only the panels of the apps that are on and that this person may see show.
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
  1. At the foot of the side menu is "Upgrade plan". Any profile sees it; what can be done on arriving is
     decided by erplora.com according to who comes in.
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
