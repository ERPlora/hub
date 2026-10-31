<!-- generated from WORKBOOK.md sha256:5c79f935129f7b5110049f5f33aa036def9d18316d58a688939830e0bfe449ae -->

## What it is for and who it is for

VeriFactu is the end of the fiscal chain: every invoice or ticket that Invoicing issues becomes here a chained
**billing record** (each record carries the fingerprint of the previous one), with its verification **QR**,
which is sent to the Spanish tax agency (AEAT). If it cannot go out at that moment, it stays in the queue and
goes out by itself later, in order. It serves the hair salon and the restaurant alike: everything is common.

It is only for businesses in **Spain** (the Canary Islands, Ceuta and Melilla included): VeriFactu binds whoever
pays tax here. A business registered on erplora.com in another country records and sends nothing to the AEAT even
with the app on: its invoices and tickets go out without a VeriFactu record or QR, as with the app off.

Who uses it:

- The **employee** looks at the records, the queue, the events and the state of the chain.
- The **manager**, besides, sends a given record, processes and retries the queue, looks up what the AEAT has
  and tests the connection.
- The **owner** and the **administrator**, besides, choose who files (their own certificate or ERPlora), go
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
  cancel one, and the choice of route (own certificate or the provider on your behalf).

## Before you start

- Turning VeriFactu on turns **Invoicing** on with it (it requires it): without invoices there is nothing to
  record. Turning VeriFactu on in the Hub **is** activating it: from that moment it records every invoice that is
  issued. There is no other switch.
- **The issuer** is Invoicing's (Invoicing → Issuer): VeriFactu takes its tax ID and its legal name from each
  invoice, it does not ask for them again.
- **The environment** starts in **testing** (the AEAT's test environment): nothing issued counts before the tax
  agency until going live (VERIFACTU-F08).
- **The sending route**: either ERPlora files on your behalf with its seal (for production it needs your signed
  authorisation, the Annex I, approved by ERPlora), or you file yourself with your own certificate. The
  authorisation (the representation authorisation) is signed and uploaded here, in "ERPlora files for you", and
  ERPlora reviews it; the certificate is uploaded here, in "My certificate". Here you choose which one to use.
- **On the Home**, while the chosen route cannot carry your records to the AEAT's production environment (ERPlora
  without the approved authorisation, or your certificate not uploaded or expired), "Finish setting up your
  business" reminds you with "Set up VeriFactu"; its "Set up" leads to VeriFactu → Configuration, and the step turns
  "Done" as soon as ERPlora approves the authorisation or you upload and choose your certificate. In testing it
  carries the "Important" pill (it does not hold back selling: in testing you sell just the same) and only whoever
  sets up VeriFactu sees it. In production (VERIFACTU-F08), if the route is lost (the authorisation is revoked, or
  the certificate expires or is removed), it carries "Needed to invoice" and the strip "You cannot invoice yet" shows
  above the other screens, because every new sale is refused; the whole team sees it, and whoever does not set up
  VeriFactu is told "An administrator has to set this up.".
- **The software producer's data** (ERPlora) go fixed in every record (its responsible declaration declares them),
  also "Serves several taxpayers", always "S" (contradiction 7, closed).

Initial setup, step by step:

1. In **Invoicing → Issuer**, fill in the legal name, the tax ID and the address.
2. Turn **VeriFactu** on in the Hub's apps.
3. Issue a test invoice (**VeriFactu → Settings → Create test invoice**, VERIFACTU-F11) and check in
   **VeriFactu → Records** that its record shows up with its QR.
4. When the route is ready, **Settings → Go live** (VERIFACTU-F08).

## Screens

Six tabs at the foot of every VeriFactu page (those of the menu, in this order): Records, Contingency, Events,
Recovery, Configuration and Settings. All of them show with the view permission; the buttons the person cannot
use do not show.

### Records
Menu **VeriFactu → Records**. Title "VeriFactu records". Table of 50 by 50 (table or cards; on the phone, cards
with the invoice number as title) with "Seq", "Invoice", "Date", "Type" (Registration / Cancellation), "F."
(F1…R5), "Issuer", "Total", "Environment" (Testing / Production) and "Status" (Pending, Sent, Accepted, Accepted
with errors, Rejected, in a coloured pill). Search box "Search invoice, issuer or tax ID…" (sequence number, invoice
number, issuer's name or tax ID). Filters of status, type, invoice type, environment, date and total (in euros),
behind the table's funnel with its counter; a total that is not an amount, or a "to" date before the "from" one, is
said under its field and does not filter. The last sealed comes on top. Per row: "View" (also by tapping the row)
and "Verify at the AEAT" (opens the QR's verification page). The list updates by itself when a record is born,
leaves or changes on any device.
Empty: "No records yet. Every invoice you issue is sealed and listed here."; with a search or filter, "No
results". Loading: "Loading…". Error: the message with "Retry".

### Record detail
It opens from a row of **Records** (`/verifactu/records/<id>`). On top, "Record {number}" with its status, its
environment and "← Back". If it is not at the AEAT (Pending or Sent), the notice "Not at the AEAT yet" with the
why and the when (VERIFACTU-F17). If it was rejected, the notice "The AEAT rejected it" with what to do
(VERIFACTU-F24). Blocks:
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
Menu **VeriFactu → Contingency**. Title "Contingency queue" and button "Process queue" ("Processing…" while it
works). Table of the records not yet at the AEAT: "Invoice", "Environment", "Attempts", "Status", "Next attempt"
and "Last error", in the order they go out (every column sorts); search box "Search invoice or error…". Per row:
"Retry" (sets it to go out with the next pass) and "View". Under the table, the result of the last manual pass.
Empty: "Queue empty: everything is in the AEAT.". Loading: "Loading…". Error: the message above the table.

### Events
Menu **VeriFactu → Events**. Title "Audit events". Table, most recent first: "When", "Severity" (Debug, Info,
Warning, Error, Critical), "Type" (Record created, Submission postponed, Submission accepted, Accepted with errors,
Submission failed, Queue processed, Record rescheduled, Chain verified, Chain broken, AEAT query, Chain recovered,
Connection test, Configuration changed) and "Message", composed in the language of whoever looks. Search box
"Search type or message…" that finds by the words that show, in Spanish or in English; filters of type, severity and
date, behind the table's funnel with its counter (a "to" date before the "from" one is said under its field and does
not filter). It updates by itself.
Empty: "No events.". Loading: "Loading…". Error: the message with "Retry".

### Recovery
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
Menu **VeriFactu → Configuration**. Title "VeriFactu configuration". Two tabs, the two routes:
- **"ERPlora files for you"** (opens by default), like the old module's `erp-verifactu-grant`: "Representation
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
  30 days or less and "The certificate has expired. Upload a valid one to send to the AEAT."). Whoever sets up
  VeriFactu sees "Choose the .p12 / .pfx file", "Certificate password", "Upload the certificate" and, with one
  loaded, "Remove" (it asks first, in a card). Note: "The certificate and its password are kept encrypted in this
  Hub and only travel to ERPlora's gateway when sending to the AEAT; they are never shown again.".
In a business outside Spain, on top shows "VeriFactu is only for businesses in Spain." as the only reason: "ERPlora
files for you" shows neither the authorisation nor the procedure, and "My certificate" only shows the certificate's
status, without uploading or removing it.

### Settings
Menu **VeriFactu → Settings**. Title "VeriFactu settings". Three blocks:
- **"Sending"**: "Use my own certificate" (switch, with its explanation by route) and "AEAT environment" with the
  pill "Testing (AEAT test)" or "Production" and, as the case may be, "Go live" (with "It cannot go live yet:" and
  what is missing, if something is missing) or "Back to testing" with its explanation and its confirmation; in
  production, "New sales and invoices are refused until this is fixed:" and the reason, if there is no route to the
  AEAT, and "Records are waiting:" and why, if they wait.
- **"Live test"**: "Test the connection" and "Create test invoice"; below, the result of the last test ("Tested
  on", "Filed through", "Environment", "ERPlora's gateway", "Issuer", "Route ready" and "This business can send." or
  "It cannot send yet:" with the reasons), or "No test run yet.".
- **"Responsible declaration"**: "Read the signed declaration", "Declaration version" and the "Identifying data of
  this system" (Producer, Producer tax ID, System name, System code, Installed version, Installation number,
  VERI\*FACTU only, Can serve several taxpayers, Serves several taxpayers: always "S").
In a business outside Spain, on top shows "VeriFactu is only for businesses in Spain." as the only reason, and "Use
my own certificate", "Go live", "Test the connection" and "Create test invoice" are disabled.
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
| VERIFACTU-F01 | Activate VeriFactu | done — turning the app on in the Hub is activating it (activation per hub arrives with phase 2); outside Spain, turned on, it records and sends nothing (FIX-HUB-VERIFACTU-ON-FOR-A-BUSINESS-OUTSIDE-SPAIN), and Apps not offering it there waits for a platform turn-on hook |
| VERIFACTU-F02 | Upload the business's own certificate | done — in the Hub; encrypted in the hub's DB with `FISCAL_CERTIFICATE_KEY` |
| VERIFACTU-F03 | Remove the own certificate | done — in the Hub |
| VERIFACTU-F04 | Choose who files: my certificate or ERPlora | done |
| VERIFACTU-F05 | Sign and upload the representation authorisation so ERPlora files | done — uploaded in the Hub, reviewed by staff in the SaaS (`fiscal/`) and the status comes back in the snapshot (round §25) |
| VERIFACTU-F06 | Send the authorisation again | done — in the Hub, like VERIFACTU-F05 |
| VERIFACTU-F07 | Request or renew the secure connection with ERPlora | discarded — no identity per hub (round 5); the Hub signs every call with HMAC |
| VERIFACTU-F08 | Go live | done — production = `prod` deployment ∧ `VERIFACTU_PRODUCTION_ENABLED` ∧ (own route with a valid certificate \| ERPlora route with an approved authorisation) ∧ active account, in every plan (round 2026-10-22b: VeriFactu in Free); the server keeps it closed until ERPlora opens it (under Ioan's supervision) |
| VERIFACTU-F09 | Go back to testing | done |
| VERIFACTU-F10 | Test the connection with the AEAT | done — with the SaaS gateway's probe (`/internal/verifactu/probe`) |
| VERIFACTU-F11 | Create a test invoice | done |
| VERIFACTU-F12 | Look up the responsible declaration | done |
| VERIFACTU-F13 | Record an issued invoice | done — Invoicing asks for it by name inside its issuing; the worker's outbox relay stays as a backup |
| VERIFACTU-F14 | Record a rectifying invoice | done — same as F13 |
| VERIFACTU-F15 | Send the record to the AEAT and collect its answer | done — the worker sends it through the SaaS gateway; without `VERIFACTU_GATEWAY_URL` the records wait in the queue |
| VERIFACTU-F16 | Look up the records and their status | done |
| VERIFACTU-F17 | See the detail of a record and why it waits | done |
| VERIFACTU-F18 | Verify the QR at the AEAT's site | done |
| VERIFACTU-F19 | Give the QR and the fiscal status to the ticket and the invoice | done (Sales and Printing ask for it by name) |
| VERIFACTU-F20 | Send later what could not go out (automatic contingency) | done — the worker runs it every minute (in phase 1, over a single hub) |
| VERIFACTU-F21 | Process the queue by hand | done |
| VERIFACTU-F22 | Retry a queue entry | done |
| VERIFACTU-F23 | Discard a queue entry | discarded — a generated record is never discarded |
| VERIFACTU-F24 | Act on a record rejected by the AEAT | done |
| VERIFACTU-F25 | Resend a given record | done — through the SaaS gateway |
| VERIFACTU-F26 | Verify the fingerprint chain | done |
| VERIFACTU-F27 | Look up what the AEAT has | done — through the SaaS gateway (`/internal/verifactu/query`) |
| VERIFACTU-F28 | Recover the chain from the AEAT after restoring a backup | done — through the SaaS gateway (`/internal/verifactu/query`) |
| VERIFACTU-F29 | Continue the chain of another application (migration) | done |
| VERIFACTU-F30 | Cancel a record sent by error | done |
| VERIFACTU-F31 | Watch the submissions from the screens | done — also from the four Home panels |
| VERIFACTU-F32 | Prevent turning the app off with unsent records | done — VeriFactu's `can_disable` and 409 `base.app_vetoed` from `base.app.disable` (hub#267) |
| VERIFACTU-F33 | Cease the activity | discarded — the census deregistration belongs to the business, outside ERPlora; a deregistered business does not open (410) |
| VERIFACTU-F34 | Renew the own certificate | done — in the Hub (uploading the renewed one replaces the previous one) |
| VERIFACTU-F35 | Ask the AEAT whether it already has a queue record | done — in the record's detail, in the Hub's admin and through the API |

### VERIFACTU-F01 Activate VeriFactu
Status: done — turning the app on in the Hub is activating it (activation per hub arrives with phase 2); outside Spain, turned on, it records and sends nothing (FIX-HUB-VERIFACTU-ON-FOR-A-BUSINESS-OUTSIDE-SPAIN), and Apps not offering it there waits for a platform turn-on hook
Actor: administrator
Screen: Hub: Apps
Steps:
1. In the Hub's apps, turn **VeriFactu** on (Invoicing turns on with it).
2. From that moment every invoice Invoicing issues is recorded (VERIFACTU-F13) in the test
   environment.
3. Only in a business in Spain. In one from another country (that of its erplora.com account), VeriFactu turned on
   does nothing: invoices go out without a record or QR, **VeriFactu → Settings** and **VeriFactu → Configuration**
   say on top "VeriFactu is only for businesses in Spain." without offering anything that leads to the AEAT, and
   whatever asks to record or send something answers the same.
In: nothing but the order.
Out: the app active; no switch of its own.
If it fails: the Hub's apps page says so.
Involved: INVOICE-F01

### VERIFACTU-F02 Upload the business's own certificate
Status: done — in the Hub; encrypted in the hub's DB with `FISCAL_CERTIFICATE_KEY`
Actor: owner and administrator (configure)
Screen: Configuration
Steps:
1. In **VeriFactu → Configuration**, tab "My certificate", tap "Choose the .p12 / .pfx file" and pick the
   business's certificate (1 MB at most).
2. Type its password in "Certificate password" and tap "Upload the certificate".
3. The Hub opens it with the password, reads holder, tax ID, kind and expiry and keeps it encrypted (Fernet)
   together with the password in the hub's database. "Certificate uploaded: {holder} ({taxId})." shows and the tab
   turns "Loaded". Uploading another one replaces the previous one.
4. In a business outside Spain it is not offered: on top it says "VeriFactu is only for businesses in Spain." and
   the tab only shows the certificate's status, without uploading or removing it.
In: the `.p12`/`.pfx` in base64 and its password (`verifactu.certificate.upload`).
Out: the certificate kept (`OwnCertificate`), an event "Own certificate of … uploaded" and the notice
`verifactu.config.changed`. The file and the password are never shown again: neither in the API, nor in the
admin, nor in the snapshot, nor in the server's logs.
If it fails: the certificate is not kept (409):
- with no storage key on the server, "This server cannot keep certificates yet: ERPlora has to set its storage
  key." (`verifactu.certificate_storage_unavailable`);
- with no issuer, "Set up the issuer first in Invoicing → Issuer." (`verifactu.issuer_missing`);
- a wrong password or a file that is not a `.p12`, "The file is not a .p12/.pfx certificate that this password
  opens."; without client-authentication use, "The certificate does not allow client authentication, so it cannot
  connect to the AEAT."; expired, "The certificate expired on {date}: upload a valid one."
  (all `verifactu.certificate_invalid`);
- a holder other than Invoicing's issuer, "The certificate belongs to {tax ID}, not to this business's issuer {tax
  ID}." (`verifactu.certificate_holder_mismatch`): through the own route it would file on behalf of someone else.
Involved: VERIFACTU-F04, VERIFACTU-F34

### VERIFACTU-F03 Remove the own certificate
Status: done — in the Hub
Actor: owner and administrator (configure)
Screen: Configuration
Steps:
1. In "My certificate", with one loaded, tap "Remove"; a card asks "Remove the certificate?".
2. On confirming, the certificate is deleted from the hub's database, "Certificate removed." shows and the tab
   turns "Not loaded".
3. If the route was "my certificate", the records can no longer go out until another one is uploaded or ERPlora
   is chosen (VERIFACTU-F04): they wait in the queue with the reason "your own certificate is not loaded or has
   expired".
In: nothing (`verifactu.certificate.remove`).
Out: the certificate deleted, an event "Own certificate of … removed" and the notice `verifactu.config.changed`.
If it fails: without the configure permission, 403.
Involved: VERIFACTU-F04

### VERIFACTU-F04 Choose who files: my certificate or ERPlora
Status: done
Actor: administrator
Screen: Settings
Steps:
1. In **VeriFactu → Settings**, the switch "Use my own certificate" shows the current route with its explanation:
   "ERPlora files your billing records with the tax agency on your behalf, with its own seal. You do not need a
   certificate." or "You file directly with the tax agency using your business certificate, uploaded in
   Configuration → My certificate.".
2. Change it.
3. "Done: from now on you send with your own certificate." or "Done: from now on ERPlora files on your behalf."
   shows.
4. In a business outside Spain, on top it says "VeriFactu is only for businesses in Spain." and the switch is
   disabled.
In: the chosen route; the uploaded certificate (VERIFACTU-F02) and the authorisation's status, from the account.
Out: the route kept; the next records go out through it (it announces `verifactu.config.changed`).
If it fails: with no valid certificate, "There is no valid certificate loaded: upload it in VeriFactu →
Configuration → My certificate."; in production and through the ERPlora route with no approved authorisation, "For
ERPlora to file in production, ERPlora still has to approve your signed authorisation.". The switch goes back to
the real route.
Involved: VERIFACTU-F02, VERIFACTU-F05

### VERIFACTU-F05 Sign and upload the representation authorisation so ERPlora files
Status: done — uploaded in the Hub (like the old module), reviewed by staff in the SaaS and the status comes back in
the snapshot (round §25, PLAN-SAAS §4)
Actor: administrator ("configure" permission)
Screen: Configuration
Steps:
1. In **VeriFactu → Configuration**, tab "ERPlora files for you", the status says "Not signed".
2. "Download the form" downloads the official form (Annex I of Agreement 17, the SaaS's) with the business's
   details already in: Invoicing's issuer's legal name, tax ID and address (the municipality and the street, with
   the number as it appears in the address); with no issuer, it comes blank. Whatever is missing is filled in and it
   is signed away from the screen: by hand (and scanned to PDF, with the stamp if it is a company) or with
   AutoFirma.
3. A company writes its legal representative (name and NIF/NIE); a sole trader signs themselves.
4. The identity document (DNI or NIE) is chosen and the PDFs attached: the signed form, the copy of the document,
   with a NIE a signature sample and, with a company, the proof of representation.
5. "Send for review": the Hub checks the documents and forwards them as they are to the SaaS; it stays "Under
   review".
6. A person at ERPlora reviews it in the SaaS; the account sends the Hub the new status: "Approved", "Returned"
   (with the reason) or "Revoked".
7. In a business outside Spain it is not offered: on top it says "VeriFactu is only for businesses in Spain." and
   the tab shows neither the authorisation nor the procedure.
In: Invoicing's issuer (the taxpayer), the representative, the document type and the PDFs in base64
(`verifactu.representation.submit`); the form, from `verifactu.representation.model`, which passes the issuer's
details to the SaaS.
Out: `POST /internal/hubs/{id}/representation` to the SaaS; "Under review" (an approved one stays in force and
filing until the new one is approved), its trace in "What you sent" and in the audit log (number, date, document
type and which documents; never their content) and the notice `verifactu.config.changed`. The Hub keeps no
document. Approved, it opens the ERPlora route in production (VERIFACTU-F08).
If it fails: before calling, with the SaaS's codes (422): the form is missing ("Attach the signed form."), it is not
a PDF ("The signed form has to be a PDF — scan it or sign it with AutoFirma."), the copy of the document is missing,
with a NIE the signature sample, with a company the representative or the proof, a file over 5 MB ("Each file has
to be 5 MB at most."); the SaaS's refusal, with its `fiscal.*` code and its fields as they are; with no issuer, 409
`verifactu.issuer_missing`; without the account's snapshot (the Hub does not know its id at ERPlora yet) or a
business the SaaS does not know, 409 `verifactu.hub_unregistered` ("ERPlora has not linked this business yet.");
without the SaaS, 503 `verifactu.saas_unreachable` ("ERPlora could not handle this right now. Try again in a few
minutes.").
When downloading the form, an issuer detail the form cannot write (a letter outside its own or a text that is too
long) comes blank to write it by hand, with the rest already in: it never leaves you without a form.
Involved: VERIFACTU-F08

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
If it fails: like VERIFACTU-F05.
Involved: VERIFACTU-F05

### VERIFACTU-F07 Request or renew the secure connection with ERPlora
Status: discarded — no identity per hub (round 5): the Hub signs every call to ERPlora's gateway with HMAC, so
there is no secure connection to request or renew
Actor: none
Screen: none
Steps:
1. There is nothing to request or renew.
2. The Hub and the ERPlora account talk over their signed internal channel.
In: nothing.
Out: nothing.
If it fails: does not apply.
Involved: none

### VERIFACTU-F08 Go live
Status: done — production = `prod` deployment ∧ `VERIFACTU_PRODUCTION_ENABLED` ∧ (own route with a valid
certificate | ERPlora route with an approved authorisation) ∧ active account (`status` of the snapshot), in every
plan (round 2026-10-22b: VeriFactu in Free, with no paid option); the server keeps it closed until ERPlora opens it (under Ioan's supervision). In `pre` it never opens: everything goes to testing. A
demo hub never goes live (`verifactu.go_live_forbidden`).
Actor: administrator
Screen: Settings
Steps:
1. In **VeriFactu → Settings**, "AEAT environment" shows "Testing (AEAT test)" and "Your invoices go to the AEAT's
   test environment. When everything is ready, go live.". If something is missing, below shows "It cannot go live
   yet:" with the list (demo business, authorisation not approved, own certificate missing or expired, account with
   a pending payment or suspended) and "Go live" stays disabled. No plan is missing from it: VeriFactu live is for
   every plan.
2. Tap "Go live" and confirm in "Send your invoices to the AEAT for real?" ("From now on every record goes to the
   real AEAT. As soon as the first one is sealed you can no longer go back to testing.").
3. "Your business is live: records now go to the real AEAT." shows and the pill turns
   "Production".
In: Invoicing's issuer; the route and its status; from the account's snapshot (`verifactu.config.sync`), the
authorisation and the business's status (the snapshot of an older SaaS still brings `live_paid`: it is accepted and not read).
Out: the environment in production (it announces `verifactu.config.changed`): new records are born in the
production chain, with the real site's QR; those born in testing keep going to testing.
If it fails: while ERPlora does not open it on the server, "Going live is not open on this server yet: ERPlora
opens it when the real submission is ready." (in Settings, in the list of what is missing: "ERPlora has not opened
real filing with the AEAT on this server yet", `production_closed`); without the SaaS gateway on the server,
"ERPlora's sending gateway is not configured on this server: nothing could reach the AEAT."
(`verifactu.gateway_unavailable`); with an own certificate this server does not open (the key
`FISCAL_CERTIFICATE_KEY` is missing or was rotated), "Your own certificate cannot be opened on this server: upload it
again in VeriFactu → Configuration → My certificate." (`verifactu.own_certificate_unreadable`); in a demo hub, "A demo
business cannot go live: it always files in the AEAT's test environment." (`verifactu.go_live_forbidden`;
who is a demo is said by the platform, `base.operations.is_demo_hub`); with no issuer, "Set up the issuer first in
Invoicing → Issuer."; through the ERPlora route with no approved authorisation, "For ERPlora to file in production,
ERPlora still has to approve your signed authorisation." (`verifactu.representation_not_approved`); with the account
with a pending payment or suspended, "Your ERPlora account has a pending payment or is suspended: settle it in your
ERPlora account to go live." (`verifactu.hub_not_active`); with an own certificate missing or expired, "There is no
valid certificate loaded: upload it in VeriFactu → Configuration → My certificate."
(`verifactu.no_own_certificate`). All of them are 409 and the environment stays in testing. Already in production,
it does nothing.
In a business outside Spain it is refused as with the app off, "VeriFactu is only for businesses in Spain." (404
`app_inactive`), and Settings says it on top, "VeriFactu is only for businesses in Spain.", as the only reason
(without the list of what is missing), with "Go live" disabled.
If the route is lost in production (the snapshot stops bringing the approved authorisation, or the own certificate
expires), it does not go back to testing (there are production records already): **nothing new is sealed** —the
sale or the invoice is refused with 409 and the route's code (`verifactu.representation_not_approved`,
`verifactu.own_certificate_missing`) and "Nothing was issued: this business files for real with the AEAT and cannot
reach it now:", the reason and "Fix it in VeriFactu → Settings and try again."— and Settings says it under "New sales
and invoices are refused until this is fixed:" (`issue_blocker`). What was already sealed with no approved
authorisation or no valid certificate waits, because the gateway could not file it. Switching to the ERPlora route
in production without the approved authorisation is refused the same way.
From the old Hub (`fiscal_profile::go_live`): the order (closed → demo → route → ready), the own certificate without
an authorisation, the 409 with the cause's code and VeriFactu with no separate payment. New from Ioan's model of
2026-10-15: the account's status, which before only held back the gateway's token in the SaaS. The paid option that
model added was withdrawn by round 2026-10-22b (VeriFactu in Free).
Involved: VERIFACTU-F05, VERIFACTU-F09

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
1. In **VeriFactu → Settings**, "Live test", tap "Test the connection" (the buttons wait while it tests).
2. The Hub checks, without filing anything with the AEAT, everything needed to send: the issuer, the producer's
   data, the route and its status and, if the gateway is configured, asks it whether it can file now.
3. Below the result shows, line by line, and "This business can send." or "It cannot send yet:" with the
   reasons.
4. In a business outside Spain, on top it says "VeriFactu is only for businesses in Spain." and "Test the
   connection" is disabled.
In: the Hub's configuration; the answer of the gateway's probe.
Out: the result as a "Connection test" event (it announces `verifactu.diagnostic.run`), without creating any
record or touching the chain.
If it fails: what is missing, said in the result. It never files a sample record: a filed record cannot be
undone.
Involved: VERIFACTU-F15

### VERIFACTU-F11 Create a test invoice
Status: done
Actor: administrator
Screen: Settings
Steps:
1. With the business in testing, in **VeriFactu → Settings**, "Live test", tap "Create test invoice". In
   production the button does not show.
2. VeriFactu asks Invoicing for a ticket (F2) of one line "Prueba VeriFactu" of €1.00 plus 21% VAT in the TICKET
   series, through the same door as the manual issuing (INVOICE-F03).
3. "Test invoice {number} created: its record is in Records." shows.
4. In a business outside Spain, on top it says "VeriFactu is only for businesses in Spain." and "Create test
   invoice" is disabled.
In: nothing to type.
Out: a real Invoicing invoice in testing and its record, which goes out like any other.
If it fails: Invoicing's refusal (no issuer, no permission to issue).
Involved: INVOICE-F03

### VERIFACTU-F12 Look up the responsible declaration
Status: done
Actor: employee, manager, administrator
Screen: Settings
Steps:
1. In **VeriFactu → Settings**, card "Responsible declaration", "Read the signed declaration" opens the one
   published on erplora.com; next to it, "Declaration version".
2. "Identifying data of this system" shows the producer's data, the installed version and the installation number
   (this business's identifier at ERPlora).
In: the declaration (fixed in the Hub's version).
Out: nothing; it is a lookup.
If it fails: the failure's message.
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
Involved: INVOICE-F01, INVOICE-F02, INVOICE-F03, INVOICE-F04, INVOICE-F05

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
A business's record is always presented as that business, never as ERPlora's hub (hub#454): the pass of ERPlora's
hub (the worker's fixed scope in phase 1, which sees the businesses' records while the tables are shared) presents
it with the id erplora.com gave the business; without that id (its account's photo has not arrived yet) nothing is
sent and the record waits with "ERPlora has not linked this business to its account on this server yet"
(`hub_unregistered`; "Send now" → 409 `verifactu.hub_unregistered`) until the photo brings it.
Involved: VERIFACTU-F20, FLOW-F04 (the card of the Automations gallery that creates an urgent task when the AEAT
rejects a record)

### VERIFACTU-F16 Look up the records and their status
Status: done
Actor: employee, manager, administrator
Screen: Records
Steps:
1. Open **VeriFactu → Records**.
2. Search by invoice number, sequence, issuer's name or tax ID, or filter by status, type, invoice type,
   environment, date and total.
3. Each row shows its status with a colour: green "Accepted", amber "Pending" / "Sent" / "Accepted with
   errors", red "Rejected"; and its environment, so as not to mix testing up with production.
In: the records.
Out: nothing; it is a lookup.
If it fails: the message with "Retry".
Involved: INVOICE-F16

### VERIFACTU-F17 See the detail of a record and why it waits
Status: done
Actor: employee, manager, administrator
Screen: Record detail
Steps:
1. In **Records**, tap a row.
2. "Record {number}" opens with the invoice, the chain, the QR, the AEAT's answer and the XML.
3. If it is not at the AEAT, "Not at the AEAT yet" says why ("ERPlora's sending gateway is not configured on this
   server", "your own certificate is not loaded or has expired", "the AEAT asked to wait until {time}", "the
   gateway or the AEAT could not be reached ({detail})", "ERPlora has not linked this business to its account on
   this server yet") and a single when: if everything it waits for clears by itself (the AEAT asked to wait, no
   connection, no answer, an AEAT fault), "It goes out by itself with the next pass, in order, and declared as late
   if it failed before. You do not have to do anything."; if it waits for something to be resolved (a refusal of
   the gateway, which is not sent again by itself; the authorisation; the route; the server; the business not
   linked), "It goes out by itself, in order and declared as late, as soon as that is resolved." (hub#454). Below,
   the "Next attempt".
4. In a business outside Spain it only says "this business is not in Spain: VeriFactu is only for businesses in
   Spain, so nothing is sent to the AEAT", with no next attempt nor buttons to send, correct or cancel:
   it never goes out.
In: the record.
Out: nothing; it is a lookup.
If it fails: "Record not found" or the failure's message.
Involved: VERIFACTU-F15

### VERIFACTU-F18 Verify the QR at the AEAT's site
Status: done
Actor: employee, manager, administrator, customer
Screen: Records
Steps:
1. In **Records**, "Verify at the AEAT" on the row (or in the detail) opens in another tab the AEAT's verification
   page with the issuer's tax ID, the number, the date and the amount.
2. A record born in testing leads to the test site; one from production, to the real site.
3. The customer does the same by scanning the QR of their ticket or their invoice.
In: the QR's link set when sealing.
Out: nothing in the Hub.
If it fails: a record that has not gone out yet shows at the AEAT as not found; a rejected one, never.
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
Status: done — the worker runs it every minute (in phase 1, over a single hub)
Actor: system
Screen: Contingency
Steps:
1. While selling, nothing stops because of this: if the gateway, the AEAT or the network are down, charging goes on
   and the record waits.
2. Every minute (scheduled task `process_queue`) the system does the pass of VERIFACTU-F15 on every chain that is
   due, each one in its environment; if passes were missed (server stopped), on coming back a single one is
   done.
3. Whatever fails again waits longer (5, 10, 20, 40 and 60 minutes), with no limit of attempts.
4. The event "Queue processed: {sent} sent, {accepted} accepted, {rejected} rejected, {waiting}
   waiting." is left.
In: the pending records.
Out: the submissions and their answers (it announces `verifactu.contingency.processed`).
If it fails: whatever does not go out stays in the queue with its reason; in a business outside Spain it never goes
out. The pass presents each record as the business it belongs to, never as ERPlora's hub (VERIFACTU-F15, hub#454).
Involved: VERIFACTU-F15

### VERIFACTU-F21 Process the queue by hand
Status: done
Actor: manager, administrator
Screen: Contingency
Steps:
1. In **VeriFactu → Contingency**, tap "Process queue" ("Processing…").
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
1. In **VeriFactu → Contingency**, tap "Retry" on the row.
2. The record (and the earlier ones of its chain, which go out before it) are set to go out with the next pass;
   the attempts are kept.
In: the chosen record.
Out: the rescheduled record (it announces `verifactu.contingency.retried`).
If it fails: an accepted or rejected record is not in the queue: "This record is not in the queue: it is already in the AEAT, or the
AEAT rejected it.".
Involved: VERIFACTU-F21

### VERIFACTU-F23 Discard a queue entry
Status: discarded — a generated record is never discarded: it leaves the queue when it is sent (VERIFACTU-F25),
because the AEAT already has it (VERIFACTU-F35) or corrected with a new one (VERIFACTU-F24)
Actor: none
Screen: none
Steps:
1. A record that is in the queue has to reach the AEAT (FAQ §5); an accepted one is no longer in the queue.
2. The only thing that leaves the queue without a new submission is what the AEAT **already has**, by asking it
   (VERIFACTU-F35); a rejection is corrected with a new record (VERIFACTU-F24).
In: nothing.
Out: nothing.
If it fails: does not apply.
Involved: VERIFACTU-F24, VERIFACTU-F35

### VERIFACTU-F24 Act on a record rejected by the AEAT
Status: done
Actor: administrator
Screen: Record detail
Steps:
1. The record shows in red "Rejected" in **Records**; in **Events** "Submission failed" is left with the reason.
2. In its detail, "The AEAT rejected it" with the AEAT's literal code and message and what to do: if the error is
   in the invoice's data (a customer's tax ID the AEAT does not know, an amount), it is corrected **in Invoicing**
   with a rectifying invoice; if not (a chain error after restoring a backup, a fault of ours), "Correct".
3. "Correct" (with confirmation) seals a **new** record of the same invoice, read again, marked as a correction,
   which enters the queue. The rejected one stays as it is. `RechazoPrevio` according to the VERI*FACTU web service
   Description v1.0.3: `X` if the AEAT has no record of that invoice (the initial registration was rejected;
   §9.1.3, "registration after rejection"); `S` if the AEAT does have it and what was rejected was a later
   correction.
4. An "Accepted with errors" can also be corrected (`Subsanacion = S`, `RechazoPrevio = N`; §9.1.2).
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
3. The record ends with the AEAT's answer, as in VERIFACTU-F15.
In: the chosen record (by its id or by its invoice's number).
Out: the submission and its answer (it announces `verifactu.record.transmitted`).
If it fails: with no gateway, "It cannot be sent now: ERPlora's sending gateway is not configured on this server. It
stays in the queue and goes out as soon as it can."; already accepted or rejected, "This record is not in the queue:
it is already in the AEAT, or the AEAT rejected it."; with the AEAT's wait under
way, "The AEAT asked to wait: it goes out by itself at {time}.". It never says "accepted" without an answer.
Involved: VERIFACTU-F15

### VERIFACTU-F26 Verify the fingerprint chain
Status: done
Actor: employee, manager, administrator
Screen: Recovery
Steps:
1. In **VeriFactu → Recovery**, with the "Issuer tax ID", tap "Validate chain" ("Working…").
2. The system recomputes the fingerprint of each record of the current environment's chain and checks that each one
   carries the previous one's.
3. "Operation completed." and the verdict show: "Fingerprint chain intact: {total} record(s) with their SHA-256
   chaining verified ({tax ID})." or "Fingerprint chain BROKEN at sequence {seq} ({tax ID}).".
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
1. In **VeriFactu → Recovery**, tap "Query AEAT" ("Working…").
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
   **VeriFactu → Recovery**.
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
1. In **VeriFactu → Recovery**, block "Continue chain manually (migration)", type the "Last
   fingerprint (64 hex)" of the previous application, the "Invoice number" and the "Date" of that last record.
2. Tap "Continue from this fingerprint" and confirm ("The fingerprint given will be the predecessor of the next
   fiscal record. Use this only during a migration and with the data of the last record of the previous
   application.").
3. "Operation completed." shows; the next invoice chains on that fingerprint.
In: the fingerprint, the number and the date of the previous application's last record.
Out: a new anchor (it announces `verifactu.chain.recovered`).
If it fails: a fingerprint that does not have 64 hexadecimal characters, "The fingerprint must be 64 hexadecimal
characters"; with no number or date, which are part of the chaining, the field asks for it; with pending records,
like VERIFACTU-F28.
Involved: none

### VERIFACTU-F30 Cancel a record sent by error
Status: done
Actor: administrator, assistant
Screen: Record detail
Steps:
1. Only for an invoice that **should never have been issued** (a duplicate, a test made in production). A
   refund or a correction is not cancelled: it is a rectifying invoice in Invoicing (VERIFACTU-F14).
2. In the detail of the registration record, tap "Cancel record", write the reason and confirm ("The AEAT will be
   told this invoice was issued by error. A refund or a correction is never this: it is a rectifying invoice in
   Invoicing. The invoice stays in Invoicing.").
3. A chained **cancellation** record is sealed, which goes out like any other, and shows in Records with
   type "Cancellation".
In: the registration record (or its invoice's number).
Out: the cancellation record (it announces `verifactu.record.created`).
If it fails: a rejected registration is not cancelled (it is not at the AEAT); an already cancelled one, neither:
"This record cannot be cancelled: only a registration that reached (or will reach) the AEAT and has no
cancellation can.". If the AEAT rejected the cancellation, it can be cancelled again: the new one
carries `RechazoPrevio = S` (§9.2.2, "cancellation after rejection").
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

### VERIFACTU-F32 Prevent turning the app off with unsent records
Status: done — the platform asks when turning off (`base.app.disable`, hub#256) and VeriFactu answers with its
`can_disable` (hub#267, FIX-BASE-APP-TURN-OFF-VETO)
Actor: system
Screen: Hub: Apps
Steps:
1. When turning VeriFactu off, the platform asks it how many records are not at the AEAT yet: the pending ones
   (also those waiting for their retry) and those sent with no answer. Invoicing cannot be turned off while
   VeriFactu is on, because VeriFactu needs it.
2. If any is left, it refuses and VeriFactu stays on. What the AEAT already answered (accepted, accepted with errors
   or rejected) does not count: a rejection is corrected with a new record, which counts while it does not go out.
3. In a business outside Spain it never refuses: its records are not going to be sent, so turning it off stops
   nothing; they are kept as they are.
In: the request to turn it off.
Out: nothing if it refuses; the app off if nothing is left to send.
If it fails: "VeriFactu still has {n} records to send to the AEAT. Wait until they are sent or fix them before turning
it off." (with one: "VeriFactu still has 1 record to send to the AEAT. Wait until it is sent or fix it before turning
it off.").
Involved: BASE-F23, BASE-F25

### VERIFACTU-F33 Cease the activity
Status: discarded — ceasing before the tax agency is the business's census deregistration (form 036/037), outside
ERPlora; and a business deregistered at ERPlora no longer opens (410), so it neither issues nor goes live
Actor: administrator
Screen: none
Steps:
1. Ceasing before the tax agency is the census deregistration (form 036/037), outside ERPlora.
2. The software sends nothing.
In: nothing.
Out: nothing.
If it fails: does not apply.
Involved: none

### VERIFACTU-F34 Renew the own certificate
Status: done — in the Hub (uploading the renewed one replaces the previous one)
Actor: owner and administrator (configure)
Screen: Configuration
Steps:
1. "My certificate" shows "Expires on {date}" and, at 30 days or less, "Expires in {n} days: upload the renewed one
   here.".
2. The new certificate is uploaded as in VERIFACTU-F02 and replaces the previous one; the chain does not change.
In: the renewed certificate.
Out: the new one, instead of the previous one.
If it fails: expired and with the route "my certificate", the records wait with the reason; if the server changed
its storage key and cannot open the kept one, they wait with "your own certificate cannot be opened on this server:
upload it again".
Involved: VERIFACTU-F02

### VERIFACTU-F35 Ask the AEAT whether it already has a queue record
Status: done — in the record's detail, in the Hub's Django admin (support) and through the API
Actor: manager, administrator (send); ERPlora's staff from the admin
Screen: Record detail ("Ask the AEAT"); for the staff, the Django admin (Records → "Ask the AEAT (out of the queue if
it already has it)")
Steps:
1. A record was left "sent, with no answer" (or pending) and the AEAT may already have it: in its detail, tap
   "Ask the AEAT".
2. The AEAT is queried, through ERPlora's gateway, for the record's issuer in the month of its issue date
   (like VERIFACTU-F27, which renews the last snapshot).
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
Involved: VERIFACTU-F22, VERIFACTU-F23, VERIFACTU-F27

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
| The configuration: environment, route, own certificate (holder, tax ID, kind, expiry; never its material), status of the authorisation, producer's data, declaration | view | F02, F04, F08, F09, F12 | `verifactu.config.get` |
| The records, with search, filters, sorting and pages (up to 100) | view | F16 | `verifactu.record.list` |
| A record, by its id or by its invoice's number, with its QR, its XML and why it waits | view | F17, F18 | `verifactu.record.get` |
| The current record of an invoice (QR, CSV, status) | view | F19 | `verifactu.record.by_invoice` |
| The queue: the records not yet at the AEAT | view | F20–F22 | `verifactu.contingency.list` |
| The audit events, with search by words and filters | view | F31 | `verifactu.event.list` |
| How many records are not at the AEAT (and whether it can be turned off) | view | F31, F32 | `verifactu.stats.compliance_summary`; when turning off, `can_disable` |
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
| Chooses the sending route | configure | F04 | `verifactu.config.update` |
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
| Platform (`base.app.disable`) | Not turn VeriFactu off with unsent records (in Spain) | `can_disable` of `VerifactuConfig` |

### Who can do what

| Permission | Owner | Administrator | Manager | Employee | Service |
|---|---|---|---|---|---|
| View records, queue, events, chain and configuration; verify the chain | yes | yes | yes | yes | `verifactu.view_record` |
| Record an issued invoice (Invoicing asks for it with the session of whoever issues) | yes | yes | yes | yes | `verifactu.add_record` |
| Send, process and retry the queue, query the AEAT, test the connection | yes | yes | yes | no | `verifactu.transmit_record` |
| Correct and cancel records | yes | yes | no | no | `verifactu.correct_record` |
| Upload and remove the own certificate, choose the route, go live and back, recover the chain, test invoice | yes | yes | no | no | `verifactu.configure` |

The roles arrive from the SaaS with a prefix (`hub_owner`, `hub_admin`, `hub_manager`, `hub_employee`). Keeping
what the account sends (`verifactu.sync_config`) belongs to no role: only to the system.
