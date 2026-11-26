## What it is for and who it is for
<!-- from WORKBOOK.md sha256:22f1600b7c0a -->

It is what the Hub always brings, without turning on any app: the **Home**, the business's **people**, its **files**, its
**apps**, the **system** and the **settings**. From here each app is opened and the business is set up to work.

### At a glance
<!-- from WORKBOOK.md sha256:aad62a55216c -->

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
  platform's steps ("Your apps", "Turn on …" for each app mandatory in their country, "Your team"), and in the bell
  they see the notices between apps that were not delivered. Only the **owner** buys for the business (upgrading the
  plan or subscribing to a paid app on erplora.com), resets the business and downloads the copies of its data, as on
  erplora.com, where the plan, the billing and the ownership are theirs alone.
- The **manager** and the **employee** see their apps, the steps that are theirs, the panels they may
  see and the activity. A step that only an administrator can complete is shown to them too, so they know
  why invoicing is not possible, but without a button.

## Reference adopted
<!-- from WORKBOOK.md sha256:77b62328977f -->

The Home has this structure: greeting and date, app launcher, setup list with a progress bar, board of panels and the "Summary" and "Activity"
tabs. It follows what the market does: the "Setup guide" list of Shopify and Square (steps with their
button, the progress on top and what is done folded away), Odoo's app launcher, the board of panels that
each person picks and orders of Lightspeed and Toast, and the bell of the notices that ask for an action, which stay
until they are solved and arrive at the top right (Shopify, Business Central, Stripe; macOS's notification centre).
System's
"Usage and plan" follows Business Central's "Capacity" and the usage pages of Supabase, Vercel and Neon: each figure
against what the plan includes and, like Google Workspace, the yellow notice at 80 % and the red one when full.

## Before you start
<!-- from WORKBOOK.md sha256:8572c671b188 -->

- You come in with your ERPlora account; the Hub has no sign-in of its own. On a shared till, after that, each
  person enters with their PIN or their badge.
- What each person sees depends on their role in the business and on the apps the business has on.
- The apps declare their steps, their panels and their counters; the Home only puts them together. While
  an app does not declare its own, nothing of it shows in the list or on the board.
- The example app (Demo) shows in the menu, in "My apps" and with an example step, panel and counter on
  the Home only in development, in the tests and in a demo business: never in a customer's.

## Screens
<!-- from WORKBOOK.md sha256:7c7582f8acc8 -->

### Home · Summary
<!-- from WORKBOOK.md sha256:01b114f3b5e8 -->
On top, the business's name and "Today" with the long date. Below, in this order:

- **How the business is working**, only for who administers it: a coloured label for each app on that says how it is
  doing (the receipt printer, the WhatsApp number), with what fixes it, and "View system".
- **"Start with a business like yours"**, only for who administers the business and while the business has
  nothing a template brings.
- **"My apps"**: one tile per app the person can open, with its icon and its name; the ones opened most in this
  browser, first.
- **"Finish setting up your business"**: how many steps are done, a bar and the steps left, each with "Set up".
- **The board of panels**, with "Customize panel" (⋮) at the top right.

#### What each part brings
<!-- from WORKBOOK.md sha256:13672a1e55bb -->
- **The business's name**: while it has none, a greeting by the hour ("Good morning", "Good afternoon", "Good evening").
- **The templates**: up to four, with "Use this one", "See all templates" and "Not now".
- **"My apps"**: on a phone, with six apps or more, the first four and "View all apps".
- **Each step to set up**: its icon, its explanation, a label ("Needed to invoice", "Important", "Recommended", "Done"
  or "Not available yet") and "Set up". The list, folded: five steps (two on a phone), first the ones that stop
  invoicing, with "View all" and "Show less". When nothing is left: "Your business is ready".

### Home · Activity
<!-- from WORKBOOK.md sha256:156a3e1e3dcb -->
The table of the latest sales: "Date", "Sale", "Customer", "Method", "Amount" and "Status", with
"Search activity…", the filters funnel (method and status), the order, the cards view and "Columns". It
also opens with the Home's link ending in #actividad.

### The bell
<!-- from WORKBOOK.md sha256:0a2c21fb32cc -->
At the top right, the last one in the bar, after "My apps", the assistant's sparkles and, in the installed app,
"Change business" (HUB_APP-F04 of ERPlora/app), on a phone too. It gathers what asks for an action and stays true
until it is solved: "You cannot issue invoices yet", an unpaid invoice of the plan, the failed events, the
plan's limits, the roles to review, the appointments to confirm, the WhatsApp customers waiting for an answer, a printer
that does not print… No notice is dismissed: it goes by itself once it is solved.

- **The bell.** With nothing pending, just the bell. With something, it becomes a pill with the bell and the number,
  in the colour and with the icon of the gravest notice (urgent, attention or information). If a notice has a
  deadline, such as the time of the soonest appointment to confirm, the bell's ring empties over the last week before
  it.
- **The arrival.** A new notice comes in as a card under the bar, at the top right (full width on a phone), stays a
  few seconds and settles in the bell, which pulses; with the assistant open, it comes in to its left. While a sale is
  being charged at the till it does not show: the bell only pulses. The first result on opening the page announces
  nothing.
- **The panel.** Tapping the bell opens a panel from the right, over the screen and over the assistant (full width on
  a phone): on top, the gravest notice, with its sentence and its button (for example "Set up your business
  details"); below, the others in rows ("3 appointments to confirm"), and tapping a row puts it on top. Each notice is
  worded by the app that gives it, in the person's language: the problem in its heading ("3 appointments to confirm"),
  the consequence in one sentence ("Customers are waiting for you to confirm their bookings before they start.") and
  the action on its button ("Confirm the appointments"). It closes with its ✕, with Esc or tapping outside, and the
  bell gets the focus back. With nothing: "All caught up". A notice just solved stays a moment with "Resolved" before
  it goes.

### The side menu
<!-- from WORKBOOK.md sha256:883276d59037 -->
On the left (on a phone, from the bar's button): the person at the top and the platform's entries in two groups,
"Home", "Employees", "Files" · "Apps", "System", "API", "Settings". Each one shows only to whoever holds the
permission its screen opens with, as in Square or Toast: "System", to whoever runs the business; "API", besides, while
the API documentation is shown (BASE-F91), and it appears or goes when the switch changes, without reloading. An
employee sees "Home", "Employees", "Files", "Apps" and "Settings". An entry the person does not have, opened by its
address, says "No access" (BASE-F118). At the bottom, the QR code to open it on a phone (BASE-F132), "Upgrade plan"
(the owner only) and "Manage on erplora.com". The entries come before the foot: if the menu is not tall enough for both,
the code folds into a row that shows it on a tap.

### "Upgrade plan"
<!-- from WORKBOOK.md sha256:ead81da17fe8 -->
At the foot of the side menu, between the QR code and "Manage on erplora.com". It opens this business's plan page on
erplora.com, in a new tab and already signed in with their account, without typing the password again. Only the
owner sees it, the only one who changes the plan on erplora.com, and only in the browser: the installed app does not
have it.

### "Manage on erplora.com"
<!-- from WORKBOOK.md sha256:33b47443add4 -->
At the foot of the side menu, right below "Upgrade plan" (if there is one), with the external link icon; with the menu folded to its
icons (desktop), only the icon stays, which says "Manage on erplora.com" on hover. It opens this business on
erplora.com's panel, already signed in with their account: in a new tab in the browser and, in the installed app, in
the device's browser. Only the owner,
the administrator and the manager have it, and only if they came in with their account: never in a session opened
with a PIN or with the badge. It does not sell, so the installed app has it too, except the Google Play one.

### The user menu
<!-- from WORKBOOK.md sha256:9800cf1641ae -->
It opens by tapping the person, at the top of the side menu. First "Profile" and, on a shared till of a business
that asks for a PIN, "Switch user"; then, only if they entered with the account (never in a PIN session), "My
account", which opens that page on erplora.com (in a new tab; in the installed app, in the device's browser), and
"Report a problem", which opens a form in a window without leaving the hub (BASE-F108); last "Theme" (light, dark
or the system's) and "Sign out". Both also show in the installed app: neither sells anything.

### The "You cannot issue invoices yet" notice
<!-- from WORKBOOK.md sha256:506c454662c8 -->
While a step that stops invoicing is missing, the bell carries the urgent notice "You cannot issue invoices yet", on
any screen (the Home too) and taking room on none: "No ticket or invoice can be issued until this is set up: Your
business details.", with "Set up your business details" and, if another step is missing, a second button with its
own ("Set up VeriFactu"). To whoever cannot set it up it says, with no buttons, "An administrator has to set this
up.". It goes by itself as soon as the step is done, on any device.

### Apps
<!-- from WORKBOOK.md sha256:01594a5ed527 -->
From "Apps" in the side menu. Three tabs at the bottom: "My apps" (the apps the business has running), "Add
apps" (every ERPlora app) and "Paid" (the ones subscribed to separately). At the top, how many apps the business has
turned on and how many of the ones its plan allows it has chosen: "27 apps turned on · 17 of 20 in your plan".
Each tab, a table (or cards) with its search, the filters funnel, the order and "Columns": "App" (icon and name),
"Category" and "Status"; in "Add apps" and "Paid", also "Description", "Price" and "Comes with". "Open" on the
row of an app the person can open and, for whoever runs the business, "Turn on" or "Turn off".
"Paid" and "Price" only show if some app is subscribed to separately; today none is: every app comes with every plan.

#### The count of apps and the notices
<!-- from WORKBOOK.md sha256:f36306390a00 -->
It counts those in "My apps", also the ones born on, like Taxes, and the ones that came along with another. With no
limit: "27 apps turned on · Unlimited". A business just signed up: "1 app turned on · 0 of 20 in your plan" (hub#1286).
Above the table, when it applies, the notice of the plan's limit or the one saying why an app was not changed.

### The screen of an app that does not open
<!-- from WORKBOOK.md sha256:8097e7649eb4 -->
In the same address as the app's screen, the reason: "Subscription needed" or "This app is not available in
this business", with "Go to Apps" (and "Upgrade plan" for the owner, in the
browser).

### No access
<!-- from WORKBOOK.md sha256:7a4d947bc180 -->
In the same address as a screen the person's role does not open, a padlock with "You do not have access to this
screen" — "Your role in this business does not open it.", the names of who can give them access, each with their
avatar, and "Go to Home".

### Settings · Business
<!-- from WORKBOOK.md sha256:1a0de23672c9 -->
The second of the tabs at the bottom of "Settings" ("General", "Business", "Printing" and "Data and backups").
The "Your business" card shows, with no fields to fill in, "Business name", "Country", "Time
zone" (with the time it is there), "Currency" and "Business language", each with a line that says what it is
for. Below, where they are changed and, for the owner and the administrator, "Change on erplora.com" (in the installed app, in the device's browser; the Google Play copy does not have it). Further
down, "Fiscal data", which opens Invoicing's issuer.

### Settings · Printing
<!-- from WORKBOOK.md sha256:35026ff0c1c7 -->
The "Printing" tab: a single row, "Printers and ticket", which opens the Printing app.

### Settings · Data and backups
<!-- from WORKBOOK.md sha256:770c39732050 -->
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
<!-- from WORKBOOK.md sha256:fe93f034b679 -->
From "System" in the side menu, which only whoever runs the business has. Four tabs at the bottom: "Usage and plan",
"Updates", "Failed events" and "Logs"; "Usage and plan" opens: their plan with "Upgrade plan" (for the owner), a line that says whether
it is enough or they have to upgrade and why, "What your plan includes", from the fullest down, with its bar, and "For
your information", with the figures no plan limits.

### System · Updates
<!-- from WORKBOOK.md sha256:b89fb9d2bf20 -->
"What we have updated": the version running, when it was published and that the hub updates itself.

### System · Failed events
<!-- from WORKBOOK.md sha256:e905914173b2 -->
One card per notice between apps that ran out of retries, with "Resend" and "Discard"; on top, "Resend all".

### System · Logs
<!-- from WORKBOOK.md sha256:37864d197fa7 -->
"Event log": the "Time", "Level" and "Event" table (on a phone, one card per event), with "Search event…" and the
level filter.

### Access
<!-- from WORKBOOK.md sha256:bb130961b87e -->
The way in of a shared till, or of a device whose session another entry closed, with no menu or bar: the logo,
"Enter your business", the notice of what happened if there is one and a card with two tabs, "PIN" (the faces,
the keypad and the badge) and "Account" ("Enter with your account", which leads to erplora.com). In the footer,
"ERPlora · trusted device"; at the top right, the switch between light and dark.

### Create your PIN
<!-- from WORKBOOK.md sha256:22fcccd522da -->
After entering with the account on a till: the keypad of circles to choose the PIN and repeat it, and "Not now".

### Switch user
<!-- from WORKBOOK.md sha256:79f247886a70 -->
Over the screen in use, with no menu: "The sale stays open. From now on it is in the name of whoever enters
here.", "Who is taking over?" with the faces, the keypad and "Cancel".

### My profile
<!-- from WORKBOOK.md sha256:b91362c5379d -->
From "Profile" in the user menu. At the top, the person (face, name and role); below, "Account details" (with the
photo), "Preferences" (language and appearance: palette, theme and interface size from 80 to 120%, default 100%) and
"PIN".

### Settings · General
<!-- from WORKBOOK.md sha256:20223bfae72a -->
What "Settings" in the side menu opens: the first tab at the bottom, "General", with "This device" (in the
ERPlora app on a computer, also "Start on login"), "PIN pad", for whoever runs the business "Devices" and, at the
end, the card of the API's documentation.

### Your business is being prepared
<!-- from WORKBOOK.md sha256:d89dba046a9c -->
The page that shows at the address of a business erplora.com is still preparing; it refreshes by itself.

### Files
<!-- from WORKBOOK.md sha256:fc8ee636158c -->
From "Files" in the side menu; the whole team sees it. On the left, "Folders": the tree of the business's folders,
which starts at "Files" (the very top), with the open folder highlighted; on a narrow screen, the tree folds into the
"Folders" selector. On the right, "Search files…", "List" and "Grid" and, for whoever administers the business, "New
folder" and "Upload file". Below, what the open folder holds: tapping a file opens it.

#### The open folder
<!-- from WORKBOOK.md sha256:3e9218268628 -->
On top, the folder's path, with ⋮ beside it to rename, move or delete that folder; "Space", with what is used and the
plan's limit ("{used} of {limit}") or "{used} used · No limit"; and what the folder holds: the folders first and then
the files, each with its icon, its name, its size (in the list, also when it changed) and its ⋮: "Open", "Download",
"Rename", "Move to…" and "Delete". In the list, each name takes one line: what does not fit is cut with "…" and the
extension always shows whole; on a phone, the size and the date go under the name, in grey. Tapping a file opens it in
the viewer, with its name, "Download" and "Close" ("Zoom in" and "Zoom out" on images and PDFs).

### Employees · Staff
<!-- from WORKBOOK.md sha256:976a92f8783f -->
What "Employees" in the side menu opens: the first tab at the bottom, "Staff", with the plan's places, "Invite on
erplora.com" for whoever runs the business (in the installed app, in the device's browser; the Google Play copy does not have it), "People are invited, given a role and removed on erplora.com, in
“Members” of the business." and the table of people (on a phone, a card per person). The other tabs: "Roles" and,
only for whoever runs the business, "API keys" and "Approvals"; each one in the address, so "Back" leaves
Employees.

### Employees · Roles
<!-- from WORKBOOK.md sha256:5d1d35230555 -->
The five roles of erplora.com and, below them, the business's own, with "Basic" or "Custom", how many people have them
and how many permissions they give; one of its own with new permissions carries "To review". Tapping one opens "What it
allows". Whoever manages the roles has "New role" at the top and, in each row, "Duplicate"; in the business's own, also
"Edit" and "Delete" in "⋮".

### Employees · Roles · What it allows
<!-- from WORKBOOK.md sha256:b6e877da5f77 -->
A role: how many people have it and, in a panel per app that is on, each permission with its phrase
and whether the role gives it ("Allowed"), lets a person do it with a manager's approval ("With approval") or not ("No").
It is read only, save one of the business's own for whoever manages the roles, who changes its name, its description
and what it allows right there, and presses "Save".

### Employees · API keys
<!-- from WORKBOOK.md sha256:c4e8c06601f5 -->
The keys with which another system calls the business's API: "New API key", the table of keys and, at the bottom, the
link to the API's documentation.

### Employees · Approvals
<!-- from WORKBOOK.md sha256:099748e4ae1e -->
The read-only record of the actions that can need a manager's approval: who did it and who approved it for them, or that
somebody whose role allows it did it by themselves.

### A person's page
<!-- from WORKBOOK.md sha256:b88b0da10ded -->
From a row of **Employees › Staff**, for whoever runs the business, with the back button: "Their details" (with
"Open on erplora.com"), "PIN" and "Badge".

### An approval is needed
<!-- from WORKBOOK.md sha256:df4d17e11e2b -->
Over the screen where the action was tried: what is approved, "Who approves it?" with the faces and the PIN pad
(whole and without scrolling on a phone, a tablet and a desk), and "Cancel".

### API documentation
<!-- from WORKBOOK.md sha256:a1d061a673e3 -->
With the back button: how the API is called, "Download the OpenAPI file" and a section per app with its calls.

### Assistant
<!-- from WORKBOOK.md sha256:e9ef01811fd3 -->
The panel the "Assistant" sparkles of the top bar open (on a phone, inside "⋮", beside "My apps"), on the right. On a tablet
or a computer it stays beside the screen and pushes it, so they keep working with it open; on a phone it covers it,
over a dark veil. At the top, "Assistant", "New conversation" once there is one and the "Close" ×. In the middle, the
conversation: empty, the sparkles, the welcome sentence and the setup's shortcuts; then, the messages, each answer
with its "Go to …" buttons, its notices and the receipts of what was done. At the bottom, the foot's notices (no
connection, the messages left this month, a plan without the assistant) and the "Write a message…" box with "Attach a
file", "Dictate by voice" and "Send".

### Assistant confirmation card
<!-- from WORKBOOK.md sha256:38e32d8b2db8 -->
It shows over everything, also with the panel closed, when the assistant wants to change something: "Run this
action?", what it will do, in which app and with which data, and "Run it" and "Cancel" ("Cancel all" when more wait
behind it). In a dangerous action, each datum on its own line and a box to type what it asks before "Run it".

## States of each screen
<!-- from WORKBOOK.md sha256:293e79bed433 -->

| State | What the person sees |
|---|---|
| Loading | The row of how the business is working in grey, grey tiles in "My apps" ("Loading your apps…" for the screen reader), the list in grey, "Loading widgets…" on the board, each panel's figure in grey and "Loading…" in "Activity"; "Loading…" on the PIN pad, "Loading your profile…" and "Loading the devices…". |
| Empty | "Your apps will show up here. Add the ones your business needs."; with no steps, the list does not show; "Empty panel. Tap ⋮ to add widgets."; a panel without data, "No data"; the bell's panel, "All caught up" and "Nothing needs your attention."; "Nobody has entered from any device yet."; in "Switch user", "Nobody here has a PIN yet: give one in My profile or in Employees.". |
| Error | Each zone fails on its own: "We couldn't check how your business is working." with "Retry", "Could not load your apps. Reload the page; if it keeps failing, sign in again.", "Could not load what is left to set up" with "Retry", "Could not load the panels" with "Retry", a panel with "Unavailable" (never the figure it had), "Could not load the latest sales" with "Retry" and, in the bell's panel, "Could not load notifications" with "Retry" or, if it already had notices, "Could not refresh the notifications. What you see may be out of date." with the ones from before. In the way in: "Could not load the PIN pad. You can still enter with your account.", "Could not load the profile" with "Retry", "Could not load this device. Check the connection and try again.", "Could not load how the business asks for the PIN. Check the connection and try again." and "Could not load the devices. Check the connection and try again.". In the app on a computer, "Could not change the start on login setting." (BASE-F120). |
| No permission | A step the person cannot do: no button and "An administrator has to set this up.". A panel or a counter they may not see does not show. In Settings, whoever does not run the business sees "This device" and "PIN pad" with the controls off ("Only an administrator can change how people enter on this device.", "Only an administrator can change whether it asks."), except "Start on login", which belongs to the computer and not to the business, and, instead of the list, "Only an administrator can see and remove the devices.". A screen their role does not open, of an app or of the platform (such as "System"), opened by its address: "No access" (BASE-F118). |

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
| No permission | What the person cannot do with their buttons, the assistant cannot either: it is not offered and, if it tries, the receipt reads "Not done, not allowed: …". With the month's messages spent, whoever is not the owner sees "Ask the business's owner to upgrade the plan." instead of "Upgrade plan". |

On the Settings · Data and backups screen:

| State | What the person sees |
|---|---|
| Loading | "Loading templates…"; in "Export" and "Reset", the rows in grey. |
| Empty | "There are no templates for your business yet.", "No template matches your search.", "This business has no app on to export." and "There is nothing to reset: no section has data.". |
| Error | "The templates could not be loaded right now. You can still import a file." with "Retry"; "The apps of this business could not be loaded." and "What each section has could not be worked out.", with "Retry". |
| No permission | Whoever does not run the business has no "Data and backups" tab: its address opens "General" for them (BASE-F48), and the Home's templates card does not show. An administrator, in "Reset", undoes imports and, instead of "Reset the business" and "Copies of the data", reads "Only the business's owner can reset it or download the copies of its data.". |

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
| Loading | The table in grey in "Staff", "Roles", "API keys" and "Approvals"; "Loading…" on a person's page; "Loading what this role allows…" in "What it allows"; the faces in grey in "An approval is needed"; "Loading the documentation…". |
| Empty | "Nobody is in this business yet.", "No API keys yet. Create one so that another system can read or write your business's data.", "There is no action of this kind in this business yet.", "Nobody here can approve this with a PIN. Somebody who may do it can swipe their badge." and "None of this business’s apps publishes its API yet.". |
| Error | "The people of this business could not be loaded.", "The roles could not be loaded.", "Your API keys could not be loaded.", "Could not load the record of approvals.", "This person could not be opened.", "Could not load what this role allows.", "Could not load who can approve it." and "Could not load the documentation.", each with "Retry"; never the empty list. |
| No permission | Whoever does not run the business has no "API keys" or "Approvals" tabs (their address opens "Staff"), sees nobody's email and does not open a person's page; in Settings, "Only who runs the business can change it.". With the documentation hidden: "The API documentation is hidden in this business.". |

## Flows
<!-- from WORKBOOK.md sha256:e111b10f2051 -->

| ID | Flow | Status |
|---|---|---|
| BASE-F01 | See what the business still has to set up | done |
| BASE-F02 | See the business at a glance on coming in | done |
| BASE-F03 | Go and set up from "Finish setting up your business" | done |
| BASE-F04 | See which steps of the list an administrator has to set up | done |
| BASE-F05 | Open an app from "My apps" | done |
| BASE-F06 | See the apps' panels on the Home | done |
| BASE-F07 | Customize the board of panels | done |
| BASE-F08 | Keep the panels up to date without reloading | done |
| BASE-F09 | Look at the recent activity | done |
| BASE-F10 | See in the bell the notices between apps that were not delivered | done |
| BASE-F11 | Go to erplora.com to manage or upgrade the plan | done |
| BASE-F12 | Ask the assistant to go over the setup | done |
| BASE-F13 | A role change or leaving the business with the hub open | done |
| BASE-F14 | See the business's apps | done |
| BASE-F15 | Open an app from Apps | done |
| BASE-F16 | Look for an app in the catalogue | done |
| BASE-F17 | Know how much an app costs before having it | done |
| BASE-F18 | Turn on an app | done |
| BASE-F19 | Know what else comes with an app | done |
| BASE-F20 | Try to use an app that needs a subscription | done |
| BASE-F21 | See why an app could not be turned on and try again | done |
| BASE-F22 | Follow an app being turned on while moving around | done |
| BASE-F23 | Turn an app off | done |
| BASE-F24 | Turn an app back on | done |
| BASE-F25 | See an app refuse to be turned off | done |
| BASE-F26 | Understand why an app does not open | done |
| BASE-F27 | See a paid app blocked | done |
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
| BASE-F41 | Know which version is running and when it was updated | done |
| BASE-F42 | See the log of what happened in the system | done |
| BASE-F43 | See the failed events | done |
| BASE-F44 | Resend a failed event | done |
| BASE-F45 | Resend all the failed events | done |
| BASE-F46 | Discard a failed event | done |
| BASE-F47 | Report an error of the screen without anyone asking | done |
| BASE-F48 | Open Settings and move through its tabs | done |
| BASE-F49 | See the business's country | done |
| BASE-F50 | See the business's currency | done |
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
| BASE-F74 | Preview and download a file | done |
| BASE-F75 | Move and rename a file or a folder | done |
| BASE-F76 | Delete a file or a folder | done |
| BASE-F77 | Reach the plan's limit of people | done |
| BASE-F78 | Remove a person's PIN | done |
| BASE-F79 | Give a person a badge or take it away | done |
| BASE-F80 | Bring back a person who left the business | done |
| BASE-F81 | Understand how each person gets in | done |
| BASE-F82 | See the business's roles and what each one allows | done |
| BASE-F83 | Give a person a basic role | done |
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
| BASE-F109 | Delete a deleted business after its 90 days | done |
| BASE-F110 | Open the business's website on its own domain | done |
| BASE-F111 | Wait for the database when it is cut for a moment | done |
| BASE-F112 | Save a downloaded file inside the app | done |
| BASE-F113 | Keep warning with the screen off (Android app) | done |
| BASE-F114 | Put a business back as it was at a past moment from the Hub admin | done |
| BASE-F115 | See the help of the screen in view | done |
| BASE-F116 | Read what is new in ERPlora | done |
| BASE-F117 | See in the bell that the plan has an unpaid invoice | done |
| BASE-F118 | Open a screen without permission: "No access" and whom to ask | done |
| BASE-F119 | What each person sees by their data permissions | done |
| BASE-F120 | Start ERPlora on signing in to the computer | done |
| BASE-F126 | Turn ERPlora's support access on or off | done |
| BASE-F127 | Make a role of your own from another | done |
| BASE-F128 | Adjust what a role of your own allows | done |
| BASE-F129 | Delete a role of your own | done |
| BASE-F130 | Give a person a role of your own | partial |
| BASE-F131 | See in the bell the roles to review | done |
| BASE-F132 | Open the Hub on a phone with the side menu's code | done |

### BASE-F01 See what the business still has to set up
<!-- from WORKBOOK.md sha256:ed75c3653f5d -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Home · Summary, The "You cannot issue invoices yet" notice
Steps:
  1. They come into the Home. In "Finish setting up your business" they see how many steps are done and a
     bar.
  2. Below, the steps left: first the ones that stop invoicing ("Needed to invoice", in red) and then the
     "Important" ones, each group in the order the apps set, also on a phone, where only two rows fit. The
     "Recommended" ones show folded only if nothing else is left. "View all" shows every step, the done ones
     too, in the order the apps set.
  3. The platform's are "Your apps" (turn on at least one business app; Taxes, which every business is born
     with, does not count, since with it alone the till has nothing to sell) and "Your team" (add the people who
     will use the till); the rest come from each app that is on.
  4. Besides, for each app mandatory in the business's country that is off, an "Important" step of the
     platform: "Turn on VeriFactu" with "It is mandatory for businesses in Spain." (VeriFactu, in Spain) or
     "Turn on Taxes" with the business's country (Taxes, in every one). Only whoever runs the business sees it,
     since they are the one who turns apps on; "Set up" leads to **Apps**, to "Add apps". As soon as they turn it
     on, the step goes by itself and the app's own steps come ("Set up VeriFactu", "Your taxes"). A business of
     another country does not see VeriFactu's. A business just signed up does not see "Turn on Taxes",
     since it is born with it on; in Spain it does see "Turn on VeriFactu": VeriFactu never turns on by
     itself.
  5. A step that only applies to another country, or that the person may not see, does not show. A business
     without a country (a demo, ERPlora's own) counts as Spain, ERPlora's market: it sees Spain's steps and none
     of another country. A step whose check fails does not show either: what could not be checked is
     never taken as done nor as pending.
  6. While a "Needed to invoice" step is missing, the bell carries the "You cannot issue invoices yet" notice,
     with that step's button ("Set up your business details"), on any screen.
  7. When someone else completes a step on another device, or turns an app on, the list updates by itself.
In: the steps each app that is on declares, with their check, their country, their permission and their
screen; and the countries where each app says it is mandatory.
Out: nothing saved.
If it fails: "Could not load what is left to set up" with "Retry". A step that is on us (there is no
business app to turn on) shows as "Not available yet" with "This one is on us: there is nothing on your
side to do yet. We are on it.".
Involved: INVENTORY-F28, BASE-F24, BASE-F25, VERIFACTU-F01, TAX-F17, BASE-F14

### BASE-F02 See the business at a glance on coming in
<!-- from WORKBOOK.md sha256:7fa7cf361784 -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Home · Summary
Steps:
  1. After coming in, the Home opens (also from "Home" in the side menu).
  2. On top, the business's name (the one on erplora.com) and "Today" with the long date in the app's
     language; while the business has no name, "Good morning", "Good afternoon" or "Good evening".
  3. For who administers the business, under the greeting, a row with how what the business needs to work is
     doing and "View system", which leads to System. Each app on that the person can see says its own in a coloured
     label: green what works, amber what needs fixing and grey what could not be checked. With Printing, "Printer
     ready" if the device that prints the receipts gave signs in the last minute and a half, "Printer not connected"
     if it is set up but does not answer, or "Printer not set up" if there is none; the last two with "Set up
     printing", which opens Printing. With the WhatsApp Inbox, "WhatsApp connected", "WhatsApp needs reconnecting" if
     WhatsApp asks for it, or "WhatsApp not connected" if no number is connected; the last two with "Connect
     WhatsApp", which opens the Inbox's settings. The row is checked again each time the person comes back to the
     Home. With no app on that says how it is doing, there is no row. Whoever does not administer the business does
     not see it.
  4. Below, in this order: "Start with a business like yours" (only while the business is empty and for who administers
     it), "My apps", "Finish setting up your business" and the board of panels.
  5. When the interface language changes, the names in "My apps" and the checklist's texts change in place,
     without reloading or reopening the application.
  6. At the bottom, two tabs: "Summary" (the above) and "Activity".
In: the business's name, the device's date and what each app on says about itself.
Out: nothing saved.
If it fails: a zone that does not load does not bring the others down; each one says its own. On a phone
the zones stack and "My apps" folds. What could not be checked shows as neutral, never as ready and without a
button, because it is not the viewer's task: "We couldn't check the printer", "We couldn't check WhatsApp". If the
whole row cannot be read: "We couldn't check how your business is working." with "Retry".
Involved: PRINTING-F21, WHATSAPP_INBOX-F01, WHATSAPP_INBOX-F02, BASE-F38

### BASE-F03 Go and set up from "Finish setting up your business"
<!-- from WORKBOOK.md sha256:d4c5bcdb65e0 -->
Status: done
Actor: owner, administrator, manager
Screen: Home · Summary
Steps:
  1. In "Finish setting up your business", a pending step the person can do carries "Set up".
  2. They tap "Set up": the screen of the app that completes that step opens.
  3. Back on the Home, the list already counts the step as done if it was completed.
  4. While the business is empty, whoever runs it starts higher up, in "Start with a business like yours": "See all
     templates" opens "Data and backups", where a template or a backup is loaded.
In: the screen each step declares.
Out: nothing from here.
If it fails: while that screen does not exist in the hub, the step shows without "Set up" (a button that
leads to "not found" is worse than none).
Involved: BASE-F38

### BASE-F04 See which steps of the list an administrator has to set up
<!-- from WORKBOOK.md sha256:57e6efc7c08c -->
Status: done
Actor: manager, employee
Screen: Home · Summary, The "You cannot issue invoices yet" notice
Steps:
  1. A step that stops invoicing and that this person cannot do stays on their list, with its "Needed to
     invoice" label, and in the bell's "You cannot issue invoices yet" notice.
  2. It carries no "Set up": it says "An administrator has to set this up.".
  3. The steps that do not stop invoicing and that this person cannot do do not show on their list.
In: the person's permissions in this business.
Out: nothing.
If it fails: if that step cannot be checked, it does not show.
Involved: none

### BASE-F05 Open an app from "My apps"
<!-- from WORKBOOK.md sha256:666e291dadd0 -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Home · Summary, the top bar of any screen
Steps:
  1. In "My apps", one tile per app this person can open, with its icon and its name (if it does not
     fit, the whole name shows on hover). An app shows if their role lets them open at least one of its screens. An
     employee has the ones of their daily work: Sales & POS, Cash register, Tables, Kitchen, Reservations, Online
     booking, Appointments, Customers, Inventory, Invoicing, Services, Staff, Time clock, Tasks, Cart & Checkout and
     the WhatsApp inbox, and Automations to answer what an automation asks them. The ones that set up the business
     (Taxes, Price Lists, Modifiers, Menus and combos, Payments, Schedules, VeriFactu, Printing and Website) belong to
     whoever manages them: the employee does not have them, even though the till and the assistant keep using what
     they read from them.
  2. The ones opened most in this browser go first.
  3. They tap a tile: the first screen of the app the person can open opens. An app that is being turned on says
     "Activating…" and opens nothing.
  4. On a phone, with six apps or more, the first four show and "View all apps", which shows the rest.
     "Add apps", the last one, leads to Apps.
  5. To leave an app, tap "My apps" in the bar: the main screen of an app has no "Back". The sheet starts
     with "Home", which goes back to the Home, and goes on with the apps; tapping one opens it. "Home" is
     there even while the list loads, when it is empty or when it could not be read.
  6. In the Android app, the phone's back button first closes whatever is open on top (a window, a sheet or the menu); a
     window that cannot be closed that way stays, and one that creates, edits or cancels something, with something typed
     and not saved, asks first "Discard changes?": "Keep editing", or back again, leaves it as it was, and "Discard
     changes" closes it. Those same windows ask the same question when "Cancel", "Close", the "×" or Escape is pressed
     and on a tap outside, on the phone and on the computer, and with nothing typed they close without asking. With
     nothing open, on a record or a new one it does the same as "Back"; on the main screen of an app it goes back to the
     Home, also when that screen was reached through a link; and on the Home it sends the app to the background.
In: the apps of the person's menu (the same as the bar's "My apps" button).
Out: how many times each app is opened in this browser (only to order them).
If it fails: while loading, grey tiles and "Loading your apps…" for the screen reader. Without apps:
"Your apps will show up here. Add the ones your business needs.". If the list could not be read: "Could
not load your apps. Reload the page; if it keeps failing, sign in again.", never that there are no apps.
In an older Android app, which cannot yet stay in the background, the back button is the system's again.
After an ERPlora update, a screen that tab had not opened yet still opens (from a tile, "My apps", the menu or
any button), in a fresh load of the page, which already brings the new version; a tap never does nothing. If
the server does not answer (offline or on a flaky network), the person stays where they were and a notice says
"Could not open Reservations. Check the connection and try again." ("that page" when the screen is not an app's), with
"Retry", which tries again and opens it as soon as the server answers.
Involved: INVENTORY-F01, INVENTORY-F02, SALE-F35, TABLE-F01, KITCHEN-F01, CUSTOMER-F01, RESERVATION-F06, APPOINTMENT-F01, STAFF-F01, SERVICE-F01, ATTENDANCE-F08, CART_CHECKOUT-F01, CASH_REGISTER-F02, COMBO-F02, INVENTORY-F06, MODIFIER-F02, PAYMENT-F01, PRICING-F02, INVOICE-F03, PRINTING-F03, SCHEDULE-F04, TASK-F01, TAX-F02, WHATSAPP_INBOX-F29, BASE-F86, ONLINE_BOOKING-F05, PAYMENT-F05, PRINTING-F14, RESERVATION-F09, SERVICE-F17, VERIFACTU-F30, BASE-F73, BASE-F75, INVENTORY-F09, TASK-F09, TASK-F10, TASK-F13, CUSTOMER-F18, KITCHEN-F22, BASE-F46

### BASE-F06 See the apps' panels on the Home
<!-- from WORKBOOK.md sha256:ed4311481f23 -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Home · Summary
Steps:
  1. Under the list is the board, with its panels from the moment the Home opens ("Loading widgets…" only while
     it is not known which ones are theirs).
  2. Each panel is a card with its title and icon: a figure (with what it counts under its title, if its app
     says so), a list with bars, a timeline, a chart or a piece of its app's screen, with its texts in the
     language of whoever is looking. Each figure has the colour of its measure, the same on every screen: sales,
     tickets and inventory, each its own. The board's first figures that have a colour head it in a row in
     colour, one per colour and two to four; the others go in a light card with the colour on their icon, in
     the order chosen. On a phone the figures go two by two. A figure with a state to watch (VeriFactu's
     contingency queue when something waits or has already failed) says it in an orange or red tag with an
     icon, without changing the figure's colour. In a list with bars, each bar measures how big its figure is against the biggest
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
  6. Only the panels of the apps that are on and that this person may see show, and none whose figure is a piece of
     data their role does not see.
In: the panels each app that is on declares; each one's data, asked for with the permissions of whoever
is looking.
Out: nothing saved in the hub.
If it fails: a panel without data says "No data" (a figure, with a dash in its place); a figure whose data
cannot be read says "Couldn't load" with "Retry", which asks for it again, and any other panel,
"Unavailable": never an old or made-up figure. A row of a list with bars (or a day of a chart) that has no figure, such as a cash
session closed without a count, shows a dash (—) and no bar, never a zero; a real zero does show as zero
(€0.00). If the board cannot be read: "Could not load the panels" with "Retry".
Involved: BASE-F119

### BASE-F07 Customize the board of panels
<!-- from WORKBOOK.md sha256:e02760696dae -->
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
app offering panels: "No active app offers widgets yet.".
Involved: none

### BASE-F08 Keep the panels up to date without reloading
<!-- from WORKBOOK.md sha256:eb3d104180ba -->
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
If it fails: if the new data does not come, the panel says "Unavailable" (a figure, "Couldn't load" with
"Retry"), not the value it had; when the connection is back, it updates by itself.
Involved: none

### BASE-F09 Look at the recent activity
<!-- from WORKBOOK.md sha256:b45c42b18437 -->
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
     switch to cards or pick columns; 15 per page. A sale charged with several methods shows them all
     under "Method" ("Cash + Card"); the method filter offers each method once and finds it by any of them.
  4. A sale charged on another device shows up by itself, without reloading.
In: the sales of the Sales app, if it is on, with the permissions of whoever is looking. Only sales: the
business's other movements do not show here.
Out: nothing saved.
If it fails: without the Sales app, the empty table. If the sales cannot be read: "Could not load the
latest sales" — "Check the connection and try again." with "Retry", instead of the table; if there were
already sales on screen, they stay under the notice.
Involved: SALE-F28

### BASE-F10 See in the bell the notices between apps that were not delivered
<!-- from WORKBOOK.md sha256:9dc8306fec6e -->
Status: done
Actor: owner, administrator
Screen: The bell
Steps:
  1. A notice between apps (for example, "sale charged" towards Invoicing) ran out of retries.
  2. An administrator's bell goes up at once, without waiting or reloading: the urgent notice "2 failed events",
     with "An app did not receive what another one sent it: what it had to do stays undone until you send it again.",
     comes in as a card and settles in it.
  3. "Review the events" opens "System" on "Failed events", where they are resent or discarded (BASE-F43).
  4. When none is left, the notice disappears.
In: how many notices of this business were left undelivered, only for whoever runs the business.
Out: nothing.
If it fails: an employee or a manager does not see the notice. If it cannot ask, the bell keeps what it
last knew and its panel says "Could not refresh the notifications. What you see may be out of date."; if it never
knew: "Could not load notifications" with "Retry".
Involved: BASE-F40

### BASE-F11 Go to erplora.com to manage or upgrade the plan
<!-- from WORKBOOK.md sha256:523d203421e1 -->
Status: done
Actor: owner, administrator, manager
Screen: The side menu, "Upgrade plan", "Manage on erplora.com"
Steps:
  1. At the foot of the side menu, under the QR code and lined up with it, is "Upgrade plan". Only the owner
     sees it: on erplora.com only the owner changes the plan and pays. With the menu folded to its icons
     (desktop), only its icon stays, which says "Upgrade plan" on hover. Only in the browser: the installed app
     does not have it.
  2. They tap it: this business's plan page on erplora.com opens in a new tab, already signed in with their
     account: they do not type the password again even if that browser did not have the erplora.com session open. The
     same from any other "Upgrade plan" of the Hub: System, Employees, Apps, the assistant's panel and the WhatsApp Inbox.
  3. The owner, the administrator or the manager who came in with their account also has, at the foot of the menu
     (right below "Upgrade plan", if they have it), "Manage on erplora.com", with the external link icon (on the folded
     menu, only the icon).
     It does not sell: the installed app has it too, except the Google Play one.
  4. They tap it: this business opens on erplora.com's panel, already signed in with their account, in a new tab; in
     the installed app, in the device's browser. The Hub stays where it was.
In: the business they are in.
Out: nothing saved in the hub. A one-time pass of one minute goes to erplora.com, of the account of whoever taps and of
this business; erplora.com checks again that this account belongs to this business.
If it fails: if the hub does not know which business it belongs to, neither of the two shows (never a button that
does nothing). If the installed app cannot open the browser, it says so: "Could not open that page. Try again.". If the
pass does not come (the server gives an error or does not answer in 8 seconds), the usual address opens: erplora.com
asks to sign in with the account and goes on to the same place. If the browser blocks the new tab, the link itself opens
that address. With the pass spent or the minute gone, erplora.com says so and offers to sign in and go on there; to an
account that no longer belongs to this business it says it does not (ACCOUNTS-F29). An employee, a session opened with
a PIN or with the badge and the Google Play app do not have "Manage on erplora.com". Whoever is not the owner has no
"Upgrade plan" anywhere in the Hub, nor erplora.com's Store: the administrator, the manager and the employee do not buy.
In ERPlora's own business, which has no plan and buys nothing, its owner has neither; "Manage on erplora.com", yes.
Involved: BASE-F40, BASE-F104, WHATSAPP_INBOX-F13, ACCOUNTS-F29, BASE-F132

### BASE-F132 Open the Hub on a phone with the side menu's code
<!-- from WORKBOOK.md sha256:2502fed09265 -->
Status: done
Actor: anyone who has entered the business
Screen: The side menu, "Open on your phone"
Operations: none
Steps:
  1. At the foot of the side menu, above "Upgrade plan" and "Manage on erplora.com", is the QR code of this business's
     address, with "Open on your phone" and how to keep it on the phone's home screen. It shows to everyone, with no
     permission or plan.
  2. If the menu is not tall enough for its entries and the code at once (a tablet in landscape, a laptop, a phone or
     the interface at a larger size in My profile), the entries show whole and the code folds into a row, "Open on your
     phone", with the QR icon. Tapping it shows the code over the page, above the row; it closes with Esc or tapping
     outside, and the focus goes back to the row.
  3. With the menu folded to its icons (desktop), only the QR icon stays, which says "Open on your phone" on hover;
     pressing it unfolds the menu.
  4. They scan the code with the phone's camera and this business's address opens in its browser.
In: the business's address.
Out: nothing saved.
If it fails: if the code cannot be drawn, the address to type on the phone shows in its place, also over the page when
the row is tapped.
Involved: BASE-F11

### BASE-F12 Ask the assistant to go over the setup
<!-- from WORKBOOK.md sha256:c95a59546413 -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Home · Summary
Steps:
  1. In "Finish setting up your business", they tap "Ask the assistant" (or ask it from its panel).
  2. The assistant reads the same list as the Home, with what that person may see, and tells them what is
     missing and where it is done; each step keeps its "Set up" in the list.
  3. Of a step that is done it says it is done, without taking a figure, a name or a setting from its text, which
     says what the step asks for and not what the business has: "Your catalog" is done because there are already
     products, never "you have one". Asked how many or which, it reads it in the step's app (the active products, in
     Inventory).
In: the list of what is missing, with the permissions of whoever asks.
Out: nothing saved.
If it fails: without the assistant, the steps keep leading to their screen from the list.
Involved: BASE-F103, INVENTORY-F28

### BASE-F13 A role change or leaving the business with the hub open
<!-- from WORKBOOK.md sha256:15bd3236782e -->
Status: done
Actor: owner, administrator, manager, employee
Screen: any screen of the hub
Steps:
  1. At erplora.com, whoever manages the business changes a person's role, removes them from the business
     or hands the ownership over to them; or in the Hub gives them a role of your own or changes what theirs allows
     (BASE-F130, BASE-F128).
  2. If their role changed, their session stays open and what they have open, on all their devices, moves
     at that moment to what the new role allows, without reloading or signing in again: the menu, "My apps"
     and the tabs show only what they may open; the screen in front of them turns into "No access" if the
     new role does not open it, and one that said "No access" opens if they now may.
  3. If they were removed from the business, at that moment their session in this business ends, on all
     their devices: what they have open stops updating and the next thing they do asks them to sign in
     again; on coming back, erplora.com tells them "You don't have access to this hub" and they do not get
     in. Their sessions in other businesses stay open.
  4. A handover of the ownership ends the session of both people in this business (HUBS-F28): they come
     back in from erplora.com and already work with their new role.
  5. If they change their password, sign out everywhere or delete their account at erplora.com, all their
     sessions of the hub end, in all their businesses.
In: the change erplora.com made (who, in which business and with which role, or that they are no longer
there).
Out: their role in the business, up to date, and what they have open with what that role allows; the
sessions of whoever is no longer in the business, ended.
If it fails: if the hub does not answer at that moment, erplora.com passes it again shortly and the change
arrives then. A device without a connection gets it when it reconnects.
Involved: HUBS-F26, HUBS-F27, HUBS-F28, BASE-F118, BASE-F128, BASE-F130

### BASE-F14 See the business's apps
<!-- from WORKBOOK.md sha256:a72cf9842bfe -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Apps
Steps:
  1. They tap "Apps" in the side menu. It opens on the "My apps" tab; "Add apps" and "Paid" have their own
     address too, which can be linked.
  2. While the list arrives: "Loading your apps…". Then one row (or one card, as chosen) for each app the
     business has running, with its icon and its name, its "Category" and its "Status" ("Active"). An app the
     business's country requires also shows, next to its status, "Mandatory in Spain" (or the business's country):
     Taxes in every country, VeriFactu in Spain. A business just signed up already has Taxes here,
     "Active": it is born on with its country's taxes and does not count against the plan's app limit: the counter at
     the top says "1 app turned on · 0 of 20 in your plan". The other apps are born off, VeriFactu too, which the
     owner turns on.
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
<!-- from WORKBOOK.md sha256:4c5a5aa521a5 -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Apps
Steps:
  1. On the row of an app in "My apps", they tap "Open".
  2. The first screen of that app the person's role lets them open opens.
In: the app's menu and what the person can see.
Out: nothing saved.
If it fails: an app the person cannot open, or that is not running, has no "Open" (it does not show greyed
out: it does not show). On tapping, it is checked again, in case it just changed: if it is no longer running,
nothing opens.
Involved: none

### BASE-F16 Look for an app in the catalogue
<!-- from WORKBOOK.md sha256:dbc036edae5e -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Apps
Steps:
  1. In Apps, they tap "Add apps" (every ERPlora app) or "Paid" (only the ones subscribed to separately).
  2. While it arrives: "Loading the catalogue…". Then one row per app with "App", "Category", "Description",
     "Price", "Comes with" and "Status" ("Active" or "Needs a subscription"), with the names and the
     descriptions in the language of whoever looks. An app the business's country requires shows "Mandatory in
     Spain" (or the business's country) next to its status, off too: that way it shows which one is still to be
     turned on.
  3. They search in "Search apps to add…" (in "Paid", "Search paid apps…") by name, description or
     category, and filter by category or by status.
In: the apps the hub brings and what the business has subscribed to on erplora.com.
Out: nothing saved.
If it fails: as in "My apps". A search without results: "No apps match your search.".
Involved: APPS-F01, BASE-F14

### BASE-F17 Know how much an app costs before having it
<!-- from WORKBOOK.md sha256:e98a4a8b4b36 -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Apps
Steps:
  1. In "Add apps" or "Paid", the "Price" column says of each app: "Free" (it comes with any plan), "Included
     in your plan", "Subscribed", "Included with" and the app that brings it (a paid one that comes with
     another the business has) or "Paid".
  2. The amount of a "Paid" app is on erplora.com's Store; whoever runs the business opens it from "Upgrade
     plan".
  3. "Paid" gathers only the apps subscribed to separately: a free one never shows there. If none is sold
     separately (today, every app comes with every plan), there is no "Paid" nor "Price", and a link to "Paid"
     opens "Add apps".
In: whether each app is subscribed to separately and what the business has subscribed to on erplora.com.
Out: nothing saved. The hub neither charges nor shows amounts: the price and the purchase are erplora.com's.
If it fails: without the list, as in "My apps".
Involved: APPS-F01, APPS-F07, BASE-F14, BASE-F20

### BASE-F18 Turn on an app
<!-- from WORKBOOK.md sha256:cdbe0b45b120 -->
Status: done
Actor: administrator
Screen: Apps
Steps:
  1. The apps the business uses are already in "My apps" and in the menu; a paid one shows in both by itself,
     without reloading, as soon as it is subscribed to on erplora.com.
  2. In "Add apps", whoever runs the business looks for an app the business does not use, "Off", and presses "Turn
     on". If it needs other apps that are off, it asks first, naming them.
  3. The app becomes "Active" at once and shows in "My apps" and, without reloading, in the menu of every device
     of the business. The counter at the top adds the apps turned on and one of the plan's: turning Tasks on, from
     "26 apps turned on · 16 of 20 in your plan" to "27 apps turned on · 17 of 20 in your plan"; the ones that come
     along with it add to the apps turned on, not to the plan's.
In: the chosen app, the ones it needs and what the business has subscribed to on erplora.com.
Out: the app running in this business, chosen by it: it counts towards its plan's limit of apps.
If it fails: with the plan's limit reached nothing is turned on and "Your plan’s app limit" shows: "You have reached the
20-app limit of your plan. Upgrade your plan or turn one off.", with "Upgrade plan" for the owner in the browser (not in
the installed app). A paid app not subscribed to offers no "Turn on". Neither does an app this business cannot use: it
shows "Not available" and, for whoever runs the business, the reason below it ("VeriFactu is only for businesses in
Spain."). Any other failure shows in a notice with the app's name and the reason, which stays until it is closed.
Involved: APPS-F07, VERIFACTU-F01, BASE-F19, BASE-F20

### BASE-F19 Know what else comes with an app
<!-- from WORKBOOK.md sha256:78edf5456e80 -->
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
<!-- from WORKBOOK.md sha256:314199041c77 -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Apps
Steps:
  1. A paid app the business has not subscribed to shows in "Add apps" and in "Paid" with "Needs a
     subscription", and is neither in "My apps" nor in the menu.
  2. The owner, in the browser, sees "Upgrade plan" next to it, which opens this business's Store on
     erplora.com in a new tab: there they see the price and subscribe.
  3. As soon as erplora.com tells the hub, the app becomes "Active" and shows in "My apps" and in the menu,
     without reloading.
  4. Whoever is not the owner, and anyone in the installed app, sees "Subscribed to on erplora.com,
     from your ERPlora account." and no button: the hub never sells, and on erplora.com only the owner buys.
In: what the business has subscribed to, as erplora.com passes it to the hub.
Out: nothing saved or charged in the hub.
If it fails: until erplora.com tells the hub, the app keeps "Needs a subscription"; a screen of it that is
opened says why.
Involved: APPS-F07, BASE-F27

### BASE-F21 See why an app could not be turned on and try again
<!-- from WORKBOOK.md sha256:346b90771a6a -->
Status: done
Actor: administrator
Screen: Apps
Steps:
  1. An app being set up does not finish because its data could not be prepared. The hub tries again by
     itself: after a minute, after 5 minutes, after 15 and then every hour.
  2. Its row, in "My apps", says "Could not turn on" and, to whoever runs the business, offers "Retry" and "Turn off";
     whoever does not run it sees the state, with no buttons. Meanwhile the app does not open and its screen says
     "Website could not be set up" — "Go to Apps to try again. Nothing of the business was lost.".
  3. "Retry" asks for it again: "Turning on Website… It will be ready in a moment." and the row goes back to "Turning
     on…".
  4. From the assistant ("Try turning on the website app again") the app is named as in "Turn an app back on" and the
     card shows its full name.
In: the app that could not be set up.
Out: the activation asked for again (`base.app.activation_requested`).
If it fails: if it fails again, it says so again with its "Retry". If it was no longer waiting, because another device
tried it again, a notice shows with the app's name and "This app is not waiting to be set up again.", which stays
until it is closed. From the assistant, a name that fits several apps, or none, shows no card.
Involved: BASE-F32, BASE-F22, BASE-F24

### BASE-F22 Follow an app being turned on while moving around
<!-- from WORKBOOK.md sha256:faecb54a3d32 -->
Status: done
Actor: administrator
Screen: Apps
Steps:
  1. Whoever runs the business turns on an app whose data is not prepared yet in this business: one that
     reached ERPlora after the business was born. The others have no wait: they are on at once.
  2. "Turning on Website… It will be ready in a moment." shows; its row says "Turning on…", with "Turn off", and "My
     apps" on the Home says "Activating…", without opening. The person can go to another screen: it goes on by itself.
     It is not in the menu yet.
  3. If its screen is opened by its address, it says "Website is being set up" — "It opens in a moment: this page shows
     it as soon as it is ready.".
  4. When it is ready it opens like any other: it turns "Active" with "Open", shows in the menu of every device of the
     business without reloading and its screen says "Website is ready" — "It can be used now.", with "Open Website".
In: how the activation is going.
Out: the app running in this business (`base.app.enabled`).
If it fails: its row says so and it is tried again, as in "See why an app could not be turned on and try again". While
ERPlora's staff keeps the platform frozen for a database upgrade (a few minutes), the app stays "Turning on…" and
finishes by itself as soon as the freeze is lifted.
Involved: BASE-F31, BASE-F32, BASE-F18, BASE-F21

### BASE-F23 Turn an app off
<!-- from WORKBOOK.md sha256:a55016847ef4 -->
Status: done
Actor: administrator
Screen: Apps
Steps:
  1. In "My apps", whoever runs the business presses "Turn off" on an app's row.
  2. It always asks, with the app's name: "Turn off Reservations?" — "It leaves the menu for everyone in this
     business. Nothing is deleted: turned on again, it has its data.". If others that came only for it go with
     it, it names them: "Tables turns off with it: only Reservations needed it.". An app the business's country
     requires never goes with it: on turning Sales off, Taxes stays on and is not named.
  3. They confirm with "Turn off": "Reservations is off. Also turned off: Tables.". Both leave "My apps" and, without
     reloading, the menu of every device of the business; their screens say the app is not available and the counter at
     the top takes away the ones turned off and, of the plan's, the one the business chose.
  4. In "Add apps" they stay, with their icon, their name and "Off": from there they are turned on again.
  5. From the assistant ("Turn off the reservations app", or without saying "app": "take Reservations off the menu", "I
     don't want to see Reservations in the menu") the app is named as in "Turn an app back on" and the high-risk card
     shows its whole name. Before the yes it also names the ones that go with it, by the same rule and in the same words
     as step 2: "Other apps: Schedules and Tables turn off with it: only Reservations needed them.". If it was off
     already, the assistant says so and nothing changes.
In: the business's apps, what each one needs and which ones the business chose.
Out: the app turned off in this business, and the ones that came only with it, with their data intact.
If it fails: if another running app needs it, nothing changes; if it cannot be turned off, it offers no "Turn off". With
"Cancel", nothing changes either. From the assistant, a name that fits several apps shows no card: it asks which one.
Involved: VERIFACTU-F32, BASE-F24, BASE-F25, BASE-F26

### BASE-F24 Turn an app back on
<!-- from WORKBOOK.md sha256:3cde5f49ed20 -->
Status: done
Actor: administrator
Screen: Apps
Steps:
  1. In "Add apps", whoever runs the business presses "Turn on" for an app they turned off, which shows "Off".
  2. If it needs others that are off too, it asks first and names them; if not, it turns it on without
     asking.
  3. The app comes back to "My apps" and to the menu, without reloading, with the data it had: "Reservations is
     on." and, if it came with others, "Also turned on: Tables.".
  4. From the assistant ("Turn on the reservations app", or without saying "app": "put Reservations back on the
     menu") the app is named as the person says it: by its name in any
     language of the Hub, case and accents aside, or, if none is called so, by the only one with a word of its name
     that starts so ("booking" is Online booking). "Reservas" is Reservations, never Online booking (Reservas online)
     even though it starts the same. The card shows its whole name, never its id, and before the yes it
     names the ones it needs that are off, as the notice of step 2 does: "Turn on in Apps: Reservations · Other
     apps: Reservations needs Schedules and Tables: they turn on with it.". If it was on already the assistant says so
     ("Customers was on already") instead of "turned on".
  5. If the business's country requires it (VeriFactu in Spain), the card also says, before the yes, that it can no
     longer be turned off, with the reason Apps gives: "Turn on in Apps: VeriFactu · Once on: VeriFactu is mandatory
     for businesses in Spain: it can't be turned off.". The assistant also knows it when asked about it.
  6. If the assistant is asked for something of an app that is off by saying its name, even without saying "app" ("I
     want to manage reservations", "book an appointment"), or if what the assistant searches for to do it names it, it
     says which app does it, what it is for as Apps says it and that it is off, instead of saying it cannot or trying it
     with something else. To whoever runs the business it shows the card of turning it on from step 4; with the yes, it
     goes on with what was asked in the same conversation, now with what that app does. To whoever cannot turn apps on
     it says that whoever runs the business turns it on; of a paid one not subscribed to, that it is subscribed to on
     erplora.com, without offering to turn it on; of one being set up or that could not be turned on, its state, as Apps
     does. What the apps that are on already do ("how many services do I have?", "raise the dye's price to 40 €")
     makes it name none.
In: what the app needs and what the business has subscribed to.
Out: the app running in this business, chosen by it.
If it fails: with the plan's limit of apps reached, the notice "Your plan’s app limit" with "Upgrade plan"; a paid app
not subscribed to cannot be turned on. Moving to a lower plan turns nothing off: with more chosen apps than the new plan
has, all of them keep running and only no other can be turned on until it is below. From the assistant, a name that fits
several apps ("reserva": Reservations and Online booking) shows no card and turns none on: the assistant asks which one,
naming them; one that is no app's: "No app has that name or id.".
Involved: BASE-F93, BASE-F97, BASE-F18, BASE-F19, BASE-F20, BASE-F25

### BASE-F25 See an app refuse to be turned off
<!-- from WORKBOOK.md sha256:1bde59055733 -->
Status: done
Actor: administrator
Screen: Apps
Steps:
  1. An app that refuses to be turned off offers no "Turn off": below its status, whoever runs the business reads the
     app's own reason in their language: "VeriFactu can't be turned off once it's on: the law requires your invoices
     to keep reaching the AEAT.".
  2. Neither do the apps that one needs, which cannot be turned off first, and each says which one it is for:
     "Invoicing can't be turned off: VeriFactu needs it. VeriFactu can't be turned off once it's on: the law requires
     your invoices to keep reaching the AEAT.".
  3. An app on that the business's country requires ("Mandatory in Spain") does not offer it either, and
     says why: "Taxes is mandatory for businesses in Spain: it can't be turned off.". It says so itself even when
     another app needs it, because turning that other one off would change nothing; an app with a reason of its own
     (VeriFactu) says its own. While it is being turned on, or if it could not be, it can still be given up.
  4. Whoever runs the business presses "Turn off" on an app another running one needs and that can be turned off (for
     instance, "Tables" while "Reservations" is on). The hub changes nothing: above the table "Nothing was changed"
     shows with what has to be done first, "Turn off Reservations first." (without asking).
  5. The notice stays until it is closed or another app is turned on or off; the app stays "Active".
In: the running apps that need it, the reason of the app that refuses, or the business's country and the apps it
requires.
Out: nothing.
If it fails: if it is asked for anyway through the assistant or the API, the hub answers the same reason and changes
nothing. Without a reason of the app's own, the same notice says it could not be changed, with the app's name and
what the hub answered.
Involved: VERIFACTU-F32, BASE-F01, BASE-F14

### BASE-F26 Understand why an app does not open
<!-- from WORKBOOK.md sha256:2509089cfe30 -->
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
other. A screen the person's role does not open says "No access" (BASE-F118); if the whole app does not open in the
business, this reason rules, since it holds for everyone.
Involved: BASE-F118

### BASE-F27 See a paid app blocked
<!-- from WORKBOOK.md sha256:4c8d806e2c59 -->
Status: done
Actor: owner, administrator, manager, employee
Screen: The screen of an app that does not open
Steps:
  1. The business stops having a paid app (its subscription on erplora.com ends) or someone opens one it has
     not subscribed to.
  2. On opening any of its screens they see "Subscription needed": the app's name and "is disabled because this
     business does not have its subscription. Your data is safe and comes back as soon as it is subscribed
     to.", with "Go to Apps" and, for the owner in the browser, "Upgrade plan".
  3. The app leaves the menu and "My apps", and the hub does nothing asked of that app, whether it comes from
     this screen, from another device, from the assistant or from an integration.
  4. If it is subscribed to with the screen open, it changes to the app's name with "is ready" — "It can be
     used now." and "Open" with its name, which opens it up to date.
In: what the business has subscribed to, as erplora.com passes it to the hub.
Out: nothing; the app's data is not touched.
If it fails: if nobody tells the hub when the subscribed period ends, the hub notices by itself when the date
passes. A demo business has every app, the paid ones too, to try them.
Involved: APPS-F07

### BASE-F29 Choose a template of the catalogue to import
<!-- from WORKBOOK.md sha256:836f685700b5 -->
Status: done
Actor: owner, administrator
Screen: Settings · Data and backups (Import)
Steps:
  1. Open "Settings" in the side menu; in "Data and backups", "Import" is what opens. It says "Load a
     template: it fills your apps with its data — a menu, services, tables — ready to use." and, below,
     "Choose what to load".
  2. While they arrive, "Loading templates…". Then one card per template: its name as the title, its
     description and each datum on its own line with the icon that says what it is: the language and the
     country by name, the version in words ("Version 1") and what it brings (how many categories, products,
     services, areas or tables). In the list view, one row per template with those data in their columns
     "Language", "Country", "Version" and "It brings". First those of the business's country and, among them,
     those in the person's language.
  3. "Search templates" searches by the name, the description or the apps it brings.
  4. Tap "Use template" on the one that fits: the button spins while it is read and "Review what it brings"
     opens.
In: the Hub's templates, one per sector and language (today restaurant and hair salon, in Spanish and in
English).
Out: nothing saved until it is loaded.
If it fails: "The templates could not be loaded right now. You can still import a file." with "Retry";
with no templates, "There are no templates for your business yet."; a search with no result, "No template
matches your search."; if the template cannot be read, "The file could not be read:" with the reason and it stays
on the choice. Who does not administer the business reads "Only an administrator can see and import
templates.".
Involved: INVENTORY-F12, BASE-F31

### BASE-F30 Upload a file to import
<!-- from WORKBOOK.md sha256:22d058cd18d8 -->
Status: done
Actor: owner, administrator
Screen: Settings · Data and backups (Import)
Steps:
  1. In "Import", tap "Upload from file" and choose a .blueprint.zip: a backup of this business or a
     template another one exported.
  2. While it is read, the button spins. Then "Review what it brings" opens.
  3. After an error the same file can be chosen again.
In: the file, of 20 MB at most (with the own photos of its products and services, INVENTORY-F33).
Out: nothing saved until it is loaded.
If it fails: "The file could not be read:" with the reason (it is not a .blueprint.zip, it is
damaged, a newer version of ERPlora made it or it is larger than 20 MB) and it stays on the choice.
Involved: BASE-F31

### BASE-F31 Review and load what the file brings
<!-- from WORKBOOK.md sha256:ac59a05a4943 -->
Status: done
Actor: owner, administrator
Screen: Settings · Data and backups (Import)
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
     PINs, fiscal data) shows in "Never loaded here". No template of the catalogue brings VeriFactu, in Spain
     either: it is not in the review and the load does not turn it on, because it binds the business to the AEAT
     and the owner turns it on from Apps.
  3. Untick the apps not wanted and tap "Import" ("Importing…"), or "Choose another" to go back.
  4. When it ends, the report shows. What the business already had stays as it was: nothing is
     duplicated nor overwritten. If an app of the template is still being set up, its part comes in by
     itself as soon as it is ready, with no coming back and nothing to tap.
In: the template or the file and the apps ticked.
Out: the apps ticked that were off, turned on before loading, with the ones they need and within the plan's
limit of apps, as if they were turned on in Apps (`base.app.enabled`); in each app ticked, what it brings and
was missing, added as if it were added by hand in that app (its categories, products, services, areas,
tables and, from a backup, customers), and the report kept (`base.blueprint.imported`).
If it fails: "The import failed:" with the reason and it stays on the review; with no app ticked, "Choose at least
one app." and it cannot be imported; if none of its apps can be turned on here, "Nothing of this file can
load in your business: none of its apps can be turned on here.". An app that could not be turned on (the
plan's limit of apps, an app the plan does not include) stays off, loads nothing and the report says why;
the rest loads. A file is not kept: if one of its apps is still being set up, its row says "It is being set up for
this business. Upload the file again in a minute to bring its data.".
Involved: BASE-F22, INVENTORY-F01, INVENTORY-F12, INVENTORY-F26, INVENTORY-F36, VERIFACTU-F01, BASE-F32

### BASE-F32 Read the import report
<!-- from WORKBOOK.md sha256:d556b3ffc787 -->
Status: done
Actor: owner, administrator
Screen: Settings · Data and backups (Import)
Steps:
  1. When it ends, "Import report" with how it went: "Everything went in.", "Not everything went in." or
     "Nothing went in.". If an app of the template is still being set up, "Still loading: what is missing
     comes in by itself as soon as its apps are ready. You can leave this screen.", with nothing to tap.
  2. One row per app with its label: "Applied", "You had it already", "Applied in part", "Failed", "Nothing
     to copy", "Left out", "App off", "Not in this business", "Not chosen", "Being set up" or "Could not be set up".
     "You had it already" shows only when everything the app brings was already in the business; an app it brings
     nothing of, like the ones the template only turns on, says "Nothing to copy". Below, for each part, "12 created
     · 3 already there · 2 failed" and, of what failed, its name and the reason.
  3. What was left out on purpose shows in "Left out on purpose".
  4. "See the templates" goes back to the catalogue; "Go to Home" leads to the Home.
  5. When the app is ready, its part loads by itself and the report gets up to date without reloading, whether this
     screen is open or not: on coming back, it is in.
In: the import's report.
Out: nothing; the report stays kept in the business. What loaded later counts in that same import: it is undone with
it (BASE-F34).
If it fails: a label the screen does not know shows as "Failed" with its own text, never as a success. If the app
cannot be set up, at the top it says "Could not be set up yet: Website. It keeps trying by itself and its data will load
as soon as it works." and its row, "Could not be set up" with "It could not be set up yet. It keeps trying by itself and
its data will load as soon as it works; «Retry what is missing» tries again now.". If meanwhile the app is
turned off, the import is undone, the business is reset or the template's version changes, nothing of it loads and its
row says why. If the load fails once the app is ready, the app stays on and its row says "Failed" with "Something went
wrong loading this part; nothing else was affected.", with "Retry what is missing".
Involved: BASE-F21, BASE-F22, BASE-F33, BASE-F34

### BASE-F33 Come back to the report of an import that did not go in whole and retry
<!-- from WORKBOOK.md sha256:a5f23a33733e -->
Status: done
Actor: owner, administrator
Screen: Settings · Data and backups (Import)
Steps:
  1. On opening "Import", if the last import did not go in whole and was not undone, its report shows first, with "This
     is the report of your last import of Restaurant (Nov 24, 2026, 10:30 AM). Not everything went in." or, if it still
     waits for an app being set up, with "Still loading…" and without "Retry what is missing", which is not needed. When
     it comes in, that same report says "Everything went in.", with no jump to the catalogue.
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
If it fails: "The retry failed:" with the reason and the report stays in sight.
Involved: BASE-F32

### BASE-F34 Undo an import
<!-- from WORKBOOK.md sha256:63445c3e5c16 -->
Status: done
Actor: owner, administrator
Screen: Settings · Data and backups (Reset)
Steps:
  1. In "Reset", "Undo an import" ("Removes only what that import brought. What you created afterwards
     stays."): one row per import that brought something and was not undone, with its name, when, who and
     how many rows it brought, and "Undo".
  2. Tap "Undo": "Undo «Restaurant»", with "The 120 rows this import brought will be removed. What you created
     afterwards stays.". It asks to type nothing: it can be imported again.
  3. Confirm with "Undo" (or "Cancel").
  4. "Import undone:" shows with one line per app ("Inventory — 85 rows removed"); what could not be removed
     (something another app still uses) shows apart with its reason. What each section has gets up to date.
In: the import chosen.
Out: exactly the rows it brought removed, also what came in later because it waited for an app, and what it still
waited for no longer comes in; what was created afterwards stays (`base.import.undone`).
If it fails: the reason shows in the dialog itself, which does not close; an
import already undone, "This load was undone already.".
Involved: BASE-F32

### BASE-F35 Export a backup or a template
<!-- from WORKBOOK.md sha256:f4f311ae8d9b -->
Status: done
Actor: owner, administrator
Screen: Settings · Data and backups (Export)
Steps:
  1. Open "Export": "Packs this business's apps — and, if you want, their data — into a file you can load in
     another business or keep as a backup.".
  2. Write the "Name" (the business's comes in; without one, its address's) and choose the "Language"; below,
     the file's final name ("File: casa-ramon_en.blueprint.zip").
  3. Answer "What is this file for?": "Backup of this business" (the one ticked; it takes the customers too)
     or "Template to share" (it never takes customers).
  4. Choose the apps and their data and tap "Export" ("Exporting…").
  5. The file downloads with the browser and "casa-ramon_en.blueprint.zip downloaded." shows.
  6. Asked of the assistant ("I'm opening another bar and want to take the menu and the customers"), it says it is
     done here, in Settings › Data and backups › Export, with "Template to share" or "Backup of this business", and
     what it takes: the products and the services go with their own photos inside. It does not make the file itself.
In: the name, the language, what it is for and what is ticked.
Out: a .blueprint.zip with the apps ticked and, of those that take their data, their rows, with the products' and
the services' own photos inside (INVENTORY-F33); never the sales, people, PINs nor fiscal data. Nothing is kept in the
business.
If it fails: "The export failed:" with the reason; without a name, "Write a name for the file." and it cannot be
exported. Who does not administer the business reads "Only an administrator can export the business.". The
administrator exports just like the owner: what is the owner's alone are the full copies ERPlora keeps before a reset.
Involved: BASE-F112 (inside the app), BASE-F37, INVENTORY-F01, INVENTORY-F26, INVENTORY-F33, INVENTORY-F36, BASE-F36

### BASE-F36 Choose which apps, data and tables travel in the export
<!-- from WORKBOOK.md sha256:da5ff03469f9 -->
Status: done
Actor: owner, administrator
Screen: Settings · Data and backups (Export)
Steps:
  1. In "Export", under "Apps" ("Choose which apps the file registers and whether their data travels with
     it."), one row per app on with two boxes, "App" and "Data". They all come with the app ticked and no
     data; an app with nothing of its own says "Nothing of its own to copy".
  2. Unticking the app unticks its data. "Select all" ticks every app and its data; "Deselect all" unticks
     them all.
  3. Ticking an app's "Data" shows "Data of Inventory" below, with one box per part and its rows;
     unticking one leaves it out. In a template the customers cannot be ticked: "Only in a backup".
  4. While no part of an app is unticked, all of it travels, also what that app brings later on.
In: the apps on and how many rows each part has.
Out: nothing saved; what is ticked travels on export.
If it fails: "The apps of this business could not be loaded." with "Retry"; with no app ticked it cannot
be exported.
Involved: none

### BASE-F37 Reset the business by sections
<!-- from WORKBOOK.md sha256:36c8b38f7f57 -->
Status: done
Actor: owner
Screen: Settings · Data and backups (Reset)
Steps:
  1. In "Reset", "Reset the business": "Removes for good the data you mark. It cannot be undone: if in
     doubt, export a copy first.", with "Export a copy first", which opens "Export".
  2. It says what is never removed: "Only what each section lists here is removed. Sales, invoices, fiscal
     records, people and their access, files and the business's settings always stay.", and "Before emptying, a
     full copy of the business's data is made and kept for 90 days, in «Copies» below.".
  3. One row per section (an app) that has something, with what it has (each part and its rows) and its total.
  4. Tick the sections and tap "Reset the business": "This cannot be undone", with "120 rows will be removed for
     good:" and the breakdown. Type the business's name ("Type «Casa Ramón» to confirm") and tap "Remove for good" (or
     "Cancel").
  5. "Copying the business's data before emptying…" shows, with "Then Inventory, Customers will be emptied. You can
     leave this screen: it goes on by itself.", and then "Emptying Inventory, Customers…". Meanwhile no other is
     offered: "A reset is under way: wait for it to finish.".
  6. "Business reset:" shows with one line per section ("Inventory — 85 rows removed") and "A full copy of the data from
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
An administrator undoes imports, but instead of "Reset the business" and "Copies of the data" reads "Only the
business's owner can reset it or download the copies of its data.": resetting, seeing the copies and downloading them
is the owner's alone, also through the API and from the assistant, which answer that they are not allowed.
Involved: BASE-F34, BASE-F35

### BASE-F38 See the Home up to date after importing a template
<!-- from WORKBOOK.md sha256:5ef2b444fec4 -->
Status: done
Actor: owner, administrator
Screen: Home · Summary
Steps:
  1. While the business has nothing a template brings (a business is born with every app off but Taxes), who
     administers it sees on top "Start with a business like yours" ("Choose the one most like yours: we turn on its apps and
     load its catalogue in one go. Then put in your own details."): up to four templates, one per kind of
     business and in their language when
     there is one (those of its country first), with their description and "Use this one"; "See all templates" opens "Data and backups" and "Not now"
     closes the card on this device.
  2. Tap "Use this one": "Preparing «Restaurant»…" while its apps are turned on and it loads, with no screens in
     between.
  3. In the same card, "Your apps and your catalogue are ready" ("What is left only you can answer: your
     business's details. They are in the list below.") with "Continue", which closes it. If an app is still being set
     up, first "Your apps are being set up" ("Their data will load by itself as soon as they are ready: Website. You can
     carry on.") with "See the report" and "Continue"; the card turns to "Your apps and your catalogue are ready" by
     itself when it comes in, with nothing to tap.
  4. Without reloading, the Home gets up to date: "Finish setting up your business" counts as done the steps
     the template solved and the panels refresh. The same after loading a template or a file from "Data and
     backups".
In: the templates and whether the business is still empty.
Out: what the template brings, as in BASE-F31 (`base.blueprint.imported`): VeriFactu stays off (VERIFACTU-F01).
If it fails: if not everything went in, "Not everything went in" with "These did not go in: Website." (or
"Something else did not go in.") and "See the report"; if an app could not be set up, "An app could not be set up
yet" with "It keeps trying by itself and its data will load when it works: Website. In the report you can try again
now." and "See the report"; if it could not be opened, "That template could not
be opened" with "Nothing has changed in your business:" with the reason and "Try again"; if it was cut halfway,
"The setup did not finish" with "Part of it may be in already. Check it in Settings › Data before trying
again." and "See the report", with no retry. If the templates cannot be read, "The templates to start with
could not be loaded." with "Retry" and "Not now".
Involved: BASE-F01, INVENTORY-F12, VERIFACTU-F01

### BASE-F39 Open System and move between its tabs
<!-- from WORKBOOK.md sha256:a114a0dda4bc -->
Status: done
Actor: owner, administrator
Screen: System · Usage and plan
Steps:
  1. They tap "System" in the side menu, or come from the bell's notice of the failed events.
  2. At the bottom there are four tabs, in this order: "Usage and plan", "Updates", "Failed events" and "Logs". "Usage and
     plan" opens. The tab chosen stays in the address: a link or a reload opens the same one.
  3. A tab that does not exist opens "Usage and plan", and so do the old links to "Resources" and to "Plan and limits"; the
     old backups one leads to "Settings" › "Data and backups".
  4. Whoever does not run the business has no "System" in the side menu: its address, also that of any of its tabs,
     tells them they have no access.
  5. At the end of "Usage and plan" come the cards the apps on in the business put there and that the person may
     see, each with its own: Printing's is "Your printer". An app that is off puts none; turning it
     on or off makes its card appear or go without reloading.
In: the cards of the apps that are on that the person may see.
Out: nothing saved.
If it fails: each tab says its own. If which cards apply cannot be read, none shows and the rest
of the tab goes on; a card that does not load is left out and the others show.
Involved: BASE-F40, BASE-F118, PRINTING-F21, BASE-F41, BASE-F42, BASE-F43

### BASE-F40 See what the business uses and whether to upgrade the plan
<!-- from WORKBOOK.md sha256:3ca66ec72586 -->
Status: done
Actor: owner, administrator
Screen: System · Usage and plan
Steps:
  1. They open "System": "Usage and plan" opens. While it loads: "Reading the system…". At the top, their plan ("Starter
     plan") and, for the owner, "Upgrade plan", which opens this business's plan page on erplora.com; to the
     administrator, in the installed app or where that link does not appear, with no button, "Plans are managed from
     your ERPlora account, on erplora.com.".
  2. Below, a line tells them whether to upgrade. In green, "Your plan is enough". In amber, "You should upgrade:" and
     the motive, with the files or the month's messages from 80 %: "you are almost out of space for files", "the
     assistant's messages are almost spent this month" or "WhatsApp messages are almost spent this month". In red, "You
     have to upgrade:" and the motive: "no more files fit", "the assistant's messages are spent this month", "WhatsApp
     messages are spent this month" or "your business runs out of capacity at its busiest moments". With several
     motives, the most serious wins and, among equals, the fullest. Green only comes when everything that applies could
     be read: with no motives, while something is answering, "Checking your plan…"; if something could not be read, "We
     could not check everything", with "Retry". A motive is said all the same, because it is still true, and what their
     plan does not include is not left to check.
  3. "What your plan includes", from the fullest down: "Files" ("1.2 GB of 5 GB", with "Measured on Nov 24, 2026"),
     "Apps", "People" and "Devices" ("3 of 5"), and the assistant and, with its app on, "WhatsApp" ("120 of 500 a
     month"), each with its bar, in the colour of the line at the top. From 80 %, the files and the messages say
     "Close"; on reaching the limit, any of them says "Full".
  4. People, devices and apps at their limit do not change the colour at the top: a Free business with 1 of 1 device is
     fine. Under the green line it reads "People at the limit: to add more, upgrade the plan.".
  5. With a limit of 0, "3 · No limit", with no bar. Messages cannot be that: with 0, "Your plan does not include the
     assistant" or "Your plan does not include WhatsApp", with no bar, and they are no motive for anything.
  6. At the end of the list, "Capacity": "2 of 5 connections", the highest measured today against what it
     really has (what its plan includes or, if that is less, what the service gives), with its bar. It never goes by
     percentage, because with a limit of 1 the first operation of the day is already 100 %, but by the times someone got
     "Too many requests. Try again in a moment.": "Fell short 3 times this week". Then, if a bigger plan would give
     more, it moves to the top of the list and the line at the top turns red.
  7. If their plan already includes all the capacity the service gives, a bigger plan would give them no more: the row
     offers no upgrade, does not turn the top red and, when it falls short, says "You already have the maximum capacity:
     tell us in "Report a problem".". Green does not come at the top either: the line, neutral, says "You do not need to
     upgrade: you already have the maximum capacity, but it sometimes falls short.". If there is another motive (the files
     or the messages), that one wins.
  8. "For your information", what no plan limits, with no bar or pill: "Requests this month", the ones the business has
     served since day 1; "Active now", the people with activity in the last 5 minutes; "Last 30 days" and "Database
     size", with "Measured on Nov 24, 2026". Neither CPU nor memory: they cannot be attributed to a business, so they do
     not appear, nor does any sentence in their place.
  9. With motives the hub knows without asking erplora.com (the files, the capacity and WhatsApp), the bell of whoever
     runs the business carries the notice "1 plan limit to review", which adds one per motive, with "Your business is
     reaching what its plan includes: some things may stop or slow down until you upgrade.", and "See the plan’s
     usage" opens "System" on "Usage and plan". Without them, the notice goes away.
  10. Whoever runs the business can ask the assistant the same ("how much space do I have left?", "how many requests
      have we had this month?") and it answers with these figures. Anyone can ask it for the assistant's messages of
      the month.
In: what is measured of this business: every night, what its files and its database take up and the people who had
activity; during the day, its requests, its connections and who has activity. The plan's limits erplora.com passes to the
hub, the apps it chose, the assistant's messages erplora.com counts and WhatsApp's.
Out: nothing saved by looking at the screen. What is measured stays per business and day, and erplora.com collects it
every night so ERPlora's team sees the same (HUBS-F22).
If it fails: "We could not read the system" — "The figures and the logs are not available right now. You can try again."
with "Retry". What has not been measured yet says so, never with a zero: before the first night, "Measured every night:
the first figure comes tomorrow."; with no measure of the capacity or the requests today, "Not measured today yet.";
WhatsApp before erplora.com sends its figures, "Not measured yet."; if the requests or the times it fell short have been
counted for less than their period, they say "Since Nov 24, 2026". The assistant is asked of erplora.com apart: if it
does not answer, its row says "Not available right now", with no figure, and the screen goes on; the same if WhatsApp
cannot be read. In a demo, instead of everything: "Use is not measured in a demo: its data is deleted when it ends.".
While the hub does not know the plan: "We do not know this business's plan yet: it shows up as soon as erplora.com sends
it." and, under "What you use", the figures with no limit, bar, pill or line at the top. ERPlora's own business will
never have one: instead it says "This is ERPlora's own business: it has no plan.", with the same figures.
Involved: BASE-F10, BASE-F11, BASE-F39, BASE-F57, BASE-F72, BASE-F73, BASE-F108, HUBS-F21, HUBS-F22, BASE-F104

### BASE-F41 Know which version is running and when it was updated
<!-- from WORKBOOK.md sha256:93231d294774 -->
Status: done
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
Involved: BASE-F116

### BASE-F42 See the log of what happened in the system
<!-- from WORKBOOK.md sha256:26d21a9b6230 -->
Status: done
Actor: owner, administrator
Screen: System · Logs
Steps:
  1. They open the "Logs" tab: the title is "Event log".
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
<!-- from WORKBOOK.md sha256:7b01ec3e1db1 -->
Status: done
Actor: owner, administrator
Screen: System · Failed events
Steps:
  1. They come from the bell's notice of the failed events or tap the "Failed events" tab.
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
connection and try again." with "Retry" in sight: a failure never shows as "All in order".
Involved: BASE-F10

### BASE-F44 Resend a failed event
<!-- from WORKBOOK.md sha256:89f57c907252 -->
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
<!-- from WORKBOOK.md sha256:e365ee832500 -->
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
If it fails: "Could not resend:" and the reason, as in "Resend a failed event".
Involved: BASE-F44

### BASE-F46 Discard a failed event
<!-- from WORKBOOK.md sha256:6567006cfb22 -->
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
If it fails: "Could not discard:" and the reason, as in "Resend a failed event".
Involved: BASE-F44

### BASE-F47 Report an error of the screen without anyone asking
<!-- from WORKBOOK.md sha256:d43fcf749b1e -->
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
<!-- from WORKBOOK.md sha256:9c94834ba542 -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Settings · General, Settings · Business, Settings · Printing, Settings · Data and backups
Operations: none
Steps:
  1. Tap "Settings" in the side menu, or arrive from a link on another screen.
  2. At the bottom, the tabs "General", "Business", "Printing" and "Data and backups", each one only for whoever can use
     what it holds: "Printing", for whoever sets up the Printing app (owner, administrator and manager), and "Data and
     backups", for whoever runs the business. An employee has "General" and "Business". "General" opens. The tab chosen
     stays in the link, so a saved link comes back to it and Back leaves Settings instead of walking its tabs. On the
     phone the four fit, whole.
  3. Old links still take you to their place: the one of the old "General" opens "General", the one of the old
     taxes tab opens "Business", and the one of a tab that no longer exists, or that the person does not have, opens
     the first.
  4. In "Printing", "Printers and ticket" ("Add your printer and set up the printed and digital ticket") opens
     the Printing app; when it is not there, it says "Install the Printing app to add your printer and set up the
     ticket" and takes you to "Apps".
In: the business's apps.
Out: nothing saved.
If it fails: it does not fail: it is navigation. Each tab says in itself when it could not load its own.
Involved: PRINTING-F06, BASE-F29, BASE-F49, BASE-F62

### BASE-F49 See the business's country
<!-- from WORKBOOK.md sha256:befe3104e7be -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Settings · Business
Steps:
  1. In "Business", "Country" ("The one of its taxes and its invoices") says, in the person's language, the
     country the business was signed up with on erplora.com.
  2. It is not chosen here: below it reads "The country does not change once the business is ready.", because
     its invoices are of one country. While the business is being prepared, it is changed on erplora.com.
In: the country erplora.com signed the business up with.
Out: nothing saved; with it, the business's templates come first and "Finish setting up your business" knows
which steps are its own.
If it fails: if the business's details cannot be read, "Couldn’t load the business’s data" with "Retry". A demo
has no country: "—".
Involved: HUBS-F15, BASE-F01, BASE-F29

### BASE-F50 See the business's currency
<!-- from WORKBOOK.md sha256:448623f4586f -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Settings · Business, Home · Summary, Home · Activity
Steps:
  1. In "Business", "Currency" ("Its country’s, for prices and totals") says the currency with its code and its
     name in the person's language: "EUR · Euro".
  2. It is not chosen: it is the one of the business's country, as in the market's payment terminals. A business
     without a country (a demo) is in euros.
  3. On the Home, the amounts of the panels (such as "Sales, last 7 days") and of "Activity" are in that currency,
     with its symbol and its decimals, as a till of that country prints them: "zł" in a business in Poland, "€" in
     one in Spain. While the business has not answered, the amount shows as "—", never in another currency or with
     guessed decimals.
  4. The apps that show prices or amounts are in that same currency, Appointments too (each service's price when
     booking and the appointment's "Total") and the preview of Online booking.
In: the business's country.
Out: nothing saved.
If it fails: as in "See the business's country".
Involved: BASE-F49

### BASE-F51 Change the business's language on erplora.com
<!-- from WORKBOOK.md sha256:2cc38c90bc3e -->
Status: done
Actor: owner, administrator
Screen: Settings · Business
Steps:
  1. In "Business", "Business language" ("The one of whoever has not chosen their own") says the business's
     language by its name.
  2. Tap "Change on erplora.com": the business's settings on erplora.com open in another tab (in the installed app,
     in the device's browser), where it is changed and "Save changes" is tapped. In the Google Play copy
     the button is not there: it is changed on erplora.com from a browser.
  3. Without reloading, "Business" shows the new language as soon as the business receives it; the same with the
     name and the time zone.
In: the language erplora.com saved.
Out: nothing saved in the business: it receives it from erplora.com (`base.hub.registered`). Whoever has not chosen
a language of their own in "My profile" and enters with their PIN sees the hub in the business's, not in their
browser's; with their account, in their erplora.com account's (BASE-F64).
If it fails: if the business does not answer, erplora.com keeps the change and sends it again;
meanwhile, "Business" stays with the previous one. Whoever does not administer the business does not see the
button: "Only the owner or an administrator changes them, on erplora.com.". In a demo, "This demo has no business
on erplora.com: its data does not change.".
Involved: HUBS-F15, HUBS-F08, BASE-F64

### BASE-F52 Enter with the erplora.com account
<!-- from WORKBOOK.md sha256:7bece8ed6387 -->
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
<!-- from WORKBOOK.md sha256:3ff821a2583d -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Access
Operations: none
Steps:
  1. At erplora.com, with the session open, they tap enter their business.
  2. The business opens with the person already in, on **Home**, without going through any sign-in screen.
In: the one-time pass erplora.com gives.
Out: the same as BASE-F52: the session and this browser as a trusted device of the business, so it then offers
the PIN pad, shows in "Devices" and its mode can be changed.
If it fails: an expired or already used pass opens nothing: the business asks for erplora.com's sign-in again.
Involved: BASE-F52

### BASE-F54 Choose the PIN the first time one enters a till
<!-- from WORKBOOK.md sha256:b447aa48f50c -->
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
<!-- from WORKBOOK.md sha256:7c8ec3f06d4d -->
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
<!-- from WORKBOOK.md sha256:02f7b0bae2a8 -->
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
<!-- from WORKBOOK.md sha256:28a72686e4b4 -->
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
<!-- from WORKBOOK.md sha256:9b2c63c0a89a -->
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
<!-- from WORKBOOK.md sha256:c212f35c2ffd -->
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
<!-- from WORKBOOK.md sha256:f422c0e62b90 -->
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
<!-- from WORKBOOK.md sha256:0a4ca1b69bbc -->
Status: done
Actor: owner, administrator, manager, employee
Screen: The user menu
Operations: none
Steps:
  1. They open the user card at the top of the side menu (on a phone, first the menu with the bar's button).
  2. They tap "Sign out".
  3. On a till with the PIN pad it goes back to **Access**, ready for the next person. On another device, erplora.com
     asks "Sign out of erplora.com?": "Sign out" ends it too and erplora.com asks to sign in again; "Stay signed in"
     leaves it open and shows the account's businesses.
In: the session.
Out: the session closed in the business; erplora.com's, only if the person confirms it.
If it fails: if the business does not answer, the session expires by itself.
Involved: BASE-F113 (in the Android app, it stops listening before leaving); HUB_APP-F04 (ERPlora/app: inside the
app, "Change business" in the bar signs out the same way and only then forgets the business)

### BASE-F62 Decide whether this device is shared or personal
<!-- from WORKBOOK.md sha256:817b601438cc -->
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
<!-- from WORKBOOK.md sha256:514223787757 -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Your business is being prepared
Operations: none
Steps:
  1. They open the address of a business erplora.com is still preparing (just created).
  2. "Your business is being prepared" shows — "It takes a few seconds. This page refreshes by itself.".
  3. When it is ready, the page refreshes and they come in as always, with Taxes already on (BASE-F14).
In: the business's state erplora.com passes on.
Out: nothing saved.
If it fails: an address that belongs to no business does not exist; a business that was closed says "This hub
is no longer available.". While ERPlora's staff keeps the platform frozen for a database upgrade (a few minutes,
hub#930), the business waits to be prepared: the page stays on "Your business is being prepared" and comes in by
itself as soon as the freeze is lifted and it is done.
Involved: none

### BASE-F64 Change my details, photo, language and appearance
<!-- from WORKBOOK.md sha256:d3f6f60ee728 -->
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
     palette", "Theme": "System (auto)", "Light", "Dark", and "Interface size": 80, 90, 100, 110 or 120%, default
     100%) are saved on choosing and applied at once on any device; "Use the business’s appearance" undoes their own
     and returns the size to 100%. The language reaches the whole open application, also the texts the server sends
     (the side menu, "My apps", the checklist, the Home's panels and the bell), without reloading or going back to
     Home.
  5. If they ask the assistant for it ("switch me to English"), the card says only what they asked for, with the name
     of its datum ("Language: English", "Interface scale: 110%"; what goes back to the business's, by its name: "The
     business's language"). On confirming it only that changes, and
     the theme, the palette and the size they did not name stay as they were. The new language applies just as from the
     selector: the open application switches to it without reloading, and stays in it on reloading or opening it again
     on this device.
In: the profile of whoever has the session.
Out: their name in this business (the one in the side menu, on the faces and in "Devices"), their photo, their language and their
appearance, including the interface size, which follow them on any device they enter, with their PIN, badge or account. With "Use the
business’s language", they enter with a PIN in the business's and with their account in their erplora.com
account's (BASE-F51). The email is only for contact: it does not change the erplora.com account.
If it fails: if the profile could not be read, "Could not load the profile" — "Your details stay the same. Check
the connection and try again." with "Retry". On saving: "Could not save the profile"; a refused photo: "Could not
save the photo. Use a JPG, PNG or WebP of up to 2 MB."; preferences: "Could not save your preferences. Check the
connection and try again.".
Involved: BASE-F51

### BASE-F65 Change my PIN from My profile
<!-- from WORKBOOK.md sha256:e5c17aa3ac08 -->
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
If it fails: a different length: "The PIN must have 4 digits."; the two do not match: "The two PINs do not
match."; easy to guess: "That PIN is too easy to guess: avoid repeated digits (1111) and runs (1234)."; someone
else already uses it: "Another active person already has that PIN: choose a different one."; the current one is
not it: "That is not your current PIN. Type it right to set a new one."; thirty tries in an hour: "Too many tries
to change the PIN." and the minutes they have to wait.
Involved: BASE-F54

### BASE-F66 Choose how many digits the business's PIN has
<!-- from WORKBOOK.md sha256:c9e0ad91da78 -->
Status: done
Actor: owner, administrator
Screen: Settings · General
Steps:
  1. With the PIN pad on, under "PIN digits" they choose "4 digits" or "6 digits".
  2. It is saved at once. Below: "Everyone types the same number of digits, which is what lets the keypad enter
     at the last one instead of asking you to confirm. The PINs in use keep working until their owner changes
     them.".
  3. From then on, the PIN pad, the screen where each person creates their PIN and **My profile** ask for that length.
In: the choice.
Out: the length of the business's PIN. It does not touch the PINs there are.
If it fails: "Could not change it. Check the connection and try again.".
Involved: BASE-F67

### BASE-F67 Decide whether the till asks for a PIN and when it asks again
<!-- from WORKBOOK.md sha256:c364906627d2 -->
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
     below what happens ("A till nobody touches for 10 minutes closes the session and shows the PIN pad: the
     next sale carries the name of the next person.").
  4. Each change is saved at once, with no button, and the card shows what the business confirms.
  5. Through the assistant ("I want everyone to have to type their PIN at the till so we know who sells"), the
     assistant reads how it is and says it by the names of this card: with the PIN pad on and "Until signing
     out", each person already enters with their PIN and every sale carries their name. To ask again after
     inactivity, it first asks how many minutes (1, 5, 10, 15 or 30): it never makes them up, nor do the stored
     ones apply unseen. The card, with each datum on its own line, says each control it changes by its
     name and the value it will have here: "Show PIN pad: Yes" and "Ask again after inactivity: 10 min"; "Until
     signing out", "Show PIN pad: No" or "PIN digits: 6 digits" depending on the change. If only the minutes
     change and the business asks "Until signing out", it says "Ask again after inactivity: Until signing out",
     which is what it will still say here.
In: how the business asks for the PIN.
Out: whether it asks and when it asks again, for every till of the business. Turning it off and on again goes
back to asking per shift.
If it fails: "Could not change it. Check the connection and try again.". If it cannot be read: "Could not load
how the business asks for the PIN. Check the connection and try again.". Whoever does not run the business sees
the controls off and "Only an administrator can change whether it asks.". Through the assistant, "after
inactivity" without its minutes does not reach the card: it goes back to the assistant, which asks how many.
Involved: BASE-F55, BASE-F59, BASE-F97, BASE-F98

### BASE-F68 See the devices someone has entered on
<!-- from WORKBOOK.md sha256:23371c4da102 -->
Status: done
Actor: owner, administrator
Screen: Settings · General
Steps:
  1. In **Settings**, under "Devices": "The devices someone has entered on. If you lose one, remove it here: its
     session closes at once and it can no longer enter with a PIN.".
  2. A row per device, the last used first: the name the business gave it (or "Unnamed device" and what it is, for
     example Chrome · Android), "The one you are using" on the current one, the mode ("Asks for a PIN" or "Stays open"),
     "In use right now" or "Last used Nov 24, 2026, 10:30 AM", "Its session stays open until Nov 24, 2026, 10:00 PM" and
     "Last entered: Ana". Never its identifier.
  3. It updates by itself when someone changes, names or removes a device.
In: the business's devices.
Out: nothing saved.
If it fails: whoever does not run the business sees "Only an administrator can see and remove the devices.",
with no list. If it does not arrive: "Could not load the devices. Check the connection and try again.", never
"Nobody has entered from any device yet.", which is only for a truly empty list.
Involved: BASE-F69, BASE-F70, BASE-F71

### BASE-F69 Name a device
<!-- from WORKBOOK.md sha256:31e9751c299c -->
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
<!-- from WORKBOOK.md sha256:f2438077c242 -->
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
  4. From the assistant ("remove the phone I lost this afternoon"), the card asks to type CONFIRM and,
     under "What will happen", says when it was last used ("Last used: Nov 22, 2026, 4:18 PM"): two devices
     without a name are called the same ("Chrome · Linux") and only their last use tells them apart.
In: the device.
Out: the device forgotten and its sessions ended: the device is cut off, not the person, who can enter on it
again with their account.
If it fails: "Could not remove this device. Check the connection and try again." or "That device is no longer
registered here. Refresh the list."; what was refused never stays as done.
Involved: BASE-F58, BASE-F68, BASE-F98

### BASE-F71 Remove at once the devices nobody uses
<!-- from WORKBOOK.md sha256:c6c12cce7727 -->
Status: done
Actor: owner, administrator
Screen: Settings · General
Steps:
  1. If there are devices nobody has used in 30 days (never the one in hand), "Remove the device unused for 30
     days" or "Remove the 3 devices unused for 30 days" shows.
  2. On tapping it, "Remove 3 devices nobody has used for 30 days?" (or "Remove the device nobody has used for
     30 days?") with "They stop showing here and, to use one again, someone will have to enter on it with their
     account. Those used in the last 30 days and the one you are using stay.".
  3. They confirm with "Remove".
  4. From the assistant ("clear out the old devices nobody uses any more"), the card asks to type CONFIRM and, under
     "What will happen", says how many it will remove and which, by their name, the last used first ("Devices to remove:
     2" and "Which: Chrome · Linux, Bar"); the one in use is never among them. If none has gone 30 days without being
     used, no card shows and the assistant says so: "No device has gone 30 days without being used, so there is nothing
     to remove.".
In: which devices nobody has used for 30 days.
Out: those devices forgotten, as in BASE-F70.
If it fails: "Could not remove the unused devices. Check the connection and try again.".
Involved: BASE-F70, BASE-F98

### BASE-F72 See the business's files
<!-- from WORKBOOK.md sha256:efc654bc9574 -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Files
Steps:
  1. Tap "Files" in the side menu. While it loads: "Loading files…".
  2. See the tree of folders on the left (on a narrow screen, the "Folders" selector), the open folder's path, what
     it holds in "Grid" (what shows first) or in "List", and "Space": what the business's files and its apps' take,
     against the plan's limit ("1.2 GB of 5 GB") or, if it has none, "1.2 GB used · No limit".
  3. Go into a folder by tapping it in the tree, in the grid or in the selector, and come back through the path. The
     open folder stays in the address, so it can be shared with the team.
  4. Search by name in "Search files…", only inside the open folder; with no results, "No file in this folder
     matches “invoice”.".
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
<!-- from WORKBOOK.md sha256:66add13d9bb6 -->
Status: done
Actor: owner, administrator
Screen: Files
Steps:
  1. In the open folder, tap "Upload file" and choose one or several, or drag them onto the manager ("Drop the files
     to upload them here"). While they upload: "Uploading 2 of 5…".
  2. "Files uploaded." shows and they appear in the folder. If there was already one with the same name, it is not
     overwritten: the new one is kept as "menu (1).pdf" and "Uploaded as “menu (1).pdf”: there was already one with that
     name." shows.
  3. For a new folder, tap "New folder", type the "Folder name" (up to 100 characters) and tap "Create folder".
     "Folder created." shows and the folder appears in the tree and in the open folder.
  4. From the assistant, a file attached in the chat is kept the same way: the person asks it to keep it in a folder,
     the assistant uploads it with its card, which says it by its name, and after the "yes" it is in the folder, with
     the same rules.
In: the files, up to 25 MB each, or the folder's name; the open folder.
Out: the file or the folder, in the business's files (`base.file.uploaded`, `base.file.folder_created`).
If it fails: each refused file says why, without stopping the others: "Could not upload “menu.pdf”:" and the reason,
"That file weighs more than 25 MB, the most Files takes.", "Programs (.exe) can't be kept in Files: they could harm
whoever opens them.", "There is no space left for that file: your plan includes 5 GB." or "The file did not arrive
whole. Upload it again.". What was uploaded and what was refused show in a single notice: one notice shows at a time and
the new one closes the one before, never one on top of another. When making a folder, the dialog stays open with the
reason: "That name is not valid. Use a name without slashes or lone dots." or "There is already a file or folder with
that name here.". Whoever does not administer the business does not see the buttons and, if they try anyway, reads "Only
an administrator can change the files.".
Involved: BASE-F40, BASE-F94

### BASE-F74 Preview and download a file
<!-- from WORKBOOK.md sha256:9fba0b1d1a58 -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Files
Steps:
  1. Tap a file, or "Open" in its ⋮. A large viewer opens inside the hub, with the name as its title, "Download" and
     "Close".
  2. It shows images (whole in the viewer, never larger than the original, with "Zoom in" and "Zoom out"), PDFs (the
     first 30 pages; if it is longer, "Showing the first 30 of 48 pages. Download the file to read it
     all."), text, logs and code, CSV and TSV as a table (a CSV in its own columns, whether separated by commas or by
     semicolons, as Spanish Excel saves it), audio and video. Of a very long text, "Showing the beginning
     of the file. Download it to read it all."; of a table of more than 500 rows, "Showing the first 500 rows.
     Download the file to see them all.".
  3. A data file (.json) is shown as a tree that folds and unfolds by parts, like the browsers' JSON viewer: the first
     two levels open and each object or list with what it holds ("6 fields", "2 items"); of an open branch with more
     than 500 entries, "120 more. Download the file to see them all.". One that is not valid JSON is shown as it
     is, with "This file is not valid JSON: it is shown as it is.".
  4. An Excel sheet (.xlsx or .xlsm) is shown as a table, with one tab per sheet if it has several, like Excel: the
     first row as the header, numbers and dates as the sheet shows them, in the person's language, and the first 500
     rows of each sheet (with the same notice); an empty sheet, "This sheet is empty.". Its macros never run.
  5. A Word document (.docx) is shown as text with its basic formatting: headings, bold, italics, underline, lists,
     tables, its own images and links (which open apart); one with no text, "This document has no text.". Nothing in
     the document runs: neither code nor links that are not to a website or an email.
  6. Any other type (the old .xls and .doc, presentations…): "No preview" with "This type of file can't be shown
     here. Download it to open it with an app on your device.".
  7. "Download", in the viewer or in the ⋮, saves the file with its name.
In: the file, which the hub reads from its store with the person's session; the browser never goes to the store and
the file is not kept in any cache. The sheet and the document are read in the browser itself.
Out: nothing saved.
If it fails: "The file could not be opened" with "The file's content did not arrive. Check the connection and try
again.", never a blank viewer; if it arrived but could not be read (damaged or saved in another format), "The file
could not be read" with "It may be damaged or saved in another format. Download it to open it with an app on your
device."; a sheet or a document over 10 MB (or one that would take too much once opened) is not even fetched: "Too
large to preview" with "The preview opens files of up to 10 MB. Download it to open it with an app on your device.".
"Download" is always at the top. If it could not be downloaded, "Could not download “menu.pdf”:" and the reason.
Involved: BASE-F112 (inside the app)

### BASE-F75 Move and rename a file or a folder
<!-- from WORKBOOK.md sha256:f9982b93331f -->
Status: done
Actor: owner, administrator
Screen: Files
Steps:
  1. To rename, choose "Rename" (or "Rename folder") in the ⋮: a dialog with the current name already typed (up to
     255 characters). Tap "Rename" and "Renamed." shows.
  2. To move, choose "Move to…": "Move “menu.pdf”" with the business's folders as a tree, starting at "Files"; choose
     one and tap "Move". The file or the folder can also be dragged onto a folder of the tree or of the grid. "Moved
     to “Invoices”." shows (to the very top, "Moved to “Files”.").
  3. A folder is moved or renamed with everything in it. If it is the open folder (its ⋮, beside the path), the
     screen follows it to its new place. It is never offered as a destination of itself or of its own folders.
In: the file or the folder and the new name, or the destination folder.
Out: the change, in the business's files (`base.file.renamed`, `base.file.moved`).
If it fails: the dialog stays open with the reason: "There is already a file or folder with that name here.", "It is
already in that folder.", "A folder can't be moved inside itself.", "That name is not valid. Use a name without slashes
or lone dots." or "That file or folder no longer exists. Refresh the list."; when dragging, "Could not move:" and the
reason. Whoever does not administer the business does not see "Rename" or "Move to…" and, if they try anyway, reads
"Only an administrator can change the files.".
Involved: none

### BASE-F76 Delete a file or a folder
<!-- from WORKBOOK.md sha256:391b4ad55eb5 -->
Status: done
Actor: owner, administrator
Screen: Files
Steps:
  1. Choose "Delete" (or "Delete folder") in the ⋮ of a file, of a folder or of the open folder.
  2. The screen asks: "Delete file" with "You are about to delete “menu.pdf”. This cannot be undone.", or "Delete
     folder" with "You are about to delete “Invoices” and everything in it. This cannot be undone.".
  3. Tap "Delete" (or "Cancel"). "File deleted." or "Folder deleted." shows. If the open folder was deleted, the
     screen goes up to the one above.
In: the file or the folder.
Out: the file or the folder, with everything it held, out of the business's files; there is no bin
(`base.file.deleted`).
If it fails: "Could not delete:" and the reason, "That file or folder no longer exists. Refresh the list." or "Your
session has expired. Sign in again and try once more.". Whoever does not administer the business does not see
"Delete" and, if they try anyway, reads "Only an administrator can change the files.".
Involved: none

### BASE-F77 Reach the plan's limit of people
<!-- from WORKBOOK.md sha256:1f393ea46e21 -->
Status: done
Actor: owner, administrator
Screen: Employees · Staff
Steps:
  1. In **Employees › Staff**, above the table, how many of the plan's places are taken: "3 of 5 places
     taken", "3 people · no limit" or, if erplora.com has not said the plan, "3 people". The accountancy
     firm takes no place: it is on the list, but it does not count here nor in "Usage and plan" of System.
  2. With every place taken, "Every place of your plan is taken" shows with "Remove on erplora.com someone who no
     longer works here, or move to a plan with more places."; on the web, and for the owner, with "Upgrade plan".
  3. To invite somebody else, "Invite on erplora.com" leads to "Members" of the business, where the limit applies
     (in the installed app, in the device's browser; the Google Play copy does not have it).
In: the people of the business and its plan's places, as erplora.com sends them.
Out: nothing saved.
If it fails: "The people of this business could not be loaded." with "Retry", never "Nobody is in this business
yet.".
Involved: BASE-F81, BASE-F83

### BASE-F78 Remove a person's PIN
<!-- from WORKBOOK.md sha256:ad0ea33f76da -->
Status: done
Actor: owner, administrator
Screen: A person's page
Steps:
  1. In **Employees › Staff**, they tap the person: their page opens.
  2. Under "PIN", "Has a PIN since Nov 24, 2026, 10:30 AM." and "Remove the PIN".
  3. They tap it: "Remove the PIN" with "Ana will stop entering the tills with their PIN. With their erplora.com
     account they still get in.". They confirm with "Remove the PIN".
  4. "PIN removed." shows and the page says "No PIN: the person chooses it in “My profile” or the first time they
     enter a till.".
In: the person.
Out: the person without a PIN: they leave the faces of the tills at once. Event `base.person.pin_removed`.
If it fails: "The PIN could not be removed."; only the owner changes the owner's way in: "Only the owner changes
the owner's way in.".
Involved: BASE-F81, BASE-F55

### BASE-F79 Give a person a badge or take it away
<!-- from WORKBOOK.md sha256:4a552876a64d -->
Status: done
Actor: owner, administrator
Screen: A person's page
Steps:
  1. On the person's page, under "Badge": "Pass the card and it fills itself: no need to click here first. You can
     also type the number, for a key fob or an engraved tag.".
  2. They pass the card over the reader (or type the number) and tap "Save badge": "Badge saved." and "Has a badge
     since Nov 24, 2026, 10:30 AM.".
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
<!-- from WORKBOOK.md sha256:c83ff036864d -->
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
<!-- from WORKBOOK.md sha256:58cb08c8f9c7 -->
Status: done
Actor: owner, administrator, manager, employee, accountancy firm
Screen: Employees · Staff
Steps:
  1. In **Employees › Staff**, a row per person (on a phone, a card): **User** (with "You" on one's own; in a row, a
     name that does not fit is cut and shows whole on hovering over it), **Email** (only for whoever sees the team's
     contact details: owner, administrator and manager), **Role** (the accountancy firm, the last one), **Access** and
     **Status**.
  2. **Access** says how they get in: "Account" always, and "PIN" and "Badge" if they have them (for example,
     "Account + PIN + Badge").
  3. **Status** says "Active" or, if erplora.com already invited them and they have not come in yet, "Not in yet".
  4. They search with "Search person…". Whoever runs the business taps a row to open the person's page.
In: the people of the business.
Out: nothing saved. It updates by itself when somebody chooses or loses their PIN or their badge.
If it fails: "The people of this business could not be loaded." with "Retry".
Involved: BASE-F77, BASE-F78, BASE-F79, BASE-F119

### BASE-F82 See the business's roles and what each one allows
<!-- from WORKBOOK.md sha256:3e9bff34693d -->
Status: done
Actor: owner, administrator, manager, employee, accountancy firm
Screen: Employees · Roles; Employees · Roles · What it allows
Steps:
  1. In **Employees › Roles**: "These are the roles of this business. Each person gets one when invited on
     erplora.com, and it is changed there.".
  2. A row per role (on a phone, a card): "Owner", "Administrator", "Manager", "Employee" and "Accountant", with
     "Basic", how many people have it and how many permissions it gives. They are erplora.com's basic roles:
     each app brings what it gives each basic role in it, and an app may bring a basic role of its own when its
     features call for it. Below them, by their name, the business's own roles, with "Custom": whoever
     has one counts in it and not in the one of their invitation, save the owner, who is always the owner. One of the
     business's own with permissions it does not carry yet also says "To review".
  3. "Accountant" is the role of the firm that keeps the business's books, and it only reads: everyone's sales, with
     the business's totals, and the invoices issued, which it opens, prints and downloads, each with its taxes and
     its VeriFactu record. Its menu has Sales and Invoicing. It does not sell, charge, issue or rectify invoices nor
     change any setting, and it takes no place of the plan.
  4. Tapping a role opens "What it allows", with the role's name at the top, "What this role lets a person do in this
     business, app by app. It is given on erplora.com and is not changed here." and "People with this role: 2".
     Below, a panel per app: "The business" first, then each app that is on by its name and "Sensitive data" last.
     In each panel, the phrase of each permission and its state: "Allowed", "With approval" (the person does it if a
     manager approves it with their PIN there and then) or "No". For example, the employee sees in "Sales
     & POS" "Void a sale" with "With approval". An app that is off does not show. It is read only: nothing is
     changed here. A role of the business's own says "What this role lets a person do in this business, app by app."
     and shows what the business saved; what no role of the business can give, owning the business, does not show.
     Whoever manages the roles adjusts it right there.
  5. Whoever manages the roles (the owner and the administrator, or whoever has it in a role of the business's own)
     makes one with "New role" or "Duplicate" and, in "⋮", edits or deletes the business's own.
  6. Whoever runs the business has "Change roles on erplora.com" (in the installed app, in the device's browser; the Google Play copy does not have it).
In: the roles, the people of the business, the apps that are on and what each app gives each role.
Out: nothing saved.
If it fails: "The roles could not be loaded." with "Retry"; in "What it allows", "Could not load what this role
allows." with "Retry", and a role that is not one of the five nor one of the business's own, "This role does not exist
in this business.".
Involved: BASE-F83, BASE-F84, BASE-F127, BASE-F128, BASE-F129, BASE-F130, BASE-F131, BASE-F77

### BASE-F83 Give a person a basic role
<!-- from WORKBOOK.md sha256:45776a5fe453 -->
Status: done
Actor: owner, administrator
Screen: Employees · Roles
Steps:
  1. In **Employees › Roles** or on a person's page, "Change roles on erplora.com" or "Open on erplora.com" leads to
     "Members" of the business (in the installed app, in the device's browser; the Google Play copy does not have
     them).
  2. There they change the role.
  3. Back here, the person shows with their new role. If they have the hub open, what they see and what
     they may do change at once, without ending their session. If the business gave them a role of its own, that one
     still rules.
In: the role chosen on erplora.com.
Out: the person with their new role, as erplora.com sends it, and their session open.
If it fails: whatever erplora.com says.
Involved: BASE-F82, BASE-F13, BASE-F130

### BASE-F127 Make a role of your own from another
<!-- from WORKBOOK.md sha256:3de28f523a3f -->
Status: done
Actor: owner, administrator
Screen: Employees · Roles; Assistant
Steps:
  1. In **Employees › Roles**, "Duplicate" in the row of a role, basic or one of your own, or "New role" at the top,
     which starts from the employee's.
  2. In "New role" they type the "Name" and, if they want another, choose "Based on" among all the roles: "It will allow
     the same as that role. Then adjust what it allows.".
  3. "Create role": the role is made with the same the other one allows, app by app, save owning the business, which no
     role of your own gives. "Role Cashier created" shows and it opens to adjust it.
  4. It shows at once in **Employees › Roles**, with "Custom" and nobody in it; it is given to a person by asking the
     assistant. From then on it does not change with the role it came from.
  5. It is also asked of the assistant: "create the role Cashier from Employee", with a description if wanted. The card
     says "Based on: Employee" and "Name: Cashier", and once accepted it is made the same way.
In: the role it comes from, the name (up to 80 letters) and, if wanted, the description.
Out: the business's own role. Event `base.role.created`. It never leaves the business: erplora.com does not know it.
If it fails: without a name, "Create role" cannot be pressed (the assistant and the API: "Give the role a name."); with
the name of another role of your own, capitals aside, "There
is already a role with that name. Choose another."; a role that is not there, "This role does not exist in this
business.". Nobody gives what they do not have: if the role it comes from allows something whoever makes it may not do, or
leaves "With approval" something their own role says "No" to, "A role may not allow more than you may do yourself." and
it is not made. What is refused is said in the window itself, which stays open. Whoever does not manage roles has no
"New role" nor "Duplicate", the assistant does not offer it to them and the API answers 403.
Involved: BASE-F82, BASE-F97, BASE-F128, BASE-F129, BASE-F130

### BASE-F128 Adjust what a role of your own allows
<!-- from WORKBOOK.md sha256:784762e39360 -->
Status: done
Actor: owner, administrator
Screen: Employees · Roles · What it allows; Assistant
Steps:
  1. In **Employees › Roles**, tap a role of your own, or "Edit" in its "⋮". At the top, "What this role lets a person do
     in this business, app by app. Whoever has it notices as soon as it is saved.", how many people have it and its
     "Name" and "Description", changed right there. Below, the same panels of "What it allows": each permission
     with its phrase and a switch or, for what a manager can approve with their PIN, "Allowed", "With approval" or "No".
  2. They change what they want and press "Save" at the end: "Role saved.". With nothing changed, "Save" cannot be pressed.
  3. If another person saves it meanwhile, what was not touched here is brought up to date.
  4. It is also asked of the assistant: "the Cashier role can't void sales", "call the Cashier role Evening till".
     The card says the role, each permission with the same phrase as "What it allows" and what it becomes ("Allowed",
     "With approval" or "No"), and, under "What will happen", how many people have that role. It asks to type CONFIRM,
     and once accepted only what was asked for changes.
  5. If somebody has the role, what they see and what they may do change at once on their devices, without ending their
     session.
  6. An app turned on after the role was saved gives what it gives the basic role it came from; a permission an app adds
     later comes in as "No". In both cases the role is left to review until it is saved with them, and the bell says so.
     Opened, it says "New permissions to review" at the top and "To review" on each: "Save", changing something or
     nothing, leaves them reviewed.
In: the role and what changes: the name, the description or the state of each permission.
Out: the role changed. Event `base.role.updated`.
If it fails: a basic role is not changed: "This is one of erplora.com's roles. Duplicate it and change the copy.".
Nobody gives what they do not have, nor "With approval" what their own role refuses them: "A role may not allow more
than you may do yourself."; and owning the business is
given to nobody: "That is only the owner's of the business: no role gives it.". A permission that is not of an app that
is on, "That permission is not of any app that is on in this business."; "With approval" for something a manager cannot
approve with their PIN, "That cannot be approved with a PIN: choose allowed or no.". The name, as when making it. What
the screen refuses is said next to "Save", with "The role could not be saved", or under the name, and what was being
changed stays. Whoever does not manage the roles sees it read only.
Involved: BASE-F13, BASE-F82, BASE-F84, BASE-F97, BASE-F98, BASE-F127, BASE-F131

### BASE-F129 Delete a role of your own
<!-- from WORKBOOK.md sha256:b4f8224d9655 -->
Status: done
Actor: owner, administrator
Screen: Employees · Roles; Assistant
Steps:
  1. In **Employees › Roles**, "Delete" in the "⋮" of a role of your own.
  2. "Delete the role Cashier? This cannot be undone.": once confirmed, "Role Cashier deleted", and it leaves the list.
  3. It is also asked of the assistant: "delete the Cashier role". The card says the role and, under "What will happen",
     how many people have it, and asks to type CONFIRM.
  4. Whoever left the business with that role, if they come back, enters with the one of their invitation.
In: the role.
Out: the role deleted. Event `base.role.deleted`.
If it fails: if somebody of the business has it, it is not deleted: "2 people have this role. Give them another before
deleting it.", in the question itself, which stays open. A basic role has no "Delete"; the assistant and the API are
answered "This is one of erplora.com's roles. Duplicate it and change the copy.".
Involved: BASE-F82, BASE-F97, BASE-F98, BASE-F127, BASE-F130

### BASE-F130 Give a person a role of your own
<!-- from WORKBOOK.md sha256:16b78f396cff -->
Status: partial — it is given by asking the assistant or through the Hub's API; its place in the person's page is missing
Actor: owner, administrator
Screen: Assistant
Steps:
  1. Ask the assistant "give Luis the Cashier role" or "take the Cashier role away from Luis".
  2. The card says the person and the role by their names and, under "What will happen", how many people have that role.
     It asks to type CONFIRM (BASE-F98).
  3. Once accepted, the person has that role, which rules over the one of their invitation: what they see and what they
     may do change at once on their devices, without ending their session (BASE-F13), and whoever may now do something
     with that role approves it with their PIN too (BASE-F84). Each person has a single role.
  4. To return them to the one of their invitation, ask for that role ("Employee"): it is the one they have from then on.
  5. That person's assistant knows the role it talks to: the role of your own, by the name the business gave it
     (BASE-F100).
In: the person and the role, one of the business's own or the one of their invitation.
Out: the person with that role. Event `base.role.assigned`. erplora.com does not know: there they keep the one of their
invitation.
If it fails: nobody gives the owner another role, "The owner is always the owner: nobody gives them another role.";
nobody changes their own, "Nobody changes their own role: ask somebody above you."; nor the one of somebody who is not
below them by their invitation, "You may only give a role to people below you in the business.". Nobody gives a role that
allows more than they may do themselves, the one of the invitation when returning a person to it, what an app that is
off would give and, "With approval", what their own role refuses them included: "A role may not allow more than you may
do yourself.". Another basic role, "That role is given
on erplora.com. Here you give one of the business's own."; a role that is not there, "This role does not exist in this
business."; a person who is not of the business, "That person is not in this business.". If somebody deletes the role at
the same time, it is either deleted or given, never both: one hears "This role does not exist in this business." or "2
people have this role. Give them another before deleting it.".
Involved: BASE-F13, BASE-F82, BASE-F84, BASE-F97, BASE-F98, BASE-F100, BASE-F127, BASE-F129

### BASE-F131 See in the bell the roles to review
<!-- from WORKBOOK.md sha256:a1822b65cbe1 -->
Status: done
Actor: owner, administrator
Screen: The bell; Employees · Roles; Employees · Roles · What it allows
Steps:
  1. An app is turned on, or an app gains a permission, after a role of your own was saved: that role is left to review.
  2. The bell of whoever manages the roles goes up without reloading with the notice "2 roles to review" and its
     sentence: "An app turned on or a new permission is not in them yet: look at what each role allows.".
  3. "Review the roles" opens **Employees › Roles**, where that role carries "To review".
  4. Opened, "New permissions to review" and each one marked "To review". They choose what the role does with each one
     and press "Save", even if nothing changes.
  5. Once saved it no longer carries the mark nor counts; with none left, the notice goes away.
In: the business's own roles and the apps that are on.
Out: nothing is saved.
If it fails: whoever does not manage the roles does not see the notice. If the notices cannot be read, the bell keeps
the last it knew, as with the other notices.
Involved: BASE-F10, BASE-F82, BASE-F128

### BASE-F84 Approve with a manager's PIN
<!-- from WORKBOOK.md sha256:e79b94167921 -->
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
  5. Whoever has one of your own roles (BASE-F130) is asked as that role says of that action: "Allowed", they do it
     without a question; "With approval", the question shows; "No", there is no question: it is refused and no PIN lets
     it through, nor an approval they had already been given. If the role changes, it counts from the next action on,
     without closing the session (BASE-F13). An app turned on after the role was saved asks as the basic role it came
     from; a permission an app added later is "No" until it is reviewed (BASE-F131). The owner is never asked.
  6. Whoever may do it by their role does not see the question: they do it and it is recorded as done by them, with
     nobody's approval (BASE-F85).
  From the assistant too: the "yes" of its card opens the same dialog, with the figures of what it was asked.
In: the name and the PIN, or the badge, of whoever approves.
Out: an approval valid for that action, of that person, once and for two minutes; it is recorded in
**Employees › Approvals** (BASE-F85). Events `base.approval.granted` and `base.approval.used`; that of an action done by
whoever may do it, `base.approval.noted`. The approval is spent together with the action: if the action fails for a reason of the business, the approval stays unused and the same action, repeated
within those two minutes, goes through with it; if it went through, it is not repeated; two at once with the same one,
only one goes through. What the approved action does on the way in other apps (the rectifying invoice of a void, the
voucher sessions it gives back) goes with the approval, as when the manager does it themselves; nothing more: not what
is only looked up, nor the next action. Whoever is not of the business gets the refusal of always, without the
approval's question.
If it fails: the dialog stays open with "Those details do not approve this. Check the name and the PIN, and try
again.", "That person cannot approve this: ask somebody who may do it themselves." (nor whoever does it "With
approval"), "This no longer needs an approval: do it again.", "This is not approved with a PIN." (also if meanwhile the
role of whoever asks became "No"), the wait after too many attempts or "Could not send the approval. Check the
connection and try again.". With nobody with a PIN who may: "Nobody here can approve this
with a PIN. Somebody who may do it can swipe their badge.". "Cancel" hands the app back its refusal.
Involved: BASE-F85, BASE-F55, BASE-F56, BASE-F100, BASE-F128, BASE-F130, SALE-F30, SALE-F31

### BASE-F85 Look up who approved what
<!-- from WORKBOOK.md sha256:2122ee4e3222 -->
Status: done
Actor: owner, administrator
Screen: Employees · Approvals
Steps:
  1. In **Employees › Approvals** (the tab exists only for whoever runs the business): "Each action that can need a
     manager's approval: who did it, who approved it and with what. Nobody, not even an administrator, can edit or
     delete it.".
  2. A row per action, the latest first: "When", "Action" (in words and in their language; with the figures of what was
     done, when the app gives them: an approval nobody used did nothing and has no figures), "Approved by", "Who" (who
     did it, or asked to), "With" ("PIN", "Badge" or "Their role") and "State" ("Done", or "Not done" if the approval
     was not used).
  3. Those done by somebody whose role allows it, by themselves, show too: the manager who voids a sale or gives a
     discount above the maximum, the owner, whoever has it "Allowed" in a role of the business's own, and the same
     asked of the assistant, with whoever said yes. They say "Their role" in "With" and leave "Approved by"
     empty. A row per action: one that was refused or failed does not show, nor the retry of one already done, nor one
     that changed nothing, nor what the system or an automation does.
  4. They search with "Search by person or action…" (by its figures too) and, in "Filters" (the funnel), filter by
     "When" (a day or a few days in a row), "Action" (the ones on the record, each once and without figures), "With"
     and "State".
  5. "Export CSV" downloads a file with the actions the search and the filters keep, also the older ones the list no
     longer shows (the last 500), with the same columns in their language; meanwhile it says "Exporting…".
In: the record of approvals.
Out: nothing; it is read only (the exported file changes nothing). It updates by itself with each approval and each
action.
If it fails: "Could not load the record of approvals." with "Retry"; with none, "There is no action of this kind in this
business yet." (and the exported file brings its header alone). If it cannot export, a notice says so with its reason
and nothing is downloaded.
Involved: BASE-F84, BASE-F100, BASE-F128, SALE-F30, SALE-F31, BASE-F112 (inside the app)

### BASE-F86 Create an API key and copy its token
<!-- from WORKBOOK.md sha256:13209079c453 -->
Status: done
Actor: owner, administrator
Screen: Employees · API keys
Steps:
  1. In **Employees › API keys**: "A key lets another system (your accountant's, your online shop) read or write
     this business's data through its API." and "New API key".
  2. In "New API key", the "Name" ("Accountant — invoices"), the "Requests per minute" ("From 1 to 10,000.") and
     "What this key may do": "Choose apps" or "All apps", with the boxes "Read", "Create", "Update" and "Delete" of
     each app or, on "All apps", only once for all of them ("Every app of your business, also the ones you add
     later."). Only the box of what whoever makes it may give shows: the rest has a dash, and the app they may give
     nothing on does not show, nor "All apps" if they may give nothing on all of them. "Create key" takes what is
     ticked on the chosen option.
  3. They tap "Create key": "API key created" shows with "Copy the token now", "This is the only time the whole
     secret is shown. Keep it somewhere safe: it will not be shown again." and "Copy" (for two seconds it says
     "Copied"). "Done" closes it.
  4. What a key may do is four actions, on every app (also the ones added later) or app by app: read, create,
     update and delete, each on its own. A key with "Read" on Inventory reads its products; creating, updating or
     deleting one, or opening another app, is refused.
  5. A key is never given more than whoever makes it may do: on an app, an action they may do in none of its calls;
     on every app, an action they may not do on some app that publishes it.
In: the name, the pace and what it may do.
Out: the key, of which the business keeps only what lets it be recognised, and who made it, which sets its ceiling
(BASE-F125). Event `base.api_key.created`.
If it fails: with no name or no box ticked, "Create key" cannot be tapped; with no app to give anything on, "There is
no app you may give access to.". "The API key could not be created.", "Choose at least one app and what the key may do
on it.", "That app does not publish what the key would do on it.", "A key may not do more than you may do yourself."
or "It could not be copied to the clipboard.".
Involved: BASE-F89, BASE-F90, BASE-F119, BASE-F125

### BASE-F87 Rotate an API key
<!-- from WORKBOOK.md sha256:0d53f808c07f -->
Status: done
Actor: owner, administrator
Screen: Employees · API keys
Steps:
  1. On the key's row, "Rotate".
  2. "Rotate the API key" with "“Online shop” gets a new token. The current one stops working at once."; they confirm
     with "Rotate".
  3. The new token shows, only once, with "Copy".
In: the key.
Out: the key with a new token; the previous one stops opening anything at once. Event `base.api_key.rotated`.
If it fails: "The API key could not be rotated.", "That key was revoked: it never works again." or "That key no
longer exists. Refresh the list and try again.".
Involved: BASE-F86, BASE-F89

### BASE-F88 Revoke an API key
<!-- from WORKBOOK.md sha256:458a37f36d18 -->
Status: done
Actor: owner, administrator
Screen: Employees · API keys
Steps:
  1. On the key's row, "Revoke".
  2. "Revoke the API key" with "You are about to revoke “Online shop”. Any system using this token loses access at
     once. This cannot be undone."; they confirm with "Revoke".
  3. "“Online shop” revoked." shows and the row stays as "Revoked", without "Rotate" or "Revoke".
In: the key.
Out: the key revoked for good; it is kept on the list. Event `base.api_key.revoked`.
If it fails: "The API key could not be revoked.".
Involved: BASE-F89

### BASE-F89 See the API keys and what each one may do
<!-- from WORKBOOK.md sha256:d4d99d2ecb4a -->
Status: done
Actor: owner, administrator
Screen: Employees · API keys
Steps:
  1. In **Employees › API keys** (the tab exists only for whoever runs the business), a row per key: "Name",
     "Token" (only its start), "Permissions", "State" ("Active" or "Revoked"), "Created by", "Created", "Last use"
     ("Never" if unused) and "Limit". "Permissions" says "Full access", "Read only" or "Write only" if the key is so
     on every app; if not, its actions on "All apps" and app by app, by their initial: R (read), C (create), U
     (update) and D (delete), as "Online shop R/C · Taxes R". "Created by" says the name of whoever made it, never
     their email address.
  2. They search with "Search API key…". At the bottom, a link leads to the API documentation.
In: the business's keys.
Out: nothing saved. It updates by itself when one is created, rotated or revoked.
If it fails: "Your API keys could not be loaded." with "Retry"; with none, "No API keys yet. Create one so that
another system can read or write your business's data.".
Involved: BASE-F86, BASE-F87, BASE-F88, BASE-F125

### BASE-F90 Read the API documentation
<!-- from WORKBOOK.md sha256:06bbdedbe93f -->
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
nothing published, "None of this business’s apps publishes its API yet.".
Involved: BASE-F91, BASE-F86, BASE-F112 (inside the app)

### BASE-F91 Show or hide the API documentation
<!-- from WORKBOOK.md sha256:9c9353b5fec2 -->
Status: done
Actor: owner, administrator
Screen: Settings · General
Steps:
  1. In **Settings › General**, on the card of the API documentation, the switch "Show the API documentation" ("Adds a
     page with the documentation of the API, for whoever connects another system."). It comes off.
  2. Turning it on saves it at once and "Open the API documentation" shows and, in the side menu, "API" (between
     "System" and "Settings"), without reloading; turning it off, both go away.
In: the switch.
Out: the business's setting. Event `base.api_doc.settings_changed`.
If it fails: "Could not save the change." and the switch goes back to what was saved; "Could not load the
setting." with "Retry". Whoever does not run the business sees it off: "Only who runs the business can change
it.".
Involved: BASE-F90

### BASE-F92 Open and close the assistant's panel
<!-- from WORKBOOK.md sha256:0063a7a68d0c -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Assistant
Steps:
  1. With the session open, they tap the "Assistant" sparkles in the top bar, next to the bell. Tapping them again
     closes it. On a phone, the sparkles and "My apps" go in "⋮" ("More actions"), so the title reads whole, and the
     bell and the help's "?" stay in sight: there, "Assistant" opens the panel as soon as the menu has finished
     closing, so what they type straight away goes to the chat's box and Enter sends it.
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
<!-- from WORKBOOK.md sha256:c35b194fa2da -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Assistant
Steps:
  1. With the conversation empty, the panel shows the sparkles, "Ask me about your sales, your stock or anything
     about your business." and the setup's shortcuts (BASE-F103).
  2. They write in "Write a message…" and press Enter or "Send". With a keyboard, Shift+Enter starts a new line; on a
     touch screen, Enter starts a new line and "Send" sends. "Send" is off with the box empty and no attachments.
  3. Their message shows on the right just as they wrote it. Below, the assistant's bubble, with three dots that move
     until the first text arrives. In Spanish, the assistant addresses them with «tú» or «usted» as they write to it
     (when it does not show, «tú», as the screens do) and keeps it to the end of the answer, never mixing the two.
     Everything it writes is in the person's language, also what it says while it looks things up or before it shows
     a card: not a sentence in English nor words of another alphabet; records' names, as they are written.
  4. While it answers, "Send" becomes "Stop", "Attach a file" and "Dictate by voice" turn off and the answer keeps
     appearing; the conversation scrolls down by itself. They can already write the next question, but it is not
     sent until this one ends.
  5. If they ask how something is done in ERPlora, what an option means or what a plan includes ("How do I open the
     cash register?"), the assistant searches ERPlora's documentation (the help, each app's and the plans) and answers
     only with what it says, and ends the answer with a "Source: …" line naming the section it comes from (its
     headings or, when it has none, its path), so the person can check it and read more; if the documentation does not
     cover it, it says so instead of making it up.
  6. If the assistant ends without saying anything, the bubble reads "(no answer)".
  7. "Stop" cuts what was left: what was already written stays, with "Stopped." below.
  8. Under each finished answer, "Read aloud" reads it with the device's voice, if it has one, and "Stop reading"
     stops it. If ERPlora has its own voices turned on (not today), the panel's header lets the person choose between
     the two for the screen's language (the first one, until another is chosen; the device remembers the choice) and
     the "Device voice".
  9. If they ask for something done with the business's data ("raise the drinks by 5 %", "add the tonic water at
     €2.50"), the assistant does it with the same actions that person has on the screens of their apps, and what
     changes something with the confirmation of BASE-F97. If the one it needs is not among those it has at hand for
     that message, it searches all of that person's for it and uses it in the next step; only when there is none does
     it say on which screen it is done. If what was asked is done by an app the business does not have on, it says
     which app it is and offers to turn it on (BASE-F24).
  10. The assistant knows from the start where the business is and what time it is there: its country, its time zone
     with the date and time at that moment, the business's language and the one the person chose in "My profile", its
     sector, the apps it has on, to whoever runs it its plan and how many apps it counts (only those the business
     chose, as Apps says) and, to whoever may see them, the settings of Sales & POS, Cash register and Reservations
     when they are on (how it charges, how the drawer opens and closes, whether each reservation needs a phone); it
     does not have to look them up for each question. Every date and time it says is in the business's time, the one the
     screens show, never in UTC: in a bar in Madrid, what happened at 16:18 it tells at 16:18, not at 15:18. Every
     amount it says is in the currency and with the decimals the screens show: what a customer's card says is «€3.60»
     it tells as €3.60, never as €360.00.
In: what the person writes; the whole conversation travels with each question (BASE-F102).
Out: the question to erplora.com, which answers it and counts it in the month's messages (BASE-F104).
If it fails: without a connection, with the service down, without a plan or without messages: BASE-F106 and BASE-F104.
If the documentation cannot be searched at that moment, the assistant says so and does not answer from memory. "Stop"
does not undo an action that had already been done. If ERPlora's voice cannot read the answer at that moment, the
device's voice reads it; if there is none either, below the answer it says "The answer could not be read aloud. Try
again.".
Involved: BASE-F24, BASE-F102, BASE-F104, BASE-F106

### BASE-F94 Attach a file or dictate by voice
<!-- from WORKBOOK.md sha256:e4f9686d9ed8 -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Assistant
Steps:
  1. To attach, they tap "Attach a file" and choose one or several: images, PDF, Word, Excel, text or CSV, or the
     copy of a business (a .blueprint.zip, the same one Settings · Data and backups › Import takes, BASE-F30). Each
     one shows over the box with its name and its "Remove attachment" ×.
  2. They go with the next message, with or without text, and stay in the person's bubble by their name. They travel
     with the conversation while the page stays open; once it is reloaded, the conversation only remembers what they
     were called.
  3. The assistant does not read the copy of a business: if the person asks it to load it, the assistant loads it
     with its card, as Import does (BASE-F31, BASE-F97). Any attachment, a photo or a PDF too, it keeps in Files when
     asked: it uploads it to the folder with its card, which says it by its name, and the very same file is in the
     folder, as with "Upload file" (BASE-F73). If the page was reloaded before saying "yes", it loads and keeps
     nothing and asks for it to be attached again.
  4. To dictate, they tap "Dictate by voice" (it only shows if the device can record). The browser (in the installed
     app, the device) asks for permission to use the microphone; while it asks, another tap does not open a second
     recording. While it records, the button turns red and is called "Stop recording"; after two minutes it stops by
     itself.
  5. On stopping, "Transcribing…" shows and the text lands in the box, after whatever was written. **It is not sent by
     itself**: the person reviews it and taps "Send", and what they ask goes through its card like any other request
     (BASE-F97).
In: the files (8 MB each; the copy of a business, 20 MB as in Import; and 20 MB among all those of a question) or the
recording.
Out: the file travels with the question to erplora.com, which reads it; the copy of a business stays in the
business: erplora.com only gets its name. What is loaded or kept in Files is the file the person attached, as it
is. The recording goes through the business to erplora.com's transcription.
The browser never talks to erplora.com directly.
If it fails: in one line over the box, and the file is not attached: "menu.pdf is too large: 8 MB at most per file.",
"The file could not be read: the file is larger than 20 MB." (the copy of a business, as in Import), "The files of
one question add up to 20 MB at most.", "menu.rar cannot be attached: images, PDF, Word, Excel, text or CSV." or
"menu.pdf could not be read.". A file no longer in the conversation is neither loaded nor kept: "There is no file
«copia.blueprint.zip» attached to this conversation: attach it again.". With the microphone blocked, "Microphone access is blocked. Allow it in
your browser to dictate." and, in the installed app (Android or Windows), where there is no browser, "Microphone
access is blocked. Allow it in your device settings to dictate."; a recording too long, "The recording is too long:
dictate a shorter message."; no voice, "Nothing was heard. Try again closer to the microphone."; and if it cannot be
transcribed, "The audio could not be transcribed. Try again.".
Involved: BASE-F73, BASE-F93, BASE-F97

### BASE-F95 Read the answer: text, lists, tables and links
<!-- from WORKBOOK.md sha256:a3d37589da50 -->
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
<!-- from WORKBOOK.md sha256:dad0c85c76a7 -->
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
<!-- from WORKBOOK.md sha256:d2fdb23a0674 -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Assistant confirmation card
Steps:
  1. The person asks it for something that changes data ("create the service Haircut at €15 for 30 minutes"). What
     the action needs and the person has not said, the assistant looks up with its tools; if none gives it, it asks
     for it in one short question and never makes it up ("Which tax do you sell it with?"), and if the request fits
     several records, it asks which one. It never asks in its text whether to go ahead: the card asks that.
  2. Before doing it, "Run this action?" shows over everything, with the action, the app and its first data in one line,
     for example "Create in Services: Haircut · Price: €15.00 · Duration (minutes): 30". The first, what the action
     touches (its record or its name), shows by its value alone when it reads on its own (a name, a record, a date or
     records by their names); each datum after it, and a figure, an amount, a yes or a no or a value of a closed list in
     first place, carries the name of its datum in front, the same as on its screen, because alone it does not say what
     it is: "Change in Services: Highlights · Minimum price: €65.00", never "Highlights · €65.00", which reads the same
     as its price; "Change in My profile: Interface scale: 110%" and "Change in Time clock: Allowed radius (m): 50 m",
     never a bare "110%" or "50 m", which do not say what changes; "Create in Sales & POS: Misc · Tax category: Product — generic · 21% · Position: 0"; "Open in Tables: Table: 4 ·
     Guests: 3". An amount, every datum its app declares as money, shows
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
     no sign when it balances); a yes or a no, as "Yes" or "No", with the name of its datum in front, also on a normal action's line,
     because alone it says nothing of what changes ("Require an opening float: Yes · Require a count to close: Yes",
     never "Yes · Yes"); a list that its app (the server) names, by its items
     one after another ("Printers: Till, Kitchen"; past four, the first three and how many more: "Till, Kitchen, Bar and
     2 more"; when an item carries a comma, such as a date, separated by semicolons: "Nov 2, 2026, 10:00 AM; Nov 9,
     2026, 10:00 AM"); the permissions granted to an automation, by each action as its History names it ("Permissions:
     Create a task, Create a customer"); a template of the catalogue, by its name and its language, as in Import
     ("Template: Restaurant (English)"), never by its code, and the apps it loads, by their name ("Apps to load: Sales &
     POS, Invoicing"), also when none is chosen and it loads all of its own ("Time clock, Cash register, Menus and
     combos and 17 more"); the rows of a file being imported (products, categories or customers), by the name of each,
     as the import keeps it ("File rows: Spoons, Stews"; a row without a name counts among the "more", never by
     another of its cells) and, in Inventory, the tax categories they take, once each, by their name and today's rate ("Tax
     category: Restaurant — food · 10%"); a list of lines that carry only their record, such as the services of an appointment, the same
     way, by the name of each ("Services: Haircut, Colour"; one that cannot be named counts among the "more"), also
     when the assistant sends a service by its name because it does not know which one it is ("Services: Colour"; when
     it sends the service and a name as well, it says the service that is booked); a list of what the person wrote,
     such as the options of a select field, by each one as written ("Options: Terrace, Inside"); a list of lines that
     carry in words their record, the name the person said, what they wrote or a time or a date and, beside it, only
     figures — a goods receipt (product and quantity), the services of a voucher (service and sessions), the dishes of
     a ticket made by hand, the intervals of a day's hours or the lines of an invoice made by hand —, by its words
     followed by its figures, the quantity as it is written in the person's language, an amount as money and a VAT
     rate typed by hand as a percentage ("Products: Red wine · 6, Beer · 2.5"; "Services included: Haircut · 5,
     Colour · 3"; "Dishes: Espresso · 2, Latte · 1"; "Opening intervals: 9:00 AM · 2:00 PM"; "Lines: Private birthday
     menus · 10% · 1 · €681.82"; when a line cannot be named, the list says how many it carries: it would read as a
     bare figure); the custom fields of a customer's card, each by its name and its value as the card shows it: a yes
     or no in the person's language, a date as it is written in it and a field that is cleared, with a dash ("Custom
     fields: Table preference · Terrace, VIP · Yes"; "VIP · —"); the special days loaded at once, by their date and
     their name and, when that day opens, its hours ("Jan 1, 2027 · New Year's Day; Jan 6, 2027 · Epiphany; Mar 26,
     2027 · Good Friday and 7 more"); a line with two records the card names, by both (the product and who serves it in
     a sale, "Shampoo · Bea Ruiz · 2"); and any other, such as a line with a record the card cannot name, one with a
     yes or no or a list inside or a list of codes, by how many items it carries; a charge, by its total and how it is paid, as the button of the
     **Charge** sheet: the total, as the POS works it out for whoever asks ("Total: €12.50"), and each payment method
     with what it pays ("Payments: Cash · €12.50"; the one without an amount pays what the others leave and, when none
     is said, all of it in cash, as the action charges), never "1 item" nor the check's version, which only the
     **Charge** sheet uses; payments that do not add up to the total show as they were said, beside the total, and
     when the total cannot be worked out (the check is no longer there or whoever asks cannot see it) it is not made
     up: in both cases the action refuses it when it runs; and a datum that groups others, such as a WhatsApp template, by its values, without the name of each one ("Template:
     cita_recordatorio · es · Ana, 10:00"; of a till count, the notes and coins counted remain: "50: 2"). A date and a
     time show as they are written in the person's language and at the business's hour ("Nov 2, 2026, 10:00 AM"; a day
     alone, "Nov 2, 2026"; a time alone, "9:30 PM"); a value of a closed list, with the name its app gives it ("Front
     desk", not the internal value), also that of a datum its app does not call like the field that names it
     ("Rectifying invoice: other causes (R4)", not "R4"); and a record, by its name when its app lets whoever asks read it ("Person: Eva
     Gil"): otherwise the card leaves it out, never by its code. A tax category also carries the rate it charges today
     in the business's country and region, as the **Sections** screen does ("Tax category: Product — generic · 21%");
     without a rule in force, its name alone, and its name alone too in a rule of Taxes, which carries its own country
     and its own rate. Adding a product says it on its line, after the name and the price ("Create in Inventory: Spoon ·
     Price: €2.50 · Tax category: Product — generic · 21%"). A record said in words is looked up as the action will
     look it up, also inside another (a course inside its menu), and the one it finds comes up ("Course: Homemade
     desserts" when "desserts" was said); if those words fit several or none, they come up as they were said; and if the action does
     not use them because its record's identifier comes, they are neither read nor shown. Nor does
     it put the key its app uses to avoid doing
     the same thing twice on a retry (charging, sending a WhatsApp, printing): nobody can judge it, and the action
     receives it all the same when it runs. Everything shows in the person's language, also the
     name of each datum when the card puts it on its own line (BASE-F98): the
     same one its app calls it by, never a technical name. An action of the platform itself is named by the screen where
     it is done, for example "Change in Settings" or "Delete in Files". Each action shows with its own verb, never a
     generic one: rectifying an invoice says "Rectify in Invoicing". Two actions with the same name in two apps each
     say what they do: emptying a cart says "Clear in Cart & Checkout", removing one of its lines "Remove in Cart &
     Checkout" and taking a product's route away in the kitchen "Clear in Kitchen"; a cash count says "Register count
     in Cash register" and cash brought in or taken out "Register movement in Cash register", as their screens do,
     never "Add"; and VeriFactu's live test, as its buttons do, "Test the connection in VeriFactu" and "Create test
     invoice in VeriFactu", never "Run" or "Create". An action that carries no datum to show says only its action and
     its app, ending in a full stop and with no empty colon after it: "Test the connection in VeriFactu.".
  3. "Run it" does it with the session of whoever asked, with the same permissions and the same checks as the button
     on its screen. "Cancel" or Esc do nothing: the assistant knows the person said no and says it was not done
     because they cancelled it, without asking them to confirm it, since that card is already closed. After "Run it",
     the assistant knows the person confirmed it: it takes it as done just as asked, says what was done and does not
     offer to undo it unless asked to.
  4. What only reads (seeing the sales, looking up a customer) asks for no card; each action that changes something
     asks for its own.
  5. Under the answer stays the receipt of each action of the turn, with the action named as on its card: "Done:
     Create in Services", or "Not done, cancelled: …", "Not done, it failed: …" and "Not done, not allowed: …". The one
     of a failure says the reason in one sentence: if its app refuses it, the same one its screen would give ("Not
     done, it failed: Remove in Employees. That person is not in this business."); if what did not fit was the data
     the assistant sent, which, with the name the card gives them ("The assistant sent data that does not fit:
     Products."), and if it asked for a change without saying what to change, that ("The assistant did not say what
     to change."). If the person changes language, the earlier receipts show entirely in the new one, the app's name
     too; the reason, said in the other language, no longer shows.
In: the action, its data and its risk, as its app declares them; the business's currency, the one of the record it is
done on (read as the person) and, in "What will happen", the one its app gives; the business's time zone; and, if its
app declares it, the check it makes before the card, as the person: if it refuses the data (adding someone with a role
the business does not have, STAFF-F01), no card shows and the assistant tells it as its error.
Out: if accepted, the action done in its app, with the same event as if its button had been tapped.
If it fails: an action its app refuses goes back to the assistant as an error and it tells it; the receipt reads
"Not done, it failed: …". Data the action does not take (a country or a currency that does not exist, a value
outside its list) never reach the card: they go back to the assistant, which corrects them, and the person confirms
only once. Neither does a change that only names its record, with no data to change (never "Change in Customers:
Lucía QA" alone): the assistant hears there is nothing to change and goes on with what it was asked, with the action
that does it, or asks what to change; if the record is not there, it hears that. "Run it" holds only for what the card
shows: if it changes before it is tapped — the action finds another
record by its name, because someone created one that fits what was said better ("Mesa" when the card said "Mesa 4"),
the record is renamed, the rate of its tax category changes, or what "What will happen" says is no longer the same —, nothing is done and the new card
shows, to be confirmed again; if what it found is no longer there, no card shows and the assistant tells it as its
error. "Cancel" and a typed word that does not match count the same even if it changed. If the page is reloaded with
the card open nothing is done, and the answer ends in "The answer was cut off." with "Try again".
Involved: BASE-F98, BASE-F99, BASE-F101

### BASE-F98 Dangerous actions: type to confirm, or not from the chat
<!-- from WORKBOOK.md sha256:e9288e7fa947 -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Assistant confirmation card
Steps:
  1. An action its app marks as dangerous is not confirmed with one click: the card says, for example, "Delete in
     Services. Check each detail before you continue.", puts each datum on its own line with its name in the person's
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
<!-- from WORKBOOK.md sha256:adbd1b0cc182 -->
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
     shows an identifier the assistant did not really read. Do not trust it.". The same with a web address: the
     assistant only gives the ones it looked up in the turn (a web search, an exchange rate or what a tool returned),
     and if it writes another one the person did not write: "This answer shows a web address the assistant did not
     really look up. Do not trust it.". The same page written another way (with or without "https://", "www." or the
     closing slash) counts as looked up.
  4. If it points to a screen this business does not have: "This answer points to a screen that does not exist
     here.", and without "Go to …" (BASE-F96).
  5. The notices carry their alert icon, are not written by the assistant and stay with the message, also on
     reloading. A clean answer carries none.
  6. The receipts of BASE-F97 say what was really done, action by action.
In: what was done in the turn, with its result, what its lookups returned and the web addresses erplora.com's tools
looked up.
Out: the notices and the receipts, kept with the conversation.
If it fails: "Done" means the action of its app ended without an error: if an app answers fine without having changed
anything, it is that action that has to say so. If the turn ends in an error, the bubble carries its failure
(BASE-F106), the notices of what it got to say and the receipts of what was indeed done.
Involved: BASE-F96, BASE-F97, BASE-F106

### BASE-F100 What the assistant can do depending on who asks: permissions and a manager's PIN
<!-- from WORKBOOK.md sha256:6782ed15c886 -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Assistant
Steps:
  1. The assistant works with the session of whoever is in front of it: it sees and does what that person would see
     and do with their buttons, in the business's apps that are on, and nothing else. An action they have no
     permission for is not offered to the assistant, which tells them so; one its app lets a manager approve is, as
     its button on the screen is, unless the person's role of your own says "No" to it (BASE-F84): that one is neither
     offered nor found, and no PIN lets it through. The assistant knows the role it talks to (owner, administrator, manager or
     employee, said in the language of the conversation, or the role of your own the person was given, by its name,
     BASE-F130) and that its tools are that role's: asked for something none
     of them does, it neither looks for another way nor tells the state of something else, but says in one sentence
     that it is not available to them here, because their role cannot do it or because that app is not on, and who
     can (to an employee, a manager or the owner; to a manager, the owner or an administrator) or on which screen it
     is done.
  2. That action comes with its card, like any other, and the assistant says beforehand that the card will ask a
     manager to approve it. Tapping "Run it" opens "An approval is needed", the same as on the screen: a manager taps
     their face and types their PIN, or swipes their badge, and the action is done once, with whoever asked for it as
     its author. It is recorded in **Employees › Approvals**.
  3. If nobody approves it ("Cancel"), it is not done: the receipt reads "Not done, cancelled: …" and the assistant
     knows it.
  4. If it tries anyway an action without permission that nobody can approve, it is not done: the receipt reads "Not
     done, not allowed: …" and the assistant explains it cannot.
  5. What the assistant tells (lists, figures) is what that person may read.
In: the session of whoever asks, which signs each action; for what a manager approves, their PIN or their badge.
Out: the action done with that person as its author. The approval is good for that action of that conversation, once
and for two minutes, and it is spent together with the action (BASE-F84). One a manager could approve and the person may
do by their role is recorded too, in their name (BASE-F85).
If it fails: if the permission is lost between offering the action and doing it, its app refuses it and the receipt
says so. An approval already used or expired does not let the action through: the receipt reads "Not done, it
failed: …" and the assistant tells it.
Involved: BASE-F13, BASE-F84, BASE-F85, BASE-F97, BASE-F130

### BASE-F101 Ask it for several things in a row
<!-- from WORKBOOK.md sha256:b63066914a0f -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Assistant
Steps:
  1. The person asks for a chain ("create the category Drinks and the product Draught beer at €2.50").
  2. The assistant solves it in rounds: it reads what it needs without asking (several things in the same round, if it
     needs them), asks for an action, it is done and it goes on. All it says goes to the same bubble, and what each
     round says in its own paragraph: never glued to the previous one.
  3. Each action that changes something asks for its own card (BASE-F97), one after the other, also those it asks for
     in the same round: accepting or cancelling the first does not answer for the next ones. If more wait behind it,
     the card carries "Cancel all", which cancels this one and those left.
  4. If they cancel one, the assistant knows and decides how to go on. What was already done stays done.
  5. A request allows twenty rounds at most, each with all the assistant asks for at once: it is a brake against
     loops, not an allowance, and a read and a change for each day of the week fit easily even if it asks for them one
     by one. On the twentieth the assistant can do nothing more
     and answers with what it has done and what is left, to ask for it in another message; if it still asks for an
     action, it is not done and its card does not appear, and it is told to answer. If it keeps trying, "I stopped:
     this needed too many steps. Ask for it in parts.".
In: the request; the result of each action, which goes back to the assistant.
Out: as many actions as cards accepted, each in its app and with its receipt.
If it fails: if an action fails half way, the assistant gets it and tells it; the earlier ones are not undone. With
the network cut half way, BASE-F106.
Involved: BASE-F97, BASE-F106

### BASE-F102 The conversation: what is kept, where and when it is deleted
<!-- from WORKBOOK.md sha256:173ed0b9e97e -->
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
<!-- from WORKBOOK.md sha256:6bedff7bf9d6 -->
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
<!-- from WORKBOOK.md sha256:32b0692c70b1 -->
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
  5. The owner sees, in the browser, "Upgrade plan", which opens the plan's page on erplora.com in another tab,
     already signed in with their account (BASE-F11); in the app installed from the store it does not show. Whoever is
     not the owner sees "Ask the business's owner to upgrade the plan.". There are no message packs: it is extended by
     upgrading the plan.
  6. With a plan without the assistant, the foot says "Your plan does not include the assistant.", with "Upgrade
     plan" for the owner; the panel opens anyway.
  7. Asked how many messages are left or how many have been used this month ("how many messages do I have left this
     month?"), the assistant answers with the same figures as "Usage and plan" (BASE-F40) and the day they renew. It
     reads them only when asked; if they cannot be read, it says so, without making up a number.
In: the messages used, the limit and the day they renew, from erplora.com.
Out: erplora.com's plan page, in another tab. The business does not keep its own count of messages.
If it fails: if the plan cannot be read, nothing is shown and they can ask anyway: what erplora.com says when
answering is what counts. If the pass of "Upgrade plan" does not arrive, the usual address opens, which asks to sign in (BASE-F11).
Involved: BASE-F11, BASE-F40, BASE-F106

### BASE-F105 Report a bad answer
<!-- from WORKBOOK.md sha256:273686eb94da -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Assistant
Steps:
  1. Under each finished answer shows "Report a problem"; not on the one still being written nor under a failure
     without an answer, which is not the assistant's.
  2. "Report this answer" opens: "If this answer of the assistant looks wrong or harmful, send it to us and we will
     review it.", with "What is wrong with it?" ("It is wrong", already ticked; "It is harmful or offensive", "It did
     not do what I asked" or "Something else") and "Comment (optional)".
  3. "Report" sends it with the question that led to it and with whether its turn brought pages of the web: the Hub
     says so when it closes each round of the turn (also the one that stops at the card of a change or after too many
     steps, which brings none), and the chat keeps it with the answer; one round that brought them is enough. "Cancel"
     sends nothing.
  4. "Thank you, we have received your report." shows and it closes.
In: the answer, the question, the reason, the comment and whether its turn brought pages of the web (when the chat
does not know, an answer from before the mark or a round stopped while writing, it does not say).
Out: the report, for erplora.com's team to review. Anyone can report. With the web search turned on, if the answer
brought pages of the web or the chat does not know where it came from, the team gets everything but the answer: the
search engine's terms do not allow keeping its results.
If it fails: "The report could not be sent. Try again.", and the window stays open with what was chosen and written.
Involved: ASSISTANT-F23

### BASE-F106 The assistant without a connection, with the service down or without a plan
<!-- from WORKBOOK.md sha256:b1eaa70683f3 -->
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
<!-- from WORKBOOK.md sha256:94bcd34257d5 -->
Status: done
Actor: ERPlora's QA team
Screen: every screen of the hub's platform
Operations: none
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
<!-- from WORKBOOK.md sha256:c25e6271691a -->
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

### BASE-F109 Delete a deleted business after its 90 days
<!-- from WORKBOOK.md sha256:d96eeeea1106 -->
Status: done
Actor: nobody: the Hub does it by itself, nobody presses anything
Screen: None; the business's address goes on saying "This hub is no longer available."
Steps:
  1. A business deleted on erplora.com (HUBS-F18, HUBS-F20) reaches its 90 days. Until then its database stays intact
     and it can be restored.
  2. The Hub checks whether it keeps documents: sales, invoices, VeriFactu records, payments, cash movements, shop
     orders or a customer's purchases, in any status and even with the app turned off. If it keeps any and they cannot
     be archived yet (there is no fiscal archive, or a VeriFactu record awaits the AEAT's answer), it stops: the
     business stays deleted, with its database, and is checked again the next day.
  3. It makes the final copy of its data, kept for 90 days in the copies store; if it already has one less than a day
     old (an earlier attempt that did not get to drop it), it makes no other. Meanwhile the business can still be
     restored and erplora.com still sees its copies.
  4. When it ends it checks again for documents, also those that came in during the copy, and if it keeps any it
     writes them to the fiscal archive, where they are kept for 6 years and nobody can delete them: each table of
     those documents as it is stored, with nothing rebuilt; the PDF of each invoice as it was handed to the customer,
     in its own language or the business's and with the VeriFactu QR if it has its record, one per
     invoice; and last a list that counts the rows and the PDFs and carries the fingerprint of each file, written only
     once every file has been read back the same. An archive made before the final copy does not count: it is made
     again after it.
  5. It drops that business's database, and only that one. From here it never comes back.
  6. It deletes its files from the store, those of Files and those its apps keep, and only its own.
  7. Only a mark stays, with no name or data, so its address goes on saying "This hub is no longer available."; its
     people and their sessions go with it.
In: the deleted business and its 90 days over. Never a demo, which is deleted its own way when it expires, the
platform's business or one moving to another server.
Out: the final copy and, with documents, its fiscal archive (on the row, `fiscal_archived_at`); and the database and
the files gone, with the event `base.hub.purged`; from there erplora.com no longer lists its copies. If its documents
cannot be archived, nothing is deleted: the database and the files are kept and the row says why,
`fiscal_archive_missing: <apps>` where there is no fiscal archive, `fiscal_archive_waiting: verifactu` while a record
awaits the AEAT and `fiscal_archive_failed` if the archive could not be written whole.
If it fails: a copy that fails drops nothing, and neither does having no copies store; a copy or a drop that fails is
tried again (1 min, 5 min, 15 min, then every hour) with the error noted on the row, with no second copy if there
already was one less than a day old. If the store does not delete its files, the business stays being dropped, with no
mark and `files_purge_failed` on the row, and it is tried again the same way. If an app cannot be read, the database
stays. A row that does not name the business's own database drops nothing (`invalid_database_name`). A business
restored during the copy stays open with its database; once it is being dropped, erplora.com gets `hub_purged`. If the
Hub shuts down mid-copy, the next one takes it up. If it shuts down mid-way through the fiscal archive, the next attempt
for that deletion uses the PDFs already uploaded and does not make them again. If the fiscal archive cannot be written
whole, or a file does not read back as it was written, it is not taken as done and nothing is deleted: the row says
`fiscal_archive_failed` with the reason and it is tried again the next day in another folder of the archive (what was
already up stays, since nobody can delete it, and without its final list it does not count), with a new final copy if
the one there is more than a day old.
Involved: HUBS-F18, HUBS-F19, HUBS-F20, PUBLIC-F34 (the same deletion of files, when a demo is retired), INVOICE-F18
(each invoice's A4 that goes to the archive)

### BASE-F110 Open the business's website on its own domain
<!-- from WORKBOOK.md sha256:6525baba0e5d -->
Status: done (the address and what it serves; connecting the domain is erplora.com's HUBS-F17, which shows it on the panel)
Actor: anyone, without an account
Screen: The business's public page (WEBSITE-F10), on its domain
Operations: none
Steps:
  1. Someone opens the business's domain (for example, www.minegocio.es) on a phone, a tablet or a computer.
  2. The business's published page shows, with its photos, in the browser's language.
  3. **Log in** leads to the business's address on erplora.com: the app and the way in stay only there.
In: a domain erplora.com has said is that business's.
Out: the business's public website and its images, without cookies; nothing else: no app, no API, no way in. With a session
of the business open in that browser it shows the same, because the session does not reach another domain. The page
tells search engines that its main address is the domain, also when it opens on its erplora.com address, which does not
redirect (WEBSITE-F10).
If it fails: a domain nobody connected opens nothing. If the business removes it, is cancelled or suspended, or has no
published page, the domain says there is nothing there. A business being prepared or moved asks to come back in a moment.
Involved: HUBS-F17, WEBSITE-F10

### BASE-F111 Wait for the database when it is cut for a moment
<!-- from WORKBOOK.md sha256:391a10311b47 -->
Status: done
Actor: anyone of the business in the Hub, on the web or in the app, and any program connected through the API
Screen: any of the Hub, Page «We will be back soon»
Operations: none
Steps:
  1. The person opens a screen or saves something while the database is cut for a few seconds: a restart, an AWS
     maintenance or the change of version.
  2. What they were reading waits and is asked for again by itself, up to 20 seconds in all. If the database comes back
     sooner, the screen arrives as always: the person only notices it took longer.
  3. What they were saving waits the same when it is known that nothing was applied: it never started (opening the
     business's database or checking who the person is), or it is a change that only touches the database and had not
     been confirmed yet. This covers Demo and the other apps' local commands. It is saved only once and in its business,
     and the notice to the other screens goes out after it is confirmed.
  4. While it waits it holds none of the transactions at once the business's plan gives: the rest of the business's
     people go on working.
  5. If the time runs out, whoever opens the business's address in the browser sees «We will be back soon» with
     «ERPlora will be back in a moment: try again in a few seconds.», on a page that refreshes by itself. Inside the app,
     what could not be loaded or saved says so in its place, as any other error.
In: nothing: the person does nothing different.
Out: the same answer as always, a few seconds late; or, past the time, a 503 answer with `Retry-After` and never a server
error. A program receives the code `database_unavailable`, or `base.hub_unavailable` if what does not answer is the
business's database while it is opened.
If it fails: what may have been applied is never repeated blindly, and each outcome says its own. An excluded command,
because it numbers, charges, generates a QR, submits to the AEAT, sends an email or a WhatsApp, calls a third party or
writes outside its transaction (cache, sessions, control or the file store), cut halfway or while being confirmed: the
person reads «The connection was lost while this was being saved. Check whether it was saved before trying again.» and a
program, the code `database_outcome_unknown`. If the save had already been confirmed and the cut only took its answer,
they read «It was saved, but the connection was lost before the answer arrived. Reload the page in a few seconds to see
it.» (`database_answer_lost`). What is no cut (a query that takes too long, a fault of the program) stays the error it
always was. erplora.com's calls to `/internal` and `/readyz` get their 503 at once, without waiting: erplora.com tries
again on its own, and `/readyz` has to say the database is gone before its probes give up.
Involved: ACCOUNTS-F50 (its twin on erplora.com), every app whose local changes repeat, the Hub's other waiting pages (a
business being prepared or moving to another server: the same look); hub#831, hub#1051 and hub#1052

### BASE-F112 Save a downloaded file inside the app
<!-- from WORKBOOK.md sha256:1042602d77fa -->
Status: done
Actor: anyone of the business who downloads a file in the Hub
Screen: those that download a file the screen already holds: VeriFactu › Configuration (the authorisation's form),
Settings · Data and backups (Export), Files, Employees · Approvals, the API documentation, Attendance, Inventory
(Products and Categories), Customers, the website's "Share and QR" and the assistant (the export it is asked for)
Steps:
  1. The person presses download: the authorisation's form, an export, a file, a CSV, the OpenAPI file or the QR.
  2. In a browser, the file goes with its name to the browser's downloads, which already say so.
  3. Inside the ERPlora app (computer, or Android 10 or later), the Hub hands the file to the app, which saves it in the
     Downloads folder, and "Saved to" appears with the file's path (on Android, "Saved to Download/menu.pdf"): inside
     the app there is no downloads bar nor any other notice.
  4. In the assistant, when asked for an export ("Give me the whole menu as a CSV"), "Download" with the file's name
     comes under its answer: the same file the export button of that screen gives, which comes down as in the two steps
     before. The assistant says it is there, without pasting its content into the chat.
In: the file the screen already holds, with its name.
Out: the file in Downloads and, inside the app, the notice with its path. Nothing is kept in the Hub.
If it fails: inside the app the button is never left without an answer. With no downloads folder the person can open
(Android 9 or earlier, iOS): "This app cannot save files on a phone or tablet. Open your business in a browser to
download it."; with the app linked to another business: "The file could not be saved: this app is linked to another
business."; a version of the app without this feature: "This version of the ERPlora app cannot save files. Update it to
download."; any other failure (a name the app refuses, no space left): "The file could not be downloaded.". In those
cases the screen does not say it was downloaded. The file the assistant gave lives in that tab: after the page reloads,
in its place it says "The file «menu.csv» is no longer here: ask for it again to download it.". The copies ERPlora keeps
(Data and backups › Copies) come down through a signed link and do not go through here.
Involved: HUB_APP-F30 (ERPlora/app), BASE-F35, BASE-F74, BASE-F85, BASE-F90, VERIFACTU-F05, ATTENDANCE-F10,
INVENTORY-F11, CUSTOMER-F09, WEBSITE-F09; hub#1041

### BASE-F113 Keep warning with the screen off (Android app)
<!-- from WORKBOOK.md sha256:5be0188aa434 -->
Status: done
Actor: system
Screen: none; on Android, the ongoing notification "ERPlora is listening"
Steps:
  1. In the ERPlora app, a person signs in to the business and hears some notice (a new kitchen ticket, an
     appointment the customer booked, a customer waiting for an answer on WhatsApp), and Android has not refused the
     notices.
  2. After the question about notices, when it is due (HUB_APP-F07), the Hub asks the app to stay listening, with the
     words of its ongoing notification in the person's language: "ERPlora is listening" and "You'll be warned when
     something needs your attention, even with the screen off.", in the channel "Notices with the screen off".
  3. With the screen off or the app in the background, the notices keep arriving at once (KITCHEN-F16,
     APPOINTMENT-F28).
  4. On signing out, also through inactivity (BASE-F61), or once nothing is left to warn about (the app that warned is
     turned off), the Hub asks the app to stop listening; on signing out, before leaving the page.
In: the notices the person hears and what Android says about the notices.
Out: the order to the app to stay listening or to stop. Nothing is kept in the Hub.
If it fails: with the notices refused ("Not now" to our question, or refused on Android), with nothing to warn about or
without knowing what Android says, the app is not kept awake. An app without this order (1.1.34 and 1.1.35) refuses it: the Hub
notes it in the console, does not ask again on that page and the person sees no error; the notices arrive with the app
on screen. If Android does not let it start, the same, and it is asked again at the next sign-in. While the
Hub does not know yet whether there is something to warn about, it asks the app nothing: reloading the page neither
stops it nor turns it on again. Signing out never waits for the app more than 2 seconds. In a browser there is no app
to ask.
Involved: HUB_APP-F26 (ERPlora/app), HUB_APP-F07 (ERPlora/app), KITCHEN-F16, APPOINTMENT-F28, BASE-F61; hub#836

### BASE-F114 Put a business back as it was at a past moment from the Hub admin
<!-- from WORKBOOK.md sha256:0b102c454f7a -->
Status: done (the action and the restore, in its place or to a separate copy, and getting back from the separate copy
the customers that were lost, the deleted ones as they were, the products, the services with their categories, the
appointments, the repeating appointments, the price list prices, the modifier groups the business deleted, with their
options, the options it took away from a modifier group it keeps, the modifier groups of the categories and of the
products, the menus the business withdrew and the courses it
removed from a menu and the menu choices of the products; making and deleting the temporary cluster is the procedure
"Devolver un negocio a un momento" of ERPlora/aws)
Actor: the ERPlora staff who run the platform, when a business asks for it
Screen: the Hub admin (`hubs.erplora.com/admin`) › Hubs, actions "Restore from a copy…" and "Restore to a separate
copy…"; Separate copies, action "Recover into the business…"; and Recoveries
Steps:
  1. A business asks to go back to how its data was at a moment of the last few days. The staff makes a temporary
     cluster restored to that moment and registers it in Clusters, closed to new hubs.
  2. In Hubs they choose the business (or several of the same cluster) and the action "Restore from a copy…".
  3. The confirmation page explains what is going to happen, says under each business the size of its database and
     how long it can stay closed ("476.8 MB: closed for up to 2 minutes"; several are restored one after another) and
     asks for the temporary cluster (only the ones closed to new hubs are offered) and the moment with its time zone
     ("2026-11-09T14:30:00Z is UTC"). They press **Restore them**.
  4. "1 hub will be restored from <cluster> as it was at 2026-11-09 14:30 UTC: closed while it is restored, for up to 2
     minutes. If it is refused, its page says why under «last error»." appears (with several, the time of all of them).
     Meanwhile the list says in the cluster column where the copy comes from ("<its cluster> ← <temporary cluster>"),
     and whoever opens the business sees it is under maintenance.
  5. When it ends, within that time at most, the system has copied the business's database from the temporary
     cluster, kept aside the one it had and put the copy in its place. The business opens again with its data of that moment and the arrow leaves
     the list.
  To a separate copy (hub#1213), for a business that invoices with VeriFactu in production or when only what was lost
  is wanted back without touching the rest:
  6. In Hubs they choose the business and the action "Restore to a separate copy…". The same page asks for the
     temporary cluster and the moment, and explains that the business stays open without anything changing and that the
     copy is no business: nobody opens it and nothing in it is sent to the tax authority. They press **Make the
     copies**.
  7. "1 hub will get a separate copy as it was at 2026-11-09 14:30 UTC, made from <cluster>: the business stays open as
     it is. Separate copies lists it, and says if it could not be made." appears. The business is not closed for a
     second.
  8. In Separate copies they see it "Being made" and, a few minutes later, "Made", with its moment and until when it is
     kept (7 days); its page also says its database, its cluster, who asked for it and when. If it could not be made, it
     says "Failed" and why under "last error".
  Bringing back into the business what the separate copy has and the business lacks (hub#1257):
  9. In Separate copies they choose the made copy and the action "Recover into the business…". The page explains that
     what the business deleted and still holds comes back as it was, with its history, and that what it no longer has is
     created again as its own screen creates it, nothing copied; that what the business has, or has made again, is left
     as it is, but for one thing: a category that comes back takes back what it had inside and the business still keeps,
     without taking it out of where the business has put it since; that records for the tax authority are never brought
     back and that the business stays open. And that
     what comes back is nothing new to the business: it starts none of its automations, so nobody is welcomed or told
     again of a booking they already had (hub#1307). Below, "What to bring back", with what can be brought ticked
     (today, **Customers**, **Product categories, Products, Product links to categories**, **Service categories,
     Services, Service links to categories, Subcategory links to categories**, **Appointments, Repeating
     appointments**, **Price list prices**, **Menus, Menu courses, Menu choices of products** and **Modifier groups,
     Modifier options, Modifier groups of categories, Modifier groups of products**). They press **Recover**.
  10. "1 separate copy will give back Customers, Product categories, Products, Product links to categories, Service
      categories, Services, Service links to categories, Subcategory links to categories, Appointments, Repeating
      appointments, Price list prices, Menus, Menu courses, Menu choices of products, Modifier groups, Modifier options,
      Modifier groups of categories, Modifier groups of products into its business within a few minutes: Recoveries says
      how it went."
      appears.
      In Recoveries they
      see it "Asked" with the copy, what
      was asked and when.
  11. A few minutes later it says "Done" and what came back, each thing apart and by its name: "Customers: 1
      restored, 2 created" or "Customers: 2 created, 1 not created". Its page also says which did not come back and why (by their identifier in the copy,
      without personal data). If one came back without something it had, its count says so ("Services: 2 created, 1
      with notes") and its page, under "notes", what it lacks and why, by its identifier in the copy. A customer the
      business deleted and still holds comes back THE SAME card, with their
      purchases and what was spent, their consents, notes and activity, their groups, tags and own fields and their
      linked orders (CUSTOMER-F33). One the business no longer has comes back as a new card, created as the Customers
      screen creates it, with their name, contact, tax ID, address, dates, source, stage, channel and notes, and with their
      groups, tags and own fields: the group, tag or field the business has with that name is that one, without making
      another, and one it no longer has is made again as it was (hub#1285); a value of a field the business deactivated,
      or one its field no longer accepts, does not come back, and the card comes back without it, with its note
      ("Customers: 2 created, 1 with notes"; hub#1438). A deleted card that comes back also gets back the group, tag or own field the business
      deleted afterwards, just like the new card (hub#1356); what the business still has stays as it is, even if it took
      the card out of a group or removed a value before deleting it, and a value it already has in a field the business
      made again stays. A card whose personal data was erased (GDPR) or one merged into another never
      comes back, and one the business has already made again (the same name, phone and email) is not repeated. With
      Products, "Product categories: 1 created; Products: 1 restored, 1 created; Product links to categories: 1
      created" (the categories, the products and the links that came back, each with its own count): first each product category the business no longer has (it deleted or lost it) comes back as a new one,
      created as the Categories screen creates it, with its name, slug, description, icon, colour, order and tax
      category; the deleted one stays deleted (INVENTORY-F07). One the business keeps, even renamed, is the same one, and
      one it has already made again (another live one with its name, case and spaces aside, that is not already one of
      the copy's; the oldest if there are two) is not repeated: its own is used, as it is. Then a product the business
      deleted and still holds comes back THE SAME and counts as restored, with its stock, its categories that are still
      live, the one that just came back if it had it in the copy, its image of the library (the one it had in the copy
      if it was deleted before deleting left it and it was left without any) and its whole history in
      Movements, active and on sale (INVENTORY-F34). One the business no longer has comes back as a new one, created as the Products screen creates it,
      with its name, SKU, EAN-13, description, type, price, cost, units, threshold, stock control and tax category, active
      or inactive as it was and in its categories: the same one if the business still has it, and otherwise the one that
      just came back or the one the business made again with its name; with no stock, which is counted (INVENTORY-F14),
      because the copy's is another day's, and with the image of the library it had (not one the library no longer
      has; never an own photo, which was deleted with the product). One the business has already created again
      (another live one with its SKU or its EAN-13) neither comes back nor is repeated. Last, the products the business
      keeps live that were, in the copy, in a category that has just come back go back into it, without losing any other
      (INVENTORY-F07): it is the only thing the recovery touches of what the business has, and it is counted apart, as
      "Product links to categories". A category the business keeps (even with products taken out of it) or made again by
      hand is not filled. With Services, "Service categories: 1 created; Services: 2 created; Service links to
      categories: 3 created; Subcategory links to categories: 1 created" (the categories, the services and what the
      business kept that went back into them, each with its own count): first each service category the business no longer has (it deleted or
      lost it) comes back as a new one, created as the Categories screen creates it, with its name, description, icon,
      colour and order, inside its parent category if the business has it or it comes back too (otherwise at the root);
      the deleted one stays deleted. Last, what it had inside in the copy and the business keeps where deleting it left
      it goes back into it (SERVICE-F08): its services still without a category, archived ones too, and its
      subcategories still hanging where it hung (the root, if it was at the root), each changed as the screen changes it:
      it is what the recovery touches of what the business has, and it is counted apart, as "Service links to
      categories" and "Subcategory links to categories"; if the business moves one meanwhile, it stays where the
      business put it and is counted "not created" with its reason (`service.service_moved`), and if it changes one
      without moving it while the category comes back (another price, another icon), it stays as the business left it
      and is counted the same, "not created" with its reason ("service.service_changed: came back without the service
      <its identifier>: changed by the business meanwhile", or `service.subcategory_changed`). What the business moved
      since (a service into another category, a subcategory elsewhere) stays where it is, and
      the category's count says so ("Service categories: 1 created, 1 with notes"), with the reason in its notes
      ("service.service_moved: came back without the service <its identifier>: moved to another category since"). One
      the business has already created again (another live one with its name, case
      and extra spaces aside) is not repeated: its own is used, as it is, and it is not filled, nor is the one an earlier
      recovery brought back if it is asked again. If that recovery failed halfway, asking for it again from the same
      copy finishes what it left: what the business keeps untouched since the category came back goes back into it,
      counted in its links. Then each service the business no longer has
      comes back as a new one, on offer, created as the Services screen creates it, with its name, pricing, prices, cost,
      duration, buffers, capacity, descriptions, booking settings, order, featured flag, SKU, barcode and notes, its tax
      category and its category: the same one if the business still has it, and otherwise the one that has just come
      back or the one the business created again with its name; and with the professionals who performed it and the
      business still has on its staff, each with their own minutes and price, assigned as Services assigns them
      (SERVICE-F31): as their main service if the business has not given them another since, and switched off if it
      was. Someone Staff terminated, or the business no longer has, is not assigned, because they can no longer be
      booked, and Recoveries says so in the service's notes ("service.member_terminated: came back without the
      professional <their identifier>: terminated in Staff", or "…: no longer in Staff"). It comes back with the image
      of the library it had, as Services sets it (SERVICE-F34): not one the library no longer has, and never a photo of
      its own, because the separate copy is of the database and not of the files. An archived one is still in
      the business and does not come
      back (it is restored in Services), nor does one the copy had archived, and one the business has already made again
      (another with the same name in the same category, not itself one of the copy's; each counts for one only, so two
      services with the same name both come back) is not repeated. Asking again creates nothing twice.
      With Appointments, "Appointments: 1 restored; Repeating appointments: 1 restored" (the appointments and the
      repeating appointments that came back, each with its count).
      Appointments always go after customers and services, whatever the order they are asked in, so each finds its
      customer and its services. Each appointment that has not come yet and was still booked (pending or confirmed, not
      charged) comes back. One the business deleted and still holds comes back THE SAME and counts as restored, as it
      was when it was deleted: with its number, its customer, its services, its professional, its time, its notes, its
      series and its history, which adds "Restored" (APPOINTMENT-F11). One the business no longer has comes back booked
      as the agenda books it: for its customer's card in the business (the same one, the one it was merged into or the
      one made again), with its services in the business as Services matches them (the same one or, if it is gone, the
      one made again by hand or just brought back by Services: the same name in the same category, the oldest if there
      are two), its professional, its time, its minutes and its notes; as a new appointment, with another number and
      without its history. It is never booked over another: one whose time is already taken, no longer fits the
      business's or the professional's hours or is blocked, or whose customer, service or professional is no longer
      there, does not come back and its reason says why ("appointment.slot_taken: …", "service.service_not_found: …");
      a deleted one that does not come back for that is not created anew. Those gone by do not come back, nor one the
      business has (even if it cancelled it) or booked again (the same customer at the same time, or its series on that
      date).
      After the appointments go their repeating appointments, those that in the copy were still booking (active, with
      their professional and not ended). One the business deleted and still holds comes back THE SAME to Repeating and
      counts as restored: active, with its customer, its services, its professional, its repetition and the appointments
      it had already booked (APPOINTMENT-F15). It books nothing by itself, so nothing is booked twice: its next dates are
      booked by "Book appointments", which skips those that already have an appointment. One the business no longer has
      is created again as Repeating creates it (APPOINTMENT-F12), for its customer's card and its services in the
      business as the appointments are, and books only the dates of its window that still fit: none on which an
      appointment already came back. If its customer is gone or its professional or one of its services can no longer be
      booked, it does not come back and its reason says why; one the business created again (the same customer,
      repeating the same way on the same day at the same time) stays as it is.
      The price list prices always go after the products: "Price list prices: 2 created". Each price of the copy the
      business no longer has comes back to its price list, with its price and its "from quantity", put as the price
      list's detail puts it, so a deleted product that comes back, the same or as a new one, gets its prices back in
      the price lists it was in (PRICING-F15), and so does a service that comes back as a new one: they go after the
      services, to the one the recovery made for it (one the business made again by hand gets none, and the price says
      why). One whose place (the same price list, the same product or service and
      the same "from quantity") the business has taken again is not repeated: the business's own stays. One the price list does not accept today
      (deactivated, or its product still deleted) does not come back and its reason says so. The product's discount
      rules, which deleting it only switched off, are switched back on by themselves with it (PRICING-F14).
      The modifier groups of the products go after the products too: "Modifier groups of products: 2 created". Each
      group that in the copy hung from a product live there and that the business no longer has linked to that product
      is linked again, as the group's sheet links it, so a deleted product that comes back, the same one or as a new
      one, asks again at the till for its sauces, its doneness or its extras (MODIFIER-F10). One whose group the
      business has linked to that product again is not repeated: the business's own stays. One the group's sheet does
      not accept today (its product still deleted, or the business already made another one by hand with its SKU, or it
      deleted the group and already made another one by hand with its name) does not come back and its reason says so.
      Just before them go, counted apart, the modifier groups of the categories: "Modifier groups of categories: 2
      created". Each group that in the copy hung from a category live there and that the business no longer has linked
      to it is linked again the same way: to the same category if the business kept it, or to the one the recovery
      brought back for it with its name, so its products ask for it again at the till. A category still deleted, or one
      the business made again by hand, stays without it, and its reason says so. Before them, counted apart, the options
      the business took away from a group it keeps: "Modifier options: 1 created". Each one comes back to its group, the
      same even renamed, as the group's sheet adds it, with its supplement, its own tax category and its order; one the
      business already made again with its name in that group is not repeated. If it came chosen by default and the
      group already comes with as many as it takes (another one, in a "choose one" group), it comes back not chosen, the
      business's stay chosen and its note says so ("Modifier options: 1 created, 1 with notes") (MODIFIER-F10). And
      before all that, counted apart, the groups themselves: "Modifier groups: 1 created". Each group the copy has and
      the business no longer has (it deleted it, with its options and its links) is created again as the Modifiers
      screen creates it, with its options as the group's sheet adds them, and its links of the copy are made to that
      one, so it shows again at the till with its options and its supplements (MODIFIER-F10). One the business made
      again by hand with its name stays as it is, with no other like it, and one it keeps, with the options it has plus
      the ones it took away. An option the group's sheet does not accept today (its own tax category is no longer active
      in Taxes) does not come back: the group comes back without it and its note says so ("Modifier groups: 1 created, 1
      with notes").
      The menu choices of the products go after the products too: "Menu choices of products: 2 created". Each choice
      that in the copy offered a product live there and that the business no longer has is added again to its course,
      as the menu builder adds it, with its supplement and, if it was sold out, sold out, so a product that comes back,
      the same or as a new one, shows again in its menus at the till (COMBO-F15). One the business still has, even if it
      changed its product, is not repeated, nor one whose product the business has offered in that course again: the
      business's own stays. One the menu builder does not accept today (its product still deleted or deactivated, or the
      business already made another one by hand with its SKU) does not come back and its reason says so. Just before
      them go, counted apart, the menus and their courses: "Menus: 1 created; Menu courses: 2 created". Each menu the
      copy has and the business withdrew (with its courses and choices) is made again as the Menus screen makes it,
      with its price, its tax category and the library image it had; then each course its menu no longer has (the menu
      has just come back or the business removed the course) is added again at the end of the menu as the builder adds
      it, and its choices go to that course, so the menu shows again at the till with its courses and supplements
      (COMBO-F15). One the business made again by hand with its name (the menu, or the course in its menu) stays as it
      is, with no second one, and what hung from it in the copy does not come back and its reason says so; what comes
      back is recognised even if renamed, so asking again does not repeat it.
In: the chosen businesses, the temporary cluster with their copy and the moment; to recover, the made separate copy and
what to bring back.
Out: the business's database as it was at that moment; the one it had, kept 7 days on its server; the notice
`control.hub.restore_requested` with who asked for it. The other businesses notice nothing. To a separate copy: the
business as it was, untouched; a separate database on its cluster with the data of that moment, closed to the
application and kept 7 days; the notice `control.hub.restore_aside_requested` with who asked for it. When recovering: in
the business, each deleted card it still held, live again with its card-recovered notice (`customer.customer.restored`),
a new card for each customer it no longer had, with its card-created notice (`customer.customer.created`), and on both
those of its groups and tags set (`customer.customer.groups_changed`, `customer.customer.tags_changed`), each group, tag or own
field it lacked made again, with its notice (`customer.group.created`, `customer.tag.created`,
`customer.field.created`, and `customer.group.updated` or `customer.tag.updated` if it was deactivated), a new
product category for each one it lacked, with its category-created notice (`inventory.category.created`) and that of
each deleted product that comes back in it (`inventory.product.categorized`), each deleted
product it still held, live again with its product-recovered notice (`inventory.product.restored`), a new product for
each product it no longer had, with its product-created notice (`inventory.product.created`), a new service category
for each one it lacked, with its category-created notice (`service.category.created`) and the one of each service or
subcategory the business kept that goes back into it (`service.service.updated`, `service.category.updated`), a new
service for each one it
no longer had, with its service-created notice (`service.service.created`) and a professional-assigned notice
(`service.assignment.assigned`) for each professional who comes back with it, each deleted appointment it still held,
live again with its appointment-recovered notice (`appointment.appointment.restored`), a new appointment for each one
it no longer had, with its appointment-created notice (`appointment.appointment.created`), each deleted repeating
appointment it still held, active again with its series-recovered notice (`appointment.recurring.restored`), a new
repeating appointment for each one it no longer had, with its series-created notice (`appointment.recurring.created`)
and that of each appointment it books, a price list price for each one it lacked, with its price-put notice
(`pricing.price_item.added`), a new modifier group for each one it lacked, with its group-created notice
(`modifier.group.created`) and that of each of its options (`modifier.option.created`), an option for each one a
modifier group it keeps lacked, with its option-created notice (`modifier.option.created`), a modifier group linked to a
category or a product for each one it lacked, with its link-made notice (`modifier.link.attached`), a menu for each one
it lacked, with its new-menu notice (`combo.combo.created`), a course for each one it lacked, with its new-course notice
(`combo.group.created`), and a menu choice for each one it lacked, with its new-choice notice
(`combo.option.created`), and nothing else. Each of
those notices says the recovery did it (its actor is `copy_recovery:<id>`, that of the row in Recoveries), so no
automation of the business starts on them (FLOW-F21), whether of something created or of something recovered; what only
brings the business's own data up to date with them goes on the same (the WhatsApp Inbox links its conversation to the
card; Price Lists switches back on the rules of the product that comes back, `pricing.rule.activated`), and what it records in doing so carries the same mark, so none starts from it either, first or second hand (the
conversation linked again does not start "a WhatsApp conversation is linked to a customer"; hub#1365). The
copy, untouched; the notice `control.copy.recovery_requested` with who asked for it.
If it fails: what the restore does not accept is said in the notice, business by business, and that business is not
touched: one that is not ready or has no database of its own, a demo, one being moved or restored, a cluster open to new
hubs or with living businesses, the business's own cluster, a copy that is not on that cluster or is too large, and a
moment that has not come yet. Without a cluster or a moment, the page asks for them again. If the business has
production VeriFactu records made, sent or changed after that moment, it is not restored and nothing changes, because it
would use again numbers the AEAT already has: its page says so under "last error" ("restore_fiscal_records: …"); for that
case there is "Restore to a separate copy…", which does not compare them because it does not touch the business. Any
other failure undoes the restore by itself: the business keeps its usual database and its page says why. A separate copy
accepts the same as the restore and what it does not accept is said in the notice the same way; if making it fails,
nothing of it is left and Separate copies says why ("restore_aside_<step>: …"); the business does not notice. Recovering
is only possible from a made copy and once at a time per copy; otherwise the notice says so ("Only a separate copy that
is made gives anything back."), and with nothing ticked the page asks again. What cannot be brought from an app is said in
its result and the rest goes on: the app is turned off in the business ("Customers: nothing (app_inactive: …)"; in an app that gives back several
things, each says so: "Service categories: nothing (app_inactive: …); Services: nothing (app_inactive: …)"), or the
copy did not have it, lacks the migration its read needs or has one this code does not know (`recover_not_in_copy`,
`recover_copy_behind`, `recover_copy_ahead`). What the create operation does not accept today (a phone no longer valid, a
product without a tax category or with one Taxes no longer has active, a service whose tax category was turned off
(`service.tax_category_unknown`), a time taken, a customer no longer there, a service the business no longer has
nor made again) is counted "not created" with its reason,
and the rest comes back; so is a deleted card that was merged into another or erased meanwhile
("customer.customer_unavailable: …"). If the copy is gone, the recovery says "Failed" and why
("recover_copy_unreadable: …"). While the business is being moved or restored, the recovery waits without doing anything.
With the platform frozen for a database upgrade, the restore waits, with the business under maintenance, until it
is unfrozen. With records from the test environment only, the chain is recovered afterwards (VERIFACTU-F28). The
support staff see the list, Separate copies and Recoveries, but not the actions.
Involved: VERIFACTU-F28, BASE-F111 (the same waiting page as a move), CUSTOMER-F01, CUSTOMER-F04, CUSTOMER-F06,
CUSTOMER-F07, CUSTOMER-F12, CUSTOMER-F13, CUSTOMER-F16, CUSTOMER-F29, CUSTOMER-F33, INVENTORY-F01, INVENTORY-F04,
INVENTORY-F07, INVENTORY-F30, INVENTORY-F34, SERVICE-F01, SERVICE-F04, SERVICE-F05, SERVICE-F07, SERVICE-F08,
SERVICE-F31, SERVICE-F34, APPOINTMENT-F01, APPOINTMENT-F10, APPOINTMENT-F11, APPOINTMENT-F12, APPOINTMENT-F15, PRICING-F07,
PRICING-F14, PRICING-F15, MODIFIER-F02, MODIFIER-F04, MODIFIER-F05, MODIFIER-F10, COMBO-F04, COMBO-F05, COMBO-F06, COMBO-F15, FLOW-F21, WHATSAPP_INBOX-F04; hub#1198,
hub#1213, hub#1257,
hub#1282, hub#1283, hub#1284,
hub#1285, hub#1306, hub#1307, hub#1319, hub#1320, hub#1321, hub#1322, hub#1323, hub#1326, hub#1327, hub#1341, hub#1343,
hub#1355, hub#1356, hub#1364, hub#1365, hub#1373, hub#1375, hub#1429, hub#1431, hub#1438, hub#1442, hub#1456, hub#1457,
hub#1458, hub#1459, hub#1473, hub#1474, hub#1495, hub#1505, aws#77

### BASE-F115 See the help of the screen in view
<!-- from WORKBOOK.md sha256:c36cfdd53265 -->
Status: done
Actor: owner, administrator, manager, employee
Screen: the top bar of a module whose help is ready or of a screen of the Hub ("?" button, "Help") and the help window
Steps:
  1. In a module whose help is ready and on the Hub's own screens (Home, Employees, a person's page, what a role allows,
     Files, Apps, System, Settings and My profile), at the top right, next to the assistant, is the "?" button ("Help"),
     going back too. It is not in a module whose help is not ready yet, on a screen without help (the API's
     documentation), on the "No access" one, nor for whoever cannot see the Home.
  2. Tapping it opens the "Help · <module>" window, with the module's icon ("Help · ERPlora" on a screen of the Hub),
     centred on a tablet or a computer and from the bottom on a phone. It never opens by itself, and it closes when the
     person moves to another module.
  3. At the top, the module's video, if it has one, in the person's language or, if there is none, in Spanish. Nothing
     is asked of YouTube until it is tapped, and it plays inside the window, across its whole width, in YouTube's full
     player: fullscreen, captions on in the help's language and its logo, which opens the video on YouTube in another
     tab.
  4. Below, "What it is for", with a short text, two or three sentences, of what is done in the module (on a screen of
     the Hub, of what the Hub always brings), and "On this screen · <tab>", marked "You are here", with the summary of
     what the tab the person is on shows: short and whole, with no "See more".
  5. "How to" brings each finished task of the module, grouped by tab, those of the tab the person is on first; on a
     screen of the Hub, those of the Hub's screens the person can see, and only the ones their role does: an employee is
     not shown how to turn an app on. Each task is a folded row that opens with its steps and its "If something goes
     wrong", one at a time. A task with a
     short video shows it when it opens, before its steps, in the same player as the module's and in the person's
     language or, if there is none, in Spanish; with several, one below the other. Opening the help or a task asks
     nothing of YouTube until the video is tapped. With more than eight tasks, "Search tasks…" appears on top, filtering by the title and the steps regardless of accents and
     capitals; if nothing matches, it says "Nothing matches your search" and "Clear search" shows them all again.
  6. "Other screens" brings the other tabs of the module, or the other screens of the Hub the person can see, folded,
     each with its short summary. A link of the help to a screen of the Hub goes there and closes the help.
  7. "Ask the assistant" closes the help and opens the assistant with the question written, without sending it: "How
     do I do this: <task>?" about the last task opened or, if none was opened, "How do I use <module> on <screen>?";
     if something was already written, the question goes below it. "Close" closes the help.
In: the module, or the screen of the Hub, and the tab the person is on.
Out: nothing: the help is only read. It is the part of the user manual of the module, or of the Hub's own screens, the
customer reads, in the person's language.
If it fails: while it is read, the window shows its skeleton; if it cannot be read, it says "Could not load the help."
and "Retry" asks for it again. The help already read stays stored until the page is reloaded: offline it opens again,
also from another tab of the module or another screen of the Hub, and each video says "Offline: the video is not
available", with the text in view. If the manual is not translated into the person's language, or its translation fell
behind, the help comes in Spanish.
Involved: BASE-F92, BASE-F93

### BASE-F116 Read what is new in ERPlora
<!-- from WORKBOOK.md sha256:a8f87874c9dd -->
Status: done
Actor: owner, administrator; through the assistant, anyone of the business
Screen: System · Updates
Steps:
  1. In the "Updates" tab, below the version and its date, comes "What's new": what has changed in ERPlora
     that the business notices, the most recent first. While it loads: "Reading what's new…".
  2. Each item says its day, whether it is something new, an improvement or a fix ("New", "Improved" or "Fixed"), a
     short title and one or two sentences on what can be done now, just as they were written. They are notes written
     for the business, never the list of changes to the code.
  3. The 20 most recent are shown, with no pages.
  4. With none, it says "Nothing new yet.".
  5. Through the assistant, "what's new in ERPlora?" or "what changed in the latest update?" reads them the same way,
     in the person's language. That is how whoever does not run the business, who has no System, reads them
     too: they say nothing about the business.
In: what is new in the version running: it travels with it, so it is always its own.
Out: nothing saved: what is new is only read.
If it fails: "Could not load what's new" with "Retry"; the version and its date stay in view.
Involved: BASE-F41, BASE-F39

### BASE-F117 See in the bell that the plan has an unpaid invoice
<!-- from WORKBOOK.md sha256:51c6d2d30239 -->
Status: done
Actor: owner, administrator
Screen: The bell
Steps:
  1. erplora.com cannot charge the renewal of the business's plan and gives it its 7 days of grace (BILLING-F16): the
     business keeps working with its whole plan.
  2. The bell of whoever runs the business goes up without reloading with the urgent notice "Your ERPlora plan has an
     unpaid invoice", which comes in as a card and settles in it. Its sentence says until when: "Pay it on
     erplora.com: if it is not paid by Nov. 24, 2026, the business is suspended. Nothing is deleted.", with the
     date on the business's clock, and the bell's ring empties over that last week.
  3. "Pay on erplora.com" opens, in a new tab, this business's unpaid invoices on erplora.com, where it is paid
     (BILLING-F17). Only in the browser: in the installed app the notice comes all the same, without the button, and
     its sentence already says where to pay it.
  4. If the deadline goes by and erplora.com has not suspended it yet, the notice says so at that moment, without
     reloading: "Pay it on erplora.com: its deadline was Nov. 24, 2026 and the business may be suspended at any
     moment. Nothing is deleted.", with the ring empty.
  5. Once it is paid, the notice disappears as soon as erplora.com tells the business. If it is suspended, the business
     stops opening until it is paid (BILLING-F16).
In: the business's status and the moment it is suspended, as erplora.com sends them in its photo of the business
(HUBS-F31). The Hub does not ask erplora.com nor count the 7 days on its own.
Out: nothing saved in the Hub.
If it fails: a manager or an employee does not see the notice. If the photo does not bring the deadline, the notice
comes without a date: "Pay it on erplora.com: if it is not paid soon, the business is suspended. Nothing is deleted.".
If the notices cannot be read, the bell keeps what it last knew, as in BASE-F10.
Involved: BASE-F10, BASE-F11, BILLING-F16 (erplora.com), BILLING-F17 (erplora.com), HUBS-F31 (erplora.com)

### BASE-F118 Open a screen without permission: "No access" and whom to ask
<!-- from WORKBOOK.md sha256:f2f551451108 -->
Status: done
Actor: manager, employee
Screen: No access
Steps:
  1. They open by its address (a link, the history, a tab left open or typing it) a screen their role does not open:
     an entry of an app that does not show in their menu, such as Taxes' "Rules" for an employee, one of the platform
     that does not show in their side menu, such as "System" for whoever does not run the business, or any screen
     that hangs from them. Also another person's page in **Employees** for whoever does not run the business, even
     when they reach it because the till switched user with the page open (BASE-F60).
  2. Instead of the screen, in the same address, "No access" shows: "You do not have access to this screen" — "Your
     role in this business does not open it.". While it looks for whom to ask: "Looking for who can give you access…".
  3. Below, "Ask one of these people to give you access:" and the name of each one, with their avatar: whoever can
     change their role on erplora.com (HUBS-F26). An employee sees the owner and the administrators; a manager, only
     the owner. Only the name: neither the email nor the phone. Those invited who have not entered yet count too.
  4. "Go to Home" leads to the Home.
In: the person's session, which says which screens of each app their role closes and which permissions they hold,
those that open each entry of the side menu (the same ones that do not show in their menus); the people of the business with their role, from erplora.com's last photo.
Out: nothing.
If it fails: if it cannot find out whom to ask, "We could not find out who can give you access" — "Ask whoever runs
the business, or try again." with "Retry", and the screen still says they have no access. With nobody to name: "Ask
whoever runs the business to give you access.". If the whole app does not open in the business (turned off or without
its subscription), its reason shows (BASE-F26). The Hub refuses what that screen would ask all the same: "No access"
only spares a screen of errors.
Involved: BASE-F26, HUBS-F26 (erplora.com)

### BASE-F119 What each person sees by their data permissions
<!-- from WORKBOOK.md sha256:606be0e0f566 -->
Status: done
Actor: owner, administrator, manager, employee, accountancy firm
Screen: Employees · Staff, Home · Summary, Sales · Sales, Customers
Steps:
  1. Besides what it may do, each role says which sensitive data it sees, with four data permissions: view costs,
     view customer contact details, view team contact details and view business totals. The owner, the
     administrator and the manager have all four; the employee, only the customers' contact details, which they need
     to serve them; the accountancy firm, only the business totals.
  2. Whoever lacks a data permission does not receive that data by any way: not on the screen, not through the API,
     not in what the assistant answers. Where it would go, the data comes empty and the screen does not show it.
  3. In **Employees › Staff**, the "Email" column only shows to whoever sees the team's contact details. An employee
     sees nobody's email, not even their own, nor inside a name: an erplora.com account without a name shows with
     what comes before the @.
  4. A Home panel whose figure is a piece of data the person does not see does not show to them on the board nor
     among the ones they may add.
  5. An API key sees the data whoever made it sees today: a key of the owner or of an administrator, who
     see all of it, reads and writes a product's cost as before.
  6. The business totals are the figures of the whole business, beyond what each one does: with everyone's sales,
     the figures of **Sales** and its Home panels are the whole business's; without them, those of the person's own
     sales. In **Customers**, "Revenue" only shows to whoever sees them.
In: the person's role in this business.
Out: nothing saved.
If it fails: a request through the API or to the assistant that filters or sorts by a piece of data the person does
not see is refused as if they had no permission, doing nothing.
Involved: BASE-F06, BASE-F07, BASE-F81, BASE-F82, BASE-F86, BASE-F125, SALE-F28, CUSTOMER-F31

### BASE-F125 A key stops working when whoever made it no longer may
<!-- from WORKBOOK.md sha256:c7040bbe5159 -->
Status: done
Actor: API (another program), owner, administrator
Screen: none (it shows in what the API answers the other program)
Steps:
  1. Each key remembers who made it. A key made before that was kept goes to the business's owner's name with the
     next photo from erplora.com, which arrives every night at the latest; until then it may do the same as the
     owner, as before.
  2. A key never does more than whoever made it, with what that person may do today in the business: it opens an
     operation only if its maker has its permission; it receives a piece of sensitive data (costs, contact details,
     the business totals) only if its maker sees it, and otherwise gets it empty (BASE-F119); and in what has an
     owner (sales, tills, invoices, appointments, commissions) it reads everything only if its maker sees
     everything, and otherwise only its maker's. When booking an appointment or serving a customer, the key stays on
     the customer's side, as until today.
  3. If whoever made it has their role changed in erplora.com and loses a permission, the key loses it at the same
     time, without touching it: what needs it answers 403 `permission_denied`, and the data they no longer see comes
     empty.
  4. If whoever made it leaves the business, the key stops opening anything: every request answers 403
     `base.api_key_owner_gone`, "Whoever made this API key is no longer in the business. Make a new one.". The key
     stays in **Employees › API keys**: whoever runs the business revokes it (BASE-F88) and makes another
     (BASE-F86).
In: the key the other program calls with and the role today of whoever made it, from the last photo from
erplora.com.
Out: nothing saved.
If it fails: the 403 says whether whoever made it lacks the permission (`permission_denied`) or is no longer in the
business (`base.api_key_owner_gone`); the rest of what refuses a key does not change: what the key itself may not
do, 403 `base.api_key_scope`, and past its requests a minute, 429 `base.api_key_rate_limited`.
Involved: BASE-F86, BASE-F88, BASE-F89, BASE-F119, HUBS-F26 (erplora.com)

### BASE-F120 Start ERPlora on signing in to the computer
<!-- from WORKBOOK.md sha256:3c20dd6a4110 -->
Status: done
Actor: owner, administrator, manager, employee
Screen: Settings · General
Operations: none
Steps:
  1. In the ERPlora app on a computer, **Settings › General** carries under "This device" the switch "Start on
     login" ("Open ERPlora when you sign in to this computer, so tickets always have somewhere to print."), off
     from the factory. In a browser and in the Android app it does not show.
  2. When it is moved, the Hub asks the app, which records it in the system and reads back what the system says;
     meanwhile the switch waits.
  3. The switch stays where the system says, not where it was moved.
In: the switch, on the computer itself.
Out: the system's start-up of this computer, not of the business. Nothing is saved in the Hub.
If it fails: below it, "Could not change the start on login setting.", and the switch goes back to what the
system says. An app older than this command does not show it.
Involved: HUB_APP-F27 (ERPlora/app), BASE-F62

### BASE-F126 Turn ERPlora's support access on or off
<!-- from WORKBOOK.md sha256:63af2ec5f10c -->
Status: done
Actor: owner, administrator, ERPlora's support staff
Screen: Settings · General, the page "This business does not let support in"
Steps:
  1. When the business wants ERPlora's support staff to come in and help set it up (loading the products, adjusting
     its apps), the owner or an administrator turns on "Let ERPlora support in" in the "Support access" card, the last
     one of Settings › General. It comes off. It is also turned on and off through the API or by asking the
     assistant, which confirms it before changing it.
  2. The change is saved at once, with who made it and when, and a notice confirms it: "Support access is on: ERPlora
     support can come in." or "Support access is off: ERPlora support can no longer come in.". It does not expire: it
     stays on until someone of the business turns it off, because getting started can take several days.
  3. Anyone of the business sees in the card whether it is on, who changed it last and when ("Last changed by Ana,
     11/24/2026, 10:30 AM.") and, under "Latest support visits", the last 10 entries of support (who and when), the
     most recent first; the API gives the same. While nobody of support has come in, it says "Nobody from ERPlora
     support has come in yet.". Whoever does not run the business sees the switch disabled, with "Only who runs the
     business can change it.".
  4. With the access on, a person of ERPlora's support comes into the business with "Enter as support", in erplora.com's
     admin, with their own account, and arrives as an administrator: they may do everything
     but what only the owner does (buying for the business, resetting it, its copies). They are not in Employees nor
     among who can give access, do not enter the tills with a PIN or a badge, take no place and do not count in the
     plan's use, and their browser does not stay as a device of the business: it neither ends another device's session
     nor has its own ended by another one's entry. Each entry joins the list of the latest entries at once,
     and what they do stays in the records under their name.
  5. With the access off they do not come in: they see "This business does not let support in" — "The owner or an
     administrator of this business has to turn on ERPlora's support access before you can come in. Ask them to, then
     try again." with "Try again".
  6. When someone of the business turns it off, the support sessions open in the business end at once and what they
     have open learns it; the rest of the team's go on.
In: on or off; the support account erplora.com vouches for.
Out: the business's setting, with who changed it and when. Event `base.support_access.changed`. Each entry of
support, with who and when. Event `base.support_access.entered`.
If it fails: whoever does not run the business has the change refused and the setting stays
as it was; reading it, they see they cannot change it. If the change cannot be saved, "Could not save the change."
shows below it and the switch goes back to what was saved; if the card cannot read the setting, "Could not load the
support access." with "Retry". With the access off, support opens no session and leaves no entry (the page of step
5).
Involved: BASE-F52, BASE-F57, BASE-F97, BASE-F100, HUBS-F38 (erplora.com)
