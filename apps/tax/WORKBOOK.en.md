<!-- generated from WORKBOOK.md sha256:a96f2af5a216b788834f261af6dedfd06ce1171254a9c251cdf8e8acece87ea6 -->

## What it is for and who it is for

Taxes keeps what says how much VAT each thing that is sold carries:

- the **tax categories** ("Restaurant — food", "Service — generic"…), which the products of Inventory, the
  services of Services, the open-price sections of Sales, the menus and the modifier options taxed apart
  point to;
- the **rules**, which set the rate of each category in a country or a region and between some dates, with
  its tax qualification (subject, exempt, not subject, reverse charge);
- the **aliases**, outside texts ("food", "beer", "IVA 10") that the Inventory importer recognises as a
  category.

Almost nobody opens it every day: it is prepared when setting up the business and touched when a rate
changes. But every line that Sales charges, every invoice of Invoicing and every product of Inventory or
Services reads from here. It serves restaurants and hair salons alike: what changes is which categories
each one sells, not how it works.

Who uses it:

- The **owner**, the **administrator** and the **manager** create categories, rules and aliases, set an end
  date on a rule and deactivate or restore it.
- The **employee** only looks and calculates.

It does not decide the price, does not issue invoices or talk to the AEAT, and does not keep the business's
country.

## Reference adopted

- [Ley 37/1992 del IVA](https://www.boe.es/buscar/act.php?id=BOE-A-1992-28740): general, reduced and
  super-reduced rates (arts. 90 and 91), exemptions (art. 20) and the equivalence surcharge. The factory
  rates come from here; checking them with the tax adviser is up to each business.
- The AEAT lists (regime `ClaveRegimen`, exemption `OperacionExenta`, causes E1…E6) travel as opaque codes:
  Taxes keeps them and gives them back, it does not interpret them.
- Odoo and Square: the tax is assigned to the product **by category**, not by a loose percentage; several
  taxes on the same line; price with the tax included or added.
- Changing a rate = setting an end date on the one in force and creating the new one, never editing the rule
  (Oracle E-Business Tax, Dynamics 365 and SAP). None of them lets two rates be in force on the same day for
  the same thing.

## Before you start

- When Taxes is turned on, the business gets **11 categories**, **18 aliases** and **the rates of Spain**
  from the factory (TAX-F16). With that a Spanish business can sell without touching anything.
- Turning on Inventory, Services, Sales, Invoicing, Menus and combos or Modifiers turns on Taxes with them,
  and Taxes cannot be turned off while any of them is on.
- **The business's country and tax region**: the country is the one of the business's ERPlora account (in
  phase 1, Spain for everybody); the tax region —the whole country, the Canary Islands, Ceuta or Melilla— is
  chosen in **Taxes → Settings** (TAX-F11). Sales, Invoicing, the screens and the assistant calculate with
  both as long as no other country is asked for.
- The factory rules are only Spain's. A business of another country (when the ERPlora account brings it)
  will have to create its own (TAX-F04); neither the "Your taxes" notice nor the step of the Home (TAX-F17)
  detect it yet, because they count the rules of any country.
- **"Today" is Madrid time** in phase 1: Taxes does not use the business's time zone yet. The day a rate
  changes (TAX-F07) starts at midnight in Madrid; in the Canary Islands (TAX-F11), one hour before their
  midnight. When it uses the business's, "today" will be its own.

Initial setup, step by step:

1. Open **Taxes → Categories** and check that the ones you sell are there; create the missing ones
   (TAX-F02).
2. Open **Taxes → Rules** and check that each category has its rate for your country (TAX-F03). Create the
   missing ones (TAX-F04); if the business is in the Canary Islands, Ceuta or Melilla, follow TAX-F11.
3. If the business is in the Canary Islands, Ceuta or Melilla, choose its region in **Taxes → Settings**
   (TAX-F11).
4. Make a test sale and check the ticket's breakdown.

## Screens

Taxes opens from the **Taxes** menu and has four tabs in the bottom bar: **Categories**, **Rules**,
**Aliases** and **Settings**. While no rate is in force, the first three carry the "Your taxes" notice at the
top for whoever can manage them, the same step the Home brings in "Finish setting up your business" (TAX-F17).
All of them follow the permission of whoever looks: with view
only, the notice "You can view the tax rules but not change them." shows, the **+** button disappears and,
in Rules, so do the row actions. The app requires the permission on every action even if the screen shows
the button.

### Categories
Table with Key, Name, Description, Origin ("System" or "Custom"), Active and the rate in force in the
business's country ("21.00%", "Exempt"…). Search "Search key or name…" (key, name and description, stored
or translated), column filters (Key, Name, Description and Origin) and sorting by any column; 50 per page,
sorted by key at first. The factory ones show with their name in the person's language; the custom ones,
with the text that was typed. A **+** button that opens the creation panel (Key, Name, Description, "Add").
No row actions.

### Rules
Table with Category, Country, Region, %, Type, Qualification (with the exemption reason if there is one),
Valid from, Valid to and Active. A component (the surcharge) shows right under its root rule, as
"↳ label". Search "Search category or country…" and filters for Country, Region, Category, Type,
Qualification, Regime, % (from–to) and Status ("Active", "Deactivated", "All"; at first, "Active"); sorting
by any column. A **+** button with the creation panel (Country, Region, Category, %, Type, Qualification,
Exemption reason —only if it is exempt—, Regime, Valid from, Valid to, "Root rule (component of)",
"Component label" and "Add"). Row actions: "Set end date" and "Deactivate"; on a deactivated one,
"Restore".

### Aliases
Table with Alias, Category, Source ("Shipped" or "Learned") and Active. Search "Search alias or category…",
filters for Alias, Category and Source and sorting by any column. A **+** button with the creation panel
(Alias, Category, Source —"Learned" at first—, "Add").

### Settings
"Your business's tax region": the business's "Country", read only ("It is the country of your ERPlora
account."), and the "Tax region" dropdown with "Whole country (VAT)", "Canary Islands (IGIC)", "Ceuta
(IPSI)" and "Melilla (IPSI)", with its explanation below, and "Save" ("Tax region saved."). Whoever only
views taxes sees the region without being able to change it ("You can see the tax region but not change
it."). It is the screen of TAX-F11.

## States of each screen

| State | What the person sees |
|---|---|
| Loading | "Loading…" while the first result arrives; in Settings, "Loading the tax settings…". |
| Empty | "No tax categories.", "No tax rules." or "No category aliases." (or "No results" with a search or filter), with **+** if they can create. |
| Error | The table's notice with "Retry"; a refusal of the creation shows inside the panel, next to its field. In Settings, "The tax settings could not be loaded." with "Retry" (without showing any region as the business's), and a refusal when saving, "The tax region could not be saved." with the reason under "Tax region". |
| Reconnecting | What is painted stays; a strip says "Reconnecting…" until the connection comes back. |
| No rates in force | For whoever can manage, the "Your taxes" notice with "Set up" (TAX-F17). |
| App inactive (`app_inactive`) | "This app is not active in this business". |
| No permission | What they cannot do does not appear; if they arrive by another door, "You do not have permission". |

## Flows

| ID | Flow | Status |
|---|---|---|
| TAX-F01 | View the tax categories | done |
| TAX-F02 | Create a custom tax category | done |
| TAX-F03 | View and filter the rules | done |
| TAX-F04 | Set the rate of a category in a country or region | done |
| TAX-F05 | Declare an exempt, not subject or reverse-charge operation | done |
| TAX-F06 | Add an equivalence surcharge to a rate | done |
| TAX-F07 | Change a rate from a date | done |
| TAX-F08 | Deactivate and restore a rule | done |
| TAX-F09 | Repair a rule that charges a rate where it should not | discarded |
| TAX-F10 | Resolve overlapping rules | discarded |
| TAX-F11 | Set up a business in the Canary Islands, Ceuta or Melilla | done |
| TAX-F12 | Create several rules at once | done |
| TAX-F13 | View the category aliases | done |
| TAX-F14 | Teach a category alias by hand | done |
| TAX-F15 | Tell the Inventory importer which category a text is | done |
| TAX-F16 | Seed the factory catalogue when turned on | done |
| TAX-F17 | Warn that rates are missing for the business's country | done |
| TAX-F18 | Calculate the tax of an amount | done |
| TAX-F19 | Hand the rules and the categories to Sales, Invoicing, Inventory and Services | done |

### TAX-F01 View the tax categories
Status: done
Actor: owner, administrator, manager, employee
Screen: Categories
Steps:
1. Open **Taxes → Categories**.
2. Search by key or name, or filter by Origin ("System" or "Custom").
3. Read the Key: it is what products and services keep and it never changes; the Name is only a label. The
   rate column says what is charged today in the business's country.
In: nothing; it reads the categories and the rules in force today.
Out: nothing (read only). The name of a factory category shows in the language of whoever looks; a custom
one, with its text. The search finds what is seen: "food" finds "Restaurant — food".
If it fails: the table's notice with "Retry". Without the view permission, "You do not have permission".
Involved: COMBO-F02, INVENTORY-F01, INVENTORY-F02, INVENTORY-F05, INVENTORY-F06, MODIFIER-F04, SALE-F01,
SALE-F35, SERVICE-F01

### TAX-F02 Create a custom tax category
Status: done
Actor: owner, administrator, manager
Screen: Categories
Steps:
1. In Categories tap **+**.
2. Type the Key (lower case; starts with a letter; letters, digits, dots and underscores; up to 80; for
   example `product.books`) and the Name; the Description is optional.
3. Tap "Add". The panel closes and the category shows in the table as "Custom".
In: key, name and description that the person types.
Out: the category, unique by key in the business; Taxes announces that there is a new category
(`tax.category.created`). It brings no rule: until one is created (TAX-F04), a sale of that category is
refused. Inventory also creates it when somebody chooses "Create" when importing a file (TAX-F15).
If it fails: a key with another shape or an empty name show below their field; a key that already exists,
"There is already a tax category with that key." below the Key. Nothing is saved.
Involved: INVENTORY-F09

### TAX-F03 View and filter the rules
Status: done
Actor: owner, administrator, manager, employee
Screen: Rules
Steps:
1. Open **Taxes → Rules**: the active ones show.
2. Search by category or country, or filter by Country, Region, Category, Type or Qualification.
3. Choose Status "Deactivated" (or "All") to see the deactivated ones; their row offers "Restore"
   (TAX-F08).
4. Recognise a component (surcharge) because it shows right under its root rule.
In: nothing; it reads the business's rules.
Out: nothing (read only).
If it fails: the table's notice with "Retry".
Involved: none

### TAX-F04 Set the rate of a category in a country or region
Status: done
Actor: owner, administrator, manager
Screen: Rules
Steps:
1. In Rules tap **+**.
2. Type the Country and choose it from the list that shows below (closed ISO 3166-1 list) and, only if the
   rate changes within the country, the Region (for example ES-CN, which has to be of that country); empty
   applies to the whole country.
3. Type part of the Category's name, choose it from the list and type the %, between 0 and 100 (up to two
   decimals).
4. Choose the Type ("VAT" at first; "IGIC (Canary Islands)", "IPSI (Ceuta/Melilla)"…) and, if you want, Valid
   from and Valid to (empty = since always / forever). Through the assistant or the API, a rule without a
   Type takes its region's: IGIC in ES-CN, IPSI in ES-CE and ES-ML, VAT elsewhere.
5. Tap "Add"; the panel closes and the rule shows in the table.
In: country, region, category, %, type and dates that the person chooses.
Out: the active rule; Taxes announces it (`tax.rule.created`). From that moment Sales and Invoicing use it
for new sales: the rule of the business's region wins and, if there is none, the whole country's, except in
the Canary Islands, Ceuta and Melilla, where only their region's applies (the national VAT does not apply
there); a rule of another region is never used. Sales already made do not change (TAX-F07).
If it fails: two active rules of the same category, country and region cannot be in force on the same day:
the refusal shows in "Valid from" with "It overlaps another active rule of this country, region and
category…" (it is solved with TAX-F07 or TAX-F08). A country that does not exist, a region of another
country, a % outside 0–100, a "Valid to" before "Valid from" or a category that does not exist show below
their field. A rule of the same country, region and category that starts the same day as another one
already saved, even a deactivated one: "There is already a rule of this country, region and category from
that day, perhaps deactivated: reactivate it or start this one another day.", in "Valid from". Nothing is
saved.
Involved: INVOICE-F01, SALE-F01

### TAX-F05 Declare an exempt, not subject or reverse-charge operation
Status: done
Actor: owner, administrator, manager
Screen: Rules
Steps:
1. In Rules tap **+** and fill in country, category and type as in TAX-F04.
2. In Qualification choose "Exempt", "Not subject", "Not subject (place of supply)" or "Reverse charge". The
   % is set to 0 and locked, with the note "This operation carries no tax, so its rate is 0 %.".
3. If it is "Exempt", type the Exemption reason (up to 10 characters, for example E1); the Regime is
   optional (empty = the general one, 01).
4. Tap "Add".
In: qualification, exemption reason and regime (AEAT codes, opaque for this app).
Out: the rule with its qualification (`tax.rule.created`). The reason is kept in upper case and only on an
exempt rule. Invoicing takes the qualification of the rule in force when issuing and VeriFactu translates it
into the AEAT record.
If it fails: a qualification that charges no tax with a % greater than 0 shows below the % ("This operation
charges no tax: its rate must be 0 %.") and nothing is saved.
Involved: INVOICE-F01

### TAX-F06 Add an equivalence surcharge to a rate
Status: done
Actor: owner, administrator, manager
Screen: Rules
Steps:
1. Create the category's main rule first (TAX-F04): it is the root.
2. In Rules tap **+**, choose the same Country, Region and Category and type the surcharge's % (for example
   5.2).
3. Choose the Type "Surcharge"; in "Root rule (component of)" choose the root and type the "Component label"
   (for example "Equivalence surcharge").
4. Tap "Add".
In: the surcharge, the root it hangs from and its label.
Out: the component rule (`tax.rule.created`). The sales of that category carry the combined rate (21 + 5.2
= 26.2) with the breakdown by component; the qualification and the tax family are still the root's.
If it fails: "The component could not be created: it must hang from a root rule with the same country,
region and category, and a root that charges no tax admits no component with a rate.", below the root rule.
A component of a component does not exist: there is only one level.
Involved: INVOICE-F01, SALE-F01

### TAX-F07 Change a rate from a date
Status: done
Actor: owner, administrator, manager
Screen: Rules
Steps:
1. In the row of the rule in force tap "Set end date".
2. Type the last day it applies (the day before the new rate starts) and tap "Save end date".
3. Create the new rule (TAX-F04) with "Valid from" the next day.
4. The table shows both with their dates; from the day of the change new sales use the new one.
In: the end date (included) and the data of the new rule.
Out: the rule with its end date (`tax.rule.ended`). A sale already made keeps its rate: the sale line keeps
its copy. An invoice already issued does not change. A rule is not edited: that action does not exist.
If it fails: an end before the start of the rule: "That rule cannot end before the day it starts."; an end
that runs into another active rule of the same slot, the overlap notice. Two consecutive periods (one ends
on 31/12, the other starts on 1/1) do not overlap. An end in the past leaves a gap without a rate: the sales
of that category are refused until the next one is created.
Involved: INVOICE-F01, INVOICE-F04, SALE-F01

### TAX-F08 Deactivate and restore a rule
Status: done
Actor: owner, administrator, manager
Screen: Rules
Steps:
1. In the row tap "Deactivate" and confirm in "Deactivate tax rule" with "Deactivate rule" ("The rule will
   no longer apply to new transactions. Previously issued fiscal documents will not change.").
2. The rule disappears from the table; to see it, choose Status "Deactivated".
3. To get it back, in that view tap "Restore" (without confirmation).
In: the chosen rule.
Out: the rule inactive or active (`tax.rule.deactivated` / `tax.rule.activated`). Its %, its country, its
category, its dates and its components do not change. Deactivating a root also stops applying its
components; if it was the category's only root, the sales of that category are refused. Deleting a rule
does not exist.
If it fails: a rule that no longer exists: "This tax rule no longer exists."; deactivating one already
deactivated or restoring one already active: "That rule is already deactivated." / "That rule is already
active."; restoring one that now overlaps another active one, the overlap notice.
Involved: SALE-F01

### TAX-F09 Repair a rule that charges a rate where it should not
Status: discarded — in the current product it served to fix rules saved before they were forbidden; here no door (screen, API, batch or assistant) lets a rule that charges no tax be created with a %, nor a component with a rate under it, so there is nothing to repair
Actor: owner, administrator, manager
Screen: Rules
Steps:
1. Whoever saves an exempt, not subject or reverse-charge rule with a % greater than 0 sees the refusal
   below the % (TAX-F05).
2. Whoever hangs a component with a rate from a root that charges no tax sees the refusal below the root
   rule (TAX-F06).
In: nothing.
Out: nothing: the incoherent rule never gets saved.
If it fails: does not apply.
Involved: none

### TAX-F10 Resolve overlapping rules
Status: discarded — here no door lets two active rules of the same country, region and category be in force on the same day, not even if two people save at the same time: the overlap is solved before saving, with TAX-F07 or TAX-F08
Actor: owner, administrator, manager
Screen: Rules
Steps:
1. Whoever saves a rule that would overlap another active one of the same country, region and category sees
   the refusal in "Valid from" (TAX-F04).
2. They set an end date on the one in force (TAX-F07) or deactivate it (TAX-F08) and save the new one again.
In: nothing.
Out: nothing: the overlap never gets saved.
If it fails: does not apply.
Involved: none

### TAX-F11 Set up a business in the Canary Islands, Ceuta or Melilla
Status: done
Actor: owner, administrator, manager
Screen: Settings and Rules
Steps:
1. In **Taxes → Settings** choose the business's "Tax region": "Canary Islands (IGIC)", "Ceuta (IPSI)" or
   "Melilla (IPSI)", and tap "Save": "Tax region saved." shows. The "Country" is the one of the business's
   ERPlora account.
2. In Rules create one rule for each category you sell: Country "Spain", the Region (ES-CN Canary Islands,
   ES-CE Ceuta or ES-ML Melilla), the region's % and the Type "IGIC (Canary Islands)" or "IPSI
   (Ceuta/Melilla)" (TAX-F04).
3. Create a rule of the region for each category you sell: in the Canary Islands, Ceuta and Melilla the
   national VAT never applies, so a category without a rule of its region cannot be charged until it has
   one. The VAT rules do not need to be deleted: they are used again with "Whole country (VAT)".
4. Make a test sale: the ticket and its breakdown say the region's tax ("IGIC 7%"), and the invoice declares
   it the same way.
In: the business's tax region and a regional rate per category that the person sets (none is seeded on
purpose).
Out: the saved region, which from that moment all sales, invoices, the calculation of TAX-F18 and the rate
that Categories and the sections of Sales show use: only the region's rule counts (the national one, of
VAT, never) and the tax family (IGIC, IPSI) is the rule's. A line without a category or a rule —a rate typed
by hand on an invoice, or a sale whose rule no longer exists— is declared with the tax of its region: IGIC
in the Canary Islands, IPSI in Ceuta and Melilla, VAT elsewhere (a sale's, the region it was charged with).
Event `tax.settings.updated`, which recalculates the open checkout.
If it fails: a region that has no taxes of its own in the business's country is refused under "Tax region"
("This region has no taxes of its own in your business's country: choose one of its tax territories, or
none."); a category without a rule of its region is never charged at the national VAT, just like a category
without any rule: the till does not let it be charged ("… cannot be charged: no tax rule applies to its tax
category … here."), the invoice refuses it below its line ("No tax rule applies today to the tax category
…") and Categories and the sections of Sales show no rate for it; it is fixed by creating its rule (step 2).
With "Whole country (VAT)", the regional rules are never used. Whoever only views taxes sees the region, but
does not change it.
Involved: INVOICE-F01, INVOICE-F03, SALE-F01

### TAX-F12 Create several rules at once
Status: done
Actor: owner, administrator, manager (through the assistant or through the API with their session; an API key does not reach it)
Screen: none (API)
Steps:
1. Up to 100 root rules are sent at once (for example, "the VAT rates of Spain 2026").
2. Each rule goes through the same checks as a single one (TAX-F04, TAX-F05), also the overlap with the
   others of the same batch.
3. If all are valid, all are saved; if any fails, none is saved and the answer says which rule failed and
   why.
In: the list of rules.
Out: the created rules; one `tax.rule.created` for each one.
If it fails: each refusal carries the rule's position (`rules.3.rate_pct`…). Components do not go by batch:
they are created one by one (TAX-F06), because they need their root already saved.
Involved: none

### TAX-F13 View the category aliases
Status: done
Actor: owner, administrator, manager, employee
Screen: Aliases
Steps:
1. Open **Taxes → Aliases**.
2. Search by alias or category, or filter by Category or Source.
In: nothing; it reads the business's aliases.
Out: nothing (read only).
If it fails: the table's notice with "Retry".
Involved: none

### TAX-F14 Teach a category alias by hand
Status: done
Actor: owner, administrator, manager
Screen: Aliases
Steps:
1. In Aliases tap **+**.
2. Type the Alias (the text that comes from outside, for example `comida`), type part of the Category's
   name and choose it from the list, and choose the Source ("Learned" at first).
3. Tap "Add".
In: the outside text, the category and the source that the person chooses.
Out: the alias, kept in lower case and without extra spaces, unique in the business (`tax.alias.created`).
The next Inventory import understands it, however it is written.
If it fails: an alias that already exists: "That alias already exists." below the Alias; a category that
does not exist, below the Category. Nothing is saved.
Involved: INVENTORY-F09

### TAX-F15 Tell the Inventory importer which category a text is
Status: done
Actor: system
Screen: none
Steps:
1. Whoever imports a file of products with a VAT or category column does nothing in Taxes.
2. Inventory asks about each text. Taxes turns it into lower case without extra spaces and compares it, in
   this order, with the keys of the categories, with their names (also the ones translated into Spanish and
   English) and with the aliases.
3. What does not match is asked by Inventory to the person; their answer is kept as a learned alias or as a
   new category (TAX-F02, TAX-F14).
In: the text, from Inventory.
Out: the category's key and why it matched (key, name or alias), or nothing.
If it fails: a text that does not match gives back "nothing", never a similar category.
Involved: INVENTORY-F09, INVENTORY-F10

### TAX-F16 Seed the factory catalogue when turned on
Status: done
Actor: system
Screen: none
Steps:
1. The first time the business turns on Taxes (or when it is born with a vertical that brings it), the app
   seeds the catalogue; nothing is done by hand.
2. It is checked in Categories and Rules.
In: nothing.
Out: 11 system categories (`restaurant.food`, `restaurant.drink`, `restaurant.alcohol`,
`restaurant.delivery`, `retail.alcohol`, `service.generic`, `service.health`, `service.education`,
`product.generic`, `product.reduced`, `product.super_reduced`), 18 factory aliases and 11 rules of Spain,
for the whole country and from 01/09/2012: 21 % (`product.generic`, `service.generic`, `retail.alcohol`),
10 % (`restaurant.food`, `restaurant.drink`, `restaurant.alcohol`, `restaurant.delivery`,
`product.reduced`), 4 % (`product.super_reduced`) and exempt with cause E1 at 0 % (`service.health`,
`service.education`). Alcoholic drinks served to be consumed on the premises are hospitality, at 10 %
(art. 91.Uno.2.2º of Ley 37/1992): `restaurant.alcohol`; the ones sold to take away or for delivery, at
21 %: `retail.alcohol` (aliases `takeaway_beer` and `takeaway_wine`). There are no rules of IGIC, IPSI,
surcharge or of any other country: an invented rate would be declared.
If it fails: it never overwrites a row that already exists nor duplicates anything.
Involved: none

### TAX-F17 Warn that rates are missing for the business's country
Status: done
Actor: owner, administrator, manager
Screen: Home, Categories, Rules and Aliases
Steps:
1. On the **Home**, while no active root rule is in force today, "Finish setting up your business" brings
   "Your taxes" ("Set up the VAT rates of the country you sell in so the till can price a sale."),
   "Important", to whoever can manage taxes. "Set up" takes you to the **Rules** tab of Taxes.
2. Open **Taxes**: meanwhile, at the top of Categories, Rules and Aliases the same "Your taxes" notice
   shows, only for whoever can manage taxes.
3. Tap "Set up": it takes you to the Rules tab, where the missing one is created with **+** (TAX-F04). In
   Rules the notice carries no button.
4. As soon as an active root rule is in force today, the notice disappears by itself and the step of the
   Home is "Done" without a reload.
In: the rules of any country (neither the notice nor the step look at the business's yet).
Out: how many rules apply today and whether taxes are set up. It does not block selling by itself. If the
last rule in force ends (TAX-F07) or is deactivated (TAX-F08), the step of the Home goes back to pending by
itself, and restoring it (TAX-F08) or creating another one (TAX-F04, TAX-F12) makes it "Done" again.
Changing the tax region (TAX-F11) does not move it.
If it fails: a single rule of any category is enough to consider it done. Today it counts the rules of any
country and of any region: a Canary Islands business without any IGIC rule does not see the notice,
although the till explains the reason when charging and the help of Settings says so (TAX-F11). An exempt or
IGIC rule also counts: a business that only sells exempt services is properly set up.
Involved: BASE-F01

### TAX-F18 Calculate the tax of an amount
Status: done
Actor: employee, manager, administrator, owner (through the assistant or through the API with their session; an API key does not reach it)
Screen: none (API)
Steps:
1. The amount (in cents), the category and, if needed, the country, the region, the date and whether the
   amount already carries the tax are given.
2. The base, the tax amount, the total, the combined rate, the qualification, the applied rule and the
   breakdown by component are obtained.
In: amount in cents, category, country (at first, the business's with its tax region, TAX-F11), region and
date (at first, today; in phase 1, today in Madrid). If a country is given, it calculates in that country
and in the region given, without the business's region.
Out: only the answer; it saves nothing and announces nothing. Without the tax included, each component's
tax is base × rate rounded to the cent, half up. With the tax included, the base is the amount ÷ (1 +
combined rate) rounded and the tax is what is left, so what is charged does not move a cent (the last
component absorbs the adjustment). It is the same calculation with which Sales closes the ticket and
Invoicing squares the tax.
If it fails: without an applicable rule, "No tax rule applies to this category in this country."; a guessed
0 % is never charged, unless whoever asks requests it explicitly (and then, with the tax of their region:
IGIC in the Canary Islands, IPSI in Ceuta and Melilla). Without an amount or without a category, below its
field. If the rules cannot be read, the calculation stops without guessing.
Involved: INVOICE-F01, INVOICE-F03, SALE-F01, SALE-F09

### TAX-F19 Hand the rules and the categories to Sales, Invoicing, Inventory and Services
Status: done
Actor: system
Screen: none
Steps:
1. Whoever charges a ticket, issues an invoice or saves a product does not open Taxes.
2. Sales and Invoicing resolve the rate of each line with the same calculation of TAX-F18, inside their own
   operation: if the rules cannot be read, the operation is refused before writing anything.
3. Inventory, Services, Sales (its open-price sections), Menus and combos and Modifiers list the categories
   to choose them, by the name in the language of whoever looks and with their rate in force.
In: what is already saved in Rules and Categories.
Out: what the sale line freezes: category, combined rate, country, region and rule. A line with a category
and without a rule is refused, it never falls to 0 %: the till says "… cannot be charged: no tax rule
applies to its tax category … here." and the invoice, "No tax rule applies today to the tax category …"
(TAX-F11). What to do with a line without a category is up to Sales.
If it fails: the cashier does not charge with a guessed rate.
Involved: COMBO-F09, INVENTORY-F01, INVENTORY-F02, INVOICE-F01, INVOICE-F03, MODIFIER-F07, SALE-F01,
SALE-F07, SERVICE-F01

## Services: what goes in and what comes out

Everything can be asked for through the screens, the assistant (by voice or text, with the person's own
session) and the API, with the same rules and the same permissions. A business's API key reaches less, the
same as in the current product: seeing the categories, the rules and the aliases, reading a text as a
category, and setting an end date on a rule or restoring it. Designed for voice: a
category is named by its key, by its name (in Spanish or in English) or by an alias ("Restaurant — food",
"food", `restaurant.food`), and a rule by its id or by its country, region and category ("the VAT one for
food in Spain": when deactivating it or setting its end date, the one in force today; when restoring it,
the last deactivated one).

### What it offers: queries (they read, they change nothing)

| What it gives | Who can | Flows | Service |
|---|---|---|---|
| The categories, with search, origin filter, pages (up to 100) and their rate in force today in a country and region | view | F01, F19 | `tax.category.list` |
| A category by its key, with its translated name | view | F02, F19 | `tax.category.get` |
| The rules, with search, filters (country, region, category, type, qualification, status) and pages | view | F03 | `tax.rule.list` |
| How many root rules apply today in the business's country and whether taxes are set up (the notice and the step "Your taxes" of the Home) | view | F17 | `tax.rule.status` |
| The root rules a component can hang from in a country, region and category: the same ones the creation accepts (also a root that starts in the future; one without tax, only for a component at 0 %) | view | F06 | `tax.rule.parent_candidates` |
| The countries in which the business has rules (all, active or deactivated), for the Country filter | view | F03, F11 | `tax.rule.countries` |
| The aliases, with search, filters (category, source) and pages | view | F13, F15 | `tax.alias.list` |
| The category that matches an outside text, and why it matched | view | F15 | `tax.alias.resolve` |
| The tax of an amount: base, tax, total, rate, qualification and breakdown | view | F18, F19 | `tax.rate.calculate` |
| The business's country and tax region, the tax of that region (`tax_kind`: VAT, IGIC or IPSI) and the regions it can choose | view | F11 | `tax.settings.get` |

Categories, rules, aliases, the setup status, the roots of a component, the countries and the settings can
be followed live.

### What it offers: actions (they change data)

| What it does | Who can | Flows | Service |
|---|---|---|---|
| Creates a custom tax category | manage | F02, F15 | `tax.category.create` |
| Creates a rule (root or component) | manage | F04, F05, F06, F11 | `tax.rule.create` |
| Creates up to 100 root rules, all or none | manage | F12 | `tax.rule.bulk_create` |
| Sets the end date of a rule | manage | F07 | `tax.rule.end` |
| Deactivates a rule | manage | F08 | `tax.rule.deactivate` |
| Restores a rule | manage | F08 | `tax.rule.activate` |
| Creates a learned alias | manage | F14, F15 | `tax.alias.create` |
| Saves the business's tax region (or the whole country) | manage | F11 | `tax.settings.update` |

### What it announces

| Notice | When | What it carries | Service |
|---|---|---|---|
| New category | Creating a category | Which one (`id`, `key`) | `tax.category.created` |
| New rule | Creating a rule (also by batch, one per rule) | Which one, its country, region, category and % | `tax.rule.created` |
| Rule with an end date | Setting the end date | Which one and its end date | `tax.rule.ended` |
| Rule deactivated | Deactivating | Which one | `tax.rule.deactivated` |
| Rule restored | Restoring | Which one | `tax.rule.activated` |
| New alias | Creating an alias | Which one, its text and its category | `tax.alias.created` |
| Tax region changed | Saving another region | The country and the region (empty = the whole country) | `tax.settings.updated` |

What each notice refreshes: the categories, with "new category", with the four of rules and with "tax region
changed" (the rate in force shows in the table); the rules and the setup status, with the four of rules and
the region's; the settings, with "tax region changed"; the aliases, with "new alias". In Sales, the open
checkout and the rate of the sections are recalculated with the four of rules and with the region's; in
Invoicing, the general rate a line of the manual invoice starts with, too.

### What it reacts to and what it needs from other apps
Nothing: Taxes depends on no app and reacts to no notice of others.

### Who uses it

| App | What for | Service |
|---|---|---|
| Inventory | Choosing the tax category of a product or of a category, with its rate; recognising the tax column of a CSV and, when importing, learning a text or creating the missing category | `tax.category.list`, `tax.alias.resolve`, `tax.alias.create`, `tax.category.create` |
| Services | Choosing the tax category of a service and the default one, with its rate | `tax.category.list` |
| Sales | The rate and the qualification of each line when charging, with the calculation of TAX-F18, and the rate of each section, in the business's country and tax region; choosing the category of a section; the name of the region's tax ("VAT", "IGIC", "IPSI") | `tax.rate.calculate` (its function, inside its operation), `tax.category.list`, `tax.settings.get` |
| Invoicing | The rate and the qualification of each line with a category; the tax of a line without a rule, its region's; the name of the region's tax | `tax.rate.calculate` (its function, inside its operation), `tax.settings.get` |
| Menus and combos, Modifiers | Choosing the own tax category of a menu or of an option, with its rate | `tax.category.list` |

### Who can do what

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| View categories, rules, aliases and the tax region, and calculate | yes | yes | yes | yes | `tax.view` |
| Create categories, rules and aliases; set an end date, deactivate and restore rules; change the tax region | yes | yes | yes | no | `tax.manage` |

The roles come from the SaaS with a prefix (`hub_owner`, `hub_admin`, `hub_manager`, `hub_employee`); the
cashier of the current product is an employee.
