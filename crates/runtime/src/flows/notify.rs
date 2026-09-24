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
/// The message promises a text — a `vars` entry, the body of an `interactive` — mapped from the
/// run, and the run never had it (hub#1660).
pub const ERR_TEXT_NOT_FOUND: &str = "flow.text_not_found";
/// The message promises options to tap and the run never published them (hub#1646).
pub const ERR_OPTIONS_NOT_FOUND: &str = "flow.options_not_found";

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
    // **The copy gets the same look as the options below** (hub#1660). The WhatsApp recipes answer
    // with `{{steps.book_appointment.text}}`: the words come from an earlier step, and when it
    // never published them the template fills in as `""` and the customer used to get a message
    // with nothing in it — refused by the proxy hours later, where nobody is looking.
    if let Some(missing) = missing_text(spec, scope) {
        return Err(RuntimeError::Domain {
            code: ERR_TEXT_NOT_FOUND.to_string(),
            message: missing.text_refusal(spec.channel.as_str()),
        });
    }
    // The tappable options (hub#1633), mapped like the rest of the copy: `resolve` recurses, so a
    // `{{steps.slots.first}}` inside a list row fills the same way `vars.text` does.
    let interactive = match spec.interactive.as_ref() {
        None => None,
        Some(i) => {
            let written = Json::Object(i.clone());
            let filled = def::resolve(&written, scope);
            // **And then it is LOOKED AT, which is the half that was missing** (hub#1646). The
            // rows of a list are not typed by hand: a `query` (hub#1641) or an `ai` turn
            // (hub#1639) publishes them, and `resolve` turns a path to a step that never published
            // into `null` — a shape the proxy refuses hours later, in a background tick, where
            // nobody is looking. `on_error: "continue"` (hub#1635) made that reachable from a
            // document nobody would call wrong: the step that fills the list may fail and the run
            // carry on to the message that promised it.
            if let Some(missing) = missing_options(&written, &filled) {
                return Err(RuntimeError::Domain {
                    code: ERR_OPTIONS_NOT_FOUND.to_string(),
                    message: missing.refusal(spec.channel.as_str()),
                });
            }
            Some(filled)
        }
    };

    // The intent the transport already knows how to send (ADR-0012), plus the release. `to` is in
    // the QUEUE row because the transport needs an address to dial; it is not in the run history.
    let mut payload = Params::new();
    payload.insert("channel".into(), json!(spec.channel.as_str()));
    payload.insert("to".into(), json!(to));
    payload.insert("template".into(), json!(template));
    payload.insert("vars".into(), Json::Object(vars.clone()));
    // Absent rather than null on an ordinary message: the transport branches on its presence, and
    // a key that is always there but usually empty is a key every reader has to interpret.
    if let Some(interactive) = interactive.clone() {
        payload.insert("interactive".into(), interactive);
    }
    payload.insert(
        host_notify::RESOLVED_VIA_KEY.into(),
        json!(host_notify::flow_grant_release(&release_id)),
    );
    // **Which step is asking** (hub#1951). The relay pairs it with the id the provider gives the
    // message, so that when the customer taps «Sí» the event can say which of two identical
    // questions it answers. It goes in the payload next to the release, and is read back only on
    // the path a module cannot reach (see `outbox::deliver_host_notify`).
    payload.insert(host_notify::FLOW_STEP_KEY.into(), json!(step.id));

    // `module_id` is empty because no module emitted this — the kernel did. That emptiness is half
    // of what tells the relay this row may carry a flow's release, and it is not something a module
    // can produce (see `outbox::deliver_host_notify`).
    let queue_op = outbox::insert_op(
        &ctx,
        "",
        outbox::FLOW_NOTIFY_EVENT,
        &payload,
        depth.max(0) as u32,
        None,
    );
    let event_id = queue_op
        .1
        .get("id")
        .and_then(|v| v.as_str())
        .unwrap_or_default()
        .to_string();

    let mut recorded_input = json!({
        "channel": spec.channel.as_str(),
        "to": { "query": spec.query, "params": Json::Object(params), "field": spec.field },
        "template": template,
        "vars": Json::Object(vars),
        "recipient": REDACTED,
    });
    // The options are the author's own words: unlike the address there is nothing personal in them
    // to keep out of the history, and a run that offered three slots is unreadable without them.
    if let Some(interactive) = interactive {
        recorded_input["interactive"] = interactive;
    }

    Ok(Prepared {
        recorded_input,
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

/// The first text this message promises — a `vars` entry, or the `header`/`body`/`footer` of an
/// `interactive` — that the run filled with **nothing**.
///
/// Same frontier as [`missing_options`]: only NOTHING counts. A path that resolves to nothing, or a
/// text made of nothing but `{{…}}` placeholders that ALL resolve to nothing. An empty string the
/// run did publish is somebody's decision, and words around an empty placeholder still say
/// something — every automation tool of the market sends a missing merge field as blank (Zapier,
/// Make, Shopify Flow, Klaviyo without a default), and refusing it would stop recipes that work.
fn missing_text(spec: &NotifyStep, scope: &Json) -> Option<MissingOptions> {
    let missing = |place: String, mapped_from: String| MissingOptions { place, mapped_from };
    for (key, written) in &spec.vars {
        if let Some(from) = nothing_from(written, scope) {
            return Some(missing(format!("vars.{key}"), from));
        }
    }
    let interactive = spec.interactive.as_ref()?;
    for part in ["header", "body", "footer"] {
        match interactive.get(part) {
            Some(whole @ Json::String(_)) => {
                if let Some(from) = nothing_from(whole, scope) {
                    return Some(missing(format!("interactive.{part}"), from));
                }
            }
            Some(Json::Object(block)) => {
                if let Some(from) = block.get("text").and_then(|t| nothing_from(t, scope)) {
                    return Some(missing(format!("interactive.{part}.text"), from));
                }
            }
            _ => {}
        }
    }
    None
}

/// What a written text was mapped from, when the run had none of it; `None` when it is there or
/// is the author's own words.
fn nothing_from(written: &Json, scope: &Json) -> Option<String> {
    let absent = |path: &str| def::resolve_path(path, scope).is_none_or(|v| v.is_null());
    let Json::String(s) = written else {
        return None;
    };
    if def::is_path(s) {
        return absent(s).then(|| s.clone());
    }
    if !s.contains("{{") || !def::render(s, &Json::Null).trim().is_empty() {
        return None;
    }
    let mut paths = Vec::new();
    def::template_paths(written, &mut paths);
    let first = paths.first()?.clone();
    paths.iter().all(|p| absent(p)).then_some(first)
}

/// A place in a message where the options live, mapped from the run and filled with **nothing**.
#[derive(Debug)]
struct MissingOptions {
    /// Where in Meta's shape it sits — `action.sections[0].rows`, `action.buttons`.
    place: String,
    /// What the document said to fill it from. Empty when the document wrote a bare `null` there.
    mapped_from: String,
}

impl MissingOptions {
    /// The sentence the run keeps. It names the step that was supposed to publish the list,
    /// because that — and not the message — is where the author has to look.
    fn refusal(&self, channel: &str) -> String {
        let source = match self.publisher() {
            Some(step) => format!(
                "`{}` resolved to nothing, so step `{step}` never published it",
                self.mapped_from
            ),
            None if self.mapped_from.is_empty() => "the document leaves it empty".to_string(),
            None => format!("`{}` resolved to nothing", self.mapped_from),
        };
        format!(
            "`{channel}`: the options this message offers at `{}` are not there — {source}. \
             Queuing it would put a message with nothing to tap on a customer's phone, and the \
             refusal would arrive later in a background tick instead of on this run",
            self.place
        )
    }

    /// The same sentence for the words of the message (hub#1660).
    fn text_refusal(&self, channel: &str) -> String {
        let source = match self.publisher() {
            Some(step) => format!(
                "`{}` resolved to nothing, so step `{step}` never published it",
                self.mapped_from
            ),
            None => format!("`{}` resolved to nothing", self.mapped_from),
        };
        format!(
            "`{channel}`: the text this message says at `{}` is not there — {source}. Queuing it \
             would put an empty message on a customer's phone, and the refusal would arrive later \
             in a background tick instead of on this run",
            self.place
        )
    }

    /// The step a `steps.<id>.<field>` path was waiting on.
    fn publisher(&self) -> Option<&str> {
        self.mapped_from
            .strip_prefix("steps.")
            .and_then(|rest| rest.split('.').next())
            .filter(|id| !id.is_empty())
    }
}

/// The first place where the options this message promises came back as **nothing**.
///
/// Only `null` counts, and only where the document actually wrote the key. Everything else is
/// deliberately somebody else's question:
///
/// - **An EMPTY list is not a missing one.** A read that legitimately found no free slots
///   publishes `[]`, and the document that wants to say «no quedan huecos» branches on
///   `steps.<id>.count` — that is the recipe's decision (hub#1641), not this door's.
/// - **How many rows Meta holds, how long a title may be, whether two ids repeat**: the SaaS proxy
///   (`whatsapp_inbox/services/interactive.py`) is the one place that knows Meta's rules, and a
///   second copy of them here would be a table that ages on its own.
///
/// What is left is the one failure the proxy cannot explain and this side can: the run did not
/// have what the document promised, and only the run knows which step owed it.
fn missing_options(written: &Json, filled: &Json) -> Option<MissingOptions> {
    let missing = |place: &str, written_at: &Json| MissingOptions {
        place: place.to_string(),
        mapped_from: match written_at {
            Json::String(s) => s.clone(),
            _ => String::new(),
        },
    };
    // `get` and not indexing: a key the document never wrote reads as `null` too, and the whole
    // point is to refuse a PROMISE, not the absence of one — a button message has no `sections`.
    let (written_action, action) = (written.get("action")?, filled.get("action")?);
    if action.is_null() {
        return Some(missing("action", written_action));
    }
    for key in ["buttons", "sections"] {
        match (written_action.get(key), action.get(key)) {
            (Some(written_at), Some(value)) if value.is_null() => {
                return Some(missing(&format!("action.{key}"), written_at))
            }
            _ => {}
        }
    }
    // A list carries its rows one level deeper, inside each section. `resolve` maps an array
    // item by item, so the two sit at the same index.
    let written_sections = written_action.get("sections")?.as_array()?;
    for (i, section) in action.get("sections")?.as_array()?.iter().enumerate() {
        let written_section = written_sections.get(i);
        // The section mapped WHOLE, and not only its rows: `interactive` has no inner shape in
        // the schema, so a document may hand the titled block over to a step the same way it
        // hands over the rows — and a `null` left in the array is the same message with nothing
        // to tap, one level up.
        if section.is_null() {
            if let Some(written_at) = written_section {
                return Some(missing(&format!("action.sections[{i}]"), written_at));
            }
        }
        match (
            written_section.and_then(|s| s.get("rows")),
            section.get("rows"),
        ) {
            (Some(written_at), Some(rows)) if rows.is_null() => {
                return Some(missing(&format!("action.sections[{i}].rows"), written_at))
            }
            _ => {}
        }
    }
    None
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
    use crate::flows::grants::{GrantKind, GrantSpec};
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

    async fn allow(db: &dyn DatabaseAdapter, wanted: &[GrantSpec]) -> Authority {
        grants::replace(db, HUB, FLOW, &registry(), wanted, "hub_user:1")
            .await
            .unwrap();
        grants::authority(db, HUB, FLOW).await.unwrap()
    }

    fn both(query: &str, field: &str, channel: &str) -> Vec<GrantSpec> {
        vec![
            GrantSpec::pair(GrantKind::Notify, channel.to_string()),
            GrantSpec::pair(GrantKind::RecipientQuery, grants::recipient_value(query, field)),
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
        prepare_in(db, step, authority, &scope()).await
    }

    async fn prepare_in(
        db: &dyn DatabaseAdapter,
        step: &StepDef,
        authority: &Authority,
        scope: &Json,
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
            scope,
            authority,
        )
        .await
    }

    #[tokio::test]
    async fn the_queued_message_carries_the_address_and_names_the_grant_that_released_it() {
        let db = db().await;
        customer(&db, "c-1", "marta@example.com", "+34600111222").await;
        let authority = allow(&db, &both("crm.customer.get", "phone", "whatsapp")).await;

        let prepared = prepare_step(
            &db,
            &step("whatsapp", "crm.customer.get", "phone"),
            &authority,
        )
        .await
        .unwrap();

        let queued = &prepared.queue_op.1;
        let payload: Json = serde_json::from_str(queued["payload"].as_str().unwrap()).unwrap();
        assert_eq!(
            payload["to"],
            json!("+34600111222"),
            "the address the row carries"
        );
        assert_eq!(payload["channel"], json!("whatsapp"));
        assert_eq!(
            payload["vars"]["text"],
            json!("Hola Marta"),
            "the copy is rendered"
        );
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

    /// **hub#1951 — the row says WHICH step asked.**
    ///
    /// `run_id` alone cannot answer it: one run may ask twice, and the run that ANSWERS a tap is a
    /// different one anyway (the event triggers it). The step is the only name the author wrote
    /// themselves, it is stable across releases and it is distinct for each question even when
    /// both use the same approved template and the same «Sí».
    ///
    /// It rides in the payload, next to the release, and not in a column: the relay only ever
    /// reads it on the path a module cannot reach (`module_id` empty **and** `run_id` present —
    /// see `outbox::deliver_host_notify`), so a module writing `flow_step` into its own
    /// `*.reminder.due` payload names nothing.
    #[tokio::test]
    async fn the_queued_question_names_the_step_that_asked_it() {
        let db = db().await;
        customer(&db, "c-1", "marta@example.com", "+34600111222").await;
        let authority = allow(&db, &both("crm.customer.get", "phone", "whatsapp")).await;

        let prepared = prepare_step(
            &db,
            &step("whatsapp", "crm.customer.get", "phone"),
            &authority,
        )
        .await
        .unwrap();

        let payload: Json =
            serde_json::from_str(prepared.queue_op.1["payload"].as_str().unwrap()).unwrap();
        assert_eq!(
            payload["flow_step"],
            json!("remind"),
            "the queued question has to carry the step that asked it, or the tap has nothing to \
             name when it comes back"
        );
    }

    /// The address goes in the QUEUE, which has to dial it — and nowhere else. What the run keeps
    /// is where it came from.
    #[tokio::test]
    async fn what_gets_written_down_says_where_the_recipient_came_from_and_not_who() {
        let db = db().await;
        customer(&db, "c-1", "marta@example.com", "+34600111222").await;
        let authority = allow(&db, &both("crm.customer.get", "phone", "whatsapp")).await;

        let prepared = prepare_step(
            &db,
            &step("whatsapp", "crm.customer.get", "phone"),
            &authority,
        )
        .await
        .unwrap();

        let written = format!("{}{}", prepared.recorded_input, prepared.output);
        assert!(
            !written.contains("+34600111222"),
            "a customer's phone is not part of a run's history: {written}"
        );
        assert!(
            written.contains(REDACTED),
            "and its place is marked: {written}"
        );
        assert_eq!(
            prepared.recorded_input["to"]["query"],
            json!("crm.customer.get")
        );
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
        let only_channel = allow(&db, &[GrantSpec::pair(GrantKind::Notify, "whatsapp")]).await;
        let err = prepare_step(&db, &step, &only_channel).await.unwrap_err();
        assert!(format!("{err}").contains("recipient_query"), "{err}");

        // …and the recipient but not the channel.
        let only_recipient = allow(
            &db,
            &[GrantSpec::pair(GrantKind::RecipientQuery, "crm.customer.get#phone")],
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
        let err = prepare_step(
            &db,
            &step("email", "crm.customer.list", "phone"),
            &authority,
        )
        .await
        .unwrap_err();
        assert!(
            format!("{err}").contains("crm.customer.list#phone"),
            "{err}"
        );
    }

    #[tokio::test]
    async fn nobody_and_several_are_both_refusals_and_neither_guesses() {
        let db = db().await;
        let authority = allow(&db, &both("crm.customer.get", "phone", "whatsapp")).await;

        // Nobody: the customer this run is about is not in the table.
        let err = prepare_step(
            &db,
            &step("whatsapp", "crm.customer.get", "phone"),
            &authority,
        )
        .await
        .unwrap_err();
        assert!(
            matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_RECIPIENT_NOT_FOUND)
        );

        // Several.
        customer(&db, "c-1", "marta@example.com", "+34600111222").await;
        customer(&db, "c-2", "otro@example.com", "+34600333444").await;
        let authority = allow(&db, &both("crm.customer.list", "phone", "whatsapp")).await;
        let err = prepare_step(
            &db,
            &step("whatsapp", "crm.customer.list", "phone"),
            &authority,
        )
        .await
        .unwrap_err();
        assert!(
            matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_RECIPIENT_AMBIGUOUS),
            "{err}"
        );
        assert!(
            format!("{err}").contains("2 rows"),
            "the refusal says how many: {err}"
        );
    }

    /// A value that is there and cannot be a recipient. The read is granted; that is not the same
    /// as the column holding an address.
    #[tokio::test]
    async fn a_column_that_is_not_an_address_for_this_channel_is_refused() {
        let db = db().await;
        customer(&db, "c-1", "marta@example.com", "").await;
        // An email in the WhatsApp channel.
        let authority = allow(&db, &both("crm.customer.get", "email", "whatsapp")).await;
        let err = prepare_step(
            &db,
            &step("whatsapp", "crm.customer.get", "email"),
            &authority,
        )
        .await
        .unwrap_err();
        assert!(matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_RECIPIENT_INVALID));

        // An empty column: nobody to write to, said as such.
        let authority = allow(&db, &both("crm.customer.get", "phone", "whatsapp")).await;
        let err = prepare_step(
            &db,
            &step("whatsapp", "crm.customer.get", "phone"),
            &authority,
        )
        .await
        .unwrap_err();
        assert!(
            matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_RECIPIENT_NOT_FOUND)
        );

        // A column that is not text at all.
        let authority = allow(&db, &both("crm.customer.get", "age", "whatsapp")).await;
        let err = prepare_step(
            &db,
            &step("whatsapp", "crm.customer.get", "age"),
            &authority,
        )
        .await
        .unwrap_err();
        assert!(matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_RECIPIENT_INVALID));
    }

    /// **The tappable options reach the queue rendered** (hub#1633).
    ///
    /// They are mapped against the run like the rest of the copy, so the slots a previous step
    /// read become the rows of the list, and they ride in the SAME row that carries the address —
    /// what the relay hands the proxy is one message, not a message plus an afterthought.
    #[tokio::test]
    async fn the_queued_message_carries_the_options_the_customer_will_tap() {
        let db = db().await;
        customer(&db, "c-1", "marta@example.com", "+34600111222").await;
        let authority = allow(&db, &both("crm.customer.get", "phone", "whatsapp")).await;

        let asking = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "ask", "kind": "notify", "channel": "whatsapp",
                "to": { "query": "crm.customer.get", "params": { "id": "input.customer_id" },
                        "field": "phone" },
                "interactive": {
                    "type": "button",
                    "body": { "text": "{{input.name}}, ¿confirmas la cita?" },
                    "action": { "buttons": [
                        { "type": "reply", "reply": { "id": "confirm", "title": "Sí" } }
                    ] }
                }
            }]
        }))
        .unwrap()
        .steps
        .remove(0);

        let prepared = prepare_step(&db, &asking, &authority).await.unwrap();

        let queued = &prepared.queue_op.1;
        let payload: Json = serde_json::from_str(queued["payload"].as_str().unwrap()).unwrap();
        assert_eq!(payload["to"], json!("+34600111222"));
        assert_eq!(
            payload["interactive"]["body"]["text"],
            json!("Marta, ¿confirmas la cita?"),
            "the options are rendered against the run like any other copy"
        );
        assert_eq!(
            payload["interactive"]["action"]["buttons"][0]["reply"]["id"],
            json!("confirm")
        );

        // The history shows the shape of the decision — the options are the author's own words,
        // and unlike the address there is nothing personal to keep out of them.
        assert_eq!(
            prepared.recorded_input["interactive"]["action"]["buttons"][0]["reply"]["title"],
            json!("Sí")
        );

        // An ordinary message does not grow an empty key that a reader would have to interpret.
        let plain = prepare_step(
            &db,
            &step("whatsapp", "crm.customer.get", "phone"),
            &authority,
        )
        .await
        .unwrap();
        let plain_payload: Json =
            serde_json::from_str(plain.queue_op.1["payload"].as_str().unwrap()).unwrap();
        assert!(
            plain_payload.get("interactive").is_none(),
            "a plain message carries no `interactive`: {plain_payload}"
        );
    }

    /// A `notify` whose `interactive` offers a list, with the rows mapped from another step.
    fn asking(rows_from: &str) -> StepDef {
        FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "ask", "kind": "notify", "channel": "whatsapp",
                "to": { "query": "crm.customer.get", "params": { "id": "input.customer_id" },
                        "field": "phone" },
                "interactive": {
                    "type": "list",
                    "body": { "text": "¿Qué hueco te viene bien?" },
                    "action": { "button": "Ver huecos",
                                "sections": [{ "title": "Huecos", "rows": rows_from }] }
                }
            }]
        }))
        .unwrap()
        .steps
        .remove(0)
    }

    /// **A list the message promises and the run does not have stops the step** (hub#1646).
    ///
    /// The rows of a tappable list are not written by hand: a previous step publishes them. If
    /// that step never ran — it failed under `on_error: "continue"`, or the document names one
    /// that does not exist — `resolve` turns the path into `null` and the message used to be
    /// queued anyway: nothing to tap on the customer's phone, and the refusal arriving hours later
    /// in a background tick at the proxy, where nobody is looking.
    #[tokio::test]
    async fn a_list_whose_rows_nobody_published_stops_the_step_instead_of_being_queued() {
        let db = db().await;
        customer(&db, "c-1", "marta@example.com", "+34600111222").await;
        let authority = allow(&db, &both("crm.customer.get", "phone", "whatsapp")).await;

        let err = prepare_in(&db, &asking("steps.libres.options"), &authority, &scope())
            .await
            .unwrap_err();
        let RuntimeError::Domain { code, message } = &err else {
            panic!("a promised list that is not there is a domain refusal: {err}");
        };
        assert_eq!(code, ERR_OPTIONS_NOT_FOUND);
        assert!(
            message.contains("steps.libres.options"),
            "the refusal names what the rows were mapped from: {message}"
        );
        assert!(
            message.contains("`libres`"),
            "…and the step that was supposed to publish them: {message}"
        );
        assert!(
            message.contains("action.sections[0].rows"),
            "…and where in the message the hole is, so a list with two sections says WHICH: \
             {message}"
        );

        // **The control**: the same document, with the step that publishes the list. If this one
        // did not queue, the assertion above would be about anything at all.
        let published = json!({
            "input": { "customer_id": "c-1", "name": "Marta" },
            "steps": { "libres": { "options": [
                { "id": "s1", "title": "10:00", "description": "con Ana" }
            ] } }
        });
        let prepared = prepare_in(&db, &asking("steps.libres.options"), &authority, &published)
            .await
            .expect("a list that IS there is queued");
        let payload: Json =
            serde_json::from_str(prepared.queue_op.1["payload"].as_str().unwrap()).unwrap();
        assert_eq!(
            payload["interactive"]["action"]["sections"][0]["rows"][0]["id"],
            json!("s1")
        );
    }

    /// The same hole on the other half of Meta's shape: the buttons of a reply message are mapped
    /// from a step too (hub#1639 publishes them), so they can be missing the same way.
    #[tokio::test]
    async fn buttons_that_nobody_published_stop_the_step_the_same_way() {
        let db = db().await;
        customer(&db, "c-1", "marta@example.com", "+34600111222").await;
        let authority = allow(&db, &both("crm.customer.get", "phone", "whatsapp")).await;

        let step = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "ask", "kind": "notify", "channel": "whatsapp",
                "to": { "query": "crm.customer.get", "params": { "id": "input.customer_id" },
                        "field": "phone" },
                "interactive": {
                    "type": "button",
                    "body": { "text": "¿Confirmas?" },
                    "action": { "buttons": "steps.pick.options" }
                }
            }]
        }))
        .unwrap()
        .steps
        .remove(0);

        let err = prepare_in(&db, &step, &authority, &scope())
            .await
            .unwrap_err();
        assert!(
            matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_OPTIONS_NOT_FOUND),
            "{err}"
        );

        // And one level up: a whole `action` mapped from a step that never published it leaves a
        // message with no options AT ALL, which is the same refusal and not a lesser one.
        let whole = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "ask", "kind": "notify", "channel": "whatsapp",
                "to": { "query": "crm.customer.get", "params": { "id": "input.customer_id" },
                        "field": "phone" },
                "interactive": {
                    "type": "button",
                    "body": { "text": "¿Confirmas?" },
                    "action": "steps.pick.action"
                }
            }]
        }))
        .unwrap()
        .steps
        .remove(0);
        let err = prepare_in(&db, &whole, &authority, &scope())
            .await
            .unwrap_err();
        assert!(
            matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_OPTIONS_NOT_FOUND),
            "{err}"
        );
    }

    /// **The refusal is about a promise the run could not keep, not about how many rows there
    /// are.** A read that legitimately found nothing publishes an EMPTY list, and a document that
    /// wants to say «no quedan huecos» branches on `steps.<id>.count` — that decision is the
    /// recipe's (hub#1641), and refusing it here would break it. Meta's own limits stay in the one
    /// place that knows them, the SaaS proxy: two validators that drift apart is worse than one.
    #[tokio::test]
    async fn an_empty_list_is_not_a_missing_one_and_meta_limits_stay_at_the_proxy() {
        let db = db().await;
        customer(&db, "c-1", "marta@example.com", "+34600111222").await;
        let authority = allow(&db, &both("crm.customer.get", "phone", "whatsapp")).await;

        let empty = json!({
            "input": { "customer_id": "c-1", "name": "Marta" },
            "steps": { "libres": { "options": [] } }
        });
        prepare_in(&db, &asking("steps.libres.options"), &authority, &empty)
            .await
            .expect("an empty read is an empty list, and the run does not fail over it");

        // Eleven rows is a Meta limit, and this door does not know Meta's limits on purpose.
        let many: Vec<Json> = (0..11)
            .map(|i| json!({ "id": format!("s{i}"), "title": format!("1{i}:00") }))
            .collect();
        let over = json!({
            "input": { "customer_id": "c-1", "name": "Marta" },
            "steps": { "libres": { "options": many } }
        });
        prepare_in(&db, &asking("steps.libres.options"), &authority, &over)
            .await
            .expect("how many rows Meta holds is the proxy's question, not this one's");
    }

    /// **A whole SECTION nobody published is the same hole as its rows** (hub#1646).
    ///
    /// `interactive` has no inner shape in `flow.schema.json`, so a document is free to map a
    /// section whole instead of only its rows — an `ai` turn that hands back a titled block. When
    /// the step that owed it never published, `resolve` leaves a `null` sitting in the array and
    /// the message used to be queued as `sections: [null]`: a list with nothing to tap, refused by
    /// the proxy hours later, which is exactly what this door exists to stop.
    #[tokio::test]
    async fn a_whole_section_nobody_published_stops_the_step_like_its_rows_would() {
        let db = db().await;
        customer(&db, "c-1", "marta@example.com", "+34600111222").await;
        let authority = allow(&db, &both("crm.customer.get", "phone", "whatsapp")).await;

        let mapped_whole = |sections: Json| {
            FlowDefinition::parse(&json!({
                "schema_version": 1,
                "steps": [{
                    "id": "ask", "kind": "notify", "channel": "whatsapp",
                    "to": { "query": "crm.customer.get", "params": { "id": "input.customer_id" },
                            "field": "phone" },
                    "interactive": {
                        "type": "list",
                        "body": { "text": "¿Qué hueco te viene bien?" },
                        "action": { "button": "Ver huecos", "sections": sections }
                    }
                }]
            }))
            .unwrap()
            .steps
            .remove(0)
        };

        let err = prepare_in(
            &db,
            &mapped_whole(json!(["steps.libres.section"])),
            &authority,
            &scope(),
        )
        .await
        .unwrap_err();
        let RuntimeError::Domain { code, message } = &err else {
            panic!("a promised section that is not there is a domain refusal: {err}");
        };
        assert_eq!(code, ERR_OPTIONS_NOT_FOUND);
        assert!(
            message.contains("action.sections[0]"),
            "the refusal says which section is the hole: {message}"
        );
        assert!(
            message.contains("`libres`"),
            "…and the step that was supposed to publish it: {message}"
        );

        // **The control**: the same document with the section published queues, and a section that
        // is there with an EMPTY list of rows is still not a missing one (hub#1641).
        let published = json!({
            "input": { "customer_id": "c-1", "name": "Marta" },
            "steps": { "libres": { "section": { "title": "Huecos", "rows": [] } } }
        });
        let prepared = prepare_in(
            &db,
            &mapped_whole(json!(["steps.libres.section"])),
            &authority,
            &published,
        )
        .await
        .expect("a section that IS there is queued, empty rows and all");
        let payload: Json =
            serde_json::from_str(prepared.queue_op.1["payload"].as_str().unwrap()).unwrap();
        assert_eq!(
            payload["interactive"]["action"]["sections"][0]["title"],
            json!("Huecos")
        );
    }

    /// A plain `notify` (no `interactive`) whose copy is mapped from the run.
    fn saying(vars: Json) -> StepDef {
        FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "confirm", "kind": "notify", "channel": "whatsapp",
                "to": { "query": "crm.customer.get", "params": { "id": "input.customer_id" },
                        "field": "phone" },
                "template": "",
                "vars": vars
            }]
        }))
        .unwrap()
        .steps
        .remove(0)
    }

    fn refused_for_text(err: &RuntimeError) -> &str {
        match err {
            RuntimeError::Domain { code, message } if code == ERR_TEXT_NOT_FOUND => message,
            other => panic!("a promised text that is not there is refused as such: {other}"),
        }
    }

    /// **The copy the message promises and the run does not have stops the step** (hub#1660).
    ///
    /// The WhatsApp recipes answer the customer with `{"text": "{{steps.book_appointment.text}}"}`:
    /// the words are written by an earlier step. When that step never published them — it failed
    /// under `on_error: "continue"`, or the document names one that does not exist — the template
    /// filled in as `""` and the message used to be queued anyway, with nothing to say, and the
    /// refusal arrived hours later at the proxy. Same hole as the options (hub#1646), on the text.
    #[tokio::test]
    async fn a_text_nobody_published_stops_the_step_instead_of_queuing_an_empty_message() {
        let db = db().await;
        customer(&db, "c-1", "marta@example.com", "+34600111222").await;
        let authority = allow(&db, &both("crm.customer.get", "phone", "whatsapp")).await;

        // Both ways a document maps a text: a `{{…}}` template and a bare path.
        for mapped in ["{{steps.book.text}}", "steps.book.text"] {
            let err = prepare_in(&db, &saying(json!({ "text": mapped })), &authority, &scope())
                .await
                .unwrap_err();
            let message = refused_for_text(&err);
            assert!(message.contains("`book`"), "names the step that owed it: {message}");
            assert!(message.contains("vars.text"), "…and where the hole is: {message}");
        }

        // **The control**: the same documents with the step that writes the text are queued, with
        // that text on the wire.
        let published = json!({
            "input": { "customer_id": "c-1", "name": "Marta" },
            "steps": { "book": { "text": "Te espero el martes a las 10:00." } }
        });
        for mapped in ["{{steps.book.text}}", "steps.book.text"] {
            let prepared =
                prepare_in(&db, &saying(json!({ "text": mapped })), &authority, &published)
                    .await
                    .expect("a text that IS there is queued");
            let payload: Json =
                serde_json::from_str(prepared.queue_op.1["payload"].as_str().unwrap()).unwrap();
            assert_eq!(payload["vars"]["text"], json!("Te espero el martes a las 10:00."));
        }
    }

    /// Every `vars` entry is a promise, not only `text`: a template variable filled with nothing
    /// is refused by Meta the same way (hub#821), and several placeholders that ALL resolve to
    /// nothing are still nothing.
    #[tokio::test]
    async fn any_var_left_with_nothing_is_the_same_hole() {
        let db = db().await;
        customer(&db, "c-1", "marta@example.com", "+34600111222").await;
        let authority = allow(&db, &both("crm.customer.get", "phone", "whatsapp")).await;

        let err = prepare_in(
            &db,
            &saying(json!({ "text": "Hola", "when": " {{steps.slot.day}} {{steps.slot.time}} " })),
            &authority,
            &scope(),
        )
        .await
        .unwrap_err();
        let message = refused_for_text(&err);
        assert!(message.contains("vars.when"), "{message}");
        assert!(message.contains("`slot`"), "{message}");
    }

    /// **Only «nothing» counts** — the frontier hub#1646 already drew for the options.
    ///
    /// - An empty string the run DID publish is the author's (or the step's) decision.
    /// - A text with words of its own and a placeholder that came back empty still says
    ///   something: that is what every automation tool of the market does with a missing merge
    ///   field (Zapier, Make, Shopify Flow, Klaviyo without a default), and refusing it would stop
    ///   recipes that work today.
    /// - A literal the author typed is never looked at.
    #[tokio::test]
    async fn an_empty_text_the_run_published_and_words_around_a_hole_are_still_sent() {
        let db = db().await;
        customer(&db, "c-1", "marta@example.com", "+34600111222").await;
        let authority = allow(&db, &both("crm.customer.get", "phone", "whatsapp")).await;

        let published_empty = json!({
            "input": { "customer_id": "c-1", "name": "Marta" },
            "steps": { "book": { "text": "", "note": null } }
        });
        for vars in [
            json!({ "text": "Hola", "note": "{{steps.book.text}}" }),
            json!({ "text": "Hola", "note": "steps.book.text" }),
            json!({ "text": "Hola {{steps.book.missing}}, te esperamos" }),
            json!({ "text": "Hola", "note": "" }),
            // Only placeholders, one of them there: the run HAD part of it.
            json!({ "text": "Hola", "note": "{{steps.book.text}} {{steps.book.missing}}" }),
        ] {
            prepare_in(&db, &saying(vars.clone()), &authority, &published_empty)
                .await
                .unwrap_or_else(|e| panic!("{vars} is not a promise the run broke: {e}"));
        }

        // A step that published an explicit `null` published NOTHING: the key being there does
        // not make it a text.
        let err = prepare_in(
            &db,
            &saying(json!({ "text": "{{steps.book.note}}" })),
            &authority,
            &published_empty,
        )
        .await
        .unwrap_err();
        refused_for_text(&err);
    }

    /// The copy of a message that ALSO offers options: the options are there (so hub#1646's door
    /// lets it through) and the text above them is not — exactly the probe in the issue.
    #[tokio::test]
    async fn the_body_of_a_list_nobody_published_stops_the_step_even_with_its_rows_there() {
        let db = db().await;
        customer(&db, "c-1", "marta@example.com", "+34600111222").await;
        let authority = allow(&db, &both("crm.customer.get", "phone", "whatsapp")).await;

        let with = |place: &str, text: &str| {
            let mut interactive = json!({
                "type": "list",
                "body": { "text": "¿Qué hueco te viene bien?" },
                "action": { "button": "Ver huecos",
                            "sections": [{ "title": "Huecos", "rows": "steps.libres.options" }] }
            });
            interactive[place] = json!({ "text": text });
            FlowDefinition::parse(&json!({
                "schema_version": 1,
                "steps": [{
                    "id": "ask", "kind": "notify", "channel": "whatsapp",
                    "to": { "query": "crm.customer.get", "params": { "id": "input.customer_id" },
                            "field": "phone" },
                    "interactive": interactive
                }]
            }))
            .unwrap()
            .steps
            .remove(0)
        };
        let options_only = json!({
            "input": { "customer_id": "c-1", "name": "Marta" },
            "steps": { "libres": { "options": [{ "id": "s1", "title": "10:00" }] } }
        });

        for place in ["body", "header", "footer"] {
            let err = prepare_in(
                &db,
                &with(place, "steps.libres.summary"),
                &authority,
                &options_only,
            )
            .await
            .unwrap_err();
            let message = refused_for_text(&err);
            assert!(
                message.contains(&format!("interactive.{place}.text")),
                "{place}: {message}"
            );
            assert!(message.contains("`libres`"), "{place}: {message}");
        }

        // A whole body mapped from a step that never published it is the same hole, one level up.
        let mut whole = with("body", "x");
        if let StepSpec::Notify(spec) = &mut whole.spec {
            spec.interactive.as_mut().unwrap()["body"] = json!("steps.libres.body");
        }
        let err = prepare_in(&db, &whole, &authority, &options_only)
            .await
            .unwrap_err();
        assert!(refused_for_text(&err).contains("interactive.body"));

        // **The control**: with the summary published the same message is queued.
        let both_there = json!({
            "input": { "customer_id": "c-1", "name": "Marta" },
            "steps": { "libres": { "options": [{ "id": "s1", "title": "10:00" }],
                                   "summary": "Mañana quedan huecos por la tarde" } }
        });
        let prepared = prepare_in(
            &db,
            &with("body", "steps.libres.summary"),
            &authority,
            &both_there,
        )
        .await
        .expect("a body that IS there is queued");
        let payload: Json =
            serde_json::from_str(prepared.queue_op.1["payload"].as_str().unwrap()).unwrap();
        assert_eq!(
            payload["interactive"]["body"]["text"],
            json!("Mañana quedan huecos por la tarde")
        );
    }
}
