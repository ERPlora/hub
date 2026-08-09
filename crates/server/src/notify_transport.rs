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
    Channel, MockTransport, NotifyIntent, NotifyTransport, Routing, SendOutcome,
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
    async fn post(&self, request: &PreparedRequest, body: &Value) -> Result<SendOutcome> {
        let mut builder = self.http.post(&request.url).json(body);
        for (name, value) in &request.headers {
            builder = builder.header(*name, value);
        }

        let response = builder
            .send()
            .await
            .map_err(|e| RuntimeError::Notify(format!("notify proxy unreachable: {e}")))?;

        let status = response.status();
        if status.is_success() {
            return Ok(SendOutcome::Sent);
        }

        // The reason has to reach whoever reads the dead-letter row: `quota_exceeded`,
        // `no_whatsapp_number` and `invalid_recipients` each need a different human action, and a
        // bare status code names none of them. Even a terminal reason travels as `Err`: the trait
        // has no terminal variant, so it retries with backoff and then dead-letters (`outbox.rs`).
        let detail: String = response
            .text()
            .await
            .unwrap_or_default()
            .trim()
            .chars()
            .take(MAX_DETAIL)
            .collect();
        Err(RuntimeError::Notify(format!(
            "notify proxy answered {status}: {detail}"
        )))
    }
}

#[async_trait]
impl NotifyTransport for CloudNotifyTransport {
    async fn send(&self, intent: &NotifyIntent, _routing: Routing) -> Result<SendOutcome> {
        // The credential first: with no machine token there is nothing to send WITH, so there is
        // no point building a body or opening a socket.
        let auth = self.machine_auth()?;

        let (request, body) =
            match intent.channel {
                Channel::Email => (self.cloud.notify_email(&auth), email_body(intent)?),
                Channel::Whatsapp => (self.cloud.notify_whatsapp(&auth), whatsapp_body(intent)?),
                Channel::Sms => return Err(RuntimeError::Notify(
                    "the sms channel has no transport yet: the SaaS proxies email and whatsapp \
                     only (ADR-0283 §5), and the hub holds no sms credential of its own"
                        .to_string(),
                )),
            };
        self.post(&request, &body).await
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
    let mut body = json!({ "to": intent.to.trim() });
    // Optional: one of THIS hub's numbers. A foreign one is a 404 at the proxy, by design.
    if let Some(phone_number_id) = var_str(intent, "phone_number_id") {
        body["phone_number_id"] = json!(phone_number_id);
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
    if let Some(components) = template_components(intent) {
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
/// them by name, so the order is only ours to keep stable — and testable).
fn template_components(intent: &NotifyIntent) -> Option<Value> {
    if let Some(explicit) = intent.vars.get("components").filter(|v| v.is_array()) {
        return Some(explicit.clone());
    }

    let mut named: Vec<(&String, &Value)> = intent
        .vars
        .as_object()?
        .iter()
        .filter(|(key, _)| !RESERVED_VARS.contains(&key.as_str()))
        .collect();
    if named.is_empty() {
        return None;
    }
    named.sort_by(|a, b| a.0.cmp(b.0));

    let parameters: Vec<Value> = named
        .into_iter()
        .map(
            |(key, value)| json!({ "type": "text", "parameter_name": key, "text": as_text(value) }),
        )
        .collect();
    Some(json!([{ "type": "body", "parameters": parameters }]))
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

        let seen: Seen = Arc::new(Mutex::new(Vec::new()));
        let app = Router::new()
            .route("/api/v1/hub/device/notify/email/", post(record))
            .route("/api/v1/hub/device/notify/whatsapp/", post(record))
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
        }
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
            )
            .await
            .expect("a 200 from the proxy is a send");
        assert_eq!(sent, SendOutcome::Sent);

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
            )
            .await
            .expect_err("a 502 from the proxy is not a delivery");
        assert!(matches!(err, RuntimeError::Notify(_)), "got {err:?}");
        assert_eq!(cloud.calls().len(), 1, "it did try");
    }

    /// Quota exhausted is still an error, never a silent success — the message did not go out.
    #[tokio::test]
    async fn quota_exceeded_is_not_a_delivery() {
        let cloud = fake_cloud(
            StatusCode::TOO_MANY_REQUESTS,
            json!({"error": "quota_exceeded"}),
        )
        .await;
        let err = transport(&cloud.base_url, Some("machine-tok"))
            .send(
                &intent(Channel::Whatsapp, "+34600999888", "reminder", json!({})),
                Routing::CloudProxy,
            )
            .await
            .unwrap_err();
        assert!(
            format!("{err}").contains("quota_exceeded"),
            "the reason has to reach the dead-letter screen: {err}"
        );
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
}
