<!-- generated from WORKBOOK.md sha256:dedbe7f256082f6730ff05acbcf83e1b175af3573ade6a4045eeb10739fe0591 -->

## What it is for and who it is for

Modifiers is the catalogue of the choices that go with a dish: the "doneness of the meat", the
"extra cheese", the size, "no onion". It is arranged in **groups**:

- each group says **how many options must be chosen**: a minimum (1 or more makes it **required**) and a
  maximum (0 is no ceiling), and whether **the same option can be repeated** ("double cheese");
- each **option** carries its **price supplement**: more, less or free; it can come **chosen by
  default** and, if it is taxed at a different VAT than the dish (a soft drink inside a menu), its **own
  tax category**;
- a group is **linked to products or to categories** of Inventory, and **it is shared**: the same
  "Sauces" group serves every burger and the whole "Meats" category.

It is **Sales** that asks for the groups at the till, charges the supplement and sends it to the kitchen:
this app keeps the catalogue, says which groups each item carries and is **the only source of the
price** of the supplement: whatever the browser sends does not count.

Who uses it:

- The **owner**, the **administrator** and the **manager** create, change and delete groups and
  options, and link or unlink them.
- The **employee** (waiter, cashier) looks up the groups; the one who lives it every day is them, at the
  till.

It is not a product variant (an option carries no stock or cost and does not take away stock) nor a
menu at a closed price (that is Menus).

## Reference adopted

Checked against the market sweep of the current module (20/08/2026) and against the round of this port
(15/10/2026, skill `market-decision`); this is adopted, nothing more:

- **Square** (modifiers): the group is an object of its own and reusable, with a minimum and a maximum of
  selections; an option can come **preselected**; it is assigned to many items.
- **Toast** (modifier groups): a kitchen name different from the commercial one; the supplement can be a
  surcharge or a discount; **default** options; an order missing a required group is not sent.
- **Clover** (groups): there is no "required" box: required is "minimum 1 or more".
- **Lightspeed Restaurant**: the group hangs from an item **or from a category**; a modifier is not a
  variant and does not move stock; it allows quantities of the same option.
- **LS Central** (infocodes): the supplement with another VAT rate is its own sales line.
- **Revo XEF** and **Ágora** (hospitality POS in Spain): groups of "modifiers"/"supplements" with a
  minimum, a maximum and a default option, edited in the group's own form with its items.
- **Loyverse** and **Odoo PoS**: the options and the items they apply to are edited on screen, not by
  another way; the extra price is set by the catalogue.

## Before you start

- Modifiers needs **Inventory** (the products and categories a group is linked to) and **Taxes** (the
  own tax category of an option). Turning Modifiers on turns both on.
- Without **Sales** nobody asks for the groups at the till; without **Kitchen** the kitchen ticket does
  not carry them. Both talk to Modifiers through its services, never through its tables.
- Supplements go in **euros with cents** on screen and in **whole cents** through the API; they can be
  negative (a discount) or zero (free).

Initial setup, step by step:

1. Open **Modifiers** and tap "New group": name and, if needed, kitchen ticket name, minimum, maximum
   and whether it repeats (MODIFIER-F02).
2. Open the group (tap its row) and add its options with their supplement (MODIFIER-F04).
3. In the same sheet, in "Applies to", link it to the products or categories that carry it
   (MODIFIER-F05).
4. At the till, tap one of those items: the sheet comes up with the group, its rule and the price of each
   option (MODIFIER-F06).

## Screens

### Modifiers
Menu **Modifiers** (a single entry). At the top, the title "Modifiers". Below, the table of groups
with the "Search…" box (it searches by name and by kitchen ticket name): **Name** (sorted and
filtered), **On the kitchen ticket** (the kitchen name; empty, the commercial one), **Choice** (sorted
by the minimum and filtered by Required or Optional), **Options** (how many it has), **Applies to** (to
how many products and categories) and **Order**; the last three are sorted too. The Choice column says
the rule: "Optional" or "Required (min. N)", with " · max. N" if there is a ceiling and " · repeats" if
an option can be repeated. By order and name; pages of 50.

Whoever can manage sees **"New group"** and, on each row, **Edit** and **Delete**. Tapping a row opens
the group's sheet, for everyone.

### Group sheet
Title "Group — {name}" and its rule. Two sections:

- **Options**: each one with its name, its kitchen ticket name (if different), its supplement ("+€1.00",
  "-€0.50" or "Free"), its own tax category if it has one and the "By default" mark. Whoever manages
  sees "Add option" and, on each one, Edit and Delete. Empty: "This group has no options yet.".
  If it has fewer options than the minimum asks for (and they cannot repeat), a notice says so: the till
  could not complete it.
- **Applies to**: each product ("Product · Burger (HAM-01)") or category ("Category · Meats") it is
  linked to; whoever manages sees "Add product or category" and, on each one, "Stop applying". Empty:
  "This group does not apply to anything yet: it will not show in the till.".

20 at a time, with "Load more".

### Forms
- **Group** ("New group" / "Editing group — {name}"): Name, "Kitchen ticket name", "Minimum (1 or more
  = required)", "Maximum (0 = no ceiling)", "An option can be chosen more than once" and Order.
- **Option** ("New option" / "Editing option — {name}"): Name, "Kitchen ticket name", "Supplement (€)"
  (negative is a discount; empty or 0, free), "Own tax category" (searched; empty = the dish's), Order
  and "Chosen by default".
- **Link** ("Apply «{group}» to…"): Product or Category, and the search box of each one.
- **Delete** group or option and **Stop applying**: they ask for confirmation saying what goes with it.

## States of each screen

| State | What the person sees |
|---|---|
| Loading | "Loading…" while the first result arrives. |
| Empty | "No modifier groups yet." (or "No results" with a search or a filter), with "New group" if they can create; in the sheet, the empty states of each section. |
| Error | The table's notice with "Retry"; a refusal of a form shows inside it, next to its field. |
| Reconnecting | What is painted stays; a strip warns "Reconnecting…" until the connection comes back. |
| App inactive (`app_inactive`) | "This app is not active in this business". |
| No permission | What they cannot do does not appear; if they arrive through another door, "You do not have permission". |

## Flows

| ID | Flow | Status |
|---|---|---|
| MODIFIER-F01 | Look up and search the groups | done |
| MODIFIER-F02 | Create a group | done |
| MODIFIER-F03 | Change or delete a group | done |
| MODIFIER-F04 | Add, change or remove the options of a group | done |
| MODIFIER-F05 | Link a group to products or categories, and unlink it | done |
| MODIFIER-F06 | Choose the options when selling an item | done |
| MODIFIER-F07 | Charge the supplement: price and VAT | done |
| MODIFIER-F08 | Have the supplement show on the kitchen ticket | done |
| MODIFIER-F09 | Unlink the groups of a product or a category that is deleted | done |

### MODIFIER-F01 Look up and search the groups
Status: done
Actor: owner, administrator, manager, employee
Screen: Modifiers
Steps:
1. Open **Modifiers**.
2. Read the table: name, kitchen ticket name, choice rule, how many options, to how many products and
   categories it applies and order.
3. To find one, type in "Search…" (name or kitchen ticket name), sort by a column or filter by name
   or by whether it is required or optional.
In: the groups of the business.
Out: nothing; it only reads.
If it fails: the table's notice with "Retry"; without groups, "No modifier groups yet.".
Involved: none

### MODIFIER-F02 Create a group
Status: done
Actor: owner, administrator, manager
Screen: Modifiers
Steps:
1. Tap "New group".
2. Type the Name (required, unique in the business regardless of case: "Sauces" and "sauces" are
   the same group).
3. If the kitchen ticket must say something else, type "Kitchen ticket name"; empty, the kitchen reads
   the name.
4. Set the Minimum (1 or more makes it required; 0, optional), the Maximum (0 is no ceiling; if it is
   not 0, it cannot be below the minimum), whether an option can be repeated and the Order in which it
   shows at the till.
5. Tap "Create": the form closes and the group shows in the table. It does not show at the till yet:
   its options (F04) and where it applies (F05) are missing.
In: what the person types.
Out: the group (announces: group created). It creates no options or links.
If it fails: an empty name or one of more than 255 characters, a minimum or maximum outside 0–50 or a
maximum below the minimum show under their field; a name another group already has, "There is already
a group with that name." under the Name. What was typed stays.
Involved: none

### MODIFIER-F03 Change or delete a group
Status: done
Actor: owner, administrator, manager, assistant
Screen: Modifiers
Steps:
1. On the group's row tap **Edit**, change what is needed and tap "Save". What is not touched stays as
   it was.
2. To delete it, tap **Delete**: the confirmation says how many options and how many links go with
   it. Confirm.
In: the group (by its id or its name) and the new fields.
Out: the group changed (announces: group changed) or deleted with its options and its links, in a
single operation (announces: group deleted). What was already ordered or sold does not change: Sales
freezes the supplement in the line.
If it fails: the same refusals as when creating; lowering the maximum below the options that already
come by default, "This group has more options chosen by default than its maximum.". A group that does
not exist, "This group does not exist.".
Involved: SALE-F11

### MODIFIER-F04 Add, change or remove the options of a group
Status: done
Actor: owner, administrator, manager, assistant
Screen: Modifiers (group sheet)
Steps:
1. Open the group and, in Options, tap "Add option".
2. Type the Name (unique within the group) and, if needed, the kitchen ticket name.
3. Type the Supplement in euros: positive charges more, negative is a discount, empty or 0 is free.
4. Only if the option is taxed differently from the dish, choose its own tax category; empty, it
   inherits the dish's.
5. Tick "Chosen by default" if the till must bring it already ticked. In a group of maximum 1, ticking
   another one unticks the previous one; with another maximum, there cannot be more default options than
   the maximum.
6. Tap "Create". To change it, **Edit**; to remove it, **Delete** (it asks for confirmation).
In: the group, name, kitchen ticket name, supplement, own tax category, order and whether it is the
default.
Out: the option (announces: option created, changed or deleted). Deleting it takes it out of the
catalogue: what was already ordered keeps its frozen copy, also on the kitchen ticket.
If it fails: an empty name or one repeated in the group, a supplement that is not an amount, a tax
category that does not exist in Taxes or more default options than the maximum show next to their
field. An option with its own tax category is charged on a separate line, which cannot be worth zero or
less: "An option with its own tax category is billed on a line of its own: its supplement must be more
than zero.". A group holds up to 100 options.
Involved: SALE-F11

### MODIFIER-F05 Link a group to products or categories, and unlink it
Status: done
Actor: owner, administrator, manager, assistant
Screen: Modifiers (group sheet)
Steps:
1. Open the group and, in "Applies to", tap "Add product or category".
2. Choose Product or Category and search for it by its name (or the SKU, for a product).
3. Tap "Apply". The same group can hang from many products and categories, and a product can carry
   several groups: they show at the till by their Order and their name.
4. To remove it, tap **Stop applying** on that row (it asks for confirmation); afterwards it can be
   linked again.
In: the group and the product or the category, from Inventory (by its id, or by its name or SKU).
Out: the link (announces: link made or removed). At the till, the item asks for its groups and those of
**all** its categories, each group only once.
If it fails: a product or a category that does not exist or is deleted, "This product does not exist in
this hub." or "This category no longer exists."; a link that already exists, "This group already
applies there.".
Involved: INVENTORY-F01, INVENTORY-F06

### MODIFIER-F06 Choose the options when selling an item
Status: done
Actor: employee, manager
Screen: Sales: Sell
Steps:
1. At the till, tap an item that has groups (its own or those of any of its categories): a sheet opens
   with its name. Without groups, the item goes straight in.
2. Each group says its rule: "Choose N" if it asks for exactly N, "Choose N to M" if it asks for a
   minimum and lets you reach a ceiling, "Choose at least N" if it asks for a minimum without a ceiling,
   "Up to N" if it only has a ceiling, "Optional" if not; each option carries its supplement with its
   sign if it is not zero ("+€1.00") and the default options already come ticked.
3. Tap the options: in a group of a single one, tapping another one changes it and tapping the same one
   removes it; in a group that repeats, each option goes on its own row, with its whole name, and each
   tap adds one to the counter ("× 2") that "−" takes away; on reaching the ceiling, the next tap warns
   that the group is full.
4. While a required group is not complete, the button says "Choose an option to continue" and tapping
   it points at that group. With everything chosen, it says "Add · <price>" with the supplements already
   added.
5. Tap "Add": the line goes in with the options in the order they were tapped and its price.
In: the groups and options of this item (service "groups of a product").
Out: the line with the chosen options; from the till only the options travel, never their price.
If it fails: a group without options is not asked. A group linked to the product and to its category
shows only once. If the groups cannot be read, "The options of this product could not be read. Try
again." and nothing goes in.
Involved: SALE-F11

### MODIFIER-F07 Charge the supplement: price and VAT
Status: done
Actor: system
Screen: none
Steps:
1. When adding the line (to a check or to a direct sale), Sales asks Modifiers to **check and
   price** the chosen options for that item, with the session of whoever sells.
2. Modifiers checks that each option belongs to a group of that item, that each group is between its
   minimum and its maximum and that nothing repeats where it cannot; it returns each option with its
   catalogue price, its names and its tax category.
3. An option without its own tax category, or with the dish's, is added to the price of the line; one
   with another category is charged on a line of its own, child of the dish's, with its rate.
4. Sales freezes that copy in the line: changing or deleting the option afterwards does not change what
   that table pays.
5. When charging, the receipt names the options under the dish and each option with another tax
   category comes out as a line of its own ("+ Soda"), for each dish, with its base and its tax: what
   the check says is what the card pays.
In: the item and the chosen options, in order.
Out: the options with their price, the total added to the line and which ones go on a line of their
own; an option chosen twice counts twice; none moves stock.
If it fails: an option that is not of that item, "This option is not offered with this product."; a
group below its minimum, "Choose at least N in «Group»."; above its maximum, "Choose at most N in
«Group»."; an option repeated where it cannot be, "«Option» cannot be chosen more than once."; some
discounts that would take the dish below zero, "These options take the price of «Dish» below zero.";
an option with a supplement on an item sold by weight or by measure, "«Item» is sold by weight or
measure: an option with a supplement cannot go with it.". The line does not go in.
Involved: SALE-F11

### MODIFIER-F08 Have the supplement show on the kitchen ticket
Status: done
Actor: system
Screen: none
Steps:
1. When pricing the options (F07), Modifiers also gives the **kitchen text**: the kitchen ticket name of
   each option (or the name, if it has none), in the order chosen, separated by ", ".
2. Sales freezes it in the line and sends it with the kitchen ticket; Kitchen paints it under the dish,
   on the kitchen screen ("+CHEESE, -ONION") and on paper, one option per row.
3. Renaming or deleting the option, or its group, after ordering it does not change what the kitchen
   already has.
In: the chosen options.
Out: the kitchen text ("+CHEESE, -ONION").
If it fails: nothing that is not F07: if the pricing fails, the line does not go in.
Involved: KITCHEN-F07, SALE-F20

### MODIFIER-F09 Unlink the groups of a product or a category that is deleted
Status: done
Actor: system
Screen: none
Steps:
1. Someone deletes a product or a category in Inventory.
2. A few seconds later, Modifiers unlinks the groups that hung from it (announces: link removed, one
   per group); the group's other links stay.
In: Inventory's notice (product deleted, category deleted).
Out: the links removed. While the notice arrives, a link to something deleted is no longer seen in the
group's sheet nor asked at the till.
If it fails: repeating the notice changes nothing; the deletion of one business never removes the
links of another.
Involved: INVENTORY-F04, INVENTORY-F07

## Services: what goes in and what comes out

Everything can be asked for through the screens, the assistant (by voice or by text, with the person's
own session) and the API, with the same rules and the same permissions. Designed for voice: a group is
named by its id or its name ("group Sauces"), an option by its id or its name and its group ("option No
onion of Extras"), a product by its id, its SKU or its name and a category by its id or its name. If a
name fits several, it is refused saying which ones (409 `*_ambiguous`).

### What it offers: queries (they read, they change nothing)

| What it gives | Who can | Flows | Service |
|---|---|---|---|
| The groups, with search, filters (name, required), order and pages (up to 100) | view | F01 | `modifier.group.list` |
| A group by its id or its name | view | F03 | `modifier.group.get` |
| The options, of a group or all of them, with search and pages | view | F04, F07 | `modifier.option.list` |
| The links, of a group, of a product or of a category, with pages | view | F05 | `modifier.link.list` |
| The groups with their options of a product (its own and those of all its categories, once each) | view | F06 | `modifier.group.for_target` |
| The check and pricing of some chosen options for a product: price, names, tax category, total to add and kitchen text | view | F07, F08 | `modifier.selection.resolve` |

The groups, a group, the options, the links and the groups of a product can be followed live.

### What it offers: actions (they change data)

| What it does | Who can | Flows | Service |
|---|---|---|---|
| Creates a group | manage | F02 | `modifier.group.create` |
| Changes a group (what is not sent stays) | manage | F03 | `modifier.group.update` |
| Deletes a group with its options and links | manage | F03 | `modifier.group.delete` |
| Adds an option to a group | manage | F04 | `modifier.option.create` |
| Changes an option (what is not sent stays) | manage | F04 | `modifier.option.update` |
| Deletes an option | manage | F04 | `modifier.option.delete` |
| Links a group to a product or a category | manage | F05 | `modifier.link.attach` |
| Unlinks a group from a product or a category | manage | F05 | `modifier.link.detach` |

### What it announces

| Notice | When | What it carries | Service |
|---|---|---|---|
| Group created, changed or deleted | F02, F03 | The group (`id`, `name`) | `modifier.group.created`, `.updated`, `.deleted` |
| Option created, changed or deleted | F04 | The option, its group, its name and its supplement | `modifier.option.created`, `.updated`, `.deleted` |
| Link made or removed | F05, F09 | The group and the product or the category | `modifier.link.attached`, `.detached` |

### What it reacts to

| Notice | From | What it does | Service |
|---|---|---|---|
| Product deleted (`inventory.product.deleted`) | Inventory | Unlinks the groups of that product (F09) | `modifier.link.drop_product` |
| Category deleted (`inventory.category.deleted`) | Inventory | Unlinks the groups of that category (F09) | `modifier.link.drop_category` |

### What it needs from other apps

- **Inventory** (requirement): its products and categories, which each link points at, and the
  categories of each product, to know which groups it carries at the till.
- **Taxes** (requirement): the own tax category of an option.

### Who uses it

| App | What for | Service |
|---|---|---|
| Sales | Asks for the groups of an item at the till and checks and prices what was chosen when adding the line (SALE-F11; "Contract with Sales") | `modifier.group.for_target`, `modifier.selection.resolve` |
| Kitchen | Does not read Modifiers: it receives from Sales the frozen options of each line (KITCHEN-F07; "Contract with Kitchen") | — |

### Who can do what

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| See groups, options and links; ask for the groups of a product and price a choice | yes | yes | yes | yes | `modifier.view` |
| Create, change and delete groups and options; link and unlink | yes | yes | yes | no | `modifier.manage` |

The roles come from the SaaS with a prefix (`hub_owner`, `hub_admin`, `hub_manager`, `hub_employee`); the
cashier of the current product is an employee.
