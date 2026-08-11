//! **The write that waits for a person** (`_flow_approvals`, ADR-0283 D3 — hub#665).
//!
//! An `ai` step is the one place in the kernel where what happens next is not written in the
//! document: it comes from a model. So a write the model proposes does not execute — under the
//! DEFAULT policy it becomes a row here, and the run stops until somebody decides.
//!
//! Three properties are the whole point, and each of them is a decision that could have gone the
//! other way:
//!
//! 1. **The payload is stored, not re-derived.** Approving runs *exactly* what was proposed. A
//!    payload rebuilt at approval time — by asking the model again, or by re-reading the run —
//!    would be a different booking wearing the same name, and the person who pressed «approve»
//!    read the first one.
//! 2. **The grant is re-checked at the moment of approving**, not at the moment of proposing.
//!    A proposal is not a stored permission: between 3 AM and 9 AM the owner may have taken the
//!    capability away, and the tray must not be a way around that.
//! 3. **Approving never re-enters the LLM.** What runs is the command in this row. Re-planning
//!    after a rejection is product (the module `flows`), not kernel — and a kernel that quietly
//!    asked the model again would make «I approved *this*» mean nothing.
//!
//! `decided_by` comes from the resolved session and never from a request body — same rule as
//! `discarded_by` in `outbox_admin.rs`. "Who authorised the hub to write while nobody was
//! watching" is the one fact this table exists to keep.
use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Value as Json};

use crate::errors::{Result, RuntimeError};
use crate::registry::{new_id, now_rfc3339};

pub const ERR_APPROVAL_NOT_FOUND: &str = "flow.approval_not_found";
pub const ERR_APPROVAL_ALREADY_DECIDED: &str = "flow.approval_already_decided";
pub const ERR_APPROVAL_EXPIRED: &str = "flow.approval_expired";

pub const STATUS_PENDING: &str = "pending";
pub const STATUS_APPROVED: &str = "approved";
pub const STATUS_REJECTED: &str = "rejected";

/// How long a proposal stays decidable. A booking proposed for «tomorrow at 10» stops being a
/// question worth answering once tomorrow has passed, and an approval left lying around for a
/// month is a standing authorisation nobody remembers granting.
pub const DEFAULT_TTL_HOURS: i64 = 72;

/// The name of the ephemeral event the WS carries so the tray lights up without polling. The
/// SCREEN is the module `flows`'s job (ADR-0283 §7); the core emits the fact.
pub const EVENT_APPROVAL_CREATED: &str = "flow.approval.created";

/// One proposal, as the tray shows it.
#[derive(Debug, Clone, serde::Serialize)]
pub struct Approval {
    pub id: String,
    pub run_id: String,
    pub flow_id: String,
    pub step_id: String,
    /// The command that will run, verbatim.
    pub command: String,
    /// …with exactly these arguments. This is what «approve» means.
    pub payload: Json,
    /// What the model said it was doing. Free text from a model: shown, never trusted.
    pub reason: String,
    pub status: String,
    pub decided_by: String,
    pub decided_at: Option<String>,
    pub expires_at: Option<String>,
    /// Why the approved command failed, if it did. Empty otherwise.
    pub error: String,
    pub created_at: String,
}

/// What the agent runner hands over when the model proposes a write.
#[derive(Debug, Clone)]
pub struct NewApproval {
    pub run_id: String,
    pub flow_id: String,
    pub step_id: String,
    pub command: String,
    pub payload: Json,
    pub reason: String,
    /// What the turn produced BEFORE it stopped (the model's text, the reads it did). It is
    /// parked on the step row so that, when the approval is decided hours later, the step's
    /// output is the whole turn and not just its ending.
    pub partial_output: Json,
}

fn not_found(id: &str) -> RuntimeError {
    RuntimeError::Domain {
        code: ERR_APPROVAL_NOT_FOUND.to_string(),
        message: format!("no approval `{id}` in this hub"),
    }
}

/// Writes the proposal. The caller (`Runtime::request_flow_approval`) parks the run in the same
/// gesture: a row here with a run still marching forward would be a question nobody is waiting for.
pub async fn create(db: &dyn DatabaseAdapter, hub_id: &str, new: &NewApproval) -> Result<Approval> {
    let id = new_id();
    let now = now_rfc3339();
    let expires_at = (chrono::Utc::now() + chrono::Duration::hours(DEFAULT_TTL_HOURS)).to_rfc3339();
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("run_id".into(), json!(new.run_id));
    p.insert("flow_id".into(), json!(new.flow_id));
    p.insert("step_id".into(), json!(new.step_id));
    p.insert("command".into(), json!(new.command));
    p.insert("payload".into(), json!(new.payload.to_string()));
    p.insert("reason".into(), json!(new.reason));
    p.insert("status".into(), json!(STATUS_PENDING));
    p.insert("expires_at".into(), json!(expires_at));
    p.insert("now".into(), json!(now));
    db.execute(
        "INSERT INTO _flow_approvals \
           (id, hub_id, run_id, flow_id, step_id, command, payload, reason, status, expires_at, \
            created_at, updated_at) \
         VALUES (:id, :hub_id, :run_id, :flow_id, :step_id, :command, :payload, :reason, :status, \
                 :expires_at, :now, :now)",
        &p,
    )
    .await?;
    get(db, hub_id, &id).await
}

pub async fn get(db: &dyn DatabaseAdapter, hub_id: &str, id: &str) -> Result<Approval> {
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT id, run_id, flow_id, step_id, command, payload, reason, status, decided_by, \
                    decided_at, expires_at, error, created_at \
             FROM _flow_approvals WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL",
            &p,
        )
        .await?;
    res.rows.first().map(row).ok_or_else(|| not_found(id))
}

/// The tray. `status = None` lists everything, newest first — the pending ones are what a person
/// acts on, the decided ones are the audit of what the hub did overnight.
pub async fn list(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    status: Option<&str>,
    limit: i64,
) -> Result<Vec<Approval>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("limit".into(), json!(limit.clamp(1, 200)));
    let sql = if status.is_some() {
        p.insert("status".into(), json!(status.unwrap_or_default()));
        "SELECT id, run_id, flow_id, step_id, command, payload, reason, status, decided_by, \
                decided_at, expires_at, error, created_at \
         FROM _flow_approvals \
         WHERE hub_id = :hub_id AND status = :status AND deleted_at IS NULL \
         ORDER BY created_at DESC, id DESC LIMIT :limit"
    } else {
        "SELECT id, run_id, flow_id, step_id, command, payload, reason, status, decided_by, \
                decided_at, expires_at, error, created_at \
         FROM _flow_approvals WHERE hub_id = :hub_id AND deleted_at IS NULL \
         ORDER BY created_at DESC, id DESC LIMIT :limit"
    };
    let res = db.query(sql, &p).await?;
    Ok(res.rows.iter().map(row).collect())
}

/// Reads a proposal that is still decidable, refusing by NAME when it is not.
///
/// The two refusals are different questions with different remedies, so they are different codes:
/// `already_decided` is the second press of a button (and must never book twice), `expired` is a
/// question about a Tuesday that has passed.
pub async fn claim_pending(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    id: &str,
) -> Result<Approval> {
    let approval = get(db, hub_id, id).await?;
    if approval.status != STATUS_PENDING {
        return Err(RuntimeError::Domain {
            code: ERR_APPROVAL_ALREADY_DECIDED.to_string(),
            message: format!(
                "approval `{id}` was already {} by `{}`",
                approval.status, approval.decided_by
            ),
        });
    }
    if let Some(expires_at) = &approval.expires_at {
        if expires_at.as_str() < now_rfc3339().as_str() {
            return Err(RuntimeError::Domain {
                code: ERR_APPROVAL_EXPIRED.to_string(),
                message: format!(
                    "approval `{id}` expired at {expires_at}; what it proposed was about a moment \
                     that has passed"
                ),
            });
        }
    }
    Ok(approval)
}

/// Records the decision. Called AFTER the command has run (or not), so the row never says
/// «approved» about something that did not happen the way it says.
pub async fn mark_decided(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    id: &str,
    status: &str,
    decided_by: &str,
    error: &str,
) -> Result<Approval> {
    let now = now_rfc3339();
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("status".into(), json!(status));
    p.insert("by".into(), json!(decided_by));
    p.insert("error".into(), json!(error));
    p.insert("now".into(), json!(now));
    db.execute(
        "UPDATE _flow_approvals \
         SET status = :status, decided_by = :by, decided_at = :now, error = :error, \
             updated_at = :now \
         WHERE id = :id AND hub_id = :hub_id AND status = 'pending' AND deleted_at IS NULL",
        &p,
    )
    .await?;
    get(db, hub_id, id).await
}

fn row(r: &Json) -> Approval {
    let text = |k: &str| r[k].as_str().unwrap_or_default().to_string();
    let opt = |k: &str| r[k].as_str().map(|s| s.to_string());
    Approval {
        id: text("id"),
        run_id: text("run_id"),
        flow_id: text("flow_id"),
        step_id: text("step_id"),
        command: text("command"),
        payload: serde_json::from_str(&text("payload")).unwrap_or(json!({})),
        reason: text("reason"),
        status: text("status"),
        decided_by: text("decided_by"),
        decided_at: opt("decided_at"),
        expires_at: opt("expires_at"),
        error: text("error"),
        created_at: text("created_at"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flows::test_support;
    use erplora_db::testutil::fresh_db;

    const HUB: &str = "hub-approvals";

    /// The stable error code of a domain refusal. `Display` carries only the message.
    fn code_of(err: &RuntimeError) -> &str {
        match err {
            RuntimeError::Domain { code, .. } => code,
            other => panic!("expected a domain refusal, got {other}"),
        }
    }

    async fn db() -> impl DatabaseAdapter {
        let db = fresh_db().await;
        test_support::ensure_schema(&db, HUB).await;
        db
    }

    fn proposal(command: &str) -> NewApproval {
        NewApproval {
            run_id: "run-1".into(),
            flow_id: "flow-1".into(),
            step_id: "agent".into(),
            command: command.into(),
            payload: json!({ "customer": "Marta", "minutes": 45 }),
            reason: "the customer asked for a colour, which takes 45 minutes".into(),
            partial_output: json!({ "text": "I will book it" }),
        }
    }

    /// The payload is stored VERBATIM, because it is what «approve» means. A tray that showed a
    /// summary and ran something rebuilt from it would be a button people press about one thing
    /// while another happens.
    #[tokio::test]
    async fn a_proposal_keeps_the_command_and_its_payload_exactly() {
        let db = db().await;
        let created = create(&db, HUB, &proposal("agenda.booking.create"))
            .await
            .unwrap();

        assert_eq!(created.status, STATUS_PENDING);
        assert_eq!(created.command, "agenda.booking.create");
        assert_eq!(created.payload["minutes"], json!(45));
        assert!(
            created.reason.contains("45 minutes"),
            "what the model said it was doing is shown to the person deciding"
        );
        assert!(
            created.expires_at.is_some(),
            "a proposal is not a standing authorisation"
        );

        let read_back = get(&db, HUB, &created.id).await.unwrap();
        assert_eq!(read_back.payload, created.payload);
    }

    /// One decision per proposal. Two admins on the same screen, or one double-click, must not
    /// book twice — and the refusal has to be recognisable, because the module `flows` shows a
    /// different message for «somebody already did this» than for a real error.
    #[tokio::test]
    async fn a_decided_proposal_cannot_be_decided_again() {
        let db = db().await;
        let created = create(&db, HUB, &proposal("agenda.booking.create"))
            .await
            .unwrap();
        claim_pending(&db, HUB, &created.id).await.unwrap();
        mark_decided(&db, HUB, &created.id, STATUS_APPROVED, "hub_user:1", "")
            .await
            .unwrap();

        let err = claim_pending(&db, HUB, &created.id)
            .await
            .expect_err("the second press must not book a second appointment");
        assert!(format!("{err}").contains("hub_user:1"), "{err}");
        assert_eq!(
            get(&db, HUB, &created.id).await.unwrap().decided_by,
            "hub_user:1"
        );
    }

    /// A proposal about a moment that has passed is refused by its own name, not silently run.
    #[tokio::test]
    async fn an_expired_proposal_is_refused_by_name() {
        let db = db().await;
        let created = create(&db, HUB, &proposal("agenda.booking.create"))
            .await
            .unwrap();
        let mut p = Params::new();
        p.insert("id".into(), json!(created.id));
        db.execute(
            "UPDATE _flow_approvals SET expires_at = '2020-01-01T00:00:00+00:00' WHERE id = :id",
            &p,
        )
        .await
        .unwrap();

        let err = claim_pending(&db, HUB, &created.id)
            .await
            .expect_err("yesterday's booking is not a question worth answering today");
        // The stable CODE, not the prose: `RuntimeError::Domain` shows only its message, and the
        // code is the half the module `flows` programs against (flows.md §13.8).
        assert_eq!(code_of(&err), ERR_APPROVAL_EXPIRED, "{err}");
    }

    #[tokio::test]
    async fn the_tray_filters_by_status_and_a_neighbouring_hub_sees_nothing() {
        let db = db().await;
        test_support::ensure_schema(&db, "hub-next-door").await;
        let one = create(&db, HUB, &proposal("agenda.booking.create"))
            .await
            .unwrap();
        create(&db, HUB, &proposal("agenda.booking.cancel"))
            .await
            .unwrap();
        mark_decided(&db, HUB, &one.id, STATUS_REJECTED, "hub_user:1", "")
            .await
            .unwrap();

        let pending = list(&db, HUB, Some(STATUS_PENDING), 50).await.unwrap();
        assert_eq!(pending.len(), 1);
        assert_eq!(pending[0].command, "agenda.booking.cancel");
        assert_eq!(list(&db, HUB, None, 50).await.unwrap().len(), 2);
        assert!(
            list(&db, "hub-next-door", None, 50).await.unwrap().is_empty(),
            "the tenant is never negotiable"
        );
        assert!(get(&db, "hub-next-door", &one.id).await.is_err());
    }
}
