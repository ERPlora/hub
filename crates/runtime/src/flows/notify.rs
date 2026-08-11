//! **The `notify` step, up to the moment it is queued** (ADR-0283 §5 / K4, hub#821).
//!
//! This is the file that lets a flow write to a CUSTOMER. Everything before it could only reach
//! the hub's own allow-list (`hub_settings.notify_allowed_recipients`) or the email of a hub user
//! — the staff — and every case that pays for the automation kernel is a message to somebody who
//! lives in a module's table.
//!
//! ```text
//!   step + run scope ─▶ notify grant (channel) ─▶ recipient grant (query # field)
//!                                                        │
//!                                    the read, read-only, with the flow's own context
//!                                                        ▼
//!                              ONE row  ─▶ syntax  ─▶ _event_outbox `flow.reminder.due`
//!                                                     + resolved_via: flow_grant:<id>
//! ```
//!
//! **Why it queues instead of sending.** `notify` is the one I/O step that does not cross the
//! `PendingIo` seam: the outbox relay already has the retries, the backoff, the dead-letter and the
//! transport (hub#663), and reaching the network from the tick would mean building all of that a
//! second time next to it. What this file produces is a row; what sends it is the same machine that
//! has been sending a module's reminders since ADR-0012.
//!
//! **Why the release is re-read later.** The row it writes carries `resolved_via`, and the relay
//! checks the grants AGAIN before the message leaves ([`crate::flows::grants::check_notify_release`]).
//! A queue is durable — a restart, a backoff, a `delay` step — so authorising once at build time
//! would mean that revoking a grant stops the next message and lets the queued one through.
//!
//! **What the run history keeps.** The recipient is a customer's phone number. The step records
//! WHICH query and WHICH field it came from and marks it `redacted`; the address itself is never
//! written to `_flow_run_steps`. That is the same criterion as hub#666 for a declared secret and
//! hub#715 for personal data in event samples: minimisation, not anonymisation — the value exists,
//! in the queue row that has to carry it, and nowhere a debugging session would stumble on it.
use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Value as Json};

use crate::errors::{Result, RuntimeError};
use crate::flows::def::{self, NotifyStep, StepDef, StepSpec};
use crate::flows::grants::{self, Authority};
use crate::flows::http::REDACTED;
use crate::host_notify;
use crate::registry::{AutomationCtx, Registry, RequestContext};
use crate::{outbox, queries};

/// The read found nobody, or the row has nothing in that column.
pub const ERR_RECIPIENT_NOT_FOUND: &str = "flow.recipient_not_found";
/// The read found several. Refused rather than resolved — see [`prepare`].
pub const ERR_RECIPIENT_AMBIGUOUS: &str = "flow.recipient_ambiguous";
/// The value is there and cannot be a recipient for this channel.
pub const ERR_RECIPIENT_INVALID: &str = "flow.recipient_invalid";

/// A `notify` step turned into one queued message: the row to insert, and the two halves of what
/// gets written down.
#[derive(Debug)]
pub(crate) struct Prepared {
    /// The `_event_outbox` INSERT. It rides in the STEP's transaction, so the message and the
    /// run's advance commit together: a crash never queues a reminder twice.
    pub queue_op: (String, Params),
    /// What `_flow_run_steps.input` records — the shape of the decision, never the address.
    pub recorded_input: Json,
    /// What later steps read as `steps.<id>`, and what the history shows as the outcome.
    pub output: Json,
}

/// Resolves the recipient of a `notify` step and builds the row that will carry the message, or
/// refuses.
///
/// Refuses when: either grant is missing, the read finds nobody, the read finds SEVERAL, the field
/// is empty or is not text, or the value cannot be a recipient for the channel. Every one of those
/// happens **before** anything is queued, so the reason lands on the run instead of eight retries
/// later in a dead-letter.
///
/// # Why several recipients is a refusal and not a fan-out
///
/// Two reasons, and either is enough. A grant authorises **one field of one read** for **one
/// message**; a query that happens to return the whole address book would turn that into a campaign
/// nobody approved, billed per WhatsApp message. And picking "the first" would make who gets
/// written to depend on a row order no document declares — the author narrows the read with
/// `to.params`, which is a sentence somebody can check.
#[allow(clippy::too_many_arguments)] // one step's worth of context, same as `run_step`
pub(crate) async fn prepare(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    flow_id: &str,
    run_id: &str,
    parent_event_id: &str,
    depth: i64,
    step: &StepDef,
    scope: &Json,
    authority: &Authority,
) -> Result<Prepared> {
    let StepSpec::Notify(spec) = &step.spec else {
        return Err(RuntimeError::Domain {
            code: ERR_RECIPIENT_INVALID.to_string(),
            message: format!("step `{}` is not a notify step", step.id),
        });
    };

    // **The two grants**, both live at this instant. The id that comes back is the one the queued
    // row will name, so that revoking THAT row is what stops the message.
    let release_id = grants::check_notify_grants(
        db,
        hub_id,
        flow_id,
        authority,
        spec.channel,
        &spec.query,
        &spec.field,
    )
    .await?;

    // The context the read runs under: attributed to the flow, machine-principal (never offered a
    // manager's PIN, hub#361), carrying only the permissions of what this flow was granted.
    let ctx = RequestContext::new(
        hub_id.to_string(),
        format!("flow:{flow_id}"),
        authority.permissions(registry),
    )
    .as_machine()
    .with_automation(AutomationCtx {
        flow_id: flow_id.to_string(),
        run_id: run_id.to_string(),
    })
    .caused_by_event(parent_event_id);

    let params: Params = def::resolve_map(&spec.params, scope);
    let rows = queries::execute(db, registry, &spec.query, &params, &ctx).await?;
    let to = recipient_of(spec, &rows)?;

    let vars = def::resolve_map(&spec.vars, scope);
    let template = as_text(&def::resolve(&json!(spec.template), scope));

    // The intent the transport already knows how to send (ADR-0012), plus the release. `to` is in
    // the QUEUE row because the transport needs an address to dial; it is not in the run history.
    let mut payload = Params::new();
    payload.insert("channel".into(), json!(spec.channel.as_str()));
    payload.insert("to".into(), json!(to));
    payload.insert("template".into(), json!(template));
    payload.insert("vars".into(), Json::Object(vars.clone()));
    payload.insert(
        host_notify::RESOLVED_VIA_KEY.into(),
        json!(host_notify::flow_grant_release(&release_id)),
    );

    // `module_id` is empty because no module emitted this — the kernel did. That emptiness is half
    // of what tells the relay this row may carry a flow's release, and it is not something a module
    // can produce (see `outbox::deliver_host_notify`).
    let queue_op = outbox::insert_op(&ctx, "", outbox::FLOW_NOTIFY_EVENT, &payload, depth.max(0) as u32);
    let event_id = queue_op
        .1
        .get("id")
        .and_then(|v| v.as_str())
        .unwrap_or_default()
        .to_string();

    Ok(Prepared {
        recorded_input: json!({
            "channel": spec.channel.as_str(),
            "to": { "query": spec.query, "params": Json::Object(params), "field": spec.field },
            "template": template,
            "vars": Json::Object(vars),
            "recipient": REDACTED,
        }),
        output: json!({
            "queued": true,
            "channel": spec.channel.as_str(),
            "event_id": event_id,
            // Said out loud rather than simply omitted: a history that showed nothing would read
            // like the step never had a recipient.
            "recipient_redacted": true,
        }),
        queue_op,
    })
}

/// The ONE recipient a read answers with, or the reason there is none.
fn recipient_of(spec: &NotifyStep, rows: &[Json]) -> Result<String> {
    let refuse = |code: &str, why: String| -> Result<String> {
        Err(RuntimeError::Domain {
            code: code.to_string(),
            message: format!(
                "`{}` reading `{}#{}`: {why}",
                spec.channel.as_str(),
                spec.query,
                spec.field
            ),
        })
    };
    match rows.len() {
        0 => return refuse(ERR_RECIPIENT_NOT_FOUND, "the read found nobody".to_string()),
        1 => {}
        n => {
            return refuse(
                ERR_RECIPIENT_AMBIGUOUS,
                format!(
                    "the read found {n} rows, and a message has one recipient. Narrow it with \
                     `to.params`: sending to the first would depend on a row order no document \
                     declares, and sending to all of them is a campaign nobody granted"
                ),
            )
        }
    }
    let value = &rows[0][spec.field.as_str()];
    let to = match value {
        Json::String(s) if !s.trim().is_empty() => s.trim().to_string(),
        Json::Null => {
            return refuse(
                ERR_RECIPIENT_NOT_FOUND,
                "the row has no such column, or it is empty".to_string(),
            )
        }
        Json::String(_) => {
            return refuse(ERR_RECIPIENT_NOT_FOUND, "the column is empty".to_string())
        }
        other => {
            return refuse(
                ERR_RECIPIENT_INVALID,
                format!("the column holds {other}, which is not an address"),
            )
        }
    };
    // The same conservative shape check `host.notify` has applied since hub#240. Coming out of a
    // granted read does not make a value a recipient: an email is not a WhatsApp number, and a
    // newline in either is an injected header.
    if let Err(e) = host_notify::check_recipient_syntax(spec.channel, &to) {
        return refuse(ERR_RECIPIENT_INVALID, format!("{e}"));
    }
    Ok(to)
}

/// How a resolved value reads on the wire — same rule as the mapping language, so a template and a
/// bare path never disagree.
fn as_text(value: &Json) -> String {
    match value {
        Json::String(s) => s.clone(),
        Json::Null => String::new(),
        other => other.to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flows::def::FlowDefinition;
    use crate::flows::grants::GrantKind;
    use crate::flows::test_support;
    use crate::registry::ModuleStatus;
    use erplora_db::testutil::fresh_db;

    const HUB: &str = "hub-notify";
    const FLOW: &str = "flow-1";

    /// A module with a read that returns a customer's contact — the shape every appointment
    /// reminder in the product is going to have.
    fn registry() -> Registry {
        let mut reg = Registry::new();
        reg.status.insert("crm".into(), ModuleStatus::Active);
        reg.queries.insert(
            "crm.customer.get".into(),
            test_support::query(
                "crm",
                "crm.view_customer",
                "SELECT id, email, phone, age FROM cust WHERE id = :id",
            ),
        );
        reg.queries.insert(
            "crm.customer.list".into(),
            test_support::query(
                "crm",
                "crm.view_customer",
                "SELECT id, email, phone, age FROM cust ORDER BY id",
            ),
        );
        reg
    }

    async fn db() -> impl DatabaseAdapter {
        let db = fresh_db().await;
        test_support::ensure_schema(&db, HUB).await;
        db.execute_batch(
            "CREATE TABLE IF NOT EXISTS cust (id TEXT PRIMARY KEY, email TEXT NOT NULL DEFAULT '', \
             phone TEXT NOT NULL DEFAULT '', age INTEGER);",
        )
        .await
        .unwrap();
        db
    }

    async fn customer(db: &dyn DatabaseAdapter, id: &str, email: &str, phone: &str) {
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        p.insert("email".into(), json!(email));
        p.insert("phone".into(), json!(phone));
        db.execute(
            "INSERT INTO cust (id, email, phone, age) VALUES (:id, :email, :phone, 41)",
            &p,
        )
        .await
        .unwrap();
    }

    async fn allow(db: &dyn DatabaseAdapter, wanted: &[(GrantKind, String)]) -> Authority {
        grants::replace(db, HUB, FLOW, &registry(), wanted, "hub_user:1")
            .await
            .unwrap();
        grants::authority(db, HUB, FLOW).await.unwrap()
    }

    fn both(query: &str, field: &str, channel: &str) -> Vec<(GrantKind, String)> {
        vec![
            (GrantKind::Notify, channel.to_string()),
            (
                GrantKind::RecipientQuery,
                grants::recipient_value(query, field),
            ),
        ]
    }

    fn step(channel: &str, query: &str, field: &str) -> StepDef {
        FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "remind", "kind": "notify", "channel": channel,
                "to": { "query": query, "params": { "id": "input.customer_id" }, "field": field },
                "template": "appointment_reminder",
                "vars": { "text": "Hola {{input.name}}" }
            }]
        }))
        .unwrap()
        .steps
        .remove(0)
    }

    fn scope() -> Json {
        json!({ "input": { "customer_id": "c-1", "name": "Marta" }, "steps": {} })
    }

    async fn prepare_step(
        db: &dyn DatabaseAdapter,
        step: &StepDef,
        authority: &Authority,
    ) -> Result<Prepared> {
        prepare(
            db,
            &registry(),
            HUB,
            FLOW,
            "run-1",
            "",
            0,
            step,
            &scope(),
            authority,
        )
        .await
    }

    #[tokio::test]
    async fn the_queued_message_carries_the_address_and_names_the_grant_that_released_it() {
        let db = db().await;
        customer(&db, "c-1", "marta@example.com", "+34600111222").await;
        let authority = allow(&db, &both("crm.customer.get", "phone", "whatsapp")).await;

        let prepared = prepare_step(&db, &step("whatsapp", "crm.customer.get", "phone"), &authority)
            .await
            .unwrap();

        let queued = &prepared.queue_op.1;
        let payload: Json =
            serde_json::from_str(queued["payload"].as_str().unwrap()).unwrap();
        assert_eq!(payload["to"], json!("+34600111222"), "the address the row carries");
        assert_eq!(payload["channel"], json!("whatsapp"));
        assert_eq!(payload["vars"]["text"], json!("Hola Marta"), "the copy is rendered");
        let release = payload[host_notify::RESOLVED_VIA_KEY].as_str().unwrap();
        let live = grants::list(&db, HUB, FLOW).await.unwrap();
        let grant = live.iter().find(|g| g.kind == "recipient_query").unwrap();
        assert_eq!(
            release,
            host_notify::flow_grant_release(&grant.id),
            "the release names the row that authorised it, so revoking that row stops the message"
        );
        // The row is the kernel's, not a module's — that is what lets the relay honour the release.
        assert_eq!(queued["module_id"], json!(""));
        assert_eq!(queued["run_id"], json!("run-1"));
        assert_eq!(queued["event_name"], json!(outbox::FLOW_NOTIFY_EVENT));
    }

    /// The address goes in the QUEUE, which has to dial it — and nowhere else. What the run keeps
    /// is where it came from.
    #[tokio::test]
    async fn what_gets_written_down_says_where_the_recipient_came_from_and_not_who() {
        let db = db().await;
        customer(&db, "c-1", "marta@example.com", "+34600111222").await;
        let authority = allow(&db, &both("crm.customer.get", "phone", "whatsapp")).await;

        let prepared = prepare_step(&db, &step("whatsapp", "crm.customer.get", "phone"), &authority)
            .await
            .unwrap();

        let written = format!("{}{}", prepared.recorded_input, prepared.output);
        assert!(
            !written.contains("+34600111222"),
            "a customer's phone is not part of a run's history: {written}"
        );
        assert!(written.contains(REDACTED), "and its place is marked: {written}");
        assert_eq!(prepared.recorded_input["to"]["query"], json!("crm.customer.get"));
        assert_eq!(prepared.recorded_input["to"]["field"], json!("phone"));
        assert_eq!(prepared.output["recipient_redacted"], json!(true));
        assert_eq!(prepared.output["queued"], json!(true));
    }

    #[tokio::test]
    async fn without_either_grant_nothing_is_prepared() {
        let db = db().await;
        customer(&db, "c-1", "marta@example.com", "+34600111222").await;
        let step = step("whatsapp", "crm.customer.get", "phone");

        // Neither.
        let none = grants::authority(&db, HUB, FLOW).await.unwrap();
        assert!(prepare_step(&db, &step, &none).await.is_err());

        // The channel but not the recipient…
        let only_channel = allow(&db, &[(GrantKind::Notify, "whatsapp".into())]).await;
        let err = prepare_step(&db, &step, &only_channel).await.unwrap_err();
        assert!(format!("{err}").contains("recipient_query"), "{err}");

        // …and the recipient but not the channel.
        let only_recipient = allow(
            &db,
            &[(
                GrantKind::RecipientQuery,
                "crm.customer.get#phone".to_string(),
            )],
        )
        .await;
        let err = prepare_step(&db, &step, &only_recipient).await.unwrap_err();
        assert!(format!("{err}").contains("notify"), "{err}");
    }

    /// The grant covers ONE field of ONE read. Its neighbours are different permissions with the
    /// same default answer — and the customer's email sitting one column away is exactly the case
    /// that makes that matter.
    #[tokio::test]
    async fn the_grant_does_not_extend_to_the_column_next_to_it() {
        let db = db().await;
        customer(&db, "c-1", "marta@example.com", "+34600111222").await;
        let authority = allow(&db, &both("crm.customer.get", "phone", "email")).await;

        let err = prepare_step(&db, &step("email", "crm.customer.get", "email"), &authority)
            .await
            .unwrap_err();
        assert!(format!("{err}").contains("crm.customer.get#email"), "{err}");

        // And the same field of another read is not covered either.
        let err = prepare_step(&db, &step("email", "crm.customer.list", "phone"), &authority)
            .await
            .unwrap_err();
        assert!(format!("{err}").contains("crm.customer.list#phone"), "{err}");
    }

    #[tokio::test]
    async fn nobody_and_several_are_both_refusals_and_neither_guesses() {
        let db = db().await;
        let authority = allow(&db, &both("crm.customer.get", "phone", "whatsapp")).await;

        // Nobody: the customer this run is about is not in the table.
        let err = prepare_step(&db, &step("whatsapp", "crm.customer.get", "phone"), &authority)
            .await
            .unwrap_err();
        assert!(matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_RECIPIENT_NOT_FOUND));

        // Several.
        customer(&db, "c-1", "marta@example.com", "+34600111222").await;
        customer(&db, "c-2", "otro@example.com", "+34600333444").await;
        let authority = allow(&db, &both("crm.customer.list", "phone", "whatsapp")).await;
        let err = prepare_step(&db, &step("whatsapp", "crm.customer.list", "phone"), &authority)
            .await
            .unwrap_err();
        assert!(
            matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_RECIPIENT_AMBIGUOUS),
            "{err}"
        );
        assert!(format!("{err}").contains("2 rows"), "the refusal says how many: {err}");
    }

    /// A value that is there and cannot be a recipient. The read is granted; that is not the same
    /// as the column holding an address.
    #[tokio::test]
    async fn a_column_that_is_not_an_address_for_this_channel_is_refused() {
        let db = db().await;
        customer(&db, "c-1", "marta@example.com", "").await;
        // An email in the WhatsApp channel.
        let authority = allow(&db, &both("crm.customer.get", "email", "whatsapp")).await;
        let err = prepare_step(&db, &step("whatsapp", "crm.customer.get", "email"), &authority)
            .await
            .unwrap_err();
        assert!(matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_RECIPIENT_INVALID));

        // An empty column: nobody to write to, said as such.
        let authority = allow(&db, &both("crm.customer.get", "phone", "whatsapp")).await;
        let err = prepare_step(&db, &step("whatsapp", "crm.customer.get", "phone"), &authority)
            .await
            .unwrap_err();
        assert!(matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_RECIPIENT_NOT_FOUND));

        // A column that is not text at all.
        let authority = allow(&db, &both("crm.customer.get", "age", "whatsapp")).await;
        let err = prepare_step(&db, &step("whatsapp", "crm.customer.get", "age"), &authority)
            .await
            .unwrap_err();
        assert!(matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_RECIPIENT_INVALID));
    }
}
