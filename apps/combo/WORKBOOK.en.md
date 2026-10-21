<!-- generated from WORKBOOK.md sha256:395517856619da028811ca1f4e57edbb4b0b5d3c37285f1ea79688f49d60450f -->

## What it is for and who it is for

Menus and combos keeps the composite items that are sold at a **closed price**: the menu of the day
("starter + main + dessert + drink for €13.50"), the kids' menu or the "sandwich + drink" to take
away. Each menu has **courses** (Starter, Main, Drink…), each one with how many picks it asks for at
least and at most, and each course offers **choices**: real products of Inventory's catalogue, with a
**supplement** if substituting costs more (or less).

Who uses it:

- The **owner**, the **administrator** and the **manager** set up the menus: price, how it is
  sold, courses, choices, supplements, order and what is sold out today.
- The **employee** looks them up and, at the till, sells them (the till's sheet belongs to Sales).
- The **assistant**, by voice or by text and with the session of whoever speaks: "create the menu of
  the day at 13.50 to eat in", "add a Starters course to the menu of the day", "put the lentils in
  Starters", "the hake has a 2-euro supplement", "no flan today".

This module keeps the menu and says what it costs and how it is billed; **Sales** offers it at the till
and charges it, **Inventory** lowers the stock of each dish and **Kitchen** receives each dish at its
station. It is not a discount nor a variant, nor the extras of a dish (that is Modifiers).

## Reference adopted

The market sweep of the current product (`architecture/modules/combos.md`, 24/08/2026: 10
references and their forums) is still valid and is adopted, nothing more:

- [Square — combos](https://squareup.com/help/us/en/article/8558-create-and-sell-combos): the combo is
  an item of the catalogue, with "required choices" per group and a charge per option; a sold-out item
  is not offered.
- [Lightspeed K-Series — combos](https://k-series-support.lightspeedhq.com/hc/en-us/articles/1260804656529-About-combos):
  groups with how many items have to be picked, at a fixed price; several items are added at once.
- [Odoo — combos](https://www.odoo.com/documentation/18.0/applications/sales/point_of_sale/combos.html):
  extra price per option and the closed price shared out in one line per component, in proportion to
  its catalogue price ([forum: how it calculates the split](https://www.odoo.com/forum/help-1/how-does-odoo-calculate-the-price-split-on-combo-products-on-pos-250869)).
- Shopify Bundles, WooCommerce Product Bundles, NetSuite (kit), Holded (pack): the stock is moved by
  the components, never by the menu.
- Toast and Clover do it as a discount, and that is why they are **not** followed: a discount is not
  sent to the kitchen, is not broken down and does not move stock.
- Spanish VAT Act: **art. 91.Uno.2.2º** (the menu served on the premises is a single restaurant service
  at 10 %, the drink included, also the alcoholic one) and **art. 79.Dos** (a pack of goods at a single
  price shares out the base in proportion to the market value of each good, which HMRC specifies as the
  individual selling price: [VATVAL03800](https://www.gov.uk/hmrc-internal-manuals/vat-valuation/vatval03800)).
- Confirm before deleting (Square, Odoo, Shopify): a menu, a course or a choice is removed after a
  question.

## Before you start

- Menus needs **Inventory** (its choices are products of the catalogue) and **Taxes** (the VAT
  category of a menu "eaten in"). Turning Menus on turns both on.
- Only a product that is sold and charged **by units** can be a choice (a menu carries "a portion",
  not "a kilo" nor "the price of 100"); the search boxes only offer those. A product deactivated
  or deleted in Inventory cannot be added.
- The closed price and the supplements are amounts in euros, written with a comma or a point.

Initial setup, step by step:

1. Open **Menus** and tap **+** (COMBO-F02): name, closed price, how it is sold and, if it is "eaten
   in", the VAT category.
2. Tap the menu to open its **builder** and add its courses with the minimum and the maximum of each one
   (COMBO-F05).
3. In each course, add the choices, with their supplement if there is one (COMBO-F06).
4. Look at the notice at the top of the builder: it says whether the menu is already on the till or what
   it lacks.

## Screens

### Menus
Menu **Menus**. Table of menus with the search box "Search a menu…" (it searches by name and by
kitchen name), table or cards view and columns: Name (sorts and filters), "Closed price" (sorts), "How
it is sold" ("Eat in" or "Take away"; sorts and filters), "On sale" (Yes or No; sorts and filters) and
Order (sorts). Pages of 50, by order and name. With the right to manage there is a **+** button and,
per row, "Edit details" and "Withdraw"; without it, only the list is seen. Tapping a row opens the
builder.

The create and edit form (title "New menu" or "Menu · {name}") has: Name, "Kitchen name" ("Leave it
empty and the kitchen ticket uses the commercial name."), "Closed price" ("What the customer pays for
the whole menu, whatever they pick."), "How is it sold?" ("Eaten in (hospitality service)" or "Sold as
a product / to take away", with the explanation of both always in sight and the chosen one
highlighted), "VAT category" (only if it is "eaten in"), "Order on the menu list" and the "On sale"
checkbox (ticked to begin with), with "Save" and "Cancel".

### Menu builder
It opens when a menu is tapped (`/combo/menus/<id>`). The back arrow of the top bar goes back to Menus.
At the top of the page, the name and the price of the menu, and a notice with what that menu will do on the ticket: "This menu is billed as a
single service: one line at its VAT category, whatever the components are taxed at." or "This menu is
billed as goods: its price will be split across the components you add, one line each.". Below, if
the menu is not on the till yet, another notice, "Not on the till yet", says why, one reason per line.

Then, the "Courses" section ("A course is a step of THIS menu — Starter, Main, Dessert, Drink. Its
order is the order it is asked for.") and a card per course, in order: name, its rule ("Compulsory ·
pick 1 · up to 1 · no repeats") and, with the right to manage, the drag handle, "Move up", "Move
down", "Edit details" and "Withdraw". Inside, "Choices": a row per product with its supplement, a
"Sold out" mark if it is not available today, "Sold out in Inventory" if its product is sold out
for the whole business and, if the product can no longer be sold, "Deactivated in Inventory", "No
longer in the catalogue", "Not sold by units in Inventory" or, in a menu "to take away", "No VAT
category to take away"; per row, the handle, move up, move down, "Sold out / Available", edit and
remove. Below, the search box "Search a product…", "Supplement", "Add choice" and "Add several"
(window with a search box and checkboxes, and the "Category" field with "Tick all of “{category}”
(N)": "Add N selected"; what is already in the course comes ticked "Already in this course").
At the end, the "Add a course" form (Course name, "Minimum picks", "Maximum picks", the checkbox "The
same option may be picked more than once" and "Save"), which becomes "Course · {name}" when editing
one.

## States of each screen

| State | What the person sees |
|---|---|
| Loading | "Loading…" in the table's slot; "Loading courses…" in the builder. |
| Empty | "No menus yet. Create the first one with the + button."; with a search or a filter, "No results". In the builder, "No courses yet. Add the first one — a menu with no course has nothing to pick." and, in a course, "No choices yet: nobody can resolve this course.". |
| Error | The table's notice with "Retry"; "The courses of this menu could not be loaded." in the builder. The refusal of a form shows inside the form, without losing what was typed; that of a choice, inside its course. |
| Reconnecting | What is painted stays; a strip warns "Reconnecting…". |
| No longer exists | If the menu is withdrawn while its builder is open (here or on another device), the builder empties and says "This menu no longer exists" ("It has been withdrawn, perhaps from another device."), with "All menus" to go back. |
| App inactive | "This app is not active in this business". |
| No permission | What they cannot do does not appear; if they arrive through another door, "You do not have permission". |

## Flows

| ID | Flow | Status |
|---|---|---|
| COMBO-F01 | Look up and search the menus | done |
| COMBO-F02 | Create a menu at a closed price | done |
| COMBO-F03 | Change the details of a menu, put it on sale or take it off sale | done |
| COMBO-F04 | Withdraw a menu | done |
| COMBO-F05 | Set up the courses of a menu | done |
| COMBO-F06 | Choose the products of each course and their supplement | done |
| COMBO-F07 | Choose a menu when selling | done |
| COMBO-F08 | Charge the menu: closed price and supplements | done |
| COMBO-F09 | Split the VAT of a menu | done |
| COMBO-F10 | Lower the stock of each dish when charging | done |
| COMBO-F11 | Send the menu to the kitchen | done |
| COMBO-F12 | Mark a choice as sold out | done |
| COMBO-F13 | When a product leaves the catalogue | done |

### COMBO-F01 Look up and search the menus
Status: done
Actor: owner, administrator, manager, employee, assistant
Screen: Menus
Steps:
1. Open **Menus**.
2. Read the table: name, closed price, how it is sold, whether it is on sale and order.
3. To find one, type in "Search a menu…", sort by a column or filter by name, by how it is sold or by
   "On sale".
4. Tap a row to open its builder.
In: the menus of the business (right to view).
Out: nothing; it only reads.
If it fails: the loading error shows in the table with "Retry"; without menus, "No menus yet. Create the
first one with the + button.".
Involved: none

### COMBO-F02 Create a menu at a closed price
Status: done
Actor: owner, administrator, manager, assistant
Screen: Menus
Steps:
1. In Menus, tap **+**.
2. Type the Name; if the kitchen ticket must say something else, the "Kitchen name".
3. Type the "Closed price": what the customer pays for the whole menu. Empty is 0.
4. Choose "How is it sold?": "Eaten in" bills ONE line at the menu's rate, the drink included (the
   menu of the day); "Sold as a product / to take away": if all the choices are taxed the same, ONE
   line at that rate; if not, ONE line per dish, each one at its rate, with the price shared out
   (COMBO-F09).
5. If it is "eaten in", choose the "VAT category" of the whole menu (in a restaurant, "Restaurant —
   food", at 10 %).
6. Leave "On sale" ticked if it can already be sold and tap "Save".
7. The form closes and the menu appears in the list. It is not on the till yet: it lacks the courses
   and the choices (COMBO-F05, F06).
In: name, kitchen name, price, way of selling, VAT category, order and "On sale"; it reads the VAT
categories from Taxes.
Out: the menu (announces: new menu).
If it fails: next to the field: "The menu needs a name.", "A menu eaten in needs its own VAT category:
without it, it cannot be billed.", "A menu price cannot be below zero. To make a choice cheaper, give it
a negative supplement instead.", "This is not an amount. Type a figure, for example 12.50." and the one
about the two possible readings of an amount ("1.250"), which quotes what was typed. A VAT category that
does not exist in Taxes: "That tax category does not exist in Taxes.". Without the right to manage
there is no + button.
Involved: TAX-F01

### COMBO-F03 Change the details of a menu, put it on sale or take it off sale
Status: done
Actor: owner, administrator, manager, assistant
Screen: Menus
Steps:
1. In the menu's row, tap "Edit details".
2. Change what is needed: name, price, way of selling, VAT category, order or "On sale".
3. Tap "Save". The list shows the change at once.
4. A menu with "On sale" unticked stays in the list, but the till stops offering it.
In: the same fields as when creating; only what is sent changes (through the assistant or the API, what
is not named stays as it was).
Out: the changed menu (announces: menu changed). What is already charged does not change: each sale line
carries its copy of the menu. An open check charges the amount it was ordered with, even if the menu
goes up in price or is taken off sale; the way of selling and the VAT category are read when charging
(COMBO-F08, F09).
If it fails: the same warnings as when creating. Switching to "eaten in" without a VAT category is
refused.
Involved: SALE-F12

### COMBO-F04 Withdraw a menu
Status: done
Actor: owner, administrator, manager, assistant
Screen: Menus
Steps:
1. In the menu's row, tap "Withdraw".
2. Confirm in "Withdraw this menu?" ("{name}" stops being on sale, together with its courses and
   choices. Tickets already issued keep reading it.).
3. The menu disappears from the list, with its courses and its choices, and the till stops offering
   it. Whoever has it open in its builder sees "This menu no longer exists".
In: the chosen menu (by id or by name).
Out: the menu, its courses and its choices deleted in a single operation (announces: menu withdrawn,
with its name). The tickets issued carry their copy and can still be read.
If it fails: the dialog says why and stays open; a menu that no longer exists, "That menu does not
exist in this business.". An open check that already had it charges it as it was ordered (COMBO-F08).
Involved: SALE-F12

### COMBO-F05 Set up the courses of a menu
Status: done
Actor: owner, administrator, manager, assistant
Screen: Menu builder
Steps:
1. Open the menu (tap its row) and go down to "Add a course".
2. Type the "Course name" (Starters, Mains, Dessert, Drink), the "Minimum picks" (1 or
   more makes the course compulsory; 0, optional) and the "Maximum picks" (0 is no limit). To begin
   with they come as 1 and 1.
3. Tick "The same option may be picked more than once" only if it is needed (two coffees in the same
   menu).
4. Tap "Save": the course goes in last, which is the last one asked.
5. To change the order, drag the handle or use "Move up" and "Move down": the new order is saved whole
   at once. "Edit details" opens the course in the form and keeps its place. "Withdraw" removes it with
   its choices, after confirming it.
In: name, minimum, maximum and repetition.
Out: the course (announces: course new, changed, reordered or withdrawn).
If it fails: next to the field: "The course needs a name.", "The maximum ({max}) is below the
minimum ({min}): nobody could ever satisfy this course." and "That menu already has a course “{name}”.".
A minimum or a maximum above 50 is refused, and so are more than 20 courses in a menu ("A menu
holds 20 courses at most."). If the server refuses, the form says so and does not lose what was written.
Involved: none

### COMBO-F06 Choose the products of each course and their supplement
Status: done
Actor: owner, administrator, manager, assistant
Screen: Menu builder
Steps:
1. On the course's card, type in "Search a product…" and choose the product from Inventory's
   catalogue (it searches by name and by SKU).
2. Type the "Supplement" if substituting costs more (or less, with a minus sign) than the closed
   price; empty is no supplement.
3. Tap "Add choice": it goes in last. For several at once, "Add several": tick the boxes
   and tap "Add N selected" (all go in without a supplement and in the order they were ticked). For
   a whole category, choose it in "Category": the list shows its products and "Tick all of
   “{category}” (N)" ticks the ones the course does not offer yet.
4. To change the product or the supplement of a choice, tap its pencil: the form says
   "Editing «{product}». It keeps its position in the course.". With the handle, move up or move down
   it is reordered; the bin removes it, after confirming it.
In: the products of Inventory (the active ones, sold by units; also those sold out today,
which can be put in a menu although the till does not offer them until they come back).
Out: the choice (announces: choice new, changed, reordered or removed). The supplement is added to the
closed price, never to the product's price.
If it fails: "Pick a catalogue product first.", "This course already offers that product. To let it
be picked twice, switch on «the same option may be picked more than once».", "“{product}” is
deactivated in Inventory: activate it before putting it in a menu.", "Only a product sold and priced
by the unit can be a menu choice; “{product}” is sold by {unit}.", "A course holds
40 choices at most." and the amount warnings. "Add several" with nothing ticked: "Tick at least one
product first."; a search or a category with no products: "No products match.". If the
catalogue does not load, the search box says so with "Retry". A product that does not exist yet is
created first in Inventory: the search box finds it as soon as it is saved.
Involved: INVENTORY-F27

### COMBO-F07 Choose a menu when selling
Status: done
Actor: employee, manager
Screen: Sales: Sell
Steps:
1. At the till, in "All", the menus on sale come first, each one with the "Menu" label and its
   closed price. Tap one: a sheet opens with its name and all its courses at once.
2. Each course says its rule: "Choose N" if it asks for exactly N, "Choose N to M" if it asks for a minimum
   and allows up to a ceiling, "Choose at least N" if it asks for a minimum with no ceiling, "Up to N" if it
   only has a ceiling, "Optional" if not; and its available choices, with the supplement with its sign if it
   is not zero ("+€2.00"). On opening nothing is chosen.
3. Choose: in a course of a single choice, tapping another one changes it; in one with a ceiling, on
   reaching it the next tap says "«Coffee» is full: take one out to choose another."; a choice that can
   be repeated carries its counter and its "−".
4. While something is missing, the button says what ("Choose 1 in «Mains»") and tapping it points at
   that course; when each compulsory course is complete, it says "Add · <total>" with the closed price
   plus the supplements. Tap it: the menu goes into the check as one line, with its dishes under the
   name.
In: the menus on sale that can be completed, with their courses and their available choices.
Out: the menu's line with what was chosen, which Menus checks and prices when it is added (COMBO-F08).
If it fails: a menu is not on the till if it is not on sale, if it has no course with choices or
if a compulsory course does not have enough available choices (sold out here or in Inventory,
deactivated or deleted in Inventory). A sold-out choice is not on the sheet, and an optional course
without available choices is not either. If Menus refuses the line, the sheet says why without closing
(COMBO-F08). If the menus cannot be read, above the grid "The menus could not be read. Try again."
with "Retry", and the products are sold just the same. With the employee profile they are
also seen and sold.
Involved: SALE-F12, MODIFIER-F06

### COMBO-F08 Charge the menu: closed price and supplements
Status: done
Actor: employee, manager
Screen: Sales: Sell
Steps:
1. Add the menu with its dishes at the till (COMBO-F07): the line goes in with the closed price plus the
   supplement of each choice, also that of a repeated one (two coffees, two supplements); a
   negative supplement makes it cheaper.
2. Charge as always: the ticket puts the menu's name with its amount and, under it, each chosen dish.
3. In an open check, the menu charges the amount it had when it was ordered even if afterwards it goes up
   in price, a dish runs out (the last flan served), it is taken off sale or it is withdrawn: when charging,
   Menus only checks again the dishes, the portions and how it is billed (COMBO-F09).
In: the menu (by id or by name) and the choices (by id, or by the product's name or SKU,
with the course if needed), with how many of each one; when charging an open check, the amount ordered.
Out: the menu's line with its amount, its kitchen name and its dishes, in the order of the courses and
of the choice, and how it is billed (COMBO-F09). Menus keeps nothing; the sale belongs to Sales.
If it fails: the line does not go into the check and the sheet (or the assistant, or the API) says why:
"That menu does not exist in this business.", "That menu is no longer on sale.", "Pick something from
the menu before adding it.", "The menu still needs a pick in “{course}”: pick {min}.", "The course
“{course}” takes {max} at most.", "The course “{course}” does not take the same choice twice.",
"“{product}” is not a choice of this menu.", "“{product}” is sold out.", "“{product}” can no longer
be sold: it is deactivated or deleted in Inventory.", "“{product}” is no longer sold by units in
Inventory, so it cannot be charged as a menu choice." and "The menu's amount cannot be negative.".
Without Menus active, the till offers no menus and one asked for through the API is refused.
Involved: SALE-F12

### COMBO-F09 Split the VAT of a menu
Status: done
Actor: employee, manager
Screen: Sales: Sell
Steps:
1. Charge a menu "eaten in": the ticket puts it in ONE line, with its amount and the VAT category of
   the menu, even if a drink inside has another rate in the catalogue (art. 91.Uno.2.2º LIVA: the drink,
   also the alcoholic one, is ancillary to the restaurant service).
2. Charge a menu "to take away": each dish goes to the tax category of its product, except what on the
   premises is a service and to take away is a sale of goods: the restaurant's beer or wine (10 % at the
   table) go to 21 % (art. 90 LIVA). If all go to the same category, it comes in ONE line with the amount
   and that category.
3. If the dishes of a menu "to take away" go to different categories, the ticket puts the menu's name
   as a header and ONE line per chosen dish, each one with its VAT and the amount shared out in proportion
   to the catalogue price of each product (art. 79.Dos LIVA), with the leftover cent to the largest
   remainder (on a tie, to the dish that comes first); the sum is exactly the amount. Example: €6.00 over
   a sandwich of €4.50 (10 %) and a beer of €2.00 (21 %): €4.15 + €1.85. There is no menu line with
   money.
4. The check shown before charging splits the same way as the charge.
In: way of selling and VAT category of the menu and the choices; catalogue price and tax category of
each product, from Inventory.
Out: the split, with the tax category of each line; Sales calculates base and tax with Taxes.
At the till the menu's setting rules: a check is not marked "to take away". Through the assistant or the API a
menu "eaten in" can be asked for to take away or for delivery, and then it is split as one "to take
away"; a menu "to take away" without its own VAT category that is eaten in goes per dish to the
categories of its products (those of eating in).
If it fails: "Eaten in" without a VAT category cannot be saved (COMBO-F02). To take away, a dish whose
category has no active equivalent in Taxes: "“{product}” is billed at {category}, which has no
equivalent to take away in Taxes, so this menu cannot be sold to take away."; in a
menu "to take away" that dish is not offered and the builder marks it "No VAT category to take away".
"To take away" with a product without a tax category: "“{product}” has no tax category in
Inventory, so this menu cannot be charged." (and it is not offered). Split with all the products at
€0 in the catalogue: "The products of this menu have no catalogue price, so its VAT cannot be
split."; if all the offered choices of a menu "to take away" are worth €0 and go to
different categories, the menu is not on the till.
Involved: SALE-F12, TAX-F19

### COMBO-F10 Lower the stock of each dish when charging
Status: done
Actor: system
Screen: none
Steps:
1. Charge at the till a check with menus (COMBO-F08). In Menus nothing is done by hand.
2. In a few seconds, Inventory lowers the stock of each chosen product: as many portions as menus and
   as times it was chosen (three menus with two coffees each, six coffees). The menu has no stock of its own,
   and a product of the service type or without stock control moves nothing.
3. If the sale is voided, Inventory gives back everything that went out.
4. If a part is refunded (one of three menus), Inventory puts back one portion of each dish of that menu.
In: the dishes of the menu's line as they were charged: each chosen product, how many times and whether it
is a service (COMBO-F08).
Out: a "Sale" movement per dish in Inventory (INVENTORY-F22), and putting it back when voiding
(INVENTORY-F23) or when refunding (INVENTORY-F24); nothing from this module. If the sale's notice arrives
twice, the stock goes down only once.
If it fails: the sale is already charged; if Inventory cannot lower the stock at that moment, it retries
on its own (INVENTORY-F21).
Involved: INVENTORY-F22, INVENTORY-F23, INVENTORY-F24, SALE-F12

### COMBO-F11 Send the menu to the kitchen
Status: done
Actor: employee, manager
Screen: none (the kitchen ticket is painted by Kitchen)
Steps:
1. At the till, add a menu to the table's check choosing its dishes (COMBO-F07) and tap "Send
   order".
2. Kitchen receives the kitchen ticket: each chosen dish at the station of its product (or of
   its category), under the menu's header with its kitchen name (or its name, if it has none), with the
   quantity times the menus ordered and the menu's note on each dish (KITCHEN-F06).
3. On the paper of each station comes the same menu header with its dishes under it.
In: the menu's line of the open check, with what Menus gave when it was ordered (COMBO-F08): its kitchen
name and each dish with its product, its category and how many times it was chosen.
Out: nothing from this module; the kitchen ticket belongs to Kitchen (announces: kitchen ticket sent).
If it fails: a menu missing a compulsory course does not go into the check (Menus refuses it when it is
ordered), so it never reaches the kitchen half done. A dish that is a service is not cooked.
Involved: KITCHEN-F06, KITCHEN-F08, SALE-F12, SALE-F20

### COMBO-F12 Mark a choice as sold out
Status: done
Actor: owner, administrator, manager, assistant
Screen: Menu builder
Steps:
1. In the choice's row, tap "Sold out" (or say "no flan in the menu of the day today").
2. The row is marked "Sold out" and the till stops offering it; the rest of the menu keeps being sold.
3. When there is some again, tap "Available".
4. If the product is marked sold out in Inventory (INVENTORY-F29), all its choices, in all the
   menus, show "Sold out in Inventory" and the till stops offering them at once, without touching the menu;
   they come back on their own when Inventory puts it on sale again.
In: the choice, or the product sold out in Inventory.
Out: the changed choice (announces: choice changed).
If it fails: if marking it sold out leaves a compulsory course without enough choices, the menu stops being
on the till and the builder's notice says so. An open check with a dish already ordered is charged the same
(COMBO-F08).
Involved: COMBO-F07, INVENTORY-F29

### COMBO-F13 When a product leaves the catalogue
Status: done
Actor: system, owner, administrator, manager, assistant
Screen: Menu builder
Steps:
1. Someone deactivates a product in Inventory: its choices stay in the menus, marked
   "Deactivated in Inventory", and the till does not offer them until it is reactivated.
2. Someone deletes a product in Inventory: in a few seconds its choices leave on their own all the
   menus that offered it, and the open builder shows it at once. Meanwhile they come marked
   "No longer in the catalogue" and the till neither offers them nor can they be charged (it is final: a
   deleted product does not come back).
3. Look at the notice at the top of the builder: if a compulsory course has been left without enough
   choices, it says why the menu is no longer on the till; add another choice to that course (COMBO-F06).
In: the product deactivated or deleted in Inventory.
Out: the choices of the deleted product, out of all the menus (announces: choice removed, with the
reason "product deleted"). If Inventory's notice arrives twice, the second one changes nothing; what
is deleted in one business does not touch the menus of another.
If it fails: if a compulsory course is left without enough choices to offer, the menu stops being
on the till and the builder's notice says why. If removing the choices fails, Menus retries
on its own; meanwhile, they stay marked and nobody sells them.
Involved: INVENTORY-F04, COMBO-F06

## Services: what goes in and what comes out

Everything can be asked for through the screens, the assistant (by voice or by text, with the session of
whoever speaks) and the API, with the same rules and permissions. A menu is named by its id or by its name; a
course by its id or by its name within the menu; a product by its id, its SKU or its name. If a name
fits several, it says which ones and asks to choose (`combo.combo_ambiguous`, `combo.group_ambiguous`,
`combo.option_ambiguous`, `inventory.product_ambiguous`).

### What it offers: queries (they read, they change nothing)

| What it gives | Who can | Flows | Service |
|---|---|---|---|
| The menus, with search, filters and order, in pages of up to 100 (live) | view | F01 | `combo.combo.list` |
| A menu with its courses and its choices, whether it is on the till and why not (live) | view | F05, F06, F12 | `combo.combo.get` |
| The till's menu catalogue: the ones that can be sold, with their courses and their available choices (live) | view | F07 | `combo.combo.for_sale` |
| The line of a menu with what was chosen: amount, components and tax split | view | F08, F09, F10, F11 | `combo.combo.resolve` |

### What it offers: actions (they change data)

| What it does | Who can | Flows | Service |
|---|---|---|---|
| Creates a menu | manage | F02 | `combo.combo.create` |
| Changes a menu (only what is sent) | manage | F03 | `combo.combo.update` |
| Withdraws a menu with its courses and choices | manage | F04 | `combo.combo.delete` |
| Adds a course (at the end) | manage | F05 | `combo.group.create` |
| Changes a course (only what is sent) | manage | F05 | `combo.group.update` |
| Withdraws a course with its choices | manage | F05 | `combo.group.delete` |
| Orders the courses of a menu, all at once | manage | F05 | `combo.group.reorder` |
| Adds a choice (at the end) | manage | F06 | `combo.option.create` |
| Adds several choices at once | manage | F06 | `combo.option.bulk_create` |
| Changes a choice: product, supplement or available (only what is sent) | manage | F06, F12 | `combo.option.update` |
| Removes a choice | manage | F06 | `combo.option.delete` |
| Orders the choices of a course, all at once | manage | F06 | `combo.option.reorder` |
| Removes the choices of a deleted product | the platform only | F13 | `combo.option.drop_product` |

### What it announces

| Notice | When | What it carries | Service |
|---|---|---|---|
| New menu | Creating a menu | `id`, `name` | `combo.combo.created` |
| Menu changed | Saving with some change | `id`, `name` | `combo.combo.updated` |
| Menu withdrawn | Withdrawing | `id`, `name` | `combo.combo.deleted` |
| Course new, changed or withdrawn | Creating, saving with changes or withdrawing a course | `id`, `combo_id` | `combo.group.created`, `.updated`, `.deleted` |
| Courses reordered | Changing the order | `combo_id` | `combo.group.reordered` |
| Choice new, changed or removed | Adding (one or several), saving with changes, marking sold out or removing; removing because the product was deleted carries `reason: "product_deleted"` | `id`, `group_id`, `combo_id`, `product_id` | `combo.option.created`, `.updated`, `.deleted` |
| Choices reordered | Changing the order | `group_id`, `combo_id` | `combo.option.reordered` |

### What it reacts to

| Notice from | What Menus does | Flows | Service that listens |
|---|---|---|---|
| Inventory: product deleted | Removes its choices from all the menus, in a few seconds (the worker's handing out of notices; repeating it changes nothing) | F13 | `inventory.product.deleted` → `combo.option.drop_product` |

Besides, Inventory's product changes (`inventory.product.updated`, `.deleted`) re-read live
the builder and the till's catalogue: the name, the price, whether it is active and whether it is
sold out belong to Inventory.

### What it needs from other apps

| From | What for | Flows | Service |
|---|---|---|---|
| Inventory (`requires`) | The products that can be a choice, with their name, SKU, price, tax category, whether they are active and whether they are sold out (direct read: it is a required app) | F06, F07, F08, F09, F12 | model `inventory.Product`; the screen's search box uses `inventory.product.list` with `is_active` and `include_sold_out` (the active ones, sold out or not) |
| Taxes (`requires`) | The tax categories of the selector and that of the menu "eaten in" | F02, F03, F09 | model `tax.TaxCategory`; the selector uses `tax.category.list` |

### Contract with Sales

Sales does not require Menus: it calls it by the operation's name (`call_app`), with the session of
whoever sells, and if Menus is not active the till offers no menus.

- **Till catalogue**: `useLive('combo.combo.for_sale', {limit: 50})`. Each row: `id`, `name`,
  `kitchen_name`, `price` (cents), `supply_kind`, `sort_order` and `groups[]` (`id`, `name`,
  `min_choices`, `max_choices` —0 no limit—, `allow_repeat`, `options[]` with `id`, `product_id`,
  `product_name`, `sku`, `price_delta`). Only menus on sale that can be completed and available
  choices.
- **When ordering and when charging**: `combo.combo.resolve` with `{id | combo, choices: [{option_id |
  product (+ group), quantity}], amount?, channel?}`; `channel` (`dine_in`, `takeaway`, `delivery`)
  decides "eaten in" or "to take away", and without it the menu's setting applies. It returns `combo_id`, `name`, `kitchen_name`,
  `supply_kind`, `price`, `supplements`, `amount`, `split` and `tax_category_key` (that of the single line,
  or `null` if it is split) and `components[]` in order: `option_id`, `group_id`, `group_name`,
  `product_id`, `product_name`, `sku`, `category_id`, `is_service`, `quantity` (per menu),
  `price_delta`, `catalog_price`, `tax_category_key` and `amount` (its share, only if `split`).
- **What Sales does with that** (SALE-F12, done; tested with the real Sales): it freezes the response in the line when ordering (and its `amount` as the
  amount ordered); when charging it calls again with that `amount` and materialises ONE line (`split = false`, at
  `tax_category_key`) or ONE line per component (`split = true`, each one at its `tax_category_key` and for
  its `amount`), with no parent line with money; its preview (`sale.checkout.preview`) splits the same way;
  it multiplies the quantities by that of the line; it passes on Menus' 409s as they are, so a menu with
  a compulsory course not chosen never goes into the check nor reaches the kitchen; in a refund it sends
  the components × the quantity refunded as lines of `sale.sale.refunded`. A menu that Menus no longer
  knows when charging (withdrawn, or Menus turned off) is charged with what was frozen. The till does not send `channel`:
  the check has no channel (the "What is left out" of Sales), so the menu's setting rules.

### Contract with Inventory

- In the notice `sale.sale.completed`, Sales puts in the menu's line `components[]` with `product_id`,
  `quantity` (that of each dish times that of the line) and `is_service` of each component of COMBO-F08; the
  menu's line does not move stock by itself (INVENTORY-F22, `inventory.stock.apply_sale`).
- The void (`sale.sale.voided`) is put back by Inventory from its book of movements (INVENTORY-F23), and
  the refund (`sale.sale.refunded`) with the components × the menus refunded, one line per product
  (INVENTORY-F24, `inventory.stock.restore_refund`).
- Tested end to end with the worker's real handing out of notices.

### Contract with Kitchen

- Kitchen does not read Menus. It receives from Sales, in `sale.order.fired`, the menu's line with `name`,
  `kitchen_name` and its components (`product_id`, `product_name`, `category_id`, `quantity` × menus), and
  puts each dish at its station under the menu's kitchen name, on the card and on paper
  (KITCHEN-F06, KITCHEN-F08). Tested end to end with the worker's real handing out of notices.

### Who can do what

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| See the menus, the till's catalogue and calculate a menu line | yes | yes | yes | yes | `combo.view` |
| Create, change, order and withdraw menus, courses and choices | yes | yes | yes | no | `combo.manage` |
