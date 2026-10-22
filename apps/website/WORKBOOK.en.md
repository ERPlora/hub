<!-- generated from WORKBOOK.md sha256:e1ea6d0b2404f0f616b356b51d9352666db03c55776a5b65b90d44c25b8d172c -->

## What it is for and who it is for

Website gives each business a simple page of its own at its ERPlora address (`https://<your-business>.erplora.com/`).
The owner picks one of four designs, fills in its sections (name and logo, title and cover photo, a few words about
the business, its catalog, how to get in touch, where it is) and its colours, hides what she does not use and
publishes. Whoever opens that address without having signed in sees the page; the team signs in from its **Log in**
button, which every template has and cannot be removed. While the page is not published (or has been taken offline),
the address still leads to the team's sign-in, as always.

It is meant like the pages of Square Online, Wix or Squarespace, but reduced to what a salon or a restaurant needs:
fixed sections, no dragging blocks around, no HTML or code of the user's. Changing the design loses nothing: the
content and the design are kept apart.

## Before you start

- The app is in the **Organization** category and needs no other app. If the business has **Inventory** or
  **Services**, the Catalog section can show its products on sale or its offered services.
- Only the **owner** and the **admin** change, publish or take the page offline; the **manager** sees it and shares
  its address and its QR; the **employee** does not see it.

## Screens

### Website (`/website`)
At the top, the status: «Your website is not online yet…» (never published), «Your website is offline…» (taken
offline) or «Your website is online at …» (with the address), and «You have changes that are not published yet.»
when the draft has changed since the last publication. Next to it, **Save**, **Publish**, **Take offline** (only when
online) and **Share and QR**, and whether everything is saved or not.

Below, the editor and the preview. On a computer, side by side; on a tablet or a phone, an **Edit / Preview** tab
switches between the two.

- **Design**: four cards with a drawing of each template in the palette's colours: **Classic** (centred and timeless:
  serif name and headings, a centred header on a soft band and each section in a card), **Modern** (a sticky bar,
  title and photo side by side and each section in two columns), **Minimal** (one narrow column with plenty of air, a
  serif reading face and thin rules between sections) and **Bold** (a dark bar, a full-width header in the main
  colour with big capitals and a strong button). All four suit a restaurant, a salon, a shop or a service.
- **Colours**: eight palettes as cards showing their colours on the light and the dark page, the chosen one
  highlighted: **Ocean**, **Forest**, **Terracotta**, **Slate**, **Rose**, **Sand**, **Midnight** and **Olive**, and
  **Your colours**, which shows two colour fields (main and second) that start from the palette on show and are kept
  if another one is chosen later. Each palette has a light and a dark version and reads well in both (WCAG AA: text,
  links and buttons); with **Your colours**, the page, the bands and the text come from the two colours, and a colour
  that would not read is adjusted just enough.
- **Page background**: **Light**, **Dark** or **Auto** (the default): auto follows each visitor's device, dark when it
  is in dark mode and light otherwise; a note under it says so.
- **Sections**, in this order, each one folding:
  - **Top bar** (always on the page): business name (up to 80) and logo; **Log in** always.
  - **Header** (always): title (up to 80), tagline (up to 160) and cover photo.
  - **About us**: **Show** switch, heading (empty = «About us»), text (up to 4000, with **bold**, lists and links in
    Markdown; no HTML) and a photo.
  - **Catalog**: **Show**, heading (empty = «Our products» or «Our services»), **What to show** (Nothing, Products or
    Services; only those of the apps the business has), the **Categories** (none chosen = all) and **Show prices**.
  - **Contact**: **Show**, heading, phone, WhatsApp (with the country code), email, Instagram, Facebook, TikTok and X
    (`https://` links) and, if **Show opening hours** is on, the week's opening hours: each day open or closed and up
    to three time slots (a closing time earlier than the opening one runs past midnight).
  - **Location**: **Show**, heading, up to four address lines and a map link (`https://`, opened apart).
  - **Footer** (always): one line of text (for example, the company's legal name) and **Log in**.
- The images (jpeg, png or webp, up to 5 MB and 8000 px a side) are uploaded from each image field: **Choose image**,
  and then its thumbnail, **Replace image** and **Remove**.
- **Preview**: the page as customers will see it with the current design and draft, at a computer's or a phone's
  width, and **Reload**. It reloads by itself after each save.

### Share and QR
The website's address with **Copy link**, its QR code and **Download PNG** (to print) and **Download SVG** (to scale up
without losing quality). It warns that, on the device where you signed in, the address opens the app (to see the
page: your phone or a private window) and, if the page is not online, that the address still leads to the team's
sign-in.

### The public page (the business's `/`)
The chosen template with what is published: top bar with the name, the sections' menu (folded on a phone) and **Log
in**; header (with a button to the first section, except in Minimal); the sections that are shown and have content;
footer with **Log in**. It adapts to phone, tablet and computer (Bootstrap 5.3) with no sideways scrolling, in the
chosen palette, light or dark; in auto it follows the visitor's device, also when it changes with the page open
(without JavaScript it shows light). The catalog is painted with what was published and, when the page
opens, refreshed with the products or services of that moment and their prices in the visitor's language. The rest of
the page's texts (Log in, the days, the default headings) come out in the browser's language (English or Spanish);
what the owner writes, as written.

## States of each screen

| State | What the person sees |
|---|---|
| Loading | «Loading your website…» with a spinner; the preview, its spinner until the page arrives. |
| Never published | The notice «Your website is not online yet. Publish it so your customers can see it.» |
| Offline | «Your website is offline. Publish it to put it back online.» |
| Online | «Your website is online at …» and, with unpublished changes, «You have changes that are not published yet.» |
| Saving | «Saving…»; then «All changes saved», or «Unsaved changes» while there are changes. |
| Error | On loading: «The website could not be loaded» with the reason. On saving: the notice and the message under each field, without losing what was typed. On publishing or taking offline: a notice. A preview that does not arrive: «The website could not be loaded» with **Reload**. A catalog whose categories cannot be read says so under the selector. |
| App inactive | «This app is not active in this business». |
| No permission | Without the permission to see it: «Only the owner or an admin can change the website.» With the one to see it (manager): the status, **Share and QR** and that same notice, without the editor. |

## Flows

| ID | Flow | Status |
|---|---|---|
| WEBSITE-F01 | Fill in and save the draft | done |
| WEBSITE-F02 | Choose the design, the palette and the background | done |
| WEBSITE-F03 | Show or hide a section | done |
| WEBSITE-F04 | Upload an image | done |
| WEBSITE-F05 | Show the catalog | done |
| WEBSITE-F06 | See the preview | done |
| WEBSITE-F07 | Publish | done |
| WEBSITE-F08 | Take the page offline | done |
| WEBSITE-F09 | Share the address and the QR | done |
| WEBSITE-F10 | Visit the public page | done |

### WEBSITE-F01 Fill in and save the draft
Status: done (server and screen)
Actor: owner, admin, assistant, API
Screen: Website
Steps:
1. Open **Website** and unfold a section.
2. Type: the draft saves itself two seconds after the last change, or when you press **Save**; also when you leave
   the screen if something was left.
In: the template, the colours and the full content of the seven sections. Images are named by their id; the address
they are served at is written by the server.
Out: the saved draft; customers see nothing until it is published. Notice `website.site.updated` (only if something
changed).
If it fails: under each field, without losing what was typed: texts that are too long, a link that does not start
with `https://`, a phone or an email that is not one, two equal times or a repeated day in the opening hours, «This
image was not uploaded to this business's website: upload it again.»

### WEBSITE-F02 Choose the design, the palette and the background
Status: done (server and screen)
Actor: owner, admin, assistant, API
Steps: press one of the four **Design** cards; one of the palettes (or **Your colours** and its two colours); the
background, **Light**, **Dark** or **Auto**. It is saved as in F01.
Out: the same content in another design or other colours; nothing is lost when changing.
If it fails: **Your colours** without its two colours: «Choose the two colours of your own palette.»

### WEBSITE-F03 Show or hide a section
Status: done (server and screen)
Steps: in About us, Catalog, Contact or Location, the **Show** switch. The top bar, the header and the footer cannot
be hidden.
Out: what is hidden is not painted on the page nor given by the public API; it is kept to show it again. A section
that is shown but has nothing (no text nor photo, no contact details, no address nor map, no catalog) is not painted
either.

### WEBSITE-F04 Upload an image
Status: done (server and screen)
Steps: on the logo, the cover or the About us photo, **Choose image**; **Remove** leaves it empty.
In: jpeg, png or webp, up to 5 MB and 8000 pixels a side; the content is checked, not only the name.
Out: the image kept in the business's file store (S3 in AWS) under a name taken from its content; the same image
twice is a single file. Notice `website.image.uploaded`.
If it fails: «The file did not arrive whole…», «The file is empty.», «The image may weigh 5 MB at most.», «This file is
not a PNG image.» (or JPEG, WEBP), «The image may be 8000 pixels a side at most.».

### WEBSITE-F05 Show the catalog
Status: done (server and screen)
Steps: in Catalog, **What to show**: Products (Inventory's on sale: active and not sold out) or Services (the offered
ones); if you want, the categories and whether prices are shown.
Out: on publishing, the catalog is copied into what is published, grouped by category in their order (what has no
category, last), up to 200 items. The public page refreshes it when it opens.
Prices: «€15.00», «From €40.00» and «€20.00 / hour» (services priced from or by the hour), «Free»; a variable price is
not shown.

### WEBSITE-F06 See the preview
Status: done (server and screen)
Steps: the preview is beside the editor (computer) or in the **Preview** tab (tablet and phone); **Computer** or
**Phone** changes its width.
Out: the draft painted by the same code as the public page, with the catalog of that moment; links are not followed
and search engines do not index it.

### WEBSITE-F07 Publish
Status: done (server and screen)
Steps: **Publish** → «Publish your website?» → **Publish**. If something was unsaved, it is saved first.
Out: what is published = the current draft (design, colours, content and the catalog's copy), one more version and
the page online. Notice `website.site.published` (with the version). The draft can keep changing without touching
what is published.
If it fails: «The website could not be published» and what was published stays as it was.

### WEBSITE-F08 Take the page offline
Status: done (server and screen)
Steps: **Take offline** → «Take your website offline?» → **Take offline**.
Out: the address leads to the team's sign-in again; nothing is lost and publishing again goes on with the next
version. Notice `website.site.unpublished`. Already offline, it does nothing.

### WEBSITE-F09 Share the address and the QR
Status: done (server and screen)
Actor: owner, admin, manager
Steps: **Share and QR** → **Copy link**, **Download PNG** or **Download SVG**.
Out: the business's public address (as the browser sees it: `https://<business>.erplora.com/`) and its QR.

### WEBSITE-F10 Visit the public page
Status: done (server and e2e)
Actor: anyone, without an account
Steps: open the business's address. **Log in** leads to ERPlora's sign-in and, back, to the app.
Out: the published page in the browser's language, without cookies, with its own security policy (no user scripts:
only the page's bundle, Bootstrap and the catalog's refresh). With a session open, the address opens the app as
always.

## Services: what goes in and what comes out

Everything can be asked for through the screens, the assistant (by voice or by text, with the session of whoever
speaks) and the API, with the same rules and the same permissions.

### What it offers: queries (they read, they change nothing)

| What it gives | Who can | Flows | Service |
|---|---|---|---|
| The draft, its publication status and the public address (can be followed live) | view | F01–F03, F07, F08 | `website.site.get` |
| The draft painted as the public page (HTML, for the preview) | manage | F06 | `website.site.preview` |
| The categories of Inventory or Services to choose from | manage | F05 | `website.catalog.categories` |
| The QR of the public address, in PNG or SVG | view | F09 | `website.qr.get` |
| What is published, without the hidden sections (no session) | anyone | F10 | `website.public.site` |
| The published catalog, read at that moment and with the prices in the asker's language (no session) | anyone | F05, F10 | `website.public.catalog` |

The two public ones answer only with the page online (otherwise, 404 `website.not_published`) and count each visitor:
60 reads a minute per address, then 429 `base.rate_limited`. The public catalog is kept for a minute.

### What it offers: actions (they change data)

| What it does | Who can | Flows | Service |
|---|---|---|---|
| Saves the draft (template, palette and background, content) | manage | F01–F03, F05 | `website.site.save` |
| Publishes the draft with the catalog's copy | manage | F07 | `website.site.publish` |
| Takes the page offline | manage | F08 | `website.site.unpublish` |
| Uploads an image (base64, up to 5 MB) | manage | F04 | `website.image.upload` |

### Assistant
The assistant (by voice or by text) uses, with the session and permissions of whoever speaks, `website.site.get`,
`website.site.save`, `website.site.publish`, `website.site.unpublish` and `website.catalog.categories`. Every field of
the draft carries its description (name, tagline, about text, contact, opening hours, location, template, palette and
background), and the save's description tells it the draft is sent whole: it reads it first with `website.site.get`,
changes only what was asked and sends it back. Example: «Put on the website the opening hours Monday to Friday from 9
to 8 pm» → it reads the draft, puts the five days with the interval `09:00`–`20:00` in `contact.hours` (leaving the
rest as it was) and calls `website.site.save`; if she adds «and publish it», `website.site.publish`. Not assistant
tools, on purpose: the preview (`website.site.preview`, an HTML page), the image upload (`website.image.upload`, a
file in base64 up to 5 MB) and the QR (`website.qr.get`, an image in base64), which are used from the screen, nor the
visitors' two public reads (`website.public.*`).

### What it announces

| Notice | When | What it carries | Service |
|---|---|---|---|
| Draft saved | Saving with some change | `id` | `website.site.updated` |
| Page published | Publishing | `id`, `version` | `website.site.published` |
| Page taken offline | Taking an online page offline | `id`, `version` | `website.site.unpublished` |
| Image uploaded | Uploading an image | `id` | `website.image.uploaded` |

### What it reacts to and what it needs from other apps
- It reacts to no notice of other apps and requires none (`requires = []`).
- **Inventory** and **Services**, only if installed: the catalog reads them by the name of their queries
  (`inventory.product.list_for_sale`, `inventory.category.list`, `inventory.product_category.list`,
  `service.service.list_for_sale`, `service.category.list`), with a context that can only read them; without the app,
  the catalog comes out empty, never an error.
- From the platform: the hub's registry (its id, for the file store; `base.operations.hub_id`), the store
  `storages["hub_files"]` and the `/p/media/…` view (`base.storage`, `base.media`), the per-visitor limit
  (`base.throttle`) and the `/` entry (`base.public_home`, which calls `apps/website/public_home.py`).

### Who can do what

| Permission | Owner | Admin | Manager | Employee | Service |
|---|---|---|---|---|---|
| See the status, share the address and the QR | yes | yes | yes | no | `website.view` |
| Change, upload images, preview, publish and take offline | yes | yes | no | no | `website.manage` |

## What it does NOT do, on purpose

- A single page per business: no additional pages nor `/p/<page>`.
- No custom domain per business (ADR-0502), no HTML, CSS or JS of the user's and no more templates than the four.
- The opening hours are not imported from Schedules; there is no booking link until Online booking's page exists in
  `/p/…`.
- Images are kept as they are (no size variants nor cropping, and their EXIF metadata is not removed); the ones that
  are no longer used and the old versions are not deleted.
- No sitemap nor robots beyond the preview's `noindex` tag.
- The real activation of the module per business (`AppActivation`) comes in phase 2.
