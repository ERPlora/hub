<!-- generated from WORKBOOK.md sha256:6cbf2d2dadf9684893a465e3aa38ab622b61bf83f0d76cb2f325d5dcd20a2405 -->

## What it is for and who it is for

Services is the **catalogue of what a hair salon or a beauty centre sells when what is sold is not an
item**: each service with its name, its pricing, its price, its duration, its category and its tax
category (the VAT it is charged with), and **which professionals perform it**, with their own duration
and price if they have them. The Appointments agenda (what is booked, how long it lasts and with whom),
the Sales till (what is charged), the Online booking page (what can be booked from outside and whether
its price and its duration are shown) and Price Lists (the special prices of a service) read from this
catalogue.

It also keeps the **vouchers**: a voucher is a package of sessions of specific services that a customer
buys once and spends over several visits. A voucher pays for a whole service line, not an amount (it is
not a gift card), and its owner is a single customer.

Who uses it:

- The **employee** (front desk, till): sees the catalogue, the categories and the vouchers, adds
  services, sees the sold vouchers and their movements, grants a voucher to a customer and spends
  sessions.
- The **manager**: also edits services and categories, creates and edits vouchers, assigns
  professionals to a service, voids or adjusts a sold voucher and sees the vouchers left with no
  customer.
- The **owner** and the **administrator**: also archive services, delete categories and vouchers and
  change the settings.

Only the hair salon uses it: the restaurant template does not bring it and no restaurant flow depends
on it.

## Reference adopted

- **Salon catalogue** (Fresha, Vagaro, Mangomint, DaySmart, Square Appointments): a service = name,
  price, duration and category; archive instead of delete; a service without a set price ("From",
  "Variable") is charged by asking for the amount.
- **Who performs each service is assigned on the service** (Fresha "Team members", Square Appointments,
  Vagaro, Mangomint, Odoo Appointments), with each professional's own duration and price.
- **Vouchers** (Mindbody, Vagaro, Boulevard, Fresha): the voucher is paid when it is sold and spending it
  issues no tax document; it covers service lines, not amounts; the expiry counts from the purchase; what
  was sold keeps the terms it was sold with; giving or correcting is a separate movement with a reason;
  only a voucher that has not been used is voided.
- Decisions of the current product that rule here: ADR-0386 (a voucher covers lines; a gift card,
  amounts), ADR-0390 (ownership is born when it is sold, the clock starts at the purchase and it is not
  transferred) and ADR-0085 (VAT is linked through the tax category of Taxes).

## Before you start

1. Services turns on **Taxes**, **Staff** and **Customers** with it, and they cannot be turned off while
   Services is on: the tax category of each service belongs to Taxes, the professionals belong to Staff
   and the owner of a voucher is a Customers card.
2. In **Taxes → Categories** there must be at least one active tax category: without it the service form
   warns "There are no tax categories yet. Set them up in Taxes before adding services.".
3. Create the categories you want to group the catalogue (SERVICE-F07) and add the services
   (SERVICE-F01). For many at once, the assistant adds them in one go (SERVICE-F06). Until there is a
   service that can be charged, the Home reminds you with "Your service catalogue".
4. Open each service and assign it the professionals who perform it (SERVICE-F31). While a service has
   nobody assigned, the agenda lets the whole bookable team perform it (SERVICE-F33).
5. Create the vouchers in **Packages** (SERVICE-F12), always filling in **Uses**: empty means unlimited
   sessions.
6. In **Settings** choose the duration, the buffer and the tax category a new service takes when they are
   not given (SERVICE-F11).

Amounts (the price of a service and that of each professional, the closed price and the amount off of a
voucher, what was paid for a voucher) are in **the business's currency**, its country's, the one **Settings →
Business** shows (euros in Spain, złoty in Poland, yen in Japan), with its decimals (the yen has none), written
with a comma or a point: "1500" is a price of 1500 yen in Japan and of €1,500.00 in Spain, and Sales charges it
the same. While the business has not answered, an amount shows as a figure without a symbol, never in euros. The
examples in this document are from a business in Spain, in euros.

## Screens

Services opens from the **Services** menu and has three tabs: **Services**, **Categories** and
**Packages**, plus **Settings** for whoever may change them. What a person cannot do does not show, and
the app refuses it even if they try through the API or the assistant.

### Services
Table with the search box "Search service…", columns **Name, Category, Pricing** (Fixed price, Hourly,
From, Variable, Free), **Price** (in the business's currency), **Duration (min)** and **Status**: **Active**, **Not configured** (with the
reason below, "No tax category: it cannot be charged") or **Archived**. It sorts by any column and, with
the **Filters** button, it filters by Name, Category, Pricing, Price (from–to, in the business's currency),
Duration and Status (the
Status filter on **Archived** switches to the archived view); list or card view; 50 per page.

**New service** opens the form: **Name, Pricing, Price (<currency>)** (in the business's currency and with
its decimals: "Price (EUR)" and "22.50" in Spain, "Price (JPY)" and "1500" in Japan; just "Price" while the
business has not answered; on leaving the field it is rewritten in the language's notation, and not before
it answers), **Duration (min)**, **Category** ("No category" or one of the
list) and **Tax category** (with no empty option; the one from the Settings comes chosen) and the
**Create service** button. Tapping a row (or its **Edit**) opens "Editing service — <name>" with the
**Save changes** button and, below, **Professionals who perform it** (SERVICE-F31, F32). Per row:
**Edit** and **Archive**; in the archived view, **Restore**. **Archive** asks to confirm: "Archive
service" — "<name> — it will no longer be offered or bookable. Its history and the appointments already
booked are kept." and, if Appointments has upcoming appointments with it, "{count} upcoming
appointment(s) still use this service. They keep their booking, price and length; only new bookings
stop.".

### Categories
Table with the search box "Search category…" and columns **Name, Parent category, Order** and
**Services** (how many services on offer it has). **New category** opens the form: **Name, Parent
category** ("No parent (root)" or another) and **Order**, with **Create category** / **Save changes**.
Per row: **Edit** and **Delete**; **Delete** asks to confirm: "Delete category" — "<name> — the category
disappears; the services in it are kept, without a category." and, if it has services, "{count}
service(s) will be left without a category.".

### Packages
At the top, **Vouchers with no customer** (manager, owner and administrator only). Table with the search
box "Search package…", columns **Name, Discount, Closed price, Lines** and **Status** (Active, Archived or
Deleted). In **Filters**, the Status filter on **Deleted** switches to the view of the vouchers deleted
from the catalogue that someone bought: per row only **Movements** and **Sold vouchers**.
**New package** opens the form: **Name, Discount type** (Percentage or Fixed amount), **Discount (%)** or
**Discount (<currency>)**, **Closed price (<currency>)** (in the business's currency: "Closed price (PLN)" in
Poland; without the code, "Discount (amount)" and "Closed price", while the business has not answered; "Leave
empty to price it as the sum of its lines minus the discount."), **Validity (days)** ("Days redeemable from the purchase; empty = never expires."), **Uses**
("Uses the voucher grants; empty = unlimited.") and **Services included**: one row per service with
**Service** and, below, **Sessions** and "Remove line"; **Add service**; **Create package** button. When
editing, instead of the lines it shows "The services included cannot be changed once created: delete
this package and create a new one.". Per row: **Edit, Movements, Sold vouchers** and **Delete** (with
"Delete package": "<name> — the package and its {count} line(s) leave the catalogue and can no longer be
sold; vouchers already sold can still be spent, and you find them filtering Status by Deleted.").

Sheets that open on top, all with **Close**, "Loading…" while they arrive, their empty state, their error
and **Load more** with "Showing {shown} of {total}" when there are more:

- **Voucher movements**: each session and each adjustment of that voucher, of every customer, the most
  recent first, with its label (**Held**, **Delivered**, **Released**, **Expired**, **Given back**,
  **Courtesy**, **Correction**), the service, the date, "Customer: <name>", who and the reason. Empty:
  "This voucher has not been used yet.".
- **Sold vouchers**: one row per purchase, with **Active** or **Voided**, the customer, the date, the
  amount, "{used} used · {remaining} left" (or "· no limit"), "Expires …" or "Never expires" and what
  was given or corrected afterwards; on a voided one, "Voided by {who} on {when}" and the reason.
  **Adjust** and **Void** buttons where they apply. Empty: "Nobody has bought this voucher yet.".
- **Vouchers with no customer**: the live vouchers whose card was deleted or anonymised, with
  "{remaining} session(s) left", "No session limit" or "Fully used", the voucher, the amount, "Customer
  deleted on {when}", "Expired" if it is and "Customer reference: <identifier>". Empty: "No voucher has
  lost its customer.".

### Services settings
Only for whoever may change them. Fields: "Default duration (min)", "Default buffer time (min)",
"Default tax category", "Show prices", "Show duration" and "Allow online booking"; **Save** button.
While the business has never saved, the factory ones show (60 min, 0 min, no category, yes, yes, yes).
Saved: "Settings saved.".

## States of each screen

| State | What the person sees |
|---|---|
| Loading | "Loading…" while the first result arrives. |
| Empty | "No services.", "No categories." or "No packages."; with a search or a filter, "No results". |
| Error | The table's notice with "Retry". A refusal of a form shows inside the form, each reason below its field, without losing what was typed; that of a row action, in its confirmation or above the table. |
| Reconnecting | What is painted stays; a strip warns "Reconnecting…". |
| App inactive | "This app is not active in this business". |
| No permission | What they cannot do does not show; if they arrive by another door, "You do not have permission". |

Amounts, durations and dates show in the format of the language of whoever is looking.

## Flows

| ID | Flow | Status |
|---|---|---|
| SERVICE-F01 | Add a service | done |
| SERVICE-F02 | Edit a service | done |
| SERVICE-F03 | Give a service an open price | done |
| SERVICE-F04 | Archive a service | done |
| SERVICE-F05 | See and restore the archived services | done |
| SERVICE-F06 | Add many services in one go | done (assistant and API; there is no importer on screen) |
| SERVICE-F07 | Create and edit categories | done |
| SERVICE-F08 | Delete a category | done |
| SERVICE-F09 | Sell a service at the till | done (Sales does it, SALE-F38) |
| SERVICE-F10 | Give the catalogue to Appointments, Sales, Online booking and Price Lists | done |
| SERVICE-F11 | Change the Services settings | done |
| SERVICE-F12 | Create a voucher | done |
| SERVICE-F13 | Edit or delete a voucher | done |
| SERVICE-F14 | Sell a voucher to a customer | done for the grant (assistant and API); not the sale at the till (see "What is left out") |
| SERVICE-F15 | Look up a customer's vouchers | done (assistant and API) |
| SERVICE-F16 | See who has bought a voucher | done |
| SERVICE-F17 | Void a voucher sold by mistake | done |
| SERVICE-F18 | Give sessions, extend the expiry or correct the balance | done |
| SERVICE-F19 | See a voucher's movements | done |
| SERVICE-F20 | A voucher expires | done |
| SERVICE-F21 | Spend a session outside the checkout | done (assistant and API) |
| SERVICE-F22 | Pay a line with a voucher | done (with Sales, SALE-F27) |
| SERVICE-F23 | Release the session if the line or the check goes away | done |
| SERVICE-F24 | Mark the sessions as spent when charging | done (not granting the vouchers sold on the receipt: see "What is left out") |
| SERVICE-F25 | The held session nobody charges comes back on its own | done (on reading and with the hourly task) |
| SERVICE-F26 | Give the session back when the sale is refunded | done (with Sales, SALE-F32) |
| SERVICE-F27 | Give the session back when the sale is voided | done (not voiding the vouchers sold in it: see "What is left out") |
| SERVICE-F28 | Merge two cards: the vouchers move to the one that stays | done |
| SERVICE-F29 | Delete or anonymise a card: its vouchers are left with no customer | done |
| SERVICE-F30 | Rescue the vouchers with no customer | done (the list; a voucher is not moved to another card) |
| SERVICE-F31 | Assign a professional to a service | done |
| SERVICE-F32 | Change or remove a professional from a service | done |
| SERVICE-F33 | Know who can perform a service | done |

### SERVICE-F01 Add a service
Status: done
Actor: employee, manager, assistant
Screen: Home, Services
Steps:
1. On the **Home**, while no service can be charged, "Finish setting up your business" brings "Your
   service catalogue" ("Add the services you sell, with their price and duration."), "Important", to
   whoever may add services. "Set up" leads to **Services**.
2. In **Services** tap **New service**.
3. Type the Name, choose the Pricing (**Fixed price** comes chosen), the Price and the Duration (min).
   Choose a Category or leave "No category".
4. Choose the Tax category (they are the ones of Taxes, by their name and their rate; the one of the
   Settings comes chosen if there is one). Without it **Create service** cannot be tapped.
5. Tap **Create service**: the form closes and the service shows in the table as **Active**.
In: the categories of Services and the active tax categories of Taxes.
Out: the service on offer and bookable (`service.service.created`); from that moment the agenda and the
till see it and, if it is booked online, the Online booking page too. What is not given takes the
Settings: duration, buffer before and after, online booking and tax category; without Settings, 60 min,
no buffer and with online booking. With the first service on offer and with its tax category active, "Your
service catalogue" is "Done" on the Home without a reload; if they are all archived (SERVICE-F04) or none
has an active tax category any more, the step goes back to pending by itself, and restoring one
(SERVICE-F05) makes it "Done" again.
If it fails: inside the form, each reason below its field: an amount that cannot be understood ("This is
not an amount. Type a figure, for example 12.50.", also with another currency's symbol: "€22.50" in a
business in Poland), one that reads two ways or a negative one; a deleted
category ("That category is not available: it does not exist in this business or it has been
deleted."); a tax category that does not exist or is deactivated ("That tax category does not exist in
Taxes or is deactivated."); with no tax category at all, the notice of Taxes. What was typed is kept.
Involved: TAX-F01, BASE-F01

### SERVICE-F02 Edit a service
Status: done
Actor: manager, assistant
Screen: Services
Steps:
1. Tap the service's row or its **Edit**: "Editing service — <name>" opens with its data.
2. Change Name, Pricing, Price, Duration, Category or Tax category (this one cannot be emptied).
3. Tap **Save changes**: the form closes and the table updates on its own.
In: the whole service.
Out: the changed service (`service.service.updated`); only what was touched changes. The appointments
already booked keep the name, the price and the duration they had; the vouchers already sold do not
change.
If it fails: the reasons of SERVICE-F01; a service that no longer exists, "That service does not exist
in this business.". A service whose category was deleted shows "No category" and saves without trouble.
Involved: SERVICE-F31

### SERVICE-F03 Give a service an open price
Status: done
Actor: manager, assistant
Screen: Services
Steps:
1. In the form choose the Pricing **From**, **Hourly**, **Variable** or **Free** (or ask the
   assistant: "Highlights from 65 €").
2. The Pricing column shows it.
In: the service.
Out: the service with its pricing (`service.service.updated`). For Sales, a service that is not at a fixed
price asks for the amount when it is charged, with its price as a suggestion; "Free" does not force the
price to 0. The minimum and maximum prices (assistant and API) are saved; the minimum cannot be above the
maximum.
If it fails: a pricing outside the five or a minimum above the maximum are refused with their reason.
Involved: SALE-F09

### SERVICE-F04 Archive a service
Status: done
Actor: owner, administrator
Screen: Services
Steps:
1. In the service's row tap **Archive**.
2. Read "Archive service": "<name> — it will no longer be offered or bookable. Its history and the
   appointments already booked are kept." and, if Appointments is active and has upcoming appointments
   with that service, "{count} upcoming appointment(s) still use this service. They keep their booking,
   price and length; only new bookings stop.".
3. Tap **Archive** (or **Cancel**). The row disappears from the list.
In: the service and, if Appointments is active and whoever archives sees appointments, how many pending or
confirmed appointments use it from now on.
Out: the service out of the offer, not erased (`service.service.archived`): it stops showing in the
agenda, at the till, on the Online booking page and in the line picker of a voucher. The appointments
already booked, the vouchers that include it and the assigned professionals do not change.
If it fails: in the confirmation, the reason (for example, "That service does not exist in this
business."). Archiving one already archived changes nothing. The appointments notice is advice: it never
stops the archiving, and if Appointments does not answer the confirmation shows without that line.
Involved: APPOINTMENT-F01, APPOINTMENT-F26

### SERVICE-F05 See and restore the archived services
Status: done
Actor: manager
Screen: Services
Steps:
1. In **Filters**, choose **Archived** in Status and tap **Apply**: the table shows only the archived ones.
2. In the row tap **Restore** (it does not ask to confirm).
3. The service comes back to the list as before, with its name, price, duration and category.
In: the archived services.
Out: the service on offer and bookable again (`service.service.restored`).
If it fails: above the table, "Could not restore the service" or "That service does not exist in this
business.". Restoring one already on offer changes nothing. In the archived view the row does not offer
Edit or Archive and tapping it opens nothing.
Involved: SERVICE-F04

### SERVICE-F06 Add many services in one go
Status: done (assistant and API; there is no importer on screen)
Actor: manager, assistant
Screen: none
Steps:
1. Ask the assistant to create a list of services (up to 500), each with a name, a price, a duration
   and, if you want, a tax category and a category.
2. The assistant answers how many were created.
In: the list of services.
Out: the services, all or none, each with its notice (`service.service.created`). What a line does not
say takes the Settings, as the single add does.
If it fails: a badly formed line, or one with a category or a tax category that do not exist, refuses the
whole batch before creating anything, with the reason of each line in its field (for example, the price
of the fourth line).
Involved: SERVICE-F01, SERVICE-F11

### SERVICE-F07 Create and edit categories
Status: done
Actor: manager, assistant
Screen: Categories
Steps:
1. In **Categories** tap **New category**.
2. Type the Name and, if you want, choose the Parent category and an Order.
3. Tap **Create category**. To change it, tap the row or its **Edit** ("Editing category —
   <name>"), change what is needed and tap **Save changes**.
In: the live categories of the business.
Out: the category (`service.category.created`, `service.category.updated`), which shows in the Category
field of the service form and in the filter of the Category column. The lists and the till sort them by
Order and name.
If it fails: a name another live category already has (ignoring case and extra spaces) shows below the
field: "There is already a category with that name. Pick another name.". A category cannot be its own
parent nor hang from one of its children: "A category cannot hang from itself or from one of its
subcategories.". A deleted parent: "That parent category is not available: it does not exist in this
business or it has been deleted.".
Involved: SERVICE-F01, SERVICE-F08

### SERVICE-F08 Delete a category
Status: done
Actor: owner, administrator
Screen: Categories
Steps:
1. In the category's row tap **Delete**.
2. Read "Delete category" and, if it has services, how many will be left without a category.
3. Tap **Delete** (or **Cancel**). The row disappears.
In: the category and how many services on offer it has.
Out: the category deleted, not erased (`service.category.deleted`); its name becomes free. Its services
are left **without a category** and its subcategories move to hang from its parent (or become roots).
If it fails: in the confirmation, the reason (for example, "That category does not exist in this
business.").
Involved: SERVICE-F07, SERVICE-F02

### SERVICE-F09 Sell a service at the till
Status: done (Sales does it, SALE-F38)
Actor: employee
Screen: Sales: Sell
Steps:
1. In the till's strip of categories, **Services** shows each service on offer with its price and its
   duration (they also show in the search).
2. A **Not configured** service shows with the mark "VAT missing" and is not sold.
3. A service that is not at a fixed price asks for the amount, with its price as a suggestion.
In: the services on offer, their pricing and their tax category.
Out: the sale line with the service; Services records nothing for selling a single service.
If it fails: Sales says it (SALE-F38).
Involved: SALE-F01, SALE-F38

### SERVICE-F10 Give the catalogue to Appointments, Sales, Online booking and Price Lists
Status: done
Actor: system, assistant
Screen: none
Steps:
1. Whoever books (the Appointments agenda and the Online booking page), charges (the Sales till) or sets
   prices (Price Lists) does not open Services: they read its list of services on offer or one service.
2. The list brings only the services on offer, with name, pricing, price, minimum and maximum, duration,
   buffer, whether it is bookable, its category and its tax category (and whether it lacks one); also
   the ones that have no tax category yet, marked.
In: the catalogue.
Out: nothing; Services does not keep who reads it.
If it fails: each reader decides.
Involved: APPOINTMENT-F01, SALE-F01, ONLINE_BOOKING-F01, ONLINE_BOOKING-F07, PRICING-F07,
WHATSAPP_INBOX-F21

### SERVICE-F11 Change the Services settings
Status: done
Actor: owner, administrator
Screen: Services settings
Steps:
1. Open **Services → Settings**.
2. Change the fields and tap **Save**.
3. "Settings saved." shows.
In: the saved settings (or the factory ones).
Out: the settings (`service.settings.updated`). The duration, the buffer (before and after), the online
booking and the default tax category are taken by every new service that does not give them (form,
assistant, API and add in one go); the form brings the default tax category chosen.
"Show prices" and "Show duration" are used by the Online booking page: without them it does not show the
price or the duration of each service.
If it fails: "The settings could not be saved." and the reason below the field (a duration of 0, a tax
category that does not exist).
Involved: SERVICE-F01, SERVICE-F06, ONLINE_BOOKING-F01

### SERVICE-F12 Create a voucher
Status: done
Actor: manager, assistant
Screen: Packages
Steps:
1. Tap **New package**.
2. Type the Name ("5 haircuts voucher"). Choose the Discount type and its value, and a Closed price if
   you want one.
3. Set the Validity (days), which counts from the purchase (empty = never expires), and the **Uses**: the
   sessions the voucher gives in total (empty = unlimited).
4. In "Services included" choose each Service (the ones on offer) and its Sessions; **Add service** adds
   another row and "Remove line" removes it.
5. Tap **Create package**: it shows in the table as **Active** with its number of lines.
In: the services on offer.
Out: the voucher in the catalogue (`service.package.created`). When it is spent, any service of its lines
uses up one of its "Uses".
If it fails: with no service at all, "Add at least one service: a package with no lines cannot be
redeemed."; a repeated service, an archived one or one that does not exist; an unreadable or negative
amount, below its field; a name another live voucher already has, "There is already a package with that
name. Pick another name.".
Involved: SERVICE-F14, SERVICE-F22

### SERVICE-F13 Edit or delete a voucher
Status: done
Actor: manager (edit), owner and administrator (delete)
Screen: Packages
Steps:
1. Tap the row or its **Edit** ("Editing package — <name>"): change Name, Discount, Closed price,
   Validity or Uses; the lines are not changed. Tap **Save changes**.
2. To take it off the catalogue tap **Delete** and confirm.
3. To see what was sold of a deleted voucher, in **Filters** choose **Deleted** in Status.
In: the voucher of the catalogue.
Out: when editing, the changed voucher (`service.package.updated`); "Uses" and "Validity" apply to the
future sales, the vouchers already sold keep what was sold; the new name also shows on them.
When deleting (`service.package.deleted`), the voucher leaves the catalogue and can no longer be granted;
the ones already sold are still spent, adjusted and voided the same. A deleted voucher nobody bought shows
in no view.
If it fails: when saving, inside the form, the reason ("That package does not exist in this business." if
it was deleted in the meantime) or those of SERVICE-F12 below their field; when deleting, the reason in
the confirmation.
Involved: SERVICE-F12, SERVICE-F16

### SERVICE-F14 Sell a voucher to a customer
Status: done for the grant (assistant and API); not the sale at the till (see "What is left out")
Actor: employee, manager, assistant
Screen: assistant
Steps:
1. Ask the assistant to grant the voucher to the customer (by her name or her phone), with the amount
   charged and the sale if there are any.
2. The voucher shows in **Sold vouchers** of that voucher (SERVICE-F16).
In: the voucher of the catalogue, live and active, and the customer (Customers).
Out: a sold voucher with the owner, the date, the amount and the "Uses" and the "Validity" of the
catalogue frozen; the expiry counts from that moment (`service.grant.granted`). No tax document comes
out: the sale of the voucher issues it.
If it fails: "Pick the customer this voucher belongs to…" if it is not said; "That package does not exist
in this business." if the voucher was deleted or is deactivated; a purchase date in the future, "A voucher
cannot be bought in the future." (extending a voucher is **Adjust**, SERVICE-F18), and one without a time
zone, asking for it; a customer name that fits several, the list to choose from.
Involved: CUSTOMER-F01

### SERVICE-F15 Look up a customer's vouchers
Status: done (assistant and API)
Actor: employee, manager, assistant
Screen: assistant
Steps:
1. Ask the assistant about the customer's vouchers, by her name or her phone.
2. It answers one row per purchase, with the voucher, the date, what was paid, the sessions used and the
   ones left, when it expires and whether it already expired or was voided; also those of a card merged
   into hers.
In: the customer (Customers) and her sold vouchers.
Out: nothing; read only.
If it fails: if the name fits several customers, the assistant says which and asks to choose; if it does
not find her, it says so.
Involved: SERVICE-F14, SERVICE-F28, CUSTOMER-F01

### SERVICE-F16 See who has bought a voucher
Status: done
Actor: employee, manager
Screen: Packages
Steps:
1. In the voucher's row tap **Sold vouchers** (for a deleted one, with Status on **Deleted**).
2. One row per purchase shows, the most recent first (see "Screens").
3. **Load more** brings the next page; **Close** goes back to the table.
In: the purchases of that voucher and the name of each customer (Customers); for a deleted card, its
identifier.
Out: nothing; read only. **Adjust** and **Void** show where they apply and for whoever may.
If it fails: empty, "Nobody has bought this voucher yet."; if it cannot be read, "Could not load the sold
vouchers" with the reason.
Involved: SERVICE-F17, SERVICE-F18

### SERVICE-F17 Void a voucher sold by mistake
Status: done
Actor: manager, assistant
Screen: Packages
Steps:
1. In **Sold vouchers**, on the wrong purchase tap **Void** (it only shows if no session has been
   spent).
2. Read "Void this voucher?": "The voucher of customer {customer} ({amount}) stops being usable and stays
   in the list as voided. The money is not given back here: if it was paid, refund the sale from Sales
   with a return.".
3. Type the Reason (required) and tap **Void**.
In: the purchase and the reason.
Out: the voucher can no longer be spent and stays as a trace, with who, when and the reason
(`service.grant.voided`). It moves no money and issues no document.
If it fails: "That voucher was already used: it cannot be voided.", "That voucher was already voided." or
"Say why this voucher is being voided: the reason stays on its record.". If another till spends a session
at the same time, the void waits and gets the real reason.
Involved: SERVICE-F16, SALE-F32

### SERVICE-F18 Give sessions, extend the expiry or correct the balance
Status: done
Actor: manager, assistant
Screen: Packages
Steps:
1. In **Sold vouchers** tap **Adjust** on a live purchase with a session limit or an expiry.
2. Choose **Add sessions** or **Remove sessions** and how many (up to 100; removing, up to the ones it has
   left), and/or "Days to extend" (up to 366).
3. Type the Reason and check "After the adjustment: {remaining} session(s) left · expires {when}".
4. Tap **Adjust**.
In: the purchase, the quantities and the reason.
Out: a separate movement with who, when, how much and why (`service.grant.adjusted`), which shows in
**Movements** as **Courtesy** or **Correction**; the purchase is not rewritten. It revives an expired or
used-up voucher.
If it fails: "Say why this voucher is being adjusted…", "Add or remove at least one session, or add at
least one day.", "You cannot take away more sessions than the customer has left.", "That voucher has no
session limit…", "That voucher never expires…" or "That voucher was already voided.".
Involved: SERVICE-F16, SERVICE-F20

### SERVICE-F19 See a voucher's movements
Status: done
Actor: employee, manager
Screen: Packages
Steps:
1. In the voucher's row tap **Movements**.
2. Each delivered session and each adjustment shows, the most recent first (see "Screens"); **Load
   more** brings the next ones, each movement only once even if several carry the same time.
In: the sessions and the adjustments of that voucher.
Out: nothing; read only.
If it fails: empty, "This voucher has not been used yet."; if it cannot be read, "Could not load the
movements" with the reason.
Involved: SERVICE-F18, SERVICE-F21, SERVICE-F22

### SERVICE-F20 A voucher expires
Status: done
Actor: system
Screen: none
Steps:
1. A voucher with "Validity (days)" expires that number of days after its purchase, plus the days given
   with **Adjust**.
2. From that moment spending it is refused with "This voucher has expired."; its unused sessions stay
   and **Adjust** revives it.
In: the purchase date, the validity sold and the days given.
Out: nothing is written when it expires.
If it fails: nothing fails when it expires; spending it afterwards is refused with "This voucher has
expired.".
Involved: SERVICE-F18, SERVICE-F21

### SERVICE-F21 Spend a session outside the checkout
Status: done (assistant and API)
Actor: employee, manager, assistant
Screen: assistant
Steps:
1. If you want, ask the assistant first whether a session of that voucher could be spent and why not.
2. Ask the assistant to spend a session of a voucher the customer bought, and if you want say which
   service was done and link it to the appointment or the sale.
In: the purchase of the voucher; the service, the appointment and the sale, as a reference.
Out: a **Delivered** session at once (`service.grant.redeemed`), which counts against the "Uses". It
issues no tax document.
If it fails: "This voucher was voided: it can no longer be used.", "This voucher has no sessions left.",
"This voucher has expired.", "This voucher does not cover that service. A voucher of haircuts pays for
haircuts, not for the shampoo." or "That voucher sale does not exist in this business.". Two tills that
spend the last session at the same time go in line and the second one gets the real reason.
Involved: SERVICE-F19, SERVICE-F20

### SERVICE-F22 Pay a line with a voucher
Status: done (with Sales, SALE-F27)
Actor: employee, manager
Screen: Sales: Charge
Steps:
1. With the customer assigned to the check, open the checkout. In "Lines paid another way", each line of
   a service shows "Pay this line with a voucher" with the vouchers of that customer that cover that
   service, have sessions and have not expired (also those of a voucher deleted from the catalogue and
   those of a card merged into hers). A line of several units is split first ("Split into {n} lines").
2. The voucher that is spent first comes chosen, with the why: first one with counted sessions before an
   unlimited one, then the one that expires first, the one already started, the one with fewer sessions
   left and the one bought first. With two or more it says "{count} valid vouchers". Tap another card to
   spend another one.
3. Check "{before} sessions left · {after} after this one" and tap **Spend one session**.
4. "{name}: session spent. {after} left." shows and the line goes to 0.00 € with "Already paid ·
   {name}"; the amount of the checkout goes down. **Undo** gives it back while the sale is not charged.
5. Charge the rest with its method (SERVICE-F24). Closing the checkout, parking the check or reloading
   the screen changes nothing: the mark lives on the check's line, so on coming back the line is still
   paid with the voucher and the slot shows the session spent with **Undo**.
In: the customer, the check, the line and its service (Sales); the customer's vouchers (Services).
Out: a **Held** session for that line for one day (`service.session.reserved`), which counts as used and
can no longer be spent on another line; the check's line, paid with the voucher. It issues no tax
document: the voucher was declared when it was sold.
If it fails: if the vouchers cannot be read, "The customer's vouchers could not be loaded. Try again
before charging the full price." with **Retry**, never "has no vouchers". With no vouchers: "This
customer has no voucher that covers this service.". When spending: "This voucher has no sessions left.",
"This voucher has expired.", "This voucher was voided: it can no longer be used." or "This voucher does
not cover that service…". If another till spends the last session at the same time, the second one waits
and gets the real reason. **Undo** after charging: "That voucher session can no longer be released: the
sale is charged. Giving it back is a refund.". Without Services active, or without permission to spend
sessions, the slot does not show.
Involved: SALE-F27, CUSTOMER-F17

### SERVICE-F23 Release the session if the line or the check goes away
Status: done
Actor: employee, manager
Screen: Sales: Sell, Charge
Steps:
1. Whoever charges taps **Undo** in the slot, removes from the check the line paid with the voucher,
   voids it if it was already sent to the kitchen or deletes the whole check.
2. Sales releases the held session of that line in the same operation.
3. In **Movements** the session shows as **Released**.
In: the held session of the line (the check's line keeps it).
Out: the session back in the voucher at once (`service.session.released`). Releasing a session already
released or expired changes nothing. Splitting or joining checks does not touch it: the session goes with
its line.
If it fails: a session already charged is not released (see above). If Services is not active at that
moment, the line is removed all the same and the session comes back on its own after one day
(SERVICE-F25).
Involved: SALE-F18, SALE-F20, SALE-F27

### SERVICE-F24 Mark the sessions as spent when charging
Status: done (not granting the vouchers sold on the receipt: see "What is left out")
Actor: employee, manager
Screen: Sales: Charge
Steps:
1. A check (whole or some lines) with lines paid with a voucher is charged.
2. In the same operation as the charge, Sales marks as **Delivered** the session of each line paid with a
   voucher that goes into that charge, linked to the sale. The lines that do not go into this charge keep
   their held session for when they are charged (SALE-F22).
3. From that moment the session is no longer released: it only comes back with a refund (SERVICE-F26) or
   by voiding the sale (SERVICE-F27).
In: the held sessions of the charged lines, the sale and its customer (Sales).
Out: the sessions spent for good and linked to the sale (`service.session.settled`). Repeating the charge
with the same key does not spend twice.
If it fails: nothing is charged and the check stays the same if a session is no longer held ("The session
held from «{name}» is no longer held (its day passed or it was released). Take the voucher off the line
and apply it again."), or if the sale is not the voucher owner's ("The voucher «{name}» belongs to another
customer: charge the sale to its owner or take the voucher off the line."). If Services is not active in
the business, it is not charged either.
Involved: SALE-F01, SALE-F22, SALE-F27

### SERVICE-F25 The held session nobody charges comes back on its own
Status: done (on reading and with the hourly task)
Actor: system
Screen: none
Steps:
1. A session held in a checkout has one day to be charged (for example, a check parked and forgotten).
2. After that deadline it stops counting in the voucher's balance at once; the hourly task marks it as
   **Expired** in **Movements**.
3. If someone goes back to that check, the line is still marked, but charging it is refused
   (SERVICE-F24): the voucher is undone and applied again.
In: the held sessions not charged and their deadline.
Out: the session back in the voucher (`service.session.expired`, one per session, when the task marks
them).
If it fails: if the task does not run, the session comes back all the same once the deadline passes: the
balance does not count it.
Involved: SALE-F17

### SERVICE-F26 Give the session back when the sale is refunded
Status: done (with Sales, SALE-F32)
Actor: manager
Screen: Sales: Refund
Steps:
1. In **Sales**, tap **Refund** on the sale (also on one paid entirely with a voucher, at 0.00 €).
2. In "What goes back", each line paid with a voucher says "Already paid · {name}". Tick it: "The
   session goes back to {name}.".
3. Tap the refund button: the session alone can be given back, with no money.
In: the sessions spent in that sale (each line of the sale keeps them).
Out: the session back in the voucher, with who, when and the refund document
(`service.session.returned`); in **Movements**, **Given back**. It moves no money and issues no
document; if the voucher has already expired, the session is recorded but cannot be spent until it is
extended (SERVICE-F18). The same refund repeated gives back a single session.
If it fails: "That session was already given back by another refund.". If Services is not active in the
business, the whole refund is refused.
Involved: SALE-F31, SALE-F32

### SERVICE-F27 Give the session back when the sale is voided
Status: done (not voiding the vouchers sold in it: see "What is left out")
Actor: manager
Screen: Sales: Void sale
Steps:
1. A manager voids a charged sale in Sales (SALE-F30).
2. In the same operation, each session spent in that sale goes back to its voucher, even if it has
   expired.
3. In **Movements** each one shows as **Given back**, with who voided it, the time and the reason.
In: the voided sale, who and the reason; the sessions spent in that sale.
Out: the sessions back in their voucher (`service.session.returned`). It moves no money and issues no tax
document.
If it fails: repeating the void does not give back twice. If Services is not active in the business, the
sale is not voided and the window says so.
Involved: SALE-F30

### SERVICE-F28 Merge two cards: the vouchers move to the one that stays
Status: done
Actor: system
Screen: none
Steps:
1. In Customers someone merges two cards of the same person.
2. At once, the vouchers of the absorbed card already show among those of the one that stays
   (SERVICE-F15) and the checkout accepts them: none is left invisible or unspendable, and none shows
   twice.
3. Within a few seconds, Services moves to the card that stays every voucher of the absorbed one (live and
   voided), with their sessions and their adjustments.
In: the card that stays and the absorbed one (Customers announces it: `customer.customer.merged`).
Out: the vouchers pointing to the card that stays (`service.grant.reassigned`); if two purchases are of
the same voucher, two stay, each with its balance and its expiry.
If it fails: repeating the notice changes nothing.
Involved: CUSTOMER-F13, SERVICE-F15, SERVICE-F22

### SERVICE-F29 Delete or anonymise a card: its vouchers are left with no customer
Status: done
Actor: system
Screen: none
Steps:
1. In Customers an administrator deletes a card or erases its personal data.
2. Its live vouchers go to **Vouchers with no customer** (SERVICE-F30) with the date it was deleted.
3. If its personal data was erased (GDPR), Services empties the free texts of its vouchers: the note of
   the purchase, the reason of a void, the reason of each adjustment and the note and the return reason
   of each session.
In: the deleted or anonymised card (Customers; when anonymising it announces `customer.customer.erased`).
Out: the voucher keeps the reference of the card, which is what matches it with the sale that paid for
it; sessions, amounts and movements do not change. When anonymising, the free texts emptied
(`service.grant.erased`). The voided ones do not show in the list.
If it fails: repeating the notice changes nothing.
Involved: CUSTOMER-F07, CUSTOMER-F16

### SERVICE-F30 Rescue the vouchers with no customer
Status: done (the list; a voucher is not moved to another card)
Actor: manager
Screen: Packages
Steps:
1. Tap **Vouchers with no customer**.
2. Each voucher whose card was deleted or anonymised shows, the most recent first (see "Screens"). There
   is no name, email or phone.
3. To give the money back, find the sale in **Sales** and make a refund; to void the voucher if it was not
   used, open it from **Sold vouchers** of that voucher, where it shows with its reference.
In: the live vouchers of deleted or anonymised cards.
Out: nothing; read only.
If it fails: empty, "No voucher has lost its customer."; if it cannot be read, "The vouchers with no
customer could not be loaded.".
Involved: SERVICE-F29, SERVICE-F17

### SERVICE-F31 Assign a professional to a service
Status: done
Actor: manager, assistant
Screen: Services (Editing service)
Steps:
1. Open the service: in "Professionals who perform it" the list shows, or "Nobody assigned yet: the whole
   bookable team may perform it.".
2. In "Add professional…" choose someone from Staff (the ones who do not have it yet show) and, if you
   want, their own "Minutes (optional)" and their own price, "Price (<currency>, optional)" (in the business's
   currency: "Price (EUR, optional)" in Spain; "Price (optional)" while the business has not answered).
3. Tap **Assign**.
In: the service and the card of the professional (Staff).
Out: the assignment, active and not main (`service.assignment.assigned`). Appointments reads it to filter
the professionals of a service and to take their own duration and price, and Sales charges that own
price (SALE-F38). Assigning the same person again (assistant or API) changes their minutes and their
price; their main service only changes if it is said.
If it fails: inside the section, "That staff member does not exist in this business.", a name that fits
several (the list to choose from) or the amount unreadable or negative. While the list arrives it shows
"Loading…"; if it cannot be read, "The professionals could not be loaded." with the reason and
"Retry", never "Nobody assigned yet".
Involved: STAFF-F01, SALE-F38

### SERVICE-F32 Change or remove a professional from a service
Status: done
Actor: manager, assistant
Screen: Services (Editing service)
Steps:
1. In "Professionals who perform it", change the "Minutes (optional)" or the "Price (<currency>, optional)" of
   a person and tap **Save**.
2. Tap "Make it their main service": "Main service" shows (one per person, the previous one stops being
   it).
3. Turn off "Performs it" so that they stop doing it without removing them, or tap "Remove".
4. If a person leaves in Staff, they stop showing at once in "Professionals who perform it"
   and in who can perform it (SERVICE-F33), and within a few seconds Services removes them on its own from
   every service they performed.
In: the assignment.
Out: the change (`service.assignment.updated`, `service.assignment.removed`). A person leaving in Staff
removes them from every service they performed.
If it fails: "That assignment does not exist in this business.".
Involved: SERVICE-F31, SERVICE-F33, STAFF-F06

### SERVICE-F33 Know who can perform a service
Status: done
Actor: system, assistant
Screen: none
Steps:
1. Whoever books asks which professionals can perform a service.
2. Services answers with the **Active** and **Bookable** people with an active assignment for that
   service, with their own duration and price, the ones whose main service it is first and then by name.
In: the service.
Out: the list, read only. Empty means "nobody declared" or "whoever has it is not active and bookable":
the rule "then the whole bookable team does it" belongs to Appointments.
If it fails: a service that does not exist, "That service does not exist in this business.".
Involved: SERVICE-F31, APPOINTMENT-F01

## Services: what goes in and what comes out

Everything can be asked for through the screens, the assistant (by voice or by text, with the session of
whoever speaks) and the API, with the same rules and the same permissions. A service, a category or a
voucher are named by their id or by their name; a professional, by their name; a customer, by her name or
her phone. If a name fits several, it says which and asks to choose (409
`service.service_ambiguous`, `service.category_ambiguous`, `service.package_ambiguous`,
`staff.ambiguous_member`, `customer.customer_ambiguous`).

### What it offers: queries (they read and change nothing)

| What it gives | Who may | Flows | Service |
|---|---|---|---|
| The services, with search, filters and sorting, in pages (up to 100) | view services | F01–F05 | `service.service.list` |
| A whole service | view services | F02, F10 | `service.service.get` |
| The catalogue to sell and book: the services on offer | view services | F09, F10 | `service.service.list_for_sale` |
| How many services are on offer and how many can be charged (the "Your service catalogue" step of the Home) | view services | F01 | `service.catalog.status` |
| The categories, with the services on offer of each | view categories | F07, F08 | `service.category.list` |
| A category | view categories | F07 | `service.category.get` |
| The settings | view services | F11 | `service.settings.get` |
| The professionals of a service, or the services of a professional | view services | F31, F32 | `service.assignment.list` |
| Who can perform a service | view services | F33 | `service.assignment.eligible` |
| The vouchers of the catalogue (and the deleted ones someone bought) | view vouchers | F12, F13 | `service.package.list` |
| A voucher with its lines | view vouchers | F13 | `service.package.get` |
| The sold vouchers, of a voucher or of a customer, with their balance | view voucher balances | F15, F16 | `service.grant.list` |
| The vouchers with no customer | view vouchers with no customer | F30 | `service.grant.list_orphans` |
| Whether a sold voucher can be voided and why not | void vouchers | F17 | `service.grant.void_check` |
| What can be adjusted on a sold voucher | adjust vouchers | F18 | `service.grant.adjust_check` |
| Whether a session can be spent and why not | spend sessions | F21 | `service.grant.redeem_check` |
| The customer's vouchers that can pay for a service, the one spent first and why | spend sessions | F22 | `service.grant.tender_options` |
| A voucher's movements | view voucher balances | F19 | `service.movement.list` |

All of them, except the checks, can be followed live.

### What it offers: actions (they change data)

| What it does | Who may | Flows | Service |
|---|---|---|---|
| Adds a service | add services | F01, F03 | `service.service.create` |
| Adds up to 500 services in one go | edit services | F06 | `service.service.bulk_create` |
| Changes a service (only what is sent) | edit services | F02, F03 | `service.service.update` |
| Archives a service | archive services | F04 | `service.service.archive` |
| Restores an archived service | edit services | F05 | `service.service.restore` |
| Creates a category | create categories | F07 | `service.category.create` |
| Changes a category (only what is sent) | edit categories | F07 | `service.category.update` |
| Deletes a category | delete categories | F08 | `service.category.delete` |
| Saves the settings (only what is sent) | settings | F11 | `service.settings.update` |
| Assigns a professional to a service (or changes their assignment) | edit services | F31 | `service.assignment.assign` |
| Changes an assignment | edit services | F32 | `service.assignment.update` |
| Removes an assignment | edit services | F32 | `service.assignment.remove` |
| Creates a voucher with its lines | create vouchers | F12 | `service.package.create` |
| Changes a voucher (only what is sent; not the lines) | edit vouchers | F13 | `service.package.update` |
| Deletes a voucher from the catalogue | delete vouchers | F13 | `service.package.delete` |
| Grants a voucher to a customer | grant vouchers | F14 | `service.grant.create` |
| Voids an unused sold voucher | void vouchers | F17 | `service.grant.void` |
| Gives or takes sessions, or extends the expiry | adjust vouchers | F18 | `service.grant.adjust` |
| Spends a session | spend sessions | F21 | `service.grant.redeem` |
| Holds a session of a voucher for a line of the check (Sales calls it) | spend sessions | F22 | `service.session.hold` |
| Releases a held session (Sales calls it) | spend sessions | F23 | `service.session.release` |
| Marks as spent the held sessions of a charged sale (Sales calls it) | spend sessions | F24 | `service.session.settle` |
| Marks the overdue holds as expired (hourly task) | system | F25 | `service.session.expire` |
| Gives back to the voucher sessions spent in a voided or refunded sale (Sales calls it) | give sessions back | F26, F27 | `service.session.return` |

### What it announces

| Notice | When | What it carries | Service |
|---|---|---|---|
| New service | Add (one per service in the add in one go) | Which (`id`) and its name | `service.service.created` |
| Service changed | Edit with some change | Which (`id`) | `service.service.updated` |
| Service archived | Archive | Which (`id`) | `service.service.archived` |
| Service restored | Restore | Which (`id`) | `service.service.restored` |
| Category new / changed / deleted | Create, edit, delete | Which (`id`) | `service.category.created`, `.updated`, `.deleted` |
| Settings changed | Save with some change | Nothing | `service.settings.updated` |
| Professional assigned / changed / removed | Assign, change, remove (also when someone leaves) | The assignment, the service and the professional | `service.assignment.assigned`, `.updated`, `.removed` |
| Voucher new / changed / deleted | Create, edit, delete | Which (`id`) | `service.package.created`, `.updated`, `.deleted` |
| Voucher granted | Grant | The purchase, the voucher and the customer | `service.grant.granted` |
| Voucher voided | Void | The purchase, the voucher and the customer, without the reason | `service.grant.voided` |
| Voucher adjusted | Adjust | The purchase and the quantities, without the reason | `service.grant.adjusted` |
| Session spent | Spend | The purchase, the session and the service | `service.grant.redeemed` |
| Session held / released / expired | Hold in the checkout, release it, the hourly task | The session and the purchase | `service.session.reserved`, `.released`, `.expired` |
| Session delivered when charging | Charge the sale | The session, the purchase and the sale | `service.session.settled` |
| Session given back | Void or refund the sale | The session, the purchase and the document, without the reason | `service.session.returned` |
| Vouchers reassigned | Merge two cards | The card that stays and the absorbed one | `service.grant.reassigned` |
| Texts of the vouchers emptied | Anonymise a card with vouchers with text | The card | `service.grant.erased` |

### What it reacts to and what it needs from other apps

| Notice of another app | What Services does | Flows |
|---|---|---|
| `staff.member.terminated` (Staff) | Removes that person from every service | F32 |
| `customer.customer.merged` (Customers) | Moves the vouchers of the absorbed card to the one that stays | F28 |
| `customer.customer.erased` (Customers) | Empties the free texts of the vouchers of that card (GDPR) | F29 |

From Taxes it reads the tax categories; from Staff, the cards (name, whether active and bookable); from
Customers, the owner's name and whether her card was deleted.

### Contract with Sales

Sales does not depend on Services (Services is not in its `requires`): it uses its operations by name,
with the session of whoever sells, as it does with Inventory.

- **Selling a service (F09)**: `service.service.list_for_sale` (search, `category_id`, pages of up to
  100) gives per service `id`, `name`, `pricing_type`, `price`, `min_price`, `max_price`,
  `duration_minutes`, `category_id`, `category_name`, `tax_category_id`, `tax_category_key` and
  `needs_tax_setup` (no live tax category: it is not sold). `service.service.get` gives one, also
  archived. When charging, the tax category of the line is the one of `tax_category_key`. With the
  line's professional, a fixed-price service is charged at her own price if her active assignment has
  one (`service.assignment.list` with `service_id` and `member_id`).
- **The voucher in the checkout and in the refund (F22–F27)**: Sales calls by name, with the session of
  whoever charges (each operation checks their permission and the active app), and **in the same
  transaction** as its own write, without waiting for any notice:
  - when paying a line with a voucher, `service.session.hold` (`grant_id`, `service_id`,
    `order_line_id`) and it keeps on the line the session it gets back;
  - when undoing it, removing the line, voiding it or deleting the check, `service.session.release` (`id`);
  - when charging, `service.session.settle` (`ids` of the charged lines, `sale_id`, `customer_id` of the
    sale);
  - when voiding the sale, `service.session.return` with all its sessions (`reference` = the sale) and,
    when refunding it, with those of the lines that go back (`reference` = the refund).
  To paint the slot, the checkout reads `service.grant.tender_options` (`customer_id`, `service_id`).
  Services keeps the sale and the check's line as opaque identifiers (`sale_id`,
  `order_line_id`): Sales is not a requirement of Services nor Services of Sales.

### Who can do what

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| View services, settings and assigned professionals | yes | yes | yes | yes | `service.view_service` |
| Add services | yes | yes | yes | yes | `service.add_service` |
| Edit and restore services, add in one go and assign professionals | yes | yes | yes | no | `service.change_service` |
| Archive services | yes | yes | no | no | `service.delete_service` |
| View categories | yes | yes | yes | yes | `service.view_category` |
| Create categories | yes | yes | yes | no | `service.add_category` |
| Edit categories | yes | yes | yes | no | `service.change_category` |
| Delete categories | yes | yes | no | no | `service.delete_category` |
| View vouchers | yes | yes | yes | yes | `service.view_package` |
| Create vouchers | yes | yes | yes | no | `service.add_package` |
| Edit vouchers | yes | yes | yes | no | `service.change_package` |
| Delete vouchers | yes | yes | no | no | `service.delete_package` |
| Grant vouchers | yes | yes | yes | yes | `service.grant_package` |
| Spend sessions | yes | yes | yes | yes | `service.redeem_package` |
| View sold vouchers, balances and movements | yes | yes | yes | yes | `service.view_package_balance` |
| View vouchers with no customer | yes | yes | yes | no | `service.view_orphan_grant` |
| Void sold vouchers | yes | yes | yes | no | `service.void_grant` |
| Adjust sold vouchers | yes | yes | yes | no | `service.adjust_grant` |
| Give sessions back when voiding or refunding a sale | yes | yes | yes | no | `service.return_session` |
| Settings | yes | yes | no | no | `service.manage_settings` |

The roles arrive from the SaaS with a prefix (`hub_owner`, `hub_admin`, `hub_manager`, `hub_employee`); the
cashier of the current product is an employee: what they had (view, spend and grant) the employee has.
