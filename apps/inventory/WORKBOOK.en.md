<!-- generated from WORKBOOK.md sha256:cbf68d22cae76c9e239707ceefa34142420b3dc72474c7a96487e75a14a656dc -->

## What it is for and who it is for

Inventory is the catalog of what is sold with stock: each product with its name, its SKU, its price,
its cost, its tax category, its unit of measure and how many units are left.

- In the **restaurant** it is **the menu**: the dishes and drinks the till shows grouped by category
  and that Kitchen sends to their station.
- In the **hair salon** it is **the products for sale** (shampoo, wax, dye for resale). The hair
  salon's services do not live here: they live in Services.

Every stock change (initial stock, goods receipt, sale, void, count, write-off) leaves a
**movement** that cannot be edited or deleted, and each product's balance is explained by them.

Who uses it:

- The **administrator** and the **manager** create and change products and categories, import and
  export the catalog, receive goods, count stock and save the settings.
- The **employee** and the **cashier** only look up products, categories and movements.

Sales are not made here: the stock goes down only when Sales takes the payment. Inventory **is not
required to sell**: without it, the till charges services and open-price lines.

## Reference adopted

ERPlora does not invent flows: it adopts the ones the market has already proven. From the restaurant
reference it adopts the menu by categories, stock control per item and the count with a reason
([Lightspeed — Practice run checklist](https://resto-support.lightspeedhq.com/hc/en-us/article_attachments/360044738513))
and the item's "sold out"
([Square — availability](https://squareup.com/help/us/en/article/8495-beta-item-availability)),
but not the quantity left on the till, which does not exist here. Also:

- **Sold out ("86") apart from active**: the item stays on the menu with its switch on, the till
  stops offering it and it comes back with one tap when there is some again: Square "Sold out", Toast
  "86", Lightspeed "Unavailable", TouchBistro and Revel. A person sets it and clears it; none of them
  clears it on its own when goods are received.
- **A category's figure counts what is shown, sold-out items included**: the till shows what is sold
  out in grey and without being able to order it ([Square](https://squareup.com/help/us/en/article/8430),
  [Toast](https://support.toasttab.com/en/article/86-an-Item),
  [Lightspeed](https://o-series-support.lightspeedhq.com/hc/articles/31329314792987),
  [SumUp](https://help.sumup.com/en-US/articles/WcT1PpyBZHREhzgn7Wstl)), and where there are figures they
  follow what is shown: WooCommerce only leaves what is sold out out of its figure when it hides it
  ([wc_recount_after_stock_change](https://wp-kama.com/plugin/woocommerce/function/_wc_term_recount)),
  and the forums' complaint is always a figure that does not match what is shown ([GeneratePress](https://generatepress.com/forums/topic/product-count-wrong-on-category-view/),
  [WoodMart](https://xtemos.com/forums/topic/out-of-stock-query-and-products-issue/),
  [Shopify](https://community.shopify.com/t/some-products-only-visible-when-customising-collection-page-not-front-end/373545)).

- **Stock control per item, with a business default**: Square "Track stock", Odoo "Track
  Inventory", Business Central, Shopify "Track quantity", WooCommerce "Manage stock?".
- **Import with column mapping, a rehearsal and a report before creating anything**: Odoo's "Test
  import", the mapping with required columns of WooCommerce and Lightspeed, and Shopify's summary.
- **Deleting a category unlinks its items; it neither deletes them nor prevents it**: Shopify,
  WooCommerce, Square, Lightspeed, Toast and Vagaro.
- **A menu or a pack moves the stock of its components, never its own**: Odoo's kit, Shopify
  Bundles, WooCommerce Product Bundles and Square.
- **A ledger of movements that is never edited and an absolute count with a reason**; **exact
  quantities with a step per unit** (exact fractions, like SAP).
- **The tax category is chosen by its type** ("Product — general · 21 %"), like Square, Lightspeed,
  Odoo and Holded.
- **The unit of a product with stock is not changed**: Odoo prevents it as soon as the product has
  movements; here it is enough for its stock to be zero.
- **The item's photo on the till's tile and, without a photo, its initials over a colour**: Square (the
  item's image or, without one, its colour and its abbreviation), Loyverse (image, or colour and shape)
  and Shopify POS (the product's image on the grid). The photo is chosen from ERPlora's library or
  uploaded from the product's card, and it travels in the business's backup, as in the current product.

## Before you start

- **Taxes** is essential: each product points at one of its tax categories. To turn Inventory on,
  Taxes is needed, and Taxes cannot be turned off while Inventory is on. Out of the box, Taxes brings
  the categories of Spain.
- **Sales** does not depend on Inventory. With both on, the till sells from this catalog and the sale
  lowers the stock (INVENTORY-F21). **Kitchen** does need Inventory: it decides what goes to each
  station by product and by category.
- **Printing**, only for the barcode label: a printer with the "Label" function (INVENTORY-F25).
- When Inventory is turned on, the business receives the units of measure (unit, kilo, gram, tonne,
  litre, millilitre, minute and hour), and the "Finish setting up your business" list asks for the first
  product (INVENTORY-F28).

Initial setup, step by step:

1. In **Inventory → Settings** decide "Track stock" and "Allow selling without stock"
   (INVENTORY-F19). Read first what each one really does.
2. Load the menu or the catalog: with your sector's template (INVENTORY-F12), with a CSV
   (INVENTORY-F09) or by hand (INVENTORY-F01).
3. Create the categories that group the menu on the till (INVENTORY-F06) and assign them
   (INVENTORY-F08).
4. Check that no product shows "Not configured" (INVENTORY-F05).
5. Give the starting stock with "Count stock" (INVENTORY-F14) or with the "Initial stock" of the new
   product: both leave their movement.
6. Make a test sale and check in **Movements** that the stock went down (INVENTORY-F21).

## Screens

Inventory opens from the **Inventory** menu and has five tabs: **Dashboard**, **Products**,
**Movements**, **Categories** and **Settings**. All of them can be seen by anyone who can view
products, except Settings (below); what a person cannot do does not appear on screen, and the app
also refuses it even if someone tries it through another door (the assistant or the API).

### Dashboard
Figures at the top: "Tracked products", "In stock", "Out of stock", "Low stock" and "Inventory
value" ("at cost"). The first four lead to Products. If there are items with stock control and no
cost, the note "N product(s) without recorded cost: the value shown is partial". Below, the "Low
stock products" table (Name, SKU, Stock, Threshold), 5 per page. Empty: "No products in low
stock.". Loading: "Loading…". Error: "Inventory metrics could not be loaded." and the table's notice
with "Retry".

### Products
Table with Name, SKU, Price, Stock ("—" for an item without stock control) and Status: an
active/inactive switch, "Yes"/"No" for whoever cannot change products, or the mark "Not configured ·
Missing tax category"; next to it, the red "Sold out" badge if the item is sold out. Search box
"Search product…" by name or SKU; sorting by column; filters by name, SKU, price from/to, stock
from/to and status ("Yes", "No", "Not configured", "Sold out"); 50 per page; table or card view.

The table's buttons: **+** (create), import CSV and export CSV, each one only for whoever has that
permission. Per row: "Details", "Receive stock" and "Count stock" (with stock permission and only on
physical products), "Write off stock" (also, only on items with stock control), "Edit", "Mark sold
out" or, if it already is, "Put back on sale" (in the "⋮" menu, for whoever can change products) and
"Delete". Tapping the row opens the product's card.

The **+** and "Edit" open the form's side panel: Name, SKU (locked when editing: "The SKU is the
product's identity: it is not edited"), Price, "Cost (<currency>)", "Initial stock" (only when
creating), "Low stock threshold", "EAN-13", "Description", "Type" ("Physical" or "Service", only when
creating), the "Track stock for this item" box with its note, "Unit of measure", "Tax category"
("Pick a tax category") and "Categories" (if there are any), and "Save" / "Save changes"
("Saving…").

The item's photo (INVENTORY-F30 to F32): the table has the "Photo" column, before the name, with the
photo's thumbnail or the initials over its colour, and the cards their "Photo" line; the product's card
shows it at the top, larger. For whoever can change products, the form ends with "Photo": the photo (or
the initials and "No photo: its initials are shown"), "Choose from the library" and "Upload photo" if it
has none, or "Change" and "Remove photo" if it has one, and the note "JPG, PNG or WebP of up to 2 MB".
The "Image library" window shows "Loading images…" while it searches, "No image matches your search. Try
another word or upload a photo." if it finds nothing and "The image library could not be loaded." with
"Retry" if it fails; at the bottom, "Upload photo". While the photo uploads, the button says "Uploading
photo…".

Empty: "No products". Loading: "Loading…". Error: the table's notice with "Retry". A refusal of the
form shows inside the panel; that of a row action, above the table.

### Product card
Window with the product's name: SKU, Price, Stock and Status ("Yes · Sold out" if it is sold out); the
SKU's barcode on a white plate with the SKU below; "Print barcode" and, with stock permission and on a
physical product, "Receive stock" and "Count stock", and "Write off stock" if the item tracks its
stock; with permission to change products, "Mark sold out" or "Put back on sale". A failure when
printing or when marking shows inside the window.

### Goods receipt
Window "Goods receipt — <product>": "Current stock", "Quantity received", "Unit cost (<currency>)" and
"Record receipt". A refusal shows inside the window.

### Stock count
Window "Stock count — <product>": "Current stock", "Difference" (as soon as there is a figure),
"Counted stock", "Reason (required)" and "Apply count", with the note of what is missing ("Enter the
counted stock to continue." / "A reason is required to apply the count."). A refusal shows inside the
window.

### Write-off
Window "Write-off — <product>": "Current stock", "Quantity written off", "Reason: waste, breakage, own
consumption… (required)" and "Write off", with the note of what is missing. A refusal shows inside the
window.

### Import products
Three windows in a row:

1. "Check the import": a drop-down per column of the file ("Do not import" or the field; Name and
   SKU carry an asterisk), "First {n} rows of {total}", the summary "{ready} row(s) ready · {failed}
   with problems" with up to 10 reasons, and "Import {n} product(s)" and "Cancel".
2. If needed, "CSV tax categories": a block per tax text not recognised (or "Rows with no tax
   category") with "Pick" / "Create" / "Skip", and "Confirm & import".
3. While it creates, above the table: "Importing {done}/{total}…" with "Stop". At the end, "Import
   result": "Rows", "Created", "Skipped (already existed)", "Failed", a line per failed row ("Line N
   · SKU — reason") and "Copy report".

### Movements
Read-only table: Date, Name, SKU, Type ("Initial", "Reception", "Sale", "Void", "Count", "Decrease",
"Refund"), Quantity (with its sign), Balance, Reason and Reference (in a sale, the number of its
ticket, its invoice or the sale itself). Search box by product, SKU, reference or ticket number;
filters by Type and by Reference; most recent first; 50 per page.

Empty: "No movements yet. They appear when you use Receive stock or Count stock on a product in
Products, and with every sale.". No matches: "No movement matches the search or the filters. A sale is
found by the number of its ticket, invoice or sale.". Error: the table's notice with "Retry".

### Categories
Table with Name, Slug and Products (how many active ones it has, sold-out ones included: the same
figure as the till's category strip, which shows them too); search box "Search category…"; 25 per page;
import and export CSV. The **+** and the row (or "Edit") open the panel: Name, "Slug (optional)",
"Tax rate" ("— (default)" or a tax category), "Cancel editing" and "Save" / "Save changes". "Delete"
opens "Delete category" with what is going to happen and "Delete and unlink" / "Cancel". Empty: "No
categories.". Loading: "Loading…".

### Settings
Heading "Inventory" with "Allow selling without stock", "Low stock threshold" (with its explanation)
and "Track stock", and "Save". It is seen and saved by whoever can manage the inventory settings: out
of the box, the administrator and the manager. The employee and the cashier are not shown the tab; if
they type its address, they see "This page does not exist". Loading: "Loading settings…". Error: "The
settings could not be loaded." with "Retry", never the factory values as if they were the business's.

## States of each screen

| State | What the person sees |
|---|---|
| Loading | "Loading…" (in Settings, "Loading settings…") while the first result arrives. |
| Empty | Products: "No products"; Movements: "No movements yet. They appear when you use Receive stock or Count stock on a product in Products, and with every sale."; Categories: "No categories."; Dashboard: "No products in low stock.". With a search or filters with no result, the table says that nothing matches. |
| Error | Dashboard: "Inventory metrics could not be loaded."; Settings: "The settings could not be loaded."; the tables, their notice with "Retry". A refusal of an action shows in its window, next to its field, or above the table. |
| Reconnecting | What is painted stays; a strip warns "Reconnecting…" until the connection comes back. |
| App inactive | "This app is not active in this business" instead of the figures and the table. |
| No permission | What it cannot do does not appear (neither **+**, nor import or export, nor the stock actions, nor the switch: "Yes"/"No"); Settings does not show and its address says "This page does not exist"; if it loses the permission with Settings open, the fields lock with "You do not have permission to change these settings. Ask an administrator if you need it.". |

## Flows

| ID | Flow | Status |
|---|---|---|
| | **Catalog** | |
| INVENTORY-F01 | Create a product | done |
| INVENTORY-F02 | Edit a product | done |
| INVENTORY-F03 | Turn a product on and off | done |
| INVENTORY-F04 | Delete a product | done |
| INVENTORY-F05 | Review the products that cannot be sold for lack of VAT | done |
| INVENTORY-F06 | Create and edit a category | done |
| INVENTORY-F07 | Delete a category | done |
| INVENTORY-F08 | Group products into categories for the till | done |
| INVENTORY-F29 | Mark an item as sold out | done |
| | **Import and export** | |
| INVENTORY-F09 | Import products from a CSV | done |
| INVENTORY-F10 | Import categories from a CSV | done |
| INVENTORY-F11 | Export the catalog to CSV | done |
| INVENTORY-F12 | Load the menu of a sector template | done |
| | **Stock** | |
| INVENTORY-F13 | Receive goods | done |
| INVENTORY-F14 | Count a product's stock | done |
| INVENTORY-F15 | Write off stock without a sale (waste, breakage, own consumption) | done |
| INVENTORY-F16 | Look up the history of movements | done |
| INVENTORY-F17 | See the dashboard and the low-stock products | done |
| INVENTORY-F18 | Warn when an item crosses its minimum | done |
| INVENTORY-F19 | Set up the inventory | done |
| INVENTORY-F20 | Decide which items have stock control | done |
| | **With other apps** | |
| INVENTORY-F21 | Lower the stock when a sale is paid | done |
| INVENTORY-F22 | Lower the stock of the components of a menu or a pack | done |
| INVENTORY-F23 | Put the stock back when a sale is voided | done |
| INVENTORY-F24 | Put back the stock of a refund | done |
| INVENTORY-F25 | Print the barcode label | done |
| INVENTORY-F26 | Sell by weight or by measure: units and step | done |
| INVENTORY-F27 | Hand the catalog to the till, to Kitchen and to Menus | done |
| INVENTORY-F28 | Complete the first step "Your catalog" | done |
| | **The item's photo** | |
| INVENTORY-F30 | Choose an item's image from the library | done |
| INVENTORY-F31 | Upload the item's own photo | done |
| INVENTORY-F32 | The photo on the till's tile | done |
| INVENTORY-F33 | The photos travel in the blueprint | done |

All the flows are common to both verticals (restaurant and hair salon).

### INVENTORY-F01 Create a product
Status: done
Actor: administrator, manager
Screen: Products
Steps:
1. In **Products**, tap **+**: the form's panel opens.
2. Type Name, SKU and Price. The price takes "2.20", "1,234.56" or whatever is pasted from the
   screen; on leaving the field it is rewritten in the business's format. Optional are "Cost
   (<currency>)" (the business's: "Cost (PLN)" in Poland), "Initial stock", "Low stock threshold"
   (empty = 10), "EAN-13" and "Description".
3. Choose "Type" ("Physical" or "Service"), the "Unit of measure" ("Unit (ud)" to begin with) and the
   "Tax category". Each tax category says its type ("Product — generic · 21 %", "… · exempt") and
   none is chosen beforehand.
4. On a physical product, the "Track stock for this item" box comes ticked or not according to the
   business's setting, with the note "Following the hub setting". Tapping it fixes the decision for
   this item (INVENTORY-F20).
5. If there are categories, search in "Categories" for the ones that group the product on the till
   and pick them one by one: each one shows below the field, with its button to remove it.
6. Tap "Save" ("Saving…"). The panel closes and the product shows in the table with Status "Yes".
In: the tax categories and their type, from Taxes; the units of measure and the product categories,
from Inventory.
Out: the product, active and linked to the ticked categories, in a single step: either it is saved
whole or nothing is saved. If initial stock was given, it stays in **Movements** as "Initial".
Inventory tells the other apps there is a new product: Sales offers it on the till's grid and the
setup step "Your catalog" is done (INVENTORY-F28).
If it fails: "Save" is off while Name, SKU or tax category are missing. With no tax categories it says
"There are no tax categories yet. Create them in Taxes: a product cannot be sold until it is known how
it is taxed.". An unreadable amount: "This is not an amount. Type a figure, for example 12.50." or
"This amount can be read in two ways…". A quantity that does not fit the unit: "The quantity does not
respect the step allowed for this unit". A SKU another live product already has: "That SKU already
exists in the catalog"; a repeated EAN-13: "Another product of the catalog already has that EAN-13". A
tax category that is no longer in Taxes is refused, also if it arrives through the assistant or the
API. Every refusal shows inside the panel and nothing is saved.
Involved: SALE-F01, TAX-F01, TAX-F19

### INVENTORY-F02 Edit a product
Status: done
Actor: administrator, manager
Screen: Products
Steps:
1. In **Products**, tap "Edit" on the row (or tap the "Not configured" mark): the panel "Editing
   product — <name>" opens with the current data.
2. Change what is needed. The SKU is locked ("The SKU is the product's identity: it is not edited").
   The stock is not edited here: it is received (INVENTORY-F13) or counted (INVENTORY-F14). The "Type"
   and the "Initial stock" do not show.
3. Tap "Save changes". "Cancel editing" or closing the panel leaves it as it was.
4. The row shows the new data.
In: the product as it is saved; the tax categories, from Taxes; the units and the product
categories.
Out: the product changed, with its categories, in a single step. Inventory tells of the change and of
each category added or removed. The new price is for what is added to a bill from now on: an open
bill keeps the price from when it was ordered (Sales decides it).
If it fails: the same refusals as creating (INVENTORY-F01), inside the panel, and nothing is saved.
The tax category cannot be emptied: the field has no empty option. The unit of a product with stock
is not changed: "The unit of a product with stock cannot be changed. Count its stock to zero and change
it afterwards.".
Involved: SALE-F01, TAX-F01, TAX-F19

### INVENTORY-F03 Turn a product on and off
Status: done
Actor: administrator, manager
Screen: Products
Steps:
1. In **Products**, tap the switch in the row's Status column.
2. Off, the product goes to "No"; on, to "Yes". A "Not configured" product has no switch until it has
   a tax category (INVENTORY-F05).
In: the product.
Out: the product active or inactive; Inventory tells of the change. Inactive, it stops showing on the
till and in the sales catalog, in the Dashboard's figures, in the low-stock list and in the number of
products of each category. It stays in Products and in its movements.
If it fails: the reason shows above the table ("The product could not be updated" or the one the app
gives). Without permission to change, "Yes"/"No" shows without a switch.
Involved: SALE-F01

### INVENTORY-F04 Delete a product
Status: done
Actor: administrator, manager
Screen: Products
Steps:
1. In **Products**, tap "Delete" on the row.
2. The "Delete product" window says "<name> (<SKU>) — will be removed from the catalog (soft delete;
   its stock movements are kept)".
3. Tap "Delete" (or "Cancel"). The row disappears.
In: the chosen product.
Out: the product is deleted and inactive, out of every list and of the till. Its SKU and its EAN-13
are free for another product. Its movements stay in **Movements** with its name. Inventory tells that
the product is gone. It does not check whether it has stock or is on an open bill: Sales refuses, when
charging, the line of a product that is no longer in the catalog.
If it fails: "The product could not be deleted" (or the reason) above the table.
Involved: SALE-F01

### INVENTORY-F05 Review the products that cannot be sold for lack of VAT
Status: done
Actor: administrator, manager
Screen: Products
Steps:
1. On the till, the notice "N items cannot be sold: their VAT is not set up." brings "Review the
   catalogue" (only for whoever can change products): it opens **Products** filtered by "Not
   configured". It can also be reached by filtering Status → "Not configured".
2. Each row carries the mark "Not configured · Missing tax category": tapping it opens the edit
   form.
3. Choose the "Tax category" and tap "Save changes". The product goes to "Yes".
In: the products whose tax category is no longer in Taxes. None is made up for them.
Out: the product with its tax category; Inventory tells of the change and the till stops marking it
"VAT missing".
If it fails: the form's refusals (INVENTORY-F02).
Involved: SALE-F01, TAX-F01

### INVENTORY-F06 Create and edit a category
Status: done
Actor: administrator, manager
Screen: Categories
Steps:
1. In **Categories**, tap **+** (or tap a row to edit it: "Editing category — <name>").
2. Type the Name. If you leave "Slug (optional)" empty, it fills itself with the name in lower case
   and with hyphens. When editing, leaving it empty keeps the one it had; through the assistant or the
   API, an empty slug is remade from the name (a category is never left without a slug). Choose, if you
   want, "Tax rate" ("— (default)" leaves it empty).
3. Tap "Save" or "Save changes". The category shows in the table with its number of products.
In: the tax categories and their type, from Taxes.
Out: the category saved. Editing it from the screen does not touch what the screen does not show: the
description, the icon, the colour and the order set through the assistant or the API are kept. Sales
reads it for the till's category strip, and Kitchen to choose what it sends to each station. A
category is not turned off: it is created, edited or deleted.
If it fails: "Save" is off without a Name. A refusal shows inside the panel, with its reason.
Involved: KITCHEN-F04, SALE-F01, TAX-F01

### INVENTORY-F07 Delete a category
Status: done
Actor: administrator, manager
Screen: Categories
Steps:
1. In **Categories**, tap "Delete" on the row.
2. The "Delete category" window says "<name> — N product(s) will lose this category (unlinked;
   products are kept)". N counts the active products.
3. Tap "Delete and unlink" (or "Cancel").
In: the chosen category.
Out: the category is deleted and all its products, active or not, unlinked in the same step; the
products stay. The till stops grouping them under it.
If it fails: "The category could not be deleted" (or the reason) above the table.
Involved: KITCHEN-F04, SALE-F01

### INVENTORY-F08 Group products into categories for the till
Status: done
Actor: administrator, manager
Screen: Products
Steps:
1. Create the category first (INVENTORY-F06).
2. In the product's form (new or edit), search in "Categories" and pick one or several: each one shows
   below the field, with its button to remove it, and it is not offered again. The field only shows if
   there is some category.
3. Save. In **Categories**, the Products column goes up; on the till, the item shows under that
   category.
In: the business's categories.
Out: the link between product and category, saved together with the product; Inventory tells of each
category added or removed. A product can be in several. Sales filters the till's grid with these links
(only of active products) and Kitchen uses them for its routing. The till sorts products and
categories by name.
If it fails: the form's refusals; if something fails neither the product nor its categories are saved.
A product without a category is sold all the same: it shows under "All".
Involved: KITCHEN-F04, SALE-F01

### INVENTORY-F09 Import products from a CSV
Status: done
Actor: administrator, manager
Screen: Import products
Steps:
1. In **Products**, tap the table's import CSV button and choose the file (with a header on the first
   line; separated by commas or by semicolons, as Excel saves it in Spanish). Nothing is created yet.
2. In "Check the import", each column comes with its field guessed from the header, in Spanish or
   English and with or without accents ("Name", "Code", "Price", "VAT"…). Change it or set "Do not
   import". Name, SKU, Price, Cost, Stock, Threshold, EAN-13, Description, Unit and Tax category can be
   imported; Name and SKU are required.
3. Look at the "First {n} rows of {total}" and at the rehearsal of the whole file: "{ready} row(s) ready
   · {failed} with problems", with the line and the reason of the first ten.
4. Tap "Import {n} product(s)" (or "Cancel", which leaves no trace).
5. If some tax text is not recognised, or there are rows with no tax column ("Rows with no tax
   category"), "CSV tax categories" shows. For each one: "Pick" a category, "Create" one (Key and Name)
   or "Skip". Tap "Confirm & import". What is chosen for a text is saved in Taxes and the next import
   already recognises it; what is chosen for "Rows with no tax category" is not saved and is asked each
   time.
6. While it creates, above the table it reads "Importing {done}/{total}…" with "Stop".
7. When it ends, "Import result": "Rows", "Created", "Skipped (already existed)", "Failed", a line per
   failure and "Copy report".
In: the file; the tax categories, their names (the translated ones too) and the learnt texts, from
Taxes; the units.
Out: an active "Physical" product per ready row, which follows the business's stock control and carries
no till categories; Inventory tells of each new product. The stock each row brings stays in
**Movements** as "Initial". In Taxes, the learnt texts and the categories created from the tax window.
A row with a SKU that a live product already has counts as skipped and that product is not touched,
whatever its other cells say (so the export itself imports back without failures, also with a negative
stock); a SKU of a deleted product creates a new one.
If it fails: row reasons: "Name or SKU missing", "Price is not a number" (also for the cost), "Price or
cost too large", "SKU repeated in the file", "Quantity is not a number", "Quantity too large", "The
quantity does not respect the step allowed for this unit", "Unit of measure not recognized", "A text is
longer than its column allows", "Another product of the catalog already has that EAN-13" and "The tax
category is missing" or "Tax category not recognized". If Taxes cannot save a learnt text or a created
category, the report says so and its rows stay as failed with that reason. "Cancel" in the tax window
imports nothing. "Stop" keeps what was already created and the report says "The import was stopped
halfway. What had already been created is counted below; the rest of the file was left untouched.".
Involved: TAX-F02, TAX-F14, TAX-F15

### INVENTORY-F10 Import categories from a CSV
Status: done
Actor: administrator, manager
Screen: Categories
Steps:
1. In **Categories**, tap the table's import CSV button and choose the file (separated by commas or by
   semicolons).
2. The columns Name (required), Slug and Tax category are recognised by their header, in Spanish or
   English ("Nombre"/"name", "IVA"/"tax"…).
3. A category is created per row with a name; the slug, if it does not come, is taken from the name.
4. When it ends, "Import result": "Rows", "Created", "Skipped (already existed)", "Failed", a line per
   failure and "Copy report". The table reloads.
In: the file; the tax categories and the learnt texts, from Taxes.
Out: the categories created. A row with the name of a category that already exists is skipped, so
repeating the file duplicates nothing.
If it fails: each row that does not go in shows in the report with its reason: "The name is missing" or
"Tax category not recognized: <text>".
Involved: TAX-F15

### INVENTORY-F11 Export the catalog to CSV
Status: done
Actor: administrator, manager
Screen: Products
Steps:
1. In **Products** (with the search and the filters you want), tap the table's export CSV button.
2. `inventory-products.csv` downloads with **all** the products that match the search and the
   filters, not only the page shown.
3. In **Categories**, the same button downloads `inventory-categories.csv` (Name, Slug and number of
   products).
In: the products or the categories that match the search and the filters.
Out: the file, with the same headers the import recognises (Name, SKU, Price, Cost, Stock, Threshold,
EAN-13, Description, Unit, Tax category, Active) and the figures as they read on screen (€2.20, 3
units), so it can be imported back without changing anything. It neither saves nor tells anything.
If it fails: with no products, the file carries only the header. Without permission to export, the
button does not show and the app does not hand it over through any other door. A text a spreadsheet
would run as a formula (it starts with =, +, -, @…) comes out with an apostrophe in front, which the
import removes.
Involved: none

### INVENTORY-F12 Load the menu of a sector template
Status: done
Actor: owner, administrator
Screen: Settings · Data and backups › Import
Steps:
1. Open "Settings" › "Data and backups": in "Import" the Hub's templates show, one per sector and
   language (today restaurant and hair salon, in Spanish and in English), with what each one "It
   brings". Tap "Use template" on your sector's (BASE-F29). In a business that is still empty, Home
   offers the same at the top, in "Start with a business like yours", with "Use this one" (BASE-F38).
2. In "Review what it brings", leave Inventory ticked, which says how many categories and products it
   brings (if it is off, "It is off in your business: loading it turns it on."); untick what you do not
   want and tap "Import" (BASE-F31).
3. The report says "Everything went in." and, in Inventory, "Applied", with the categories and the
   products created (BASE-F32).
4. In **Products** the menu is there: each product with its price, its tax category (none shows "Not
   configured", INVENTORY-F05), its photo from the library (INVENTORY-F33) and its category; in
   **Categories**, the template's, and the stock it brings, in **Movements** as "Initial".
In: the template and the ticked apps.
Out: the template's products, created as in the import of a CSV (INVENTORY-F09), with their tax
category, their category, their photo, their stock and their threshold, and the template's categories
(the restaurant's menu brings 16 products in 6 categories, with stock only on the bottled drinks; the
hair salon's, 5 products for sale with their stock). Inventory tells of each new product. If it is loaded
again over a catalog with the same SKUs, those products are skipped: neither their price nor their
stock changes, and the report says "You had it already"; a category with the same name is not
duplicated either.
If it fails: each product goes in or fails on its own: the one Inventory refuses shows in the report with
its name and its reason ("Not everything went in.") and the rest loads. A photo the library no longer
has leaves its product without a photo, with "That image is no longer in the library. Choose another
one." in the report. If Inventory cannot be turned on (the plan's cap on apps), nothing of it loads and
the report says why. What was loaded can be undone whole (BASE-F34).
Involved: BASE-F29, BASE-F31, BASE-F32, BASE-F34, BASE-F38, INVENTORY-F05, INVENTORY-F09, INVENTORY-F33

### INVENTORY-F13 Receive goods
Status: done
Actor: administrator, manager
Screen: Goods receipt
Steps:
1. In **Products**, tap "Receive stock" on the row or on the product's card.
2. In "Goods receipt — <product>" the "Current stock" shows. Type the "Quantity received" and, if you
   want, the "Unit cost (<currency>)".
3. Tap "Record receipt". The window closes and the row shows the new stock.
4. In **Movements** a "Reception" line shows with the quantity in positive and the balance.
In: the product and its unit's step. Through the assistant or the API, a goods receipt can carry several
products and the number of the delivery note.
Out: the stock goes up and the "Reception" movement stays with quantity, balance, cost and, if there is
one, the delivery note. If a cost was typed, it becomes the product's cost. It applies even if the item
has no stock control. If an item with control goes above its threshold, it tells of the crossing
(INVENTORY-F18). Inventory tells that the stock changed.
If it fails: "Record receipt" is off without a quantity. "The quantity does not respect the step allowed
for this unit", an unreadable cost ("This is not an amount…") or the reason of any other refusal show
inside the window. A service is not received: it has no button, and through the assistant or the API it
is refused with "A service has no stock.". A goods receipt with a line without a product, with a product
that does not exist or with a zero quantity is refused whole, saying which line fails: none goes in.
Involved: none

### INVENTORY-F14 Count a product's stock
Status: done
Actor: administrator, manager
Screen: Stock count
Steps:
1. In **Products**, tap "Count stock" on the row or on the product's card.
2. In "Stock count — <product>", type in "Counted stock" what there really is (the total, not the
   difference): if the system says 5 and you count 7, type 7. "Difference" shows (+2).
3. Type the "Reason (required)".
4. Tap "Apply count". The row shows the counted balance; in **Movements** "Count" shows with the
   difference and the reason.
In: the product and its balance.
Out: the balance becomes what was counted and the "Count" movement stays with the difference (if there
is no difference, nothing is recorded). Inventory tells that the stock changed. It applies even if the
item has no stock control. If it crosses the threshold of an item with control, in either direction, it
tells of the crossing (INVENTORY-F18).
If it fails: "Apply count" is off and says what is missing: "Enter the counted stock to continue." or "A
reason is required to apply the count.". A negative quantity or one that does not fit the unit: "The
quantity does not respect the step allowed for this unit". A reason shorter than 3 characters: "Ensure
this value has at least 3 characters.". A service is not counted: it has no button, and through the
assistant or the API it is refused with "A service has no stock.". Everything shows inside the window,
also the reason of any other refusal.
Involved: none

### INVENTORY-F15 Write off stock without a sale (waste, breakage, own consumption)
Status: done
Actor: administrator, manager (screen); assistant
Screen: Products' card and table ("Write-off" window); assistant
Steps:
1. In **Products**, tap "Write off stock" on the row (⋮ menu) or on the product's card: it only shows on
   physical products with stock control and with permission to move stock.
2. In "Write-off — <product>" type the quantity and the reason (waste, breakage, own consumption…) and
   tap "Write off". Through the assistant: "write off 2 bottles of red wine for breakage"; it shows the
   confirmation card with the product, the quantity and the reason.
3. In **Movements** "Decrease" shows with the quantity in negative and the reason.
In: the product, the quantity (in its unit's step) and the reason. It can also be asked for through the
API.
Out: the stock goes down and the "Decrease" movement stays; Inventory tells that the stock changed and,
if it crosses the threshold, of the crossing (INVENTORY-F18). The manager and the administrator can ask
for it.
If it fails: if there is not enough and "Allow selling without stock" is off, "There is not enough stock
to complete the operation.". A product that does not exist: "This product does not exist in this hub.".
A quantity off the step: "The quantity does not respect the step allowed for this unit: use multiples
of …" (it is not rounded). A service is refused with "A service has no stock.", and an item without
stock control with "This article does not track its stock: there is nothing to write off." (409
`inventory.stock_not_tracked`): neither a silent success nor a movement. Everything shows inside the
window.
Involved: none

### INVENTORY-F16 Look up the history of movements
Status: done
Actor: administrator, manager, employee, cashier
Screen: Movements
Steps:
1. Open **Inventory → Movements**: the most recent first.
2. Search by product, SKU or reference, or type the number of a ticket, an invoice or a sale: that sale
   shows and, if it was voided, its void.
3. Filter by Type or by Reference; sort by Date, Quantity or Balance.
4. In a sale, the Reference is the number of its ticket or invoice (or, without Invoicing, the sale's
   number). On a tablet, tapping a cut-off reference unfolds it.
In: the ledger of movements; the number of each sale and that of its ticket or invoice, which Inventory
notes down from Sales when the sale lowers the stock, only to show them and search them.
Out: nothing: it is read-only and no movement is edited or deleted. Each movement also keeps who made
it, although this screen does not show it.
If it fails: a sale whose number Inventory did not get to note down leaves the Reference cell empty. A
ticket that Invoicing numbers later (for example, without the business's details when charging) is read
and searched by the sale's number. Loading error: the table's notice with "Retry".
Involved: INVOICE-F20, SALE-F28

### INVENTORY-F17 See the dashboard and the low-stock products
Status: done
Actor: administrator, manager, employee, cashier
Screen: Dashboard
Steps:
1. Open **Inventory → Dashboard**: "Tracked products", "In stock", "Out of stock" (balance 0 or less),
   "Low stock" (balance equal to or below its threshold) and "Inventory value" at cost. Tapping one of
   the first four leads to **Products**.
2. Below, "Low stock products", from the one with least to the one with most, with its threshold.
3. On **Home**, Inventory's panels: "Low-stock products" (the "Low stock" figure), "Stock value (at
   cost)" and "Lowest-stock products" (the five with the least, the first the one with the least) show
   by default; "Products in stock" is added with ⋮ ("Customize panel"), where they are grouped under
   "Inventory". The value shows in the business's currency.
In: the active, physical products with stock control. The value is the sum of cost times balance of
those with a positive balance; a negative balance does not subtract.
Out: nothing.
If it fails: "Inventory metrics could not be loaded." and the table's notice with "Retry"; on Home, a
panel that cannot be read says "Unavailable". The dashboard and Home's panels refresh on their own with
any stock movement (sale, void, goods receipt, count, write-off), with any creation, change or deletion
of a product and when the settings are saved. Home's panels are seen by whoever can view the products.
Involved: none

### INVENTORY-F18 Warn when an item crosses its minimum
Status: done
Actor: system
Screen: none
Steps:
1. A sale, a write-off or a count takes an item with stock control from being above its threshold to
   being at it or below: Inventory tells of the "below" crossing.
2. While it stays below, it is not repeated. When a goods receipt, a count or a void takes it above
   again, it tells of "recovered", and that re-arms the next one.
3. If the same item goes on several lines of a sale (on its own and inside a menu), it is decided once
   on the total.
4. For someone to find out, the manager sets up in **Flows** an automation that starts with this notice
   (for example, a warning to restock), as with any other notice of the business (FLOW-F21).
In: the balance before and the one after the movement, and the product's threshold.
Out: the notice with the product (SKU and name), the quantity before and the one after, the threshold,
the type of movement and the sale or the delivery note.
If it fails: it only tells of what really moved: a sale that did not lower the stock (INVENTORY-F21)
does not tell. Two movements at once on the same product apply one after the other, so the notice is
neither lost nor sent twice. If the movement does not get saved, the notice does not go out either.
Involved: FLOW-F21

### INVENTORY-F19 Set up the inventory
Status: done
Actor: administrator, manager
Screen: Settings
Steps:
1. Open **Inventory → Settings**. The administrator and the manager see and save it, the same from the
   tab as through the assistant.
2. "Track stock" (out of the box, on): it is what the items that have not decided for themselves do
   (INVENTORY-F20).
3. "Allow selling without stock" (out of the box, off): on, a sale lowers the stock even if it goes
   negative; off, if a sale asks for more than what is left, that item lowers nothing (the sale is
   charged all the same) and a write-off without a sale is refused.
4. "Low stock threshold" (out of the box, 10, in whole units): the threshold a product created without
   its own starts with (it only happens through the assistant or the API: the form and the CSV always
   send one). Changing it does not touch the products that already exist.
5. Tap "Save": "Settings saved.".
In: the business's saved settings (one per business); if they were never saved, the factory ones apply.
Out: the settings, which apply from the next movement. They only tell the open screens (the Dashboard and
the lists refresh); no other app reacts.
If it fails: "The settings could not be saved.". If, with the tab open, another person without the
permission comes in (shift change), the fields lock, "Save" disappears and "You do not have permission
to change these settings. Ask an administrator if you need it." shows.
Involved: SALE-F01

### INVENTORY-F20 Decide which items have stock control
Status: done
Actor: administrator, manager
Screen: Products
Steps:
1. In the form of a physical product, look at "Track stock for this item": ticked or not according to
   what applies to it today; below, "Following the hub setting" while it is not touched.
2. Untick it so it is catalog only ("Catalog only: sales do not move its stock") or tick it so it has
   stock even if the business does not.
3. Save. In **Products**, the Stock column of an item without control shows "—".
In: the business's "Track stock" setting, to show what applies before deciding.
Out: the item's decision; Inventory tells of the change. The item's applies; if it has none, the
business's; if the business never saved settings, yes. A service never has control. Without control,
the sale does not move it, it does not show in low stock nor in the Dashboard's figures and it does not
cross its minimum; receiving and counting do move it.
If it fails: the form's refusals (INVENTORY-F01). Once decided, the item does not go back to "Following
the hub setting".
Involved: SALE-F01

### INVENTORY-F21 Lower the stock when a sale is paid
Status: done
Actor: system
Screen: none
Steps:
1. Sales charges a ticket and tells of the paid sale (SALE-F01). Nothing is done by hand in Inventory.
2. For each line with an item of the catalog, Inventory lowers the quantity sold, also if the line is on
   the house. A service line, an open-price line, an add-on or an item without stock control move
   nothing.
3. If the same item goes on several lines, each one leaves its movement.
4. It is checked in **Movements**: a "Sale" line per line of the ticket, with its number as the
   reference, and the balance that was left.
In: the paid sale, from Sales: each line with its item, its quantity (exact, already checked against the
step when charging), whether it is a service and, if it is a menu, its components (INVENTORY-F22).
Out: the stock goes down and the "Sale" movement stays with the sale as the reference, in the same step.
With "Allow selling without stock" on, the balance can go negative; off, an item that does not reach
lowers nothing. Inventory tells that the stock changed and, if it crosses the minimum, of the crossing
(INVENTORY-F18). If no line moves stock, it notes down that this sale moved nothing, so that its void
puts nothing back.
If it fails: the sale is already paid. If Inventory cannot apply it at that moment, it retries on its
own and, if it keeps failing, it stays in the business's list of failed notices to retry it by hand.
Two sales at once on the last unit: with the setting off, the second lowers nothing; on, it goes
negative.
Involved: SALE-F01, SALE-F11, SALE-F15

### INVENTORY-F22 Lower the stock of the components of a menu or a pack
Status: done
Actor: system
Screen: none
Steps:
1. Sales charges a menu (or a pack) with the customer's choices (SALE-F12).
2. Inventory lowers each chosen component by the line's quantity: three menus, three portions of each
   dish. The menu has no stock and never shows in **Movements**.
3. A component that is a service (the usual in a hair salon pack) or that has no stock control moves
   nothing, and it is not an error.
4. If an item goes on its own and inside a menu on the same ticket, the minimum's crossing is decided
   once on the total.
In: the line's components, which Sales fixes from the Menus menu when charging.
Out: a "Sale" movement per component; the void puts them back the same way (INVENTORY-F23).
If it fails: as INVENTORY-F21.
Involved: COMBO-F10, SALE-F12

### INVENTORY-F23 Put the stock back when a sale is voided
Status: done
Actor: system
Screen: none
Steps:
1. The manager voids a sale in Sales (SALE-F30).
2. Inventory gives back to each item exactly what that sale took from it, according to its own ledger
   of movements: the menus, through their components, and nothing of what did not get lowered (without
   stock control, without balance, services).
3. In **Movements** a "Void" line shows per item, with the same reference as the sale.
In: the voided sale, from Sales (only which one it is).
Out: the stock goes up and the "Void" movement stays. It gives back what went out even if the item
stopped tracking stock in between. Inventory tells that the stock changed and, if an item goes back
above its threshold, of "recovered" (INVENTORY-F18).
If it fails: the void puts back only once, even if the notice arrives twice. The result is the same
whether the sale or the void arrives first: if the void arrives first, the sale that arrives later no
longer lowers anything. An item deleted after the sale gets nothing back.
Involved: SALE-F30

### INVENTORY-F24 Put back the stock of a refund
Status: done
Actor: system
Screen: none
Steps:
1. The manager refunds a sale in Sales (SALE-F31) and marks which lines and how many units come back
   (like the "return to stock" of Square and Toast).
2. Inventory puts those units back to each item, only once per refund.
3. In **Movements** a "Refund" line shows per item, with the sale as the reference and the refund's
   reason.
In: the refund, from Sales: its sale, its identifier, its reason and the lines that come back (product
and quantity). A money-only refund brings no lines.
Out: the stock goes up and the "Refund" movement stays; Inventory tells that the stock changed and, if an
item goes back above its threshold, of "recovered" (INVENTORY-F18). It never puts back more than what
the sale lowered and the earlier refunds did not put back (the ledger says so), so nothing comes back
that the sale did not lower: a service, an open-price line, an item that did not reach or without stock
control. An item that stopped tracking its stock is left as it is. A later void puts back only what is
still missing.
If it fails: the same refund delivered twice puts back once. The refund of a voided sale (or of one
Inventory did not get to see) puts nothing back. A menu line does not put back its components: the
refund's notice does not bring them; if they go back to the shelf, they are counted (INVENTORY-F14).
Involved: SALE-F31

### INVENTORY-F25 Print the barcode label
Status: done
Actor: administrator, manager, employee, cashier
Screen: Product card
Steps:
1. Open the product's card (tap the row or "Details"): the barcode of its SKU shows on a white plate,
   with the SKU below, which also reads with the dark theme.
2. Tap "Print barcode".
3. The label (name, barcode and price) goes to Printing's queue, to the printer with the "Label"
   function, and the card says "The label went to the printer "<name>".". The device that collects that
   printer's jobs prints it (PRINTING-F12). Each tap prints one label.
4. If no printer has the "Label" function, the label waits in the queue and the card says so: "The
   label is waiting in the print queue: no printer has the "Label" function. Give it to one in
   Printing.".
In: the product's SKU, name and price; the printer with the "Label" function, from Printing. It can also
be asked for through the assistant ("print the shampoo's label") or through the API.
Out: a label job in Printing's queue, with the price in the business's currency.
If it fails: whoever does not reach the print queue (Printing is not active, or they cannot print) sees
the browser's print dialog with the code, the SKU and the name, without a price. A SKU with letters a
barcode does not carry (accents, ñ) is neither drawn nor printed: "This SKU cannot be turned into a
barcode: use letters without accents, digits and signs.". Any other refusal shows inside the card:
"Could not print the barcode label: <reason>".
Involved: PRINTING-F04, PRINTING-F12

### INVENTORY-F26 Sell by weight or by measure: units and step
Status: done
Actor: administrator, manager
Screen: Products
Steps:
1. In the product's form, choose the "Unit of measure": "Unit (ud)", "Kilogram (kg)", "Gram (g)",
   "Tonne (t)", "Litre (l)", "Millilitre (ml)", "Minute (min)" or "Hour (h)".
2. Each one has its step: the gram within the kilo, the millilitre within the litre, the kilo within the
   tonne, the quarter of an hour in the hour and the whole unit in the others.
3. The initial stock, the threshold, the goods receipt, the count and the write-off only take quantities
   of that step.
4. On the till the item is sold by typing the quantity (0.532 kg) and the sale lowers that exact
   quantity, without rounding (SALE-F10).
In: the business's units, which arrive when Inventory is turned on.
Out: the product with its unit. Sales reads it for the line; the price is per 1 of the unit. Through the
assistant or the API, the price can refer to another quantity (per 100 g, or per kilo with the stock in
grams).
If it fails: "The quantity does not respect the step allowed for this unit" on screen; "The quantity
does not respect the step allowed for this unit: use multiples of …" through the assistant or the API.
The unit of a product with stock is not changed (INVENTORY-F02).
Involved: SALE-F10

### INVENTORY-F27 Hand the catalog to the till, to Kitchen and to Menus
Status: done
Actor: system
Screen: none
Steps:
1. When the till opens, Sales asks Inventory for the active products (the sold-out ones, to show them in
   grey), the categories, which categories each product has and the units. When charging, it asks for
   the whole sales catalog: price, cost, tax category, unit and whether each item has stock control.
2. Kitchen asks for the products and the categories to choose what it sends to each station.
3. Menus asks for the products that can be set as a component: the active ones, also those sold out
   today (a menu is built with them); when selling, it does not offer a choice whose product is sold out.
4. Without Inventory active, the till says so on the grid ("Inventory is not active, so there is no
   product grid. You can still charge open-price sales; …") and sells services and open price.
In: nothing: the other apps ask for it (see [Services](#services-what-goes-in-and-what-comes-out)).
Out: the readings. In the sales catalog only the products on sale show: active, not sold out
(INVENTORY-F29) and not deleted; the category map carries the active ones. The till's grid and search
also show what is sold out, in grey with "Sold out", and the figures of its strip ("All" and each
category) count what the grid shows: the active ones, sold-out ones included. They do not let it be
ordered: tapping it adds nothing and says "… is sold out.", and a new line of a sold-out item that
arrives through the assistant or the API is refused without writing anything (SALE-F07). An item marked
sold out with the till open turns grey at once, without reloading, and comes back the same way; the menu
that cannot be completed without that item leaves the till (COMBO-F12). The sales catalog carries no
stock: the till neither shows nor checks how many units are left.
If it fails: whoever asks decides. Sales refuses a catalog line if it cannot read the sales catalog and
warns on the till if Inventory is active and does not answer; Kitchen is left without routing options.
Involved: COMBO-F06, KITCHEN-F04, SALE-F01, INVENTORY-F29

### INVENTORY-F28 Complete the first step "Your catalog"
Status: done
Actor: administrator, manager
Screen: Home: Finish setting up your business
Steps:
1. In the "Finish setting up your business" list the required step "Your catalog" shows ("Add at least
   one product so there is something to sell."), marked "Important".
2. "Set up" leads to **Inventory → Products**.
3. As soon as there is an active product (physical or of the service type), the step shows as done,
   without reloading.
In: the number of active products.
Out: the step done or pending. It is seen by whoever can create products.
If it fails: if all the products are turned off or deleted, the step goes back to pending, also without
reloading.
Involved: none

### INVENTORY-F29 Mark an item as sold out
Status: done
Actor: administrator, manager
Screen: Products; Product card
Steps:
1. A dish or an item runs out halfway through the day: in **Inventory → Products**, find it and, in its
   row's "⋮" menu, tap "Mark sold out". Also from its card, with "Mark sold out", or by telling the
   assistant ("the croquettes have run out").
2. The row shows the "Sold out" badge next to its switch, which stays on: the item is not turned off nor
   does it lose anything. The till stops selling it at once: on the grid and in the search it shows in
   grey with "Sold out" and cannot be ordered, also on the tills that were already open, and in the
   menus "Sold out in Inventory" shows: the menu that could only be completed with it stops being
   offered.
3. To see everything sold out, filter Status by "Sold out".
4. When there is some again, tap "Put back on sale" in the "⋮" menu or on the card: the badge goes away
   and the till sells it again.
In: the item (through the screen, or by its SKU or its name from the assistant or the API) and whether
it is sold out or goes back on sale.
Out: the item marked or unmarked; Inventory tells of the change (`inventory.product.updated`). Marking
it twice changes nothing. Turning it off, on or editing it does not take the mark away. A sold-out item
keeps counting in its category, because the till keeps showing it in grey (INVENTORY-F27), and it does
not show in the sales catalog.
If it fails: the reason shows above the table or inside the card ("Could not change whether the product
is sold out" or the one the app gives). Whoever cannot change products sees the badge, but not the
actions. An item that no longer exists gives "This product does not exist in this hub".
Involved: SALE-F01, INVENTORY-F27, COMBO-F12

### INVENTORY-F30 Choose an item's image from the library
Status: done
Actor: administrator, manager, assistant
Screen: Products
Steps:
1. In the product's form (the **+** or "Edit"), in "Photo", tap "Choose from the library": the "Image
   library" window opens with the "Search image…" box already filled with the product's name.
2. Search in Spanish or in English ("café con leche", "latte", "champú"): the search looks at each
   image's title and synonyms, never at its file name. Each image shows with its title in the business's
   language (in English if it is not Spanish). The tabs "All", "Hospitality", "Hair", "Beauty", "Retail",
   "Fitness" and "Spa and wellness" narrow by sector; they come 60 at a time with "Load more".
3. Tap an image: the window closes and the form shows it in "Photo", with "Change" and "Remove photo".
4. Tap "Save" or "Save changes": the photo stays on the item. "Cancel editing" or closing the panel
   discards it.
5. Through the assistant: "put a photo on the white coffee". The assistant searches by the item's name,
   shows up to five candidate images by their title and asks which one; it never sets one on its own.
   When one is chosen, it asks for the one-tap confirmation card and sets it.
In: the item and ERPlora's image library, the same for every business, with each image's title and
synonyms in Spanish and in English.
Out: the item with its library image. The business does not keep a copy of the image, only which one it
is, so it does not use space of its plan. Inventory tells of the change (`inventory.product.updated`) and
the till shows it without reloading (INVENTORY-F32). Choosing another one replaces it; if the previous
one was an own photo (INVENTORY-F31), it is deleted from the business's folder. "Remove photo" leaves the
item with its initials. The candidates come from `inventory.product.suggest_image`, the search is
`base.catalog_image.search` and the photo is set or removed by `inventory.product.set_image`.
If it fails: if the library does not answer, "The image library could not be loaded." with "Retry", and
the product can still be saved without a photo. No results: "No image matches your search. Try another
word or upload a photo.". The assistant that finds no candidates says so and proposes uploading a photo
from the card. An image the library no longer has is refused when the photo is saved: the panel says
"The product has been saved, but the photo has not: That image is no longer in the library. Choose
another one." with "Retry", and the item keeps the photo it had (through the assistant or the API
nothing is saved). Whoever cannot change products does not see "Photo", and the app also refuses it
through the assistant or the API.
Involved: INVENTORY-F01, INVENTORY-F02, INVENTORY-F32, BASE-F93

### INVENTORY-F31 Upload the item's own photo
Status: done
Actor: administrator, manager
Screen: Products
Steps:
1. In the product's form (the **+** or "Edit"), in "Photo", tap "Upload photo" and choose an image from
   the device (on the phone or the tablet, also with the camera): JPG, PNG or WebP of up to 2 MB.
2. The form shows it in "Photo", cropped square, with "Change" and "Remove photo".
3. Tap "Save" or "Save changes": the item is saved and then its photo ("Uploading photo…"). "Cancel
   editing" or closing the panel discards it.
In: the chosen image and the item.
Out: the photo, turned into a 512 × 512 WebP (cropped at the centre), in the business's folder, which
only the business's people see and which counts in its plan's space, like its files. The item points at
it and Inventory tells of the change (`inventory.product.updated`); the till shows it without reloading
(INVENTORY-F32). Uploading another one, choosing one from the library or "Remove photo" deletes the
previous one from the folder; deleting the item (INVENTORY-F04), too. The upload is
`inventory.product.upload_image`, also through the API.
If it fails: next to "Photo", when choosing it, and nothing is uploaded: an image of more than 2 MB, "The
photo weighs more than 2 MB. Choose a lighter one."; a file that is not an image, "That file is not a
photo. Upload a JPG, PNG or WebP image.". If the item was saved and the photo was not, the panel says so
("The product has been saved, but the photo has not: <reason>") with "Retry", which only uploads the
photo again, and the item keeps the photo it had; the reason is, with no space in the plan, "There is no
space left for that file: your plan includes <space>." and, if the storage does not answer, "The photo
could not be saved. Try again.".
Involved: INVENTORY-F01, INVENTORY-F02, INVENTORY-F04, INVENTORY-F32, BASE-F28

### INVENTORY-F32 The photo on the till's tile
Status: done
Actor: employee, cashier
Screen: Sales: Sell; Products; Product card
Steps:
1. On the till (Sales), each item's tile shows its photo above the name, the unit and the price; what is
   sold out shows in grey with "Sold out", also with a photo. The till's search shows the same tiles.
2. An item without a photo, or whose photo cannot load, shows its initials over its colour, as until now:
   never a gap or a broken image.
3. The menus' tiles (Menus) follow the same rule: their photo if they have one and, if not, their
   initials.
4. In **Inventory → Products**, each row carries before the name, in the "Photo" column, the photo's
   thumbnail (or the initials), and each card its "Photo" line; the product's card shows it at the top,
   larger.
In: each item's photo, from the library or its own.
Out: nothing: it is only shown. The library's images are kept on the device and are not asked for again;
the own ones are only seen by whoever has signed in to the business.
If it fails: a photo that does not load (no connection, deleted or no longer in the library) leaves the
initials, without a notice; the till sells all the same.
Involved: SALE-F01, SALE-F07, COMBO-F07, INVENTORY-F27, INVENTORY-F29

### INVENTORY-F33 The photos travel in the blueprint
Status: done
Actor: owner, administrator
Screen: Settings · Data and backups
Steps:
1. Export a backup or a template with Inventory and its data (BASE-F35): the file carries inside the
   items' own photos; the library's do not go inside, only which one each one is, because the library is
   the same in every business.
2. Import it into another business (BASE-F31): each own photo is copied to the folder of the business
   that imports, with a new name, and its item points at the copy; the items with a library image show
   it all the same.
3. The Hub's templates (restaurant and hair salon, INVENTORY-F12) bring each item with its library image;
   one the library does not have yet (the restaurant's patatas bravas) loads without a photo, never
   with another product's.
In: the exported file (.blueprint.zip) with its photos.
Out: the items with their photo in the business that imports. Importing the same file twice duplicates
neither the items nor their photos: the item that is already there (the same SKU) is skipped, and its
photo with it. Undoing the import (BASE-F34) also deletes the photos it copied, and resetting Inventory
(BASE-F37) deletes its items and their own photos.
If it fails: a photo missing from the file, or an image the library no longer has, does not prevent
importing the item: it goes in without a photo (with its initials) and the import's report says so. A
photo that does not fit in the plan's space of the business that imports leaves its item without a
photo, with the reason in the report. The file weighs 20 MB at most, 100 MB uncompressed, with 1,000
entries at most (before, 5 MB, 50 MB and 200): 300 photos of 60 KB fit. A photo inside that is not a
WebP of up to 2 MB makes the file unreadable ("The file holds a photo that is not a WebP image of up to
2 MB, so it cannot be read.").
Involved: BASE-F31, BASE-F34, BASE-F35, BASE-F36, BASE-F37, INVENTORY-F12

## What the verticals share

The restaurant uses Inventory for the menu and the hair salon for the products for sale, with the same
screens, the same settings and the same reaction to the sale. There is no setting per vertical: touching
a piece of this table affects both businesses.

| Shared piece | Flows that use it |
|---|---|
| The product's form (the same panel for creating and editing; tax category required, with no default option) | F01, F02, F05, F08, F20, F26 |
| The tax category picker with name and type ("· 21 %", "exempt"), read from Taxes | F01, F02, F06, F09 |
| The stock control that applies to an item: its own, or the business's if it did not set one; a service never | F17, F18, F19, F20, F21, F22 |
| The rule for lowering stock: balance and movement in the same step; with "Allow selling without stock" off, it does not lower if it does not reach | F15, F21, F22 |
| The ledger of movements (it is not edited; the balance is explained by it; the void gives back what it says) | F01, F09, F12, F13, F14, F15, F16, F21, F22, F23 |
| Each product's low-stock threshold and the crossing notice | F13, F14, F15, F17, F18, F21, F23 |
| The unit of measure and its step | F01, F02, F09, F13, F14, F15, F26 |
| The sales catalog that Sales, Kitchen and Menus read (only active, not deleted products) | F03, F04, F08, F27 |
| The tax texts learnt in Taxes when importing | F09, F10 |
| The item's photo: from the common library or its own, with the initials if there is none | F30, F31, F32, F33 |

## Services: what goes in and what comes out

Everything Inventory does can be asked for through three doors, always with the same rules and the same
permissions: its **screens**, the **assistant** and the **API**. This section is the full list. The
queries run without asking; the actions, from the assistant, first ask for the confirmation card ("one
tap" or "type to confirm", according to the risk).

Through the assistant (also by voice) and through the API, a product is named by its SKU or by its name,
and a category by its name, as well as by its identifier: "write off 2 bottles of red wine" is enough. If
the name matches several, Inventory does not choose: it says which ones they are and asks which one.
Every list can be searched and goes in pages of up to 100.

### What it offers: queries (they read, they change nothing)

| What it gives | Who can | Flows | Service |
|---|---|---|---|
| The products with their stock and whether they are sold out, with search, filters (name, SKU, price, stock, status, sold out) and pages; "on sale" gives what the till offers | view products | F03, F05, F27, F29 | `inventory.product.list` |
| A product's full card (by its id, its SKU or its name) | view products | F02, F25 | `inventory.product.get` |
| The whole sales catalog: products on sale (active and not sold out) with price, cost, tax category, unit and whether they have stock control | view products | F27 | `inventory.product.list_for_sale` |
| The products at their threshold or below, from the one with least to the one with most | view products | F17 | `inventory.product.list_low_stock` |
| Which categories each active product has | view products | F08, F27 | `inventory.product_category.list` |
| The categories, with how many active products each one has (sold-out ones included, what the till shows) | view categories | F06, F27 | `inventory.category.list` |
| The ledger of movements: date, product, type, quantity, balance, reason, reference and who made it | view stock | F16 | `inventory.movement.list` |
| The dashboard's figures: tracked products, in stock, sold out, in low stock, value at cost and number of active products | view products | F17, F28 | `inventory.stock.get_summary` |
| The units of measure with their step | view products | F26 | `inventory.unit.list` |
| The inventory settings | manage settings | F19 | `inventory.config.get` |
| Up to five library images for a product's photo, by its name and titled in the business's language; it sets none | view products | F30 | `inventory.product.suggest_image` |

### What it offers: actions (they change data)

| What it does | Who can | Confirmation in the assistant | Flows | Service |
|---|---|---|---|---|
| Creates a product, with its categories and its initial stock | create products | one tap | F01, F20, F26 | `inventory.product.create` |
| Creates many products at once and says which row went in, which was skipped and which failed | import products | one tap | F09 | `inventory.product.bulk_create` |
| Changes a product: data, active or inactive, stock control and categories | change products | one tap | F02, F03, F05, F08, F20 | `inventory.product.update` |
| Deletes a product | delete products | type to confirm | F04 | `inventory.product.delete` |
| Marks a product as sold out or puts it back on sale | change products | one tap | F29 | `inventory.product.set_sold_out` |
| Sets a product's photo, from the library, or removes it | change products | one tap | F30 | `inventory.product.set_image` |
| Uploads a product's own photo (JPG, PNG or WebP of up to 2 MB; kept as a 512 × 512 WebP) | change products | not the assistant's: the file is chosen on the card | F31 | `inventory.product.upload_image` |
| Adds a product to a category | change products | one tap | F08 | `inventory.product_category.add` |
| Removes a product from a category | change products | one tap | F08 | `inventory.product_category.remove` |
| Creates a category | create categories | one tap | F06 | `inventory.category.create` |
| Creates many categories at once, with a report per row | create categories | one tap | F10 | `inventory.category.bulk_create` |
| Changes a category | change categories | one tap | F06 | `inventory.category.update` |
| Deletes a category and unlinks its products | delete categories | type to confirm | F07 | `inventory.category.delete` |
| Exports products or categories to CSV | export products | one tap | F11 | `inventory.product.export`, `inventory.category.export` |
| Records a goods receipt (one or several products, cost and delivery note) | move stock | one tap | F13 | `inventory.stock.receive` |
| Applies a count: the balance becomes what was counted, with a reason | move stock | one tap | F14 | `inventory.stock.count` |
| Writes off a quantity without a sale (waste, breakage, own consumption), with a reason | move stock | one tap | F15 | `inventory.stock.write_off` |
| Sends the barcode label to print | view products | one tap | F25 | `inventory.product.print_label` |
| Saves the settings | manage settings | one tap | F19 | `inventory.config.update` |

### What it announces (for the apps that want to react)

| Notice | When | What it carries | Who uses it | Service |
|---|---|---|---|---|
| New product | Created on screen, import, template, assistant or API | The product and its categories | Flows; Home's panels | `inventory.product.created` |
| Product changed | Change, turn on or off, mark sold out or put back on sale | The product as it is left, also whether it is sold out | Flows; Home's panels; the till, Kitchen and Menus | `inventory.product.updated` |
| Product deleted | Delete | Which one it was (SKU and name) | Flows; Home's panels | `inventory.product.deleted` |
| Product added to a category | Creation, change or a single link | Product and category | Flows | `inventory.product.categorized` |
| Product removed from a category | Change, a single link or a deleted category | Product and category | Flows | `inventory.product.uncategorized` |
| Stock changed | Any movement: initial, goods receipt, count, write-off, sale, void | Product, quantity, balance and type of movement | Dashboard and Home's panels | `inventory.stock.changed` |
| Minimum crossed | An item with control crosses its threshold, downwards or "recovered" | Product (SKU and name), quantity before and after, threshold, type of movement, sale or delivery note | Flows (warn to restock) | `inventory.stock.threshold_crossed` |
| Category new, changed or deleted | Create, change or delete a category | Which one (id and name) | The open screens | `inventory.category.created`, `.updated`, `.deleted` |
| Settings changed | Saving the settings with some change | Nothing | The Dashboard and the open lists | `inventory.config.updated` |

The notices carry only what the "What it carries" column says: neither the business's tax identity nor
data of whoever caused it.

### What it reacts to

| Notice from | What Inventory does | Flows | Service that listens |
|---|---|---|---|
| Sales: sale paid | Lowers the stock of each line and of the menus' components | F21, F22 | `sale.sale.completed` |
| Sales: sale voided | Puts back exactly what that sale lowered | F23 | `sale.sale.voided` |
| Sales: sale refunded | Puts back the units of the lines that come back, once per refund | F24 | `sale.sale.refunded` |

### What it needs from other apps

| From | What for | Flows | Service |
|---|---|---|---|
| Taxes | The tax categories with their type, for the picker (also to name the chosen one when it is not among the first ones) and to import products | F01, F02, F06, F09 | `tax.category.list` |
| Taxes | Check when saving or importing that the chosen tax category exists and is still active, and know which products do not have it (direct reading: it is a required app) | F01, F02, F05, F06, F09, F10 | model `tax.TaxCategory` |
| Taxes | Recognise the text of a CSV's tax column: the key, the name in any language or a learnt text | F09, F10 | `tax.alias.resolve` |
| Taxes | Create a tax category or learn a text from the import | F09 | `tax.category.create`, `tax.alias.create` |
| Sales | The number of a sale's ticket or invoice, for a movement's Reference | F16 | `sale.sale.get` |
| Printing | Send the label to the printer with the "Label" function | F25 | `printing.job.create` |
| Platform | The business's currency (its country's; in ERPlora's own hub, that of its issuer's country), to write the CSV's prices and costs, read them when importing and put it on the label | F09, F11, F25 | `base.business.get` |
| Platform | The title of the library image set on an item, so the assistant's card names it by its title and not by its reference | F30 | `base.catalog_image.get` |

Inventory uses nothing else from other apps: a sale's number arrives in its notice, and that of its
ticket or invoice is given by Sales, not by Invoicing.

### Who can do what

| Permission | Administrator | Manager | Employee | Cashier | Service |
|---|---|---|---|---|---|
| View products | yes | yes | yes | yes | `inventory.view_product` |
| View categories | yes | yes | yes | yes | `inventory.view_category` |
| View stock and movements | yes | yes | yes | yes | `inventory.view_stock` |
| Create products | yes | yes | no | no | `inventory.add_product` |
| Change products | yes | yes | no | no | `inventory.change_product` |
| Delete products | yes | yes | no | no | `inventory.delete_product` |
| Create categories | yes | yes | no | no | `inventory.add_category` |
| Change categories | yes | yes | no | no | `inventory.change_category` |
| Delete categories | yes | yes | no | no | `inventory.delete_category` |
| Import products | yes | yes | no | no | `inventory.import_product` |
| Export products | yes | yes | no | no | `inventory.export_product` |
| Move stock (receive, count, write off) | yes | yes | no | no | `inventory.adjust_stock` |
| Manage settings | yes | yes | no | no | `inventory.manage_settings` |

These are each profile's factory permissions; the administrator can change them in Roles. The
administrator can do everything. The app checks them at every door (screen, assistant and API), not only
on the screen.
