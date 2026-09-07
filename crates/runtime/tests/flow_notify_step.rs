//! **A flow writes to the CUSTOMER** — the `notify` step and the `recipient_query` grant (hub#821,
//! ADR-0283 §5 / `architecture/hub/flows.md` §5).
//!
//! Until this landed a flow could only reach the ALLOW-LIST of `hub_settings` or the email of a
//! hub user — the staff. Every case that pays for the kernel (an appointment reminder, a WhatsApp
//! confirmation, a survey after the till closes) is a message to a customer, and customers live in
//! a module's table, not in the core.
//!
//! ```text
//!   notify step ─▶ notify grant (channel) ─▶ recipient_query grant (one query # one field)
//!                        │                             │
//!                        │                    read, read-only, with the flow's own context
//!                        ▼                             ▼
//!            _event_outbox row `flow.reminder.due` + resolved_via: flow_grant:<id>
//!                        │
//!            relay ─▶ deliver_host_notify ─▶ BOTH grants re-read, ALIVE ─▶ transport
//! ```
//!
//! The properties pinned here, and why a unit test could not:
//!
//! - **No grant, nothing leaves.** With its positive twin in the same test, so the zero means
//!   something.
//! - **The grant names ONE FIELD of ONE QUERY.** Another field or another query is a different
//!   permission with the same default answer.
//! - **Revoking cuts a message that is ALREADY QUEUED.** This is the whole reason the release is
//!   re-checked at delivery and not only when the event was built: the queue is durable, retried
//!   and delayed, so "I revoked it" has to mean the message does not go.
//! - **The three gates of hub#240 are untouched for a module.** A module that copies a live
//!   `resolved_via` into its own `*.reminder.due` payload gets nowhere: the release belongs to the
//!   flow that produced the run, and a module event has no run.
//! - **A free address never becomes a recipient**: the document has no syntax for one.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::flows::grants::{GrantKind, GrantSpec};
use erplora_runtime::flows::{store, NewFlow};
use erplora_runtime::host_notify::MockTransport;
use erplora_runtime::{RequestContext, Runtime};
use serde_json::{json, Value};

const HUB: &str = "hub-notify-e2e";
const PHONE: &str = "+34600111222";
const EMAIL: &str = "marta@example.com";

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_flows")
        .join(name)
}

fn owner() -> RequestContext {
    RequestContext::new(HUB, "hub_user:owner", ["crm.change_customer".to_string()])
}

/// A hub with the CRM module installed, one customer in it, and a transport that records instead
/// of sending. The transport is the assertion surface: what came out of the hub, and nothing else.
async fn runtime() -> (Runtime, MockTransport) {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture("crm")).await.unwrap();

    let transport = MockTransport::new();
    rt.set_notify_transport(std::sync::Arc::new(transport.clone()));

    let mut p = Params::new();
    p.insert("hub".into(), json!(HUB));
    p.insert("email".into(), json!(EMAIL));
    p.insert("phone".into(), json!(PHONE));
    rt.db_for_test()
        .execute(
            "INSERT INTO crm_customer (id, hub_id, email, phone) \
             VALUES ('c-1', :hub, :email, :phone)",
            &p,
        )
        .await
        .unwrap();
    (rt, transport)
}

/// «When this run happens, message that customer» — the shape the whole issue exists for.
fn reminder(channel: &str, query: &str, field: &str) -> Value {
    json!({
        "schema_version": 1,
        "steps": [{
            "id": "remind",
            "kind": "notify",
            "channel": channel,
            "to": { "query": query, "params": { "id": "input.customer_id" }, "field": field },
            "template": "appointment_reminder",
            "vars": { "text": "Te esperamos el {{input.when}}" }
        }]
    })
}

async fn create_flow(rt: &Runtime, definition: Value) -> String {
    rt.create_flow(
        &NewFlow {
            name: "Reminder".into(),
            enabled: true,
            definition,
        },
        "hub_user:owner",
    )
    .await
    .unwrap()
    .id
}

async fn set_grants(rt: &Runtime, flow_id: &str, wanted: &[GrantSpec]) {
    rt.replace_flow_grants(flow_id, wanted, "hub_user:owner")
        .await
        .unwrap();
}

fn both_grants() -> Vec<GrantSpec> {
    vec![
        GrantSpec::pair(GrantKind::Notify, "whatsapp"),
        GrantSpec::pair(GrantKind::RecipientQuery, "crm.customer.get#phone"),
    ]
}

/// Starts the flow by hand and advances the tick until the step is over.
async fn run_flow(rt: &Runtime, flow_id: &str) -> String {
    let run_id = rt
        .start_flow_run(
            flow_id,
            &json!({ "customer_id": "c-1", "when": "martes" }),
            "hub_user:owner",
        )
        .await
        .unwrap();
    rt.process_flows().await.unwrap();
    run_id
}

async fn rows(rt: &Runtime, sql: &str) -> Vec<Value> {
    rt.db_for_test()
        .query(sql, &Params::new())
        .await
        .unwrap()
        .rows
}

/// The queued host-notify events of this hub, whatever their state.
async fn queued_notifications(rt: &Runtime) -> Vec<Value> {
    rows(
        rt,
        "SELECT id, event_name, status, last_error, module_id, run_id, payload \
         FROM _event_outbox WHERE event_name LIKE '%.reminder.due' ORDER BY created_at",
    )
    .await
}

// ── the grant is the gate ─────────────────────────────────────────────────────────────────────

/// Without a `recipient_query` grant NOTHING leaves — and with it, exactly one message does. The
/// two halves are one test on purpose: a zero that is never contrasted with a one is a test that
/// passes when the feature is missing entirely.
#[tokio::test]
async fn without_the_recipient_grant_nothing_is_sent_and_with_it_exactly_one_message_is() {
    let (rt, transport) = runtime().await;
    let flow_id = create_flow(&rt, reminder("whatsapp", "crm.customer.get", "phone")).await;
    // The channel, but not whose address: the two questions are two grants.
    set_grants(&rt, &flow_id, &[GrantSpec::pair(GrantKind::Notify, "whatsapp")]).await;

    let run_id = run_flow(&rt, &flow_id).await;

    assert!(
        queued_notifications(&rt).await.is_empty(),
        "nothing was even queued, so there is nothing for the relay to send"
    );
    rt.drain_outbox().await.unwrap();
    assert!(transport.sent().is_empty(), "nothing left the hub");
    let (run, _) = rt.get_flow_run(&run_id).await.unwrap();
    assert_eq!(run.status, store::STATUS_FAILED);
    assert!(
        run.last_error.contains("flow.grant_denied"),
        "the run says which permission was missing: {}",
        run.last_error
    );

    // The same flow, the same input, one grant more.
    set_grants(&rt, &flow_id, &both_grants()).await;
    run_flow(&rt, &flow_id).await;
    assert_eq!(
        queued_notifications(&rt).await.len(),
        1,
        "one step, one message"
    );
    rt.drain_outbox().await.unwrap();

    let sent = transport.sent();
    assert_eq!(sent.len(), 1, "exactly one message came out of the hub");
    assert_eq!(
        sent[0].0.to, PHONE,
        "the recipient came from the customer's row"
    );
    assert_eq!(sent[0].0.template, "appointment_reminder");
    assert_eq!(
        sent[0].0.vars["text"],
        json!("Te esperamos el martes"),
        "the copy was rendered against the run"
    );
}

/// A grant authorises **one field of one query**. Asking for another field of the same query, or
/// the same field of another query, is a different permission with the same default answer.
#[tokio::test]
async fn the_grant_covers_one_field_of_one_query_and_nothing_next_to_it() {
    let (rt, transport) = runtime().await;
    let phone_grant = GrantSpec::pair(GrantKind::RecipientQuery, "crm.customer.get#phone");

    // Another FIELD of the granted query: the customer's email is not their phone.
    let by_email = create_flow(&rt, reminder("email", "crm.customer.get", "email")).await;
    set_grants(
        &rt,
        &by_email,
        &[GrantSpec::pair(GrantKind::Notify, "email"), phone_grant.clone()],
    )
    .await;
    let run_id = run_flow(&rt, &by_email).await;
    let (run, _) = rt.get_flow_run(&run_id).await.unwrap();
    assert_eq!(run.status, store::STATUS_FAILED);
    assert!(
        run.last_error.contains("flow.grant_denied"),
        "{}",
        run.last_error
    );

    // Another QUERY, same field name: a grant over the notes does not open the customers.
    let other_query = create_flow(&rt, reminder("whatsapp", "crm.customer.list", "phone")).await;
    set_grants(
        &rt,
        &other_query,
        &[
            GrantSpec::pair(GrantKind::Notify, "whatsapp"),
            GrantSpec::pair(GrantKind::RecipientQuery, "crm.customer.get#phone"),
        ],
    )
    .await;
    let run_id = run_flow(&rt, &other_query).await;
    let (run, _) = rt.get_flow_run(&run_id).await.unwrap();
    assert_eq!(run.status, store::STATUS_FAILED);
    assert!(
        run.last_error.contains("flow.grant_denied"),
        "{}",
        run.last_error
    );

    rt.drain_outbox().await.unwrap();
    assert!(transport.sent().is_empty(), "neither run reached anybody");
    assert!(queued_notifications(&rt).await.is_empty());
}

// ── the property this design exists for ───────────────────────────────────────────────────────

/// **Revoking the grant cuts a message that is already queued.**
///
/// The queue is durable and retried, so between "the flow decided to write to this customer" and
/// "the message leaves the hub" there can be minutes and a restart. If the release were only
/// checked when the event was built, revoking a grant would stop the NEXT message and let the one
/// in the queue through — and «I revoked it» has to mean the message does not go.
#[tokio::test]
async fn revoking_the_recipient_grant_cuts_a_message_that_is_already_queued() {
    let (rt, transport) = runtime().await;
    let flow_id = create_flow(&rt, reminder("whatsapp", "crm.customer.get", "phone")).await;
    set_grants(&rt, &flow_id, &both_grants()).await;

    run_flow(&rt, &flow_id).await;
    let queued = queued_notifications(&rt).await;
    assert_eq!(queued.len(), 1, "the message is in the queue, not yet out");
    assert_eq!(queued[0]["status"], json!("pending"));
    assert!(transport.sent().is_empty(), "nothing has left yet");

    // The owner changes their mind while the relay has not run.
    set_grants(&rt, &flow_id, &[GrantSpec::pair(GrantKind::Notify, "whatsapp")]).await;
    rt.drain_outbox().await.unwrap();

    assert!(
        transport.sent().is_empty(),
        "a revoked grant stops a message that was already queued"
    );
    let queued = queued_notifications(&rt).await;
    assert_ne!(
        queued[0]["status"],
        json!("delivered"),
        "and the row is NOT marked delivered: it retries and dies in dead-letter, visibly"
    );
    assert!(
        queued[0]["last_error"]
            .as_str()
            .unwrap_or_default()
            .contains("grant"),
        "the queue says why it did not go: {}",
        queued[0]["last_error"]
    );
}

/// The twin: revoking the CHANNEL cuts it too. The two grants are separate on purpose — a flow may
/// be allowed to send email and not WhatsApp, which costs money per message — so each of them is a
/// live veto of its own.
#[tokio::test]
async fn revoking_the_channel_grant_also_cuts_a_message_that_is_already_queued() {
    let (rt, transport) = runtime().await;
    let flow_id = create_flow(&rt, reminder("whatsapp", "crm.customer.get", "phone")).await;
    set_grants(&rt, &flow_id, &both_grants()).await;
    run_flow(&rt, &flow_id).await;
    assert_eq!(queued_notifications(&rt).await.len(), 1);

    set_grants(
        &rt,
        &flow_id,
        &[GrantSpec::pair(GrantKind::RecipientQuery, "crm.customer.get#phone")],
    )
    .await;
    rt.drain_outbox().await.unwrap();

    assert!(
        transport.sent().is_empty(),
        "the channel grant is a live veto too, not a save-time formality"
    );
}

/// Deleting the whole flow revokes everything it had (`revoke_all`), so the queue empties itself
/// of that flow's messages for the same reason: a hub does not act on a withdrawn instruction.
#[tokio::test]
async fn deleting_the_flow_cuts_the_messages_it_had_already_queued() {
    let (rt, transport) = runtime().await;
    let flow_id = create_flow(&rt, reminder("whatsapp", "crm.customer.get", "phone")).await;
    set_grants(&rt, &flow_id, &both_grants()).await;
    run_flow(&rt, &flow_id).await;
    assert_eq!(queued_notifications(&rt).await.len(), 1);

    rt.delete_flow(&flow_id, "hub_user:owner").await.unwrap();
    rt.drain_outbox().await.unwrap();

    assert!(
        transport.sent().is_empty(),
        "the flow is gone; so is its message"
    );
}

// ── what a module cannot borrow ───────────────────────────────────────────────────────────────

/// **The three gates of hub#240 are untouched.** A module that copies a live `resolved_via` into
/// its own `*.reminder.due` payload does not get the flow's release: the release belongs to the
/// run that produced the event, and a module's event has no run. Its recipient still has to come
/// from the hub's own data.
#[tokio::test]
async fn a_module_cannot_borrow_a_flows_release_by_copying_it_into_its_payload() {
    let (rt, transport) = runtime().await;
    let flow_id = create_flow(&rt, reminder("whatsapp", "crm.customer.get", "phone")).await;
    set_grants(&rt, &flow_id, &both_grants()).await;

    // A real, live release id — the strongest version of the attack: nothing here is guessed.
    let live = rt.list_flow_grants(&flow_id).await.unwrap();
    let release = live
        .iter()
        .find(|g| g.kind == "recipient_query")
        .map(|g| format!("flow_grant:{}", g.id))
        .expect("the flow has a live recipient_query grant");

    // The module has `notify` declared AND granted, and the channel it declares — gates 1 and 2
    // open. Gate 3 is the one being tested.
    rt.set_module_capability("crm", "notify", true, "hub_user:owner")
        .await
        .unwrap();

    let mut p = Params::new();
    p.insert("channel".into(), json!("email"));
    p.insert("to".into(), json!("atacante@evil.test"));
    p.insert("template".into(), json!("x"));
    p.insert("vars".into(), json!({ "text": "hola" }));
    p.insert("resolved_via".into(), json!(release));
    rt.execute_command("crm.reminder.send", &p, &owner())
        .await
        .unwrap();
    rt.drain_outbox().await.unwrap();

    assert!(
        transport.sent().is_empty(),
        "a module's free address is refused however the payload dresses it up"
    );

    // The sharper version: the same command run BY A FLOW, so the outbox row really does carry a
    // `run_id` of the flow that owns the release. It is still a module's event — `module_id` says
    // so — and a module's event goes through the three gates, whatever its payload claims.
    let laundering = create_flow(
        &rt,
        json!({
            "schema_version": 1,
            "steps": [{
                "id": "launder", "kind": "command", "command": "crm.reminder.send",
                "params": {
                    "channel": "email", "to": "atacante@evil.test", "template": "x",
                    "vars": { "text": "hola" }, "resolved_via": release
                }
            }]
        }),
    )
    .await;
    set_grants(
        &rt,
        &laundering,
        &[GrantSpec::pair(GrantKind::Command, "crm.reminder.send")],
    )
    .await;
    rt.start_flow_run(&laundering, &json!({}), "hub_user:owner")
        .await
        .unwrap();
    rt.process_flows().await.unwrap();
    rt.drain_outbox().await.unwrap();

    assert!(
        transport.sent().is_empty(),
        "a flow cannot launder a free address through a module command either: the release belongs \
         to the KERNEL's own row, and a module's event carries its module"
    );
}

// ── the document has no syntax for a free address ─────────────────────────────────────────────

/// A literal recipient is not "discouraged": it cannot be written. `to` is a query and a field, so
/// there is no shape a flow author (or a template from the marketplace) could use to type an
/// address in, and no path by which one from the event payload could become one.
#[tokio::test]
async fn a_flow_document_cannot_name_a_recipient_by_hand() {
    let (rt, _transport) = runtime().await;
    for to in [
        json!("atacante@evil.test"),
        json!("{{input.email}}"),
        json!({ "address": "atacante@evil.test" }),
        json!({ "query": "crm.customer.get", "params": {}, "field": "phone", "address": "x@y.z" }),
    ] {
        let definition = json!({
            "schema_version": 1,
            "steps": [{
                "id": "remind", "kind": "notify", "channel": "email", "to": to,
                "vars": { "text": "hola" }
            }]
        });
        rt.create_flow(
            &NewFlow {
                name: "N".into(),
                enabled: true,
                definition,
            },
            "hub_user:owner",
        )
        .await
        .expect_err("a `to` that is not one field of one query is not a flow document");
    }
}

// ── what the query answers, and what it does not ──────────────────────────────────────────────

/// A query that finds nobody, or finds several, does not send. Picking "the first" would make the
/// recipient depend on a row order nobody declared, and fanning out would turn a grant for one
/// message into a campaign nobody authorised.
#[tokio::test]
async fn no_recipient_and_several_recipients_both_stop_the_step_instead_of_guessing() {
    let (rt, transport) = runtime().await;

    // Nobody: the run's input names a customer that is not in the table.
    let flow_id = create_flow(&rt, reminder("whatsapp", "crm.customer.get", "phone")).await;
    set_grants(&rt, &flow_id, &both_grants()).await;
    let run_id = rt
        .start_flow_run(
            &flow_id,
            &json!({ "customer_id": "ghost" }),
            "hub_user:owner",
        )
        .await
        .unwrap();
    rt.process_flows().await.unwrap();
    let (run, _) = rt.get_flow_run(&run_id).await.unwrap();
    assert_eq!(run.status, store::STATUS_FAILED);
    assert!(
        run.last_error.contains("flow.recipient_not_found"),
        "{}",
        run.last_error
    );

    // Several: a second customer, and a query that returns them all.
    let mut p = Params::new();
    p.insert("hub".into(), json!(HUB));
    rt.db_for_test()
        .execute(
            "INSERT INTO crm_customer (id, hub_id, email, phone) \
             VALUES ('c-2', :hub, 'otro@example.com', '+34600333444')",
            &p,
        )
        .await
        .unwrap();
    let many = create_flow(&rt, reminder("whatsapp", "crm.customer.list", "phone")).await;
    set_grants(
        &rt,
        &many,
        &[
            GrantSpec::pair(GrantKind::Notify, "whatsapp"),
            GrantSpec::pair(GrantKind::RecipientQuery, "crm.customer.list#phone"),
        ],
    )
    .await;
    let run_id = run_flow(&rt, &many).await;
    let (run, _) = rt.get_flow_run(&run_id).await.unwrap();
    assert_eq!(run.status, store::STATUS_FAILED);
    assert!(
        run.last_error.contains("flow.recipient_ambiguous"),
        "{}",
        run.last_error
    );

    rt.drain_outbox().await.unwrap();
    assert!(transport.sent().is_empty());
    assert!(
        queued_notifications(&rt).await.is_empty(),
        "nothing was queued either"
    );
}

/// A value that cannot be a recipient for the channel is refused with the same conservative rules
/// `host.notify` has always applied — before anything is queued, so the refusal is on the run and
/// not eight retries later in a dead-letter.
#[tokio::test]
async fn a_field_that_does_not_look_like_a_phone_is_refused_before_anything_is_queued() {
    let (rt, transport) = runtime().await;
    // The customer's EMAIL is a perfectly good value — for the email channel. Sent as a WhatsApp
    // number it is not a recipient.
    let flow_id = create_flow(&rt, reminder("whatsapp", "crm.customer.get", "email")).await;
    set_grants(
        &rt,
        &flow_id,
        &[
            GrantSpec::pair(GrantKind::Notify, "whatsapp"),
            GrantSpec::pair(GrantKind::RecipientQuery, "crm.customer.get#email"),
        ],
    )
    .await;

    let run_id = run_flow(&rt, &flow_id).await;
    let (run, _) = rt.get_flow_run(&run_id).await.unwrap();
    assert_eq!(run.status, store::STATUS_FAILED);
    assert!(
        run.last_error.contains("flow.recipient_invalid"),
        "{}",
        run.last_error
    );
    rt.drain_outbox().await.unwrap();
    assert!(transport.sent().is_empty());
    assert!(queued_notifications(&rt).await.is_empty());
}

// ── the run history ───────────────────────────────────────────────────────────────────────────

/// The resolved recipient is a **customer's phone number**. The run history is read hours later by
/// whoever is debugging, and it does not need it: the step records WHICH query and WHICH field the
/// address came from, marked `redacted`, and never the address itself (hub#666 for secrets,
/// hub#715 for personal data — same criterion, minimisation, not anonymisation).
#[tokio::test]
async fn the_run_history_says_where_the_recipient_came_from_and_never_who_it_was() {
    let (rt, transport) = runtime().await;
    let flow_id = create_flow(&rt, reminder("whatsapp", "crm.customer.get", "phone")).await;
    set_grants(&rt, &flow_id, &both_grants()).await;
    let run_id = run_flow(&rt, &flow_id).await;
    rt.drain_outbox().await.unwrap();
    assert_eq!(transport.sent().len(), 1, "it really did go out");

    let (run, steps) = rt.get_flow_run(&run_id).await.unwrap();
    assert_eq!(run.status, store::STATUS_DONE);
    assert_eq!(steps.len(), 1);
    assert_eq!(steps[0].status, "done");
    assert_eq!(steps[0].input["to"]["query"], json!("crm.customer.get"));
    assert_eq!(steps[0].input["to"]["field"], json!("phone"));
    assert_eq!(
        steps[0].output["recipient_redacted"],
        json!(true),
        "the history says a recipient was withheld, rather than quietly omitting it"
    );

    let history = format!("{:?}{:?}", steps, run);
    assert!(
        !history.contains(PHONE),
        "a customer's phone number is not part of a run's history: {history}"
    );
}

// ── quota exhausted is terminal NOW, and still an operator's to retry (hub#971) ──────────────

/// The Cloud proxy answering «quota exceeded» is not a stumble: the eighth attempt, minutes later,
/// meets the same wall as the first. So the row dies on the FIRST pass — but unlike a revoked
/// release (hub#827) the cause CAN come back (a top-up, next month), so the row stays retryable by
/// hand: `failure_kind` empty, recipient kept, and the reason readable in `last_error`.
#[tokio::test]
async fn quota_exceeded_dies_on_the_first_pass_but_stays_retryable_by_hand() {
    let (mut rt, _recording) = runtime().await;
    rt.set_notify_transport(std::sync::Arc::new(MockTransport::quota_exhausted()));
    let flow_id = create_flow(&rt, reminder("whatsapp", "crm.customer.get", "phone")).await;
    set_grants(&rt, &flow_id, &both_grants()).await;
    run_flow(&rt, &flow_id).await;

    rt.drain_outbox().await.unwrap();

    let queued = rows(
        &rt,
        "SELECT status, attempts, failure_kind, last_error, payload FROM _event_outbox \
         WHERE event_name LIKE '%.reminder.due'",
    )
    .await;
    assert_eq!(queued.len(), 1);
    assert_eq!(
        queued[0]["status"],
        json!("dead"),
        "no ladder: {:?}",
        queued[0]
    );
    assert_eq!(
        queued[0]["failure_kind"],
        json!(""),
        "an operator may retry after a top-up"
    );
    assert!(
        queued[0]["last_error"]
            .as_str()
            .unwrap_or_default()
            .contains("quota"),
        "the queue says why: {}",
        queued[0]["last_error"]
    );
    assert!(
        queued[0]["payload"]
            .as_str()
            .unwrap_or_default()
            .contains(PHONE),
        "the recipient is kept: a manual retry has to have someone to dial"
    );
}

/// The control: a transport that merely fails keeps its backoff ladder — after one pass the row is
/// still `pending`. Without this the test above would pass against a relay that kills everything.
#[tokio::test]
async fn a_transport_that_merely_fails_still_climbs_the_ladder() {
    let (mut rt, _recording) = runtime().await;
    rt.set_notify_transport(std::sync::Arc::new(MockTransport::failing()));
    let flow_id = create_flow(&rt, reminder("whatsapp", "crm.customer.get", "phone")).await;
    set_grants(&rt, &flow_id, &both_grants()).await;
    run_flow(&rt, &flow_id).await;

    rt.drain_outbox().await.unwrap();

    let queued = rows(
        &rt,
        "SELECT status, attempts FROM _event_outbox WHERE event_name LIKE '%.reminder.due'",
    )
    .await;
    assert_eq!(queued[0]["status"], json!("pending"), "{:?}", queued[0]);
    assert_eq!(queued[0]["attempts"], json!(1));
}


/// **The whole point of hub#1633, end to end**: the salon's automation offers the free slots as
/// something the customer TAPS, and what comes out of the hub is the message Meta will paint.
///
/// It runs the same road as any other reminder — grants, the recipient read, the outbox — because
/// the options are copy, not a second kind of send. What this proves is the half a unit test
/// cannot: that the object survives the queue row and reaches the transport rendered, and that
/// nothing else about the message changed on the way.
#[tokio::test]
async fn a_flow_offers_the_customer_options_to_tap_and_they_reach_the_transport_rendered() {
    let (rt, transport) = runtime().await;
    let flow_id = create_flow(
        &rt,
        json!({
            "schema_version": 1,
            "steps": [{
                "id": "ask",
                "kind": "notify",
                "channel": "whatsapp",
                "to": { "query": "crm.customer.get", "params": { "id": "input.customer_id" },
                        "field": "phone" },
                "interactive": {
                    "type": "list",
                    "body": { "text": "Estos son los huecos del {{input.when}}" },
                    "action": {
                        "button": "Ver huecos",
                        "sections": [{ "title": "Mañana", "rows": [
                            { "id": "slot:10:30", "title": "{{input.when}} 10:30" },
                            { "id": "slot:12:00", "title": "{{input.when}} 12:00" }
                        ] }]
                    }
                }
            }]
        }),
    )
    .await;
    set_grants(&rt, &flow_id, &both_grants()).await;
    run_flow(&rt, &flow_id).await;

    rt.drain_outbox().await.unwrap();

    let sent = transport.sent();
    assert_eq!(sent.len(), 1, "one run, one message");
    let intent = &sent[0].0;
    assert_eq!(intent.to, PHONE);
    assert_eq!(
        intent.interactive["body"]["text"],
        json!("Estos son los huecos del martes"),
        "the copy of a tappable message is rendered against the run like any other"
    );
    assert_eq!(
        intent.interactive["action"]["sections"][0]["rows"][0]["title"],
        json!("martes 10:30"),
        "the templates INSIDE the options resolve too, however deep they sit"
    );
    assert_eq!(
        intent.interactive["action"]["sections"][0]["rows"][0]["id"],
        json!("slot:10:30"),
        "the id is what comes back as `reply_id`, so it must survive untouched"
    );

    // The control: an ordinary reminder still carries no options at all, so the assertion above
    // is about what this flow asked for and not about something every message now grows.
    let plain_id = create_flow(&rt, reminder("whatsapp", "crm.customer.get", "phone")).await;
    set_grants(&rt, &plain_id, &both_grants()).await;
    run_flow(&rt, &plain_id).await;
    rt.drain_outbox().await.unwrap();

    let sent = transport.sent();
    assert_eq!(sent.len(), 2);
    assert!(
        sent[1].0.interactive.is_null(),
        "a plain reminder offers nothing to tap: {:?}",
        sent[1].0.interactive
    );
}

/// **The whole point of hub#1641, end to end**: the list is ALREADY in the database, so nothing
/// asks a language model to read it out loud. A `query` step publishes it whole, and the tappable
/// message names it with ONE bare path — `steps.<id>.options` — which is exactly the mapping the
/// kernel could already resolve. Nothing indexes an array anywhere along the road.
///
/// What this proves that a unit test cannot: the list survives the run scope, the outbox row and
/// the relay, and reaches the transport as the rows Meta will paint.
#[tokio::test]
async fn a_read_fills_the_tappable_list_and_it_reaches_the_transport_whole() {
    let (rt, transport) = runtime().await;
    for (id, text) in [("n-1", "martes 10:30"), ("n-2", "martes 12:00")] {
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        p.insert("hub".into(), json!(HUB));
        p.insert("text".into(), json!(text));
        rt.db_for_test()
            .execute(
                "INSERT INTO crm_note (id, hub_id, created_by, customer_id, text) \
                 VALUES (:id, :hub, 'seed', 'c-1', :text)",
                &p,
            )
            .await
            .unwrap();
    }

    let flow_id = create_flow(
        &rt,
        json!({
            "schema_version": 1,
            "steps": [
                { "id": "free", "kind": "query", "query": "crm.note.list", "limit": 5,
                  "result": "options",
                  "options": { "id": "id", "title": "text", "description": "customer_id" } },
                { "id": "ask", "kind": "notify", "channel": "whatsapp",
                  "to": { "query": "crm.customer.get", "params": { "id": "input.customer_id" },
                          "field": "phone" },
                  "interactive": {
                      "type": "list",
                      "body": { "text": "Estos son los huecos del {{input.when}}" },
                      "action": {
                          "button": "Ver huecos",
                          "sections": [{ "title": "Mañana", "rows": "steps.free.options" }]
                      }
                  } }
            ]
        }),
    )
    .await;
    let mut grants = both_grants();
    grants.push(GrantSpec::pair(GrantKind::Query, "crm.note.list"));
    set_grants(&rt, &flow_id, &grants).await;
    run_flow(&rt, &flow_id).await;
    rt.drain_outbox().await.unwrap();

    let sent = transport.sent();
    assert_eq!(sent.len(), 1, "one run, one message");
    let rows = &sent[0].0.interactive["action"]["sections"][0]["rows"];
    assert!(
        rows.is_array(),
        "the list travelled as a list, not as a string that looks like one: {rows}"
    );
    assert_eq!(
        rows,
        &json!([
            { "id": "n-1", "title": "martes 10:30", "description": "c-1" },
            { "id": "n-2", "title": "martes 12:00", "description": "c-1" }
        ]),
        "the rows the read found are the rows Meta will paint"
    );
    assert_eq!(
        sent[0].0.interactive["body"]["text"],
        json!("Estos son los huecos del martes"),
        "and the rest of the message is rendered as it always was"
    );

    // The control, so the assertion above is about the read and not about anything a message now
    // grows on its own: with the notes gone, the same flow sends the same message with no rows.
    rt.db_for_test()
        .execute("DELETE FROM crm_note", &Params::new())
        .await
        .unwrap();
    run_flow(&rt, &flow_id).await;
    rt.drain_outbox().await.unwrap();
    let sent = transport.sent();
    assert_eq!(sent.len(), 2);
    assert_eq!(
        sent[1].0.interactive["action"]["sections"][0]["rows"],
        json!([]),
        "an empty read is an empty list, and the run does not fail over it"
    );
}
