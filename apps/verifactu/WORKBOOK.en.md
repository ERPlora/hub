<!-- generated from WORKBOOK.md sha256:4231f9897a3e4a0f870c2299c5daca692481094661ae0487d22c2450d33b7164 -->

## What it is for and who it is for

VeriFactu turns every invoice and every ticket that Invoicing issues into its record for the Spanish tax agency
(AEAT): chained to the previous one by its fingerprint, with the QR the customer can check, and sent to the AEAT in
order. What cannot go out at that moment waits in the queue and goes out by itself later. It is only for businesses
in Spain, and it starts in the AEAT's test environment until you go live.

### In detail

VeriFactu is the end of the fiscal chain: every invoice or ticket that Invoicing issues becomes here a chained
**billing record** (each record carries the fingerprint of the previous one), with its verification **QR**,
which is sent to the Spanish tax agency (AEAT). If it cannot go out at that moment, it stays in the queue and
goes out by itself later, in order. It serves the hair salon and the restaurant alike: everything is common.

It is only for businesses in **Spain** (the Canary Islands, Ceuta and Melilla included): VeriFactu binds whoever
pays tax here. A business registered on erplora.com in another country records and sends nothing to the AEAT even
with the app on: its invoices and tickets go out without a VeriFactu record or QR, as with the app off.

Who uses it:

- The **employee** does not open its screens (by its address, "No access" (BASE-F118)); their sales reach the AEAT all the same.
- The **manager**, besides, sends a given record, processes and retries the queue, looks up what the AEAT has
  and tests the connection.
- The **owner** and the **administrator**, besides, upload or remove the business's certificate, go
  live or go back to testing, correct or cancel a record, recover the chain and create the test invoice.
- The **system**, with nobody in front, records every invoice in the same operation that issues it and sends
  the queue.

It does not issue or rectify invoices (that is Invoicing) nor work out taxes (they arrive decided in the
invoice). The business's own certificate, if it uses one, is uploaded here and kept encrypted in the hub's
database.

## Reference adopted

Here the reference is not a competitor: it is the AEAT's rules.

- [Real Decreto 1007/2023](https://www.boe.es/buscar/act.php?id=BOE-A-2023-24840) (Regulation of billing
  computer systems) and the [Orden HAC/1177/2024](https://www.boe.es/buscar/doc.php?id=BOE-A-2024-22138):
  registration and cancellation records, chaining by SHA-256 fingerprint, verifiable QR, identification of the
  computer system, voluntary submission with incident and responsible declaration.
- "Detalle de las especificaciones técnicas para generación de la huella o hash de los registros de
  facturación" v0.1.2 (27/08/2024): the exact order of the fingerprint's fields and its three official cases,
  which the app reproduces in its tests.
- The AEAT's official schemas `SuministroLR.xsd` and `SuministroInformacion.xsd`: every record is validated
  against them **before** it is sealed or sent.
- The **VERI\*FACTU** mode only: every record is filed with the AEAT; that is why there is no event log of the
  NO VERI\*FACTU mode, and "Events" is our own traceability.
- [The AEAT's VeriFactu FAQ](https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu/preguntas-frecuentes.html):
  a generated record has to reach the AEAT; what goes out late because of an incident is declared with
  `Incidencia = S`; the system respects the `TiempoEsperaEnvio` the AEAT returns between submissions and groups
  up to 1,000 records of the same taxpayer per submission.
- From the market (Odoo `l10n_es_edi_verifactu`, Holded, Sage, Square) the split of screens is copied: a list
  of submissions with their status and their QR, the detail with the AEAT's answer, a send-now button and a
  cancel one, and the two routes (own certificate or the provider on your behalf).

## Before you start

- Turning VeriFactu on turns **Invoicing** on with it (it requires it): without invoices there is nothing to
  record. Turning VeriFactu on in the Hub **is** activating it: from that moment it records every invoice that is
  issued. There is no other switch.
- **The issuer** is Invoicing's (Invoicing → Issuer): VeriFactu takes its tax ID and its legal name from each
  invoice, it does not ask for them again.
- **The environment** starts in **testing** (the AEAT's test environment): nothing issued counts before the tax
  agency until going live (VERIFACTU-F08).
- **The sending route** is not chosen: your certificate decides it (VERIFACTU-F04). With your own certificate
  loaded and in force, you file yourself with it; without it, in testing ERPlora files on your behalf with its seal.
  Going live needs your certificate or, where ERPlora files on behalf of businesses, your signed authorisation (the
  Annex I) approved by ERPlora; with both, the certificate wins, and the route of that moment is fixed. The
  authorisation (the representation authorisation) is signed and uploaded here, in "ERPlora files for you", and
  ERPlora reviews it; the certificate is uploaded here, in "My certificate".
- **On the Home**, while you have no way to carry your records to the AEAT's production environment (neither your
  certificate in force nor the approved authorisation), "Finish setting up your business" reminds you with "Set up
  VeriFactu"; its "Set up" leads to VeriFactu → Configuration, and the step turns "Done" as soon as you upload your
  certificate or ERPlora approves the authorisation. In testing it carries the "Important" pill (it does not hold
  back selling: in testing you sell just the same) and only whoever sets up VeriFactu sees it. In production
  (VERIFACTU-F08), if the fixed route is lost (with ERPlora's, the authorisation is revoked; with the certificate's,
  it expires or is removed), it carries "Needed to invoice" and the bell carries the notice "You cannot issue
  invoices yet", with "Set up VeriFactu", because every new sale is refused; the whole team sees it, and whoever does not set up
  VeriFactu is told "An administrator has to set this up.". Only a business in Spain is asked; one without a
  country (a demo) counts as Spain, and one from another country never sees it, neither in testing nor in production
  (hub#682).
- **It is mandatory in Spain.** While it is off in a business in Spain (or without a country, such as a demo),
  "Finish setting up your business" asks whoever runs it to "Turn on VeriFactu" ("Important"), with "Set up"
  leading to **Apps**; as soon as they turn it on, that step goes and "Set up VeriFactu" comes. It never turns on by
  itself: it binds the business to the AEAT until the end of the calendar year, so the owner turns it on (BASE-F01,
  hub#997).
- **The software producer's data** (ERPlora) go fixed in every record (its responsible declaration declares them),
  also "Serves several taxpayers", always "S".
- **Hours and days are the business's**, in its time zone (the one in "Settings"), not Madrid's: the time each record
  is generated at (with its offset), the time the AEAT asked to wait until, the current month the AEAT is asked about
  and the day your certificate expires. A business in the Canary Islands sees its records generated at its own time
  and, on New Year's Eve at 23:30, asks the AEAT about December, even though it is already January in Madrid.

Initial setup, step by step:

1. In **Invoicing → Issuer**, fill in the legal name, the tax ID and the address.
2. Turn **VeriFactu** on in the Hub's apps.
3. Issue a test invoice (**VeriFactu → Settings → Create test invoice**, VERIFACTU-F11) and check in
   **VeriFactu → Records** that its record shows up with its QR.
4. When the route is ready, **Settings → Go live** (VERIFACTU-F08).

## Screens

Six tabs at the foot of every VeriFactu page (those of the menu, in this order): Records, Contingency, Events,
Recovery, Configuration and Settings. The first four, for whoever sends records;
Configuration and Settings, only for whoever configures VeriFactu. The buttons the person cannot use do not show.

### Records
Every invoice and every ticket you issue has its VeriFactu record here, the latest on top, with its status at the
AEAT (Pending, Sent, Accepted, Accepted with errors or Rejected) and its environment, testing or production. Search
them by invoice, issuer or tax ID and filter them by status, type, date or total. Tap one to open its detail: the
invoice, the fingerprint chain, the QR, the AEAT's answer and, if it has not arrived yet, why it waits; from there,
depending on its status and your permission, you send it now, correct it or cancel it.

#### Detail
Menu **VeriFactu → Records**. Title "VeriFactu records". Table of 50 by 50 (table or cards; on the phone, cards
with the invoice number as title) with "Seq", "Invoice", "Date", "Type" (Registration / Cancellation), "F."
(F1…R5), "Issuer", "Total", "Environment" (Testing / Production) and "Status" (Pending, Sent, Accepted, Accepted
with errors, Rejected, in a coloured pill; beside a registration rejected or accepted with errors, "Pending
correction" or "Corrected", which opens the record that corrects it: VERIFACTU-F24). Search box "Search invoice, issuer or tax ID…" (sequence number, invoice
number, issuer's name or tax ID). Filters of status, type, invoice type, correction ("Pending correction" or
"Corrected"), environment, date and total (in euros),
behind the table's funnel with its counter; a total that is not an amount, or a "to" date before the "from" one, is
said under its field and does not filter. The last sealed comes on top. Per row: "View" (also by tapping the row)
and "Verify at the AEAT" (opens the QR's verification page). The list updates by itself when a record is born,
leaves or changes on any device.
Empty: "No records yet. Every invoice you issue is sealed and listed here."; with a search or filter, "No
results". Loading: "Loading…". Error: the message with "Retry".

#### Record detail
It opens from a row of **Records** (`/verifactu/records/<id>`). On top, "Record {number}" with its status, its
environment and "← Back". If it is not at the AEAT (Pending or Sent), the notice "Not at the AEAT yet" with the
why and the when (VERIFACTU-F17). If it was rejected, the notice "The AEAT rejected it" with what to do
(VERIFACTU-F24); once corrected (an "Accepted with errors" too), instead of what to do, "Already corrected with a new
record" with the link "Open the record that corrects it". Blocks:
- **Invoice**: "Invoice", "Issue date", "Operation date" (if it is another), "Invoice type", "Issuer", "Issuer tax
  ID", "Customer" and "Customer tax ID" (if there are any), "Rectifies" / "Replaces", "Base", "Tax" and "Total".
- **Fingerprint chain**: "Seq", "Generated at", "Fingerprint", "Previous fingerprint" (or "First record of the
  chain").
- **QR**: the QR image and "Verify at the AEAT".
- **AEAT response**: "Sent at", "CSV", "Response code", "Response message", "Attempts", "Next attempt" and the
  "Delivery fingerprint" ("Transmission ID", "Envelope digest (SHA-256)"; "Not stamped yet" while it has not gone
  out).
- **XML**: the envelope that is sent (or "The XML is built when the record is sent to the AEAT.").
Buttons by status and permission: "Send now" (VERIFACTU-F25) and "Ask the AEAT" (VERIFACTU-F35) while it is in the
queue, "Correct" (VERIFACTU-F24) and "Cancel record" (VERIFACTU-F30). A refusal shows right above the buttons.
Error on opening: "Record not found" or the failure's message, with "← Back".

### Contingency
The queue of the records that are not at the AEAT yet, in the order they will go out, with their attempts, the next
attempt and the last error. The system sends them by itself, in order, and whatever fails again waits a little
longer before the next attempt. "Process queue" does the pass at that moment and "Retry" sets a record to go out
with the next one. Empty, everything is at the AEAT.

#### Detail
Menu **VeriFactu → Contingency**. Title "Contingency queue" and button "Process queue" ("Processing…" while it
works). Table of the records not yet at the AEAT: "Invoice", "Environment", "Attempts", "Status", "Next attempt"
and "Last error", in the order they go out (every column sorts); search box "Search invoice or error…". Per row:
"Retry" (sets it to go out with the next pass) and "View". Under the table, the result of the last manual pass.
Empty: "Queue empty: everything is in the AEAT.". Loading: "Loading…". Error: the message above the table.

### Events
What has happened with your records and with the connection to the AEAT, most recent first: every record created,
every submission accepted, deferred or failed, every pass of the queue, the chain checks, the queries to the AEAT and
the configuration changes. Search them by type or by message and filter them by type, severity or date.

#### Detail
Menu **VeriFactu → Events**. Title "Audit events". Table, most recent first: "When", "Severity" (Debug, Info,
Warning, Error, Critical), "Type" (Record created, Submission postponed, Submission accepted, Accepted with errors,
Submission failed, Queue processed, Record rescheduled, Chain verified, Chain broken, AEAT query, Chain recovered,
Connection test, Configuration changed) and "Message", composed in the language of whoever looks. Search box
"Search type or message…" that finds by the words that show, in Spanish or in English; filters of type, severity and
date, behind the table's funnel with its counter (a "to" date before the "from" one is said under its field and does
not filter). It updates by itself.
Empty: "No events.". Loading: "Loading…". Error: the message with "Retry".

### Recovery
Here you check that the fingerprint chain of your records is intact and look up the records the AEAT has of your
business this month. If needed, you recover the chain: from the AEAT, after restoring a backup of the database, or
from the last fingerprint of the application you used before, when migrating. Both recoveries ask for
confirmation.

#### Detail
Menu **VeriFactu → Recovery**. Title "Chain recovery". Field "Issuer tax ID" (filled with Invoicing's issuer's)
and the current environment. Block "Chain integrity" with the last verdict ("Fingerprint chain intact ✓",
"Fingerprint chain BROKEN ✗" with the sequence, or "Not validated yet") and the note "This recomputes the SHA-256
fingerprints and verifies the chaining. It does not re-audit the amounts: the base, the tax and the total are
taken as the invoice declared them.". Buttons "Validate chain", "Query AEAT"
and "Recover chain from AEAT". Table "Latest records at the AEAT": "Invoice", "Date", "Fingerprint", "Status",
"CSV" and "Queried on"; empty: "No AEAT data. Press «Query AEAT».". Block "Continue chain manually (migration)" with
"Last fingerprint (64 hex)", "Invoice number" and "Date" and "Continue from this fingerprint". Both recoveries ask
for confirmation ("Confirm recovery" / "Cancel"). When done: "Operation completed.".

### Configuration
Here you prepare how your records reach the AEAT. In "My certificate" you upload your business's electronic
certificate (a .p12 or .pfx file) with its password, see its holder and when it expires, and renew or remove it. If
ERPlora files on behalf of businesses, the tab "ERPlora files for you" lets you download the authorisation form and,
once signed, send it for review, and says what status it is in. Only whoever sets up VeriFactu uploads or sends anything.

#### Detail
Menu **VeriFactu → Configuration**. Title "VeriFactu configuration". With ERPlora's route available, two tabs,
the two routes:
- **"ERPlora files for you"** (opens by default): "Representation
  authorisation" with its status ("Not signed", "Under review since {date}", "Approved on {date}", "Returned on
  {date}" with "Note of the review", "Revoked on {date}"); "What you sent" ("Submission no. {n}, sent on {date}" and
  the documents: "Signed model", "Copy of the identity document", "Signature sample", "Proof of representation");
  "Its steps" (with two or more: each status the account reported, with its date and its reason). Under review or
  approved, "Send again" opens the procedure with its notice ("the new submission replaces the one under review" /
  "you keep filing with the current one") and "Cancel". Not signed, returned or revoked, the procedure is open: the
  introductory text, "Taxpayer: {name} ({taxId}), Invoicing’s issuer." (it is read, not asked for), "1 · Get the
  official form" with "Download the form" (the SaaS's blank form) and how to sign it (by hand or with AutoFirma);
  with a company, "Legal representative" with "Full name of the person signing" and "ID number of the person
  signing" (a sole trader signs themselves and is not asked); the basic information of art. 13 GDPR **before**
  asking for any document; "2 · Upload the signed form" with "Identity document" (DNI / NIE) and the attachments,
  each one a PDF of 5 MB at most: "Attach the signed form (PDF)", "Attach a copy of the ID (PDF)", with a NIE
  "Attach a signature sample (PDF)" and with a company "Attach the proof of representation (PDF)"; "Send for
  review". With no issuer in Invoicing or while the account has not linked the business, it says so and does not
  send. Only whoever sets up VeriFactu sees the procedure. If the account has not sent anything yet, "Your ERPlora
  account has not sent this yet.".
- **"My certificate"**: "Business certificate (.p12 / .pfx)" with "Loaded" / "Not loaded", "Holder", "Holder's tax
  ID", "Kind", "Uploaded on" and "Expires on" (with the notice "Expires in {n} days: upload the renewed one here." at
  30 days or less and "The certificate has expired. Upload a valid one to send to the AEAT.") and, in testing, "AEAT
  test environment": "Not tested yet", "Accepted" or "Refused", with the notice of how it is tried or why it was
  refused (VERIFACTU-F02). Whoever sets up
  VeriFactu sees "Choose the .p12 / .pfx file", "Certificate password", "Upload the certificate" and, with one
  loaded, "Remove" (it asks first, in a card that says what will happen: in testing, "You can keep testing without
  it: your test records keep going out."; in production with your certificate, "Records will wait until you upload
  another certificate."; in production with ERPlora, "Your records keep going out with ERPlora's seal."). Note: "The
  certificate and its password are kept encrypted in this Hub and only travel to ERPlora's gateway when sending to
  the AEAT; they are never shown again.".
When ERPlora's route is unavailable, there are no tabs and nothing of the authorisation is shown. The certificate
is the only card: its status says "No certificate uploaded", "Valid", "Expires soon" or "Expired", along with its
details and expiry notices. In testing without a certificate, "You can test VeriFactu without a certificate. You only
need one to go live."; in production, "Upload a valid certificate to send your records to the AEAT.". "Upload the
certificate" is the only primary action; choosing the file and removing it are secondary. When removing it, the
notice is the same as with the tabs. The encryption note does not mention ERPlora's route.
In a business outside Spain, on top shows "VeriFactu is only for businesses in Spain." as the only reason: "ERPlora
files for you", if available, shows neither the authorisation nor the procedure, and the certificate only shows its
status, without uploading or removing it.

### Settings
Here you see which route your records go out by (with your certificate or through ERPlora) and which AEAT
environment you are in, testing or production. You go live once nothing is missing (if something is, the screen
says what), or go back to testing while no record has been sealed in production. You also test the connection with
the AEAT without sending anything, create a test invoice while in testing and read the system's responsible
declaration.

#### Detail
Menu **VeriFactu → Settings**. Title "VeriFactu settings". Three blocks:
- **"Sending"**: with ERPlora's route available, a sentence with its icon says which route the records go out by
  and what is missing (VERIFACTU-F04), with "Open Configuration": with your certificate, "You file directly with the
  tax agency using your business certificate, uploaded in Configuration → My certificate."; by ERPlora with the
  approved authorisation, "ERPlora files your billing records with the tax agency on your behalf, with its own seal:
  your signed authorisation is approved."; by ERPlora in testing without it, "ERPlora files your test records with
  its seal. To go live, upload your business certificate or get ERPlora to approve your signed authorisation."; by
  ERPlora in production without it, "ERPlora files on your behalf with its seal, but your signed authorisation is not
  approved: your records wait until it is.". Below, "AEAT environment" with the pill "Testing (AEAT test)" or "Production" and, as the case may be, "Go live" (with
  "It cannot go live yet:" and what is missing, if something is missing) or "Back to testing" with its explanation
  and its confirmation; in production, "New sales and invoices are refused until this is fixed:" and the reason, if
  there is no route to the AEAT, and "Records are waiting:" and why, if they wait.
- **"Live test"**: "Test the connection" and "Create test invoice"; below, the result of the last test ("Tested
  on", "Filed through", "Environment", "ERPlora's gateway", "Issuer", "Route ready" and "This business can send." or
  "It cannot send yet:" with the reasons), or "No test run yet.".
- **"Responsible declaration"**: "Read the signed declaration", "Declaration version" and the "Identifying data of
  this system" (Producer, Producer tax ID, System name, System code, Installed version, Installation number,
  VERI\*FACTU only, Can serve several taxpayers, Serves several taxpayers: always "S").
When ERPlora's route is unavailable, "Sending" shows the certificate status and "Upload your certificate" or
"Manage certificate", without the route's sentence or any reference to the authorisation. If it is needed for
production, an information notice beside "Go live" says "You can keep testing. To go live, upload your business
certificate.", with no link of its own: the action is the one beside the certificate status, a single one in the
card; the other blockers stay in their list and the button is
disabled while any remain. Notices and diagnostics do not bring back the authorisation or the old route's name, and
"Test the connection" is secondary in testing.
In a business outside Spain, on top shows "VeriFactu is only for businesses in Spain." as the only reason, and "Go
live", "Test the connection" and "Create test invoice" are disabled.
Screen notices: the result of each action in a strip on top (green if it went well, red if not).

## States of each screen

| State | What the person sees |
|---|---|
| Loading | "Loading…" while the first result arrives. |
| Empty | Each table's own text (or "No results" with a search or filter). |
| Error | The table's notice with "Retry"; a refusal of an action shows above its buttons. |
| Reconnecting | What is painted stays; a strip warns "Reconnecting…". |
| App inactive (`app_inactive`) | "This app is not active in this business". |
| No permission | What they cannot do does not show; if they arrive through another door, "You do not have permission". |

## Flows

| ID | Flow | Status |
|---|---|---|
| VERIFACTU-F01 | Activate VeriFactu | done — turning the app on in the Hub is activating it, in that business; outside Spain, Apps does not offer it and the hub refuses it (`can_enable`, hub#694), and one already on records and sends nothing |
| VERIFACTU-F02 | Upload the business's own certificate | done — in the Hub; encrypted in the hub's DB with `FISCAL_CERTIFICATE_KEY` |
| VERIFACTU-F03 | Remove the own certificate | done — in the Hub |
| VERIFACTU-F04 | Know who files: my certificate or ERPlora | done — the route is not chosen: the certificate decides it and it is fixed on going live |
| VERIFACTU-F05 | Sign and upload the representation authorisation so ERPlora files | done — uploaded in the Hub, reviewed by staff in the SaaS (`fiscal/`) and the status comes back in the snapshot; with the ERPlora route closed on the server it is not offered |
| VERIFACTU-F06 | Send the authorisation again | done — in the Hub, like VERIFACTU-F05 |
| VERIFACTU-F08 | Go live | done — production = `prod` deployment ∧ `VERIFACTU_PRODUCTION_ENABLED` ∧ (an own certificate in force and accepted by the AEAT's test environment \| ERPlora route open on the server with an approved authorisation) ∧ active account, in every plan (Free included); the server keeps it closed until ERPlora opens it (under Ioan's supervision) |
| VERIFACTU-F09 | Go back to testing | done |
| VERIFACTU-F10 | Test the connection with the AEAT | done — with the SaaS gateway's probe (`/internal/verifactu/probe`) |
| VERIFACTU-F11 | Create a test invoice | done |
| VERIFACTU-F12 | Look up the responsible declaration | done |
| VERIFACTU-F13 | Record an issued invoice | done — Invoicing asks for it by name inside its issuing; the worker's outbox relay stays as a backup |
| VERIFACTU-F14 | Record a rectifying invoice | done — same as F13 |
| VERIFACTU-F15 | Send the record to the AEAT and collect its answer | done — the worker sends it through the SaaS gateway; without `VERIFACTU_GATEWAY_URL` the records wait in the queue |
| VERIFACTU-F16 | Look up the records and their status | done |
| VERIFACTU-F17 | See the detail of a record and why it waits | done |
| VERIFACTU-F18 | Verify the QR at the AEAT's site | partial — a record has yet to be checked in the installed app, which opens the AEAT's site since version 1.1.34 |
| VERIFACTU-F19 | Give the QR and the fiscal status to the ticket and the invoice | done (Sales and Printing ask for it by name) |
| VERIFACTU-F20 | Send later what could not go out (automatic contingency) | done — the worker runs it every minute, in each business |
| VERIFACTU-F21 | Process the queue by hand | done |
| VERIFACTU-F22 | Retry a queue entry | done |
| VERIFACTU-F24 | Act on a record rejected by the AEAT | done |
| VERIFACTU-F25 | Resend a given record | done — through the SaaS gateway |
| VERIFACTU-F26 | Verify the fingerprint chain | done |
| VERIFACTU-F27 | Look up what the AEAT has | done — through the SaaS gateway (`/internal/verifactu/query`) |
| VERIFACTU-F28 | Recover the chain from the AEAT after restoring a backup | done — through the SaaS gateway (`/internal/verifactu/query`) |
| VERIFACTU-F29 | Continue the chain of another application (migration) | done |
| VERIFACTU-F30 | Cancel a record sent by error | done |
| VERIFACTU-F31 | Watch the submissions from the screens | done — also from the four Home panels |
| VERIFACTU-F32 | Prevent turning the app off once on | done — VeriFactu's `can_disable` and 409 `base.app_vetoed` from `base.app.disable` (hub#267); in Spain it never goes off |
| VERIFACTU-F34 | Renew the own certificate | done — in the Hub (uploading the renewed one replaces the previous one) |
| VERIFACTU-F35 | Ask the AEAT whether it already has a queue record | done — in the record's detail, in the Hub's admin and through the API |

### VERIFACTU-F01 Activate VeriFactu
Status: done — turning the app on in the Hub is activating it, in that business; outside Spain, Apps does not offer it and the hub refuses it (`can_enable`, hub#694), one already on records and sends nothing and the Home does not ask it to "Set up VeriFactu" (hub#682); no template turns it on, in Spain either: the owner turns it on (hub#998)
Actor: administrator
Screen: Hub: Apps
Steps:
1. In the Hub's apps, turn **VeriFactu** on (Invoicing turns on with it).
2. From that moment every invoice Invoicing issues is recorded (VERIFACTU-F13) in the test
   environment.
3. Only in a business in Spain. In one from another country (that of its erplora.com account), Apps does not offer
   it: it shows "Not available" with "VeriFactu is only for businesses in Spain." and no "Turn on", and the hub answers
   the same if asked through the assistant or the API. A data file that brings it (the one another business exported)
   does not promise to turn it on, loads everything else and ends complete, with no "Retry", saying why VeriFactu
   stays out.
4. If it was already on in a business from another country, it does nothing and can be turned off: invoices go out without a record or QR, **VeriFactu → Settings** and **VeriFactu → Configuration**
   say on top "VeriFactu is only for businesses in Spain." without offering anything that leads to the AEAT, and
   whatever asks to record or send something answers the same.
   "Finish setting up your business", on the Home, does not ask it to "Set up VeriFactu" nor does the bell's notice
   "You cannot issue invoices yet" show because of it; a business without a country (a demo) counts as Spain and does see it
   (hub#682).
5. No template turns it on, in Spain either: neither the Home's "Start with a business like yours" nor "Use template"
   in **Settings → Data and backups** names it in "Review what it brings" or turns it on. They load everything else of
   the sector, Invoicing included, and VeriFactu stays "Off" in Apps, with "Turn on", and "Finish setting up your
   business" asks to "Turn on VeriFactu" until the owner turns it on themselves: it binds them to the AEAT until the end
   of the calendar year and no longer goes off (VERIFACTU-F32).
In: nothing but the order.
Out: the app active; no switch of its own.
If it fails: the Hub's apps page says so.
Involved: INVOICE-F01, BASE-F18, BASE-F31, BASE-F38

### VERIFACTU-F02 Upload the business's own certificate
Status: done — in the Hub; encrypted in the hub's DB with `FISCAL_CERTIFICATE_KEY`
Actor: owner and administrator (configure)
Screen: Configuration
Steps:
1. In **Configuration**, tab "My certificate", tap "Choose the .p12 / .pfx file" and pick the business's
   certificate (1 MB at most).
2. Type its password in "Certificate password" and tap "Upload the certificate".
3. The Hub opens it with the password, reads holder, tax ID, kind and expiry and keeps it encrypted, together with
   the password, in the Hub's database. It does not look at which authority issued it: whether it is valid is for
   the AEAT's test environment to say (step 4). For example, "Certificate uploaded: Bar Sol SL (B12345678)." shows
   and the tab turns "Loaded". Uploading another one replaces the previous one.
4. While the business is in testing, from that moment its records go out with it, also those the
   gateway had refused, and with them the AEAT's test environment tries it. In the tab, the row "AEAT test
   environment" says "Not tested yet" and below "It is tried with the next record that goes out in testing: once the
   AEAT's test environment accepts it, you can go live.". When the AEAT's test environment answers a submission made
   with it with its verdict on the records (even if it rejects one for its content), it turns "Accepted" and it can
   go live with it. If it refuses it because of the certificate, it turns "Refused" and below it says why: the
   AEAT's site answers with its error page ("Se ha producido un error al verificar el certificado
   presentado": no authority it recognises issued it, it is not valid for this service or it has expired), or it
   answers the fault 4112 ("El titular del certificado debe ser Obligado Emisión, Colaborador Social, Apoderado o
   Sucesor"). An AEAT that is down or does not answer, a fault of the submission's content or a passing fault such as
   103 "NIF no identificado" (the AEAT's test environment gave it to good certificates and identified them a while
   later) does not change it; if the AEAT's test environment accepts it
   later, it turns "Accepted". Uploading another one leaves it "Not tested yet" again. In production the row does
   not show: production never tries a certificate.
5. In a business outside Spain it is not offered: on top it says "VeriFactu is only for businesses in Spain." and
   the tab only shows the certificate's status, without uploading or removing it.
In: the `.p12`/`.pfx` in base64 and its password (`verifactu.certificate.upload`).
Out: the certificate kept (`OwnCertificate`), an event "Own certificate of … uploaded" and the notice
`verifactu.config.changed`; when the AEAT's test environment accepts or refuses it, the event "The AEAT's test environment accepted the own certificate of …: the business can go live
with it." or "The AEAT's test environment refused the own certificate of … (reason): upload another one." and the
same notice. The file and the password are never shown again: neither in the API, nor in the
admin, nor in the snapshot, nor in the server's logs.
If it fails: the certificate is not kept and the screen says why:
- if this server cannot keep certificates yet, "This server cannot keep certificates yet: ERPlora has to set its
  storage key.";
- with no issuer, it asks to set it up first in Invoicing, tab Issuer;
- with a wrong password or a file that is not a .p12, "The file is not a .p12/.pfx certificate that this password
  opens."; self-signed, "No authority issued this certificate (it is self-signed), so the AEAT will not accept it.
  Use your business's electronic certificate issued by a recognised authority, for example the FNMT."; without
  client-authentication use, "The certificate does not allow client authentication, so it cannot
  connect to the AEAT."; expired, for example "The certificate expired on 2025-12-31: upload a valid one.";
- with a holder other than Invoicing's issuer, for example "The certificate belongs to B87654321, not to this
  business's issuer B12345678.": through the own route it would file on behalf of someone else.
Involved: VERIFACTU-F04, VERIFACTU-F08, VERIFACTU-F34

### VERIFACTU-F03 Remove the own certificate
Status: done — in the Hub
Actor: owner and administrator (configure)
Screen: Configuration
Steps:
1. In "My certificate", with one loaded, tap "Remove"; a card asks "Remove the certificate?" and says what will
   happen (the Configuration screen).
2. On confirming, the certificate is deleted from the Hub's database, "Certificate removed." shows and the tab
   turns "Not loaded".
3. In testing, the records not sent yet go out with ERPlora's seal instead, also those the gateway had refused. In
   production with the certificate's route fixed, they can no longer go out until another one is uploaded: they
   wait in the queue with the reason "your own certificate is not loaded or has expired" and new sales are refused;
   they never go back to the seal. In production with ERPlora's route fixed,
   nothing changes.
In: nothing (`verifactu.certificate.remove`).
Out: the certificate deleted, an event "Own certificate of … removed" and the notice `verifactu.config.changed`.
If it fails: without the permission to set up VeriFactu, "Remove" does not show, and asking for it through another
door is refused.
Involved: VERIFACTU-F04, VERIFACTU-F08

### VERIFACTU-F04 Know who files: my certificate or ERPlora
Status: done — the route is not chosen: the certificate decides it and it is fixed on going live
Actor: administrator
Screen: Settings
Steps:
1. The certificate decides the route. With an own certificate loaded and in force, the records go out
   with it; without it, in testing ERPlora files them with its seal,
   also in a demo business. While the business is in testing, uploading, removing or letting the certificate expire
   changes the route of what has not gone out yet.
2. In **Settings**, "Sending" says it in a sentence with its icon, along with what is missing.
3. On going live, the route of that moment is fixed: with a valid certificate, the certificate, even
   if the authorisation is approved too; without it, ERPlora's. From then on, uploading, removing or letting the
   certificate expire does not change it. With the certificate's route fixed and no valid certificate, the records
   wait and new sales are refused; they never go back to the seal. With ERPlora's route fixed, it keeps sending and
   cancelling with the seal while its authorisation stays approved.
4. ERPlora can stop filing on behalf of businesses on a server (to begin with, it does): then going live is only
   possible with the own certificate. Testing without a certificate, demos included, keeps
   going out with the seal, and whoever is already live through it keeps sending and cancelling through it. ERPlora's
   own business is not affected: it always files with the seal.
5. In a business outside Spain, on top it says "VeriFactu is only for businesses in Spain.".
In: the uploaded certificate (VERIFACTU-F02, F03), the environment and, from the account, the authorisation's status.
Out: the route each record goes out by, in `verifactu.config.get` (`route`); on going live, kept.
If it fails: there is nothing to choose and nothing to refuse. What is missing to send is said by "Records are
waiting:", and what is missing to go live, by the list "It cannot go live yet:", on the same screen.
Involved: VERIFACTU-F02, VERIFACTU-F03, VERIFACTU-F05, VERIFACTU-F08

### VERIFACTU-F05 Sign and upload the representation authorisation so ERPlora files
Status: done — uploaded in the Hub, reviewed by staff in the SaaS and the status comes back in the snapshot
Actor: administrator ("configure" permission)
Screen: Configuration
Steps:
1. In **Configuration**, tab "ERPlora files for you", the status says "Not signed".
2. "Download the form" downloads the official form (Annex I of Agreement 17, which ERPlora provides) with the business's
   details already in: Invoicing's issuer's legal name, tax ID and address (the municipality and the street, with
   the number as it appears in the address); with no issuer, it comes blank. Whatever is missing is filled in and it
   is signed away from the screen: by hand (and scanned to PDF, with the stamp if it is a company) or with
   AutoFirma. Under the button, "Model downloaded. Sign it and upload it below." appears; inside the ERPlora app the
   form is saved in Downloads and the folder where it was left appears too.
3. A company writes its legal representative (name and NIF/NIE); a sole trader signs themselves.
4. The identity document (DNI or NIE) is chosen and the PDFs attached: the signed form, the copy of the document,
   with a NIE a signature sample and, with a company, the proof of representation.
5. "Send for review": the Hub checks the documents and forwards them as they are to ERPlora; it stays "Under
   review".
6. A person at ERPlora reviews it; your ERPlora account sends the Hub the new status: "Approved", "Returned"
   (with the reason) or "Revoked".
7. In a business outside Spain it is not offered: on top it says "VeriFactu is only for businesses in Spain." and
   the tab shows neither the authorisation nor the procedure.
8. To whoever asks the assistant for ERPlora to file on the business's behalf, the assistant explains these steps.
   Where ERPlora does not file on behalf of businesses, it does not offer them: it says "ERPlora does not file on
   behalf of businesses for now: file with your own certificate." and explains how to upload it in the "My certificate" tab.
In: Invoicing's issuer (the taxpayer), the representative, the document type and the PDFs in base64
(`verifactu.representation.submit`); the form, from `verifactu.representation.model`, which passes the issuer's
details to the SaaS.
Out: `POST /internal/hubs/{id}/representation` to the SaaS; "Under review" (an approved one stays in force and
filing until the new one is approved), its trace in "What you sent" and in the audit log (number, date, document
type and which documents; never their content) and the notice `verifactu.config.changed`. The Hub keeps no
document. Approved, it opens the ERPlora route in production (VERIFACTU-F08).
If it fails: before sending anything, the screen says what is missing: the form ("Attach the signed form."), that it
be a PDF ("The signed form has to be a PDF — scan it or sign it with AutoFirma."), the copy of the document, with a
NIE the signature sample, with a company the representative or the proof, or a file over 5 MB ("Each file has to be
5 MB at most."). If ERPlora refuses it on receiving it, its reason shows. With no issuer in Invoicing, it asks to set
it up first; if ERPlora has not linked the business yet, "ERPlora has not linked this business yet."; if ERPlora does
not answer, "ERPlora could not handle this right now. Try again in a few minutes.". If ERPlora stops filing on behalf
of businesses, the tab "ERPlora files for you" no longer shows, and asking for it through another door answers
"ERPlora does not file on behalf of businesses for now: file with your own certificate.".
When downloading the form, an issuer detail the form cannot write (a letter outside its own or a text that is too
long) comes blank to write it by hand, with the rest already in: it never leaves you without a form. Inside the app,
if it cannot save it, it says so with its reason and "Model downloaded" does not appear.
Involved: VERIFACTU-F08, BASE-F112 (inside the app)

### VERIFACTU-F06 Send the authorisation again
Status: done — in the Hub, like VERIFACTU-F05
Actor: administrator ("configure" permission)
Screen: Configuration
Steps:
1. Returned or revoked, the procedure is already open: what the reason says is corrected and it is sent again.
2. Under review or approved, "Send again" opens it and warns: the new submission replaces the one under review;
   with an approved one, filing goes on with it while the new one is reviewed. "Cancel" closes it.
In: like VERIFACTU-F05.
Out: like VERIFACTU-F05; the submission carries the next number.
If it fails: the same as when sending it the first time.
Involved: VERIFACTU-F05

### VERIFACTU-F08 Go live
Status: done — production = `prod` deployment ∧ `VERIFACTU_PRODUCTION_ENABLED` ∧ (an own certificate in force and
accepted by the AEAT's test environment | ERPlora route open on the server with an approved authorisation) ∧ active account (`status` of the snapshot), in every
plan (Free included, with no paid option); the server keeps it closed until ERPlora opens it (under Ioan's supervision). In `pre` it never opens: everything goes to testing. A
demo hub never goes live (`verifactu.go_live_forbidden`).
Actor: administrator
Screen: Settings
Steps:
1. In **Settings**, "AEAT environment" shows "Testing (AEAT test)" and "Your invoices go to the AEAT's
   test environment. When everything is ready, go live.". If something is missing, below shows "It cannot go live
   yet:" with the list (demo business, authorisation not approved, ERPlora route closed on the server, own certificate
   missing or expired, own certificate the AEAT's test environment has not accepted yet or refused, account with a
   pending payment or suspended) and "Go live" stays disabled. No plan is missing from it: VeriFactu live is for
   every plan.
2. Tap "Go live" and confirm in "Send your invoices to the AEAT for real?" ("From now on every record goes to the
   real AEAT. As soon as the first one is sealed you can no longer go back to testing.").
3. "Your business is live: records now go to the real AEAT." shows and the pill turns
   "Production".
In: Invoicing's issuer; the own certificate, its expiry and whether the AEAT's test environment accepted it
(VERIFACTU-F02); from the account's snapshot (`verifactu.config.sync`),
the authorisation and the business's status (the snapshot of an older SaaS still brings `live_paid`: it is accepted
and not read).
Out: the environment in production and the route of that moment fixed (VERIFACTU-F04: with a valid certificate, the
certificate; without it, ERPlora's), announcing `verifactu.config.changed`: new records are born in the production
chain, with the real site's QR; those born in testing keep going to testing.
If it fails: while something is missing, "Go live" stays disabled, the environment stays in testing and the list "It
cannot go live yet:" says what is missing:
- that ERPlora has not opened real filing with the AEAT on this server yet, or that its sending gateway is missing;
- that it is a demo business, which always files in the AEAT's test environment;
- with your certificate, that this server cannot open it (it has to be uploaded again in "My certificate"), that the
  AEAT's test environment has not accepted it yet (it is tried with the next record that goes out in testing: make a
  sale or an invoice and go live once it is accepted) or that it refused it (another one has to be uploaded);
- with no valid certificate, that ERPlora has not approved your signed authorisation yet or, if ERPlora does not file
  on behalf of businesses, that your own certificate is missing;
- that your ERPlora account has a pending payment or is suspended: the payment has to be settled in your account.

With no issuer in Invoicing, it asks to set it up first. Already live, it does nothing. In a business outside Spain,
Settings says on top "VeriFactu is only for businesses in Spain." as the only reason and "Go live" is disabled.
If the fixed route is lost in production (with ERPlora's, your authorisation is revoked; with the certificate's, it
expires or is removed), the route does not change and it does not go back to testing: nothing new is sealed. The sale
or the invoice is refused with "Nothing was issued: this business files for real with the AEAT and cannot reach it
now:" and the reason, and Settings says it under "New sales and invoices are refused until this is fixed:". What was
already sealed waits, because it could not be filed.
If ERPlora stops filing on behalf of businesses, whoever is already live through that route keeps sealing, sending and
cancelling with ERPlora's seal, because the AEAT only accepts a cancellation filed with the same seal; uploading a
certificate afterwards does not change it either. Whoever is already live with their certificate and uploads another
one keeps sending with it without it being tried: production never tries a certificate.
Involved: VERIFACTU-F04, VERIFACTU-F05, VERIFACTU-F09

### VERIFACTU-F09 Go back to testing
Status: done
Actor: administrator
Screen: Settings
Steps:
1. In production and with no record sealed in production, "No record has been sealed in production yet, so you can
   still go back to testing." and "Back to testing" show.
2. Confirm in "Go back to the test environment?".
3. "Your business is back in the test environment." shows.
In: whether there are production records.
Out: the environment in testing (it announces `verifactu.config.changed`).
If it fails: with a production record already sealed (a sale is enough), "It cannot go back to testing: this
business already has records in production." and the button does not show.
Involved: VERIFACTU-F08

### VERIFACTU-F10 Test the connection with the AEAT
Status: done — with the SaaS gateway's probe (`/internal/verifactu/probe`)
Actor: manager, administrator
Screen: Settings
Steps:
1. In **Settings**, "Live test", tap "Test the connection" (the buttons wait while it tests).
2. The Hub checks, without filing anything with the AEAT, everything needed to send: the issuer, the producer's
   data, the route and its status and, if the gateway is configured, asks it whether it can file now.
3. Below the result shows, line by line, and "This business can send." or "It cannot send yet:" with the
   reasons.
4. In a business outside Spain, on top it says "VeriFactu is only for businesses in Spain." and "Test the
   connection" is disabled.
5. Asked of the assistant ("check whether it already connects to the tax office, without sending anything"), its card
   names it as the button does: "Test the connection in VeriFactu.", and after "Run it" the receipt says "Done: Test the
   connection in VeriFactu".
In: the Hub's configuration; the answer of the gateway's probe.
Out: the result as a "Connection test" event (it announces `verifactu.diagnostic.run`), without creating any
record or touching the chain.
If it fails: what is missing, said in the result. It never files a sample record: a filed record cannot be
undone.
Involved: VERIFACTU-F15, BASE-F97

### VERIFACTU-F11 Create a test invoice
Status: done
Actor: administrator
Screen: Settings
Steps:
1. With the business in testing, in **Settings**, "Live test", tap "Create test invoice". In production the button
   does not show.
2. VeriFactu asks Invoicing for a ticket (F2) of one line "Prueba VeriFactu" of €1.00 plus 21% VAT in the TICKET
   series, like an invoice made by hand.
3. For example, "Test invoice TICKET-2026-000001 created: its record is in Records." shows.
4. In a business outside Spain, on top it says "VeriFactu is only for businesses in Spain." and "Create test
   invoice" is disabled.
5. Asked of the assistant, its card says "Create test invoice in VeriFactu. Check each datum before going on." and,
   below, what it will issue: "Series: TICKET", "Price: €1.00" and "VAT: 21%"; it is issued only after typing
   "CONFIRM".
In: nothing to type.
Out: a real Invoicing invoice in testing and its record, which goes out like any other.
If it fails: Invoicing's refusal (no issuer, no permission to issue).
Involved: INVOICE-F03, BASE-F97

### VERIFACTU-F12 Look up the responsible declaration
Status: done
Actor: employee, manager, administrator
Screen: Settings
Steps:
1. In **Settings**, card "Responsible declaration", "Read the signed declaration" opens the one
   published on erplora.com (in the installed app, in the device's browser); next to it, "Declaration version".
2. "Identifying data of this system" shows the producer's data, the installed version and the installation number
   (this business's identifier at ERPlora).
In: the declaration (fixed in the Hub's version).
Out: nothing; it is a lookup.
If it fails: the failure's message; in the installed app, if it cannot open it, "Could not open that page. Try again.".
Involved: none

### VERIFACTU-F13 Record an issued invoice
Status: done — Invoicing asks for it by name inside its issuing; the worker's outbox relay stays as a backup
Actor: whoever issues (their own session); in the reaction to the notice, the system
Screen: none
Steps:
1. Invoicing issues an invoice or a ticket (when charging, by hand or the test invoice).
2. In the **same transaction** that issues it, with the session of whoever issues, Invoicing asks VeriFactu for its
   record (the record carries that user in "created by"). Only if the database fails for a moment (a lock, a
   connection) does the document stay "pending" and the reaction to the notice `invoice.invoice.issued` seals it
   afterwards, as the system. If the business is not in Spain, VeriFactu records nothing: the invoice is issued all
   the same, without a record or QR, as with the app off, and it is never undone because of that.
3. VeriFactu reads the invoice (number, dates, issuer, customer, amounts, breakdown by tax key and the invoice it
   rectifies or replaces) and checks it: the breakdown adds up to the base and the tax, each key's tax matches its
   rate, there are no more than 12 keys (those the AEAT accepts; it is never cut), an ordinary invoice does not add
   up to a negative, a full invoice identifies the customer.
4. It seals the **registration** record: it locks its chain's row (issuer's tax ID and environment), gives it the
   next number, works out its fingerprint with the previous record's and sets its QR on the environment's site
   (testing or real). It **always** validates its XML against the official schema; with the producer's data already
   received it keeps it, and without them it validates it with a provisional `SistemaInformatico` that is not kept
   (its XML is built before the first submission).
5. The record shows in **Records** as "Pending" and goes out with the next pass (VERIFACTU-F15).
In: the issued invoice, from Invoicing (by its id).
Out: the sealed record (it announces `verifactu.record.created`).
If it fails: if it does not add up or the XML does not pass the schema, nothing is written nor a number spent, and
**the whole issuing is undone** (Invoicing gives the number back to its series): retrying would fail the same. An
invoice that already has a record answers the same one: never two records or two numbers, not even with two
deliveries at once. An invoice that does not exist does nothing.
Involved: INVOICE-F01, INVOICE-F02, INVOICE-F03, INVOICE-F05

### VERIFACTU-F14 Record a rectifying invoice
Status: done — same as F13
Actor: system
Screen: none
Steps:
1. Invoicing issues a rectifying invoice (R1–R5, by differences, negative amounts): a refund, the voiding of a sale
   (R5 of the ticket) or a manual correction.
2. VeriFactu records it as one more **registration**, with its R type, `TipoRectificativa = I` and the invoice it
   rectifies (tax ID, number and date). Voiding a sale is a rectifying invoice: it is **not** a cancellation record
   (that is VERIFACTU-F30).
In: the issued rectifying invoice, from Invoicing.
Out: the registration record of the rectifying invoice (it announces `verifactu.record.created`).
If it fails: like VERIFACTU-F13.
Involved: INVOICE-F07, INVOICE-F08, INVOICE-F09, INVOICE-F10

### VERIFACTU-F15 Send the record to the AEAT and collect its answer
Status: done — the worker sends it through the SaaS gateway; without `VERIFACTU_GATEWAY_URL` the records wait in the queue
Actor: system
Screen: none
Steps:
1. The sending pass (every minute, VERIFACTU-F20, or "Process queue") takes each chain whose AEAT wait
   (`TiempoEsperaEnvio`) is over and whose first pending record is due, and gathers its pending records in chain
   order, up to 1,000 in one submission.
2. It builds the envelope (the taxpayer, who files if it is ERPlora and, if any already tried to go out before,
   `Incidencia = S`), validates it against the schema and sends it to ERPlora's gateway, which files it with the
   AEAT of the records' environment with ERPlora's seal or with your certificate and returns its answer.
3. With the answer, each record ends "Accepted" (with its CSV), "Accepted with errors" (it is at the AEAT; the code
   is kept), or "Rejected" (with the AEAT's code and message; VERIFACTU-F24). A "duplicate" (3000) of a record the
   AEAT had already accepted counts as accepted. The wait the AEAT asks for is kept in the chain and the next
   submission does not go out before it.
4. If there is no answer (the gateway or the AEAT down): the record stays "Pending" with "Attempts" +1 and the next
   attempt at 5, 10, 20, 40 and 60 minutes, without limit. If the request went out but nothing came back, it stays
   "Sent" and is sent again with an incident (the AEAT will say "duplicate" if it already had it).
In: the pending records; the route; the gateway's answer.
Out: the status and the answer in each record (it announces `verifactu.record.transmitted` and, as the case may be,
`verifactu.record.rejected` or `verifactu.record.accepted_with_errors`, without amounts).
If it fails: with no gateway configured, no producer's data or no route ready, nothing is sent and each record
says why it waits (VERIFACTU-F17). A record is never taken as accepted without the AEAT's answer. A business
outside Spain never sends anything: what was sealed before is kept as it is, without going out, and says why.
A business's record is always presented as that business, never as ERPlora's hub (hub#454): the worker goes
through each business in its database and on its scope, and each pass presents what its database holds as its
business, whatever tax ID the record bears. ERPlora's hub's database holds ERPlora's records only (hub#602, hub#1130).
Involved: VERIFACTU-F20, FLOW-F04 (the card of the Automations gallery that creates an urgent task when the AEAT
rejects a record)

### VERIFACTU-F16 Look up the records and their status
Status: done
Actor: employee, manager, administrator
Screen: Records
Steps:
1. Open **Records**.
2. Search by invoice number, sequence, issuer's name or tax ID, or filter by status, type, invoice type,
   environment, date and total.
3. Each row shows its status with a colour: green "Accepted", amber "Pending" / "Sent" / "Accepted with
   errors", red "Rejected"; and its environment, so as not to mix testing up with production.
In: the records.
Out: nothing; it is a lookup.
If it fails: the message with "Retry". The total is read as in any amount field of the Hub and as in the other
lists ("1.000,50", "1,000.50", "2 500" and "12,50 €" filter); one it cannot read says so under its
field in the words of the amount field ("This is not an amount. Type a figure, for example 12.50.", "This amount
cannot be negative." or, with "1.000" in euros, "This amount can be read in two ways…"), and an end date before
the start date, "The end date cannot be before the start date."; neither of the two filters.
Involved: INVOICE-F16

### VERIFACTU-F17 See the detail of a record and why it waits
Status: done
Actor: employee, manager, administrator
Screen: Record detail
Steps:
1. In **Records**, tap a row.
2. Its detail opens, for example "Record TICKET-2026-000001", with the invoice, the chain, the QR, the AEAT's
   answer and the XML.
3. If it is not at the AEAT, "Not at the AEAT yet" says why ("ERPlora's sending gateway is not configured on this
   server", "your own certificate is not loaded or has expired", that the AEAT asked to wait until a given time,
   that the gateway or the AEAT could not be reached) and a single when: if everything it waits for clears by
   itself (the AEAT asked to wait, no connection, no answer, an AEAT fault), "It goes out by itself with the next
   pass, in order, and declared as late if it failed before. You do not have to do anything."; if it waits for
   something to be resolved (a refusal of the gateway, which is not sent again by itself; the authorisation; the
   route; the server), "It goes out by itself, in order and declared as late, as soon as that is resolved.".
   Below, the "Next attempt".
4. In a business outside Spain it only says "this business is not in Spain: VeriFactu is only for businesses in
   Spain, so nothing is sent to the AEAT", with no next attempt nor buttons to send, correct or cancel:
   it never goes out.
In: the record.
Out: nothing; it is a lookup.
If it fails: "Record not found" or the failure's message.
Involved: VERIFACTU-F15

### VERIFACTU-F18 Verify the QR at the AEAT's site
Status: partial — a record has yet to be checked in the installed app: since version 1.1.34 the app opens the AEAT's site in
the device's browser, but it has not been tried on a device yet
Actor: employee, manager, administrator, customer
Screen: Records
Steps:
1. In **Records**, "Verify at the AEAT" on the row (or in the detail) opens in another tab (in the installed app, in the
   device's browser) the AEAT's verification page with the issuer's tax ID, the number, the date and the amount.
2. A record born in testing leads to the test site; one from production, to the real site.
3. The customer does the same by scanning the QR of their ticket or their invoice.
In: the QR's link set when sealing.
Out: nothing in the Hub.
If it fails: a record that has not gone out yet shows at the AEAT as not found; a rejected one, never. In the installed
app, if it cannot open the page, "Could not open that page. Try again.".
Involved: VERIFACTU-F19

### VERIFACTU-F19 Give the QR and the fiscal status to the ticket and the invoice
Status: done (Sales and Printing ask for it by name)
Actor: system
Screen: none
Steps:
1. When Sales, Invoicing or Printing paint a document, they ask VeriFactu for the record of its invoice.
2. VeriFactu returns the most recent one: its link and its QR image, its CSV, its status, its type and its
   fingerprint.
In: the invoice's id.
Out: the record (`verifactu.record.by_invoice`); with no record, nothing (the document goes out without a QR).
If it fails: without VeriFactu active, without the view permission or in a business outside Spain, the document
goes out without a VeriFactu QR or receipt.
Involved: INVOICE-F17, INVOICE-F18

### VERIFACTU-F20 Send later what could not go out (automatic contingency)
Status: done — the worker runs it every minute, in each business
Actor: system
Screen: Contingency
Steps:
1. While selling, nothing stops because of this: if the gateway, the AEAT or the network are down, charging goes on
   and the record waits.
2. Every minute the system does the sending pass on every chain that is due, each one in its environment, in order
   and respecting the wait the AEAT asked for; if passes were missed (server stopped), on coming back a single one
   is done.
3. Whatever fails again waits longer (5, 10, 20, 40 and 60 minutes), with no limit of attempts.
4. The pass's event is left in **Events**, for example "Queue processed: 3 sent, 3 accepted, 0 rejected, 0
   waiting.".
In: the pending records.
Out: the submissions and their answers (it announces `verifactu.contingency.processed`).
If it fails: whatever does not go out stays in the queue with its reason; in a business outside Spain it never goes
out. The pass presents each record as the business it belongs to, never as ERPlora's.
Involved: VERIFACTU-F15

### VERIFACTU-F21 Process the queue by hand
Status: done
Actor: manager, administrator
Screen: Contingency
Steps:
1. In **Contingency**, tap "Process queue" ("Processing…").
2. The same pass as the automatic one is done at that moment.
3. Under the table the result shows; the table updates by itself.
In: the queue.
Out: like VERIFACTU-F20.
If it fails: with no gateway, the notice "ERPlora's sending gateway is not configured on this server"; the records
stay in the queue and go out as soon as it is.
Involved: VERIFACTU-F20

### VERIFACTU-F22 Retry a queue entry
Status: done
Actor: manager, administrator
Screen: Contingency
Steps:
1. In **Contingency**, tap "Retry" on the row.
2. The record (and the earlier ones of its chain, which go out before it) are set to go out with the next pass;
   the attempts are kept.
In: the chosen record.
Out: the rescheduled record (it announces `verifactu.contingency.retried`).
If it fails: an accepted or rejected record is not in the queue: "This record is not in the queue: it is already in the AEAT, or the
AEAT rejected it.".
Involved: VERIFACTU-F21

### VERIFACTU-F24 Act on a record rejected by the AEAT
Status: done
Actor: administrator
Screen: Records, Record detail
Steps:
1. The record shows in red "Rejected" in **Records**, with "Pending correction" beside it; in **Events** "Submission
   failed" is left with the reason. The "Correction" filter, on "Pending correction", leaves only the ones still to
   do.
2. In its detail, "The AEAT rejected it" with the AEAT's literal code and message and what to do: if the error is
   in the invoice's data (a customer's tax ID the AEAT does not know, an amount), it is corrected **in Invoicing**
   with a rectifying invoice; if not (a chain error after restoring a backup, a fault of ours), "Correct".
3. "Correct" (with confirmation) seals a **new** record of the same invoice, read again, marked as a correction,
   which enters the queue. The rejected one stays as it is. The new record tells the AEAT whether it already had
   that invoice or whether it was rejected from the first submission.
4. An "Accepted with errors" can also be corrected.
5. Once corrected, in **Records** the earlier one says "Corrected", which opens the record that corrects it, and its
   detail, "Already corrected with a new record" with "Open the record that corrects it". If the AEAT rejects the
   correction too, that one shows "Pending correction" and is corrected in turn; the earlier one stays "Corrected".
In: the rejected or accepted-with-errors record.
Out: the correction record (it announces `verifactu.record.created`).
If it fails: only a registration record rejected or accepted with errors is corrected, and only the last one of its
invoice: "This record cannot be corrected: only the last record of a registration the AEAT rejected or accepted
with errors can.".
Involved: INVOICE-F08

### VERIFACTU-F25 Resend a given record
Status: done — through the SaaS gateway
Actor: manager, administrator, assistant
Screen: Record detail
Steps:
1. In the detail of a pending record or of one sent with no answer, tap "Send now".
2. Its chain up to it goes out right away (the earlier pending ones go first, in order), if the AEAT's wait is
   over.
3. The record ends with the AEAT's answer: "Accepted", "Accepted with errors" or "Rejected".
In: the chosen record (by its id or by its invoice's number).
Out: the submission and its answer (it announces `verifactu.record.transmitted`).
If it fails: with no gateway, "It cannot be sent now: ERPlora's sending gateway is not configured on this server. It
stays in the queue and goes out as soon as it can."; already accepted or rejected, "This record is not in the queue:
it is already in the AEAT, or the AEAT rejected it."; with the AEAT's wait under
way, for example "The AEAT asked to wait: it goes out by itself at 12:05.". It never says "accepted" without an
answer.
Involved: VERIFACTU-F15

### VERIFACTU-F26 Verify the fingerprint chain
Status: done
Actor: employee, manager, administrator
Screen: Recovery
Steps:
1. In **Recovery**, with the "Issuer tax ID", tap "Validate chain" ("Working…").
2. The system recomputes the fingerprint of each record of the current environment's chain and checks that each one
   carries the previous one's.
3. "Operation completed." and the verdict show: for example, "Fingerprint chain intact: 120 records with their
   SHA-256 chaining verified (B12345678). Amounts are not re-audited." or "Fingerprint chain BROKEN at sequence 57
   (B12345678).".
In: the chain's records.
Out: the verdict as an event (it announces `verifactu.chain.validated`). It only reads: it repairs nothing and does
not re-audit the amounts.
If it fails: with no records of that tax ID, "There are no records of that issuer in this environment.".
Involved: VERIFACTU-F28

### VERIFACTU-F27 Look up what the AEAT has
Status: done — through the SaaS gateway (`/internal/verifactu/query`)
Actor: manager, administrator
Screen: Recovery
Steps:
1. In **Recovery**, tap "Query AEAT" ("Working…").
2. The system asks the AEAT, through the gateway, for that issuer's records of the current month.
3. The table "Latest records at the AEAT" fills up and "Operation completed." shows.
4. In the table, search by invoice, fingerprint or CSV ("Search invoice, fingerprint or CSV…"), sort by any column
   and filter by "Status" (Registered, Accepted with errors, Cancelled) or by "Date" from the funnel; with no
   matches, "No results"; with no query yet, "No AEAT data. Press «Query AEAT».".
In: the issuer's tax ID; the AEAT's answer.
Out: the snapshot of what the AEAT has, which replaces the previous one (it announces `verifactu.aeat.queried`). It
does not touch the chain.
If it fails: with no gateway, the message of the gateway not configured; a refusal from the AEAT, its message.
Involved: VERIFACTU-F28

### VERIFACTU-F28 Recover the chain from the AEAT after restoring a backup
Status: done — through the SaaS gateway (`/internal/verifactu/query`)
Actor: administrator
Screen: Recovery
Steps:
1. After restoring a backup of the database (the AEAT has records the backup does not), stop issuing and open
   **Recovery**.
2. Tap "Recover chain from AEAT" and confirm ("Local continuity will be rebuilt from the latest record
   available at the AEAT. Verify the issuer tax ID before continuing.").
3. The system queries the AEAT and anchors the current environment's chain on the last record (by its generation
   date) the AEAT has of that issuer in the current month. "Operation completed." shows.
In: the issuer's tax ID; the AEAT's answer.
Out: a new anchor (it announces `verifactu.chain.recovered`): the next record chains on it.
If it fails: if the AEAT has no records of that issuer this month, "The AEAT has no records of that issuer this
month: there is nothing to recover." and nothing is anchored; with pending records in the chain, "The pending
records of this chain have to go out first.".
Involved: VERIFACTU-F26

### VERIFACTU-F29 Continue the chain of another application (migration)
Status: done
Actor: administrator
Screen: Recovery
Steps:
1. In **Recovery**, block "Continue chain manually (migration)", type the "Last
   fingerprint (64 hex)" of the previous application, the "Invoice number" and the "Date" of that last record.
2. Tap "Continue from this fingerprint" and confirm ("The fingerprint given will be the predecessor of the next
   fiscal record. Use this only during a migration and with the data of the last record of the previous
   application.").
3. "Operation completed." shows; the next invoice chains on that fingerprint.
In: the fingerprint, the number and the date of the previous application's last record.
Out: a new anchor (it announces `verifactu.chain.recovered`).
If it fails: a fingerprint that does not have 64 hexadecimal characters, "The fingerprint must be 64 hexadecimal
characters"; with no number or date, which are part of the chaining, the field asks for it; with pending records
in the chain, "The pending records of this chain have to go out first.".
Involved: none

### VERIFACTU-F30 Cancel a record sent by error
Status: done
Actor: administrator, assistant
Screen: Record detail
Steps:
1. Only for an invoice that **should never have been issued** (a duplicate, a test made in production). A
   refund or a correction is not cancelled: it is a rectifying invoice in Invoicing.
2. In the detail of the registration record, tap "Cancel record", write the reason and confirm ("The AEAT will be
   told this invoice was issued by error. A refund or a correction is never this: it is a rectifying invoice in
   Invoicing. The invoice stays in Invoicing.").
3. A chained **cancellation** record is sealed, which goes out like any other, and shows in Records with
   type "Cancellation".
In: the registration record (or its invoice's number).
Out: the cancellation record (it announces `verifactu.record.created`).
If it fails: a rejected registration is not cancelled (it is not at the AEAT); an already cancelled one, neither:
"This record cannot be cancelled: only a registration that reached (or will reach) the AEAT and has no
cancellation can.". If the AEAT rejected the cancellation, it can be cancelled again: the new one tells the AEAT
that the earlier one was rejected.
Involved: INVOICE-F07

### VERIFACTU-F31 Watch the submissions from the screens
Status: done — also from the four Home panels
Actor: employee, manager, administrator
Screen: Records, Contingency, Events, Home
Steps:
1. **Records** and **Contingency** say what is still to arrive; **Events**, what happened. The three update by
   themselves.
2. On the **Home**, the panel "VeriFactu pending" (on by default) counts what is not at the AEAT yet (pending, sent
   with no answer or rejected); from "Customize panel" you add "Contingency queue" (what waits in the queue, with "In
   contingency queue" under the figure, in orange if it waits and in red if an attempt has already failed),
   "Records by status" and "Recent AEAT events" (the last eight, with their time, their type and their sentence).
   All of them update by themselves and whoever can look up the records sees them.
3. The summaries (pending, by status, queue and latest events) can be asked of the assistant or through the API.
In: the records and the events.
Out: nothing; it is a lookup.
If it fails: the message with "Retry".
Involved: none

### VERIFACTU-F32 Prevent turning the app off once on
Status: done — the platform asks when turning off (`base.app.disable`, hub#256) and VeriFactu answers with its
`can_disable` (hub#267); in Spain, once on, it never goes off, and Apps does not offer "Turn off" (hub#618)
Actor: system
Screen: Hub: Apps
Steps:
1. When turning VeriFactu off in a business in Spain, the platform asks it and VeriFactu always refuses: once on,
   the business's invoices have to keep reaching the AEAT (the law requires staying with VERI*FACTU at least until
   the natural year ends, and ERPlora has no other way of recording them). In **Apps** its row offers no "Turn off"
   and says that reason (BASE-F25).
2. Whatever the queue holds makes no difference: with records to send or with everything already answered by the
   AEAT, the answer is the same. VeriFactu stays on and its records stay as they were. The apps it needs cannot be
   turned off either: Invoicing and, through it, Taxes, Sales & POS and Customers; their rows do not offer it either
   and say why (hub#619).
3. A business without a country (a demo) is in Spain: it does not go off either.
4. While its status says "Turning on…" or "Could not turn on" it has not been on yet nor sealed anything: it can be
   turned off.
5. In a business outside Spain it never refuses: its records are not going to be sent, so turning it off stops
   nothing; they are kept as they are.
In: the request to turn it off.
Out: nothing in Spain with the app on; otherwise, the app off.
If it fails: "VeriFactu can't be turned off once it's on: the law requires your invoices to keep reaching the
AEAT.".
Involved: BASE-F21, BASE-F23, BASE-F25

### VERIFACTU-F34 Renew the own certificate
Status: done — in the Hub (uploading the renewed one replaces the previous one)
Actor: owner and administrator (configure)
Screen: Configuration
Steps:
1. "My certificate" shows its date in "Expires on" and, at 30 days or less, for example "Expires in 12 days: upload
   the renewed one here.".
2. The new certificate is uploaded like the first one, with "Choose the .p12 / .pfx file", its password and "Upload
   the certificate", and replaces the previous one; the chain does not change.
In: the renewed certificate.
Out: the new one, instead of the previous one.
If it fails: expired, in testing the records go out with ERPlora's seal until the renewed one is uploaded, and in
production with the certificate's route fixed they wait with the reason; if the server changed
its storage key and cannot open the kept one, they wait with "your own certificate cannot be opened on this server:
upload it again".
Involved: VERIFACTU-F02

### VERIFACTU-F35 Ask the AEAT whether it already has a queue record
Status: done — in the record's detail, in the Hub's Django admin (support) and through the API
Actor: manager, administrator (send); ERPlora's staff from the admin
Screen: Record detail ("Ask the AEAT"); for the staff, the Django admin (Records → "Ask the AEAT (out of the queue if
it already has it)")
Steps:
1. A record was left "Sent" with no answer (or "Pending") and the AEAT may already have it: in its detail, tap
   "Ask the AEAT".
2. The AEAT is queried, through ERPlora's gateway, for the record's issuer in the month of its issue date; the
   table "Latest records at the AEAT" of Recovery is brought up to date with that query.
3. If the AEAT returns **that very record** (same issuer, number and fingerprint), it leaves the queue as "Accepted"
   or "Accepted with errors", according to what the AEAT says, without losing its attempts; an event with who did it
   is left.
4. If it does not have it (or has another record of the same invoice, e.g. the original of a correction), nothing
   changes: it stays in the queue and is sent with the next pass.
In: the record (id or its invoice's number).
Out: if the AEAT had it, the record (it announces `verifactu.record.reconciled`; the query, `verifactu.aeat.queried`).
In the detail "The AEAT already has {number}: it is out of the queue." shows or, as a warning, "The AEAT does not have
{number}: it stays in the queue and goes out with the next pass.".
If it fails: an accepted or rejected record is not in the queue (the detail does not offer the button; through the
API, "This record is not in the queue: it is already in the AEAT, or the AEAT rejected it."); with no gateway or if the AEAT does not answer, the reason, above the
buttons, and the record stays in the queue.
Involved: VERIFACTU-F22, VERIFACTU-F27

## Services: what goes in and what comes out

Everything can be asked for through the screens, the assistant (by voice or by text, with the person's own session)
and the API, with the same rules and permissions, except uploading the business's own certificate and sending the
signed authorisation: they carry files and the certificate's password, which are not said or written in a
conversation, so the assistant does not offer them and they are done in **VeriFactu → Configuration** ("My certificate"
and "ERPlora files for you") or through the API. Designed for voice: a record is named by the **number of its
invoice** (`TICKET-2026-000012`) or by its sequence; an issuer, by its tax ID.

### What it offers: queries (they read, they change nothing)

| What it gives | Who can | Flows | Service |
|---|---|---|---|
| The configuration: environment, route the records go out by (and whether ERPlora's is available), own certificate (holder, tax ID, kind, expiry; never its material), status of the authorisation, producer's data, declaration | view | F02, F04, F08, F09, F12 | `verifactu.config.get` |
| The records, with search, filters, sorting and pages (up to 100) | view | F16 | `verifactu.record.list` |
| A record, by its id or by its invoice's number, with its QR, its XML and why it waits | view | F17, F18 | `verifactu.record.get` |
| The current record of an invoice (QR, CSV, status) | view | F19 | `verifactu.record.by_invoice` |
| The queue: the records not yet at the AEAT | view | F20–F22 | `verifactu.contingency.list` |
| The audit events, with search by words and filters | view | F31 | `verifactu.event.list` |
| How many records are not at the AEAT | view | F31 | `verifactu.stats.compliance_summary` |
| The records by status | view | F31 | `verifactu.stats.records_by_status` |
| The summary of the queue | view | F31 | `verifactu.stats.contingency_summary` |
| The latest events | view | F31 | `verifactu.stats.events_recent` |
| The last snapshot of what the AEAT has | view | F27 | `verifactu.aeat_record.list` |
| The status of each chain and its last verdict | view | F26 | `verifactu.chain.status` |
| The result of the last connection test | view | F10 | `verifactu.diagnostic.last` |

All of them can be followed live.

### What it offers: actions (they change data)

| What it does | Who can | Flows | Service |
|---|---|---|---|
| Seals the registration record of an issued invoice (also the reaction to its notice) | record | F13, F14 | `verifactu.record.create` |
| Corrects a rejected or accepted-with-errors record | correct | F24 | `verifactu.record.correct` |
| Seals the cancellation record of an invoice issued by error | correct | F30 | `verifactu.record.cancel` |
| Sends a record right away (and the earlier ones of its chain) | send | F25 | `verifactu.record.transmit` |
| Does the queue's sending pass (also the every-minute task) | send | F20, F21 | `verifactu.contingency.process` |
| Sets a record to go out with the next pass | send | F22 | `verifactu.contingency.retry` |
| Asks the AEAT whether it already has a queue record; if it has it, it leaves the queue as registered | send | F35 | `verifactu.record.reconcile` |
| Verifies the fingerprint chain | view | F26 | `verifactu.chain.validate` |
| Queries the AEAT for the month's records | send | F27 | `verifactu.aeat.query` |
| Recovers the chain from the AEAT | configure | F28 | `verifactu.chain.recover_from_aeat` |
| Continues the chain from an external fingerprint | configure | F29 | `verifactu.chain.recover_manual` |
| Tests the connection without filing anything | send | F10 | `verifactu.diagnostic.run` |
| Creates the test invoice (in testing) | configure | F11 | `verifactu.test_invoice.create` |
| Goes live | configure | F08 | `verifactu.config.go_live` |
| Goes back to testing | configure | F09 | `verifactu.config.back_to_testing` |
| Uploads (or replaces) the own certificate | configure | F02, F34 | `verifactu.certificate.upload` |
| Removes the own certificate | configure | F03 | `verifactu.certificate.remove` |
| Keeps what the ERPlora account sends (status of the authorisation, status of the account) | system only | F05, F08 | `verifactu.config.sync` |
| Sets ERPlora's platform hub to its deployment's environment | system only | — | `verifactu.config.follow_deployment` |
| Sends the signed representation authorisation for review | configure | F05, F06 | `verifactu.representation.submit` |
| Gives the official blank form (PDF) | configure | F05 | `verifactu.representation.model` |

In a business outside Spain, whatever seals a record or talks to the AEAT or to the gateway (record, correct,
cancel, send right away, reconcile, query the AEAT, recover from it, test the connection, the test invoice, go live
and send the authorisation) answers as with the app off: 404 `app_inactive`,
"VeriFactu is only for businesses in Spain.". The queue's pass sends nothing and leaves each record its reason
(`outside_spain`); an invoice's record (`verifactu.record.by_invoice`) is not given.

### What it announces

| Notice | When | What it carries | Service |
|---|---|---|---|
| Record created | Every sealed record (registration, correction, cancellation) | `record_id`, `invoice_id`, `invoice_number`, `record_type`, `sequence`, `environment` | `verifactu.record.created` |
| Record sent | A submission with an answer or without one | `record_ids`, `transmission_id`, `environment` | `verifactu.record.transmitted` |
| Record rejected | The AEAT rejects it | `record_id`, `invoice_number`, `code`, `message`, `environment` (without amounts) | `verifactu.record.rejected` |
| Accepted with errors | The AEAT registers it with an error | the same | `verifactu.record.accepted_with_errors` |
| Queue processed | A pass (by hand or scheduled) | `sent`, `accepted`, `rejected`, `waiting` | `verifactu.contingency.processed` |
| Record rescheduled | "Retry" | `record_id` | `verifactu.contingency.retried` |
| Record reconciled | The AEAT already had a queue record (VERIFACTU-F35) | `record_id`, `invoice_number`, `status`, `environment` | `verifactu.record.reconciled` |
| Chain verified | "Validate chain" | `issuer_nif`, `environment`, `valid`, `total`, `first_invalid_sequence` | `verifactu.chain.validated` |
| Chain recovered | Recovering from the AEAT or by hand | `issuer_nif`, `environment`, `sequence`, `source` | `verifactu.chain.recovered` |
| AEAT query | "Query AEAT" | `issuer_nif`, `count` | `verifactu.aeat.queried` |
| Connection test | "Test the connection" | `can_send` | `verifactu.diagnostic.run` |
| Configuration changed | Route, environment or what the account sends | `fields` | `verifactu.config.changed` |

### What it reacts to

| Notice | From | What it does | Service |
|---|---|---|---|
| Document issued (`invoice.invoice.issued`) | Invoicing | Seals its registration record (F13, F14) | `verifactu.record.create` |

It runs as the system, in its own transaction, and it is idempotent: one registration record per invoice and
environment. It is the **backup**: Invoicing asks for it inside its issuing (contract below) and the notice of an
already sealed document adds nothing (`already`). In a business outside Spain it does not react (it is taken as
delivered).

### What it needs from other apps

- **Invoicing** (requirement): the issued invoice (`Invoice`), read from its row by its id; for the test invoice,
  its operation `invoice.invoice.create`.
  A record keeps its invoice with `PROTECT` (the law keeps both); what that demands of Invoicing's tests, in
  "Contract with Invoicing".

### Who uses it

| App | What for | Service |
|---|---|---|
| Invoicing | Seal the record of each document inside its issuing | `verifactu.record.create` |
| Sales, Invoicing, Printing | Put the QR and the fiscal status on the ticket and the invoice | `verifactu.record.by_invoice` |
| Platform (`base.app.disable`) | Not turn VeriFactu off once on (in Spain) | `can_disable` of `VerifactuConfig` |
| Platform (`base.app.enable`) | Not turn VeriFactu on outside Spain | `can_enable` of `VerifactuConfig` |

### Who can do what

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| View records, queue, events, chain and configuration; verify the chain | yes | yes | yes | yes | `verifactu.view_record` |
| Record an issued invoice (Invoicing asks for it with the session of whoever issues) | yes | yes | yes | yes | `verifactu.add_record` |
| Send, process and retry the queue, query the AEAT, test the connection | yes | yes | yes | no | `verifactu.transmit_record` |
| Correct and cancel records | yes | yes | no | no | `verifactu.correct_record` |
| Upload and remove the own certificate, go live and back, recover the chain, test invoice | yes | yes | no | no | `verifactu.configure` |

The roles arrive from the SaaS with a prefix (`hub_owner`, `hub_admin`, `hub_manager`, `hub_employee`). Keeping
what the account sends (`verifactu.sync_config`) belongs to no role: only to the system.
