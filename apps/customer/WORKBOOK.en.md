<!-- generated from WORKBOOK.md sha256:ed840a901ff341f3a14d4b4245851d2f0bd4544c5c94005c7afa55c504af1199 -->

## What it is for and who it is for

Customers is the business's **file of people and companies** and the owner of their personal data: the
card with the contact and tax details, its groups, tags and own fields, its notes and its activity, its
consent to receive advertising through each channel and what the person has bought.

- In the **hair salon** it is the client of the agenda: Appointments hangs her visits from the card and
  recognises her when she writes on WhatsApp.
- In the **restaurant** it is the guest who books or asks for an invoice: the till puts their card on the
  check and the invoice comes out with their tax details.

It is the app the others depend on most: the till asks it for the sale's customer and its tax copy,
Appointments and Reservations look them up by name or phone, WhatsApp recognises them by their number and
all of them learn when two cards are merged or a person's data is erased. Customers needs no other app.

Who uses it:

- The **owner** and the **administrator**: everything, also deleting cards and erasing personal data.
- The **manager**: edits cards, merges duplicates, creates and changes groups, tags and fields (and
  deletes fields), exports and notes in the activity what other apps bring.
- The **employee** (also at the till): looks up, adds, edits the card, imports, adds notes, assigns
  groups and tags, records consent and puts the customer on the sale. With a manager's PIN, on their
  own device, merges duplicates and creates or changes groups, tags and fields (BASE-F84).
- The **customer** does not use these screens: their data comes in at the counter, at the till or
  through their WhatsApp.

## Reference adopted

ERPlora does not invent flows: it adopts the ones the market has already proven.

- **Phones in the international E.164 format** (ITU-T), with Google's **libphonenumber** rules: a number
  without prefix is read in the business's country, as the reference POS systems do; ERPlora today always
  reads it in Spain (CUSTOMER-F11, hub#527).
- **Adding a card** like Odoo, Shopify, Square, Toast, Lightspeed, Fresha and Holded: only the name is
  required; phone, email and tax ID in sight and the rest one tap away.
- **Merging duplicate cards** like Square, Shopify, Odoo, Fresha, Lightspeed and Mindbody: one card
  stays, fills its gaps from the other and each app re-points what is its own.
- **Customer at the till** like Square, Toast, Lightspeed, Shopify POS and Fresha: search by name or
  phone and "+ new customer" in two taps, without leaving the sale.
- **Consent per channel**, with the sentence stored word for word and withdrawing it as easy as giving
  it: GDPR arts. 7 and 17 and EDPB Guidelines 05/2020, like Shopify, Klaviyo, Mailchimp and HubSpot.
- **Erasing personal data** like Shopify's `customers/redact` notice and Odoo's privacy lookup: the
  person is erased and what the law requires to be kept (the sales) is kept.
- **Notes and activity in a single timeline**, like Odoo's "chatter" and Shopify's timeline.
- **Allergies and sensitivity test** in their own block of the card, in sight of whoever serves, like
  Fresha, Phorest, Timely, Vagaro, Zenoti, Mindbody, Shortcuts and Kitomba; and, being health data, only
  with the person's explicit permission (GDPR art. 9.2.a), which is withdrawn as easily as it is given,
  and withdrawing it erases them (arts. 7.3 and 17).
- **Permissions per action** like Shopify's staff permissions: view, manage, export, merge, delete and
  erase personal data are different permissions.

## Before you start

1. Turn on **Customers** on the business's apps page. It needs no other app. With **Sales & POS** the
   search appears at the till and purchases are recorded by themselves; with **Appointments**, the
   visit history on the card; with the **WhatsApp inbox**, recognition by phone.
2. The country assumed for a phone written without prefix is today **Spain**, even if the business has
   another country in Settings → Business: a phone from another country is written with its prefix
   (`+48…`) (CUSTOMER-F11).
3. If segmenting is needed, create the groups, the tags (CUSTOMER-F27, F28) and the business's own
   fields (CUSTOMER-F29). Mark as required only the essential ones: they are demanded every time the
   full card is saved (not when it is added).
4. Bring in the customers you already have with **Import CSV** (CUSTOMER-F08) or add them
   (CUSTOMER-F01).
5. Check at the till that the card shows in the search and that the sale is charged with it
   (CUSTOMER-F17).

⚠️ The business is the first part of the address (`a.localhost:8000` is business `a`). While the
businesses live in the shared database of the beginning, **they share the cards**; what is already kept
apart is the live notice. Each business gets its own database, and with it its cards, as the platform
gives it one.

## Screens

Customers opens from the **Customers** menu and has four tabs: **Customers**, **Groups**, **Tags** and
**Fields**. It has no settings tab.

### Customers
At the top, four figures: "Customers", "Active", "VIP" and "Revenue" (what the live cards have spent).
Below, the table: "Name", "Email", "Phone", "Stage" and "Spent"; search "Search name, phone or email…"
(it also searches tax ID and company); filters by stage, source, active and spent ("From / To", in the
business's currency); sort by any column; 50 per page. In the bar, **Add** and **Import CSV** for whoever
may manage cards, and **Export CSV** for whoever may export. Tapping a row opens the card.

### Customer card
The name and the buttons the profile allows: **Edit**, **Delete**, **Merge with…** and **Erase personal
data** (the employee sees **Merge with…**, which they do with a manager's PIN). Blocks: the details (Email, Phone, Tax ID, Company, Address, Stage, Source, Preferred channel,
Purchases, Spent, Last purchase, Active, internal notes, birthday, anniversary and custom fields);
"Groups" and "Tags" with checkboxes; "Marketing consent" with one line per channel and "Everything that
was decided"; "Add note"; "Activity"; "Purchases" (each sale with its amount and its status); and at the
end the blocks of other apps (today, the "Visit history" of Appointments).

### Groups
Table "Name", "Description", "Customers" (how many live cards it has), "Order" and "Active"; search
"Search group…" and an active filter; **Add** and **Edit** for whoever may configure and for the
employee (with a manager's PIN), **Delete** for the owner and the administrator.

### Tags
Table "Name", "Color", "Customers" and "Active"; search "Search tag…"; same actions as Groups.

### Fields
Table "Name", "Type", "Required" (Yes/No), "Order" and "Active"; search "Search field…"; filters by
type, required and active; **Add**, **Edit** and **Delete** for whoever may configure and for the
employee (with a manager's PIN).

### Till customer search
It lives inside the sale screen of **Sales & POS**: an "Assign customer" button (or the name of the
customer already chosen) opens a search by name, phone or email, with "+ New customer «…»" (name and
phone) and **Remove customer**. Customers paints it; Sales & POS keeps the slot.

### Till customer search · API
The Customers component `CustomerSearch` (Sales & POS imports it by its path, from the Customers
components).

```vue
<CustomerSearch v-model="venta.cliente" v-model:open="eligiendo" />
```

- `v-model` (`CustomerSnapshot | null`): the assigned customer, as a COPY of their tax card at that
  moment: `customer_id`, `customer_name`, `customer_tax_id`, `customer_address` ("street, postal code
  city, country", in the page's language) and `customer_country` (two-letter ISO code, or empty). `null` =
  no customer.
- `v-model:open` (optional): opens and closes the search; Sales & POS sets it to `true` when it requires
  a customer and there is none.
- The button says "Assign customer" or the customer's name. The search (an `ion-modal`) looks by name,
  phone or email among the first 20 cards, live, and tells apart "searching", "no results", "down" (with
  "Retry") and "no permission". On choosing it reads the whole card (`customer.customer.detail`); if it
  cannot be read, it does not assign and says so. "+ New customer «…»" (whoever manages cards) creates
  with name and phone; if live cards already have that phone, it shows them and asks "use or create a new
  one" (it never assigns without choosing; F12, F18). "Remove customer" returns `null`.
- It does not link the order: that belongs to Sales & POS, with `customer.order.link` and
  `customer.order.customer` (F19).
- While Sales & POS does not exist, it is seen and tested at `/customer/preview/customer-search` (only
  on the development server; never in the production build).

## States of each screen

| State | What the person sees |
|---|---|
| Loading | "Loading…" while the first result arrives. |
| Empty | "No customers." (or "No results" if there is a search or a filter); "No groups.", "No tags.", "No custom fields.", "No activity recorded." |
| Error | The reason with "Retry"; what was typed is kept. |
| Reconnecting | What is painted stays; a strip warns "Reconnecting…". |
| App inactive | "This app is not active in this business". |
| No permission | What they cannot do does not appear; if they come in by another door, "You do not have permission". |
| Card that is no longer there | "This customer is no longer available." (deleted, merged into another or with its data erased). |

## Flows

| ID | Flow | Status | Vertical |
|---|---|---|---|
| CUSTOMER-F01 | Add a card | done | common |
| CUSTOMER-F02 | Search and filter cards | done | common |
| CUSTOMER-F03 | Open a customer's card | done | common |
| CUSTOMER-F04 | Edit the card and its custom fields | done | common |
| CUSTOMER-F05 | Add a note to the card | done | common |
| CUSTOMER-F06 | Put groups and tags on a card | done | common |
| CUSTOMER-F07 | Delete a card | done | common |
| CUSTOMER-F08 | Import cards from a CSV | done | common |
| CUSTOMER-F09 | Export the cards to CSV | done | common |
| CUSTOMER-F10 | Recognise a person by their phone number | done | common |
| CUSTOMER-F11 | Store the phone in the international format (E.164) | done | common |
| CUSTOMER-F12 | Avoid duplicate cards of the same person | done | common |
| CUSTOMER-F13 | Merge two cards of the same person | done | common |
| CUSTOMER-F14 | Record the consent of a channel | done | common |
| CUSTOMER-F15 | Withdraw the consent of a channel | done | common |
| CUSTOMER-F16 | Erase a customer's personal data (GDPR) | done | common |
| CUSTOMER-F17 | Assign a customer to the sale at the till | done | common |
| CUSTOMER-F18 | Create a customer from the till's search | done | common |
| CUSTOMER-F19 | Link the customer to the open order | done | common |
| CUSTOMER-F20 | Add the purchase to the card when charging | done | common |
| CUSTOMER-F21 | Subtract a voided sale | done | common |
| CUSTOMER-F22 | Subtract a refund | done | common |
| CUSTOMER-F23 | See a customer's purchase history | done | common |
| CUSTOMER-F24 | See on the card what other apps know about the customer | done | common |
| CUSTOMER-F25 | Create the client without leaving the agenda | done | hair salon |
| CUSTOMER-F26 | Create the card of whoever asks for an appointment on WhatsApp | discarded — WhatsApp's automatic appointment answer is not offered yet (hub#514) | hair salon |
| CUSTOMER-F27 | Create, change and delete customer groups | done | common |
| CUSTOMER-F28 | Create, change and delete customer tags | done | common |
| CUSTOMER-F29 | Define the card's custom fields | done | common |
| CUSTOMER-F30 | Give a customer's card to other apps | done | common |
| CUSTOMER-F31 | See the customers' figures | done | common |
| CUSTOMER-F32 | Note allergies or the sensitivity test with their permission | done | hair salon |

"Done": server and pages with their tests (of the pages and end to end in Chrome).
"Discarded": it does not go into the app for now; the reason and its issue go in its "Status".

### CUSTOMER-F01 Add a card
Status: done
Actor: owner, administrator, manager, employee
Screen: Customers
Steps:
1. In **Customers** tap **Add**: the "New customer" dialog opens (the product's side panel, asked of
   `@erplora/ui` in `UI-REQUESTS.md`).
2. In sight: "Name", "Phone", "Email", "Tax ID" and "Company". Behind "More details": "Address", "City",
   "Postal code", "Country", "Photo" (its address), "Birthday", "Anniversary", "Source" ("Walk-in" to
   begin with), "Stage" ("Lead" to begin with), "Preferred channel" ("None" to begin with) and "Internal
   notes".
3. Only the name is required: until there is one, **Save** cannot be tapped.
4. Tap **Save**: the panel closes and the card appears in the list; the figures are recalculated.
In: what is typed. The country is stored with its two-letter code (`ES`, `FR`). The phone is stored in
the international format (`+34` and the digits together, CUSTOMER-F11); the email and the tax ID, without
the spaces at the ends.
Out: the new card, active and with no consent of any kind (CUSTOMER-F14), and the card-created notice
(`customer.customer.created`), which WhatsApp listens to so as to join to the card the conversations
that number already had.
If it fails: the reason shows under its field and what was typed is kept. A malformed email: "Enter a
valid email.". A phone that is not a number of its country: "This is not a valid phone number of its
country: check the digits or write it with its international prefix (+44…).". A country that does not
exist: "Choose a country from the list.". A date that does not exist in "Birthday" or "Anniversary" (a
31/02): "Enter a valid date.". Nothing is saved. Custom fields are not asked for when adding.
Involved: WHATSAPP_INBOX-F04

### CUSTOMER-F02 Search and filter cards
Status: done
Actor: everyone
Screen: Customers
Steps:
1. Type in the search. It searches at once in name, email, phone, tax ID and company, ignoring case and
   accents ("garcia" finds "García"). A term made only of digits and phone signs (with spaces, dashes or
   brackets, with `+` or `00` in front) is searched by its digits, without the `00` or the national zero,
   so the card is found however it is written.
2. With the filters: stage, source, active and spent by range ("From / To", in the business's currency,
   the one of its country in Settings → Business, with its decimals: the yen has none; with or without its
   symbol, "12,50 zł").
3. Sort by name, email, phone, stage, spent, last purchase or date added. To begin with, by name from A
   to Z, 50 per page (at most 100).
4. Tap a row to open its card (CUSTOMER-F03).
In: the text, the filters and the sort.
Out: nothing; read only. Cards that are deleted, merged into another or with their data erased do not
show; those marked as not active do.
If it fails: the table shows the error with "Retry". No results: "No customers.".
Involved: none

### CUSTOMER-F03 Open a customer's card
Status: done
Actor: everyone
Screen: Customer card
Steps:
1. From **Customers**, tap the row.
2. The card shows all its details (also internal notes, birthday, anniversary and custom fields, which
   in the current product were only seen when editing), its groups and tags, its consent per channel, the
   activity (newest first, 50 per page), its purchases and the blocks of other apps.
3. **← Back** returns to the list.
In: the card and, apart, its activity, its purchases and its consent history.
Out: nothing; read only. If another person changes it while it is open, the change is seen without
reloading.
If it fails: "This customer is no longer available." if it was deleted, merged into another or its data
was erased.
Involved: CUSTOMER-F24

### CUSTOMER-F04 Edit the card and its custom fields
Status: done
Actor: everyone who manages cards (owner, administrator, manager, employee)
Screen: Customer card
Steps:
1. On the card tap **Edit**: the details become the add form, plus the business's "Custom fields" (each
   with its shape: text, number, date, yes/no, select or long text; the required ones carry `*`) and the
   "Active" checkbox.
2. Change what is needed. Emptying a field is also a change.
3. Tap **Save**. "Customer updated" shows.
In: the changed details and the value of each custom field. The phone is stored in the international
format, as when adding.
Out: the card and its fields saved in a single write, and the card-updated notice
(`customer.customer.updated`), which WhatsApp listens to so as to join the conversations of a phone just
corrected. Saving without changing anything notifies nobody. The consent stays recorded with the address
it was given for: changing the phone or the email does not carry it over (CUSTOMER-F14).
If it fails: an empty required field ("This field is required."), a value that does not fit its type
("Enter a number." if "three" is written in a number, "Enter a valid date." if the date does not exist,
like a 31/02, also in "Birthday" and "Anniversary", "Choose one of the options."), a field that no longer
exists or a phone that is not of its country reject the WHOLE save: the reason shows next to its field
and the card keeps what it had saved. The "Active" checkbox unticked only changes the "Active" figure:
the card still shows in searches, at the till and on WhatsApp.
Involved: WHATSAPP_INBOX-F04

### CUSTOMER-F05 Add a note to the card
Status: done
Actor: everyone who manages cards
Screen: Customer card
Steps:
1. In "Add note", write the note.
2. Tap **Add**. "Note added" shows and the note appears at the top of the "Activity", with who wrote it
   and when.
In: the text (up to 5,000 characters) and, if whoever writes it puts them in by another way (an
automation), a title of its own and the author's name.
Out: the note, which IS its entry in the activity (a single row: there can be no note without activity),
and the note-added notice (`customer.note.added`). Notes are neither edited nor deleted. An automation can
write notes through the same service.
If it fails: an empty note shows under the field; "This customer is no longer available." if the card no
longer exists.
Involved: none

### CUSTOMER-F06 Put groups and tags on a card
Status: done
Actor: everyone who manages cards
Screen: Customer card
Steps:
1. In "Groups", tick or untick the checkboxes.
2. Tap **Save groups**. "Groups assigned" shows.
3. The same with "Tags" and **Save tags** ("Tags assigned").
In: the full selection of groups or of tags.
Out: the selection REPLACES the previous one (it is not added), and the groups- or tags-changed notice
(`customer.customer.groups_changed`, `customer.customer.tags_changed`) if something changed. The
"Customers" count of Groups and Tags updates by itself. If another person changes the card while you are
ticking, what you ticked or unticked and have not saved yet stays as you left it; what that person adds,
deletes or removes and you have not touched appears or disappears in your selection too. Saving never
puts back what another person removed or deleted.
If it fails: a group or a tag another person has just deleted: "That group no longer exists." / "That
tag no longer exists.", and nothing is saved; what was deleted leaves your selection (the rest you ticked
stays, even if the search hides it) and the next **Save groups** or **Save tags** works. With no groups
or tags: "No groups." / "No tags.".
Involved: none

### CUSTOMER-F07 Delete a card
Status: done
Actor: owner, administrator
Screen: Customer card
Steps:
1. On the card tap **Delete**.
2. A dialog asks "Delete customer" — "Delete {name}? They no longer show in the list, at the till or in
   the search by phone. Their sales are kept." with **Cancel** and **Delete**.
3. On confirming, "Customer {name} deleted" shows and the card disappears from the list, the till and
   the search by phone.
In: the card.
Out: the card marked as deleted KEEPING its details, its activity, its consents, its purchases and its
linked orders, and the card-deleted notice (`customer.customer.deleted`). A card with purchases is
deleted all the same: sales and invoices keep their own tax copy. A sale that arrives later for that
card no longer adds up (CUSTOMER-F20). It is not the erasure of personal data: that is CUSTOMER-F16.
If it fails: a card that does not exist: "This customer is no longer available.", notifying nobody. On a
card already deleted, merged into another or with its data erased it does NOT fail: it answers fine and
notifies again.
Involved: SERVICE-F29

### CUSTOMER-F08 Import cards from a CSV
Status: done
Actor: everyone who manages cards
Screen: Customers
Steps:
1. Tap **Import CSV** and choose the file.
2. Headers it understands: `name`/"Nombre", `email`/"Email"/"correo", `phone`/"Teléfono"/"tel",
   `tax_id`/"NIF"/"CIF", `company_name`/"Empresa", `address`/"Dirección", `city`/"Ciudad",
   `postal_code`/"CP"/"Código postal", `country`/"País", `lifecycle_stage`/"Etapa" and `notes`/"Notas"
   (the same columns the export gives, CUSTOMER-F09), and also `source`, `preferred_channel`,
   `birthday`, `anniversary` and `avatar`.
3. While it works, "Importing…" shows. When it ends, a summary "Import: {total} rows — {created}
   created, {skipped} skipped." with each skipped row and its reason, which begins with the column it
   speaks of ("Name: This field is required."; the same with an email or a phone that are not valid), and
   those with something to review ("Country not recognised: imported without country, check it on the
   card.").
In: the file, which the screen sends in blocks of 50 rows.
Out: the cards created, with source "Import", the phone in the international format and without consent
(even if the file brings a consent column), and a card-created notice for each one, so WhatsApp joins
their conversations as with adding by hand. A row without stage comes in as "Active" (it is a customer
already had), just as in the current product; the old stage `customer` is also read as "Active". A row
without source comes in as "Import".
If it fails: a bad row is skipped with its reason and the others are created. A row with the same name,
phone and email as a card already there (because it was already imported or because the file repeats it)
is skipped with "There is already a card with this name, phone and email: it is not created again."; so,
importing the same file again after a cut halfway only creates what was missing. It is enough for one of
the three to change for it to be created (a mother and her daughter share a phone, CUSTOMER-F12).
Involved: WHATSAPP_INBOX-F04

### CUSTOMER-F09 Export the cards to CSV
Status: done
Actor: owner, administrator, manager
Screen: Customers
Steps:
1. With the search and the filters wanted, tap **Export CSV**.
2. The browser downloads `customers.csv` with ALL the cards that match the search, not only the page
   that is seen.
In: the table's search and filters.
Out: a file with the columns `name`, `email`, `phone`, `tax_id`, `company_name`, `address`, `city`,
`postal_code`, `country`, `lifecycle_stage`, `notes`, `source`, `is_active`, `total_purchases`,
`total_spent` (in the business's currency, with its decimals: two in euros or in złoty, none in yen),
`last_purchase_at`, `created_at`, `groups` and `tags`. A value that starts with `=`, `+`, `-` or `@` (a
phone, for example) comes out with an apostrophe in front so the spreadsheet does not read it as a
formula; the import removes it.
If it fails: without permission to export, the server refuses it even if called through the API. With no
cards, a file with only the headers comes out.
Involved: none

### CUSTOMER-F10 Recognise a person by their phone number
Status: done
Actor: system
Screen: none
Steps:
1. Another app (WhatsApp, Reservations when noting a reservation by hand) or the till's quick add
   (CUSTOMER-F12) asks which cards carry a number.
2. The number is read with the same rules it is stored with (CUSTOMER-F11): with the prefix it carries
   (`+` or the `00` of the business's country) or, if it carries none, in the business's country.
3. Digits without `+` are also read as an international number, which is how WhatsApp gives them: in a
   business in Spain, digits starting with `44` are also a United Kingdom number.
4. The live cards whose phone is one of those numbers match. In a business in Spain, the same mobile
   written with spaces, with dashes or with `+34`, `0034` or `34` in front is the same person.
5. The same digits behind another country's prefix are another person: that mobile with France's prefix
   (`+33`) is not the card of a Spanish salon's Spanish mobile.
In: the number as it arrives.
Out: the cards that match (name, email and phone), by name. If there are two or more, whoever asks
decides.
If it fails: an empty number, with letters or that is not possible in its country matches nobody (it
never returns the whole list). Cards that are deleted, merged or with their data erased do not show.
Involved: RESERVATION-F06, WHATSAPP_INBOX-F04

### CUSTOMER-F11 Store the phone in the international format (E.164)
Status: done
Actor: whoever adds or edits
Screen: Customer card
Steps:
1. When adding, editing, importing or creating at the till or through WhatsApp, the phone is written as
   one has it (with spaces or dashes, with `0034` or `+34` in front, or with another country's prefix and
   the national zero in brackets).
2. On saving, libphonenumber's rules are read: with the prefix it carries or, if it carries none, in the
   business's country (today always Spain, see "Before you start"); out go spaces, dashes, dots, slashes,
   brackets and the national zero (also in brackets after the prefix). Italy and the other countries that
   keep the `0` after the prefix keep it. The number has to be a valid number of its country (its
   numbering, not only its length). It is stored with its prefix and the digits together (`+34` and the
   nine digits, for a Spanish number).
3. Emptying the phone is allowed: only the name is required.
In: the typed phone.
Out: the phone in E.164 on the card. Whoever copies it (Appointments in the appointment) copies it
already normalised.
If it fails: a number that is not valid in its country (`600111` in Spain, a range not in use), with
letters (an extension) or with two numbers in the same field is rejected with "This is not a valid phone
number of its country: check the digits or write it with its international prefix (+44…)." and nothing
is saved.
Involved: APPOINTMENT-F01, WHATSAPP_INBOX-F04

### CUSTOMER-F12 Avoid duplicate cards of the same person
Status: done
Actor: everyone who manages cards
Screen: Customers and Till customer search
Steps:
1. Before creating, search by name, phone, email or tax ID (CUSTOMER-F02).
2. In the till's quick add, if the phone is that of one or more live cards (CUSTOMER-F10), they are shown
   and it asks: use one of them or create another (it may be another person with the same phone). It
   never assigns without choosing (CUSTOMER-F18).
3. On WhatsApp, the appointment answer only creates a card if the search by number finds nobody.
4. If there are already two cards of the same person, they are joined with CUSTOMER-F13.
In: what is typed.
Out: nothing of its own. On purpose, no rule prevents two cards with the same phone, email or tax ID: a
mother and her daughter share a phone, and a company gives the same email to several people.
If it fails: the duplicate card is created; it is joined later.
Involved: WHATSAPP_INBOX-F37

### CUSTOMER-F13 Merge two cards of the same person
Status: done
Actor: owner, administrator, manager; the employee, with a manager's PIN
Screen: Customer card
Steps:
1. Open the card that is going to STAY and tap **Merge with…**.
2. Look for the duplicate (name, email, phone, tax ID or company) and tap it.
3. Read the warning: "{absorbed} will be merged into {surviving}: its appointments, sales, bookings,
   conversations, prepaid packages, notes and consents move to {surviving}, empty fields are filled from
   it, and {absorbed} disappears from the list. This cannot be undone.".
4. Tap **Merge**. "{name} was merged into this customer." shows.
5. If an employee taps it, "An approval is needed" opens on top first with "Approving: Merge two customer
   cards", and a manager approves it with their PIN (or their badge) on that same device (BASE-F84); then
   they are merged.
In: the two cards, live and different.
Out: the one that stays keeps its details and only fills its EMPTY fields with the other's (also the
preferred channel if it was "None"); the internal notes are put together one after the other; purchases
and spent are added up and the last purchase is the most recent. The activity (notes included), the
custom fields it did not have, the groups and the tags (joined), the purchases, the linked orders and all
the consents move to it, and the consents keep the address they were given for. Name, stage, source and
"Active" are its own. Its activity gets "Duplicate customer merged into this one". The other is retired,
with the figures at zero, and keeps its details and the field values that clashed until the data of the
one that stays is erased: CUSTOMER-F16 erases both at once (it is the same person). Cards previously
merged into the absorbed one move to point at the one that stays, so there are never chains. The
cards-merged notice (`customer.customer.merged`) makes Appointments, Sales & POS, Reservations, WhatsApp
and Services re-point what is theirs; Online booking follows it through Appointments. Kitchen keeps no
customer: it has nothing to re-point.
If it fails: "This customer is no longer available." if one of the two is no longer there; choosing the
same card: "Pick another card: a card cannot be merged into itself."; if "Cancel" is tapped in "An
approval is needed", "This needs a manager's approval.". Nothing changes.
Involved: APPOINTMENT-F23, RESERVATION-F21, SALE-F33, SERVICE-F28, WHATSAPP_INBOX-F12, ONLINE_BOOKING-F09, BASE-F84

### CUSTOMER-F14 Record the consent of a channel
Status: done
Actor: everyone who manages cards
Screen: Customer card
Steps:
1. In "Marketing consent" there is a line for Email, WhatsApp and SMS (and another for each channel with
   something recorded: Phone, Post), with its state: "Never asked", "Given" or "Withdrawn", and the date
   and the address if there are any.
2. Tap **Record consent**. The sentence "I want to receive offers and news from this business through
   this channel. I can unsubscribe whenever I want." shows with the hint "Read it out loud and only press
   if they say yes. This exact sentence is what gets stored as the record, together with your name and
   the time.".
3. If the customer says yes, tap **They said yes**. "Consent recorded." shows.
In: the channel, the exact sentence and its version, the origin ("at the counter" to begin with) and, if
there is one, a proof. The address is put by the server with the card's at that moment (the email, the
phone for WhatsApp, SMS and calls, or the postal address) and who records it comes from the session.
Out: a new fact that is never edited or deleted, a "Consent given" entry in the activity and the
consent-given notice (`customer.consent.granted`).
If it fails: an empty sentence or a date in the future are rejected next to their field; "This customer
is no longer available." if the card is no longer there. Whoever does not manage cards sees the state
without buttons. Editing, creating or importing a card NEVER sets consent.
Involved: none

### CUSTOMER-F15 Withdraw the consent of a channel
Status: done
Actor: everyone who manages cards
Screen: Customer card
Steps:
1. On a "Given" channel, tap **Withdraw**: a single tap, with no dialog and no reason asked for.
2. "Consent withdrawn. It is in force from now on." shows and the line becomes "Withdrawn".
In: the channel and, if wished, a reason.
Out: a new fact (the earlier "Given" is kept: it proves the time when writing was allowed), "Consent
withdrawn" in the activity and the `customer.consent.withdrawn` notice. Giving it again later is another
fact.
If it fails: like CUSTOMER-F14.
Involved: none

### CUSTOMER-F16 Erase a customer's personal data (GDPR)
Status: done
Actor: owner, administrator
Screen: Customer card
Steps:
1. On the card tap **Erase personal data**.
2. "Erase personal data (GDPR)" shows with the text "This erases {name}'s personal data, their notes,
   their activity, their health data and their custom fields, and cannot be undone. Sales and invoices
   keep their reference. An audit entry records who, when and why." and the field "Reason (kept in the
   audit)".
3. Tap **Erase personal data**. The card closes and "Personal data erased." shows.
In: the card and the reason (optional, up to 500 characters). It also works for a card already deleted or
merged into another. The duplicate cards that were merged into it (CUSTOMER-F13) are the same person:
their data is erased in the same step, each with its audit and its notice.
Out: the card keeps its identifier, the fixed name `Deleted customer` and no contact, tax ID, address,
dates, internal notes or channel, and disappears from every list. Its activity (notes included), its
health data (CUSTOMER-F32), its custom field values and its membership of groups and tags are erased;
its consents are left without address, proof or reason. Source, stage, purchases, spent, last purchase
and date added are kept, as are the purchases and the linked orders (commercial and tax proof) and a
single audit entry (who, when, the reason and what was erased and what was kept). The data-erased
notice (`customer.customer.erased`) is listened to by WhatsApp, Services, Appointments, Reservations,
Online booking and Tables to empty their copies. Sales & POS and Invoicing keep their tax copy (it is a
tax document).
If it fails: "This customer is no longer available." if it does not exist. Repeating it does not change
the data or duplicate the audit, but notifies again.
Involved: RESERVATION-F22, SERVICE-F29, WHATSAPP_INBOX-F11, APPOINTMENT-F24, ONLINE_BOOKING-F12, TABLE-F31

### CUSTOMER-F17 Assign a customer to the sale at the till
Status: done — the search is `CustomerSearch` (see "Till customer search · API"); Sales & POS mounts it on its screen
Actor: everyone
Screen: Till customer search
Steps:
1. On the sale screen tap "Assign customer". If the business requires a customer, charging without one
   opens the search by itself.
2. The search shows the first 20 cards by name; typing searches like CUSTOMER-F02.
3. Tap the card: the button starts showing its name and the sale receives a COPY of its tax details
   (name, tax ID, address and country).
4. **Remove customer** leaves the sale without a customer. On charging, parking, leaving it at the table
   or deleting the check, Sales & POS lets go of the customer and removes its link to the order
   (CUSTOMER-F19).
5. On reloading, recovering a parked check or picking up a table again, the check comes back with its
   customer: Sales & POS asks Customers which customer that order has.
In: the search and, on choosing, the full card (CUSTOMER-F30).
Out: to Sales & POS, the customer and the tax copy. Changing the card later does not change an issued
invoice.
If it fails: the reason with "Retry"; with no results, "No results."; if the full card cannot be read,
the customer is not assigned. If on recovering the check its customer is no longer available, the check
stays without a customer; if it cannot be read, Sales & POS warns "The check's customer could not be
read. Choose them again if the sale needs one." (or with the reason Customers gives).
Involved: SALE-F04, SALE-F05, SALE-F17, INVOICE-F02

### CUSTOMER-F18 Create a customer from the till's search
Status: done — the search is `CustomerSearch` (see "Till customer search · API"); Sales & POS mounts it on its screen
Actor: everyone who manages cards
Screen: Till customer search
Steps:
1. Type something it does not find and tap **+ New customer «{what you typed}»**. If it looks like a
   phone, it goes to "Phone"; if not, to "Name".
2. Fill in "Name" and "Phone" and tap **Create and assign**.
3. If that phone is already a live card's, "There is already {name} with this phone. Use that card or
   create a new one?" shows (with several, "These customers already have this phone…" and the list) with
   **Use {name}** and **Create a new one**; nothing is assigned until choosing (like Square and
   Lightspeed).
4. The chosen card or the new one is assigned to the sale as in CUSTOMER-F17.
In: name and phone.
Out: the card with source "Walk-in", the phone in E.164, the card-created notice and the sale with a
customer.
If it fails: without a name it cannot be tapped; a phone that is not of its country shows inside the
form; if it cannot be looked up who has that phone, the card is created (the sale is not blocked; if it
was the same person they are joined with CUSTOMER-F13).
Involved: SALE-F05, WHATSAPP_INBOX-F04

### CUSTOMER-F19 Link the customer to the open order
Status: done
Actor: system (Sales & POS asks for it)
Screen: none
Steps:
1. With a customer assigned, Sales & POS opens or saves the order (the table's check, the cart) and asks
   Customers to link it.
2. Customers notes which customer that order has. Reassigning another customer to the same order
   replaces the previous one (an order, at most one customer); the same customer again rewrites nothing.
3. On letting go of the customer (removing them, leaving the check at the table, deleting the check),
   Sales & POS asks for the link without a customer and the link is removed.
In: the order and the customer (or none), with the permission of whoever is at the till.
Out: the customer ↔ order link and its notice (`customer.order.linked` or `customer.order.unlinked`).
Sales & POS reads it to give the customer back to the check (CUSTOMER-F17).
If it fails: the sale goes on; Sales & POS warns "The customer could not be linked to the check. Choose
them again." (or with the reason Customers gives). A customer that is no longer available is not linked.
Involved: SALE-F17

### CUSTOMER-F20 Add the purchase to the card when charging
Status: done
Actor: system
Screen: none
Steps:
1. A sale with a customer is charged.
2. On its card "Purchases" goes up by one and "Spent" by the sale's total, "Last purchase" becomes that
   moment and the "Activity" gains "Purchase recorded".
3. The stage moves forward by itself: "Lead" or "Prospect" → "1st purchase"; "1st purchase", "At risk"
   or "Dormant" → "Active". "Churned" and "VIP" are not touched.
In: the charged sale, with its customer and its total in cents (the `sale.sale.completed` notice of
Sales & POS).
Out: one line in the purchase history per sale, the card's figures and stage, the activity entry and the
`customer.purchase.recorded` notice.
If it fails: a sale without a customer does nothing; the same sale delivered twice counts only once; a
card that is deleted, merged or with its data erased does not add up.
Involved: SALE-F01

### CUSTOMER-F21 Subtract a voided sale
Status: done
Actor: system
Screen: none
Steps:
1. A sale that had a customer is voided.
2. On its card "Purchases" and "Spent" go down, "Last purchase" goes back to the previous purchase still
   standing and the "Activity" gains "Purchase voided" with the reason.
3. The stage goes back: with no purchases, "1st purchase" or "Active" → "Lead"; with one, "Active" →
   "1st purchase". "VIP" and the others are not touched.
In: the voided sale (the `sale.sale.voided` notice of Sales & POS).
Out: the history line marked as voided (it is not deleted), the figures, the stage and the
`customer.purchase.voided` notice.
If it fails: voiding the same sale twice subtracts only once; a sale that was not recorded does nothing.
Involved: SALE-F30

### CUSTOMER-F22 Subtract a refund
Status: done
Actor: system
Screen: none
Steps:
1. All or part of a sale that had a customer is refunded.
2. On its card, "Spent" goes down by what was refunded; "Purchases", "Last purchase" and the stage do not
   change; the "Activity" gains "Purchase refunded" with the amount and the reason.
In: the sale's refund (the `sale.sale.refunded` notice of Sales & POS: sale, refund, amount refunded,
reason and moment).
Out: a refund line in the purchase history, with its amount negative and the status "Refund", and the
`customer.purchase.refunded` notice. The card's "Spent" is what was charged minus what was refunded,
also for the figures audit (`customer.purchase.divergences`).
If it fails: the same refund delivered twice counts only once; the refund of a sale that is not recorded
(no customer) or that was voided does nothing; on a card with its data erased it subtracts but leaves no
activity.
Involved: SALE-F31

### CUSTOMER-F23 See a customer's purchase history
Status: done
Actor: everyone
Screen: Customer card
Steps:
1. Open the card (CUSTOMER-F03).
2. In "Purchases" each sale shows with its date, its amount (in the currency it was charged in) and its
   status ("Paid" or "Voided"), and each refund on its own line ("Refund", amount negative), the newest
   first, 50 per page; it can be filtered by status.
In: the card's purchase history.
Out: nothing; read only.
If it fails: "No purchases." if there are none.
Involved: none

### CUSTOMER-F24 See on the card what other apps know about the customer
Status: done
Actor: everyone
Screen: Customer card
Steps:
1. Open the card. At the end appears the block of each switched-on app that offers one (today,
   Appointments with the "Visit history"); if the app is off, its block does not show.
2. Read the block: in "Visit history" their last ten appointments show, the newest first, with the
   services, the professional, the status and the notes of the visit. A new appointment appears without
   reloading the card.
In: which customer is open (Customers tells the block; it passes it no more data).
Out: nothing; read only.
If it fails: each block shows its own error in its place ("This block could not be shown.") and the rest
of the card goes on.
Involved: APPOINTMENT-F20

### CUSTOMER-F25 Create the client without leaving the agenda
Status: done
Actor: everyone who manages cards
Screen: Appointments: Agenda
Steps:
1. In the agenda, tap "Add appointment" and, in "New appointment", choose the services, the
   professional, the day and the time in the order you like.
2. In "Customer", tap "Assign customer" and write the client's name or phone. If she has no card, "No
   results." shows and, below, "+ New customer «…»" with what you have written.
3. Tap it. What was written goes to "Name" (or to "Phone", if it is a number); fill in the other (only
   the name is required) and tap "Create and assign".
4. If that phone is already on another card, it is shown and you choose: "Use" that card or "Create a new
   one" (a mother and her daughter may share a phone).
5. The client stays chosen in "Customer" and the rest of the appointment goes on as it was; tap "Add
   appointment".
In: the name and, if you give it, the phone.
Out: the new card, with source "Walk-in", and the appointment with it.
If it fails: the reason shows inside "Choose customer", next to what you have written (a phone that is
not of its country, under "Phone"), and nothing is lost: neither the typed name and phone nor the
services, the professional, the day and the time of the appointment. Correct it and tap "Create and
assign" again. Whoever does not manage cards does not see "+ New customer".
Involved: APPOINTMENT-F01, CUSTOMER-F18

### CUSTOMER-F26 Create the card of whoever asks for an appointment on WhatsApp
Status: discarded — the WhatsApp inbox's automatic appointment answer is not offered yet: after
"Approve", Appointments refuses an automation's appointment (WHATSAPP_INBOX-F21). The Customers part is
there: looking up by the number (CUSTOMER-F10) and adding with source "WhatsApp", which the table answer
(WHATSAPP_INBOX-F24) and the inbox's "Create card" (WHATSAPP_INBOX-F37) already use (hub#514)
Actor: assistant
Screen: none
Steps:
1. A client writes to the salon's WhatsApp with the automatic appointment answer switched on.
2. The answer looks up her card by the number (CUSTOMER-F10). If it finds it, it uses it.
3. If not, it creates a card with the name the client has given (or her phone as the name), her phone
   in E.164 and source "WhatsApp".
4. In the restaurant, the table answer does the same with whoever asks for a table (WHATSAPP_INBOX-F24).
In: the number and the message.
Out: the new card and the card-created notice.
If it fails: a number that is not valid creates no card; if it matches two or more cards, it creates
none.
Involved: WHATSAPP_INBOX-F21, WHATSAPP_INBOX-F24, WHATSAPP_INBOX-F37, APPOINTMENT-F18

### CUSTOMER-F27 Create, change and delete customer groups
Status: done
Actor: owner, administrator, manager; the employee creates and changes with a manager's PIN (deleting:
owner and administrator)
Screen: Groups
Steps:
1. In **Groups** tap **Add** ("New group"): "Name" (required), "Description", "Color" and "Order".
   **Save** → "Group created".
2. To change it, tap the row ("Edit · {name}"), which adds the "Active" checkbox. **Save** → "Group
   updated". A deactivated group stops being offered on the cards (those that have it keep it) and stays
   in the list with the inactive filter, from where it is activated again.
3. To remove it, **Delete**: "Delete {name}? The customers who have it lose it." → "Group {name}
   deleted".
4. If an employee taps **Save**, "An approval is needed" opens on top first with "Approving: Create a
   customer group" (or "Change a customer group"), and a manager approves it with their PIN (or their
   badge) on that same device (BASE-F84). Deleting is never asked for: the employee does not see it.
In: the group's details.
Out: the group, which is assigned from each card (CUSTOMER-F06), and its notice
(`customer.group.created`, `.updated`, `.deleted`). Deleting a group really removes it from all its
cards. A group carries no discount or price.
If it fails: a name already used by another active group (ignoring case and the spaces at the ends):
"There is already a group with that name. Choose another name." under "Name"; an inactive group frees its
name, and reactivating it with a name another one already has is rejected all the same. If "Cancel" is
tapped in "An approval is needed", the form stays open with what was typed and says "This needs a
manager's approval.".
Involved: BASE-F84

### CUSTOMER-F28 Create, change and delete customer tags
Status: done
Actor: owner, administrator, manager; the employee creates and changes with a manager's PIN (deleting:
owner and administrator)
Screen: Tags
Steps:
1. In **Tags** tap **Add** ("New tag"): "Name" and "Color". **Save** → "Tag created".
2. When editing ("Edit · {name}") "Active" appears, as in the groups. **Save** → "Tag updated".
3. **Delete**: "Delete {name}? The customers who have it lose it." → "Tag {name} deleted".
4. As with the groups, the employee saves with a manager's PIN: "Approving: Create a customer tag" (or
   "Change a customer tag") (BASE-F84). Deleting is not offered to them.
In: name and color.
Out: the tag, which is assigned from each card (CUSTOMER-F06), and its notice (`customer.tag.created`,
`.updated`, `.deleted`). Deleting it removes it from all its cards.
If it fails: "There is already a tag with that name. Choose another name." under "Name"; "Cancel" in
"An approval is needed": "This needs a manager's approval." and nothing is saved.
Involved: BASE-F84

### CUSTOMER-F29 Define the card's custom fields
Status: done
Actor: owner, administrator, manager; the employee, with a manager's PIN
Screen: Fields
Steps:
1. In **Fields** tap **Add** ("New custom field"): "Name", "Type" ("Text", "Number", "Date", "Yes/No",
   "Select" or "Long text"), the "Options" if it is a select, "Order" and, if needed, "Required".
2. **Save** → "Field created". The field appears on the card of ALL the customers (CUSTOMER-F03, F04),
   with its shape.
3. When editing ("Edit · {name}") "Active" appears: an inactive field does not show on the cards and is
   not demanded, and its values stay. Everything can be changed except the type, if there are already
   cards with a value. **Delete** → "Delete {name}? The values saved on the cards are deleted too." →
   "Field {name} deleted".
4. If an employee saves or deletes, a manager approves it first with their PIN (or their badge) on that
   same device (BASE-F84): "Approving: Create a custom field" ("Change…", "Delete a custom field").
In: the field's definition.
Out: the field and its notice (`customer.field.created`, `.updated`, `.deleted`). "Required" is only
demanded when saving the full card (CUSTOMER-F04), never when adding it (Customers, till, import or
WhatsApp).
If it fails: "There is already a field with that name. Choose another name." under "Name"; a select
field without options: "Add at least one option."; changing the type of a field with values: "This field
already has values on some cards: its type cannot change."; "Cancel" in "An approval is needed": "This
needs a manager's approval." and nothing changes.
Involved: BASE-F84

### CUSTOMER-F30 Give a customer's card to other apps
Status: done
Actor: system
Screen: none
Steps:
1. Another app asks for a customer's card by its identifier: Appointments when booking, Services when
   painting the holder of a prepaid package, Sales & POS when assigning the customer (CUSTOMER-F17); and
   the card itself.
2. Customers answers with the card: name, email, phone, tax ID, company, address, city, postal code,
   country, notes, birthday, anniversary, preferred channel, stage, source, whether it is active, the
   purchase totals, its groups, its tags, its custom fields and its consent per channel.
In: the card's identifier and the permission to view customers.
Out: nothing stored; read only.
If it fails: a card that does not exist, is deleted, merged into another or with its data erased is not
returned: "This customer is no longer available.". A deactivated card is returned.
Involved: APPOINTMENT-F01, SERVICE-F16, SALE-F05

### CUSTOMER-F31 See the customers' figures
Status: done
Actor: everyone
Screen: Customers
Steps:
1. Open **Customers**: at the top, above the table, four figures show: "Customers", "Active", "VIP" and
   "Revenue".
2. "Customers" counts the cards still in the list; "Active", those with the "Active" checkbox ticked;
   "VIP", those of the "VIP" stage, and "Revenue" adds up what all of them have spent, in the business's
   currency.
3. The figures change by themselves, without reloading, when someone adds, edits, deletes, merges or
   erases the data of a card, or when a sale with a customer is charged, voided or refunded.
In: nothing: they count all the cards still in the list, not only those the table's search or filters
let through.
Out: nothing; read only.
If it fails: "The figures could not be loaded" in their place, and the table keeps working. While they
arrive, each figure shows "…". On the phone they go two by two, so the table can still be seen below.
Involved: none

### CUSTOMER-F32 Note allergies or the sensitivity test with their permission
Status: done
Actor: everyone who manages cards (seeing it: everyone)
Screen: Customer card
Steps:
1. On the card, the "Health and allergies" block says "To note allergies or sensitivity tests you need
   their explicit permission." and shows **Ask for permission**.
2. Tap it: the sentence "I give my permission for this business to keep my allergies and my sensitivity
   tests to look after me safely. I can withdraw it whenever I want and they will then be erased." shows
   with the hint "Read it out loud and only press if they say yes. This exact sentence is what gets stored
   as the record, together with your name and the time.".
3. If she says yes, tap **They said yes**: "Permission recorded." shows and the block shows her health
   data (at first, "No allergies noted." and "No sensitivity test.").
4. Tap **Edit**: "Allergies and sensitivities", "Sensitivity test date" and "Result" ("No result",
   "Negative" or "Positive"). **Save** → "Health data saved.".
5. With allergies noted, the block shows them highlighted, as a warning, so whoever serves sees them
   before the service.
6. **Withdraw permission** asks "Withdraw the permission? Their allergies and sensitivity test are
   erased." and, on confirming, "Permission withdrawn and health data erased." shows.
In: the exact sentence and its version (who records it comes from the session); the allergies (up to
2,000 characters), the date of the test and its result.
Out: the permission, as one more fact of the consent book (purpose "health data", with its entry in the
"Activity" and its notice `customer.health.consent_granted` or `customer.health.consent_withdrawn`), and
the health data, with "Health data updated" in the activity (without its content) and the
`customer.health.updated` notice. The notices carry only identifiers. Withdrawing the permission ERASES
the health data in the same step.
If it fails: without the permission in force nothing is saved: "Record their permission first to keep
health data.". A test with a future date: "This date is in the future."; a result without a date: "Enter
the date of the test.". "This customer is no longer available." if the card is no longer there. Whoever
does not manage cards sees the block without buttons.
Involved: CUSTOMER-F13, CUSTOMER-F16

## What the verticals share

Touching a piece of this table affects the hair salon **and** the restaurant.

| Shared piece | Flows that use it |
|---|---|
| A single card form for adding and editing | F01, F04, F11 |
| Reading the phone (the same rules when saving and when searching by number) | F01, F04, F08, F10, F11, F18, F26 |
| The list's text search (table, merge, till and Appointments' picker) | F02, F13, F17, F18, F25 |
| The card-created or card-updated notice, which WhatsApp listens to | F01, F04, F08, F18, F26 |
| The merge and its notice | F13 |
| The data erasure and its notice, and the deletion | F07, F16 |
| The till's search, the tax copy and the purchase history | F17, F18, F19, F20, F21, F23 |
| The consent per channel | F14, F15 |
| Groups, tags and custom fields | F06, F27, F28, F29 |

What is **not** shared: the visit history on the card (Appointments only, F24) and adding from the agenda
(F25).

## Services: what goes in and what comes out

Everything can be asked for through the screens, the assistant (by voice or by text, with the session of
whoever uses it) and the API, with the same rules and the same permissions. Lists come in pages of up to
100 and all of them have a search. To speak naturally, a customer can be named by their id or by their
exact name, their phone or their email ("add a note to Ana García"), and a group, a tag or a field, by
its name; if two cards fit, the id, the phone or the email is asked for.

### What it offers: queries (they read, they change nothing)

| What it gives | Who may | Flows | Live | Service |
|---|---|---|---|---|
| The cards, with search, filters, sort and pages | view | F02, F17 | yes | `customer.customer.list` |
| The full card, with groups, tags, fields and consent per channel | view | F03, F30 | yes | `customer.customer.detail` |
| The figures: customers, active, VIP and revenue | view | F02, F31 | yes | `customer.customer.stats` |
| The cards that carry a phone number | view | F10, F12, F18 | no | `customer.customer.by_phone` |
| The CSV of all the cards that match the search | export | F09 | no | `customer.customer.export` |
| The groups, with how many cards each one has | view | F06, F27 | yes | `customer.group.list` |
| The tags, with how many cards each one has | view | F06, F28 | yes | `customer.tag.list` |
| The custom fields | view | F04, F29 | yes | `customer.field.list` |
| A card's activity, newest first | view | F03, F05 | yes | `customer.activity.list` |
| A card's purchases | view | F23 | yes | `customer.purchase.list` |
| The cards whose figures do not add up with their purchases (audit) | view | F20, F21 | yes | `customer.purchase.divergences` |
| A card's consent in force, by purpose and channel (also for API keys) | view | F14, F15 | yes | `customer.consent.state` |
| Everything that was decided about a card's consent | view | F14, F15 | yes | `customer.consent.history` |
| Which customer an order has | view | F17, F19 | yes | `customer.order.customer` |
| A card's orders (also for API keys) | view | F19 | yes | `customer.order.list` |
| A card's health data and its permission (on screen only) | view | F32 | yes | `customer.health.detail` |

### What it offers: actions (they change data)

| What it does | Who may | Flows | Service |
|---|---|---|---|
| Adds a card | manage | F01, F18, F25, F26 | `customer.customer.create` |
| Changes the card (only what is sent) and its custom fields | manage | F04 | `customer.customer.update` |
| Creates up to 50 cards from a CSV, row by row | manage | F08 | `customer.customer.import` |
| Replaces a card's groups | manage | F06 | `customer.customer.set_groups` |
| Replaces a card's tags | manage | F06 | `customer.customer.set_tags` |
| Deletes a card (keeps its data) | delete | F07 | `customer.customer.delete` |
| Merges a duplicate card into another | merge | F13 | `customer.customer.merge` |
| Erases a card's personal data | erase data | F16 | `customer.customer.erase` |
| Adds a note | manage | F05 | `customer.note.add` |
| Notes in the activity an entry from another app (a visit, a reservation) | record activity | F24 | `customer.activity.add` |
| Records a consent given | manage | F14 | `customer.consent.grant` |
| Records a consent withdrawn | manage | F15 | `customer.consent.withdraw` |
| Links (or unlinks) an order's customer | manage | F19 | `customer.order.link` |
| Records the permission to keep health data | manage | F32 | `customer.health.grant` |
| Withdraws that permission and erases the health data | manage | F32 | `customer.health.withdraw` |
| Saves the allergies and the sensitivity test (with the permission in force) | manage | F32 | `customer.health.update` |
| Creates and changes groups; deletes them | configure; delete | F27 | `customer.group.create`, `.update`; `.delete` |
| Creates and changes tags; deletes them | configure; delete | F28 | `customer.tag.create`, `.update`; `.delete` |
| Creates, changes and deletes custom fields | configure | F29 | `customer.field.create`, `.update`, `.delete` |
| Records the purchase of a charged sale (system only) | system | F20 | `customer.purchase.record` |
| Subtracts the purchase of a voided sale (system only) | system | F21 | `customer.purchase.void` |
| Records a refund and subtracts it from spent (system only) | system | F22 | `customer.purchase.refund` |

### What it announces (for the apps that want to react)

The notices carry only identifiers, never personal data: whoever needs the card asks for it
(CUSTOMER-F30).

| Notice | When | What it carries | Service |
|---|---|---|---|
| Card created | Add, quick add, WhatsApp and import (one per row) | `id` | `customer.customer.created` |
| Card updated | Edit with some change | `id` | `customer.customer.updated` |
| Groups changed | Save groups with some change | `id` | `customer.customer.groups_changed` |
| Tags changed | Save tags with some change | `id` | `customer.customer.tags_changed` |
| Card deleted | Delete (also the repetition) | `id` | `customer.customer.deleted` |
| Cards merged | Merge | `id` (the one that stays) and `absorbed_id` | `customer.customer.merged` |
| Personal data erased | Erase data (also the repetition) | `id` | `customer.customer.erased` |
| Note added | Add note | `id` (the note) and `customer_id` | `customer.note.added` |
| Activity noted by another app | Note activity | `id` (the entry) and `customer_id` | `customer.activity.recorded` |
| Consent given / withdrawn | Record / withdraw | `id`, `customer_id` and `channel` | `customer.consent.granted`, `customer.consent.withdrawn` |
| Order linked / unlinked | Link with another customer / let go of them | `order_id` and `customer_id` | `customer.order.linked`, `customer.order.unlinked` |
| Purchase recorded / voided | Sale charged / voided | `customer_id` and `sale_id` | `customer.purchase.recorded`, `customer.purchase.voided` |
| Refund recorded | Sale refunded (all or part) | `customer_id`, `sale_id` and `refund_id` | `customer.purchase.refunded` |
| Group, tag or field created, changed or deleted | Configure | `id` | `customer.group.*`, `customer.tag.*`, `customer.field.*` |
| Health data permission given / withdrawn | Record / withdraw | `id` (the fact) and `customer_id` | `customer.health.consent_granted`, `customer.health.consent_withdrawn` |
| Health data saved | Save with some change | `id` and `customer_id` | `customer.health.updated` |

### What it reacts to (notices from other apps)

| Notice | From | What it does | Service |
|---|---|---|---|
| Sale charged (`sale.sale.completed`) | Sales & POS | Records the purchase (CUSTOMER-F20) | `customer.purchase.record` |
| Sale voided (`sale.sale.voided`) | Sales & POS | Subtracts the purchase (CUSTOMER-F21) | `customer.purchase.void` |
| Sale refunded (`sale.sale.refunded`) | Sales & POS | Records the refund and subtracts it from spent (CUSTOMER-F22) | `customer.purchase.refund` |

The three reactions belong to Customers (like those of Inventory) and are tested with the real notices
of Sales & POS; the system runs them, each in its own transaction, as soon as the Sales & POS notice goes
out (a few seconds after the charge, the void or the refund). Customers does not depend on Sales & POS:
it is the only link.

### What it needs from other apps

Nothing to work. With **Sales & POS**, the till's search, the link to the order and the purchases are
used; with **Appointments**, the visits block and adding from the agenda; with the **WhatsApp inbox**,
recognition by number and automatic adding. None of those apps is a requirement of Customers: it is they
who use the services of Customers.

### Who may do what

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| View cards, groups, tags, fields, activity, purchases and consents | yes | yes | yes | yes | `customer.view` |
| Add, edit, import, add notes, assign groups and tags, record consent and link orders | yes | yes | yes | yes | `customer.manage` |
| Create and change groups, tags and custom fields; delete fields | yes | yes | yes | with PIN | `customer.configure` |
| Merge duplicate cards | yes | yes | yes | with PIN | `customer.merge` |
| Export to CSV | yes | yes | yes | no | `customer.export` |
| Note in the activity what other apps bring | yes | yes | yes | no | `customer.record_activity` |
| Delete cards, groups and tags | yes | yes | no | no | `customer.delete` |
| Erase personal data | yes | yes | no | no | `customer.erase` |

"With PIN": the employee does it if a manager approves it on the spot with their PIN (or their badge) on
the same device (BASE-F84), as in the current product: what the manager holds, another profile does with
their approval. Exporting is a read and is not approved; deleting cards, groups and tags and erasing
personal data belong only to the owner and the administrator, and are never asked for.

Recording and voiding purchases belongs to no role: the system does it when a sale is charged or voided
(`customer.record_purchase`, which no app declares and therefore only the system has).

The server applies these permissions even if the screen shows the button, also through the API and the
assistant. What the "Cashier" profile had in the current product, the employee has here.
