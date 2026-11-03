<!-- generated from WORKBOOK.md sha256:75fde3d7c5585f467709eab15cc449c75e66fe7b4e7c347d9bebf92d97027d4b -->

## What it is for and who it is for

The WhatsApp inbox puts the business's WhatsApp inside the Hub: each customer who writes to the business's number
has **one conversation**, with all their messages, and the team reads it and **answers from the Hub**, without
picking up the phone. It recognises the person by their number and links the conversation to their card in
Customers; it lets you **assign** each conversation to someone on the team, mark it **open, pending or closed** and
leave **internal notes** the customer never sees. Once 24 hours have passed since the customer's last message,
WhatsApp only lets you write with a **template approved by Meta**: the inbox knows it and offers the business's
templates, which are created, edited and deleted in its Settings.

It serves the hair salon (the customer asking for an appointment) and the restaurant (the guest asking about a
table) alike: what changes is what is answered, not how.

Who uses it:

- The **owner** and the **administrator**: everything, including seeing the number's status, managing the
  templates (Settings) and erasing a number's data.
- The **manager**: reads, answers, assigns to anyone, changes the status and leaves notes.
- The **employee**: reads, answers, assigns to themselves, changes the status and leaves notes.
- On the other side, the **customer** only uses their WhatsApp.

The owner can keep answering from the WhatsApp Business app on their phone: what they write there shows in the
conversation as a message from the business (Meta's coexistence).

## Reference adopted

| Product | How it solves it | Source |
|---|---|---|
| Square Messages | Inbox in the dashboard and in the POS: you pick the conversation and answer; asks for consent before writing first to a mobile | https://squareup.com/help/us/en/article/8415-reply-to-customers-with-square-messages |
| Shopify Inbox | Open/closed conversations, closed and reopened by hand; assigned only to whoever has chat permission | https://help.shopify.com/en/manual/inbox/conversations |
| Fresha (Client Connect) | Client inbox: answer, open/closed, unread and internal notes for the team | https://www.fresha.com/help-center/knowledge-base/messaging/102320-manage-client-messages-in-client-connect |
| Vagaro Connect | Two-way messages with clients from the dashboard | https://www.vagaro.com/en-au/pro/updates/vagaro-connect |
| Odoo (WhatsApp) | Free reply within 24 h of the customer's last message; after that, only an approved template. Templates are written in Odoo and sent to Meta with "Submit for Approval" | https://odoo.com/pt_BR/forum/ajuda-1/v183-how-can-i-send-a-whatsapp-message-to-my-customer-after-24-hours-285255 |
| Zendesk | Open / pending (waiting for the customer) / solved; when the customer answers, it goes back to open | https://www.eesel.ai/blog/zendesk-ticket-status-lifecycle |
| Intercom | Internal notes in the conversation that do not change its status; open, snooze, close | https://community.intercom.com/inbox-9/snoozed-conversations-reopen-when-adding-a-note-8095 |
| Front | Internal comments inline with the conversation, for the team only | https://www.getmacha.com/blog/front-comments-and-mentions-explained |
| Meta (WhatsApp Business Platform) | 24 h window from the customer's last message; outside it, only templates | https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/send-messages |
| SleekFlow / Chakra (WhatsApp inboxes) | Mandatory opt-in before writing; "I'll take it" with a warning when agents clash | https://help.sleekflow.io/whatsapp/whatsapp-message-opt-in · https://chakrahq.com/article/whatsapp-shared-inbox-for-customer-support-teams/ |
| WATI, Respond.io, Twilio, Gupshup, AiSensy, Interakt, Zoko (templates) | Create, edit and delete the template in their own dashboard, with examples of the variables, and see Meta's verdict in the list | https://support.wati.io/en/articles/11463217-how-to-create-a-whatsapp-template-message |

**Wins:** an inbox you answer from (Square, Shopify, Fresha, Vagaro, Odoo), with three statuses (open, pending,
closed) where a new message from the customer reopens the conversation (Zendesk), assignment to whoever can read the
inbox with "Assign to me" that never overrides someone else (Shopify, Chakra), internal notes in the thread (Fresha,
Intercom, Front), Meta's 24-hour rule enforced on the server and the templates managed in the app itself (Odoo, WATI,
Respond.io and the current product).
**Why not the others:** answering only from the phone (the current product) forces you to pick up the phone and
leaves the inbox read-only; two statuses (Shopify) do not tell "waiting for the customer" from "it is done";
assigning by typing an identifier (the current product) is used by nobody; sending the owner to WhatsApp Manager to
create the templates takes them out of the app for something they do every day.

## Before you start

1. Turn on **Customers**: the inbox does not turn on without it (it links each conversation to its card).
2. Connect the business's WhatsApp Business number in **WhatsApp inbox → Settings → Connect WhatsApp**: Meta's
   window opens, you sign in with Facebook and choose the number (the WhatsApp account and the link with Meta are
   kept by erplora.com).
3. Create the templates in **Settings → Meta templates → Add template** (or in WhatsApp Manager) and wait for Meta
   to approve them: the ones from WhatsApp Manager show up by themselves in the same list.
4. Write to the number from another phone and check that the conversation shows up in the inbox.

## Screens

### Inbox
Menu **WhatsApp inbox → Inbox** (title "WhatsApp inbox"). Every role sees it. Table with **Contact** (the card's
name, or the WhatsApp one, or the number), **Phone**, **Status** (Open, Pending, Closed), **Assigned to**,
**Unread** and **Last message** (the time if it is from today, "Yesterday", or the date, on the business's clock);
search box "Filter contact or phone…"; filters **Status**, **Assigned to** (Me, Unassigned) and **Unread** behind
**Filters**, next to the search box (on the phone they open in a sheet over the list) and with **Apply**; 50 per
page; the most recent activity first. Row action **Open** (or tap the row): the conversation opens in a panel on top
of the list, which stays underneath.

The panel shows: the contact, their number and their status; the linked card in Customers (with a link) or **Link
to a card** / **Create card**; **Assigned to** with the team picker and **Assign to me**; the status buttons
**Open / Pending / Closed**; the thread, from the oldest message to the newest (the customer's on the left, the
business's on the right with their status —Sending…, Sent, Delivered, Read, Not delivered, or Not sent with
**Retry**—, photos and voice notes inside their bubble, videos and documents with **Open the attachment**, internal
notes in yellow with their author); **View earlier** if there are more; and below, the box to write in with two
tabs: **Reply** (text, **Send**, and **Template**) and **Internal note** (**Add note**). With the 24-hour window
closed, the text box says so ("More than 24 hours have passed since the customer's last message: WhatsApp only lets
you write to them with an approved template.") and only **Template** is left. Only the owner and the administrator
see **Erase this number's data**.

Notices above the list: "Reconnecting…" while the live connection comes back; the number not connected ("WhatsApp is
not connected. Connect the business’s number in Settings to receive and send messages.") or to be reconnected
("WhatsApp asks to reconnect the number in Settings: until then nothing can be sent."), both with **Go to Settings**
for whoever can configure; from 80 % of the month's messages, the ones left ("You have 30 of 150 WhatsApp messages
of your plan left this month."); the plan's messages spent this month ("You have used all the WhatsApp messages of
your plan this month. Messages keep arriving here, but nothing can be sent until next month or until you upgrade the
plan.") or a plan that includes none ("Your plan does not include WhatsApp messages. Messages keep arriving here, but
nothing can be sent until you upgrade the plan."), all three with **Upgrade plan** for whoever can configure, in the
browser (it is not in the installed app: what sells is only on the web).
Empty: "No conversations.", in view below the search box on the phone too; with a search or a filter: "No results";
loading: an indicator; list error: the reason with **Retry**; panel error: the reason the Hub gives or "Could not load
the conversation"; a photo or a voice note that does not load: "The image could not be loaded." or "The voice note
could not be loaded.", with **Open the attachment**.

### Settings
Menu **WhatsApp inbox → Settings** (title "Channel settings"), owner and administrator only. Three blocks: **Your
number** ("Connected" with the number and the business's name, "Not connected" or "Needs reconnecting"; not
connected or to be reconnected, "Checking with erplora.com…" and then **Connect WhatsApp** or **Reconnect**, or the
reason it cannot be done yet; connected or to be reconnected, **Disconnect**, which asks first); **This month** (the
messages sent against the plan's; from 80 %, "You have 30 of 150 messages of your plan left this month.", and at the
cap "You have used all the messages of your plan this month."; if the plan includes none, "Your plan does not include
WhatsApp messages."; before erplora.com speaks, "erplora.com has not reported this month’s messages yet."; from 80 %
and at the cap, **Upgrade plan**, which opens erplora.com's plans, only in the browser); and **Meta templates**: a
table with **Name**, **Language**, **Category** (Utility, Marketing, Authentication), **Status in Meta** (Not sent to
Meta, Approved, In review, Rejected, Paused by Meta, Disabled by Meta, Deleted in WhatsApp Manager; underneath, when
it applies, "Sending to Meta…", "Not accepted: …", "Changes not sent: …" or "Being deleted at Meta") and **Text**,
with search box "Search template…", Meta's reason on the rejected ones and the **Add template** button. Row actions:
**Edit** (or tap the row; only the ones the Hub knows how to write), **Send to Meta again** (the one that did not get
there or was not accepted) and **Delete**. Empty: "No templates." with "Create one with «Add template»: Meta reviews
it. The ones made in WhatsApp Manager appear here too.".

### Template (sheet)
It opens with **Add template** ("New template") or **Edit** ("Edit template — name"), on top of Settings. Fields:
**Name** ("Lowercase letters, numbers and underscores. It cannot be changed later."), **Language** and **Category**
(Utility or Marketing), **Header type** (Text, Photo, Video or Document) with **Header (optional)** if it is text or,
if it carries a file, **Choose file** ("No file chosen"; once chosen, its name and size with **Change file**, what it
accepts, e.g. "JPEG or PNG, up to 5 MB.", and "Meta reviews the template with this file."), **Text** ("Where a
variable goes, write its number between double braces, starting with 1."), an **Example for variable n** for each
variable ("Meta reviews the template with these examples."), **Footer (optional)** and **Buttons** (**Add button**:
Quick reply, Link or Call, with its text and its address or its number; **Remove button**). Final button **Send to
Meta for review** (new) or **Save and send to Meta** (edit). When editing an approved one it warns: "Until Meta
approves the changes, the approved one keeps being sent."; the category of one Meta has not rejected cannot be
touched ("Meta only lets you change the category of a template it rejected.").

## States of each screen

| Screen | Loading | Empty | Error | No permission / app off |
|---|---|---|---|---|
| Inbox | indicator in the table; the panel, "Loading…" | "No conversations." / "No results" | the reason + **Retry**; the panel, its reason | "You do not have permission" / "This app is not active in this business" instead of the list |
| Conversation panel | "Loading…" | "No messages yet." | "Could not load the conversation" | — |
| Settings | indicator | "No templates." | the reason + **Retry** | same as the inbox |
| Template (sheet) | the final button busy while it saves | — | the reason under its field, or at the top the one the Hub gives | only the owner and the administrator open it |

## Flows

| ID | Flow | Status | Vertical |
|---|---|---|---|
| WHATSAPP_INBOX-F01 | Connect the business's WhatsApp number | done | common |
| WHATSAPP_INBOX-F02 | Disconnect or reconnect the number | done | common |
| WHATSAPP_INBOX-F03 | Receive a message in the inbox | done | common |
| WHATSAPP_INBOX-F04 | Recognise the customer by their number | done | common |
| WHATSAPP_INBOX-F05 | Read a conversation | done | common |
| WHATSAPP_INBOX-F06 | See a photo, a voice note or a document | done | common |
| WHATSAPP_INBOX-F07 | Assign a conversation to someone on the team | done | common |
| WHATSAPP_INBOX-F08 | Answer from the WhatsApp Business app on the phone | done | common |
| WHATSAPP_INBOX-F09 | See who is waiting for an answer | done | common |
| WHATSAPP_INBOX-F10 | Erase the data of a number with no card | done | common |
| WHATSAPP_INBOX-F11 | Erase a customer's data from their card | done | common |
| WHATSAPP_INBOX-F12 | Merge two cards of the same customer | done | common |
| WHATSAPP_INBOX-F13 | See the month's usage and reach the cap | done | common |
| WHATSAPP_INBOX-F14 | Turn on "Book appointments" | discarded — **Book appointments** is not offered: after your **Approve**, Appointments refuses the appointment the assistant proposes, because an automation only books with the permission for its own appointments; the card comes back when Appointments accepts it (hub#514) | hair salon |
| WHATSAPP_INBOX-F15 | Turn on "Book a table" | done | restaurant |
| WHATSAPP_INBOX-F16 | Decide whether WhatsApp bookings confirm by themselves | done | common |
| WHATSAPP_INBOX-F17 | Turn off an automatic answer | done | common |
| WHATSAPP_INBOX-F18 | Update an automatic answer to its improved version | done | common |
| WHATSAPP_INBOX-F19 | Choose the slot by writing instead of tapping | done | common |
| WHATSAPP_INBOX-F20 | When the assistant cannot answer | done | common |
| WHATSAPP_INBOX-F21 | The customer asks for an appointment on WhatsApp | discarded — not offered: after your **Approve**, Appointments refuses the appointment the assistant proposes (F14); today she is answered from the inbox and the appointment is booked by hand in the Agenda (hub#514) | hair salon |
| WHATSAPP_INBOX-F22 | The customer cancels or moves her appointment on WhatsApp | discarded — not offered, for the same reason as F21, and cancelling an appointment cannot be entrusted to an automation either; today it is cancelled or moved by hand from the Agenda (hub#514) | hair salon |
| WHATSAPP_INBOX-F23 | The customer gets the notice when the salon confirms | done | hair salon |
| WHATSAPP_INBOX-F24 | The guest asks for a table on WhatsApp | done | restaurant |
| WHATSAPP_INBOX-F25 | The guest cancels or changes their table on WhatsApp | done | restaurant |
| WHATSAPP_INBOX-F26 | The guest gets the notice when the restaurant confirms | done | restaurant |
| WHATSAPP_INBOX-F27 | See the templates and what Meta says about each one | done | common |
| WHATSAPP_INBOX-F28 | Bring in the templates created in WhatsApp Manager | done | common |
| WHATSAPP_INBOX-F29 | Create a template and send it for review | done | common |
| WHATSAPP_INBOX-F30 | Edit a template | done | common |
| WHATSAPP_INBOX-F31 | Delete a template | done | common |
| WHATSAPP_INBOX-F32 | Answer from the inbox | done | common |
| WHATSAPP_INBOX-F33 | Send a template | done | common |
| WHATSAPP_INBOX-F34 | Know whether a message got there and was read | done | common |
| WHATSAPP_INBOX-F35 | Change a conversation's status | done | common |
| WHATSAPP_INBOX-F36 | Leave an internal note | done | common |
| WHATSAPP_INBOX-F37 | Link the conversation to a card or create the card | done | common |
| WHATSAPP_INBOX-F38 | Know which question what the customer taps answers | done | common |

### WHATSAPP_INBOX-F01 Connect the business's WhatsApp number
Status: done
Actor: owner, administrator
Screen: Settings
Steps:
1. Open **WhatsApp inbox → Settings**: **Your number** says "Not connected" and, after "Checking with
   erplora.com…", offers **Connect WhatsApp**.
2. Press **Connect WhatsApp**: Meta's window opens ("Finish in Meta’s window…"); you sign in with Facebook and
   choose or add the business's number. If it is already used in the WhatsApp Business app on the phone, you scan
   the code with that phone and keep using WhatsApp on it as always.
3. When you finish in the window, **Your number** says "Connecting…" and straight away "Connected" with the number
   and the business's name, without reloading. If the number came from the phone app, it warns that its contacts
   and chats reach the inbox within a few minutes.
In: what Meta's window returns (a one-time code, the WhatsApp Business account, the chosen number and the
portfolio) and erplora.com's answer.
Out: the number connected to this business, without touching anyone else's; notice
`whatsapp_inbox.channel.connected`.
If it fails: if erplora.com does not answer, **Your number** says so with **Retry**; if WhatsApp is not available in
ERPlora yet, it says so and does not offer to connect. If the browser does not let the window open, it asks you to
allow pop-ups; if the window closes before finishing or Meta does not finish, nothing is connected and it says why.
If Meta refuses the code (it expires after 30 seconds), the chosen number is not in the account or the account has
several and none was chosen, it says so and nothing is connected; a demo cannot connect any number. If erplora.com
does not confirm, in a moment **Your number** says whether it ended up connected.
Involved: erplora.com (the business's WhatsApp Business account), Meta

### WHATSAPP_INBOX-F02 Disconnect or reconnect the number
Status: done
Actor: owner, administrator
Screen: Settings, Inbox
Steps:
1. If WhatsApp withdrew the permission, **Your number** says "Needs reconnecting" and the inbox warns that
   nothing can be sent, with **Go to Settings** for whoever can configure.
2. **Reconnect** opens Meta's window, as when connecting (F01).
3. **Disconnect** asks first ("Disconnect the WhatsApp number?": it stops receiving and sending until it is
   connected again; the saved conversations are not touched). On confirming, **Your number** says "Not
   connected" and "WhatsApp disconnected.".
4. With the number back, the notices go away by themselves, without reloading.
In: the number's status erplora.com sends to the Hub and its answer when disconnecting.
Out: the saved conversations are not touched; notice `whatsapp_inbox.channel.disconnected`.
If it fails: if erplora.com does not answer or does not confirm, the dialog says so and the number stays as it was
(in a moment **Your number** says how it ended up); if erplora.com had no number connected for this business, it
says so and **Your number** stays "Not connected". While it is still "Needs reconnecting", **Send** says why it does
not go out ("The number needs reconnecting in Settings to send.") and a message not delivered because of it says
"Needs reconnecting" with **Reconnect**; what is saved can still be read.
Involved: erplora.com

### WHATSAPP_INBOX-F03 Receive a message in the inbox
Status: done
Actor: customer, system
Screen: Inbox
Steps:
1. The customer writes to the business's number.
2. Within a few seconds her conversation comes up at the top of the inbox with **Unread** increased and the time in
   **Last message**; if the inbox or her conversation are open, they refresh by themselves.
3. A message that arrives twice shows up once and counts once.
4. The history messages the connection brings show up with the time they were said and do not count in
   **Unread**; if one arrived empty (a history photo announced too early) and later arrives complete, it is
   completed in its place.
5. If the conversation was pending or closed, it goes back to **Open**.
6. With the plan's messages spent, the message arrives all the same: the cap only limits what is sent.
In: each message erplora.com receives from Meta for this business.
Out: one conversation per number and the message saved; notice `whatsapp_inbox.message.received`.
If it fails: if the Hub does not answer, erplora.com keeps the message and delivers it again; a number that is not a
number is not saved.
Involved: erplora.com, Customers (recognises the customer, F04)

### WHATSAPP_INBOX-F04 Recognise the customer by their number
Status: done
Actor: system
Screen: none
Steps:
1. When someone whose number is on **one** card in Customers writes, their conversation is linked to that card.
2. When a card is created or corrected with the number of someone who had already written, their conversation is
   linked to it.
3. The number is compared as a number: written with spaces, with the country prefix or with "00" in front it is the
   same person in a business in Spain, and a foreign number that keeps its zero (a landline in Italy) too; the same
   digits with another country's prefix are another person.
In: the conversation's number and the cards with that number.
Out: the conversation knows which card it belongs to. It only fills an empty link: the one a person set is
respected. A deleted card counts as empty: its conversation is left without a card and another live card with the
same number claims it.
If it fails: if two cards have the same number, it is linked to neither and the message stays saved.
Involved: Customers

### WHATSAPP_INBOX-F05 Read a conversation
Status: done
Actor: employee, manager, administrator, owner
Screen: Inbox
Steps:
1. Search by contact or phone (the phone written any way, also just a part of it) or, in **Filters**, filter by
   status, assignment or unread. The assistant names it as people say it: "Ana Lopez", "ana lópez" or "Zoé 🌸" lead
   to the same conversation if only one matches.
2. Press **Open** on the row (or tap the row).
3. The thread shows up on top of the list, from the oldest to the newest; a message with no text or attachment shows
   its type in the reader's language ("Location", "Button reply"…), and a reaction (👍) shows on the message it
   answers, without counting in **Unread**.
4. On opening it, **Unread** goes back to "—"; a message that arrives with the thread open is left read too.
5. **Close** goes back to the list.
In: the search, the filters and the chosen conversation.
Out: **Unread** at zero in that conversation; nothing else changes.
If it fails: the reason inside the panel; the list stays available. While the list loads, the table says so (never
"0 conversations").
Involved: Customers (the card's name)

### WHATSAPP_INBOX-F06 See a photo, a voice note or a document
Status: done
Actor: employee, manager, administrator, owner
Screen: Inbox
Steps:
1. A message with an attachment shows its type (Photo, Voice note, Video, Document, Sticker), the file's name and its
   text.
2. A photo or a sticker show inside their bubble, without spilling out of it; tapping them opens them full size in a
   new tab (in the installed app, in the device's browser).
3. A voice note is listened to with its player, in the same bubble.
4. A video or a document: pressing **Open the attachment** opens it in a new tab (in the installed app, in the
   device's browser).
5. Only attachments from erplora.com, over https, are shown and opened.
In: the attachment erplora.com keeps: its link, its type, its name and its caption.
Out: nothing changes in the Hub.
If it fails: if erplora.com does not deliver the photo or the voice note (also when the browser does not have the
erplora.com session of whoever signed in on the device: erplora.com only serves them to whoever has it), the bubble
says "The image could not be loaded." or "The voice note could not be loaded." and leaves **Open the attachment**;
if erplora.com no longer keeps it, the tab says so.
Involved: erplora.com (keeps the attachments)

### WHATSAPP_INBOX-F07 Assign a conversation to someone on the team
Status: done
Actor: employee (to themselves), manager, administrator, owner
Screen: Inbox
Steps:
1. Open the conversation (F05).
2. Press **Assign to me**, or choose someone on the team in **Assigned to** (manager, administrator and owner
   only), or **Remove assignment**.
3. The list and the panel show the assignment, on every open screen.
In: to whom: to me, to a person on the team or to nobody.
Out: the conversation is assigned; notice `whatsapp_inbox.conversation.assigned`.
If it fails: whoever cannot assign to others (the employee) never takes a conversation away from someone else: "This
conversation is already with {name}.", also if it was assigned to them an instant before; nor can they assign it to
someone else ("You may only assign conversations to yourself."). The manager does reassign, and their **Assign to
me** does not override anyone either.
Involved: the business's team (the people with access to the inbox)

### WHATSAPP_INBOX-F08 Answer from the WhatsApp Business app on the phone
Status: done
Actor: owner
Screen: Inbox
Steps:
1. Answer as always from the WhatsApp Business app on the phone.
2. The answer shows in the thread as a message from the business, marked "From the phone".
3. It does not count in **Unread**.
In: the echo of what the owner writes on the phone, which erplora.com sends.
Out: the message saved in its conversation; notice `whatsapp_inbox.message.received`.
If it fails: if it does not arrive, the thread does not show it; the phone still has it.
Involved: erplora.com, the WhatsApp Business app on the phone

### WHATSAPP_INBOX-F09 See who is waiting for an answer
Status: done
Actor: everyone
Screen: Inbox
Steps:
1. In **Filters**, choose **Status: Open** and **Unread** and press **Apply**: the conversations whose last message
   is the customer's are left.
2. The Hub's bell counts **WhatsApp customers waiting for an answer** and leads to the **Inbox**; it also counts the
   conversations an automatic answer could not answer, marked "Needs attention" next to the name (F20). It goes down
   by itself as soon as someone answers (from the Hub or from the phone), leaves it pending or closes it, and it does
   not show when nobody is waiting.
3. In the installed app, each message from a customer that is left unanswered alerts with a system notification,
   with their name and what they wrote; tapping it opens that conversation in the **Inbox**.
4. When sorting by any column, the rows without that datum go last, in both directions.
In: the filters and the order; the customers' messages.
Out: the filtered list and the counts (`whatsapp_inbox.conversation.summary`,
`whatsapp_inbox.conversation.count_awaiting_reply`) and the notices (`whatsapp_inbox.conversation.notices`); nothing
changes.
If it fails: the reason with **Retry**.
Involved: the bell in the top bar, the installed app's notifications

### WHATSAPP_INBOX-F10 Erase the data of a number with no card
Status: done
Actor: owner, administrator
Screen: Inbox
Steps:
1. Open the conversation of the person who asks to erase their data.
2. Press **Erase this number's data**; read "Erase this number's data?" with the number and the warning that it
   cannot be undone; press **Erase data** (or **Cancel**).
3. The panel closes, the conversation leaves the list and "The data of this number has been erased." shows.
In: the conversation and the confirmation.
Out: number, name, texts, attachments and notes emptied in the Hub at once; conversation closed and erased. If they
write again, a new conversation starts. Notice `whatsapp_inbox.conversation.erased` with the identifier (no notice of
the app carries the number, the name or what was said, so the internal history keeps nothing of theirs). After
saving, the Hub asks erplora.com to forget that number and its messages (attachments included, which live there);
until it confirms, the number is kept apart only to ask for it.
If it fails: "Could not erase the data of this number" (or the reason). If erplora.com does not confirm, it is asked
again, always for the business that erased it: on pressing it again (from whichever business) and every 5 minutes;
pressing it twice erases nothing more.
Involved: erplora.com

### WHATSAPP_INBOX-F11 Erase a customer's data from their card
Status: done
Actor: system
Screen: none (it is erased from the card, in Customers)
Steps:
1. In Customers, a card's data is erased.
2. Every conversation linked to that card is emptied and closed as in F10.
In: the notice `customer.customer.erased`.
Out: the conversations emptied and closed; notice `whatsapp_inbox.conversation.erased` for each one.
If it fails: the notice is retried; repeating it changes nothing.
Involved: Customers, erplora.com

### WHATSAPP_INBOX-F12 Merge two cards of the same customer
Status: done
Actor: system
Screen: none (they are merged from Customers)
Steps:
1. In Customers, a duplicate card is merged into another one.
2. The conversations of the absorbed card move to the one that stays, without touching anything else.
In: the notice `customer.customer.merged`.
Out: the conversations, on the card that stays.
If it fails: the notice is retried; repeating it changes nothing.
Involved: Customers

### WHATSAPP_INBOX-F13 See the month's usage and reach the cap
Status: done
Actor: everyone (notice), owner and administrator (Settings)
Screen: Inbox, Settings
Steps:
1. **Settings → This month** shows the messages sent this month against the plan's; both numbers come from
   erplora.com. If the plan does not include WhatsApp messages, it says so ("Your plan does not include WhatsApp
   messages."), never that it has no limit; from 80 % of the plan's, for example, "You have 30 of 150 messages of
   your plan left this month." with **Upgrade plan** (in the browser; it is not in the installed app); at the cap,
   "You have used all the messages of your plan this month."; before erplora.com speaks, "erplora.com has not
   reported this month’s messages yet.".
2. From 80 % of the month's messages, the inbox warns above the list, for example, "You have 30 of 150 WhatsApp
   messages of your plan left this month."; whoever can configure sees, in the browser, **Upgrade plan**, which opens
   erplora.com's plans. Below 80 %, nothing. The count moves by itself, without reloading.
3. At the cap (with a plan that includes none, from the first message), the inbox warns above the list and **Send**
   explains it instead of sending ("Your plan does not include WhatsApp messages: nothing can be sent." when the plan
   includes none); whoever can configure sees, in the browser, **Upgrade plan**, which opens erplora.com's plans.
4. What the customers write is still saved.
5. When the month changes (on the business's clock) the notice goes away even if erplora.com has not spoken yet; if
   the plan includes no messages, it stays.
In: the month's usage and cap that erplora.com sends (0: the plan includes none).
Out: the notice in the inbox and in Settings; nothing is saved.
If it fails: if erplora.com refuses a send because of the cap (the Hub's figures were behind), the message does not
reach Meta nor is it counted, it stays "Not delivered" and says so with "This month's WhatsApp messages of your plan
are spent: nothing can be sent until next month.", never as Meta's reason; if it asks to go slower, it is not the
cap: the message stays "Not sent" with **Retry**.
Involved: erplora.com, BASE-F104

### WHATSAPP_INBOX-F14 Turn on "Book appointments"
Status: discarded — **Book appointments** is not offered: after your **Approve** in **Waiting for your answer**,
Appointments refuses the appointment the assistant proposes, because an automation only books with the permission for
its own appointments, not on behalf of a professional; until Appointments accepts it, the card does not show in
Settings nor its automatic answer in the Automations gallery, and the customer who asks for an appointment on
WhatsApp is answered from the inbox (hub#514)
Actor: owner, administrator
Screen: Settings
Steps:
1. In **Settings → What do you use it for?**, the **Book appointments** card explains what it does: WhatsApp answers
   by itself, reads your agenda, offers the free slots and books or moves the appointment of the customer who writes
   when you say yes.
2. Press **Turn on** and confirm it: the card turns "On" with **Turn off**.
3. The appointments' confirmation switch appears (F16).
In: that Appointments, Customers and Automations are active in the business; the assistant is provided by
erplora.com.
Out: the appointments' automatic answer and "Tell the customer by WhatsApp when their appointment is confirmed"
turned on, with exactly the permissions they ask for; the answer asks the assistant with "Ask me first" and what it
wants to book or move waits for you first in **Waiting for your answer** (F21). Today only the notice can be turned
on, from Automations (F23).
If it fails: as in F15, naming Appointments.
Involved: APPOINTMENT-F18, APPOINTMENT-F19, CUSTOMER-F26, FLOW-F33, FLOW-F37, FLOW-F38, WHATSAPP_INBOX-F15,
WHATSAPP_INBOX-F21, WHATSAPP_INBOX-F23

### WHATSAPP_INBOX-F15 Turn on "Book a table"
Status: done
Actor: owner, administrator
Screen: Settings
Steps:
1. In **Settings → What do you use it for?**, the **Book a table** card explains what it does: "WhatsApp answers by
   itself: it checks the free tables, books the table of whoever writes once you say yes, and answers them.".
2. Press **Turn on**: "WhatsApp will answer by itself: it checks the free tables, books the table of whoever writes
   once you say yes, and answers them. Turn it on?" shows, with **Turn on** and **Not now**.
3. Press **Turn on**: the card turns "On" with **Turn off** and says "Done. Write to yourself from another phone: “I
   want a table for two tomorrow”.".
4. The confirmation switch appears (F16).
In: that Reservations, Customers and Automations are active in the business; the assistant is provided by
erplora.com.
Out: the automations "WhatsApp → table booked" and "Tell the customer by WhatsApp when their reservation is
confirmed" turned on (the first time, with exactly the permissions they ask for). They show in Automations, under
**Comes with "WhatsApp inbox"**, and pausing them there leaves this card off. "WhatsApp → table booked" asks the
assistant with "Ask me first": it can only look at how the day is going and the free tables, and book, change the
reservation or put on the waiting list whoever writes; what it wants to do waits for you first in **Waiting for your
answer** (F24).
If it fails: the card says the reason and pauses what it got to turn on; without permission, "Only an owner or an
admin can turn it on."; without Automations or without Customers, the card says "“Book a table” needs the app
Automations." (or "Customers") with **See apps** and does not offer **Turn on**; without Reservations, **What do you
use it for?** does not show.
Involved: RESERVATION-F17, CUSTOMER-F26, FLOW-F33, FLOW-F34, FLOW-F35, FLOW-F37, FLOW-F38, WHATSAPP_INBOX-F24,
WHATSAPP_INBOX-F26

### WHATSAPP_INBOX-F16 Decide whether WhatsApp bookings confirm by themselves
Status: done
Actor: owner, administrator
Screen: Settings
Steps:
1. With the **Book a table** card "On", choose below **Reservations confirm by themselves** or **I review them
   first**; each option takes its whole row and its text wraps to the next line on the phone, never cut.
2. With "I review them first", where they wait shows: "Each new reservation waits for you in Reservations with
   “Confirm”.".
3. The change is saved at once in Reservations, not in this app, and decides every new reservation, also the one
   taken by hand.
4. In the hair salon, the appointments' switch comes with **Book appointments** (F14).
In: how Reservations confirms today. Without changing it, Reservations reviews.
Out: the rule changed in Reservations; the automatic answer reads it before each booking and tells the assistant,
which tells whoever writes whether it is confirmed or the restaurant will confirm it. With "Reservations confirm by
themselves", the reservation is born confirmed and that also triggers the notice of F26.
If it fails: "Could not save how reservations confirm. Try again.", and the switch goes back to how it was.
Involved: RESERVATION-F04, WHATSAPP_INBOX-F14, WHATSAPP_INBOX-F15, WHATSAPP_INBOX-F26

### WHATSAPP_INBOX-F17 Turn off an automatic answer
Status: done
Actor: owner, administrator
Screen: Settings
Steps:
1. On the "On" card, press **Turn off**.
2. The card turns "Off" with **Turn on**; WhatsApp stops answering by itself.
In: the chosen card.
Out: the notices that go with it are paused first and the automatic answer last, so that an answer is never left on
behind a card that is off. Turning off is pausing, never deleting: in Automations it stays in its list as "Paused",
with its permissions and its history, and pausing it from there leaves this card off all the same.
If it fails: the card says the reason and is painted again with what is really still on.
Involved: FLOW-F34, WHATSAPP_INBOX-F15

### WHATSAPP_INBOX-F18 Update an automatic answer to its improved version
Status: done
Actor: owner, administrator
Screen: Settings
Steps:
1. If the app brings a better version than the one that was turned on, the card says "There is an improved version
   of this automatic answer." with **Update**.
2. Press **Update**: "The new one replaces the current one, also the changes made by hand, and it stays on or paused
   as it is." shows.
3. Confirm with **Update**: "Done: this automatic answer already works with the latest version.".
In: which automations of the card have a new version.
Out: only those automations go back to the version the app brings today, keeping whether they are on and their
history: it is the same as "Restore the factory one" in Automations.
If it fails: "This automatic answer no longer exists here: turn it on again." or "Could not update. Try again."; the
notice stays while something is left without updating.
Involved: FLOW-F35, WHATSAPP_INBOX-F15

### WHATSAPP_INBOX-F19 Choose the slot by writing instead of tapping
Status: done
Actor: customer
Screen: WhatsApp: the customer's chat
Steps:
1. The automatic answer offers them a short numbered list of times (F24; in F21, once it is offered).
2. They write `el 2`, `la segunda` or `21:30`: the list goes written in the message, with no options to tap.
3. If what they write points to exactly one of the options offered, it is checked that it is still free and proposed
   as if they had written it in full: it waits for you in **Waiting for your answer** and, with your **Approve**, it
   is booked. If it is not clear which one, the list is offered to them again.
In: their message and the last thing the business wrote them from the Hub in the 24 hours before, which is where the
list goes; never what you wrote them from the phone nor what did not reach them.
Out: the booking of the option they point to, as in F24. The list is forgotten as soon as the business writes them
again (the booking done, another question) and after 24 hours.
If it fails: with no list from the last 24 hours, or if what they write does not point to exactly one option, it is
offered to them again.
Involved: APPOINTMENT-F02, RESERVATION-F05, WHATSAPP_INBOX-F21, WHATSAPP_INBOX-F24, WHATSAPP_INBOX-F38

### WHATSAPP_INBOX-F20 When the assistant cannot answer
Status: done
Actor: system
Screen: WhatsApp: the customer's chat; Inbox
Steps:
1. If the assistant fails or says nothing, the customer gets a fixed text: "Sorry, I cannot check the reservations
   right now. Someone from the team will answer you here as soon as they can.".
2. Their conversation is marked "Needs attention", which shows next to their name in the inbox, and the bell counts
   it among the customers waiting for an answer (F09).
3. Nothing else is sent to them in that turn.
4. The mark is only set in that case and when the automatic answer does not answer because the plan's messages for
   the month were spent or the number is not connected (F13); when it is the assistant itself that answers that
   someone from the business will reply, the conversation is not marked.
5. The mark is removed as soon as someone from the business answers them (from the inbox or from the phone) or
   leaves it pending or closed.
In: what the assistant answered in that turn.
Out: an apology and the attention mark (`whatsapp_inbox.conversation.flagged`).
If it fails: if the mark cannot be set, the apology goes out all the same and the message stays unread in the inbox.
Involved: WHATSAPP_INBOX-F09, WHATSAPP_INBOX-F13, WHATSAPP_INBOX-F24

### WHATSAPP_INBOX-F21 The customer asks for an appointment on WhatsApp
Status: discarded — not offered: after your **Approve** in **Waiting for your answer**, Appointments refuses the
appointment the assistant proposes, because an automation only books with the permission for its own appointments,
not on behalf of a professional; that is why **Book appointments** (F14) does not show, and today the customer is
answered from the inbox and the appointment is booked by hand in the Agenda (hub#514)
Actor: customer, owner
Screen: WhatsApp: the customer's chat; Automations
Steps:
1. The customer writes, for example, `¿Tenéis hueco mañana por la tarde para un corte?`.
2. She gets a fixed acknowledgement at once: that the agenda is being checked and she will be answered right now.
3. If she has no card, one is created for her with WhatsApp as its source.
4. The assistant looks at the slots that are really free. If her message sets service, day and time and it is free,
   it proposes booking it with the professional who works at that time; if not, it answers with a short numbered list
   of slots (F19). The assistant never chooses the time for her.
5. The appointment it wants to book waits for you in Automations, in **Waiting for your answer**, with whom it is
   for; with **Approve** it is booked and she gets the answer: that the appointment is booked (day, time and
   professional) if the salon confirms by itself, or that she has been put down and the salon will confirm it, as
   F16 says. The appointment is in the Agenda.
6. With **No**, or if nobody answers within 72 hours, nothing is booked and she is left with the acknowledgement:
   answer her from the inbox.
In: the written message (not the history, nor the owner's answers from the phone, nor photos without text).
Out: a new card if needed (Customers), the conversation linked to the card, the proposal in **Waiting for your
answer** and, after the yes, an appointment confirmed or pending (Appointments, `appointment.appointment.created`)
and an answer by WhatsApp. The services and their length come from the Services catalogue; the free times, from
Appointments.
If it fails: F20; with no slot, she is told why and offered others. With the plan's messages for the month spent she
gets nothing (no acknowledgement, no answer, no appointment) and her message stays in the inbox with "Needs
attention" (F13).
Involved: APPOINTMENT-F02, APPOINTMENT-F18, CUSTOMER-F10, CUSTOMER-F26, FLOW-F37, FLOW-F38, WHATSAPP_INBOX-F16,
WHATSAPP_INBOX-F19, WHATSAPP_INBOX-F20

### WHATSAPP_INBOX-F22 The customer cancels or moves her appointment on WhatsApp
Status: discarded — not offered, for the same reason as F21: Appointments does not accept an automation's changes,
and cancelling an appointment cannot be entrusted to it either (cancelling a table can: F25); today it is cancelled
or moved by hand from the Agenda (hub#514)
Actor: customer, owner
Screen: WhatsApp: the customer's chat; Automations
Steps:
1. The customer writes `no puedo ir` or `¿me la cambias al jueves?`.
2. Her latest appointment is looked up by her number.
3. Cancel: it is cancelled with the salon's rules (whether it is allowed and how far ahead); outside the deadline she
   is told and the appointment stays.
4. Move: she is offered slots and the change of the same appointment, with the same professional and the same
   service, waits for you in **Waiting for your answer**; with **Approve** it is moved.
5. She gets the answer with what happened.
In: the message and that customer's latest appointment.
Out: once it is offered, the appointment cancelled or moved in Appointments as if she cancelled or moved it herself
(`appointment.appointment.cancelled`, `appointment.appointment.rescheduled`); never someone else's.
If it fails: F20; if Appointments refuses it, it is explained to her. With the plan's messages for the month spent,
nothing is cancelled or moved, she gets no answer and the conversation is left with "Needs attention" (F13).
Involved: APPOINTMENT-F04, APPOINTMENT-F06, FLOW-F38, WHATSAPP_INBOX-F20

### WHATSAPP_INBOX-F23 The customer gets the notice when the salon confirms
Status: done
Actor: owner, manager, customer
Screen: Automations; WhatsApp: the customer's chat
Steps:
1. In Automations, below the gallery, under **Comes with "WhatsApp inbox"**, turn on "Tell the customer by WhatsApp
   when their appointment is confirmed" (FLOW-F33). To notify after the 24 hours, create in **Settings** the Utility
   template `appointment_confirmed` with four data (the day, the time, the service and the professional) and wait for
   Meta to approve it (F29).
2. With "I review them first", the person in charge presses **Confirm** in the Agenda.
3. If the customer has a WhatsApp conversation with the business, she gets "Confirmed! We are expecting you on {day}
   at {time} for your {service} with {professional}.", with the day and the time in the business's language and on
   its clock.
4. The conversation is looked up with the phone on the customer's card, and only the exact international number of a
   conversation of this business counts: an incomplete phone notifies nobody, and the notice never goes out to
   someone else's conversation.
5. Outside the 24 hours since the customer's last message, the notice goes out with the approved Utility template,
   because WhatsApp does not let free text through.
6. The notice goes out with any confirmation of an appointment with a conversation, also that of an appointment born
   already confirmed because **Confirm bookings made by the customer automatically** is on in Appointments
   (APPOINTMENT-F18).
In: the confirmed appointment (Appointments), the customer's card (Customers) and the conversation whose number is
exactly the one on her card.
Out: a WhatsApp to the customer, which shows in her conversation in the inbox (`whatsapp_inbox.message.sent`); the
same notice never goes out twice.
If it fails: the reason stays in the automation's history and nothing shows in the Agenda. With no phone on the card
or no conversation with that number, the automation stops at its step, without an error; outside the 24 hours without
the approved template, with the number not connected or with the month's messages spent, it stops with the reason.
What Meta refuses later shows in the conversation ("Not delivered").
Involved: APPOINTMENT-F03, APPOINTMENT-F18, CUSTOMER-F11, FLOW-F31, FLOW-F33, WHATSAPP_INBOX-F14,
WHATSAPP_INBOX-F29, WHATSAPP_INBOX-F33

### WHATSAPP_INBOX-F24 The guest asks for a table on WhatsApp
Status: done
Actor: customer, owner
Screen: WhatsApp: the customer's chat; Automations
Steps:
1. The guest writes, for example, `Mesa para 4 el sábado a las 21`.
2. They get a fixed acknowledgement at once: "Thanks for writing! Let me check the reservations book and I will come
   straight back to you.".
3. If they have no card, one is created for them with WhatsApp as its source.
4. It is checked whether that day opens, the slots and the free tables; the time and how many they are are said by
   the guest, never by the assistant.
5. If there is room, the assistant proposes booking it; if not, it offers them other times in a short numbered list
   (F19) or to put them on the waiting list.
6. The booking (or the entry on the waiting list) waits for you in Automations, in **Waiting for your answer**; with
   **Approve** it is made and they get the answer: that the table is booked, or that they have been put down and the
   restaurant will confirm it, as F16 says. With **No**, or if nobody answers within 72 hours, nothing is booked and
   they are left with the acknowledgement.
In: the written message and the card of their phone if they already have one.
Out: a reservation confirmed or pending, or an entry on the waiting list (Reservations,
`reservation.reservation.created`), with the phone they write from and the name they give in the message (if they
give none, their WhatsApp one), linked to their card or, if their phone has none, to a new one with WhatsApp as its
source (Customers), and an answer by WhatsApp; never on someone else's card even if the message names it, nor with
another phone even if the message gives it: the card and the phone are set by the automation and the assistant
cannot change them.
If it fails: F20; with no places or with too many guests, it is explained to them. With the plan's messages for the
month spent they get nothing (no acknowledgement, no answer, no reservation) and their message stays in the inbox
with "Needs attention" (F13).
Involved: RESERVATION-F05, RESERVATION-F14, RESERVATION-F17, CUSTOMER-F10, FLOW-F37, FLOW-F38,
WHATSAPP_INBOX-F16, WHATSAPP_INBOX-F19, WHATSAPP_INBOX-F20

### WHATSAPP_INBOX-F25 The guest cancels or changes their table on WhatsApp
Status: done
Actor: customer, owner
Screen: WhatsApp: the customer's chat; Automations
Steps:
1. The guest writes `no podemos ir` or `¿podemos pasarla a las 22?`.
2. They get at once the same acknowledgement as when asking for a table (F24), and their latest reservation is looked
   up by their number.
3. The change or the cancellation of that same reservation waits for you in Automations, in **Waiting for your
   answer**, with the reservation named by its guest, its day and its time. A cancellation can only be approved by
   whoever can cancel reservations.
4. With **Approve** it is done with the restaurant's rules and they are answered with what happened. With **No**, or
   if nobody answers within 72 hours, nothing is changed or cancelled and they are left with the acknowledgement.
In: the message and that guest's latest reservation.
Out: the reservation changed (`reservation.reservation.updated`) or cancelled
(`reservation.reservation.status_changed`) in Reservations, and the answer by WhatsApp; never someone else's: the
change and the cancellation always go on behalf of the card of their number, which the automation sets and the
assistant cannot change or remove, so Reservations refuses that of a reservation that is not theirs even if it is
approved, and the card in **Waiting for your answer** says whose reservation it is before your **Approve**.
If it fails: F20; if Reservations refuses it, it is explained to them. With the plan's messages for the month spent,
nothing is changed or cancelled, they get no answer and the conversation is left with "Needs attention" (F13).
Involved: RESERVATION-F09, RESERVATION-F18, FLOW-F28, FLOW-F38, WHATSAPP_INBOX-F20, WHATSAPP_INBOX-F24

### WHATSAPP_INBOX-F26 The guest gets the notice when the restaurant confirms
Status: done
Actor: owner, manager, customer
Screen: Automations; Reservations; WhatsApp: the customer's chat
Steps:
1. In Automations, below the gallery, under **Comes with "WhatsApp inbox"**, turn on "Tell the customer by WhatsApp
   when their reservation is confirmed" (FLOW-F33). To notify after the 24 hours, create in **Settings** the Utility
   template `reservation_confirmed` with three data (the day, the time and the guests) and wait for Meta to approve it
   (F29).
2. With "Confirm new reservations automatically" off, the person in charge presses "Confirm" on the Pending
   reservation, in Reservations.
3. If the guest has a WhatsApp conversation with the business, they get "Confirmed! We are expecting you on {day} at
   {time}, table for {guests}.", with the day and the time in the business's language and on its clock.
4. The conversation is looked up with the reservation's phone (the one of their conversation, if the reservation came
   by WhatsApp), and only the exact international number of a conversation of this business counts: an incomplete
   phone notifies nobody, and the notice never goes out to someone else's conversation.
5. Outside the 24 hours since the guest's last message, the notice goes out with the approved Utility template,
   because WhatsApp does not let free text through.
6. The notice goes out with any confirmation of a reservation with a conversation, also that of a reservation born
   already confirmed because "Confirm new reservations automatically" is on. Seating it, completing it, cancelling it
   or marking it as a no-show do not notify.
In: the confirmed reservation (Reservations) and the conversation whose number is exactly the reservation's.
Out: a WhatsApp to the guest, which shows in their conversation in the inbox (`whatsapp_inbox.message.sent`); the
same notice never goes out twice.
If it fails: the reason stays in the automation's history and nothing shows in Reservations. With no phone on the
reservation or no conversation with that number, the automation stops at its step, without an error; outside the
24 hours without the approved template, with the number not connected or with the month's messages spent, it stops
with the reason. What Meta refuses later shows in the conversation ("Not delivered"). A business without Reservations
does not see this automation.
Involved: RESERVATION-F07, RESERVATION-F19, FLOW-F31, FLOW-F33, WHATSAPP_INBOX-F15, WHATSAPP_INBOX-F29,
WHATSAPP_INBOX-F33

### WHATSAPP_INBOX-F27 See the templates and what Meta says about each one
Status: done
Actor: owner, administrator
Screen: Settings
Steps:
1. **Settings → Meta templates** lists the templates with their status in Meta; a rejected one shows "Meta's reason:
   …".
2. When Meta changes its verdict, the table changes by itself.
In: the list erplora.com sends to the Hub each time it changes.
Out: nothing; a template Meta no longer lists stays "Deleted in WhatsApp Manager" and cannot be sent.
If it fails: if the table does not load, the reason with **Retry**; if erplora.com does not send the list, the last
one it sent stays.
Involved: erplora.com, Meta

### WHATSAPP_INBOX-F28 Bring in the templates created in WhatsApp Manager
Status: done
Actor: system
Screen: Settings
Steps:
1. The business creates a template in WhatsApp Manager.
2. It shows in **Settings → Meta templates** as soon as erplora.com sends it, with its text, its variables, its
   buttons and its status.
3. The ones the Hub cannot fill in when sending (a header with a location or with a variable; variables with a name
   instead of a number; verification codes) show with their status and "Can't be sent or edited here: it is managed in
   WhatsApp Manager.", but are not offered for sending nor edited here; they can be deleted.
4. The ones with a photo, a video or a document in the header are sent from the inbox choosing the file (F33), but
   are edited there: they say "Edited in WhatsApp Manager.".
In: the list of templates erplora.com brings from Meta.
Out: each template saved as Meta has it.
If it fails: it never overwrites a Hub template still on its way to Meta nor brings back one deleted here.
Involved: erplora.com, WhatsApp Manager

### WHATSAPP_INBOX-F29 Create a template and send it for review
Status: done
Actor: owner, administrator
Screen: Settings, Template (sheet)
Steps:
1. In **Settings → Meta templates**, press **Add template**.
2. Write the name, choose language and category (Utility or Marketing) and write the text with `{{1}}`, `{{2}}`…
   where the variables go, with an example of each one; if you want, header, footer and buttons (quick replies
   together, up to two links and one call; ten at most).
3. For a header with a photo, a video or a document, choose "Photo", "Video" or "Document" in **Header type** and
   press **Choose file** (a JPEG or PNG photo up to 5 MB, an MP4 video up to 16 MB or a PDF up to 25 MB): it is saved
   at once in the business's files and the sheet shows its thumbnail (the photo, or the video's first frame with the
   play sign; a document, its icon) next to its name and its size. Meta reviews the template with that file; without
   it, it cannot be sent for review.
4. Press **Send to Meta for review**: the template shows in the list as "Not sent to Meta" with "Sending to Meta…"
   and turns "In review" as soon as Meta receives it. One with a file in its header names its file ("Photo: …").
5. When Meta decides, it turns by itself to "Approved" (it can be sent now, F33) or to "Rejected" with its reason.
In: name, language, category, header (a text, or a photo, a video or a document), text, examples, footer, buttons and
a saving key (the same one when retrying).
Out: the header's file saved in the business's files when it is chosen (notice
`whatsapp_inbox.template_sample.uploaded`); the template saved and, after saving, handed to erplora.com with its file
for it to register it in Meta; notice `whatsapp_inbox.template.created`.
If it fails: what Meta would not accept is said under its field (a name with capital letters or spaces, variables not
numbered in order or with a name, a variable without an example, a variable in the header or the footer, more than
60 characters in the header or the footer, mixed buttons or too many); the same name in the same language: "There is
already a template “…” in that language.". A file that is not of the chosen type is said underneath and not saved
("Choose a JPEG or PNG photo.", "Choose an MP4 video.", "Choose a PDF document."), and one that weighs too much too
("This file weighs more than 5 MB: choose a lighter one."); one that does not fit in the plan's space for files (the
business's files and the headers' count together), as in Files: "No space is left for that file: your plan includes
{space}."; if it could not be uploaded: "The file could not be uploaded. Try again.". If the photo or the video cannot
be shown, the sheet says so under its name ("The photo could not be shown.", "The video could not be shown.") and it
can still be sent. If, when it is handed over, the file is no longer in the business's files, the list says "Not
accepted: The header's file is no longer in the business's files: choose it again with Edit.". If Meta does not
accept it or asks to wait, the list says "Not accepted: …" with Meta's reason ("Meta did not answer. Try again in a
few minutes." when Meta does not answer: it never blames ERPlora) and it is corrected with **Edit** or repeated with
**Send to Meta again**. If erplora.com does not answer, the list says so and **Send to Meta again** hands it over
again with the same key (also by itself, every 5 minutes): it is never registered twice. With the month spent it can
be created all the same.
Involved: erplora.com, Meta

### WHATSAPP_INBOX-F30 Edit a template
Status: done
Actor: owner, administrator
Screen: Settings, Template (sheet)
Steps:
1. In **Settings → Meta templates**, press **Edit** on the row (or tap it).
2. Change the text, the examples, the header (also its file, which the sheet shows with its thumbnail, with **Change
   file**), the footer or the buttons (the category, only if Meta rejected it; the name and the language do not
   change) and press **Save and send to Meta**.
3. An approved template keeps being sent as Meta approved it while the change is on its way ("Until Meta approves the
   changes, the approved one keeps being sent."); as soon as Meta receives it, it turns "In review" with the new text.
In: the change and a saving key (the same one when retrying).
Out: the change kept apart until Meta receives it, so that its verdict never falls on a text changed afterwards;
notice `whatsapp_inbox.template.updated`.
If it fails: a template in review is not changed ("Meta is reviewing this template: wait for its verdict to change
it."), nor one on its way ("This template is on its way to Meta: wait a moment."); the one with something the Hub
cannot write, or disabled or deleted in WhatsApp Manager, is changed there ("This template is changed in WhatsApp
Manager: the Hub cannot change it."); the category of an approved one: "Meta only lets you change the category of a
template it rejected.". If the change does not reach Meta, the row says "Changes not sent: …" with **Send to Meta
again**; the rest, as in F29.
Involved: erplora.com, Meta

### WHATSAPP_INBOX-F31 Delete a template
Status: done
Actor: owner, administrator
Screen: Settings
Steps:
1. In **Settings → Meta templates**, press **Delete** on the row.
2. Read "Delete this template?" with its name and its language and the warning "An approved template takes days to be
   approved again."; press **Delete template** (or **Cancel**).
3. It can no longer be sent. It leaves the list as soon as Meta confirms; meanwhile the row says "Being deleted at
   Meta".
In: the template.
Out: the template deleted here and, after saving, the deletion of that template in that language asked of
erplora.com (one Meta never had is deleted without asking); notice `whatsapp_inbox.template.deleted`.
If it fails: if Meta no longer had it, it counts as deleted; if erplora.com or Meta do not answer, the row says "Being
deleted at Meta" with the reason and **Send to Meta again** asks for it again. The list Meta sends never brings it
back, even if it keeps listing it until deleting it; a new one with the same name can be created.
Involved: erplora.com, Meta

### WHATSAPP_INBOX-F32 Answer from the inbox
Status: done
Actor: employee, manager, administrator, owner
Screen: Inbox
Steps:
1. Open the conversation (F05), tab **Reply**.
2. Write and press **Send** (or Ctrl+Enter).
3. The message shows in the thread, on the right, "Sending…"; **Unread** stays at zero. As soon as erplora.com
   accepts it, it turns "Sent".
In: the text (up to 4096 characters) and a message key (the screen and the assistant generate it; the same one when
retrying).
Out: the message saved in the queue and, after saving, handed to erplora.com; notices `whatsapp_inbox.message.sent`
and, when erplora.com answers, `whatsapp_inbox.message.status_changed`.
If it fails: if it cannot even be saved, the box keeps the text with the reason: more than 24 hours have passed since
the customer's last message ("More than 24 hours have passed…"), or the number is not connected, the month is spent
or the Hub does not reach erplora.com (the box says so before you write). If erplora.com refuses it (number blocked,
the month's cap…), the bubble says "Not delivered" and its reason; if erplora.com does not have the business's number
connected, the Hub says so in its own words ("WhatsApp is not connected: connect the number in Settings to send."),
never as Meta's reason. If erplora.com does not answer, does not confirm or asks to go slower, the bubble says "Not
sent" with **Retry**, which hands it over again with the same key: it never goes out twice. It always goes out
through the number of the business that sent it, even if someone else retries it from the shared inbox of phase 1.
Involved: erplora.com, Meta

### WHATSAPP_INBOX-F33 Send a template
Status: done
Actor: employee, manager, administrator, owner
Screen: Inbox
Steps:
1. In **Reply**, press **Template**: "Send a template" opens with the **approved** templates the Hub can fill in
   (name, language, category and text).
2. Choose one and fill in its variables (`{{1}}`, `{{2}}`…); the preview shows the final text.
3. If its header carries a photo, a video or a document, the one made here already brings its own (its thumbnail,
   its name and its size, with **Change file**) and the one made in WhatsApp Manager asks for **Choose file** ("No
   file chosen"): it is saved at once in the business's files and its thumbnail shows, with what it accepts ("JPEG or
   PNG, up to 5 MB.") and "The customer receives the template with this file."; a photo or a video that cannot be
   shown says so as in F29.
4. Press **Send**: the message shows in the thread as in F32; the one with a file in its header names it ("Photo ·
   carta.jpg").
Also through the assistant or the API to a number that has not written yet ("send the reminder template to this
number"): its conversation is created. An automation does not use this send but a narrower one, which never
creates a conversation: it only writes to the one that already exists with the exact international number (FLOW-F31,
F23). A number written by hand belongs to the business's country unless it carries its prefix.
In: the template (name and language), its variables, its header's file (if it carries a photo, a video or a document:
its own or the chosen one), a message key and the conversation or the number. An automation only sends the ones that
ask for nothing but their variables: those with a file in the header, with their own.
Out: the message saved and handed over as in F32; notice `whatsapp_inbox.message.sent`.
If it fails: a **Marketing** template is only sent to a customer with a card and with the marketing consent by
WhatsApp given in Customers ("This customer has not agreed to receive marketing by WhatsApp."); a template not
approved, deleted or that the Hub cannot fill in cannot be chosen; missing variables: "Fill in every variable of the
template."; an incomplete number: "This is not a phone number." and nothing is saved; without its header's file:
"Choose the header's file: the template is sent with it."; a file of the wrong type or that weighs too much is said
underneath ("Choose a JPEG or PNG photo.") and not saved, just like one that does not fit in the plan's space (F29).
If, when it is handed over, the file is no longer in the business's files, the message says "The header's file is no
longer in the business's files: send the template again choosing its file."; if Meta does not take the file or does
not answer, "Meta did not answer. Try again in a few minutes." and it is handed over again with the same key (it
never blames ERPlora); the rest, as in F32.
Involved: Customers (the marketing consent), erplora.com, Meta

### WHATSAPP_INBOX-F34 Know whether a message got there and was read
Status: done
Actor: everyone
Screen: Inbox
Steps:
1. Each message sent carries its status: **Sending…**, **Sent**, **Delivered**, **Read**, **Not delivered** (with
   Meta's or erplora.com's reason) or **Not sent** (with **Retry**). If it was not delivered because WhatsApp
   withdrew the number's permission, it says "Needs reconnecting" with **Reconnect**, which leads to **Your number**
   in **Settings** (only whoever can configure; without **Retry**, which would fail again); with the number back, the
   message stays with "WhatsApp's permission for your number had expired.".
2. It changes by itself, without reloading, when erplora.com tells it.
In: each status erplora.com receives from Meta for a message of the Hub.
Out: the status only moves forward (a "Delivered" that arrives late does not undo a "Read"); a status that arrives
before erplora.com's answer is matched with the message by its key and is not lost; notice
`whatsapp_inbox.message.status_changed`.
If it fails: a status of a message the Hub does not know is ignored without an error.
Involved: erplora.com, Meta

### WHATSAPP_INBOX-F35 Change a conversation's status
Status: done
Actor: employee, manager, administrator, owner
Screen: Inbox
Steps:
1. In the panel, press **Open**, **Pending** (waiting for the customer) or **Closed** (solved).
2. The list shows it at once on every screen.
3. If the customer writes again, the conversation goes back to **Open** by itself.
In: the chosen status.
Out: notice `whatsapp_inbox.conversation.status_changed`.
If it fails: the reason inside the panel; the status does not change.
Involved: no other app

### WHATSAPP_INBOX-F36 Leave an internal note
Status: done
Actor: employee, manager, administrator, owner
Screen: Inbox
Steps:
1. In the panel, tab **Internal note**: write and press **Add note**.
2. The note shows in the thread, in yellow, with its author and its time; the customer never sees it.
3. Whoever wrote it, the manager, the administrator and the owner can **Delete** it.
In: the note's text.
Out: notice `whatsapp_inbox.note.added` / `whatsapp_inbox.note.deleted`.
If it fails: the reason in the panel; the employee does not delete someone else's note.
Involved: no other app

### WHATSAPP_INBOX-F37 Link the conversation to a card or create the card
Status: done
Actor: employee, manager, administrator, owner
Screen: Inbox
Steps:
1. In the panel with no card, **Link to a card** searches Customers by name, phone or email; choosing one links it.
2. Or **Create card**: it creates a card in Customers with the WhatsApp name (or the number) and the number, with
   "WhatsApp" as its source, and links it.
3. With a card, **View card** leads to it and **Unlink** removes it.
In: the chosen card, or nothing to create it.
Out: notice `whatsapp_inbox.conversation.customer_linked`.
If it fails: Customers' reasons (for example, a number that is not valid).
Involved: Customers

### WHATSAPP_INBOX-F38 Know which question what the customer taps answers
Status: done
Actor: customer, system
Screen: Inbox
Steps:
1. The business sends a template with quick replies ("Yes", "No") or a message with buttons.
2. The customer taps an option: in the thread it shows with the option's text, as a button reply.
3. The app waiting for that answer (an appointment reminder) knows which of its messages it answers, even if there
   are two open questions.
In: the option tapped (its identifier and its text) and the message it answers, which erplora.com sends or the Hub
reads from what Meta sent.
Out: the option saved with the message; notice `whatsapp_inbox.message.received` with the Hub's message it answers and
the option, empty (never missing) when it does not answer anything this Hub sent.
If it fails: if it answers a message this Hub did not send (or quotes one of its own), the notice points to none.
Involved: erplora.com; Appointments and Reservations, when they notify by WhatsApp

## Services: what goes in and what comes out

### What it offers: reads (they read, they change nothing)

| Operation | What it returns |
|---|---|
| `whatsapp_inbox.conversation.list` | Conversations, with search by contact or phone and filters by status, assignment, unread and card |
| `whatsapp_inbox.conversation.detail` | A conversation (by id, number or name) with its card, its assignment and whether the 24 h window is open |
| `whatsapp_inbox.conversation.by_phone` | The conversation of an exact number (international format), or none: to notify from another app |
| `whatsapp_inbox.conversation.summary` | Open, unread and waiting for an answer, and whether the month's cap is spent |
| `whatsapp_inbox.conversation.count_awaiting_reply` | How many customers are waiting for an answer (open with the customer's last message or marked "Needs attention"): the bell counts it |
| `whatsapp_inbox.conversation.notices` | The customers waiting for an answer, from the newest to the oldest, with who, what they last wrote and when: the device's notifications |
| `whatsapp_inbox.message.list` | A conversation's messages, from the newest to the oldest |
| `whatsapp_inbox.message.get` | A message by its id (the one that started an automation): what it says, who and when, the exact international number of its conversation, what to call the customer, whether they can be written to now and the last thing the business wrote them from the Hub in the 24 hours before (the list they may be answering, F19) |
| `whatsapp_inbox.note.list` | A conversation's internal notes |
| `whatsapp_inbox.template.list` | The templates (filters by status, category, language, name and whether they can be sent), with their way to Meta |
| `whatsapp_inbox.template_sample.detail` | A header's file by its id, as it was returned when saved (name, photo, video or document and size); only the asking business's |
| `whatsapp_inbox.channel.get` | The number's status and the month's usage |
| `whatsapp_inbox.agent.list` | The business's people a conversation can be assigned to |

### What it offers: actions (they change data)

| Operation | What it does |
|---|---|
| `whatsapp_inbox.message.send` | Saves and hands over a text (within 24 h) or an approved template, to a conversation or to a number; asks for a key per message |
| `whatsapp_inbox.message.retry` | Hands over again a message that did not go out, with the same key |
| `whatsapp_inbox.message.notify` | The send an automation can have (FLOW-F31): only to the live conversation of the exact international number, never a new one; text within 24 h and the approved template outside them; same way out as `message.send` |
| `whatsapp_inbox.conversation.mark_read` | Leaves **Unread** at zero |
| `whatsapp_inbox.conversation.assign` | Assigns or unassigns; "Assign to me" does not override someone else |
| `whatsapp_inbox.conversation.set_status` | Open, pending or closed |
| `whatsapp_inbox.conversation.link_customer` | Links to a card, creates the card or unlinks |
| `whatsapp_inbox.conversation.erase` | Erases a number's data (irreversible) |
| `whatsapp_inbox.conversation.flag` | Marks an open conversation "Needs attention" (the automatic answer could not answer, F20); it goes away by itself when answering, leaving it pending or closing it |
| `whatsapp_inbox.note.add` / `whatsapp_inbox.note.delete` | Internal notes |
| `whatsapp_inbox.template_sample.upload` | Saves the file of a header with a photo, a video or a document in the business's files and returns its id |
| `whatsapp_inbox.template.create` | Creates a template and hands it to erplora.com for Meta; asks for a key per save |
| `whatsapp_inbox.template.update` | Changes a template; the approved one keeps being sent until Meta receives the change |
| `whatsapp_inbox.template.retry` | Hands over again the template (or its deletion) that did not reach Meta; a rejection goes with a new key |
| `whatsapp_inbox.template.delete` | Deletes a template here and in Meta (irreversible) |
| `whatsapp_inbox.channel.prepare` | Asks erplora.com what to open Meta's window with and says whether it can be opened yet (it saves nothing; it is an action because it waits for erplora.com outside any transaction) |
| `whatsapp_inbox.channel.connect` | Connects the number Meta's window chose, with its one-time code just as it arrived |
| `whatsapp_inbox.channel.disconnect` | Disconnects the business's number; the conversations stay |

The system's (with no public route; only erplora.com through `/internal`, the deliveries, the worker and the
reactions): `whatsapp_inbox.message.receive`, `whatsapp_inbox.message.update_status`,
`whatsapp_inbox.channel.sync`; the deliveries (`whatsapp_inbox.message.claim_delivery`,
`whatsapp_inbox.message.record_delivery`, `whatsapp_inbox.conversation.claim_erasure`,
`whatsapp_inbox.conversation.record_erasure`, `whatsapp_inbox.template.claim_submit`,
`whatsapp_inbox.template.record_submit`, `whatsapp_inbox.template.claim_delete`,
`whatsapp_inbox.template.record_delete`); the worker's task `whatsapp_inbox.delivery.resume`; and
the reactions to Customers (`whatsapp_inbox.conversation.claim_for_customer`,
`whatsapp_inbox.conversation.move_customer`, `whatsapp_inbox.conversation.release_customer`,
`whatsapp_inbox.conversation.erase_for_customer`).

### What it announces

`whatsapp_inbox.message.received` (with the Hub's message it answers and the option tapped, F38),
`whatsapp_inbox.message.sent`, `whatsapp_inbox.message.status_changed`, `whatsapp_inbox.conversation.read`,
`whatsapp_inbox.conversation.assigned`, `whatsapp_inbox.conversation.status_changed`,
`whatsapp_inbox.conversation.customer_linked`, `whatsapp_inbox.conversation.flagged`, `whatsapp_inbox.conversation.erased`,
`whatsapp_inbox.note.added`, `whatsapp_inbox.note.deleted`, `whatsapp_inbox.channel.synced`,
`whatsapp_inbox.channel.connected`, `whatsapp_inbox.channel.disconnected`, `whatsapp_inbox.template.created`, `whatsapp_inbox.template.updated`, `whatsapp_inbox.template.deleted`,
`whatsapp_inbox.template_sample.uploaded`.
They carry identifiers, never a number, a name or a text of the conversation.

### What it reacts to and what it needs from other apps

- **Customers** (required): `customer.customer.created` and `customer.customer.updated` link the conversations with no
  card of that number (F04); `customer.customer.merged` moves them to the card that stays (F12);
  `customer.customer.deleted` leaves them without a card and another live card of the number claims them;
  `customer.customer.erased` erases them (F11). It reads the cards by number and the marketing consent by WhatsApp; it
  creates cards only with `customer.customer.create`.

### Who uses it

- **Automations**: this app's recipe "Tell the customer by WhatsApp when their appointment is confirmed" (F23) reads
  the card, looks up the conversation with `conversation.by_phone` and notifies with `message.notify`; the business's
  automations use the same `message.notify` (FLOW-F31). To know what the customer answered, the notice
  `message.received` (F38). The automatic answer "WhatsApp → table booked" (F24) starts on `message.received`, reads
  the message with `message.get` and marks the conversation with `conversation.flag` (F20).
- The **assistant**: every operation, with human references ("answer Ana", "assign Ana's conversation to Luis", "send
  the reminder template to the number I dictate", "create a reminder template").

### Who can do what

| Permission | Owner | Administrator | Manager | Employee |
|---|---|---|---|---|
| `whatsapp_inbox.view` (read, mark as read) | yes | yes | yes | yes |
| `whatsapp_inbox.reply` (send, also choosing the file of a template's header; notify an exact number, retry, notes, status, card, assign a free one to yourself) | yes | yes | yes | yes |
| `whatsapp_inbox.assign` (assign to someone else, take it from someone else, delete other people's notes) | yes | yes | yes | no |
| `whatsapp_inbox.configure` (Settings; connect, reconnect and disconnect the number; create, edit, resend and delete templates) | yes | yes | no | no |
| `whatsapp_inbox.erase` (erase a number's data) | yes | yes | no | no |

The system's operations ask for `whatsapp_inbox.receive`, which no role has.
