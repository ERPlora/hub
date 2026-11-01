<!-- generated from WORKBOOK.md sha256:4879782912984019afe4d26b06a180a9331a06c0dafd311f3fbcce6a015deb57 -->

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
- **The business's details**, in "Settings": its name, its country, its time zone, its currency and its
  language, as erplora.com has them, and where to go to change them.
- **The business's files**, in "Files": the documents the team keeps in folders (suppliers' invoices,
  contracts, letters, photos), to open, download and tidy them from any device.
- **The assistant**, with the sparkles in the top bar: they ask it about the business, writing or by voice, and it
  does what the person could do with their buttons, always after they confirm it.

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
each person picks and orders of Lightspeed and Toast, and the bell with counters of any back office. System's
"Usage and plan" follows Business Central's "Capacity" and the usage pages of Supabase, Vercel and Neon: each figure
against what the plan includes and, like Google Workspace, the yellow notice at 80 % and the red one when full.

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

### "erplora.com" of the bar
At the top right, between "My apps" and the assistant's sparkles: a cloud and "erplora.com" ("Manage on erplora.com"
on hover). It opens this business on erplora.com's panel: in a new tab in the browser and, in the installed app, in
the device's browser. Only the owner, the administrator and the manager have it, and only if they came in with their
account: never in a session opened with a PIN or with the badge. The Google Play app does not have it.
On a phone it goes inside "More options", the first one, as "Manage on erplora.com".

### The bell
At the top right, after "My apps" and the assistant's sparkles; on a phone, both go inside "More options", which
carries its number. Its number adds up the pending notices; tapped, one row per notice ("Failed events (2)") that
leads to its screen. With nothing: "All caught up. No notifications.".

### The side menu
On the left (on a phone, from the bar's button): the person at the top and the platform's entries in two groups,
"Home", "Employees", "Files" · "Apps", "System", "API", "Settings". Each one shows only to whoever may open its screen:
"System", to whoever runs the business; "API", while the API documentation is shown (BASE-F91), and it appears or goes
when the switch changes, without reloading. An employee sees "Home", "Employees", "Files", "Apps" and "Settings". At
the bottom, the QR code and "Upgrade plan".

### "Upgrade plan"
At the foot of the side menu, between the QR code and the brand. It opens this business's plan page on
erplora.com, in a new tab. Only in the browser: the installed app does not have it.

### The user menu
It opens by tapping the person, at the top of the side menu. First "Profile" and, on a shared till of a business
that asks for a PIN, "Switch user"; then, only if they entered with the account (never in a PIN session), "My
account", which opens that page on erplora.com (in a new tab; in the installed app, in the device's browser), and
"Report a problem", which opens a form in a window without leaving the hub (BASE-F108); last "Theme" (light, dark
or the system's) and "Sign out". Both also show in the installed app: neither sells anything.

### The "You cannot issue invoices yet" strip
Over any screen while a step that stops invoicing is missing: "No ticket or invoice can be issued until
this is set up:" and each step with "Set up" (on the screen that sets it up, only its name). It does not
show on the Home's "Summary" (the list says the same a little further down); on "Activity", it does.

### Apps
From "Apps" in the side menu. Three tabs at the bottom: "My apps" (the apps the business has running), "Add
apps" (every ERPlora app) and "Paid" (the ones subscribed to separately). At the top, how many apps the business
has chosen against its plan's limit: "17 of 20 apps turned on" or, with no limit, "17 apps turned on · Unlimited".
Each tab, a table (or cards) with its search, the filters funnel, the order and "Columns": "App" (icon and name),
"Category" and "Status"; in "Add apps" and "Paid", also "Description", "Price" and "Comes with". "Open" on the
row of an app the person can open and, for whoever runs the business, "Turn on" or "Turn off". Above the table,
when it applies, the notice of the plan's limit or the one saying why an app was not changed.
"Paid" and "Price" only show if some app is subscribed to separately; today none is: every app comes with every plan.

### The screen of an app that does not open
In the same address as the app's screen, the reason: "Subscription needed" or "This app is not available in
this business", with "Go to Apps" (and "Upgrade plan" for whoever runs the business, in the
browser).

### Settings · Business
The second of the tabs at the bottom of "Settings" ("General", "Business", "Printing" and "Data and backups").
The "Your business" card shows, with no fields to fill in, "Business name", "Country", "Time
zone" (with the time it is there), "Currency" and "Business language", each with a line that says what it is
for. Below, where they are changed and, for the owner and the administrator, "Change on erplora.com" (in the installed app, in the device's browser; the Google Play copy does not have it). Further
down, "Fiscal data", which opens Invoicing's issuer.

### Settings · Printing
The "Printing" tab: a single row, "Printers and ticket", which opens the Printing app.

### Settings · Data and backups
The "Data and backups" tab of "Settings", the last one, after "General", "Business" and "Printing". On top, a
selector with "Import" (what opens), "Export" and "Reset";
the one chosen stays in the link, so it can be shared and Back leaves Settings.

- **Import**: "Choose what to load", with "Upload from file" and the templates as cards or as a list, with
  "Search templates"; each with its language, its country, its version, what it brings and "Use template".
  Then "Review what it brings" and the "Import report".
- **Export**: the file's name and language, "What is this file for?", the apps with their "App" and "Data"
  boxes, and "Export".
- **Reset**: "Undo an import", with one row per import that can be undone, "Reset the business", with what
  each section has, and "Copies of the data", with the copies kept and their "Download".

### System · Usage and plan
From "System" in the side menu. Four tabs at the bottom: "Usage and plan", "Updates", "Failed events" and "Logs" (this
one, only for whoever runs the business); "Usage and plan" opens: their plan with "Upgrade plan", a line that says whether
it is enough or they have to upgrade and why, "What your plan includes", from the fullest down, with its bar, and "For
your information", with the figures no plan limits.

### System · Updates
"What we have updated": the version running, when it was published and that the hub updates itself.

### System · Failed events
One card per notice between apps that ran out of retries, with "Resend" and "Discard"; on top, "Resend all".

### System · Logs
"Event log": the "Time", "Level" and "Event" table (on a phone, one card per event), with "Search event…" and the
level filter.

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
What "Settings" in the side menu opens: the first tab at the bottom, "General", with "This device", "PIN pad",
for whoever runs the business "Devices" and, at the end, "API documentation".

### Your business is being prepared
The page that shows at the address of a business erplora.com is still preparing; it refreshes by itself.

### Files
From "Files" in the side menu; the whole team sees it. On the left, "Folders": the tree of the business's folders,
which starts at "Files" (the very top), with the open folder highlighted; on a narrow screen, the tree folds into the
"Folders" selector. On the right, "Search files…", "List" and "Grid" and, for whoever administers the business, "New
folder" and "Upload file". Below, the open folder's path, with ⋮ beside it to rename, move or delete that folder;
"Space", with what is used and the plan's limit ("{used} of {limit}") or "{used} used · No limit"; and what the folder
holds: the folders first and then the files, each with its icon, its name, its size (in the list, also when it
changed) and its ⋮: "Open", "Download", "Rename", "Move to…" and "Delete". In the list, each name takes one line:
what does not fit is cut with "…" and the extension always shows whole; on a phone, the size and the date go under
the name, in grey. Tapping a file opens it in the viewer, with
its name, "Download" and "Close" ("Zoom in" and "Zoom out" on images and PDFs).

### Employees · Staff
What "Employees" in the side menu opens: the first tab at the bottom, "Staff", with the plan's places, "Invite on
erplora.com" for whoever runs the business (in the installed app, in the device's browser; the Google Play copy does not have it), "People are invited, given a role and removed on erplora.com, in
“Members” of the business." and the table of people (on a phone, a card per person). The other tabs: "Roles" and,
only for whoever runs the business, "API keys" and "Approvals"; each one in the address, so "Back" leaves
Employees.

### Employees · Roles
The four roles of erplora.com, with where they come from, how many people have them and how many permissions they
give.

### Employees · API keys
The keys with which another system calls the business's API: "New API key", the table of keys and, at the bottom,
"API documentation".

### Employees · Approvals
The record of what was approved with a manager's PIN, read only.

### A person's page
From a row of **Employees › Staff**, for whoever runs the business, with the back button: "Their details" (with
"Open on erplora.com"), "PIN" and "Badge".

### An approval is needed
Over the screen where the action was tried: what is approved, "Who approves it?" with the faces and the PIN pad
(whole and without scrolling on a phone, a tablet and a desk), and "Cancel".

### API documentation
With the back button: how the API is called, "Download the OpenAPI file" and a section per app with its calls.

### Assistant
The panel the "Assistant" sparkles of the top bar open (on a phone, inside "More options"), on the right. On a tablet
or a computer it stays beside the screen and pushes it, so they keep working with it open; on a phone it covers it,
over a dark veil. At the top, "Assistant", "New conversation" once there is one and the "Close" ×. In the middle, the
conversation: empty, the sparkles, the welcome sentence and the setup's shortcuts; then, the messages, each answer
with its "Go to …" buttons, its notices and the receipts of what was done. At the bottom, the foot's notices (no
connection, the messages left this month, a plan without the assistant) and the "Write a message…" box with "Attach a
file", "Dictate by voice" and "Send".

### Assistant confirmation card
It shows over everything, also with the panel closed, when the assistant wants to change something: "Run this
action?", what it will do, in which app and with which data, and "Run it" and "Cancel" ("Cancel all" when more wait
behind it). In a dangerous action, each datum on its own line and a box to type what it asks before "Run it".

## States of each screen

| State | What the person sees |
|---|---|
| Loading | Grey tiles in "My apps" ("Loading your apps…" for the screen reader), the list in grey, "Loading widgets…" on the board, each panel's figure in grey and "Loading…" in "Activity"; "Loading…" on the PIN pad, "Loading your profile…" and "Loading the devices…". |
| Empty | "Your apps will show up here. Add the ones your business needs."; with no steps, the list does not show; "Empty panel. Tap ⋮ to add widgets."; a panel without data, "No data"; the bell, "All caught up. No notifications."; "Nobody has entered from any device yet."; in "Switch user", "Nobody here has a PIN yet: give one in My profile or in Employees.". |
| Error | Each zone fails on its own: "Could not load your apps. Reload the page; if it keeps failing, sign in again.", "Could not load what is left to set up" with "Retry", "Could not load the panels" with "Retry", a panel with "Unavailable" (never the figure it had), "Could not load the latest sales" with "Retry" and, in the bell, "Could not check the notifications. They will show up when the connection is back.". In the way in: "Could not load the PIN pad. You can still enter with your account.", "Could not load the profile" with "Retry", "Could not load this device. Check the connection and try again.", "Could not load how the business asks for the PIN. Check the connection and try again." and "Could not load the devices. Check the connection and try again.". |
| No permission | A step the person cannot do: no button and "An administrator has to set this up.". A panel or a counter they may not see does not show. In Settings, whoever does not run the business sees "This device" and "PIN pad" with the controls off ("Only an administrator can change how people enter on this device.", "Only an administrator can change whether it asks.") and, instead of the list, "Only an administrator can see and remove the devices.". |

On the Settings · Business screen:

| State | What the person sees |
|---|---|
| Loading | "Loading the business’s data…". |
| Empty | A demo has no name nor country: those rows read "—", and below, "This demo has no business on erplora.com: its data does not change.". |
| Error | "Couldn’t load the business’s data" with "Nothing has changed. Check the connection and try again." and "Retry"; never a blank card. |
| No permission | Whoever does not administer the business sees it the same, without "Change on erplora.com" and with "Only the owner or an administrator changes them, on erplora.com."; "Fiscal data" does not show to whoever may not write the issuer. |

In the assistant's panel:

| State | What the person sees |
|---|---|
| Loading | Three dots that move in the assistant's bubble until the first text arrives ("The assistant is writing" for the screen reader), and "Transcribing…" while what was dictated is turned into text. |
| Empty | The sparkles, "Ask me about your sales, your stock or anything about your business." (opened from the setup, "Review your business's setup. Choose an option or write your question.") and the shortcuts. An answer that ends without saying anything: "(no answer)". |
| Error | In the bubble, with its way out: "The assistant could not be reached. Check the connection and try again.", "The assistant is not available right now. Try again in a few minutes." or "The answer was cut off.", with "Try again"; "This conversation is too long: start a new one." with "New conversation"; "Your session has ended. Sign in again to keep talking." with "Sign in again". Without Internet, in the foot, "No connection: you can write, and send when it is back.". |
| No permission | What the person cannot do with their buttons, the assistant cannot either: it is not offered and, if it tries, the receipt reads "Not done, not allowed: …". With the month's messages spent, whoever does not run the business sees "Ask whoever runs the business to upgrade the plan." instead of "Upgrade plan". |

On the Settings · Data and backups screen:

| State | What the person sees |
|---|---|
| Loading | "Loading templates…"; in "Export" and "Reset", the rows in grey. |
| Empty | "There are no templates for your business yet.", "No template matches your search.", "This business has no app on to export." and "There is nothing to reset: no section has data.". |
| Error | "The templates could not be loaded right now. You can still import a file." with "Retry"; "The apps of this business could not be loaded." and "What each section has could not be worked out.", with "Retry". |
| No permission | "Only an administrator can see and import templates.", "Only an administrator can export the business." and "Only an administrator can undo imports or reset the business."; the Home's templates card does not show. |

On the Files screen:

| State | What the person sees |
|---|---|
| Loading | "Loading files…"; in the viewer, "Opening the file…". |
| Empty | "No files" and, to whoever administers the business, "Upload a file or drag it here."; a search with no results, "No file in this folder matches “{search}”.". |
| Error | "The files could not be loaded" with the reason and "Retry", never "No files"; in the viewer, "The file could not be opened" with "The file's content did not arrive. Check the connection and try again.". |
| No permission | Whoever does not administer the business sees, opens and downloads, without "New folder", "Upload file", "Rename", "Move to…" or "Delete". |

On the Employees screens and the API documentation:

| State | What the person sees |
|---|---|
| Loading | The table in grey in "Staff", "Roles", "API keys" and "Approvals"; "Loading…" on a person's page; the faces in grey in "An approval is needed"; "Loading the documentation…". |
| Empty | "Nobody is in this business yet.", "No API keys yet. Create one so that another system can read or write your business's data.", "Nobody has had to approve anything in this business yet.", "Nobody here can approve this with a PIN. Somebody who may do it can swipe their badge." and "None of this business’s apps publishes its API yet.". |
| Error | "The people of this business could not be loaded.", "The roles could not be loaded.", "Your API keys could not be loaded.", "Could not load the record of approvals.", "This person could not be opened.", "Could not load who can approve it." and "Could not load the documentation.", each with "Retry"; never the empty list. |
| No permission | Whoever does not run the business has no "API keys" or "Approvals" tabs (their address opens "Staff"), sees nobody's email and does not open a person's page; in Settings, "Only who runs the business can change it.". With the documentation hidden: "The API documentation is hidden in this business.". |

## Flows

| ID | Flow | Status |
|---|---|---|
| BASE-F01 | See what the business still has to set up | done |
| BASE-F02 | See the business at a glance on coming in | discarded |
| BASE-F03 | Go and set up from "Finish setting up your business" | done |
| BASE-F04 | See which steps of the list an administrator has to set up | done |
| BASE-F05 | Open an app from "My apps" | done |
| BASE-F06 | See the apps' panels on the Home | done |
| BASE-F07 | Customize the board of panels | done |
| BASE-F08 | Keep the panels up to date without reloading | done |
| BASE-F09 | Look at the recent activity | done |
| BASE-F10 | See in the bell the notices between apps that were not delivered | done |
| BASE-F11 | Go to erplora.com to manage or upgrade the plan | discarded |
| BASE-F12 | Ask the assistant to go over the setup | done |
| BASE-F13 | Lose access on a role change or on leaving the business | done |
| BASE-F14 | See the business's apps | done |
| BASE-F15 | Open an app from Apps | done |
| BASE-F16 | Look for an app in the catalogue | done |
| BASE-F17 | Know how much an app costs before having it | done |
| BASE-F18 | Install an app | done |
| BASE-F19 | Know what else comes with an app | done |
| BASE-F20 | Try to use an app that needs a subscription | done |
| BASE-F21 | See why an app could not be turned on and try again | done |
| BASE-F22 | Follow an app being turned on while moving around | done |
| BASE-F23 | Turn an app off | done |
| BASE-F24 | Turn an app on | done |
| BASE-F25 | See an app refuse to be turned off | done |
| BASE-F26 | Understand why an app does not open | done |
| BASE-F27 | See a paid app blocked | done |
| BASE-F28 | See how much of the plan's limits is in use | discarded |
| BASE-F29 | Choose a template of the catalogue to import | done |
| BASE-F30 | Upload a file to import | done |
| BASE-F31 | Review and load what the file brings | done |
| BASE-F32 | Read the import report | done |
| BASE-F33 | Come back to the report of an import that did not go in whole and retry | done |
| BASE-F34 | Undo an import | done |
| BASE-F35 | Export a backup or a template | done |
| BASE-F36 | Choose which apps, data and tables travel in the export | done |
| BASE-F37 | Reset the business by sections | done |
| BASE-F38 | See the Home up to date after importing a template | done |
| BASE-F39 | Open System and move between its tabs | done |
| BASE-F40 | See what the business uses and whether to upgrade the plan | done |
| BASE-F41 | Know which version is running and what has been updated | discarded |
| BASE-F42 | See the log of what happened in the system | done |
| BASE-F43 | See the failed events | done |
| BASE-F44 | Resend a failed event | done |
| BASE-F45 | Resend all the failed events | done |
| BASE-F46 | Discard a failed event | done |
| BASE-F47 | Report an error of the screen without anyone asking | done |
| BASE-F48 | Open Settings and move through its tabs | done |
| BASE-F49 | See the business's country | done |
| BASE-F50 | See the business's currency | discarded |
| BASE-F51 | Change the business's language on erplora.com | done |
| BASE-F52 | Enter with the erplora.com account | done |
| BASE-F53 | Enter from the erplora.com panel without typing the password again | done |
| BASE-F54 | Choose the PIN the first time one enters a till | done |
| BASE-F55 | Enter with a PIN | done |
| BASE-F56 | Enter by passing the badge | done |
| BASE-F57 | Lose the session because it was opened on another device | done |
| BASE-F58 | The session ends while working | done |
| BASE-F59 | Close the session of a till nobody touches | done |
| BASE-F60 | Switch user without losing the sale | done |
| BASE-F61 | Sign out | done |
| BASE-F62 | Decide whether this device is shared or personal | done |
| BASE-F63 | Open a hub that is not set up yet | done |
| BASE-F64 | Change my details, photo, language and appearance | done |
| BASE-F65 | Change my PIN from My profile | done |
| BASE-F66 | Choose how many digits the business's PIN has | done |
| BASE-F67 | Decide whether the till asks for a PIN and when it asks again | done |
| BASE-F68 | See the devices someone has entered on | done |
| BASE-F69 | Name a device | done |
| BASE-F70 | Remove a device that was lost | done |
| BASE-F71 | Remove at once the devices nobody uses | done |
| BASE-F72 | See the business's files | done |
| BASE-F73 | Upload files and make folders | done |
| BASE-F74 | Preview and download a file | discarded |
| BASE-F75 | Move and rename a file or a folder | done |
| BASE-F76 | Delete a file or a folder | done |
| BASE-F77 | Reach the plan's limit of people | done |
| BASE-F78 | Remove a person's PIN | done |
| BASE-F79 | Give a person a badge or take it away | done |
| BASE-F80 | Bring back a person who left the business | done |
| BASE-F81 | Understand how each person gets in | done |
| BASE-F82 | See the roles and turn on the ones an app brings | discarded |
| BASE-F83 | Give a person a role | done |
| BASE-F84 | Approve with a manager's PIN | done |
| BASE-F85 | Look up who approved what | done |
| BASE-F86 | Create an API key and copy its token | done |
| BASE-F87 | Rotate an API key | done |
| BASE-F88 | Revoke an API key | done |
| BASE-F89 | See the API keys and what each one may do | done |
| BASE-F90 | Read the API documentation | done |
| BASE-F91 | Show or hide the API documentation | done |
| BASE-F92 | Open and close the assistant's panel | done |
| BASE-F93 | Ask the assistant and read how it writes | done |
| BASE-F94 | Attach a file or dictate by voice | done |
| BASE-F95 | Read the answer: text, lists, tables and links | done |
| BASE-F96 | Go to a screen from an answer | done |
| BASE-F97 | Confirm an action before it runs | done |
| BASE-F98 | Dangerous actions: type to confirm, or not from the chat | done |
| BASE-F99 | Check what the assistant says against what it really did | done |
| BASE-F100 | What the assistant can do depending on who asks: permissions and a manager's PIN | done |
| BASE-F101 | Ask it for several things in a row | done |
| BASE-F102 | The conversation: what is kept, where and when it is deleted | done |
| BASE-F103 | The assistant in the setup | done |
| BASE-F104 | See the assistant's plan, the usage limit and extend it | done |
| BASE-F105 | Report a bad answer | done |
| BASE-F106 | The assistant without a connection, with the service down or without a plan | done |
| BASE-F107 | Pass the master QA of the Hub | done |
| BASE-F108 | Report a problem to support | done |

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
Status: discarded — the hub's health row (the printer and WhatsApp, with a link to System) needs each app to say how its own part is doing, and that touches Printing and the WhatsApp Inbox; today the bell already warns when nobody is printing (hub#573)
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

### BASE-F03 Go and set up from "Finish setting up your business"
Status: done
Actor: owner, administrator, manager
Screen: Home · Summary
Steps:
  1. In "Finish setting up your business", a pending step the person can do carries "Set up".
  2. They tap "Set up": the screen of the app that completes that step opens.
  3. Back on the Home, the list already counts the step as done if it was completed.
  4. While the business is empty, whoever runs it starts higher up, in "Start with a business like yours"
     (BASE-F38): "See all templates" opens "Data and backups", where a template or a backup is loaded.
In: the screen each step declares.
Out: nothing from here.
If it fails: while that screen does not exist in the hub, the step shows without "Set up" (a button that
leads to "not found" is worse than none).
Involved: BASE-F38

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
Status: done
Actor: owner, administrator, manager, employee
Screen: Home · Summary · the top bar of any screen
Steps:
  1. In "My apps", one tile per app this person can open, with its icon and its name (if it does not
     fit, the whole name shows on hover).
  2. The ones opened most in this browser go first.
  3. They tap a tile: the app opens. An app that is being turned on says "Activating…" and opens nothing.
  4. On a phone, with six apps or more, the first four show and "View all apps", which shows the rest.
     "Add apps", the last one, leads to Apps.
  5. To leave an app, tap "My apps" in the bar: the main screen of an app has no "Back". The sheet starts
     with "Home", which goes back to the Home, and goes on with the apps; tapping one opens it. "Home" is
     there even while the list loads, when it is empty or when it could not be read.
  6. In the Android app, the phone's back button first closes whatever is open on top (a window, a sheet
     or the menu); a window that cannot be closed that way stays. With nothing open, on a record or a new
     one it does the same as "Back"; on the main screen of an app it goes back to the Home, also when that
     screen was reached through a link; and on the Home it sends the app to the background.
In: the apps of the person's menu (the same as the bar's "My apps" button).
Out: how many times each app is opened in this browser (only to order them).
If it fails: while loading, grey tiles and "Loading your apps…" for the screen reader. Without apps:
"Your apps will show up here. Add the ones your business needs.". If the list could not be read: "Could
not load your apps. Reload the page; if it keeps failing, sign in again.", never that there are no apps.
In an older Android app, which cannot yet stay in the background, the back button is the system's again.
After an ERPlora update, a screen that tab had not opened yet still opens (from a tile, "My apps", the menu or
any button), in a fresh load of the page, which already brings the new version; a tap never does nothing. If
the server does not answer (offline or on a flaky network), the person stays where they were and a notice says
"Could not open <app>. Check the connection and try again." ("that page" when the screen is not an app's), with
"Retry", which tries again and opens it as soon as the server answers.
Involved: none

### BASE-F06 See the apps' panels on the Home
Status: done
Actor: owner, administrator, manager, employee
Screen: Home · Summary
Steps:
  1. Under the list is the board, with its panels from the moment the Home opens ("Loading widgets…" only while
     it is not known which ones are theirs).
  2. Each panel is a card with its title and icon: a figure (with what it counts under it, if its app says
     so), a list with bars, a timeline, a chart or a piece of its app's screen, with its texts in the language
     of whoever is looking. In a list with bars, each bar measures how big its figure is against the biggest
     one of the list, whatever its sign; a negative figure, such as a cash discrepancy where money was missing
     or a product with stock below zero, shows in red and with its sign (-€0.40), and the others keep the
     panel's colour or, if its app gives each row a colour, their own row's. The red of a negative figure
     always wins over its row's colour.
  3. In a chart of days, each bar has its weekday under it (or its date, if it spans more than a week) and
     above them show the day and its amount: the last bar's until you tap another. A day below zero has its
     bar as tall as its figure, in red; the others keep their colour.
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
old or made-up figure. A row of a list with bars (or a day of a chart) that has no figure, such as a cash
session closed without a count, shows a dash (—) and no bar, never a zero; a real zero does show as zero
(€0.00). If the board cannot be read: "Could not load the panels" with "Retry".
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
Status: done
Actor: owner, administrator
Screen: The bell
Steps:
  1. A notice between apps (for example, "sale charged" towards Invoicing) ran out of retries.
  2. An administrator's bell goes up at once, without waiting or reloading, and opened it shows "Failed
     events" with how many there are.
  3. Tapping the row opens "System" on "Failed events", where they are resent or discarded (BASE-F43).
  4. When none is left, the row disappears.
In: how many notices of this business were left undelivered, only for whoever runs the business.
Out: nothing.
If it fails: an employee or a manager does not see the row. If it cannot ask, the bell keeps what it
last knew; if it never knew: "Could not check the notifications. They will show up when the connection is
back.".
Involved: BASE-F40

### BASE-F11 Go to erplora.com to manage or upgrade the plan
Status: discarded — without the one-time pass: if the browser does not have the erplora.com session open, you sign in with the account on arrival; the pass belongs mostly to erplora.com (saas#190)
Actor: owner, administrator, manager, employee
Screen: Side menu, top bar
Steps:
  1. At the foot of the side menu, under the QR code and lined up with it, is "Upgrade plan". Any profile
     sees it; what can be done on arriving is decided by erplora.com according to who comes in. With the
     menu folded to its icons (desktop), only its icon stays, which says "Upgrade plan" on hover. Only in the
     browser: the installed app does not have it.
  2. They tap it: this business's plan page on erplora.com opens in a new tab.
  3. The owner, the administrator or the manager who came in with their account also has, at the top right,
     "erplora.com", with a cloud (on a phone, "Manage on erplora.com", the first one of "More options").
  4. They tap it: this business opens on erplora.com's panel, in a new tab; in the installed app, in the device's
     browser. The Hub stays where it was.
In: the business they are in.
Out: nothing saved in the hub.
If it fails: if the hub does not know which business it belongs to, neither of the two shows (never a button that
does nothing). If the installed app cannot open the browser, it says so: "Could not open that page. Try again.". An
employee, a session opened with a PIN or with the badge and the Google Play app do not have "erplora.com".
Involved: BASE-F40

### BASE-F12 Ask the assistant to go over the setup
Status: done
Actor: owner, administrator, manager, employee
Screen: Home · Summary
Steps:
  1. In "Finish setting up your business", they tap "Ask the assistant" (or ask it from its panel).
  2. The assistant reads the same list as the Home, with what that person may see, and tells them what is
     missing and where it is done; each step keeps its "Set up" in the list.
In: the list of what is missing, with the permissions of whoever asks.
Out: nothing saved.
If it fails: without the assistant, the steps keep leading to their screen from the list.
Involved: BASE-F103

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
  2. The amount of a "Paid" app is on erplora.com's Store; whoever runs the business opens it from "Upgrade
     plan" (BASE-F20).
  3. "Paid" gathers only the apps subscribed to separately: a free one never shows there. If none is sold
     separately (today, every app comes with every plan), there is no "Paid" nor "Price", and a link to "Paid"
     opens "Add apps".
In: whether each app is subscribed to separately and what the business has subscribed to on erplora.com.
Out: nothing saved. The hub neither charges nor shows amounts: the price and the purchase are erplora.com's.
If it fails: without the list, as in "My apps" (BASE-F14).
Involved: APPS-F01, APPS-F07

### BASE-F18 Install an app
Status: done
Actor: administrator
Screen: Apps
Steps:
  1. The apps the business uses are already in "My apps" and in the menu; a paid one shows in both by itself,
     without reloading, as soon as it is subscribed to on erplora.com (BASE-F20).
  2. In "Add apps", whoever runs the business looks for an app the business does not use, "Off", and presses "Turn
     on". If it needs other apps that are off, it asks first, naming them (BASE-F19).
  3. The app becomes "Installed" at once and shows in "My apps" and, without reloading, in the menu of every device
     of the business. The counter at the top adds one: from "16 of 20 apps turned on" to "17 of 20 apps turned
     on".
In: the chosen app, the ones it needs and what the business has subscribed to on erplora.com.
Out: the app running in this business, chosen by it: it counts towards its plan's limit of apps.
If it fails: with the plan's limit reached nothing is turned on and "Your plan’s app limit" shows: "You have
reached the 20-app limit of your plan. Upgrade your plan or turn one off.", with "Upgrade plan" for whoever runs
the business in the browser (not in the installed app). A paid app not subscribed to offers no "Turn on"
(BASE-F20). Any other failure shows in a notice with the app's name and the reason, which stays until it is
closed.
Involved: APPS-F07

### BASE-F19 Know what else comes with an app
Status: done
Actor: administrator
Screen: Apps
Steps:
  1. In "Add apps", the "Comes with" column names the apps each one needs (for instance, "Sales & POS" comes
     with "Customers" and "Taxes"): whoever has one also has the ones it brings.
  2. A paid app the business has because another one it subscribed to needs it says "Included with" and the
     name of that other one under "Price".
  3. On pressing "Turn on" for an app that needs others that are off, it asks first and names them: "Turn on
     Reservations?" — "Reservations needs Tables: it turns on with it.".
  4. On confirming with "Turn on", the notice also names the ones turned on with it: "Reservations is on. Also
     turned on: Tables.". The ones that come this way do not count towards the plan's limit of apps: only the
     chosen one does.
In: what each app needs and which ones are off.
Out: nothing saved while asking; on confirming, the app and the ones it needs running (BASE-F18).
If it fails: if a paid app brings another paid one that has not been subscribed to, the two are subscribed to
together: until then, "Needs a subscription". With "Cancel", nothing changes.
Involved: none

### BASE-F20 Try to use an app that needs a subscription
Status: done
Actor: owner, administrator, manager, employee
Screen: Apps
Steps:
  1. A paid app the business has not subscribed to shows in "Add apps" and in "Paid" with "Needs a
     subscription", and is neither in "My apps" nor in the menu.
  2. Whoever runs the business, in the browser, sees "Upgrade plan" next to it, which opens this
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
Status: done
Actor: administrator
Screen: Apps
Steps:
  1. An app being set up (BASE-F22) does not finish because its data could not be prepared. The hub tries again by
     itself: after a minute, after 5 minutes, after 15 and then every hour.
  2. Its row, in "My apps", says "Could not turn on" and, to whoever runs the business, offers "Retry" and "Turn off";
     whoever does not run it sees the state, with no buttons. Meanwhile the app does not open and its screen says "{app}
     could not be set up" — "Go to Apps to try again. Nothing of the business was lost.".
  3. "Retry" asks for it again: "Turning on {app}… It will be ready in a moment." and the row goes back to "Turning
     on…".
In: the app that could not be set up.
Out: the activation asked for again (`base.app.activation_requested`).
If it fails: if it fails again, it says so again with its "Retry". If it was no longer waiting, because another device
tried it again, a notice shows with the app's name and "This app is not waiting to be set up again.", which stays
until it is closed.
Involved: none

### BASE-F22 Follow an app being turned on while moving around
Status: done
Actor: administrator
Screen: Apps
Steps:
  1. Whoever runs the business turns on an app (BASE-F18) whose data is not prepared yet in this business: one that
     reached ERPlora after the business was born. The others have no wait: they are on at once (BASE-F18).
  2. "Turning on {app}… It will be ready in a moment." shows; its row says "Turning on…", with "Turn off", and "My apps"
     on the Home says "Activating…", without opening. The person can go to another screen: it goes on by itself. It is
     not in the menu yet.
  3. If its screen is opened by its address, it says "{app} is being set up" — "It opens in a moment: this page shows it
     as soon as it is ready.".
  4. When it is ready it opens like any other: it turns "Active" with "Open", shows in the menu of every device of the
     business without reloading and its screen says "{app} is ready" — "It can be used now.", with "Open {app}".
In: how the activation is going.
Out: the app running in this business (`base.app.enabled`).
If it fails: BASE-F21.
Involved: none

### BASE-F23 Turn an app off
Status: done
Actor: administrator
Screen: Apps
Steps:
  1. In "My apps", whoever runs the business presses "Turn off" on an app's row.
  2. It always asks, with the app's name: "Turn off Reservations?" — "It leaves the menu for everyone in this
     business. Nothing is deleted: turned on again, it has its data.". If others that came only for it go with
     it, it names them: "Tables turns off with it: only Reservations needed it.".
  3. They confirm with "Turn off": "Reservations is off. Also turned off: Tables.". Both leave "My apps" and,
     without reloading, the menu of every device of the business; their screens say the app is not available
     (BASE-F26) and the counter at the top takes one away.
  4. In "Add apps" they stay, with their icon, their name and "Off": from there they are turned on again
     (BASE-F24).
In: the business's apps, what each one needs and which ones the business chose.
Out: the app turned off in this business, and the ones that came only with it, with their data intact.
If it fails: if another running app needs it, or the app itself refuses, nothing changes (BASE-F25). With
"Cancel", nothing either.
Involved: VERIFACTU-F32

### BASE-F24 Turn an app on
Status: done
Actor: administrator
Screen: Apps
Steps:
  1. In "Add apps", whoever runs the business presses "Turn on" for an app they turned off, which shows "Off".
  2. If it needs others that are off too, it asks first and names them (BASE-F19); if not, it turns it on without
     asking.
  3. The app comes back to "My apps" and to the menu, without reloading, with the data it had: "Reservations is
     on." and, if it came with others, "Also turned on: Tables.".
In: what the app needs and what the business has subscribed to.
Out: the app running in this business, chosen by it.
If it fails: with the plan's limit of apps reached, the notice of BASE-F18 with "Upgrade plan"; a paid app not
subscribed to cannot be turned on (BASE-F20). Moving to a lower plan turns nothing off: with more chosen apps than
the new plan has, all of them keep running and only no other can be turned on until it is below.
Involved: none

### BASE-F25 See an app refuse to be turned off
Status: done
Actor: administrator
Screen: Apps
Steps:
  1. Whoever runs the business presses "Turn off" on an app another running one needs (for instance, "Tables"
     while "Reservations" is on), or on one that refuses while it has something of its own halfway (VeriFactu,
     with records the AEAT has not accepted yet: VERIFACTU-F32).
  2. The hub changes nothing: above the table "Nothing was changed" shows with what has to be done first, "Turn
     off Reservations first." (without asking), or, after confirming, with the app's own reason in the language of
     who asks: "VeriFactu still has 1 record to send to the AEAT. Wait until it is sent or fix it before turning it
     off.".
  3. The notice stays until it is closed or another app is turned on or off; the app stays "Active".
In: the running apps that need it, or the reason of the app that refuses.
Out: nothing.
If it fails: without a reason of the app's own, the same notice says it could not be changed, with the app's name
and what the hub answered.
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
     to.", with "Go to Apps" and, for whoever runs the business in the browser, "Upgrade plan".
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
Status: discarded — merged into BASE-F40
Actor: owner, administrator
Screen: System · Usage and plan
Steps:
  1. They tap "System" in the side menu: "Usage and plan" opens, which joins what was in "Resources" and "Plan and limits".
  2. The people, the devices and the apps of the plan are in "What your plan includes" (BASE-F40).
In: the same as BASE-F40.
Out: nothing saved.
If it fails: BASE-F40 says it.
Involved: BASE-F40, BASE-F57

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
In: the file, of 20 MB at most (with the own photos of its products and services, INVENTORY-F33).
Out: nothing saved until it is loaded.
If it fails: "The file could not be read: {reason}" with the reason (it is not a .blueprint.zip, it is
damaged, a newer version of ERPlora made it or it is larger than 20 MB) and it stays on the choice.
Involved: none

### BASE-F31 Review and load what the file brings
Status: done
Actor: owner, administrator
Screen: Settings · Data and backups › Import
Steps:
  1. After choosing a template or a file, "Review what it brings" shows: "Name", "Type" ("Template" or
     "Backup"), "Language" and "Country" by name, how many "Apps" and, for a file, when it was made
     ("Created").
  2. Below, one box per app with what it brings (each part and its rows). The ones on in the business and the
     ones the load turns on come ticked: an app of the template or the file that is off says "It is off in your
     business: loading it turns it on.". An app only its data names, or one the plan does not include, says
     "This app is off in your business: nothing of it will load." and one this business does not have, "This
     business does not have this app: nothing of it will load.". A template's
     customers stay out: "Personal data: it loads only from a backup.". What the Hub never loads (people,
     PINs, fiscal data) shows in "Never loaded here".
  3. Untick the apps not wanted and tap "Import" ("Importing…"), or "Choose another" to go back.
  4. When it ends, the report shows (BASE-F32). What the business already had stays as it was: nothing is
     duplicated nor overwritten.
In: the template or the file and the apps ticked.
Out: the apps ticked that were off, turned on before loading, with the ones they need and within the plan's
limit of apps, as if they were turned on in Apps (`base.app.enabled`); in each app ticked, what it brings and
was missing, added as if it were added by hand in that app (its categories, products, services, areas,
tables and, from a backup, customers), and the report kept (`base.blueprint.imported`).
If it fails: "The import failed: {reason}" and it stays on the review; with no app ticked, "Choose at least
one app." and it cannot be imported; if none of its apps can be turned on here, "Nothing of this file can
load in your business: none of its apps can be turned on here.". An app that could not be turned on (the
plan's limit of apps, an app the plan does not include) stays off, loads nothing and the report says why;
the rest loads.
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
Status: done
Actor: owner, administrator
Screen: Settings · Data and backups › Reset
Steps:
  1. In "Reset", "Reset the business": "Removes for good the data you mark. It cannot be undone: if in
     doubt, export a copy first.", with "Export a copy first", which opens "Export".
  2. It says what is never removed: "Only what each section lists here is removed. Sales, invoices, fiscal
     records, people and their access, files and the business's settings always stay.", and "Before emptying, a
     full copy of the business's data is made and kept for 90 days, in «Copies» below.".
  3. One row per section (an app) that has something, with what it has (each part and its rows) and its total.
  4. Tick the sections and tap "Reset the business": "This cannot be undone", with "{n} rows will be removed for
     good:" and the breakdown. Type the business's name ("Type «{name}» to confirm") and tap "Remove for good" (or
     "Cancel").
  5. "Copying the business's data before emptying…" shows, with "Then {sections} will be emptied. You can leave this
     screen: it goes on by itself.", and then "Emptying {sections}…". Meanwhile no other is offered: "A reset is under
     way: wait for it to finish.".
  6. "Business reset:" shows with one line per section ("{app} — {n} rows removed") and "A full copy of the data from
     before is kept in «Copies».", and the list is worked out again.
  7. Below, "Copies of the data": one row per copy, with why it was made ("Before a reset" or "When the business was
     deleted"), its date, its size and "Download". With none: "No copies yet: one is made before each reset.".
In: what each section has and what is ticked.
Out: a copy of all the business's data, kept for 90 days, and then what is ticked, removed for good
(`base.hub.data_reset`).
If it fails: the reason shows in the dialog, which does not close: a name that is not the business's, "The
name does not match.". If the copy cannot be made, nothing is emptied: "Nothing was emptied", with "The copy of the
data could not be made, so nothing was emptied." and "Try again", with the same sections. If emptying is what fails,
the copy is kept: "The sections could not be emptied, so nothing was removed. The copy of the data from before is
kept.". Who does not administer the business reads "Only an administrator can undo imports or reset the business.".
Involved: none

### BASE-F38 See the Home up to date after importing a template
Status: done
Actor: owner, administrator
Screen: Home · Summary
Steps:
  1. While the business has nothing a template brings (a business is born with every app off), who administers
     it sees on top "Start with a business like yours" ("Choose the one most like yours: we turn on its apps and
     load its catalogue in one go. Then put in your own details."): up to four templates, one per kind of
     business and in their language when
     there is one (those of its country first), with their description and "Use this one"; "See all templates" opens "Data and backups" and "Not now"
     closes the card on this device.
  2. Tap "Use this one": "Preparing «{name}»…" while its apps are turned on and it loads, with no screens in
     between.
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

### BASE-F39 Open System and move between its tabs
Status: done
Actor: owner, administrator, manager, employee
Screen: System · Usage and plan
Steps:
  1. They tap "System" in the side menu, or come from the bell's "Failed events" row.
  2. At the bottom there are four tabs, in this order: "Usage and plan", "Updates", "Failed events" and "Logs". "Usage and
     plan" opens. The tab chosen stays in the address: a link or a reload opens the same one.
  3. A tab that does not exist opens "Usage and plan", and so do the old links to "Resources" and to "Plan and limits"; the
     old backups one leads to "Settings" › "Data and backups".
  4. Whoever is neither the owner nor an administrator sees three: "Logs" does not exist for them and, if they ask for
     it, "Usage and plan" opens. In "Usage and plan" they read "Only the owner or an administrator can see how much the
     hub is using." and in "Failed events", "Only the owner or an administrator can see the failed events.", with
     no "Retry".
In: the person's role in the business; whoever does not run it is never asked for anything the hub would refuse.
Out: nothing saved.
If it fails: each tab says its own (BASE-F40 to BASE-F43).
Involved: BASE-F40

### BASE-F40 See what the business uses and whether to upgrade the plan
Status: done
Actor: owner, administrator
Screen: System · Usage and plan
Steps:
  1. They open "System": "Usage and plan" opens. While it loads: "Reading the system…". At the top, their plan ("Starter
     plan") and "Upgrade plan", which opens this business's plan page on erplora.com (BASE-F11); in the installed app, or
     where that link does not appear, with no button, "Plans are managed from your ERPlora account, on erplora.com.".
  2. Below, a line tells them whether to upgrade. In green, "Your plan is enough". In amber, "You should upgrade: {motive}",
     with the files or the month's messages from 80 %: "you are almost out of space for files", "the assistant's messages
     are almost spent this month" or "WhatsApp messages are almost spent this month". In red, "You have to upgrade:
     {motive}": "no more files fit", "the assistant's messages are spent this month", "WhatsApp messages are spent this
     month" or "your business runs out of capacity at its busiest moments". With several motives, the most serious wins
     and, among equals, the fullest.
  3. "What your plan includes", from the fullest down: "Files" ("{used} of {limit}", with "Measured on {day}"), "Apps",
     "People" and "Devices" ("{used} of {limit}"), and "Assistant" and, with its app on, "WhatsApp" ("{used} of {limit} a
     month"), each with its bar, in the colour of the line at the top. From 80 %, the files and the messages say "Close";
     on reaching the limit, any of them says "Full".
  4. People, devices and apps at their limit do not change the colour at the top: a Free business with 1 of 1 device is
     fine. Under the green line it reads "People at the limit: to add more, upgrade the plan.".
  5. With a limit of 0, "{used} · No limit", with no bar. Messages cannot be that: with 0, "Your plan does not include the
     assistant" or "Your plan does not include WhatsApp", with no bar, and they are no motive for anything.
  6. At the end of the list, "Capacity": "{used} of {limit} connections", the highest measured today against what it
     really has (what its plan includes or, if that is less, what the service gives), with its bar. It never goes by
     percentage, because with a limit of 1 the first operation of the day is already 100 %, but by the times someone got
     "Too many requests. Try again in a moment.": "fell short {count} times this week". Then, if a bigger plan would give
     more, it moves to the top of the list and the line at the top turns red.
  7. If their plan already includes all the capacity the service gives, a bigger plan would give them no more: the row
     offers no upgrade, does not turn the top red and, when it falls short, says "You already have the maximum capacity:
     tell us in "Report a problem".".
  8. "For your information", what no plan limits, with no bar or pill: "Requests this month", the ones the business has
     served since day 1; "Active now", the people with activity in the last 5 minutes; "Last 30 days" and "Database size",
     with "Measured on {day}". Neither CPU nor memory: they cannot be attributed to a business, so they do not appear, nor
     does any sentence in their place.
  9. With motives the hub knows without asking erplora.com (the files, the capacity and WhatsApp), the bell of whoever
     runs the business shows the "Plan limits" row, which adds one per motive and opens "System" on "Usage and plan".
     Without them, the row goes away.
  10. Whoever runs the business can ask the assistant the same ("how much space do I have left?", "how many requests
      have we had this month?") and it answers with these figures.
In: what is measured of this business: every night, what its files and its database take up and the people who had
activity; during the day, its requests, its connections and who has activity. The plan's limits erplora.com passes to the
hub, the apps it chose, the assistant's messages erplora.com counts and WhatsApp's.
Out: nothing saved by looking at the screen. What is measured stays per business and day, and erplora.com collects it
every night so ERPlora's team sees the same (HUBS-F22).
If it fails: "We could not read the system" — "The figures and the logs are not available right now. You can
try again." with "Retry". What has not been measured yet says so, never with a zero: before the first night, "Measured
every night: the first figure comes tomorrow."; with no measure of the capacity or the requests today, "Not measured today
yet."; WhatsApp before erplora.com sends its figures, "Not measured yet."; if the requests or the times it fell short have
been counted for less than their period, they say "Since {day}". The assistant is asked of erplora.com apart: if it does
not answer, its row says "Not available right now", with no figure, and the screen goes on; the same if WhatsApp cannot be
read. In a demo, instead of everything: "Use is not measured in a demo: its data is deleted when it ends.". While the hub
does not know the plan: "We do not know this business's plan yet: it shows up as soon as erplora.com sends it." and, under
"What you use", the figures with no limit, bar, pill or line at the top. Whoever does not run the business reads what
BASE-F39 says.
Involved: BASE-F10, BASE-F11, BASE-F39, BASE-F57, BASE-F72, BASE-F73, BASE-F108, HUBS-F21, HUBS-F22

### BASE-F41 Know which version is running and what has been updated
Status: discarded — the version and its date, yes; apps no longer have their own version (they are all released together with the hub) and there are no notes for each version to show yet (hub#576)
Actor: owner, administrator
Screen: System · Updates
Steps:
  1. They open the "Updates" tab. The title is "What we have updated" and a pill says which version the hub is
     on. While it loads: "Reading the version…".
  2. Below, the day it was updated or, when that is not known, "We do not know when this version was
     published.": never a made-up date.
  3. And: "This hub updates itself when we publish a new version, without stopping the service: there is nothing
     to install.". There is no button to update.
  4. Whoever does not run the business sees the title and that text, without the version.
In: the version running and when it was published.
Out: nothing saved.
If it fails: "We could not read the system" — "The figures and the logs are not available right now. You can
try again." with "Retry".
Involved: none

### BASE-F42 See the log of what happened in the system
Status: done
Actor: owner, administrator
Screen: System · Logs
Steps:
  1. They open the "Logs" tab: the title is "Event log". For whoever does not run the business the tab does not
     exist (BASE-F39).
  2. They see the last 50 events between the business's apps, newest first, with "Time", "Level" ("Info",
     "Warning" or "Error", in a pill) and "Event": its name, the app that recorded it and what happened to it in
     their language (delivered, waiting, in "Failed events"…). Never what it carried.
  3. They search with "Search event…", filter by level and go 20 at a time. On a phone, each event is a card
     headed by its time.
  4. The log gets up to date by itself when a notice fails, is resent or is discarded; the rest, when the tab
     opens again.
In: the last events of this business, never another's.
Out: nothing saved.
If it fails: "The log could not be loaded. Check the connection and try again." with "Retry". With no events:
"No events yet: nothing has gone between this business's apps.".
Involved: none

### BASE-F43 See the failed events
Status: done
Actor: owner, administrator
Screen: System · Failed events
Steps:
  1. They come from the bell's "Failed events" row (BASE-F10) or tap the "Failed events" tab.
  2. While it loads: "Loading the failed events…". With events: "Fix the cause (a permission, an app that is
     off…) and resend. The event is never edited: if the cause is still there, it fails again and comes back
     here.".
  3. Each notice is a card with its name, how many times it was tried, from which app to which it was going (for
     instance, from "Sales & POS" to "Invoicing"), when it happened and its last error as it is, with "Resend" and
     "Discard". On top, "Resend all". If the app it was for is no longer on, the card says it cannot be resent
     until it is turned on, with no "Resend".
  4. The 100 most recent show; with more, the screen says how many show out of how many.
  5. The list and the bell get up to date by themselves when a notice fails, is resent or is discarded.
  6. With none: "All in order" — "No failed events. The queue of events lives in the database: a restart never
     loses it.".
In: the notices between apps of this business that ran out of retries, never another's.
Out: nothing saved.
If it fails: "We could not read the system" — "The queue of failed events could not be loaded. Check the
connection and try again." with "Retry" in sight: a failure never shows as "All in order". Whoever does not run
the business reads "Only the owner or an administrator can see the failed events.".
Involved: none

### BASE-F44 Resend a failed event
Status: done
Actor: owner, administrator
Screen: System · Failed events
Steps:
  1. Whoever fixed the cause (turned the app on, completed the business's details…) taps "Resend" on its card;
     the button is disabled while it works.
  2. "Event resent." shows, the card goes away and the bell goes down at once.
  3. The notice goes back to the queue with its attempts at zero and only the app that had failed gets it; if the
     cause is still there, it fails again and comes back here.
In: the notice chosen.
Out: the notice, back in the queue; `base.failed_event.retried`.
If it fails: "Could not resend:" and the reason: "that event is no longer in the queue; refresh the list."
(someone resent or discarded it first), "the app it was for is no longer on in this business; turn it on and
resend it." or "only the owner or an administrator can do it.".
Involved: none

### BASE-F45 Resend all the failed events
Status: done
Actor: owner, administrator
Screen: System · Failed events
Steps:
  1. After a failure that knocked over several notices, they fix the cause and tap "Resend all" (it only shows
     with notices in the list).
  2. They confirm in "Resend every failed event?" — "The ones that can be resent go back to the queue; those for
     an app that is off stay here." with "Resend all" (or "Cancel": nothing happens).
  3. How many were resent shows ("Events resent: 2.") and the list and the bell empty; if there was none that
     could be resent: "There was nothing to resend.".
  4. Every notice of the business that can be resent goes back to the queue, also those that do not fit in the
     list; those for an app that is off stay.
In: the business's failed notices.
Out: the notices, back in the queue; `base.failed_event.retried`, with how many.
If it fails: "Could not resend:" and the reason, as in BASE-F44.
Involved: none

### BASE-F46 Discard a failed event
Status: done
Actor: owner, administrator
Screen: System · Failed events
Steps:
  1. They decide a notice must never be delivered (it is repeated, it was done by hand) and tap "Discard" on its
     card.
  2. The "Discard this event for good?" window opens: it says which notice will never reach which app and that
     who discarded it, when and why are kept, warns "If it was a sale for Invoicing, that sale stays without its
     invoice." and asks "Why (optional)".
  3. They tap "Discard for good" (or "Cancel": nothing happens).
  4. "Event discarded (kept for the audit)." shows, the card goes away and the bell goes down.
In: the notice chosen and, if they want, why.
Out: the notice closed for good, with who, when and why; it is neither deleted nor tried again.
`base.failed_event.discarded`.
If it fails: "Could not discard:" and the reason, as in BASE-F44.
Involved: none

### BASE-F47 Report an error of the screen without anyone asking
Status: done
Actor: system
Screen: none
Steps:
  1. The person does nothing: when the screen has an error nobody caught (also while drawing a part of the
     screen, or in a wait that failed untreated), it is noted by itself.
  2. It is sent to the hub with no window, no capture and no question, even while the tab is closing.
  3. An identical error is not sent again within 30 seconds, and at most 50 different ones are remembered. A notice
     from the browser itself that is no error of the screen, the one saying it left part of the drawing for the next
     moment, is not sent: it breaks nothing and no app can fix it.
  4. The hub leaves it in its error log with the business, the person and the screen where it happened.
In: the error's message, its trace and the screen, only with a session.
Out: one line in the hub's error log; nothing is kept in the browser.
If it fails: nothing visible happens: the sending is not retried and makes no other report. With no session, or
with more than 30 reports a minute from the same person, the hub does not note it. To tell something by hand,
"Report a problem" in the user menu (BASE-F108).
Involved: none

### BASE-F48 Open Settings and move through its tabs
Status: done
Actor: owner, administrator, manager, employee
Screen: Settings
Steps:
  1. Tap "Settings" in the side menu, or arrive from a link on another screen.
  2. At the bottom, the tabs "General", "Business", "Printing" and "Data and backups", in the old hub's order;
     "General" opens (BASE-F62). The tab chosen stays in the link, so a saved link comes back to it and Back
     leaves Settings instead of walking its tabs. On the phone the four fit, whole.
  3. Old links still take you to their place: the one of the old "General" opens "General", the one of the old
     taxes tab opens "Business", and the one of a tab that no longer exists opens the first.
  4. In "Printing", "Printers and ticket" ("Add your printer and set up the printed and digital ticket") opens
     the Printing app; when it is not there, it says "Install the Printing app to add your printer and set up the
     ticket" and takes you to "Apps".
In: the business's apps.
Out: nothing saved.
If it fails: it does not fail: it is navigation. Each tab says in itself when it could not load its own (BASE-F49,
BASE-F29).
Involved: PRINTING-F06, BASE-F29, BASE-F49, BASE-F62

### BASE-F49 See the business's country
Status: done
Actor: owner, administrator, manager, employee
Screen: Settings · Business
Steps:
  1. In "Business", "Country" ("The one of its taxes and its invoices") says, in the person's language, the
     country the business was signed up with on erplora.com.
  2. It is not chosen here: below it reads "The country does not change once the business is ready.", because
     its invoices are of one country. While the business is being prepared, it is changed on erplora.com
     (HUBS-F15).
In: the country erplora.com signed the business up with.
Out: nothing saved; with it, the business's templates come first and "Finish setting up your business" knows
which steps are its own.
If it fails: if the business's details cannot be read, "Couldn’t load the business’s data" with "Retry". A demo
has no country: "—".
Involved: HUBS-F15, BASE-F01, BASE-F29

### BASE-F50 See the business's currency
Status: discarded — every app is in the business's currency except Appointments, which stays in euros even if the business's country pays in another currency: with Spain and Portugal it adds up, with a country of another currency it does not (hub#577)
Actor: owner, administrator, manager, employee
Screen: Settings · Business; Home · Summary and Home · Activity
Steps:
  1. In "Business", "Currency" ("Its country’s, for prices and totals") says the currency with its code and its
     name in the person's language: "EUR · Euro".
  2. It is not chosen: it is the one of the business's country, as in the market's payment terminals. A business
     without a country (a demo) is in euros.
  3. On the Home, the amounts of the panels (such as "Sales, last 7 days") and of "Activity" are in that currency,
     with its symbol and its decimals, as a till of that country prints them: "zł" in a business in Poland, "€" in
     one in Spain. While the business has not answered, the amount shows without a symbol, never in another currency.
In: the business's country.
Out: nothing saved.
If it fails: as in BASE-F49.
Involved: BASE-F49

### BASE-F51 Change the business's language on erplora.com
Status: done
Actor: owner, administrator
Screen: Settings · Business
Steps:
  1. In "Business", "Business language" ("The one of whoever has not chosen their own") says the business's
     language by its name.
  2. Tap "Change on erplora.com": the business's settings on erplora.com open in another tab (in the installed app,
     in the device's browser), where it is changed and "Save changes" is tapped (HUBS-F15). In the Google Play copy
     the button is not there: it is changed on erplora.com from a browser.
  3. Without reloading, "Business" shows the new language as soon as the business receives it; the same with the
     name and the time zone.
In: the language erplora.com saved.
Out: nothing saved in the business: it receives it from erplora.com (`base.hub.registered`). Whoever has not chosen
a language of their own in "My profile" and enters with their PIN sees the hub in the business's, not in their
browser's; with their account, in their erplora.com account's (BASE-F64).
If it fails: if the business does not answer, erplora.com keeps the change and sends it again (HUBS-F08);
meanwhile, "Business" stays with the previous one. Whoever does not administer the business does not see the
button: "Only the owner or an administrator changes them, on erplora.com.". In a demo, "This demo has no business
on erplora.com: its data does not change.".
Involved: HUBS-F15, HUBS-F08, BASE-F64

### BASE-F52 Enter with the erplora.com account
Status: done
Actor: owner, administrator, manager, employee
Screen: Access
Steps:
  1. Opens the business without a session. On a device that does not offer a PIN it goes straight to
     erplora.com's sign-in for this business; on a till that does offer it, **Access** shows and they tap the
     "Account" tab and then "Enter with your account".
  2. At erplora.com they sign in as always: email and password, Google or their verification code.
  3. They come back to the business already in, on the screen they had asked for (a link to a tab, such as
     `/settings#data` or `/system#plan`, comes back to that tab) or on **Home**. If this device asks for a PIN,
     the business already enters its tills with a PIN and the person has none yet, it first asks them to choose
     it (BASE-F54).
In: the account erplora.com checks; this browser.
Out: the person's session in this business and this browser turned into a trusted device of the business (it
shows in "Devices", shared until someone says otherwise). The session lasts a 12-hour shift on a shared device,
30 days on a personal one and 1 hour at most if the business always asks for the PIN.
If it fails: erplora.com says why they do not get in (credentials, verification, "You don't have access to this
hub"); the business keeps nothing until it comes back with the person identified.
Involved: BASE-F13

### BASE-F53 Enter from the erplora.com panel without typing the password again
Status: done
Actor: owner, administrator, manager, employee
Screen: Access
Steps:
  1. At erplora.com, with the session open, they tap enter their business.
  2. The business opens with the person already in, on **Home**, without going through any sign-in screen.
In: the one-time pass erplora.com gives.
Out: the same as BASE-F52: the session and this browser as a trusted device of the business, so it then offers
the PIN pad, shows in "Devices" and its mode can be changed.
If it fails: an expired or already used pass opens nothing: the business asks for erplora.com's sign-in again.
Involved: BASE-F52

### BASE-F54 Choose the PIN the first time one enters a till
Status: done
Actor: owner, administrator, manager, employee
Screen: Create your PIN
Steps:
  1. After entering with the account (BASE-F52) on a shared device of a business that asks for a PIN, where
     someone else already enters with theirs, and if the person has no PIN yet, "Create your PIN" shows — "With
     it you will enter this till without your password.".
  2. They type the PIN on the keypad of circles: "Choose a {n}-digit PIN" (4 or 6, whatever the business says).
  3. They repeat it: "Confirm your PIN". Once it matches it is saved and they go where they were going.
  4. "Not now" leaves it for later: they enter all the same and can choose it in **My profile** (BASE-F65).
In: the session just opened; the business's PIN digits.
Out: the person's PIN, stored encrypted; their face shows in "Switch user" at once and on the PIN pad of
**Access** within a minute.
If it fails: the repetition does not match: "The PINs do not match, try again" and back to the first step.
Repeated or consecutive digits: "That PIN is too easy to guess: avoid repeated digits (1111) and runs (1234).".
Someone else already uses it: "Another active person already has that PIN: choose a different one.". Without a
connection: "Could not save the PIN. Try again.". A business in which nobody has a PIN does not ask for it on
entering: the first one is chosen in **My profile**.
Involved: BASE-F52, BASE-F65

### BASE-F55 Enter with a PIN
Status: done
Actor: owner, administrator, manager, employee
Screen: Access
Steps:
  1. On a shared device of a business that asks for a PIN, **Access** opens on the "PIN" tab: "Enter your PIN",
     "…or pass your badge: no need to choose your name first." and "Choose your user" with a face per person
     (initials and name; never their email). With a single person, they are already chosen.
  2. They tap their name: "PIN of {name}" and the keypad show, with as many circles as the business's PIN has
     digits. The arrow ("Change user") goes back to the faces. The keypad shows whole, down to the 0 and the erase
     key, without scrolling the screen: on a tablet in landscape (in its browser too), a laptop or a low phone, the
     name shows without the big face and the keys sit a little closer, always the size of a finger.
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
Involved: BASE-F54, BASE-F67

### BASE-F56 Enter by passing the badge
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
Out: the same as BASE-F55.
If it fails: a card that is nobody's or whose owner is gone: "That badge opens nothing here. Enter with your PIN
or ask an administrator."; it counts as a failed attempt. The PIN pad stays available.
Involved: BASE-F55

### BASE-F57 Lose the session because it was opened on another device
Status: done
Actor: owner, administrator, manager, employee
Screen: Access
Steps:
  1. The business's plan covers a number of devices at a time (the Free one, one) and someone enters on another.
  2. The session of the device that has gone longest without an entry ends at that moment: what it has open stops
     updating.
  3. Its next screen is **Access**, which says at the top "Session opened on another device" — "Your plan covers
     one device at a time, so entering on another one closed the session on this one. Enter again to use it here,
     or add devices to your plan." with "Upgrade plan" in the browser (in the installed app it is not there: what
     sells is only on the web).
  4. They can enter again (and it closes the other one's) or go to erplora.com to extend the plan.
In: the devices the plan covers, which erplora.com passes to the business.
Out: the sessions of the devices left over, ended, and the reason kept on each one to tell it.
If it fails: with no limit in the plan nothing ends.
Involved: BASE-F11, BASE-F40

### BASE-F58 The session ends while working
Status: done
Actor: owner, administrator, manager, employee
Screen: Access
Steps:
  1. The session ends: the shift is over (12 hours on a shared device, 30 days on a personal one, 1 hour if the
     business always asks for the PIN), an administrator removes the device or the person leaves the business.
  2. The next thing they open takes them to the way in; if the session ended because the device was removed or
     the person left the business, what they have open finds out at once.
  3. On a till with the PIN pad, **Access** says at the top "Your session has ended" — "It expired or it was
     closed. Enter again." and, below it, the whole keypad (also on a tablet in landscape or a low phone): the next
     person enters with their PIN. On a device without the PIN pad it goes to erplora.com's sign-in, which brings
     them back in if their session there is still open.
In: the session that no longer exists.
Out: nothing saved; the half-made sale is kept by its app.
If it fails: without a network, the screen does not take the session as ended.
Involved: BASE-F13, BASE-F70

### BASE-F59 Close the session of a till nobody touches
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
Involved: BASE-F67

### BASE-F60 Switch user without losing the sale
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
Involved: BASE-F55, BASE-F56

### BASE-F61 Sign out
Status: done
Actor: owner, administrator, manager, employee
Screen: The user menu
Steps:
  1. They open the user card at the top of the side menu (on a phone, first the menu with the bar's button).
  2. They tap "Sign out".
  3. On a till with the PIN pad it goes back to **Access**, ready for the next person. On another device, erplora.com
     asks "Sign out of erplora.com?": "Sign out" ends it too and erplora.com asks to sign in again; "Stay signed in"
     leaves it open and shows the account's businesses.
In: the session.
Out: the session closed in the business; erplora.com's, only if the person confirms it.
If it fails: if the business does not answer, the session expires by itself.
Involved: none

### BASE-F62 Decide whether this device is shared or personal
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
Involved: BASE-F55

### BASE-F63 Open a hub that is not set up yet
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

### BASE-F64 Change my details, photo, language and appearance
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
appearance, which follow them on any device they enter, with their PIN or with their account. With "Use the
business’s language", they enter with a PIN in the business's and with their account in their erplora.com
account's (BASE-F51). The email is only for contact: it does not change the erplora.com account.
If it fails: if the profile could not be read, "Could not load the profile" — "Your details stay the same. Check
the connection and try again." with "Retry". On saving: "Could not save the profile"; a refused photo: "Could not
save the photo. Use a JPG, PNG or WebP of up to 2 MB."; preferences: "Could not save your preferences. Check the
connection and try again.".
Involved: BASE-F51

### BASE-F65 Change my PIN from My profile
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
Involved: BASE-F54

### BASE-F66 Choose how many digits the business's PIN has
Status: done
Actor: owner, administrator
Screen: Settings · General
Steps:
  1. With the PIN pad on (BASE-F67), under "PIN digits" they choose "4 digits" or "6 digits".
  2. It is saved at once. Below: "Everyone types the same number of digits, which is what lets the keypad enter
     at the last one instead of asking you to confirm. The PINs in use keep working until their owner changes
     them.".
  3. From then on, the PIN pad, "Create your PIN" and **My profile** ask for that length.
In: the choice.
Out: the length of the business's PIN. It does not touch the PINs there are.
If it fails: "Could not change it. Check the connection and try again.".
Involved: BASE-F67

### BASE-F67 Decide whether the till asks for a PIN and when it asks again
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
Involved: BASE-F55, BASE-F59

### BASE-F68 See the devices someone has entered on
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
Involved: BASE-F69, BASE-F70, BASE-F71

### BASE-F69 Name a device
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
Involved: BASE-F68

### BASE-F70 Remove a device that was lost
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
Involved: BASE-F58, BASE-F68

### BASE-F71 Remove at once the devices nobody uses
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
Out: those devices forgotten, as in BASE-F70.
If it fails: "Could not remove the unused devices. Check the connection and try again.".
Involved: BASE-F70

### BASE-F72 See the business's files
Status: done
Actor: owner, administrator, manager, employee
Screen: Files
Steps:
  1. Tap "Files" in the side menu. While it loads: "Loading files…".
  2. See the tree of folders on the left (on a narrow screen, the "Folders" selector), the open folder's path, what
     it holds in "Grid" (what shows first) or in "List", and "Space": what the business's files and its apps' take,
     against the plan's limit ("{used} of {limit}") or, if it has none, "{used} used · No limit".
  3. Go into a folder by tapping it in the tree, in the grid or in the selector, and come back through the path. The
     open folder stays in the address, so it can be shared with the team.
  4. Search by name in "Search files…", only inside the open folder; with no results, "No file in this folder
     matches “{search}”.".
  5. An empty folder says "No files" (to whoever administers the business, also "Upload a file or drag it here.").
  6. The folder brings itself up to date when someone on the team uploads, moves, renames or deletes something, from
     any device.
In: the files and folders of this business, never another's. The folders the apps use for their own things (the
website's images) do not show here.
Out: nothing saved.
If it fails: "The files could not be loaded" with the reason ("The file store did not answer. Try again in a
moment." or "Check the connection and try again.") and "Retry"; a failure never shows as "No files".
Involved: BASE-F40

### BASE-F73 Upload files and make folders
Status: done
Actor: owner, administrator
Screen: Files
Steps:
  1. In the open folder, tap "Upload file" and choose one or several, or drag them onto the manager ("Drop the files
     to upload them here"). While they upload: "Uploading {done} of {total}…".
  2. "Files uploaded." shows and they appear in the folder. If there was already one with the same name, it is not
     overwritten: the new one is kept as "name (1).ext" and "Uploaded as “{name}”: there was already one with that
     name." shows.
  3. For a new folder, tap "New folder", type the "Folder name" (up to 100 characters) and tap "Create folder".
     "Folder created." shows and the folder appears in the tree and in the open folder.
In: the files, up to 25 MB each, or the folder's name; the open folder.
Out: the file or the folder, in the business's files (`base.file.uploaded`, `base.file.folder_created`).
If it fails: each refused file says why, without stopping the others: "Could not upload “{name}”: {reason}", with
"That file weighs more than 25 MB, the most Files takes.", "Programs (.{extension}) can't be kept in Files: they
could harm whoever opens them.", "There is no space left for that file: your plan includes {space}." or "The file did
not arrive whole. Upload it again.". What was uploaded and what was refused show in a single notice: one notice shows
at a time and the new one closes the one before, never one on top of another. When making a folder, the dialog stays open with the reason: "That name is not
valid. Use a name without slashes or lone dots." or "There is already a file or folder with that name here.".
Whoever does not administer the business does not see the buttons and, if they try anyway, reads "Only an
administrator can change the files.".
Involved: BASE-F40

### BASE-F74 Preview and download a file
Status: discarded — Excel sheets (xlsx) and Word documents (docx) say "No preview" and are downloaded, and a data file (.json) is shown sorted but cannot be folded; the old hub's viewer showed them (hub#578)
Actor: owner, administrator, manager, employee
Screen: Files
Steps:
  1. Tap a file, or "Open" in its ⋮. A large viewer opens inside the hub, with the name as its title, "Download" and
     "Close".
  2. It shows images (whole in the viewer, never larger than the original, with "Zoom in" and "Zoom out"), PDFs (the
     first 30 pages; if it is longer, "Showing the first {shown} of {total} pages. Download the file to read it
     all."), text, logs and code, CSV and TSV as a table, data files (.json) tidied, audio and video. Of a very long
     text, "Showing the beginning of the file. Download it to read it all."; of a table of more than 500 rows,
     "Showing the first {shown} rows. Download the file to see them all.".
  3. Any other type: "No preview" with "This type of file can't be shown here. Download it to open it with an app on
     your device.".
  4. "Download", in the viewer or in the ⋮, saves the file with its name.
In: the file, which the hub reads from its store with the person's session; the browser never goes to the store and
the file is not kept in any cache.
Out: nothing saved.
If it fails: "The file could not be opened" with "The file's content did not arrive. Check the connection and try
again.", never a blank viewer; if it could not be downloaded, "Could not download “{name}”: {reason}".
Involved: none

### BASE-F75 Move and rename a file or a folder
Status: done
Actor: owner, administrator
Screen: Files
Steps:
  1. To rename, choose "Rename" (or "Rename folder") in the ⋮: a dialog with the current name already typed (up to
     255 characters). Tap "Rename" and "Renamed." shows.
  2. To move, choose "Move to…": "Move “{name}”" with the business's folders as a tree, starting at "Files"; choose
     one and tap "Move". The file or the folder can also be dragged onto a folder of the tree or of the grid. "Moved
     to “{folder}”." shows (to the very top, "Moved to “Files”.").
  3. A folder is moved or renamed with everything in it. If it is the open folder (its ⋮, beside the path), the
     screen follows it to its new place. It is never offered as a destination of itself or of its own folders.
In: the file or the folder and the new name, or the destination folder.
Out: the change, in the business's files (`base.file.renamed`, `base.file.moved`).
If it fails: the dialog stays open with the reason: "There is already a file or folder with that name here.", "It is
already in that folder.", "A folder can't be moved inside itself.", "That name is not valid. Use a name without
slashes or lone dots." or "That file or folder no longer exists. Refresh the list."; when dragging, "Could not move:
{reason}". Whoever does not administer the business does not see "Rename" or "Move to…" and, if they try anyway,
reads "Only an administrator can change the files.".
Involved: none

### BASE-F76 Delete a file or a folder
Status: done
Actor: owner, administrator
Screen: Files
Steps:
  1. Choose "Delete" (or "Delete folder") in the ⋮ of a file, of a folder or of the open folder.
  2. The screen asks: "Delete file" with "You are about to delete “{name}”. This cannot be undone.", or "Delete
     folder" with "You are about to delete “{name}” and everything in it. This cannot be undone.".
  3. Tap "Delete" (or "Cancel"). "File deleted." or "Folder deleted." shows. If the open folder was deleted, the
     screen goes up to the one above.
In: the file or the folder.
Out: the file or the folder, with everything it held, out of the business's files; there is no bin
(`base.file.deleted`).
If it fails: "Could not delete: {reason}", with "That file or folder no longer exists. Refresh the list." or "Your
session has expired. Sign in again and try once more.". Whoever does not administer the business does not see
"Delete" and, if they try anyway, reads "Only an administrator can change the files.".
Involved: none

### BASE-F77 Reach the plan's limit of people
Status: done
Actor: owner, administrator
Screen: Employees · Staff
Steps:
  1. In **Employees › Staff**, above the table, how many of the plan's places are taken: "{used} of {limit} places
     taken", "{used} people · no limit" or, if erplora.com has not said the plan, "{used} people".
  2. With every place taken, "Every place of your plan is taken" shows with "Remove on erplora.com someone who no
     longer works here, or move to a plan with more places."; on the web, with "Upgrade plan".
  3. To invite somebody else, "Invite on erplora.com" leads to "Members" of the business, where the limit applies
     (in the installed app, in the device's browser; the Google Play copy does not have it).
In: the people of the business and its plan's places, as erplora.com sends them.
Out: nothing saved.
If it fails: "The people of this business could not be loaded." with "Retry", never "Nobody is in this business
yet.".
Involved: BASE-F81, BASE-F83

### BASE-F78 Remove a person's PIN
Status: done
Actor: owner, administrator
Screen: A person's page
Steps:
  1. In **Employees › Staff**, they tap the person: their page opens.
  2. Under "PIN", "Has a PIN since {when}." and "Remove the PIN".
  3. They tap it: "Remove the PIN" with "{name} will stop entering the tills with their PIN. With their erplora.com
     account they still get in.". They confirm with "Remove the PIN".
  4. "PIN removed." shows and the page says "No PIN: the person chooses it in “My profile” or the first time they
     enter a till.".
In: the person.
Out: the person without a PIN: they leave the faces of the tills at once. Event `base.person.pin_removed`.
If it fails: "The PIN could not be removed."; only the owner changes the owner's way in: "Only the owner changes
the owner's way in.".
Involved: BASE-F81, BASE-F55

### BASE-F79 Give a person a badge or take it away
Status: done
Actor: owner, administrator
Screen: A person's page
Steps:
  1. On the person's page, under "Badge": "Pass the card and it fills itself: no need to click here first. You can
     also type the number, for a key fob or an engraved tag.".
  2. They pass the card over the reader (or type the number) and tap "Save badge": "Badge saved." and "Has a badge
     since {when}.".
  3. To take it away, "Remove the badge": "Badge removed." and "No badge.".
In: the person and their badge.
Out: the person's badge, kept without its number (only what lets it be recognised). Events `base.person.badge_set`
and `base.person.badge_removed`.
If it fails: "A badge has 4 to 64 characters: letters, digits, “-” and “_”.", "Somebody else already carries that
badge. A badge says who is at the till: two people cannot share it.", "Too many badges tried. Wait a few minutes
and try again.", "The badge could not be saved." or "The badge could not be removed.". Nobody registers their own:
"Nobody registers their own badge: ask another administrator.".
Involved: BASE-F56, BASE-F81

### BASE-F80 Bring back a person who left the business
Status: done
Actor: owner, administrator
Screen: Employees · Staff
Steps:
  1. Whoever left the business is no longer in **Employees › Staff**: they were removed on erplora.com.
  2. To bring them back, "Invite on erplora.com" and they are invited again in "Members" of the business, with
     their role (in the installed app, in the device's browser; the Google Play copy does not have it).
  3. When they accept, they are back on the list with what the business kept of them: their PIN and their badge
     still work.
In: the invitation on erplora.com.
Out: the person back in the business, with their PIN and their badge from before.
If it fails: until they accept, they show as "Not in yet".
Involved: BASE-F77, BASE-F81

### BASE-F81 Understand how each person gets in
Status: done
Actor: owner, administrator, manager, employee
Screen: Employees · Staff
Steps:
  1. In **Employees › Staff**, a row per person (on a phone, a card): "User" (with "You" on one's own; in a row, a
     name that does not fit is cut and shows whole on hovering over it), "Email" (only for whoever runs the business),
     "Role", "Access" and "Status".
  2. "Access" says how they get in: "Account" always, and "PIN" and "Badge" if they have them (for example,
     "Account + PIN + Badge").
  3. "Status" says "Active" or, if erplora.com already invited them and they have not come in yet, "Not in yet".
  4. They search with "Search person…". Whoever runs the business taps a row to open the person's page.
In: the people of the business.
Out: nothing saved. It updates by itself when somebody chooses or loses their PIN or their badge.
If it fails: "The people of this business could not be loaded." with "Retry".
Involved: BASE-F77, BASE-F78, BASE-F79

### BASE-F82 See the roles and turn on the ones an app brings
Status: discarded — the four roles of erplora.com are shown; whether an app brings its own roles to turn on is still to be decided in the new product, where the role is given when inviting on erplora.com (hub#579)
Actor: owner, administrator, manager, employee
Screen: Employees · Roles
Steps:
  1. In **Employees › Roles**: "These are the roles of this business. Each person gets one when invited on
     erplora.com, and it is changed there.".
  2. A row per role: "Owner", "Administrator", "Manager" and "Employee", with "Basic", "Always available", how
     many people have it and how many permissions it gives.
  3. Whoever runs the business has "Change roles on erplora.com" (in the installed app, in the device's browser; the Google Play copy does not have it).
In: the roles and the people of the business.
Out: nothing saved.
If it fails: "The roles could not be loaded." with "Retry".
Involved: BASE-F83

### BASE-F83 Give a person a role
Status: done
Actor: owner, administrator
Screen: Employees · Roles
Steps:
  1. In **Employees › Roles** or on a person's page, "Change roles on erplora.com" or "Open on erplora.com" leads to
     "Members" of the business (in the installed app, in the device's browser; the Google Play copy does not have
     them).
  2. There they change the role.
  3. Back here, the person shows with their new role and what they may do changes at once.
In: the role chosen on erplora.com.
Out: the person with their new role, as erplora.com sends it.
If it fails: whatever erplora.com says.
Involved: BASE-F82, BASE-F13

### BASE-F84 Approve with a manager's PIN
Status: done
Actor: employee, manager
Screen: An approval is needed
Steps:
  1. Somebody tries something their role does not allow and that the app lets a manager approve. Instead of an
     error, "An approval is needed" shows with "Approving: {action}", in the app's words and in the language of
     whoever asks; when the app says it with figures, with those of that very request (the percentage or the amount
     of a discount, in the business's currency, or the quantity), so the manager knows how much they approve. If a
     figure is missing or zero, the sentence does not name it.
  2. They read "Ask a manager to enter their PIN to approve it." and "…or to swipe their badge: nothing to press
     first.".
  3. Under "Who approves it?", the faces of those who may do it themselves and have a PIN (with only one, their pad
     shows at once). The manager taps theirs and types their PIN on the pad, whole in view without scrolling, the 0
     and "Erase" too ("Another person" goes back to the faces), or swipes their badge at any moment.
  4. The action is done once and "Approved by {name}" shows. The session of whoever asked is not closed.
  From the assistant too: the "yes" of its card opens the same dialog, with the figures of what it was asked.
In: the name and the PIN, or the badge, of whoever approves.
Out: an approval valid for that action, of that person, once and for two minutes; it is recorded in
**Employees › Approvals**. Events `base.approval.granted` and `base.approval.used`. It is spent together with the
action: if the action fails for a reason of the business, the approval stays unused and the same action, repeated
within those two minutes, goes through with it; if it went through, it is not repeated; two at once with the same one,
only one goes through. What the approved action does on the way in other apps (the rectifying invoice of a void, the
voucher sessions it gives back) goes with the approval, as when the manager does it themselves; nothing more: not what
is only looked up, nor the next action. Whoever is not of the business gets the refusal of always, without the
approval's question.
If it fails: the dialog stays open with "Those details do not approve this. Check the name and the PIN, and try
again.", "That person cannot approve this: ask somebody who may do it themselves.", "This no longer needs an
approval: do it again.", "This is not approved with a PIN.", the wait after too many attempts or "Could not send
the approval. Check the connection and try again.". With nobody with a PIN who may: "Nobody here can approve this
with a PIN. Somebody who may do it can swipe their badge.". "Cancel" hands the app back its refusal.
Involved: BASE-F85, BASE-F55, BASE-F56, SALE-F30, SALE-F31

### BASE-F85 Look up who approved what
Status: done
Actor: owner, administrator
Screen: Employees · Approvals
Steps:
  1. In **Employees › Approvals** (the tab exists only for whoever runs the business): "Each action that needed a
     manager's PIN: who asked for it, who approved it and what for. Nobody, not even an administrator, can edit or
     delete it.".
  2. A row per approval, the latest first: "When", "Action" (in words and in their language; with the figures of
     what was done with it, when the app gives them: an unused approval did nothing and has no figures), "Approved
     by", "Asked by", "With" ("PIN" or "Badge") and "State" ("Used" or "Not used").
  3. They search with "Search by person or action…" (by its figures too) and, in "Filters" (the funnel), filter by
     "When" (a day or a few days in a row), "Action" (the ones on the record, each once and without figures), "With"
     and "State".
  4. "Export CSV" downloads a file with the approvals the search and the filters keep, also the older ones the list
     no longer shows, with the same columns in their language; meanwhile it says "Exporting…".
In: the record of approvals.
Out: nothing; it is read only (the exported file changes nothing). It updates by itself with each approval.
If it fails: "Could not load the record of approvals." with "Retry"; with none, "Nobody has had to approve
anything in this business yet." (and the exported file brings its header alone). If it cannot export, a notice says
so with its reason and nothing is downloaded.
Involved: BASE-F84

### BASE-F86 Create an API key and copy its token
Status: done
Actor: owner, administrator
Screen: Employees · API keys
Steps:
  1. In **Employees › API keys**: "A key lets another system (your accountant's, your online shop) read or write
     this business's data through its API." and "New API key".
  2. In "New API key", the "Name" ("Accountant — invoices"), the "Requests per minute" ("From 1 to 10,000.") and
     "What this key may do": "Full access", "Read only", "Write only" or "Per app", ticking "Read" and "Write" on
     each app.
  3. They tap "Create key": "API key created" shows with "Copy the token now", "This is the only time the whole
     secret is shown. Keep it somewhere safe: it will not be shown again." and "Copy" (for two seconds it says
     "Copied"). "Done" closes it.
In: the name, the pace and what it may do.
Out: the key, of which the business keeps only what lets it be recognised. Event `base.api_key.created`.
If it fails: "The API key could not be created.", "Choose at least one app and what the key may do on it.", "That
app does not publish what the key would do on it." or "It could not be copied to the clipboard.". A business that
still shares its database with others (those signed up before every business was born with its own) has no "New API
key" (BASE-F89).
Involved: BASE-F89, BASE-F90

### BASE-F87 Rotate an API key
Status: done
Actor: owner, administrator
Screen: Employees · API keys
Steps:
  1. On the key's row, "Rotate".
  2. "Rotate the API key" with "“{name}” gets a new token. The current one stops working at once."; they confirm
     with "Rotate".
  3. The new token shows, only once, with "Copy".
In: the key.
Out: the key with a new token; the previous one stops opening anything at once. Event `base.api_key.rotated`.
If it fails: "The API key could not be rotated.", "That key was revoked: it never works again." or "That key no
longer exists. Refresh the list and try again.".
Involved: BASE-F86, BASE-F89

### BASE-F88 Revoke an API key
Status: done
Actor: owner, administrator
Screen: Employees · API keys
Steps:
  1. On the key's row, "Revoke".
  2. "Revoke the API key" with "You are about to revoke “{name}”. Any system using this token loses access at
     once. This cannot be undone."; they confirm with "Revoke".
  3. "“{name}” revoked." shows and the row stays as "Revoked", without "Rotate" or "Revoke".
In: the key.
Out: the key revoked for good; it is kept on the list. Event `base.api_key.revoked`.
If it fails: "The API key could not be revoked.".
Involved: BASE-F89

### BASE-F89 See the API keys and what each one may do
Status: done
Actor: owner, administrator
Screen: Employees · API keys
Steps:
  1. In **Employees › API keys** (the tab exists only for whoever runs the business), a row per key: "Name",
     "Token" (only its start), "Permissions", "State" ("Active" or "Revoked"), "Created", "Last use" ("Never" if
     unused) and "Limit".
  2. They search with "Search API key…". At the bottom, "API documentation" leads to the documentation.
In: the business's keys.
Out: nothing saved. It updates by itself when one is created, rotated or revoked.
If it fails: "Your API keys could not be loaded." with "Retry"; with none, "No API keys yet. Create one so that
another system can read or write your business's data.". A business that still shares its database with others
cannot have keys, because a key of its own could open another's data: instead, "Not available yet" and "API keys are
not available yet in this business." show, until it moves to its own.
Involved: BASE-F86, BASE-F87, BASE-F88

### BASE-F90 Read the API documentation
Status: done
Actor: owner, administrator, manager, employee
Screen: API documentation
Steps:
  1. With the documentation shown (BASE-F91), it opens from "API" in the side menu, from **Settings › General**
     ("Open the API documentation") or from **Employees › API keys** ("API documentation").
  2. They read "The API of this business: what its apps publish for other systems. To call it, create a key in
     Employees › API keys and send it as “Authorization: Bearer <key>”.".
  3. A section per app, with its calls (the method, the address and what it does); opening one, its "Parameters"
     and its "Body".
  4. "Download the OpenAPI file" saves it to take it to another tool.
In: what the business's apps publish.
Out: nothing saved. It grows or shrinks with the business's apps.
If it fails: hidden, "The API documentation is hidden in this business." and, for whoever runs the business,
"Show it in Settings › General"; if it does not arrive, "Could not load the documentation." with "Retry"; with
nothing published, "None of this business’s apps publishes its API yet.". If the business cannot have keys yet:
"API keys are not available yet for this business: you can read the documentation, but no system can call it
yet.".
Involved: BASE-F91, BASE-F86

### BASE-F91 Show or hide the API documentation
Status: done
Actor: owner, administrator
Screen: Settings · General
Steps:
  1. In **Settings › General**, under "API documentation", the switch "Show the API documentation" ("Adds a page
     with the documentation of the API, for whoever connects another system."). It comes off.
  2. Turning it on saves it at once and "Open the API documentation" shows and, in the side menu, "API" (between
     "System" and "Settings"), without reloading; turning it off, both go away.
In: the switch.
Out: the business's setting. Event `base.api_doc.settings_changed`.
If it fails: "Could not save the change." and the switch goes back to what was saved; "Could not load the
setting." with "Retry". Whoever does not run the business sees it off: "Only who runs the business can change
it.".
Involved: BASE-F90

### BASE-F92 Open and close the assistant's panel
Status: done
Actor: owner, administrator, manager, employee
Screen: Assistant
Steps:
  1. With the session open, they tap the "Assistant" sparkles in the top bar, next to the bell. Tapping them again
     closes it. On a phone, the sparkles and the bell (and "erplora.com", for whoever has it) go together in "More
     options" (with the bell's number), so the title stays centred: there, "Assistant" opens the panel and
     "Notifications", the bell.
  2. The panel comes in from the right. On a tablet or a computer it takes a column beside the screen and pushes it:
     they can keep working with the panel open. On a phone it covers the screen, over a dark veil.
  3. It closes with the "Close" ×, with the Esc key (wherever the cursor is, except in a window open over the
     panel), by tapping the veil on a phone, by tapping the sparkles again or with "Go to …" in an answer
     (BASE-F96).
  4. If it is left open, it stays open on changing screen and on reloading: the device only remembers whether it was
     open or closed.
In: the session.
Out: on opening it, the panel reads the assistant's messages the business has left this month (BASE-F104) and the
list of what is left to set up, for its shortcuts (BASE-F103); closing it asks for nothing.
If it fails: it has no failure of its own. Without a session (the way in, the PIN) there are no sparkles. Closing the
panel does not cut an answer already on its way: it keeps being written and, if it asks for a confirmation, the card
shows over whatever screen is there (BASE-F97).
Involved: BASE-F93, BASE-F97, BASE-F103, BASE-F104

### BASE-F93 Ask the assistant and read how it writes
Status: done
Actor: owner, administrator, manager, employee
Screen: Assistant
Steps:
  1. With the conversation empty, the panel shows the sparkles, "Ask me about your sales, your stock or anything
     about your business." and the setup's shortcuts (BASE-F103).
  2. They write in "Write a message…" and press Enter or "Send". With a keyboard, Shift+Enter starts a new line; on a
     touch screen, Enter starts a new line and "Send" sends. "Send" is off with the box empty and no attachments.
  3. Their message shows on the right just as they wrote it. Below, the assistant's bubble, with three dots that move
     until the first text arrives.
  4. While it answers, "Send" becomes "Stop", "Attach a file" and "Dictate by voice" turn off and the answer keeps
     appearing; the conversation scrolls down by itself. They can already write the next question, but it is not
     sent until this one ends.
  5. If they ask how something is done in ERPlora, what an option means or what a plan includes ("How do I open the
     cash register?"), the assistant searches ERPlora's documentation (the help, each app's and the plans) and answers
     only with what it says, citing which section it comes from; if the documentation does not cover it, it says so
     instead of making it up.
  6. If the assistant ends without saying anything, the bubble reads "(no answer)".
  7. "Stop" cuts what was left: what was already written stays, with "Stopped." below.
  8. Under each finished answer, "Read aloud" reads it with the device's own voice, if it has one, and "Stop
     reading" stops it.
In: what the person writes; the whole conversation travels with each question (BASE-F102).
Out: the question to erplora.com, which answers it and counts it in the month's messages (BASE-F104).
If it fails: without a connection, with the service down, without a plan or without messages: BASE-F106 and BASE-F104.
If the documentation cannot be searched at that moment, the assistant says so and does not answer from memory. "Stop"
does not undo an action that had already been done.
Involved: BASE-F102, BASE-F104, BASE-F106

### BASE-F94 Attach a file or dictate by voice
Status: done
Actor: owner, administrator, manager, employee
Screen: Assistant
Steps:
  1. To attach, they tap "Attach a file" and choose one or several: images, PDF, Word, Excel, text or CSV. Each one
     shows over the box with its name and its "Remove attachment" ×.
  2. They go with the next message, with or without text, and stay in the person's bubble by their name. They travel
     only once, with that question: afterwards the conversation only remembers what they were called.
  3. To dictate, they tap "Dictate by voice" (it only shows if the device can record). The browser (in the installed
     app, the device) asks for permission to use the microphone; while it asks, another tap does not open a second
     recording. While it records, the button turns red and is called "Stop recording"; after two minutes it stops by
     itself.
  4. On stopping, "Transcribing…" shows and the text lands in the box, after whatever was written. **It is not sent by
     itself**: the person reviews it and taps "Send", and what they ask goes through its card like any other request
     (BASE-F97).
In: the files (8 MB each and 20 MB among all those of a question) or the recording.
Out: the file travels with the question to erplora.com, which reads it; the recording goes through the business to
erplora.com's transcription. The browser never talks to erplora.com directly.
If it fails: in one line over the box, and the file is not attached: "menu.pdf is too large: 8 MB at most per file.",
"The files of one question add up to 20 MB at most.", "menu.zip cannot be attached: images, PDF, Word, Excel, text
or CSV." or "menu.pdf could not be read.". With the microphone blocked, "Microphone access is blocked. Allow it in
your browser to dictate." and, in the installed app (Android or Windows), where there is no browser, "Microphone
access is blocked. Allow it in your device settings to dictate."; a recording too long, "The recording is too long:
dictate a shorter message."; no voice, "Nothing was heard. Try again closer to the microphone."; and if it cannot be
transcribed, "The audio could not be transcribed. Try again.".
Involved: BASE-F93, BASE-F97

### BASE-F95 Read the answer: text, lists, tables and links
Status: done
Actor: owner, administrator, manager, employee
Screen: Assistant
Steps:
  1. The answer is painted with its format: bold, italics, code, headings, bulleted or numbered lists and tables.
  2. A table fits in the bubble: its cells break the text instead of widening the panel, also on a phone.
  3. A link is read by its text, without brackets nor address. It can only be tapped if it leads to a screen of this
     business (BASE-F96); any other address, from outside or made up, stays as text.
  4. What the panel does not understand (code blocks, images, quotes) stays as plain text. The person's message
     always shows just as they wrote it.
In: the assistant's text.
Out: nothing; it is only painted. The panel never paints HTML that comes in an answer.
If it fails: a badly written answer reads as text: it is never lost nor breaks the panel.
Involved: BASE-F96

### BASE-F96 Go to a screen from an answer
Status: done
Actor: owner, administrator, manager, employee
Screen: Assistant
Steps:
  1. If the answer names a screen of this business, "Go to …" with its name shows under the bubble (up to four,
     without repeating) and the mention itself can be tapped.
  2. It can lead to Home, Employees, Apps, Settings, My profile, Files (for whoever sees them), System (for whoever
     runs the business) and the screens in the menu of each app that is on.
  3. The button uses the name the person sees in the menu ("Go to Settings", "Go to Home" and, for an app, its name
     and the screen's), never the address.
  4. Tapping it opens that screen and the panel closes so it can be seen.
In: the screens the answer names; those of this business and of its apps that are on.
Out: the screen opened; nothing is asked for.
If it fails: a screen this business does not have (that of an app that is off, a made-up address) does not show as a
button nor as a link, and the answer carries the notice of BASE-F99. If the person may not see the screen they reach,
that screen tells them.
Involved: BASE-F92, BASE-F99

### BASE-F97 Confirm an action before it runs
Status: done
Actor: owner, administrator, manager, employee
Screen: Assistant confirmation card
Steps:
  1. The person asks it for something that changes data ("create the service Haircut at €15 for 30 minutes").
  2. Before doing it, "Run this action?" shows over everything, with the action, the app and its first data in one line,
     for example "Create in Services: Haircut · €15.00 · 30". An amount, every datum its app declares as money, shows
     in the business's currency (never in cents), also inside a datum that groups others, and the assistant
     understands it the same even if the app changes how it explains it: "at €15" shows "€15.00", never "1500". If
     the action names its own currency, the amount shows in it and with its decimals, as in Stripe or Square: a
     payment in dollars says "$15.00", and in yen, without decimals; a currency that does not exist is not made up:
     if the action no longer takes it in its data, no card shows (see "If it fails"); otherwise the amount shows as
     written and the action refuses it when it runs. If the action is done on something that has
     its own currency, the amount shows in that one: adding a line to a cart in dollars says "$12.50", and setting a
     price on a price list in yen, "¥1,500"; if that cannot be read (it does not exist or whoever asks cannot see it),
     the amount shows as written and the action decides. Every amount of a card is written the same way, on top or
     inside a datum that groups others: "$1.50" in both, never "US$1.50" beside it. One of "What will happen" that its app gives
     in another currency shows in its own: rectifying an invoice issued in euros says "Total: -€121.00" even though the business now charges in złoty, and
     the assistant says it in that same currency in its answer. A difference shows with its sign as on its app's
     screen, to see at a glance whether there is too much or too little (closing the till says "Difference: +€137.90" when there is too much, "-€4.90" when there is too little and
     no sign when it balances); a yes or a no, as "Yes" or "No"; a list that its app (the server) names, by its items
     one after another ("Printers: Till, Kitchen"; past four, the first three and how many more: "Till, Kitchen, Bar and
     2 more"; when an item carries a comma, such as a date, separated by semicolons: "Nov 2, 2026, 10:00 AM; Nov 9,
     2026, 10:00 AM") and any other, such as the lines of a sale or a list of codes, by how many items it carries; and a datum that groups others, such as a WhatsApp template, by its values, without the name of each one ("Template:
     cita_recordatorio · es · Ana, 10:00"; of a till count, the notes and coins counted remain: "50: 2"). A date and a
     time show as they are written in the person's language and at the business's hour ("Nov 2, 2026, 10:00 AM"; a day
     alone, "Nov 2, 2026"; a time alone, "9:30 PM"); a value of a closed list, with the name its app gives it ("Front
     desk", not the internal value); and a record, by its name when its app lets whoever asks read it ("Person: Eva
     Gil"): otherwise the card leaves it out, never by its code. Nor does it put the key its app uses to avoid doing
     the same thing twice on a retry (charging, sending a WhatsApp, printing): nobody can judge it, and the action
     receives it all the same when it runs. Everything shows in the person's language, also the
     name of each datum when the card puts it on its own line (BASE-F98): the
     same one its app calls it by, never a technical name. An action of the platform itself is named by the screen where
     it is done, for example "Change in Settings" or "Delete in Files". Each action shows with its own verb, never a
     generic one: rectifying an invoice says "Rectify in Invoicing". Two actions with the same name in two apps each
     say what they do: emptying a cart says "Clear in Cart & Checkout", removing one of its lines "Remove in Cart &
     Checkout" and taking a product's route away in the kitchen "Clear in Kitchen"; a cash count says "Register count
     in Cash register" and cash brought in or taken out "Register movement in Cash register", as their screens do,
     never "Add".
  3. "Run it" does it with the session of whoever asked, with the same permissions and the same checks as the button
     on its screen. "Cancel" or Esc do nothing: the assistant knows it was not confirmed and says so.
  4. What only reads (seeing the sales, looking up a customer) asks for no card; each action that changes something
     asks for its own.
  5. Under the answer stays the receipt of each action of the turn, with the action named as on its card: "Done:
     Create in Services", or "Not done, cancelled: …", "Not done, it failed: …" and "Not done, not allowed: …". If the
     person changes language, the earlier receipts show entirely in the new one, the app's name too.
In: the action, its data and its risk, as its app declares them; the business's currency, the one of the record it is
done on (read as the person) and, in "What will happen", the one its app gives; the business's time zone; and, if its
app declares it, the check it makes before the card, as the person: if it refuses the data (adding someone with a role
the business does not have, STAFF-F01), no card shows and the assistant tells it as its error.
Out: if accepted, the action done in its app, with the same event as if its button had been tapped.
If it fails: an action its app refuses goes back to the assistant as an error and it tells it; the receipt reads
"Not done, it failed: …". Data the action does not take (a country or a currency that does not exist, a value
outside its list) never reach the card: they go back to the assistant, which corrects them, and the person confirms
only once. If the page is reloaded with the card open nothing is done, and the answer ends in "The answer was cut
off." with "Try again".
Involved: BASE-F98, BASE-F99, BASE-F101

### BASE-F98 Dangerous actions: type to confirm, or not from the chat
Status: done
Actor: owner, administrator, manager, employee
Screen: Assistant confirmation card
Steps:
  1. An action its app marks as dangerous is not confirmed with one click: the card says, for example, "Delete in
     Services. Check each datum before going on.", puts each datum on its own line with its name in the person's
     language and asks "To confirm, type CONFIRM:".
  2. If its app declares it, the card first says, under "What will happen", what the action is going to do, as its
     app works it out for the person who asks and with their permissions. For example, when taking someone's PIN
     away it says whose it is ("Name: …" and "Email: …"), not just the person's code. What the app does not show
     that person does not appear on the card either.
  3. If the action names the records one by one, it says how many ("It acts on 3 records.") and asks to type that
     number instead of the word.
  4. If it does not name them (all of them, or those matching a filter), it is not done from the chat: no card shows, the answer reads "I
     cannot tell how many records this would change, so I do not do it from here. Open its screen, where you can see
     them." and the assistant explains where it is done.
  5. "Run it" can only be tapped when what was typed matches (regardless of capitals and of the spaces at the ends),
     and the business checks it again before doing it.
  6. Resetting the business and exporting a copy are never done from the chat: they are done in Settings › Data and
     backups.
In: the risk the app declares in each action, and its data; if it declares one, its preview.
Out: if accepted, as in BASE-F97.
If it fails: what was typed and does not match does not let it run; cancelling does nothing and the assistant counts
it as cancelled. If the preview cannot be read (the record is no longer there, or the person cannot see it), no card
shows and nothing is done: nothing is confirmed blind. The receipt says "Not done, it failed: …" or "Not done, not
allowed: …" and the assistant tells why.
Involved: BASE-F35, BASE-F37, BASE-F97

### BASE-F99 Check what the assistant says against what it really did
Status: done
Actor: owner, administrator, manager, employee
Screen: Assistant
Steps:
  1. When each answer ends, the panel compares it with what was really done in that turn: it does not trust what the
     answer says about itself.
  2. If it says it changed something ("I have created…", "has been saved…", "se ha guardado…") and in the turn no action
     was done (or it was cancelled, failed or was not allowed), "The assistant said it made a change, but no action
     was run. Nothing was changed." shows outside the bubble.
  3. If it writes an identifier that no lookup of the turn returned and that the person did not write: "This answer
     shows an identifier the assistant did not really read. Do not trust it.".
  4. If it points to a screen this business does not have: "This answer points to a screen that does not exist
     here.", and without "Go to …" (BASE-F96).
  5. The notices carry their alert icon, are not written by the assistant and stay with the message, also on
     reloading. A clean answer carries none.
  6. The receipts of BASE-F97 say what was really done, action by action.
In: what was done in the turn, with its result, and what its lookups returned.
Out: the notices and the receipts, kept with the conversation.
If it fails: "Done" means the action of its app ended without an error: if an app answers fine without having changed
anything, it is that action that has to say so. If the turn ends in an error, the bubble carries its failure
(BASE-F106), the notices of what it got to say and the receipts of what was indeed done.
Involved: BASE-F96, BASE-F97, BASE-F106

### BASE-F100 What the assistant can do depending on who asks: permissions and a manager's PIN
Status: done
Actor: owner, administrator, manager, employee
Screen: Assistant
Steps:
  1. The assistant works with the session of whoever is in front of it: it sees and does what that person would see
     and do with their buttons, in the business's apps that are on, and nothing else. An action they have no
     permission for is not offered to the assistant, which tells them so; one its app lets a manager approve is, as
     its button on the screen is.
  2. That action comes with its card, like any other. Tapping "Run it" opens "An approval is needed", the same as on
     the screen: a manager taps their face and types their PIN, or swipes their badge, and the action is done once,
     with whoever asked for it as its author. It is recorded in **Employees › Approvals**.
  3. If nobody approves it ("Cancel"), it is not done: the receipt reads "Not done, cancelled: …" and the assistant
     knows it.
  4. If it tries anyway an action without permission that nobody can approve, it is not done: the receipt reads "Not
     done, not allowed: …" and the assistant explains it cannot.
  5. What the assistant tells (lists, figures) is what that person may read.
In: the session of whoever asks, which signs each action; for what a manager approves, their PIN or their badge.
Out: the action done with that person as its author. The approval is good for that action of that conversation, once
and for two minutes, and it is spent together with the action (BASE-F84).
If it fails: if the permission is lost between offering the action and doing it, its app refuses it and the receipt
says so. An approval already used or expired does not let the action through: the receipt reads "Not done, it
failed: …" and the assistant tells it.
Involved: BASE-F13, BASE-F84, BASE-F97

### BASE-F101 Ask it for several things in a row
Status: done
Actor: owner, administrator, manager, employee
Screen: Assistant
Steps:
  1. The person asks for a chain ("create the category Drinks and the product Draught beer at €2.50").
  2. The assistant solves it in rounds: it reads what it needs without asking, asks for an action, it is done and it
     goes on. All it says goes to the same bubble, and what each round says in its own paragraph: never glued to the
     previous one.
  3. Each action that changes something asks for its own card (BASE-F97), one after the other: accepting the first
     does not accept the next ones. If more wait behind it, the card carries "Cancel all", which cancels this one and
     those left.
  4. If they cancel one, the assistant knows and decides how to go on. What was already done stays done.
  5. A request allows six rounds at most: it is a brake against loops, not an allowance. Past them, "I stopped: this
     needed too many steps. Ask for it in parts.".
In: the request; the result of each action, which goes back to the assistant.
Out: as many actions as cards accepted, each in its app and with its receipt.
If it fails: if an action fails half way, the assistant gets it and tells it; the earlier ones are not undone. With
the network cut half way, BASE-F106.
Involved: BASE-F97, BASE-F106

### BASE-F102 The conversation: what is kept, where and when it is deleted
Status: done
Actor: owner, administrator, manager, employee
Screen: Assistant
Steps:
  1. The conversation lives only in that browser tab: the business does not keep it. Reloading the page brings it
     back; closing the tab loses it. Closing the panel does not delete it.
  2. An answer that was being written on reloading stays with what had arrived and "The answer was cut off.", with
     "Try again".
  3. "New conversation", at the top of the panel, empties it and starts from scratch.
  4. On signing out (also when the till closes by itself for inactivity) it is deleted, and the answer that was
     arriving is cut. On switching user with a PIN, that of whoever left is deleted along with what they had written
     without sending and their attachments, and whoever arrives finds the panel closed and empty.
  5. What is kept: what the person wrote (of their attachments, only the name), what the assistant answered, its
     notices and its receipts.
In: the panel's messages; the sign-outs and the user switches.
Out: nothing outside the browser; with each question, the whole conversation travels to answer it.
If it fails: if the browser does not let it be kept (private mode, full storage), the conversation goes on while the
tab is open, but does not survive a reload. A kept one that cannot be read, or another person's, starts empty. A
conversation that is too long says "This conversation is too long: start a new one." with "New conversation".
Involved: BASE-F59, BASE-F60, BASE-F61

### BASE-F103 The assistant in the setup
Status: done
Actor: owner, administrator, manager, employee
Screen: Assistant
Steps:
  1. On the Home, while something is left, "Finish setting up your business" carries "Ask the assistant". It opens
     the panel with "Review your business's setup. Choose an option or write your question.".
  2. Opened from the bar, the empty conversation offers the same shortcuts: "What is left to set up?" and, for each
     pending step this person can do (up to four, in the list's order), "How do I set up “Your team”?", with the
     step's name as it shows in the list. The steps only an administrator can do and the "Not available yet" ones do
     not show as shortcuts.
  3. Tapping a shortcut asks it at once.
  4. From the setup (the button or a shortcut), before each question the assistant reads the list again: what is
     pending, what stops invoicing, what is done and what is an administrator's. A business that gets set up half way
     through the chat stops being described as not set up.
  5. What they ask it to do (turn an app on, load a template) goes through its card (BASE-F97).
In: the list of what is missing, with what that person may see (BASE-F01).
Out: the list, for the assistant; the normal conversation.
If it fails: if the list cannot be read, the assistant knows it and does not say the business is set up, and the
shortcuts are left at "What is left to set up?". Each step keeps its "Set up" in the list: with the assistant down,
nobody is left without a way out.
Involved: BASE-F01, BASE-F12, BASE-F97

### BASE-F104 See the assistant's plan, the usage limit and extend it
Status: done
Actor: owner, administrator, manager, employee
Screen: Assistant
Steps:
  1. On opening the panel, the assistant's messages the business has left this month are read. If they cannot be
     read, nothing is shown: never a made-up number.
  2. From 80 %, the foot says, for example, "You have 30 of 300 messages left this month." with "They renew on
     November 1.". Below 80 %, nothing.
  3. The count moves when each answer ends, without reloading.
  4. Once spent, the answer is "You have used all the assistant's messages of this month (300 of 300)." with "They
     renew on November 1.", and not a connection failure. The foot says the same, without repeating "Upgrade plan":
     "You have used all 300 messages of this month." with "They renew on November 1."; also when the panel opens
     with the month already spent.
  5. Whoever runs the business sees, in the browser, "Upgrade plan", which opens the plan's page on erplora.com in
     another tab; in the app installed from the store it does not show. Whoever does not run it sees "Ask whoever
     runs the business to upgrade the plan.". There are no message packs: it is extended by upgrading the plan.
  6. With a plan without the assistant, the foot says "Your plan does not include the assistant.", with "Upgrade
     plan" for whoever runs the business; the panel opens anyway.
In: the messages used, the limit and the day they renew, from erplora.com.
Out: erplora.com's plan page, in another tab. The business does not keep its own count of messages.
If it fails: if the plan cannot be read, nothing is shown and they can ask anyway: what erplora.com says when
answering is what counts.
Involved: BASE-F11, BASE-F106

### BASE-F105 Report a bad answer
Status: done
Actor: owner, administrator, manager, employee
Screen: Assistant
Steps:
  1. Under each finished answer shows "Report a problem"; not on the one still being written nor under a failure
     without an answer, which is not the assistant's.
  2. "Report this answer" opens: "If this answer of the assistant looks wrong or harmful, send it to us and we will
     review it.", with "What is wrong with it?" ("It is wrong", already ticked; "It is harmful or offensive", "It did
     not do what I asked" or "Something else") and "Comment (optional)".
  3. "Report" sends it with the question that led to it; "Cancel" sends nothing.
  4. "Thank you, we have received your report." shows and it closes.
In: the answer, the question, the reason and the comment.
Out: the report, for erplora.com's team to review. Anyone can report.
If it fails: "The report could not be sent. Try again.", and the window stays open with what was chosen and written.
Involved: none

### BASE-F106 The assistant without a connection, with the service down or without a plan
Status: done
Actor: owner, administrator, manager, employee
Screen: Assistant
Steps:
  1. Without Internet on the device, the foot says "No connection: you can write, and send when it is back." and
     "Send" turns off until it is back.
  2. If the question does not reach erplora.com, the bubble reads "The assistant could not be reached. Check the
     connection and try again." with "Try again".
  3. If erplora.com or its service fail, "The assistant is not available right now. Try again in a few minutes." with
     "Try again". If the answer is cut half way, what was written stays, with "The answer was cut off." and "Try
     again".
  4. With too many questions in a row, "Too many questions in a row: wait 60 seconds and try again.".
  5. If the session ends half way through the chat, "Your session has ended. Sign in again to keep talking." with
     "Sign in again".
  6. Running out of messages or having a plan without the assistant is no breakdown: BASE-F104.
  7. "Try again" asks the same question again: it is never lost.
In: what happened to the question.
Out: the failure, in the bubble and kept with the conversation (BASE-F102); it does not reach the assistant as if it
had said it.
If it fails: a failure with nothing written leaves no empty bubble: only the sentence with its way out.
Involved: BASE-F93, BASE-F102, BASE-F104

### BASE-F107 Pass the master QA of the Hub
Status: done
Actor: ERPlora's QA team
Screen: every screen of the hub's platform
Steps:
  1. The team creates on erplora.com, with a new account, a business of its kind (a restaurant): the hub receives it
     with its sector and in "Data and backups" offers that sector's template first, which leaves the business with
     its menu and its tables.
  2. It goes through the platform as its owner, on the phone, the tablet and the computer, in Spanish and in English:
     the Home with "Summary" and "Activity", "My apps" and the bell; "Add apps" and the tabs of Apps ("Paid" does
     not show while no app is sold apart); the tabs of Settings and the sections of "Data and backups"; Employees, a person's page, the roles, the keys and the
     approvals; the five tabs of System; Files; "My profile"; an address that does not exist; and the assistant,
     which opens and answers.
  3. On each screen it checks that it loads with no error, that nothing runs off a side and that no text is left in
     the other language or untranslated.
  4. The day of a restaurant or a hair salon (opening the till, seating or booking, ordering, cooking, charging with
     the receipt signed for the AEAT, printing and closing the till) is tested by the apps that do it, each with its
     own flows.
In: a new business created on erplora.com and its test accounts.
Out: every screen of the platform seen and checked in both languages and the three sizes.
If it fails: what fails on a screen is a failure of the app that has it and is fixed there; if erplora.com does not
have the business types or the test assistant yet, the QA does not start and says which is missing.
Involved: HUBS-F01, BASE-F05, BASE-F14, BASE-F29, BASE-F38, BASE-F39, BASE-F48, BASE-F92

### BASE-F108 Report a problem to support
Status: done
Actor: owner, administrator, manager, employee (whoever entered with their erplora.com account)
Screen: The user menu
Steps:
  1. In the user menu, "Report a problem". It only shows if they entered with the account: never in a PIN session
     on a shared till, which has no account to answer to.
  2. "Report a problem" opens in a window, without leaving the hub: "Tell us what went wrong. We will reply by
     email.", with "Subject" and "What happened?" ("Describe the steps and what you expected to happen") and, below,
     "Your account, your businesses, the page you came from and your browser go with your report.".
  3. "Send report" waits until both are written; while it is sent, the window neither closes nor sends it twice.
  4. "Report sent" shows, with the email support will answer to, and "Close".
  5. "Cancel" or closing the window sends nothing, and what was written is still there if it opens again.
In: the subject and what happened.
Out: a mail to erplora.com's support mailbox with the subject, the text and, below, the account, its businesses, this
business, the screen they were on and their browser; support answers to the account's email (ACCOUNTS-F38). The hub
keeps nothing.
If it fails: after five reports in an hour (the hub's and erplora.com's together), "Too many attempts. Please try
again in a few minutes."; if erplora.com does not answer or cannot send it, a notice with the support address to
write to directly. In both cases what was written stays and can be sent again.
Involved: ACCOUNTS-F38, BASE-F40
