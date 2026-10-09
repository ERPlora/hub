//! Real `host.notify` transport — every live channel leaves through the SaaS proxy
//! (ADR-0012 + ADR-0283 §5 K4, `architecture/hub/flows.md` §5).
//!
//! `host.notify` had a real mechanism and a fake exit: the outbox relay, its retries, its
//! dead-letter and the three gates of hub#240 all worked, and then handed the message to a
//! [`MockTransport`] that filed it in memory. Nothing a module "sent" ever left the hub.
//!
//! This is the exit. Both channels the SaaS proxies go out with the hub's **machine** credential
//! (`X-Hub-Token` + `X-Hub-Id`, `IsHubMachine`) — the sender is the outbox relay, with no user
//! logged in (ADR-0003):
//!
//!  - `POST /api/v1/hub/device/notify/email/` → SES/SMTP. `From` is ERPlora's verified sender and
//!    the business `Reply-To` is resolved SERVER-SIDE; neither travels in this body, because a
//!    free `Reply-To` would turn mail signed by ERPlora into phishing (saas#1347).
//!  - `POST /api/v1/hub/device/notify/whatsapp/` → Meta Graph with the hub's own Fernet-stored
//!    token, with the quota charged before the money is spent.
//!
//! **The hub never holds a Meta/SES credential** — the same rule as the LLM proxy. That is also
//! why [`Routing`] is not honoured here: ADR-0012 sent "tenant" channels to a local encrypted
//! secret, but no such secret store exists and flows.md §5 settled that everything goes through
//! the proxy. A tenant's own SMTP is separate work, and until it exists honouring `Routing` would
//! only mean refusing to send.
//!
//! ## What the intent carries — and what it does not
//!
//! [`NotifyIntent`] is `{channel, to, template, vars}`, and there is **no template catalogue**:
//! not in the hub, and not behind either endpoint. So `template` is a NAME and the copy travels
//! in `vars`:
//!
//!  - **email** — `subject` = `vars.subject`, falling back to the template name; `text` =
//!    `vars.text`/`vars.body` (**required**); `html` = `vars.html` (optional).
//!  - **whatsapp** — a non-empty `template` sends Meta's template OBJECT, which is where the real
//!    WhatsApp catalogue lives (templates are registered and approved per WABA). An empty one
//!    sends `vars.text`/`vars.body` as free text, which Meta only accepts inside its 24 h service
//!    window — its rule to enforce, not ours.
//!  - **sms** — ADR-0012 lists it, the SaaS does not proxy it, and the hub holds no provider
//!    credential of its own. Refused with a clear reason.
//!
//! The transport does **not** invent copy: an intent with nothing to say is refused here rather
//! than delivered as a blank email signed by ERPlora.

use std::sync::Arc;

use async_trait::async_trait;
use cloud_client::{Auth, CloudClient, PreparedRequest};
use erplora_runtime::errors::{Result, RuntimeError};
use erplora_runtime::host_notify::{
    button_url_index, Channel, MockTransport, NotifyIntent, NotifyTransport, Routing, SendOutcome,
    BUTTON_URL_VAR_PREFIX, HEADER_DOCUMENT_FILENAME_VAR, HEADER_VARS,
};
use serde_json::{json, Value};

use crate::state::{HubId, MachineToken};

/// Env var that swaps the real proxy transport for the in-memory [`MockTransport`].
pub const TRANSPORT_ENV: &str = "HUB_NOTIFY_TRANSPORT";

/// The only value of [`TRANSPORT_ENV`] that picks the mock.
const MOCK_TRANSPORT: &str = "mock";

/// Keys of `vars` that shape the ENVELOPE instead of filling a template variable.
const RESERVED_VARS: &[&str] = &[
    "subject",
    "text",
    "body",
    "html",
    "language",
    "phone_number_id",
    "components",
];

/// The header that names one delivery to the proxy, identical on each of its retries (hub#2648):
/// erplora.com answers a key it has already sent with the stored result instead of sending again
/// (ERPlora/saas#2633), the way Stripe, Twilio and SendGrid treat theirs.
pub const IDEMPOTENCY_KEY_HEADER: &str = "Idempotency-Key";

/// The longest name of a header's PDF the transport sends (hub#2405), in characters. A chat
/// shows far less; the cut only keeps a runaway mapped value from travelling whole.
const MAX_DOCUMENT_NAME_CHARS: usize = 200;

/// How much of the proxy's answer is worth carrying into the error (and thus into the
/// dead-letter row). Enough for `{"error": "..."}`; not a whole HTML error page.
const MAX_DETAIL: usize = 300;

/// Sends `host.notify` messages through the SaaS device proxy with the hub's machine credential.
///
/// Both the hub id and the machine token are read **live** on every send, not captured at boot:
/// a hub that enrols (or rotates its token) after startup starts sending without a restart, the
/// same hot-reload `auth::machine_auth` and [`crate::error_sink::CloudErrorSink`] rely on.
pub struct CloudNotifyTransport {
    http: reqwest::Client,
    cloud: CloudClient,
    hub_id: HubId,
    machine_token: MachineToken,
}

/// Hand-written so the machine token can never reach a log line: the trait requires `Debug`, and
/// the relay prints the transport when a delivery fails.
impl std::fmt::Debug for CloudNotifyTransport {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("CloudNotifyTransport")
            .field("machine_token", &"<redacted>")
            .finish()
    }
}

impl CloudNotifyTransport {
    pub fn new(
        http: reqwest::Client,
        cloud_base_url: &str,
        hub_id: HubId,
        machine_token: MachineToken,
    ) -> Self {
        Self {
            http,
            cloud: CloudClient::new(cloud_base_url),
            hub_id,
            machine_token,
        }
    }

    /// The hub's machine credential, or an error if this hub is not enrolled.
    ///
    /// An un-enrolled hub simply cannot talk to the proxy, and the honest answer is to fail —
    /// loudly and retryably. The relay backs off and, after `MAX_ATTEMPTS`, dead-letters the row,
    /// which is visible. Anything quieter would be a reminder nobody knows was never sent.
    fn machine_auth(&self) -> Result<Auth> {
        let hub_id = self
            .hub_id
            .read()
            .ok()
            .map(|guard| guard.clone())
            .unwrap_or_default();
        let token = self
            .machine_token
            .read()
            .ok()
            .and_then(|guard| guard.clone())
            .ok_or_else(|| {
                RuntimeError::Notify(
                    "the hub is not enrolled (no machine token): host.notify goes out through the \
                     SaaS proxy and there is no credential to sign the call with"
                        .to_string(),
                )
            })?;
        Ok(Auth::HubToken { hub_id, token })
    }

    /// POSTs `body` to a prepared request. Any non-2xx is an `Err` — never a silent success.
    ///
    /// `delivery_key` travels as [`IDEMPOTENCY_KEY_HEADER`] on every attempt (hub#2648).
    async fn post(
        &self,
        request: &PreparedRequest,
        body: &Value,
        delivery_key: &str,
    ) -> Result<SendOutcome> {
        let mut builder = self
            .http
            .post(&request.url)
            .header(IDEMPOTENCY_KEY_HEADER, delivery_key)
            .json(body);
        for (name, value) in &request.headers {
            builder = builder.header(*name, value);
        }

        let response = builder.send().await.map_err(|e| {
            RuntimeError::Notify(format!(
                "notify proxy unreachable: {}",
                crate::cloud_proxy::cloud_unreachable(&e.to_string())
            ))
        })?;

        let status = response.status();
        let retry_after = retry_after_secs(response.headers());
        if status.is_success() {
            // The id the provider gave the message — Meta's `wamid` (hub#1951). A 200 is a send
            // whatever the body says: email has no id worth threading a conversation by, and a
            // proxy that answers something other than JSON has still delivered. Bounded for the
            // same reason `detail` is: this ends up in a column, and nothing about a `wamid`
            // needs three hundred characters.
            let body: Value = response.json().await.unwrap_or(Value::Null);
            let message_id: String = body
                .get("message_id")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .chars()
                .take(MAX_DETAIL)
                .collect();
            return Ok(SendOutcome::Sent { message_id });
        }

        // The reason has to reach whoever reads the dead-letter row: `quota_exceeded`,
        // `no_whatsapp_number` and `invalid_recipients` each need a different human action, and a
        // bare status code names none of them.
        let text = response.text().await.unwrap_or_default();
        let quota_spent = names_quota_exceeded(&text);
        let detail: String = text.trim().chars().take(MAX_DETAIL).collect();
        // A spent quota is an ANSWER, not a stumble (hub#971): the proxy says so with 402, or with
        // 429 and `{"error": "quota_exceeded"}`, and the relay must not spend eight rungs of
        // backoff against it. Any OTHER 429 is the proxy's rate limit (DRF's throttle, the email
        // door's `@quota`), which lifts on its own: the relay waits it out (hub#2649). Everything
        // else stays an `Err` and keeps its ladder.
        if status == reqwest::StatusCode::PAYMENT_REQUIRED {
            return Ok(SendOutcome::QuotaExceeded { detail });
        }
        // Meta refused it on the spot and erplora.com said why (hub#2723, ERPlora/saas#2669):
        // `{"error": "meta_send_failed", "meta_error": {code, reason, title, detail}}`. An answer,
        // not a stumble — the relay decides whether that reason is worth the ladder.
        if let Some(meta_error) = meta_send_failure(&text) {
            return Ok(SendOutcome::Refused {
                reason: crate::whatsapp_statuses::meta_reason(&meta_error),
                detail: crate::whatsapp_statuses::describe_meta_error(&meta_error),
            });
        }
        if status == reqwest::StatusCode::TOO_MANY_REQUESTS {
            if quota_spent {
                return Ok(SendOutcome::QuotaExceeded { detail });
            }
            return Ok(SendOutcome::RateLimited {
                retry_after_secs: retry_after,
                detail,
            });
        }
        Err(RuntimeError::Notify(format!(
            "notify proxy answered {status}: {detail}"
        )))
    }
}

/// The proxy's own name for a spent quota: `{"error": "quota_exceeded", …}`
/// (ERPlora/saas `whatsapp_inbox/api/notify.py`). Read from the code, never from the prose
/// (ADR-0055); a body that is not that JSON is not the quota.
fn names_quota_exceeded(body: &str) -> bool {
    serde_json::from_str::<Value>(body)
        .ok()
        .and_then(|v| v.get("error").and_then(Value::as_str).map(str::to_owned))
        .is_some_and(|code| code == "quota_exceeded")
}

/// The `meta_error` of a `meta_send_failed` answer that names a reason (ERPlora/saas#2669); `None`
/// for any other body, including a bare `meta_send_failed` from an older erplora.com — that one
/// stays an `Err` on the ladder.
fn meta_send_failure(body: &str) -> Option<Value> {
    let body: Value = serde_json::from_str(body).ok()?;
    if body.get("error").and_then(Value::as_str) != Some("meta_send_failed") {
        return None;
    }
    let meta_error = body.get("meta_error")?;
    meta_error
        .get("reason")
        .and_then(Value::as_str)
        .filter(|r| !r.trim().is_empty())?;
    Some(meta_error.clone())
}

/// `Retry-After` in seconds. It may also be an HTTP date; DRF always sends seconds, and a date or
/// an unreadable value is `None` — the relay then applies its own bounded wait rather than an
/// invented reading of somebody else's (the rule `cloud_proxy` already follows).
fn retry_after_secs(headers: &reqwest::header::HeaderMap) -> Option<u64> {
    headers
        .get(reqwest::header::RETRY_AFTER)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.trim().parse::<u64>().ok())
}

impl CloudNotifyTransport {
    /// The intent with its header photo, video or PDF turned into a link Meta can fetch, when the
    /// header names a file the owner uploaded to the hub ([`header_media_file`], hub#2335 and
    /// hub#2347); `None` when there is
    /// nothing to sign — a typed link, no header, or a value [`whatsapp_body`] will refuse.
    ///
    /// Signed on EVERY attempt, never once when the step was saved: the link lasts an hour, and a
    /// `delay` step or the relay's backoff can hold a message far longer than that.
    async fn sign_header_media(
        &self,
        auth: &Auth,
        intent: &NotifyIntent,
    ) -> Result<Option<NotifyIntent>> {
        let present: Vec<(&str, &str, &Value)> = HEADER_VARS
            .iter()
            .filter_map(|(key, kind)| intent.vars.get(*key).map(|value| (*key, *kind, value)))
            .collect();
        // Two headers are refused by `whatsapp_body` before the network; signing first would
        // spend a call on a message that is not going anywhere.
        let [(key, kind, value)] = present.as_slice() else {
            return Ok(None);
        };
        let Some(file) = value.as_str().and_then(header_media_file) else {
            return Ok(None);
        };
        // A header signs only a stored file of its OWN kind (the extension the door gave it from
        // its bytes, hub#2347): a title reading like a file is its text, and a video header naming
        // a stored photo is refused as the not-a-link it is — Meta would refuse it anyway.
        if Some(*kind) != header_media_kind(file) {
            return Ok(None);
        }
        // The file is stored under its fingerprint, and a signed link ends in it: without a name
        // the customer's chat would show that fingerprint (hub#2405). The owner's name, or — for a
        // step saved before the field existed — the template's, always with the `.pdf` a phone
        // needs to open it. Settled before the network: a name that is not text is refused
        // without spending the signing call.
        let document = match *kind {
            "document" => Some(with_pdf_extension(
                document_name(intent)?.unwrap_or_else(|| intent.template.trim().to_string()),
            )),
            _ => None,
        };
        let request = self.cloud.media_signed_link(auth, file);
        let mut builder = self.http.get(&request.url);
        for (name, value) in &request.headers {
            builder = builder.header(*name, value);
        }
        let response = builder.send().await.map_err(|e| {
            RuntimeError::Notify(format!(
                "the file of `vars.{key}` (`{file}`) could not be signed: {}",
                crate::cloud_proxy::cloud_unreachable(&e.to_string())
            ))
        })?;
        let status = response.status();
        let link = if status.is_success() {
            response
                .json::<Value>()
                .await
                .ok()
                .and_then(|v| v.get("url").and_then(Value::as_str).map(str::to_owned))
        } else {
            None
        };
        let Some(link) = link else {
            // A refusal, or — once erplora.com checks the file exists before signing
            // (ERPlora/saas#2393; today it signs any key) — a `404` for a file deleted from
            // Archivos. Either way the message does not leave without its approved picture.
            return Err(RuntimeError::Notify(format!(
                "the file of `vars.{key}` (`{file}`) could not be signed: erplora.com answered \
                 {status} with no link to it — if it was deleted from Archivos, upload it again \
                 in the automation step"
            )));
        };
        let mut signed = intent.clone();
        signed.vars[*key] = json!(link);
        if let Some(name) = document {
            signed.vars[HEADER_DOCUMENT_FILENAME_VAR] = json!(name);
        }
        Ok(Some(signed))
    }
}

/// **Where a file uploaded for a WhatsApp header lives** in the hub's `media/` (hub#2335). The
/// flow step keeps `whatsapp/headers/<file>` and the transport signs it at send time.
pub(crate) const HEADER_MEDIA_FOLDER: &str = "whatsapp/headers";

/// The hub file a header value names — `whatsapp/headers/<one file name>` — or `None`.
///
/// **Only that folder, and one level of it.** The rest of `media/` holds the hub's logs, its
/// imports, a module's scans; a `vars.header_*` written by a flow or emitted by a module must not
/// turn a customer's WhatsApp into a way out for them. So the name is ONE segment: no `/`, no `\`,
/// no `.`/`..`, nothing that is not printable — a path that could climb out is simply not a ref,
/// and [`whatsapp_body`] refuses it as the not-a-link it is.
pub(crate) fn header_media_file(value: &str) -> Option<&str> {
    let value = value.trim();
    let name = value.strip_prefix(HEADER_MEDIA_FOLDER)?.strip_prefix('/')?;
    let valid = !name.is_empty()
        && name != "."
        && name != ".."
        && name.len() <= 255
        && !name.contains(['/', '\\', '?', '#'])
        && !name.chars().any(char::is_control);
    valid.then_some(value)
}

/// The kind of header a stored file can fill, from the extension the door named it with
/// (`flows_header_media.rs` decides it from the file's bytes): `image`, `video` or `document` —
/// the kinds of [`HEADER_VARS`] — or `None` for a name the door never gives.
pub(crate) fn header_media_kind(file: &str) -> Option<&'static str> {
    match file.rsplit_once('.')?.1 {
        "jpg" | "png" => Some("image"),
        "mp4" => Some("video"),
        "pdf" => Some("document"),
        _ => None,
    }
}

#[async_trait]
impl NotifyTransport for CloudNotifyTransport {
    async fn send(
        &self,
        intent: &NotifyIntent,
        _routing: Routing,
        delivery_key: &str,
    ) -> Result<SendOutcome> {
        // The credential first: with no machine token there is nothing to send WITH, so there is
        // no point building a body or opening a socket.
        let auth = self.machine_auth()?;

        let signed;
        let (request, body) =
            match intent.channel {
                Channel::Email => (self.cloud.notify_email(&auth), email_body(intent)?),
                Channel::Whatsapp => {
                    signed = self.sign_header_media(&auth, intent).await?;
                    let intent = signed.as_ref().unwrap_or(intent);
                    (self.cloud.notify_whatsapp(&auth), whatsapp_body(intent)?)
                }
                Channel::Sms => return Err(RuntimeError::Notify(
                    "the sms channel has no transport yet: the SaaS proxies email and whatsapp \
                     only (ADR-0283 §5), and the hub holds no sms credential of its own"
                        .to_string(),
                )),
            };
        self.post(&request, &body, delivery_key).await
    }
}

/// `vars.<key>` as a trimmed, non-empty string — or nothing.
fn var_str<'a>(intent: &'a NotifyIntent, key: &str) -> Option<&'a str> {
    intent
        .vars
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|s| !s.is_empty())
}

/// Body of `POST /api/v1/hub/device/notify/email/`: `{to, subject, text, html?}`.
///
/// `from`/`reply_to` are deliberately absent — the SaaS resolves both, and it must stay that way.
fn email_body(intent: &NotifyIntent) -> Result<Value> {
    // An email has nothing to tap (hub#1633). Said out loud instead of dropped: a bare email where
    // somebody meant to ask a question is a message nobody wrote, and it still reaches a customer.
    if !intent.interactive.is_null() {
        return Err(RuntimeError::Notify(
            "email notification carrying `interactive`: options to tap are a whatsapp shape and \
             an email has nothing to tap. Send them on the whatsapp channel, or say it in the text"
                .to_string(),
        ));
    }

    let subject = var_str(intent, "subject").unwrap_or_else(|| intent.template.trim());
    if subject.is_empty() {
        return Err(RuntimeError::Notify(
            "email notification with no subject: put one in `vars.subject` or name the template \
             (the proxy rejects an empty subject)"
                .to_string(),
        ));
    }

    let text = var_str(intent, "text")
        .or_else(|| var_str(intent, "body"))
        .ok_or_else(|| {
            RuntimeError::Notify(
                "email notification with no body: the text goes in `vars.text`. There is no \
                 template catalogue yet, and the transport will not make one up — a blank email \
                 signed by ERPlora would still reach a real customer"
                    .to_string(),
            )
        })?;

    let mut body = json!({ "to": intent.to.trim(), "subject": subject, "text": text });
    if let Some(html) = var_str(intent, "html") {
        body["html"] = json!(html);
    }
    Ok(body)
}

/// Body of `POST /api/v1/hub/device/notify/whatsapp/`: `{to, body|template, phone_number_id?}`.
///
/// `template` is Meta's OBJECT (`{name, language, components}`), which the SaaS forwards verbatim
/// — not the bare template name the Rust client's doc-comment used to promise (hub#663).
fn whatsapp_body(intent: &NotifyIntent) -> Result<Value> {
    let header = template_header(intent)?;
    if let (Some((key, _)), true) = (
        &header,
        intent.template.trim().is_empty() || !intent.interactive.is_null(),
    ) {
        return Err(RuntimeError::Notify(format!(
            "whatsapp notification with `vars.{key}` outside a template: only an approved template \
             has a header, and dropping it would send a message nobody wrote"
        )));
    }
    let url_buttons = url_buttons(intent)?;
    if let (Some((first, _)), true) = (
        url_buttons.first(),
        intent.template.trim().is_empty() || !intent.interactive.is_null(),
    ) {
        return Err(RuntimeError::Notify(format!(
            "whatsapp notification with `vars.{BUTTON_URL_VAR_PREFIX}{}` outside a template: only \
             an approved template has link buttons, and dropping their end would send a link \
             nobody wrote",
            first
        )));
    }
    let mut body = json!({ "to": intent.to.trim() });
    // Optional: one of THIS hub's numbers. A foreign one is a 404 at the proxy, by design.
    if let Some(phone_number_id) = var_str(intent, "phone_number_id") {
        body["phone_number_id"] = json!(phone_number_id);
    }

    // **Options the customer TAPS** (hub#1633). Meta's shape is the wire shape: the proxy checks it
    // against Meta's limits and forwards it verbatim, so translating it here would be a second
    // contract to keep in step with Meta. It wins over copy because a Meta message has ONE `type`
    // and the proxy answers a request carrying two with `conflicting_message_type` — a paid round
    // trip spent to be told what is knowable here. A flow can never reach that pairing (
    // `flows::def` refuses it at save time); a module emitting the same intent can.
    if !intent.interactive.is_null() {
        if !intent.interactive.is_object() {
            return Err(RuntimeError::Notify(
                "whatsapp notification whose `interactive` is not an object: the options are \
                 Meta's own shape (`{type, body, action}`), and anything else comes back from \
                 Meta as an opaque 400 once the call has already been paid for"
                    .to_string(),
            ));
        }
        body["interactive"] = intent.interactive.clone();
        return Ok(body);
    }

    let name = intent.template.trim();
    if name.is_empty() {
        let text = var_str(intent, "text")
            .or_else(|| var_str(intent, "body"))
            .ok_or_else(|| {
                RuntimeError::Notify(
                    "whatsapp notification with neither a template nor `vars.text`: nothing to send"
                        .to_string(),
                )
            })?;
        body["body"] = json!(text);
        return Ok(body);
    }

    let mut template = json!({ "name": name });
    // Omitted = the proxy's own default (`es`). Sending a guess would silently pick a language
    // variant of the template that the business never approved.
    if let Some(language) = var_str(intent, "language") {
        template["language"] = json!(language);
    }
    if let Some(components) = template_components(intent, header, url_buttons) {
        template["components"] = components;
    }
    body["template"] = template;
    Ok(body)
}

/// Meta's `components` for the template.
///
/// `vars.components` wins verbatim: a template with POSITIONAL variables has no other way to be
/// filled, and the proxy passes the block to Meta untouched. Otherwise the remaining `vars` become
/// NAMED body parameters, sorted so the same intent always produces the same payload (Meta matches
/// them by name, so the order is only ours to keep stable — and testable). The header
/// ([`template_header`]: text hub#2111, media hub#2101) goes first, as Meta's own `header`
/// component, and the link
/// buttons' variable ends ([`url_buttons`]) last (hub#2110).
fn template_components(
    intent: &NotifyIntent,
    header: Option<(&str, Value)>,
    url_buttons: Vec<(u8, Value)>,
) -> Option<Value> {
    if let Some(explicit) = intent.vars.get("components").filter(|v| v.is_array()) {
        return Some(explicit.clone());
    }

    let mut components = Vec::new();
    if let Some((_, parameter)) = header {
        components.push(json!({ "type": "header", "parameters": [parameter] }));
    }

    let mut named: Vec<(&String, &Value)> = intent
        .vars
        .as_object()
        .into_iter()
        .flatten()
        .filter(|(key, _)| !RESERVED_VARS.contains(&key.as_str()))
        .filter(|(key, _)| !HEADER_VARS.iter().any(|(header, _)| header == key))
        .filter(|(key, _)| key.as_str() != HEADER_DOCUMENT_FILENAME_VAR)
        .filter(|(key, _)| !key.starts_with(BUTTON_URL_VAR_PREFIX))
        .collect();
    named.sort_by(|a, b| a.0.cmp(b.0));
    if !named.is_empty() {
        let parameters: Vec<Value> = named
            .into_iter()
            .map(|(key, value)| {
                json!({ "type": "text", "parameter_name": key, "text": as_text(value) })
            })
            .collect();
        components.push(json!({ "type": "body", "parameters": parameters }));
    }
    components.extend(url_buttons.into_iter().map(|(_, button)| button));

    (!components.is_empty()).then(|| Value::Array(components))
}

/// Meta's `button` components for the template's link buttons, with their position (hub#2110).
/// Meta matches each one by its `index`, so the array order is only the `vars` key order — stable,
/// which keeps the payload testable.
///
/// `vars.button_url_<n>` is the text Meta appends to the `{{1}}` of the URL button at position
/// `<n>`. Refused before the network when Meta could only answer an opaque 400 after the call was
/// paid for: a key whose position is not one digit (it would otherwise travel as a body variable),
/// or an end that is empty or not a scalar (a link to the bare prefix, or to `{"a":1}`).
fn url_buttons(intent: &NotifyIntent) -> Result<Vec<(u8, Value)>> {
    let mut buttons: Vec<(u8, Value)> = Vec::new();
    for (key, value) in intent.vars.as_object().into_iter().flatten() {
        if !key.starts_with(BUTTON_URL_VAR_PREFIX) {
            continue;
        }
        let index = button_url_index(key).ok_or_else(|| {
            RuntimeError::Notify(format!(
                "whatsapp notification with `vars.{key}`: a link button is `button_url_<n>`, with \
                 `<n>` the button's position in the template (0-9)"
            ))
        })?;
        let text = match value {
            Value::String(text) => text.trim().to_string(),
            Value::Number(number) => number.to_string(),
            _ => String::new(),
        };
        if text.is_empty() {
            return Err(RuntimeError::Notify(format!(
                "whatsapp notification whose `vars.{key}` is empty or not text: it is the end of \
                 the button's link, and without it the customer would tap a link to nowhere"
            )));
        }
        buttons.push((
            index,
            json!({
                "type": "button",
                "sub_type": "url",
                "index": index.to_string(),
                "parameters": [{ "type": "text", "text": text }]
            }),
        ));
    }
    Ok(buttons)
}

/// The header the intent asks for, as `(var key, Meta's header parameter)`: the value of a text
/// header's `{{1}}` (hub#2111) or the link of a media header (hub#2101).
///
/// Refused before the network when it cannot be what Meta expects: two of them (a template has
/// one header), a text value that is empty or not a scalar (a title with a hole), or a media value
/// that is not an http(s) link Meta can fetch — all would come back as an opaque 400 once the call
/// was paid for, or as a promotion without its picture.
fn template_header(intent: &NotifyIntent) -> Result<Option<(&'static str, Value)>> {
    let present: Vec<(&'static str, &'static str, &Value)> = HEADER_VARS
        .iter()
        .filter_map(|(key, kind)| intent.vars.get(*key).map(|value| (*key, *kind, value)))
        .collect();
    let document_named = intent.vars.get(HEADER_DOCUMENT_FILENAME_VAR).is_some();
    if document_named && !matches!(present.as_slice(), [("header_document", _, _)]) {
        return Err(RuntimeError::Notify(format!(
            "whatsapp notification with `vars.{HEADER_DOCUMENT_FILENAME_VAR}` and no \
             `vars.header_document`: it is the name of the header's PDF, and there is no PDF to \
             name"
        )));
    }
    let (key, kind, value) = match present.as_slice() {
        [] => return Ok(None),
        [one] => *one,
        many => {
            let keys: Vec<String> = many.iter().map(|(k, _, _)| format!("`vars.{k}`")).collect();
            return Err(RuntimeError::Notify(format!(
                "whatsapp notification with {}: a template has ONE header, so keep only the \
                 one its approved header asks for",
                keys.join(" and ")
            )));
        }
    };
    if kind == "text" {
        let text = match value {
            Value::String(text) => text.trim().to_string(),
            Value::Number(number) => number.to_string(),
            _ => String::new(),
        };
        if text.is_empty() {
            return Err(RuntimeError::Notify(format!(
                "whatsapp notification whose `vars.{key}` is empty or not text: it fills the \
                 variable of the template's title, and Meta refuses a title with a hole"
            )));
        }
        return Ok(Some((key, json!({ "type": "text", "text": text }))));
    }
    let link = value
        .as_str()
        .map(str::trim)
        .filter(|link| link.starts_with("https://") || link.starts_with("http://"))
        .ok_or_else(|| {
            RuntimeError::Notify(format!(
                "whatsapp notification whose `vars.{key}` is not an http(s) link: Meta downloads \
                 the header media itself, so it has to be a public address it can fetch"
            ))
        })?;
    let mut media = json!({ "link": link });
    if let Some(name) = document_name(intent)? {
        media["filename"] = json!(name);
    }
    Ok(Some((key, json!({ "type": kind, kind: media }))))
}

/// `vars.header_document_filename` as a name a chat can print (hub#2405), or `None` when there is
/// nothing to print. What a file name cannot carry — a folder separator, a line break — does not
/// travel; a runaway value is cut on a character at [`MAX_DOCUMENT_NAME_CHARS`]. A value that is
/// not text (an object, a list) is refused: the flow mapped the wrong thing, and printing its
/// JSON as the name of the customer's PDF would hide it.
fn document_name(intent: &NotifyIntent) -> Result<Option<String>> {
    let raw = match intent.vars.get(HEADER_DOCUMENT_FILENAME_VAR) {
        None | Some(Value::Null) => return Ok(None),
        Some(Value::String(text)) => text.clone(),
        Some(Value::Number(number)) => number.to_string(),
        Some(_) => {
            return Err(RuntimeError::Notify(format!(
                "whatsapp notification whose `vars.{HEADER_DOCUMENT_FILENAME_VAR}` is not text: it \
                 is the name the customer sees on the header's PDF"
            )))
        }
    };
    let cleaned: String = raw
        .chars()
        .filter(|c| !c.is_control())
        .map(|c| if matches!(c, '/' | '\\') { '-' } else { c })
        .collect();
    let cleaned = cleaned.trim();
    Ok((!cleaned.is_empty()).then(|| cleaned.chars().take(MAX_DOCUMENT_NAME_CHARS).collect()))
}

/// The name of a PDF the hub stores, ending in `.pdf` so the phone that downloads it knows how to
/// open it — cut first when needed, so the extension survives [`MAX_DOCUMENT_NAME_CHARS`].
fn with_pdf_extension(name: String) -> String {
    const EXTENSION: &str = ".pdf";
    if name.to_ascii_lowercase().ends_with(EXTENSION) {
        return name;
    }
    let stem: String = name
        .chars()
        .take(MAX_DOCUMENT_NAME_CHARS - EXTENSION.len())
        .collect();
    format!("{stem}{EXTENSION}")
}

/// A template variable as the text Meta will print. A string goes through unquoted; anything else
/// is rendered as its JSON so a number or a boolean still reads sensibly in a chat.
fn as_text(value: &Value) -> String {
    match value {
        Value::String(s) => s.clone(),
        other => other.to_string(),
    }
}

/// Does the environment ask for the in-memory mock?
///
/// **Opt-in by exact name, on purpose.** A mock answers `Sent` without sending anything, and the
/// relay then writes the `_event_delivery` marker — so a mock reached by accident is a
/// notification that never left and that nobody will ever discover. The production default is the
/// real proxy, and a hub that cannot use it fails visibly instead.
pub fn mock_requested(raw: Option<&str>) -> bool {
    raw.map(|value| value.trim().eq_ignore_ascii_case(MOCK_TRANSPORT))
        .unwrap_or(false)
}

/// The transport the host injects at boot ([`erplora_runtime::Runtime::set_notify_transport`]).
pub fn build(
    http: reqwest::Client,
    cloud_base_url: &str,
    hub_id: HubId,
    machine_token: MachineToken,
    requested: Option<String>,
) -> Arc<dyn NotifyTransport> {
    if mock_requested(requested.as_deref()) {
        tracing::warn!(
            "host.notify: {TRANSPORT_ENV}=mock — notifications are recorded in memory and NOTHING \
             is sent"
        );
        return Arc::new(MockTransport::new());
    }
    Arc::new(CloudNotifyTransport::new(
        http,
        cloud_base_url,
        hub_id,
        machine_token,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::extract::State;
    use axum::http::{HeaderMap, StatusCode};
    use axum::routing::post;
    use axum::{Json, Router};
    use erplora_runtime::host_notify::Channel;
    use serde_json::json;
    use std::sync::{Mutex, RwLock};

    /// Everything the fake SaaS saw, in arrival order: `(path, headers, body)`.
    type Seen = Arc<Mutex<Vec<(String, HeaderMap, Value)>>>;

    struct FakeCloud {
        base_url: String,
        seen: Seen,
        server: tokio::task::JoinHandle<()>,
    }

    impl FakeCloud {
        fn calls(&self) -> Vec<(String, HeaderMap, Value)> {
            self.seen.lock().unwrap().clone()
        }
    }

    impl Drop for FakeCloud {
        fn drop(&mut self) {
            self.server.abort();
        }
    }

    /// Fake SaaS serving the two device notify endpoints, answering `status` to every call.
    async fn fake_cloud(status: StatusCode, reply: Value) -> FakeCloud {
        #[derive(Clone)]
        struct St {
            seen: Seen,
            status: StatusCode,
            reply: Value,
        }

        async fn record(
            State(st): State<St>,
            uri: axum::http::Uri,
            headers: HeaderMap,
            body: String,
        ) -> (StatusCode, Json<Value>) {
            let parsed: Value = serde_json::from_str(&body).unwrap_or(Value::Null);
            st.seen
                .lock()
                .unwrap()
                .push((uri.path().to_string(), headers, parsed));
            (st.status, Json(st.reply.clone()))
        }

        /// The media manager's signing door (`GET …/media/raw/?path=`): a signed link to the path
        /// asked for, or `404` for a file that is not there (any path naming `missing`).
        async fn sign(
            State(st): State<St>,
            uri: axum::http::Uri,
            headers: HeaderMap,
            axum::extract::Query(q): axum::extract::Query<
                std::collections::HashMap<String, String>,
            >,
        ) -> (StatusCode, Json<Value>) {
            let path = q.get("path").cloned().unwrap_or_default();
            st.seen.lock().unwrap().push((
                uri.path().to_string(),
                headers,
                json!({ "path": path }),
            ));
            if path.contains("missing") {
                return (StatusCode::NOT_FOUND, Json(json!({ "error": "not found" })));
            }
            // A refusal whose body still carries a `url` (a proxy's error page, a half-written
            // answer): the status decides, not the body.
            if path.contains("refused") {
                return (
                    StatusCode::FORBIDDEN,
                    Json(json!({ "url": format!("https://objects.example/{path}") })),
                );
            }
            if path.contains("odd") {
                return (StatusCode::OK, Json(json!({ "url": "file:///etc/passwd" })));
            }
            (
                StatusCode::OK,
                Json(
                    json!({ "url": format!("https://objects.example/{path}?X-Amz-Signature=s1") }),
                ),
            )
        }

        let seen: Seen = Arc::new(Mutex::new(Vec::new()));
        let app = Router::new()
            .route("/api/v1/hub/device/notify/email/", post(record))
            .route("/api/v1/hub/device/notify/whatsapp/", post(record))
            .route("/api/v1/hub/device/media/raw/", axum::routing::get(sign))
            .with_state(St {
                seen: seen.clone(),
                status,
                reply,
            });
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        FakeCloud {
            base_url: format!("http://{addr}"),
            seen,
            server,
        }
    }

    fn transport(base_url: &str, token: Option<&str>) -> CloudNotifyTransport {
        CloudNotifyTransport::new(
            reqwest::Client::new(),
            base_url,
            Arc::new(RwLock::new("hub-1".to_string())),
            Arc::new(RwLock::new(token.map(str::to_string))),
        )
    }

    fn intent(channel: Channel, to: &str, template: &str, vars: Value) -> NotifyIntent {
        NotifyIntent {
            channel,
            to: to.to_string(),
            template: template.to_string(),
            vars,
            interactive: Value::Null,
        }
    }

    /// The same intent, plus the options the customer will tap.
    fn tappable(to: &str, interactive: Value) -> NotifyIntent {
        NotifyIntent {
            interactive,
            ..intent(Channel::Whatsapp, to, "", json!({}))
        }
    }

    fn buttons() -> Value {
        json!({
            "type": "button",
            "body": { "text": "¿Confirmas la cita del martes a las 10:30?" },
            "action": { "buttons": [
                { "type": "reply", "reply": { "id": "confirm", "title": "Sí" } },
                { "type": "reply", "reply": { "id": "cancel", "title": "No" } }
            ] }
        })
    }

    /// The email proxy gets exactly the body `apps/notify/api/views.py` validates — and the hub's
    /// MACHINE credential, because the sender is the outbox relay with no user logged in.
    #[tokio::test]
    async fn email_posts_the_body_the_saas_expects_with_the_machine_credential() {
        let cloud = fake_cloud(StatusCode::OK, json!({"message_id": "<a@b>"})).await;
        let sent = transport(&cloud.base_url, Some("machine-tok"))
            .send(
                &intent(
                    Channel::Email,
                    "cliente@x.com",
                    "appointment_reminder",
                    json!({"subject": "Tu cita de mañana", "text": "Te esperamos a las 10:00"}),
                ),
                Routing::Tenant,
                "ev-1",
            )
            .await
            .expect("a 200 from the proxy is a send");
        assert_eq!(
            sent,
            SendOutcome::Sent {
                message_id: "<a@b>".to_string()
            }
        );

        let calls = cloud.calls();
        assert_eq!(calls.len(), 1);
        let (path, headers, body) = &calls[0];
        assert_eq!(path, "/api/v1/hub/device/notify/email/");
        assert_eq!(headers["x-hub-id"], "hub-1");
        assert_eq!(headers["x-hub-token"], "machine-tok");
        assert_eq!(body["to"], "cliente@x.com");
        assert_eq!(body["subject"], "Tu cita de mañana");
        assert_eq!(body["text"], "Te esperamos a las 10:00");
        // `Reply-To`/`From` are the SaaS's to set: sending them from here would be signing
        // phishing with ERPlora's own sender (saas#1347).
        assert!(body.get("reply_to").is_none());
        assert!(body.get("from").is_none());
    }

    /// **hub#1951 — the send brings back the id the provider gave it.**
    ///
    /// The proxy already answers `{"message_id": "wamid…"}` and this side threw it away, so the
    /// hub knew a question had gone out but not WHICH message it was. That id is the only thing
    /// Meta puts in `context.id` when the customer taps, so without it a tap cannot be matched to
    /// the question it answers.
    #[tokio::test]
    async fn a_send_brings_back_the_id_the_provider_gave_it() {
        let cloud = fake_cloud(StatusCode::OK, json!({"message_id": "wamid.9"})).await;
        let sent = transport(&cloud.base_url, Some("machine-tok"))
            .send(
                &intent(
                    Channel::Whatsapp,
                    "+34600111222",
                    "appointment_reminder",
                    json!({"text": "¿Confirmas?"}),
                ),
                Routing::Tenant,
                "ev-1",
            )
            .await
            .expect("a 200 from the proxy is a send");
        assert_eq!(
            sent,
            SendOutcome::Sent {
                message_id: "wamid.9".to_string()
            }
        );
    }

    /// **Empty, never an error.** Email has no `wamid` worth threading a conversation by, and a
    /// SaaS older than the field names nothing: a 200 is a send in both cases. Refusing one here
    /// would turn "delivered, unidentified" into eight retries and a dead-letter.
    #[tokio::test]
    async fn a_send_the_provider_did_not_name_is_still_a_send() {
        let cloud = fake_cloud(StatusCode::OK, json!({})).await;
        let sent = transport(&cloud.base_url, Some("machine-tok"))
            .send(
                &intent(
                    Channel::Email,
                    "cliente@x.com",
                    "appointment_reminder",
                    json!({"subject": "Tu cita", "text": "Te esperamos"}),
                ),
                Routing::Tenant,
                "ev-1",
            )
            .await
            .expect("a 200 with no id is still a send");
        assert_eq!(
            sent,
            SendOutcome::Sent {
                message_id: String::new()
            }
        );
    }

    /// **hub#2648 — every attempt of a delivery names it with the same key.** The relay sends
    /// first and records the send afterwards; whatever breaks in between retries the send. The
    /// proxy only recognises the retry by the `Idempotency-Key` it carries, so both channels
    /// carry the key they were handed, unchanged on a retry and different for another delivery.
    #[tokio::test]
    async fn every_attempt_of_a_delivery_carries_its_idempotency_key() {
        let cloud = fake_cloud(StatusCode::OK, json!({"message_id": "m"})).await;
        let t = transport(&cloud.base_url, Some("machine-tok"));
        let whatsapp = intent(Channel::Whatsapp, "+34600111222", "reminder", json!({}));
        let email = intent(
            Channel::Email,
            "cliente@x.com",
            "reminder",
            json!({"subject": "Tu cita", "text": "Te esperamos"}),
        );
        for (message, key) in [
            (&whatsapp, "ev-wa"),
            (&whatsapp, "ev-wa"),
            (&email, "ev-mail"),
        ] {
            t.send(message, Routing::CloudProxy, key)
                .await
                .expect("a 200 from the proxy is a send");
        }

        let keys: Vec<String> = cloud
            .calls()
            .iter()
            .map(|(_, headers, _)| {
                headers
                    .get(IDEMPOTENCY_KEY_HEADER)
                    .and_then(|v| v.to_str().ok())
                    .unwrap_or("<missing>")
                    .to_string()
            })
            .collect();
        assert_eq!(keys, ["ev-wa", "ev-wa", "ev-mail"]);
    }

    /// Without a subject in `vars`, the template NAME is the subject — the SaaS rejects an empty
    /// one with a 400, and a notification with no subject is not worth a round trip.
    #[test]
    fn email_falls_back_to_the_template_name_as_subject() {
        let body = email_body(&intent(
            Channel::Email,
            "cliente@x.com",
            "appointment_reminder",
            json!({"body": "a las 10:00", "html": "<p>a las 10:00</p>"}),
        ))
        .unwrap();
        assert_eq!(body["subject"], "appointment_reminder");
        assert_eq!(body["text"], "a las 10:00");
        assert_eq!(body["html"], "<p>a las 10:00</p>");
    }

    /// No text, no email. The transport does not invent copy: an email whose body the hub made up
    /// still goes out signed by ERPlora, to a real customer.
    #[test]
    fn email_without_a_body_is_refused_before_the_network() {
        let err = email_body(&intent(
            Channel::Email,
            "cliente@x.com",
            "appointment_reminder",
            json!({"when": "10:00"}),
        ))
        .unwrap_err();
        assert!(format!("{err}").contains("vars.text"), "{err}");
    }

    /// WhatsApp: the template is an OBJECT for Meta (`{name, language, components}`), not the bare
    /// name the old doc-comment of `cloud-client::notify_whatsapp` promised.
    #[tokio::test]
    async fn whatsapp_posts_a_meta_template_object() {
        let cloud = fake_cloud(StatusCode::OK, json!({"message_id": "wamid.1"})).await;
        transport(&cloud.base_url, Some("machine-tok"))
            .send(
                &intent(
                    Channel::Whatsapp,
                    "+34600999888",
                    "appointment_reminder",
                    json!({"language": "es", "when": "10:00", "who": "Ana"}),
                ),
                Routing::CloudProxy,
                "ev-1",
            )
            .await
            .unwrap();

        let calls = cloud.calls();
        assert_eq!(calls.len(), 1);
        let (path, _, body) = &calls[0];
        assert_eq!(path, "/api/v1/hub/device/notify/whatsapp/");
        assert_eq!(body["to"], "+34600999888");
        assert_eq!(body["template"]["name"], "appointment_reminder");
        assert_eq!(body["template"]["language"], "es");
        // Named parameters, sorted by key so the payload is deterministic.
        assert_eq!(
            body["template"]["components"],
            json!([{ "type": "body", "parameters": [
                {"type": "text", "parameter_name": "when", "text": "10:00"},
                {"type": "text", "parameter_name": "who", "text": "Ana"}
            ]}])
        );
    }

    /// An empty `template` means free text (`{to, body}`) — only legal inside Meta's 24 h window,
    /// but that is Meta's rule to enforce, not ours.
    #[test]
    fn whatsapp_without_a_template_sends_free_text() {
        let body = whatsapp_body(&intent(
            Channel::Whatsapp,
            "+34600999888",
            "",
            json!({"text": "tu mesa está lista"}),
        ))
        .unwrap();
        assert_eq!(body["body"], "tu mesa está lista");
        assert!(body.get("template").is_none());
    }

    /// A module may drive Meta's `components` verbatim — positional templates have no other way.
    #[test]
    fn whatsapp_passes_explicit_components_through() {
        let components =
            json!([{ "type": "body", "parameters": [{"type": "text", "text": "10:00"}]}]);
        let body = whatsapp_body(&intent(
            Channel::Whatsapp,
            "+34600999888",
            "reminder",
            json!({ "components": components.clone() }),
        ))
        .unwrap();
        assert_eq!(body["template"]["components"], components);
    }

    /// A proxy failure must NOT be reported as sent: `deliver_host_notify` only writes the
    /// `_event_delivery` marker on `Ok`, so an `Err` is what keeps the row retryable and, after
    /// `MAX_ATTEMPTS`, sends it to dead-letter.
    #[tokio::test]
    async fn a_proxy_failure_leaves_the_event_retryable() {
        let cloud = fake_cloud(
            StatusCode::BAD_GATEWAY,
            json!({"error": "meta_send_failed"}),
        )
        .await;
        let err = transport(&cloud.base_url, Some("machine-tok"))
            .send(
                &intent(
                    Channel::Email,
                    "cliente@x.com",
                    "t",
                    json!({"subject": "s", "text": "t"}),
                ),
                Routing::Tenant,
                "ev-1",
            )
            .await
            .expect_err("a 502 from the proxy is not a delivery");
        assert!(matches!(err, RuntimeError::Notify(_)), "got {err:?}");
        assert_eq!(cloud.calls().len(), 1, "it did try");
    }

    /// Quota exhausted is not a delivery — and not a stumble either (hub#971): it comes back as
    /// the outcome the relay dead-letters at once, with the proxy's reason on it, instead of an
    /// `Err` that would climb eight rungs of backoff against the same wall.
    #[tokio::test]
    async fn quota_exceeded_is_not_a_delivery() {
        for status in [StatusCode::TOO_MANY_REQUESTS, StatusCode::PAYMENT_REQUIRED] {
            let cloud = fake_cloud(status, json!({"error": "quota_exceeded"})).await;
            let outcome = transport(&cloud.base_url, Some("machine-tok"))
                .send(
                    &intent(Channel::Whatsapp, "+34600999888", "reminder", json!({})),
                    Routing::CloudProxy,
                    "ev-1",
                )
                .await
                .unwrap_or_else(|e| panic!("{status} is an answer, not a transport error: {e}"));
            match outcome {
                SendOutcome::QuotaExceeded { detail } => assert!(
                    detail.contains("quota_exceeded"),
                    "the reason has to reach the dead-letter screen: {detail}"
                ),
                other => panic!("{status} must be QuotaExceeded, got {other:?}"),
            }
        }
    }

    /// Meta refused in the act and erplora.com said why (ERPlora/saas#2669): the reason comes
    /// back as an answer, so the relay can tell the refusal the eighth attempt would repeat
    /// (hub#2723) from a stumble. Meta's code reaches the dead-letter.
    #[tokio::test]
    async fn a_refusal_meta_explains_comes_back_with_its_reason_hub2723() {
        let cloud = fake_cloud(
            StatusCode::BAD_GATEWAY,
            json!({"error": "meta_send_failed", "meta_error": {
                "code": 131047, "reason": "outside_window",
                "title": "Re-engagement message", "detail": "More than 24 hours."}}),
        )
        .await;
        let outcome = transport(&cloud.base_url, Some("machine-tok"))
            .send(
                &intent(Channel::Whatsapp, "+34600999888", "reminder", json!({})),
                Routing::CloudProxy,
                "ev-1",
            )
            .await
            .expect("a refusal with its reason is an answer");
        match outcome {
            SendOutcome::Refused { reason, detail } => {
                assert_eq!(reason, "outside_window");
                assert!(detail.contains("131047"), "{detail}");
            }
            other => panic!("expected Refused, got {other:?}"),
        }
    }

    /// The control: any other non-2xx stays an `Err` and keeps its ladder (a 502 is a stumble).
    #[tokio::test]
    async fn other_refusals_stay_errors_and_keep_the_ladder() {
        let cloud = fake_cloud(StatusCode::BAD_GATEWAY, json!({"error": "upstream"})).await;
        let err = transport(&cloud.base_url, Some("machine-tok"))
            .send(
                &intent(Channel::Whatsapp, "+34600999888", "reminder", json!({})),
                Routing::CloudProxy,
                "ev-1",
            )
            .await
            .unwrap_err();
        assert!(format!("{err}").contains("502"), "{err}");
    }

    /// Fake SaaS answering every notify call with `status`, the raw `body` and, if given, a
    /// `Retry-After` header — the shapes DRF's throttle and the email door's `@quota` produce.
    async fn answering_cloud(
        status: StatusCode,
        retry_after: Option<&'static str>,
        body: String,
    ) -> (String, tokio::task::JoinHandle<()>) {
        let reply = move || {
            let body = body.clone();
            async move {
                let mut headers = HeaderMap::new();
                if let Some(value) = retry_after {
                    headers.insert(
                        axum::http::header::RETRY_AFTER,
                        axum::http::HeaderValue::from_static(value),
                    );
                }
                (status, headers, body)
            }
        };
        let app = Router::new()
            .route("/api/v1/hub/device/notify/email/", post(reply.clone()))
            .route("/api/v1/hub/device/notify/whatsapp/", post(reply));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        (format!("http://{addr}"), server)
    }

    async fn outcome_of(
        status: StatusCode,
        retry_after: Option<&'static str>,
        body: &str,
    ) -> SendOutcome {
        let (base_url, server) = answering_cloud(status, retry_after, body.to_string()).await;
        let outcome = transport(&base_url, Some("machine-tok"))
            .send(
                &intent(Channel::Whatsapp, "+34600999888", "reminder", json!({})),
                Routing::CloudProxy,
                "ev-1",
            )
            .await
            .unwrap_or_else(|e| panic!("{status} is an answer, not a transport error: {e}"));
        server.abort();
        outcome
    }

    /// A 429 that does not say `quota_exceeded` is erplora.com's rate limit (hub#2649): the
    /// relay is told to wait, with the proxy's `Retry-After` when it is a number of seconds.
    #[tokio::test]
    async fn a_429_that_is_not_the_quota_is_a_rate_limit_hub2649() {
        let drf = r#"{"detail": "Request was throttled. Expected available in 30 seconds."}"#;
        let cases: [(Option<&'static str>, &str, Option<u64>); 5] = [
            (Some("30"), drf, Some(30)),
            (Some(" 7 "), drf, Some(7)),
            // The email door's `@quota` names no wait.
            (
                None,
                r#"{"detail": "Too many requests. Please try again later."}"#,
                None,
            ),
            // An HTTP date is legal, but the hub does not guess at it: the relay's default applies.
            (Some("Wed, 21 Oct 2026 07:28:00 GMT"), drf, None),
            // A gateway's HTML page in front of erplora.com is not the quota either.
            (None, "<html>429 Too Many Requests</html>", None),
        ];
        for (retry_after, body, expected) in cases {
            match outcome_of(StatusCode::TOO_MANY_REQUESTS, retry_after, body).await {
                SendOutcome::RateLimited {
                    retry_after_secs,
                    detail,
                } => {
                    assert_eq!(retry_after_secs, expected, "Retry-After {retry_after:?}");
                    assert_eq!(detail, body.trim(), "the proxy's answer travels to the row");
                }
                other => panic!("429 {body} must be RateLimited, got {other:?}"),
            }
        }
    }

    /// The quota is told apart by its CODE, read from the whole body: a long `detail` the
    /// dead-letter text would cut must not turn a spent quota into a wait (hub#2649). And a 402 is
    /// the quota whatever it carries.
    #[tokio::test]
    async fn the_quota_is_read_from_the_whole_body_and_402_is_always_the_quota_hub2649() {
        let long = format!(
            r#"{{"detail": "{}", "error": "quota_exceeded"}}"#,
            "x".repeat(MAX_DETAIL * 2)
        );
        for (status, retry_after, body) in [
            (StatusCode::TOO_MANY_REQUESTS, Some("30"), long.as_str()),
            (
                StatusCode::PAYMENT_REQUIRED,
                Some("30"),
                r#"{"detail": "throttled"}"#,
            ),
        ] {
            match outcome_of(status, retry_after, body).await {
                SendOutcome::QuotaExceeded { .. } => {}
                other => panic!("{status} {body:.60} must be QuotaExceeded, got {other:?}"),
            }
        }
    }

    /// An un-enrolled hub has no machine credential, so there is nothing to sign the call with.
    /// It must fail LOUD (retryable) instead of quietly pretending it sent something.
    #[tokio::test]
    async fn without_a_machine_token_nothing_is_sent_and_nothing_is_claimed() {
        let cloud = fake_cloud(StatusCode::OK, json!({"message_id": "x"})).await;
        let err = transport(&cloud.base_url, None)
            .send(
                &intent(
                    Channel::Email,
                    "cliente@x.com",
                    "t",
                    json!({"subject": "s", "text": "t"}),
                ),
                Routing::Tenant,
                "ev-1",
            )
            .await
            .unwrap_err();
        assert!(format!("{err}").contains("not enrolled"), "{err}");
        assert!(cloud.calls().is_empty(), "no credential, no request");
    }

    /// SMS has no proxy on the SaaS side yet (only `notify/email/` and `notify/whatsapp/` exist).
    /// Saying so beats posting into a 404 eight times.
    #[tokio::test]
    async fn sms_has_no_proxy_yet_and_says_so() {
        let cloud = fake_cloud(StatusCode::OK, json!({})).await;
        let err = transport(&cloud.base_url, Some("machine-tok"))
            .send(
                &intent(Channel::Sms, "+34600999888", "t", json!({"text": "hola"})),
                Routing::Tenant,
                "ev-1",
            )
            .await
            .unwrap_err();
        assert!(format!("{err}").contains("sms"), "{err}");
        assert!(cloud.calls().is_empty());
    }

    /// `Routing::Tenant` still goes through the proxy: the hub holds no local SMTP/Meta secret, so
    /// honouring ADR-0012's local branch today would only mean refusing to send (flows.md §5).
    #[tokio::test]
    async fn tenant_routing_still_goes_through_the_proxy() {
        let cloud = fake_cloud(StatusCode::OK, json!({"message_id": "wamid.2"})).await;
        transport(&cloud.base_url, Some("machine-tok"))
            .send(
                &intent(Channel::Whatsapp, "+34600999888", "reminder", json!({})),
                Routing::Tenant,
                "ev-1",
            )
            .await
            .unwrap();
        assert_eq!(cloud.calls()[0].0, "/api/v1/hub/device/notify/whatsapp/");
    }

    /// The machine token is a secret: it must not land in a log line through `{:?}`.
    #[test]
    fn debug_never_prints_the_machine_token() {
        let printed = format!("{:?}", transport("https://erplora.com", Some("s3cr3t")));
        assert!(!printed.contains("s3cr3t"), "{printed}");
    }

    /// The mock is OPT-IN and must be asked for by name: it answers `Sent` without sending, which
    /// the outbox then marks as delivered. Reachable by accident, it is a notification that never
    /// left and nobody ever finds out.
    #[test]
    fn the_mock_transport_is_opt_in_by_name() {
        assert!(mock_requested(Some("mock")));
        assert!(mock_requested(Some("MOCK")));
        assert!(mock_requested(Some("  mock  ")));

        assert!(
            !mock_requested(None),
            "production default is the real proxy"
        );
        assert!(!mock_requested(Some("")));
        assert!(!mock_requested(Some("1")));
        assert!(!mock_requested(Some("cloud")));
        assert!(!mock_requested(Some("mocking")));
    }

    #[test]
    fn build_picks_the_transport_the_env_asked_for() {
        let hub_id: HubId = Arc::new(RwLock::new("hub-1".into()));
        let token: MachineToken = Arc::new(RwLock::new(Some("tok".into())));

        let mocked = build(
            reqwest::Client::new(),
            "https://erplora.com",
            hub_id.clone(),
            token.clone(),
            Some("mock".into()),
        );
        assert!(
            format!("{mocked:?}").starts_with("MockTransport"),
            "{mocked:?}"
        );

        let real = build(
            reqwest::Client::new(),
            "https://erplora.com",
            hub_id,
            token,
            None,
        );
        assert!(
            format!("{real:?}").starts_with("CloudNotifyTransport"),
            "{real:?}"
        );
    }

    /// **Options travel to the proxy unchanged** (hub#1633).
    ///
    /// Meta's shape is the wire shape: the SaaS checks it against Meta's limits and forwards it
    /// verbatim, so a second shape here would be a translation layer that has to grow every time
    /// Meta adds a field — and the hub would be writing to a contract that exists nowhere else.
    #[test]
    fn whatsapp_sends_the_options_the_customer_taps_and_nothing_else() {
        let body = whatsapp_body(&tappable("+34600111222", buttons())).unwrap();
        assert_eq!(body["to"], "+34600111222");
        assert_eq!(body["interactive"], buttons());
        // A Meta message has ONE type. Sending copy alongside would be `conflicting_message_type`
        // at the proxy — a paid round trip spent to be told what was knowable here.
        assert!(body.get("body").is_none(), "{body}");
        assert!(body.get("template").is_none(), "{body}");
    }

    /// Which of THIS hub's numbers sends is not copy, so it still rides next to the options.
    #[test]
    fn whatsapp_options_still_choose_the_sending_number() {
        let with_number = NotifyIntent {
            vars: json!({ "phone_number_id": "123456" }),
            ..tappable("+34600111222", buttons())
        };
        let body = whatsapp_body(&with_number).unwrap();
        assert_eq!(body["phone_number_id"], "123456");
        assert_eq!(body["interactive"], buttons());
    }

    /// An `interactive` that is not an object is a typo, and forwarding it would come back as an
    /// opaque 400 from Meta after the call was already paid for.
    #[test]
    fn whatsapp_refuses_options_that_are_not_an_object_before_the_network() {
        for bad in [json!("button"), json!(["confirm"]), json!(7)] {
            let err = whatsapp_body(&tappable("+34600111222", bad.clone()))
                .expect_err("the options are an object of Meta's own shape");
            assert!(format!("{err}").contains("interactive"), "{err} for {bad}");
        }
    }

    /// An email has nothing to tap. A flow can never get here — `flows::def` refuses the pairing at
    /// save time — but a MODULE emits the same intent from `host.notify`, and dropping the options
    /// silently would send a bare email where somebody meant to ask a question.
    #[test]
    fn email_refuses_options_instead_of_dropping_them() {
        let err = email_body(&NotifyIntent {
            interactive: buttons(),
            ..intent(
                Channel::Email,
                "cliente@x.com",
                "reminder",
                json!({ "text": "Te esperamos" }),
            )
        })
        .expect_err("an email has nothing to tap");
        assert!(format!("{err}").contains("interactive"), "{err}");
    }

    /// **A template with media in its header** (hub#2101). Meta refuses the send unless the header
    /// parameter travels with it, and before this the only way to write one was `vars.components`
    /// by hand — the one thing the flow editor cannot offer an owner. `vars.header_<kind>` is the
    /// link; the remaining vars stay the named body parameters they always were.
    #[test]
    fn whatsapp_template_with_a_header_image_sends_it_as_the_header_parameter() {
        let body = whatsapp_body(&intent(
            Channel::Whatsapp,
            "+34600999888",
            "autumn_promo",
            json!({"header_image": " https://cdn.example.com/salon.jpg ", "who": "Ana"}),
        ))
        .unwrap();
        assert_eq!(
            body["template"]["components"],
            json!([
                { "type": "header", "parameters": [
                    {"type": "image", "image": {"link": "https://cdn.example.com/salon.jpg"}}
                ]},
                { "type": "body", "parameters": [
                    {"type": "text", "parameter_name": "who", "text": "Ana"}
                ]}
            ])
        );
    }

    /// Video and document are the same parameter under another type; a template whose body has
    /// no variables still needs its header.
    #[test]
    fn whatsapp_template_header_video_and_document_need_no_body_variables() {
        for (key, kind) in [("header_video", "video"), ("header_document", "document")] {
            let body = whatsapp_body(&intent(
                Channel::Whatsapp,
                "+34600999888",
                "menu_of_the_day",
                json!({ key: "https://cdn.example.com/file", "language": "es" }),
            ))
            .unwrap();
            assert_eq!(
                body["template"]["components"],
                json!([{ "type": "header", "parameters": [
                    { "type": kind, kind: {"link": "https://cdn.example.com/file"} }
                ]}]),
                "{key}"
            );
        }
    }

    /// **The photo the owner UPLOADED from the flow step** (hub#2335). She has no public link to
    /// her salon's picture: the step stores the hub file (`whatsapp/headers/<id>.jpg`) and every
    /// send asks the SaaS for a freshly signed link to it — a link signed when the step was saved
    /// would have expired by the time a `delay` step or the relay's backoff lets the message out.
    #[tokio::test]
    async fn a_header_image_uploaded_to_the_hub_goes_out_as_a_freshly_signed_link() {
        let cloud = fake_cloud(StatusCode::OK, json!({"message_id": "wamid.7"})).await;
        transport(&cloud.base_url, Some("machine-tok"))
            .send(
                &intent(
                    Channel::Whatsapp,
                    "+34600111222",
                    "autumn_promo",
                    json!({"header_image": " whatsapp/headers/0b8e.jpg ", "who": "Ana"}),
                ),
                Routing::Tenant,
                "ev-1",
            )
            .await
            .expect("an uploaded header is sent");

        let calls = cloud.calls();
        assert_eq!(calls.len(), 2, "sign, then send: {calls:?}");
        let (path, headers, asked) = &calls[0];
        assert_eq!(path, "/api/v1/hub/device/media/raw/");
        assert_eq!(asked["path"], "whatsapp/headers/0b8e.jpg");
        assert_eq!(
            headers["x-hub-token"], "machine-tok",
            "signed as the hub, like the send"
        );
        let (path, _, body) = &calls[1];
        assert_eq!(path, "/api/v1/hub/device/notify/whatsapp/");
        assert_eq!(
            body["template"]["components"],
            json!([
                { "type": "header", "parameters": [{ "type": "image", "image": {
                    "link": "https://objects.example/whatsapp/headers/0b8e.jpg?X-Amz-Signature=s1"
                }}]},
                { "type": "body", "parameters": [
                    {"type": "text", "parameter_name": "who", "text": "Ana"}
                ]}
            ])
        );
    }

    /// A link she typed is still hers to send: nothing is signed for it.
    #[tokio::test]
    async fn a_header_link_is_sent_as_written_without_asking_for_a_signature() {
        let cloud = fake_cloud(StatusCode::OK, json!({"message_id": "wamid.8"})).await;
        transport(&cloud.base_url, Some("machine-tok"))
            .send(
                &intent(
                    Channel::Whatsapp,
                    "+34600111222",
                    "autumn_promo",
                    json!({"header_image": "https://cdn.example.com/salon.jpg"}),
                ),
                Routing::Tenant,
                "ev-1",
            )
            .await
            .expect("a link is sent");
        let calls = cloud.calls();
        assert_eq!(calls.len(), 1, "{calls:?}");
        assert_eq!(calls[0].0, "/api/v1/hub/device/notify/whatsapp/");
    }

    /// **Only the header folder is signed.** The rest of `media/` holds the hub's logs, its
    /// imports, a module's scans: a `vars.header_*` naming any of them — written by a flow or
    /// emitted by a module — must not turn a customer's WhatsApp into a way out for the hub's
    /// files. Refused before the network: nothing is signed, nothing is sent.
    #[tokio::test]
    async fn a_hub_file_outside_the_header_folder_never_leaves_by_whatsapp() {
        let cloud = fake_cloud(StatusCode::OK, json!({"message_id": "wamid.9"})).await;
        for stray in [
            "_logs/hub.log",
            "whatsapp/headers/../../_logs/hub.log",
            "whatsapp/headers/./x.jpg",
            "whatsapp/headers/",
            "whatsapp/headers/.",
            "whatsapp/headers/..",
            "whatsapp/headersx/x.jpg",
            "whatsapp/headersx.jpg",
            "/whatsapp/headers/x.jpg",
            "whatsapp/headers\\x.jpg",
            "modules/verifactu/cert.p12",
            "whatsapp/headers/a\nb.jpg",
            &format!("whatsapp/headers/{}.jpg", "a".repeat(252)),
        ] {
            let err = transport(&cloud.base_url, Some("machine-tok"))
                .send(
                    &intent(
                        Channel::Whatsapp,
                        "+34600111222",
                        "autumn_promo",
                        json!({ "header_image": stray }),
                    ),
                    Routing::Tenant,
                    "ev-1",
                )
                .await
                .expect_err(stray);
            assert!(format!("{err}").contains("header_image"), "{stray}: {err}");
        }
        assert!(cloud.calls().is_empty(), "{:?}", cloud.calls());
    }

    /// The file was deleted from Archivos after the step was saved: the send fails where the
    /// dead-letter shows it, instead of reaching Meta with no picture.
    #[tokio::test]
    async fn a_header_file_that_is_gone_is_not_sent_without_its_picture() {
        let cloud = fake_cloud(StatusCode::OK, json!({"message_id": "wamid.10"})).await;
        let err = transport(&cloud.base_url, Some("machine-tok"))
            .send(
                &intent(
                    Channel::Whatsapp,
                    "+34600111222",
                    "autumn_promo",
                    json!({"header_image": "whatsapp/headers/missing.jpg"}),
                ),
                Routing::Tenant,
                "ev-1",
            )
            .await
            .expect_err("no file, no send");
        assert!(
            format!("{err}").contains("whatsapp/headers/missing.jpg"),
            "{err}"
        );
        let calls = cloud.calls();
        assert_eq!(calls.len(), 1, "signed, never sent: {calls:?}");
        assert_eq!(calls[0].0, "/api/v1/hub/device/media/raw/");
    }

    /// The SaaS refused to sign — whatever its body says, there is no link to send.
    #[tokio::test]
    async fn a_refused_signature_is_never_taken_as_a_link() {
        let cloud = fake_cloud(StatusCode::OK, json!({"message_id": "wamid.11"})).await;
        let err = transport(&cloud.base_url, Some("machine-tok"))
            .send(
                &intent(
                    Channel::Whatsapp,
                    "+34600111222",
                    "autumn_promo",
                    json!({"header_image": "whatsapp/headers/refused.jpg"}),
                ),
                Routing::Tenant,
                "ev-1",
            )
            .await
            .expect_err("a refusal is not a link");
        assert!(format!("{err}").contains("403"), "{err}");
        let calls = cloud.calls();
        assert_eq!(calls.len(), 1, "signed, never sent: {calls:?}");
    }

    /// A signed answer that is not a web link is not handed to Meta either.
    #[tokio::test]
    async fn a_signed_answer_that_is_not_a_web_link_is_not_sent() {
        let cloud = fake_cloud(StatusCode::OK, json!({"message_id": "wamid.12"})).await;
        let err = transport(&cloud.base_url, Some("machine-tok"))
            .send(
                &intent(
                    Channel::Whatsapp,
                    "+34600111222",
                    "autumn_promo",
                    json!({"header_image": "whatsapp/headers/odd.jpg"}),
                ),
                Routing::Tenant,
                "ev-1",
            )
            .await
            .expect_err("file:// is not a link Meta can fetch");
        assert!(format!("{err}").contains("header_image"), "{err}");
        let calls = cloud.calls();
        assert_eq!(calls.len(), 1, "signed, never sent: {calls:?}");
    }

    /// **The video or the PDF the owner UPLOADED from the flow step** (hub#2347): the promotion's
    /// video and the restaurant's menu go out exactly like the photo — a fresh link signed on every
    /// send, in the header parameter of their own kind. The PDF also carries a name the customer
    /// can read (hub#2405: here the template's, as no name was written).
    #[tokio::test]
    async fn a_header_video_or_document_uploaded_to_the_hub_goes_out_as_a_freshly_signed_link() {
        for (key, file, kind, named) in [
            ("header_video", "whatsapp/headers/0b8e.mp4", "video", None),
            (
                "header_document",
                "whatsapp/headers/0b8e.pdf",
                "document",
                Some("autumn_promo.pdf"),
            ),
        ] {
            let cloud = fake_cloud(StatusCode::OK, json!({"message_id": "wamid.15"})).await;
            transport(&cloud.base_url, Some("machine-tok"))
                .send(
                    &intent(
                        Channel::Whatsapp,
                        "+34600111222",
                        "autumn_promo",
                        json!({ key: format!(" {file} ") }),
                    ),
                    Routing::Tenant,
                    "ev-1",
                )
                .await
                .unwrap_or_else(|e| panic!("{key}: an uploaded header is sent: {e}"));
            let calls = cloud.calls();
            assert_eq!(calls.len(), 2, "{key}: sign, then send: {calls:?}");
            assert_eq!(calls[0].0, "/api/v1/hub/device/media/raw/");
            assert_eq!(calls[0].2["path"], file, "{key}");
            let mut media = json!({
                "link": format!("https://objects.example/{file}?X-Amz-Signature=s1")
            });
            if let Some(name) = named {
                media["filename"] = json!(name);
            }
            assert_eq!(
                calls[1].2["template"]["components"][0],
                json!({ "type": "header", "parameters": [{ "type": kind, kind: media }]}),
                "{key}"
            );
        }
    }

    /// **The name the customer sees on the header's PDF** (hub#2405). Without Meta's
    /// `document.filename` the chat shows the end of the link — a fingerprint of letters and
    /// numbers that reads like spam. `vars.header_document_filename` is that name, sent as
    /// written, and never a body variable of the template.
    #[test]
    fn a_header_document_goes_out_with_the_name_the_customer_sees() {
        let body = whatsapp_body(&intent(
            Channel::Whatsapp,
            "+34600999888",
            "autumn_menu",
            json!({
                "header_document": "https://cdn.example.com/menu.pdf",
                "header_document_filename": "  Carta de otoño.pdf ",
                "who": "Ana"
            }),
        ))
        .unwrap();
        assert_eq!(
            body["template"]["components"],
            json!([
                { "type": "header", "parameters": [{ "type": "document", "document": {
                    "link": "https://cdn.example.com/menu.pdf",
                    "filename": "Carta de otoño.pdf"
                }}]},
                { "type": "body", "parameters": [
                    {"type": "text", "parameter_name": "who", "text": "Ana"}
                ]}
            ])
        );
    }

    /// A name is ONE file name the chat can print: what a file name cannot carry (a folder
    /// separator, a line break) is not sent, and a name longer than a chat shows is cut on a
    /// character, never inside one.
    #[test]
    fn the_document_name_is_cleaned_of_what_a_file_name_cannot_carry() {
        let name = |raw: Value| {
            let body = whatsapp_body(&intent(
                Channel::Whatsapp,
                "+34600999888",
                "autumn_menu",
                json!({
                    "header_document": "https://cdn.example.com/menu.pdf",
                    "header_document_filename": raw
                }),
            ))
            .unwrap();
            body["template"]["components"][0]["parameters"][0]["document"]["filename"].clone()
        };
        assert_eq!(
            name(json!("Menu/2026\\autumn\r\nlist.pdf")),
            json!("Menu-2026-autumnlist.pdf")
        );
        assert_eq!(name(json!(2026)), json!("2026"));
        let long = "ñ".repeat(MAX_DOCUMENT_NAME_CHARS + 20);
        assert_eq!(
            name(json!(long)),
            json!("ñ".repeat(MAX_DOCUMENT_NAME_CHARS)),
            "cut on a character"
        );
        // Nothing left to print = no name: Meta falls back to the link, as before.
        let body = whatsapp_body(&intent(
            Channel::Whatsapp,
            "+34600999888",
            "autumn_menu",
            json!({
                "header_document": "https://cdn.example.com/menu.pdf",
                "header_document_filename": " \n\t "
            }),
        ))
        .unwrap();
        assert_eq!(
            body["template"]["components"][0]["parameters"][0]["document"],
            json!({ "link": "https://cdn.example.com/menu.pdf" })
        );
    }

    /// A name for a document the message does not carry is a flow that does not know what it
    /// sends: refused before the network, naming the key — on its own, next to a photo, or when
    /// it is not something a chat can print.
    #[test]
    fn a_document_name_without_a_document_header_is_refused_before_the_network() {
        for vars in [
            json!({ "header_document_filename": "Menu.pdf" }),
            json!({ "header_image": "https://a/x.jpg", "header_document_filename": "Menu.pdf" }),
            json!({ "header_text": "Hi", "header_document_filename": "Menu.pdf" }),
            json!({ "header_document": "https://a/x.pdf", "header_document_filename": {"a": 1} }),
            json!({ "header_document": "https://a/x.pdf", "header_document_filename": ["Menu"] }),
        ] {
            let err = whatsapp_body(&intent(
                Channel::Whatsapp,
                "+34600999888",
                "autumn_menu",
                vars.clone(),
            ))
            .expect_err("no document to name");
            assert!(
                format!("{err}").contains("header_document_filename"),
                "{err} for {vars}"
            );
        }
    }

    /// **The PDF the owner UPLOADED is sent with a name she recognises** (hub#2405). The hub keeps
    /// the file under its fingerprint, so the name travels next to it: hers when the step has one
    /// (with the `.pdf` a phone needs to open it), and the template's own name when a step saved
    /// before the field existed has none — never the fingerprint of the signed link.
    #[tokio::test]
    async fn an_uploaded_pdf_goes_out_named_as_the_owner_wrote_it_or_after_its_template() {
        let long = "ñ".repeat(MAX_DOCUMENT_NAME_CHARS);
        let long_sent = format!("{}.pdf", "ñ".repeat(MAX_DOCUMENT_NAME_CHARS - 4));
        for (written, sent) in [
            (Some(json!("Carta de otoño.pdf")), "Carta de otoño.pdf"),
            (Some(json!("Carta de otoño")), "Carta de otoño.pdf"),
            (Some(json!("Tarifa.PDF")), "Tarifa.PDF"),
            // Cut to make room: the extension is what lets the phone open it.
            (Some(json!(long)), long_sent.as_str()),
            (Some(json!("   ")), "autumn_menu.pdf"),
            // A mapped value that came back empty.
            (Some(Value::Null), "autumn_menu.pdf"),
            (None, "autumn_menu.pdf"),
        ] {
            let mut vars = json!({ "header_document": "whatsapp/headers/0b8e.pdf" });
            if let Some(written) = &written {
                vars["header_document_filename"] = written.clone();
            }
            let written = format!("{written:?}");
            let cloud = fake_cloud(StatusCode::OK, json!({"message_id": "wamid.16"})).await;
            transport(&cloud.base_url, Some("machine-tok"))
                .send(
                    &intent(Channel::Whatsapp, "+34600111222", " autumn_menu ", vars),
                    Routing::Tenant,
                    "ev-1",
                )
                .await
                .unwrap_or_else(|e| panic!("{written}: an uploaded PDF is sent: {e}"));
            let calls = cloud.calls();
            assert_eq!(calls.len(), 2, "{written}: sign, then send: {calls:?}");
            assert_eq!(
                calls[1].2["template"]["components"],
                json!([{ "type": "header", "parameters": [{ "type": "document", "document": {
                    "link": "https://objects.example/whatsapp/headers/0b8e.pdf?X-Amz-Signature=s1",
                    "filename": sent
                }}]}]),
                "{written}"
            );
        }
    }

    /// **Each header signs only a file of its own kind** (the extension the door gave it from its
    /// bytes): a stored photo is not a video, a video is not a PDF, and a title that happens to read
    /// like a stored file is the title's text. Nothing is signed for them — a media header naming
    /// the wrong kind is refused as the not-a-link it is, before the network.
    #[tokio::test]
    async fn each_media_header_signs_only_a_stored_file_of_its_own_kind() {
        let cloud = fake_cloud(StatusCode::OK, json!({"message_id": "wamid.13"})).await;
        transport(&cloud.base_url, Some("machine-tok"))
            .send(
                &intent(
                    Channel::Whatsapp,
                    "+34600111222",
                    "autumn_promo",
                    json!({"header_text": "whatsapp/headers/0b8e.jpg"}),
                ),
                Routing::Tenant,
                "ev-1",
            )
            .await
            .expect("a title is sent as written");
        let calls = cloud.calls();
        assert_eq!(calls.len(), 1, "nothing signed for a title: {calls:?}");
        assert_eq!(
            calls[0].2["template"]["components"][0]["parameters"][0]["text"],
            "whatsapp/headers/0b8e.jpg"
        );

        for (key, file) in [
            ("header_video", "whatsapp/headers/0b8e.jpg"),
            ("header_video", "whatsapp/headers/0b8e.pdf"),
            ("header_document", "whatsapp/headers/0b8e.mp4"),
            ("header_document", "whatsapp/headers/0b8e.png"),
            ("header_image", "whatsapp/headers/0b8e.mp4"),
            ("header_image", "whatsapp/headers/0b8e.pdf"),
            ("header_image", "whatsapp/headers/0b8e"),
            ("header_video", "whatsapp/headers/mp4"),
        ] {
            let cloud = fake_cloud(StatusCode::OK, json!({"message_id": "wamid.14"})).await;
            let err = transport(&cloud.base_url, Some("machine-tok"))
                .send(
                    &intent(
                        Channel::Whatsapp,
                        "+34600111222",
                        "autumn_promo",
                        json!({ key: file }),
                    ),
                    Routing::Tenant,
                    "ev-1",
                )
                .await
                .expect_err(file);
            assert!(format!("{err}").contains(key), "{key} {file}: {err}");
            assert!(cloud.calls().is_empty(), "{key} {file}: {:?}", cloud.calls());
        }
    }

    /// A template has ONE header. Two media keys is a flow that does not know which one it meant,
    /// and picking one by precedence would send a message nobody approved.
    #[test]
    fn whatsapp_refuses_two_header_media_before_the_network() {
        let err = whatsapp_body(&intent(
            Channel::Whatsapp,
            "+34600999888",
            "promo",
            json!({"header_image": "https://a/x.jpg", "header_video": "https://a/x.mp4"}),
        ))
        .expect_err("a template has one header");
        let text = format!("{err}");
        assert!(
            text.contains("header_image") && text.contains("header_video"),
            "{text}"
        );
    }

    /// Meta fetches the media itself: anything that is not an http(s) link comes back as an
    /// opaque 400 after the call was paid for — or, blank, as a message without its picture.
    #[test]
    fn whatsapp_refuses_a_header_that_is_not_a_link() {
        for bad in [
            json!("salon.jpg"),
            json!(""),
            json!(7),
            json!("ftp://a/x.jpg"),
        ] {
            let err = whatsapp_body(&intent(
                Channel::Whatsapp,
                "+34600999888",
                "promo",
                json!({ "header_image": bad.clone() }),
            ))
            .expect_err("the header is a link Meta can fetch");
            assert!(format!("{err}").contains("header_image"), "{err} for {bad}");
        }
    }

    /// Free text has no header: dropping the picture silently would send a message the owner did
    /// not write.
    #[test]
    fn whatsapp_free_text_refuses_header_media() {
        let err = whatsapp_body(&intent(
            Channel::Whatsapp,
            "+34600999888",
            "",
            json!({"text": "hola", "header_image": "https://a/x.jpg"}),
        ))
        .expect_err("only a template has a header");
        assert!(format!("{err}").contains("header_image"), "{err}");
    }

    /// A tappable message wins over the template (hub#1633) and returns before the components are
    /// built, so a header riding next to `interactive` would vanish without a word. A flow cannot
    /// pair them (`flows::def` refuses it), but a module emitting the intent can — and it is told.
    #[test]
    fn whatsapp_interactive_refuses_header_media() {
        let err = whatsapp_body(&NotifyIntent {
            interactive: buttons(),
            ..intent(
                Channel::Whatsapp,
                "+34600999888",
                "promo",
                json!({"header_image": "https://a/x.jpg"}),
            )
        })
        .expect_err("a tappable message has no template header");
        assert!(format!("{err}").contains("header_image"), "{err}");
    }

    /// **A template whose text header has a variable** (hub#2111): «Your appointment on {{1}}».
    /// Meta refuses the send unless the `header` component fills that `{{1}}`, and before this the
    /// only way to write it was `vars.components` by hand. `vars.header_text` is the value; it is
    /// never a body variable, and the rest of the vars stay the named body parameters.
    #[test]
    fn whatsapp_template_with_a_header_text_sends_it_as_the_header_parameter() {
        let body = whatsapp_body(&intent(
            Channel::Whatsapp,
            "+34600999888",
            "appointment_reminder",
            json!({"header_text": " 3 October ", "who": "Ana", "button_url_0": "A1"}),
        ))
        .unwrap();
        assert_eq!(
            body["template"]["components"],
            json!([
                { "type": "header", "parameters": [{"type": "text", "text": "3 October"}] },
                { "type": "body", "parameters": [
                    {"type": "text", "parameter_name": "who", "text": "Ana"}
                ]},
                { "type": "button", "sub_type": "url", "index": "0", "parameters": [
                    {"type": "text", "text": "A1"}
                ]}
            ])
        );
    }

    /// A number mapped from the run (a table, a day) is still the header's text, and a template
    /// whose body has no variables still needs its header.
    #[test]
    fn whatsapp_template_header_text_takes_a_number_and_needs_no_body_variables() {
        let body = whatsapp_body(&intent(
            Channel::Whatsapp,
            "+34600999888",
            "table_ready",
            json!({"header_text": 12, "language": "es"}),
        ))
        .unwrap();
        assert_eq!(
            body["template"]["components"],
            json!([{ "type": "header", "parameters": [{"type": "text", "text": "12"}] }])
        );
    }

    /// An empty header value is a title with a hole Meta refuses after the call was paid for; an
    /// object or a list is not a title at all.
    #[test]
    fn whatsapp_refuses_a_header_text_without_a_value() {
        for bad in [
            json!(""),
            json!("   "),
            json!(null),
            json!({"a": 1}),
            json!(["x"]),
        ] {
            let err = whatsapp_body(&intent(
                Channel::Whatsapp,
                "+34600999888",
                "appointment_reminder",
                json!({ "header_text": bad.clone() }),
            ))
            .expect_err("the header's variable needs a value");
            assert!(format!("{err}").contains("header_text"), "{err} for {bad}");
        }
    }

    /// A template has ONE header: a text value next to a media link is a flow that does not know
    /// which header its template has.
    #[test]
    fn whatsapp_refuses_a_header_text_next_to_header_media() {
        let err = whatsapp_body(&intent(
            Channel::Whatsapp,
            "+34600999888",
            "promo",
            json!({"header_text": "Hi", "header_image": "https://a/x.jpg"}),
        ))
        .expect_err("a template has one header");
        let text = format!("{err}");
        assert!(
            text.contains("header_text") && text.contains("header_image"),
            "{text}"
        );
    }

    /// Outside a template (free text or a tappable message) there is no header to fill.
    #[test]
    fn whatsapp_refuses_a_header_text_outside_a_template() {
        let free = whatsapp_body(&intent(
            Channel::Whatsapp,
            "+34600999888",
            "",
            json!({"text": "hola", "header_text": "Hi"}),
        ))
        .expect_err("only a template has a header");
        assert!(format!("{free}").contains("header_text"), "{free}");
        let tappable = whatsapp_body(&NotifyIntent {
            interactive: buttons(),
            ..intent(
                Channel::Whatsapp,
                "+34600999888",
                "promo",
                json!({"header_text": "Hi"}),
            )
        })
        .expect_err("a tappable message has no template header");
        assert!(format!("{tappable}").contains("header_text"), "{tappable}");
    }

    /// **A template's link button with a variable end** (hub#2110): «See your appointment»
    /// pointing at `https://…/c/{{1}}`. Meta refuses the send unless the `button` component
    /// carries that end, and before this the only way to write it was `vars.components` by hand.
    /// `vars.button_url_<n>` is the end of the button at position `<n>`; the buttons follow the
    /// header and the body.
    #[test]
    fn whatsapp_template_with_url_buttons_sends_their_variable_part() {
        let body = whatsapp_body(&intent(
            Channel::Whatsapp,
            "+34600999888",
            "appointment_confirmed",
            json!({
                "button_url_1": "pay/A1B2",
                "who": "Ana",
                "header_image": "https://cdn.example.com/salon.jpg",
                "button_url_0": 4521,
            }),
        ))
        .unwrap();
        assert_eq!(
            body["template"]["components"],
            json!([
                { "type": "header", "parameters": [
                    {"type": "image", "image": {"link": "https://cdn.example.com/salon.jpg"}}
                ]},
                { "type": "body", "parameters": [
                    {"type": "text", "parameter_name": "who", "text": "Ana"}
                ]},
                { "type": "button", "sub_type": "url", "index": "0", "parameters": [
                    {"type": "text", "text": "4521"}
                ]},
                { "type": "button", "sub_type": "url", "index": "1", "parameters": [
                    {"type": "text", "text": "pay/A1B2"}
                ]}
            ])
        );
    }

    /// A template whose only variable is the button's end still sends it.
    #[test]
    fn whatsapp_template_url_button_needs_no_body_variables() {
        let body = whatsapp_body(&intent(
            Channel::Whatsapp,
            "+34600999888",
            "order_ready",
            json!({ "button_url_0": " R-77 ", "language": "es" }),
        ))
        .unwrap();
        assert_eq!(
            body["template"]["components"],
            json!([{ "type": "button", "sub_type": "url", "index": "0", "parameters": [
                {"type": "text", "text": "R-77"}
            ]}])
        );
    }

    /// An empty end is a link to the bare prefix — the customer taps «Pay» and lands nowhere — and
    /// Meta answers an opaque 400 after the call was paid for. Refused before the network.
    #[test]
    fn whatsapp_refuses_a_url_button_without_a_value() {
        for bad in [
            json!(""),
            json!("   "),
            json!(null),
            json!({}),
            json!([]),
            json!(true),
        ] {
            let err = whatsapp_body(&intent(
                Channel::Whatsapp,
                "+34600999888",
                "order_ready",
                json!({ "button_url_0": bad.clone() }),
            ))
            .expect_err("the button's end is text Meta appends to the link");
            assert!(format!("{err}").contains("button_url_0"), "{err} for {bad}");
        }
    }

    /// A near miss of the key is a typo, not a body variable named `button_url_x` that Meta would
    /// refuse with a message nobody can read.
    #[test]
    fn whatsapp_refuses_a_malformed_url_button_key() {
        for key in ["button_url_", "button_url_10", "button_url_x"] {
            let err = whatsapp_body(&intent(
                Channel::Whatsapp,
                "+34600999888",
                "order_ready",
                json!({ key: "A1" }),
            ))
            .expect_err("the position is one digit");
            assert!(format!("{err}").contains(key), "{err} for {key}");
        }
    }

    /// Only a template has buttons: next to free text or a tappable message the end would vanish
    /// without a word.
    #[test]
    fn whatsapp_refuses_a_url_button_outside_a_template() {
        let free_text = intent(
            Channel::Whatsapp,
            "+34600999888",
            "",
            json!({"text": "hola", "button_url_0": "A1"}),
        );
        let tappable = NotifyIntent {
            interactive: buttons(),
            ..intent(
                Channel::Whatsapp,
                "+34600999888",
                "promo",
                json!({"button_url_0": "A1"}),
            )
        };
        for intent in [free_text, tappable] {
            let err = whatsapp_body(&intent).expect_err("only a template has link buttons");
            assert!(format!("{err}").contains("button_url_0"), "{err}");
        }
    }
}
