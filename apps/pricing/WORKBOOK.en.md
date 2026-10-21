<!-- generated from WORKBOOK.md sha256:3ad38f7dc178b64d9ed15a555e6cfe60ca91dc5aa4eb44b0299b06dab87d0060 -->

## What it is for and who it is for

Price Lists keeps **other prices** for your products and services and the **automatic discounts**:

- a **price list** is a price other than the catalog's for some products or
  services: "Wholesale", "VIP members", "Summer season". It can be given a **customer
  group** (it only applies to whoever is in that group), some **dates** (it only applies between them) and
  **quantity breaks** ("from 10 units on, €0.80"). One of them can be the **general
  price list**, the one that applies to everybody;
- a **discount rule** lowers the amount of a single line: a percentage, an amount per unit,
  "buy 2, get 1 free" or a discount by quantity tiers. It is limited to everything, to products, to
  services, to a category, to a product or to a service; and, if you want, to a customer group, to
  a minimum quantity and to some dates.

Price Lists **works out the price** of a line: given the product or the service, the customer, the quantity and the
day, it says which price applies, which list it comes from, which rule takes how much off and what is left. It is used by the
apps that sell (Sales, when it asks for it: see "Contract with Sales"), the assistant ("how much is
a haircut for a customer of the VIP group?") and the API.

Who uses it:

- The **owner**, the **administrator** and the **manager** create and change price lists, prices and
  rules, choose the general price list and deactivate what no longer applies.
- The **employee** sees the price lists and the rules and looks up prices.

## Reference adopted

**Which price list wins, how many automatic discounts add up and when the price is set** (skill
`market-decision`, 2026-10-15). The current product chose the lowest price among all the active
price lists (without looking at dates or at the default list), chained every rule by priority
on the ticket's amount, and nobody called it.

| Product | How it solves it | Source |
|---|---|---|
| Business Central | Lists per customer, customer price group or everybody, with dates, minimum quantity and currency; the **best price** (the lowest) on the date wins; without an agreement, the catalog's price; worked out when the line is inserted | https://learn.microsoft.com/en-us/dynamics365/business-central/sales-how-record-sales-price-discount-payment-agreements |
| Shopify | B2B catalogs per company or market, fixed price or % and volume breaks; the **lowest price** wins; automatic discounts do not combine: **the best one for the customer** applies; a manual POS discount always applies | https://help.shopify.com/en/manual/b2b/catalogs · https://help.shopify.com/manual/discounts/discount-combinations · https://help.shopify.com/en/manual/sell-in-person/shopify-pos/discount-management/combining-discounts |
| Lightspeed X-Series | Price books per customer group, store, dates and min./max. units (breaks by repeating the product); the general book is the base; among promotions **the best one for the customer** wins; book and promotion stack | https://x-series-support.lightspeedhq.com/hc/en-us/articles/25534056400411-Running-sales-using-price-books · https://x-series-support.lightspeedhq.com/hc/en-us/articles/25534113032859-Setting-up-multi-save-and-conditional-promotions |
| Odoo 18 | Pricelist on the customer's record or the POS default one; rules with dates, minimum quantity and scope (product, category, all); without a rule, the base price; changing the customer or the quantity recalculates the lines without a manual price | https://www.odoo.com/documentation/18.0/applications/sales/point_of_sale/pricing/pricelists.html |
| Square | The per-customer price is an automatic discount tied to a customer group; rules by quantity, 2-for-1, dates and hours; **a single automatic discount per item, the most favourable** | https://squareup.com/help/us/en/article/6603 · https://developer.squareup.com/blog/discounting-at-square/ |
| Toast | Prices per menu, time of day or level; automatic 2-for-1, volume, fixed or % discounts; **one per item**; manual ones are never removed when recalculating | https://doc.toasttab.com/doc/platformguide/adminAutoApplyDiscounts.html · https://doc.toasttab.com/doc/platformguide/adminToastPosPricingFeatures.html |
| WooCommerce | Coupons (%, fixed per cart or per product, minimum spend, categories, expiry) and Dynamic Pricing per role, breaks per product or category; in categories the biggest discount wins | https://woocommerce.com/document/coupon-management/ · https://woocommerce.com/document/woocommerce-dynamic-pricing/ |
| Holded | Extra rates per product next to the main price, with a default rate on the contact's record | https://help.holded.com/en/articles/6865131 |
| Fresha | Manual discount (fixed or %) per item or on the total at checkout; offers with a duration in online booking | https://www.fresha.com/help-center/knowledge-base/sales/518-apply-a-discount-at-checkout |
| Square forum | An automatic 10 % adds up to a 35 % staff discount and the staff remove it by hand: they ask not to stack | https://community.squareup.com/t5/Square-for-Retail/Stacking-Discounts-MUST-GO/td-p/363325 |
| Shopify forum | Discounts marked as combinable do not combine: "only the largest discounts apply" per item | https://community.shopify.com/t/why-arent-my-automatic-discount-codes-combining-at-checkout/227952 |
| Odoo forum | The customer's pricelist is not applied by itself at the POS and has to be chosen by hand | https://www.odoo.com/forum/help-1/pos-and-customer-pricelist-131813 |

**Wins:**

1. **A price list applies to a customer group or to everybody** (the general one), between its dates, as in
   Business Central, Shopify and Lightspeed. If several price lists have a price for the line, **the lowest
   one** wins (the "best price" of Business Central, Shopify and Lightspeed). Inside a price list, the highest
   minimum-quantity break the line reaches. With no price in any of them, **the catalog's**.
2. **A single automatic discount per line: the best one for the customer** (Square, Shopify, Toast,
   Lightspeed promotions); with equal discounts, the rule with the lower priority and then the one with the lower
   code. The rule applies on the price list's price (Lightspeed: book and promotion stack).
3. **The price is resolved on the server when the line is added** and frozen in it (Business Central,
   Toast). It is asked for again only if the quantity or the customer of the check changes, and never over a
   price set by hand (Odoo).
4. **A manual discount goes on top** of the price already resolved and is not removed when recalculating (Shopify, Toast,
   Odoo). Sales decides and caps it (`max_discount_percent`), not this app.

**Why not the others:** "the most specific rule wins" (Odoo) forces the owner to understand an order they
cannot see, and the forum complains that the customer's pricelist is not applied; chaining every rule
(the current product, Square with the forum's complaint) undercharges without anyone noticing; discounts
by ticket amount (minimum spend) need the whole ticket, which this app does not have: they stay out
("What it does NOT do").

**The quantities of a rule on an item sold by weight** (skill `market-decision`,
2026-10-15): do a "€0.50 per unit", a "buy 2, get 1 free", a tier or a minimum count grams,
kilos or lines?

| Product | How it solves it | Source |
|---|---|---|
| Odoo 18 | The minimum quantity is in the product's unit of measure; loyalty adds up the quantities in that unit and rounds the free units down | Odoo 18 source code: pricelists and loyalty |
| Business Central | Line price and discount per unit of measure and minimum quantity in that unit | https://learn.microsoft.com/en-us/dynamics365/business-central/sales-how-record-sales-price-discount-payment-agreements |
| Dynamics 365 Commerce | Quantity and mix-and-match discounts with a unit of measure on each line; it does not convert units | https://learn.microsoft.com/en-us/dynamics365/commerce/retail-discounts-overview |
| Square | Rules count whole "items"; with a unit of measure it does not say how it counts 0.25 lb | https://developer.squareup.com/reference/square/objects/CatalogProductSet |
| Lightspeed X-Series | By weight, quantity = weight; promotions count items without saying what they do with decimals | https://x-series-api.lightspeedhq.com/docs/promotions |
| Toast | By weight, decimal quantity; the 2-for-1 counts items and does not mention weight | https://intercom.help/toast-central/en/articles/9307949-configure-items-priced-by-weight |
| Loyverse | No quantity rules: weighed items only get the percentage | https://help.loyverse.com/help/how-create-and-configure-discounts |
| Toast forum | The dollar discount only covers the first pound; below 1 lb there is no discount | https://community.toasttab.com/t5/restaurant-operations/discounting-of-weighed-items-under-a-lb/m-p/14871 |
| Reckon forum | A 2 $/kg promotion rounds the weight to units (0.5 kg without discount); they ask for it to go "relative to the weight" | https://community.reckon.com/discussion/5944939/why-isnt-the-promotional-prices-applied-to-weighted-items-in-pos |

**Wins:** counting **in the unit of the price** (kg for a coffee at €20/kg sold in grams), as Odoo,
Business Central and Dynamics 365 Commerce do, with the free units rounded down (Odoo).
**Why not the others:** counting grams gives the coffee away (250 × €0.50) and meets a minimum of 3 with 3 g;
counting each line as one unit is the failure the forums complain about; leaving weighed items out is something nobody
does on purpose, and it leaves a delicatessen without promotions.

## Before you start

1. Price Lists needs **Inventory** (the products and their categories) and **Customers** (the groups):
   turning it on turns both on. **Services** is not needed: if it is there, services also get prices
   and rules for services.
2. If a price list is for a group ("VIP", "Wholesale"), first create the group in **Customers → Groups**
   and put its customers in it.
3. With no price list or rule, everything is charged at the catalog's price: installing Price Lists changes nothing
   until you create the first one.
4. "Today" and the dates of the price lists and the rules are the business's day: in phase 1, the Hub's
   time zone, **Europe/Madrid**. The business's currency is the **euro**.

## Screens

Price Lists opens from the **Price Lists** menu (tags icon). What a person cannot do does not
show, and the app refuses it even if they try through the API or the assistant.

### Price Lists
Two tables, one above the other, as in the current product.

**Price lists**: search box "Search code or name…", columns **Code** (with the tag
**General** if it is the general price list), **Name**, **Currency**, **Customer group** ("Everybody" if it is
the general one, "—" if it has none), **Tax** ("Business default", "Tax included", "Tax
excluded"), **Validity** ("Always", "From Jul 1, 2026", "Until…" or both dates), **Prices**
(how many it has) and **Status** (Active or Inactive). It sorts by Code, Name, Currency, Group and Tax
(by default, by name) and filters, with the funnel of the bar, by Code, Name and Currency (by the
text they contain), Customer group, Tax and Status (on opening, **Active** already chosen;
**Inactive**, or **All** for both); 50 per page, as a list or as cards.

- **+** opens **New price list**: **Code** and **Name** (required), **Currency** (EUR), **Tax**
  (Business default by default), **Customer group** (search box; empty = none), **From** and
  **Until**, and **General list** (a toggle; not possible with a group).
- Row actions: **Open** (also by tapping the row), **Edit**, **Make general** (in the "⋮" menu;
  only on an active one, without a group, in euros and that is not general yet; asks for confirmation), **Deactivate** (in the
  "⋮" menu; asks for confirmation; not on the general one) or **Activate** (on the inactive ones). The employee only sees
  **Open**.

**Discount rules**: search box "Search code or name…", columns **Code**, **Name**, **Type**
(Percentage, Amount per unit, Buy X, get Y, Tiered), **Value** ("10%", "€0.50 per
unit", "Buy 2, get 1", "3+: 10% · 6+: 15%"), **Applies to** ("Everything", "All
products", "All services", the category, the product or the service, with "(deleted)" if
Inventory deleted it; with the customer group after it if it has one, or "Deleted group"), **Validity**, **Priority** and **Status**. It sorts by Code, Name, Type and
Priority (Value is neither sorted nor filtered: its units differ); it filters, with the funnel, by
Code, Name, Type, Applies to and Status (as in the price lists: **Active** on opening); 50 per page.

- **+** opens **New discount rule** (PRICING-F10).
- Row actions: **Edit** (also by tapping the row), **Deactivate** (asks for confirmation) or
  **Activate** (on the inactive ones). The employee has no actions.

### Price list (detail)
It opens from the row and has **Back**; its title is the price list's name. At the top, the price list:
**Code** with the tag **General**, **Customer group** ("Everybody" on the general one), **Currency**,
**Tax**, **Validity** and **Status**, and in the bar **Edit**, **Make general** and **Deactivate /
Activate** (whichever applies; with the same confirmations as in the table).

Below, **Prices**: search box "Search product or service…", columns **Item** (name),
**Type** (Product or Service), **SKU**, **From** (the minimum quantity, with its unit), **Price** and
**Catalog price** (Inventory's; "—" on a service). The prices, in the price list's currency. Sorted
by Item, From and Price; filtered by Type, with the funnel; 50 per page.

- **+** opens **New price**: **Type** (Product or Service), the item's search box (a product by
  name or SKU; a service by name), **From quantity** (minimum quantity, 1 by default) and
  **Price**.
- Row actions: **Edit** (price and minimum quantity; also by tapping the row) and **Remove** (asks for
  confirmation).

## States of each screen

| State | What the person sees |
|---|---|
| Loading | "Loading…" while the first result arrives. |
| Empty | "No price lists.", "No discount rules." or "This price list has no prices yet."; with a search or a filter, "No results". |
| Error | The table's notice with "Retry". A form's refusal shows inside the form and under its field, without losing what was typed; a confirmation's, inside the confirmation. |
| Reconnecting | What is painted stays; a strip says "Reconnecting…". |
| App inactive | "This app is not active in this business". |
| No permission | What they cannot do does not show; if they get there through another door, "You do not have permission". |
| Price list that does not exist | The detail says "This price list does not exist" with **Back**. |

## Flows

| ID | Flow | Status |
|---|---|---|
| PRICING-F01 | See the price lists | done |
| PRICING-F02 | Create a price list | done |
| PRICING-F03 | Edit a price list | done |
| PRICING-F04 | Choose the general price list | done |
| PRICING-F05 | Deactivate or reactivate a price list | done |
| PRICING-F06 | See the prices of a price list | done |
| PRICING-F07 | Put the price of a product or a service in a price list | done |
| PRICING-F08 | Change or remove a price | done |
| PRICING-F09 | See the discount rules | done |
| PRICING-F10 | Create a discount rule | done |
| PRICING-F11 | Edit a rule | done |
| PRICING-F12 | Deactivate or reactivate a rule | done |
| PRICING-F13 | Look up the price of a line | done |
| PRICING-F14 | When a product, a category or a group is deleted, or a service changes | done |

### PRICING-F01 See the price lists
Status: done (server and screen)
Actor: owner, administrator, manager, employee, assistant
Screen: Price Lists
Steps:
1. Open **Price Lists** in the menu: at the top, the active price lists.
2. Search by code or name, sort or filter (Status **Inactive** shows the deactivated ones).
In: the business's price lists.
Out: nothing; the table keeps itself up to date when someone changes a price list or a price.
If it fails: the table's notice with "Retry".
Involved: Customers (the group's name)

### PRICING-F02 Create a price list
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Price Lists
Steps:
1. Tap **+** in "Price lists": **New price list** opens.
2. Type the **Code** (up to 50 characters; unique, case-insensitive: "VIP" and "vip" are the
   same) and the **Name** (up to 200).
3. If you want: the **Currency** (three-letter ISO code with two decimals: EUR, USD, GBP…), the
   **Tax** (Business default, Tax included, Tax excluded), the **Customer group**,
   **From** and **Until** (both included), and **General list**.
4. Tap **Create**: the price list shows in the table, active and without prices.
In: the form. The assistant names the group by its name.
Out: the price list and the notice `pricing.price_list.created`. If it is marked as general, the one that was
stops being so in the same operation: there are never two.
If it fails: under its field and without creating anything: "A price list with that code already exists. Pick a different code."
(also if the one that has it is deactivated), a currency that does not exist or does not have two decimals,
"Until" before "From", a group that does not exist, "The general list is for everybody: take its customer
group off." or "The general list goes in the business's currency (EUR), the one the till sells in." (the toggle
turns off by itself with a group or with another currency).
Involved: Customers

### PRICING-F03 Edit a price list
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Price Lists, Price list (detail)
Steps:
1. **Edit** on the row or in the detail: **Editing price list — {name}** with what it has.
2. Change whatever you want (code, name, currency, tax, group, dates) and tap **Save**.
In: only what changed. Removing the group leaves the price list without a group.
Out: the price list and `pricing.price_list.updated` (without changes, nothing).
If it fails: the same refusals as when creating; the general one cannot be given a group or another currency. If
Customers deleted its group, the column and the form say "Deleted group" and the price list applies to nobody
until it is removed or another one is chosen.
Involved: Customers

### PRICING-F04 Choose the general price list
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Price Lists, Price list (detail)
Steps:
1. **Make general** on an active price list, without a group and in euros (on any other it is not offered).
2. Confirm "{name} becomes the general price list: it will apply to every customer, and the current one will
   stop being general.".
In: the price list. Through the assistant or the API the mark can also be **taken off** (no general list).
Out: the new general price list and `pricing.price_list.default_changed` (with the previous one). If two people
choose at the same time, a single one remains: the last one.
If it fails: "A deactivated price list cannot be the general one.", "The general list is for everybody: take
its customer group off.", "The general list goes in the business's currency (EUR)…" and, if other choices win the race
three times in a row, "Someone else is changing the general price list right now. Try again
in a moment." (409 `pricing.default_busy`, never a server error).
Involved: none

### PRICING-F05 Deactivate or reactivate a price list
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Price Lists, Price list (detail)
Steps:
1. **Deactivate** and confirm "{name} will stop applying to new sales. Its prices are
   kept.".
2. To use it again, filter by **Inactive** and tap **Activate**.
In: the price list.
Out: the price list and `pricing.price_list.deactivated` or `…activated`. Sales already made do not change.
If it fails: "This is the general price list: make another one general or take its mark off before
deactivating it.", "That price list is already deactivated.", "That price list is already active.".
Involved: none

### PRICING-F06 See the prices of a price list
Status: done (server and screen)
Actor: owner, administrator, manager, employee, assistant
Screen: Price list (detail)
Steps:
1. Tap a price list in the table: its detail opens.
2. Search by name or SKU, filter by Type or sort.
In: the price list's prices; of a product, its name, SKU, unit and catalog price from
Inventory, up to date; of a service, its name.
Out: nothing. Through the API and the assistant, also the prices of a product or a service in every price
list.
If it fails: "This price list does not exist" with **Back**.
Involved: Inventory, Services

### PRICING-F07 Put the price of a product or a service in a price list
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Price list (detail)
Steps:
1. **+** in "Prices": **New price**.
2. In **Type**, choose **Product** (search it by name or SKU) or **Service** (search it by name).
3. **From quantity**: the minimum quantity from which it applies (1 by default; in the product's
   unit, "0.5" kg, and in its step). For volume prices, repeat the product with another minimum
   quantity.
4. **Price**: in euros, as a person types it ("12.50"). It is the price for the same quantity as the
   catalog's (if the catalog says "€0.37 per 100 ud", the price list's is also per 100 ud).
5. Tap **Add**.
In: the price list (active), the item and its price. The assistant names the price list by its code or its
name and the item by its name or its SKU.
Out: the price and `pricing.price_item.added`.
If it fails: under its field and without saving anything: "That price list is not available: it does not exist in this
business or it is deactivated.", "That article already has a price in this list from that quantity.", a
product that does not exist or is deleted, a quantity that does not fit the product's unit or is not
greater than 0, a negative price. Without Services in the business: "Services is not active in this
business.".
Involved: Inventory, Services

### PRICING-F08 Change or remove a price
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Price list (detail)
Steps:
1. **Edit** on the row: change **Price** or **From quantity** and **Save**.
2. **Remove** on the row and confirm "The price of {item} from {quantity} will be removed. It will be charged at
   another list's price or the catalog's.".
In: the price, by its row; the assistant, by the price list, the item and the minimum quantity (1 if it does not
say).
Out: `pricing.price_item.updated` or `pricing.price_item.removed`.
If it fails: "That article already has a price in this list from that quantity.", "That price no longer
exists.". The prices of a **deactivated** price list are not changed (as they are not added: "That price list is not
available…"): the detail offers neither **+** nor **Edit**, only **Remove**.
Involved: none

### PRICING-F09 See the discount rules
Status: done (server and screen)
Actor: owner, administrator, manager, employee, assistant
Screen: Price Lists
Steps:
1. Scroll down to **Discount rules**: the active ones.
2. Search, sort or filter (Status **Inactive** shows the deactivated ones).
In: the business's rules; the name of the category, the product or the group, up to date.
Out: nothing.
If it fails: the table's notice with "Retry".
Involved: Inventory, Customers

### PRICING-F10 Create a discount rule
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Price Lists
Steps:
1. **+** in "Discount rules": **New discount rule**.
2. **Code** and **Name** (required; the code, unique).
3. **Type** and its value (the units are those of each item's price: kg for a coffee at €20/kg
   sold in grams; one unit for what is sold by units and for services):
   - **Percentage**: the % taken off the line (up to 100, two decimals).
   - **Amount per unit**: the euros taken off for each unit of the price sold.
   - **Buy X, get Y**: "Buy" and "Free" (2 and 1 = every 3 units, 1 free, rounded down).
   - **Tiered**: up to 10 tiers, each one with **From quantity** and **Percent (%)** ("Add
     tier", "Remove tier").
4. **Applies to**: Everything, All products, All services, A category, A product or A
   service (with its search box).
5. If you want: **Customer group** (only for them; when none is chosen, "Every customer"), **Minimum
   quantity**, **From**, **Until** and **Priority** (100 by default; with equal discounts, the lower number
   wins).
6. **Create**.
In: the form.
Out: the active rule and `pricing.rule.created`.
If it fails: under its field: "A discount rule with that code already exists. Pick a different code.", a value that is missing or
out of range for its type, repeated or unordered tiers, a category, a product or a service
that does not exist, "Until" before "From".
Involved: Inventory, Services, Customers

### PRICING-F11 Edit a rule
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Price Lists
Steps:
1. **Edit** on the row: **Editing rule — {name}**.
2. Change whatever you want and **Save**.
In: only what changed; the assistant names the rule by its code or its name.
Out: the rule and `pricing.rule.updated` (without changes, nothing).
If it fails: the same refusals as when creating.
Involved: Inventory, Services, Customers

### PRICING-F12 Deactivate or reactivate a rule
Status: done (server and screen)
Actor: owner, administrator, manager, assistant
Screen: Price Lists
Steps:
1. **Deactivate** and confirm "{name} will stop applying to new sales.".
2. To use it again, filter by **Inactive** and tap **Activate**.
In: the rule.
Out: `pricing.rule.deactivated` or `pricing.rule.activated`. Sales already made do not change.
If it fails: "That discount rule is already deactivated.", "That discount rule is already active." and, if
Customers deleted its group, "This rule's customer group no longer exists: choose another group or take it off
before activating it." (409 `pricing.rule_group_deleted`): without a group it would apply to everybody.
Involved: Customers

### PRICING-F13 Look up the price of a line
Status: done (it has no screen of its own: whoever sells or the assistant asks for it; Sales does not ask for it yet, see "Contract with Sales")
Actor: system (Sales), assistant, employee through the API
Screen: none
Steps:
1. Whoever asks gives the **product** or the **service** (by id, name or SKU), and if they want the
   **customer**, the **quantity** (1 by default), the **moment** (now by default) or a specific
   **price list**.
2. The candidate price lists are the active ones, valid that day, in euros and **of the sale's tax basis**
   (`tax_included`; tax included if it does not say, as at a till) or that follow the business, that
   apply to that customer: the general one and those of their active groups. Prices of different bases are never compared
   (a general one at €10.00 with VAT does not lose against a company one at €9.00 without VAT, €10.89 with
   it). With a specific price list, only that one (it has to be active and valid).
3. In each candidate, the price of the highest minimum-quantity break the quantity reaches. **The lowest
   price** wins; with none, the catalog's.
4. The candidate rules are the active ones, valid that day, for that item (by their scope), without a group
   or of one of the customer's groups, and with the minimum quantity reached. Their quantities (amount per unit,
   buy and free, tiers and minimum) count **in the unit of the price**: for a coffee at €20/kg sold
   in grams, "€0.50 per unit" is per kg, "buy 2, get 1 free" gives 1 kg away out of every 3 kg (the free units
   are rounded down) and a minimum of 3 asks for 3 kg. The discount of each one is worked out
   on the line's amount and **the biggest** wins (with equal discounts, the one with the lower priority and then
   the one with the lower code). Only one.
In: the above; from Inventory, the product (price, unit and step); from Services, the service
(through its query, with the permission of whoever asks); from Customers, the record and its groups.
Out: the catalog price, the line's price and the price list it comes from (or none), whether its prices
include tax, the currency, the line's amount, the discount and the rule that gives it, and the total.
It writes nothing and sends no notice.
If it fails: a product or a customer that does not exist (404), a name that fits several (409 with the
list), a specific price list that does not exist, is deactivated or is not valid that day (409
`pricing.price_list_unavailable`), Services switched off (409 `pricing.services_unavailable`), a
quantity that is not greater than 0.
Involved: Inventory, Services, Customers, Sales

### PRICING-F14 When a product, a category or a group is deleted, or a service changes
Status: done (it has no screen: the app does it by itself, a few seconds after the other app's change)
Actor: system
Screen: none
Steps:
1. Inventory deletes a product (`inventory.product.deleted`): Price Lists removes its prices from every
   price list and deactivates that product's rules.
2. Inventory deletes a category (`inventory.category.deleted`): Price Lists deactivates its rules.
3. Customers deletes a group (`customer.group.deleted`): its price lists are left without a group and its rules are
   deactivated (a group's discount never comes to apply to everybody).
4. Services changes a service (`service.service.updated`): Price Lists copies its new name into its
   prices and its rules.
In: the notice.
Out: `pricing.price_item.removed`, `pricing.rule.deactivated`, `pricing.price_list.updated` or
`pricing.price_item.updated` and `pricing.rule.updated`. Repeating the notice changes nothing.
If it fails: it retries by itself, further apart each time (up to an hour between attempts), and after eight attempts it is
given up and noted down. Meanwhile, a deleted product or category no longer shows in the prices
and a deleted group applies to nobody (it is checked when reading).
Involved: Inventory, Customers, Services

## Services: what goes in and what comes out

Everything can be asked for through the screens, the assistant (by voice or by text, with the session of whoever speaks)
and the API, with the same rules and the same permissions. A price list is named by its id, its code or its
name ("wholesale list"); a rule by its id, its code or its name; a product by its id, its SKU
or its name; a service by its id or its name; a group by its id or its name ("VIP group"); a customer
by their id, their name, their phone or their email. If a name fits several, it says which ones
(`pricing.ambiguous_price_list`, `pricing.ambiguous_rule` or the owning app's).

### What it offers: queries (they read, they change nothing)

| What it gives | Who can | Flows | Service | Live |
|---|---|---|---|---|
| The price lists, with search, filters and sorting, in pages of up to 100 | view | F01 | `pricing.price_list.list` | yes |
| A price list | view | F03, F06 | `pricing.price_list.get` | yes |
| The prices of a price list, or those of a product or a service in all of them | view | F06 | `pricing.price_item.list` | yes |
| The discount rules | view | F09 | `pricing.rule.list` | yes |
| The price of a line (price list, rule, discount and total) | view | F13 | `pricing.price.resolve` | no |

### What it offers: actions (they change data)

| What it does | Who can | Flows | Service |
|---|---|---|---|
| Creates a price list | manage | F02 | `pricing.price_list.create` |
| Changes a price list (only what is sent) | manage | F03 | `pricing.price_list.update` |
| Chooses or takes off the general price list | manage | F04 | `pricing.price_list.set_default` |
| Deactivates a price list | manage | F05 | `pricing.price_list.deactivate` |
| Reactivates a price list | manage | F05 | `pricing.price_list.activate` |
| Puts the price of a product or a service in a price list | manage | F07 | `pricing.price_item.add` |
| Changes a price | manage | F08 | `pricing.price_item.update` |
| Removes a price | manage | F08 | `pricing.price_item.remove` |
| Creates a rule | manage | F10 | `pricing.rule.create` |
| Changes a rule | manage | F11 | `pricing.rule.update` |
| Deactivates a rule | manage | F12 | `pricing.rule.deactivate` |
| Reactivates a rule | manage | F12 | `pricing.rule.activate` |
| Forgets a deleted product | only the platform | F14 | `pricing.catalog.forget_product` |
| Forgets a deleted category | only the platform | F14 | `pricing.catalog.forget_category` |
| Forgets a deleted customer group | only the platform | F14 | `pricing.catalog.forget_group` |
| Copies a service's new name | only the platform | F14 | `pricing.catalog.refresh_service` |

When the Hub has API keys (`erpk_live`), they will reach the queries, creating and changing price lists and
putting, changing and removing prices (to sync prices from another system); choosing the general one,
deactivating and the rules, only from the Hub or the assistant.

### What it announces

| Notice | When | What it carries | Service |
|---|---|---|---|
| New price list | Create | `id`, `code`, `is_default` | `pricing.price_list.created` |
| Price list changed | Edit with some change, or its group deleted | `id` | `pricing.price_list.updated` |
| General price list changed | Choose it or take it off | `id`, `is_default`, `previous_id` | `pricing.price_list.default_changed` |
| Price list deactivated / reactivated | Deactivate / activate | `id` | `pricing.price_list.deactivated`, `…activated` |
| Price put | Add | `id`, `price_list_id`, `product_id` or `service_id`, `min_quantity`, `price` | `pricing.price_item.added` |
| Price changed | Edit, or a service's new name | `id` (or `service_id`) | `pricing.price_item.updated` |
| Price removed | Remove, or the product deleted | `id`, `price_list_id` | `pricing.price_item.removed` |
| New rule | Create | `id`, `code` | `pricing.rule.created` |
| Rule changed | Edit, or a service's new name | `id` | `pricing.rule.updated` |
| Rule deactivated / reactivated | Deactivate / activate, or its product, category or group deleted | `id` | `pricing.rule.deactivated`, `…activated` |

No app listens to them except **Automations**, which can start an automation with any
of them (FLOW-F21). Its steps can also look up price lists, prices, rules and the price of a
line, and use the Price Lists actions that do not ask for confirmation (FLOW-F11): create or change a price list,
put or change a price and create, change or reactivate a rule.

### What it reacts to and what it needs from other apps
- **Inventory** (`requires`): the prices and the rules point at its products and categories; Price Lists reads
  their name, SKU, unit, step and catalog price. It reacts to `inventory.product.deleted` and
  `inventory.category.deleted` (F14).
- **Customers** (`requires`): a price list or a rule can belong to a group; the price of a line reads the
  customer's active groups (a deactivated group stops giving its prices and its rules). If Customers
  **deletes** a group (`customer.group.deleted`), its price lists are left without a group and its rules are
  deactivated (F14); meanwhile, a group that no longer exists applies to nobody.
- **Services** (not a requirement): a price or a rule of a service keeps its id and a copy of its
  name; the service is checked and its catalog price is read with `service.service.get`, with the session
  of whoever asks. It reacts to `service.service.updated` (F14).
- From the platform: the business's time zone (the "today" of the dates).

### Contract with Sales
Sales does **not** require Price Lists and Price Lists does not touch Sales. What is asked of Sales (this app does not do it):

1. In `sale.order.add_line` and `sale.order.add_service_line`, if Price Lists is active, call **by
   name** (`call_app`, as it does with Invoicing or Services) `pricing.price.resolve` with the
   product or the service, the check's customer, the quantity, the moment and **the sale's
   `tax_included`** (only the price lists of that basis or that follow the business compete); Price Lists off or absent
   = the catalog's price, as today.
2. Freeze `unit_price` in the line (the price list's price, in the same price unit as the
   catalog's) and keep `price_list_id`/`price_list_code` and the automatic discount (`discount`, in cents
   of that line, with `rule_id`/`rule_code`) apart from the manual discount, for the ticket.
3. Ask for it again only when that line's quantity or the check's customer changes, and never on
   a free-price line, with an appointment's `booked_price` or with a price set by hand (Odoo).
4. The manual line discount and the check discount go **on top** (Shopify, Toast, Odoo), with Sales'
   `max_discount_percent` cap.
5. The automatic price lists already come in the sale's basis and in euros. Only a price list asked for by its
   name can come in another basis or currency: if the answer's `tax_included` is not `null` and does not
   match the sale's, or the currency is not the sale's, do not use that price (Sales' own
   409): Price Lists converts neither bases nor currencies.
6. On a service, the price list's price only applies if the service has a fixed price (the others are
   typed, as today) and is below `booked_price` and the professional's own price, which keep
   ruling.

### Who can do what

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| See price lists, prices and rules, and look up the price of a line | yes | yes | yes | yes | `pricing.view` |
| Create, change, choose the general one, deactivate and reactivate | yes | yes | yes | no | `pricing.manage` |
