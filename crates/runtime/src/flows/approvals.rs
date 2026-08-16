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
/// The caller is authenticated and is simply not who the question was addressed to (hub#950).
/// Its own code because the remedy is a different one: not «log in», not «try again», but «ask
/// somebody with that role» — and the tray shows a different message for each.
pub const ERR_APPROVAL_NOT_YOURS: &str = "flow.approval_not_yours";

/// **What kind of question this row is** — the column that generalises the table instead of
/// forking it (hub#950).
///
/// `command` is the original: a WRITE a model proposed, with its payload stored verbatim, and
/// approving RUNS it. `decision` is the generic `approval` step: a question in words, with no
/// command and no payload, and approving runs **nothing** — it records an answer and lets the run
/// carry on to the step that does the work.
///
/// One table and not two because everything around them is the same thing: one tray, one
/// idempotency rule, one expiry sweep, one audit of who decided what. The difference is what
/// «approve» executes, and that is one branch in one method.
pub const KIND_COMMAND: &str = "command";
pub const KIND_DECISION: &str = "decision";

pub const STATUS_PENDING: &str = "pending";
pub const STATUS_APPROVED: &str = "approved";
pub const STATUS_REJECTED: &str = "rejected";
/// Nobody answered in time (hub#972). A **decided** status, terminal like the other two: what it
/// says is that the question is closed, not that it is still hanging.
pub const STATUS_EXPIRED: &str = "expired";

/// Who closes an expired proposal. Not a person, and it cannot be mistaken for one: every human
/// principal in this hub is `hub_user:…`. The row still records WHEN it was closed, because
/// «nobody answered» is a fact about a moment.
pub const DECIDED_BY_EXPIRY: &str = "system:expiry";

/// How long a proposal stays decidable. A booking proposed for «tomorrow at 10» stops being a
/// question worth answering once tomorrow has passed, and an approval left lying around for a
/// month is a standing authorisation nobody remembers granting.
pub const DEFAULT_TTL_HOURS: i64 = 72;

/// The name of the ephemeral event the WS carries so the tray lights up without polling. The
/// SCREEN is the module `flows`'s job (ADR-0283 §7); the core emits the fact.
pub const EVENT_APPROVAL_CREATED: &str = "flow.approval.created";

/// …and the one the sweep emits, so a tray that was open all night stops showing a question that
/// can no longer be answered. Same shape and same reason as [`EVENT_APPROVAL_CREATED`].
pub const EVENT_APPROVAL_EXPIRED: &str = "flow.approval.expired";

/// **What happens to the RUN when its proposal expires** — the value of the `on_expire` column.
///
/// It is a column and not a constant because the answer belongs to whoever wrote the flow: the
/// generic `approval` step (hub#950) sets it per document, and the sweep is the one place that
/// reads it. Storing it next to the `payload` — rather than looking the flow up at sweep time —
/// keeps the same property the payload has: editing (or deleting) the flow does not change what a
/// proposal already in the tray means.
pub const ON_EXPIRE_REJECT: &str = "reject";
pub const ON_EXPIRE_CANCEL: &str = "cancel";
pub const ON_EXPIRE_CONTINUE: &str = "continue";

/// The parsed form of that column.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExpiryPolicy {
    /// Treat the silence as a **refusal** — the DEFAULT, and the conservative reading. The steps
    /// written after an `ai` step assumed it acted; carrying on as if it had would be the one
    /// mistake an approval exists to prevent. Today a rejection ends the run (§14.7), so this and
    /// [`ExpiryPolicy::Cancel`] land in the same place; they stop being synonyms the day `on_reject`
    /// exists, and the row already says which one was meant.
    Reject,
    /// End the run, without calling it a refusal.
    Cancel,
    /// Carry on to the next step. Opt-in, for a document whose remaining steps do NOT depend on
    /// the write — the `Limit Wait Time` of n8n, not a default anybody should inherit.
    Continue,
}

impl ExpiryPolicy {
    /// Anything unrecognised degrades to [`ExpiryPolicy::Reject`]. A row written by a newer version
    /// (or by hand) must not be able to talk this hub into carrying on: the failure mode of
    /// guessing here is a write nobody authorised.
    pub fn parse(raw: &str) -> Self {
        match raw {
            ON_EXPIRE_CONTINUE => Self::Continue,
            ON_EXPIRE_CANCEL => Self::Cancel,
            _ => Self::Reject,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Reject => ON_EXPIRE_REJECT,
            Self::Cancel => ON_EXPIRE_CANCEL,
            Self::Continue => ON_EXPIRE_CONTINUE,
        }
    }

    /// Every value, in document order. Mirrored by `schemas/flow.schema.json`.
    pub const ALL: &'static [ExpiryPolicy] = &[Self::Reject, Self::Cancel, Self::Continue];
}

/// **What happens to the RUN when a person says no** — the value of the `on_reject` column
/// (hub#950).
///
/// A column for the same reason `on_expire` is one: the answer belongs to whoever wrote the flow,
/// and it has to be the answer that was in force when the question was ASKED. Editing the document
/// while somebody is looking at the tray must not change what her refusal costs.
pub const ON_REJECT_CANCEL: &str = "cancel";
pub const ON_REJECT_CONTINUE: &str = "continue";

/// The parsed form of that column.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RejectPolicy {
    /// End the run — **the DEFAULT, and what a rejection has always done**. The steps written after
    /// an approval assumed it was granted, so carrying on without it is the one mistake an approval
    /// exists to prevent. `cancelled` and not `failed`: a person stopping the hub is the design
    /// working.
    Cancel,
    /// Carry on to the next step with `steps.<id>.decision == "rejected"`. Opt-in, and it is what
    /// makes the three branches of the original contract composable out of a LINEAR document: a
    /// `condition` written after the approval IS the «rejected» branch.
    Continue,
}

impl RejectPolicy {
    /// Anything unrecognised degrades to [`RejectPolicy::Cancel`], the same rule and the same
    /// reason as [`ExpiryPolicy::parse`]: a row written by a newer version — or by hand — must not
    /// be able to talk this hub into carrying a run past a refusal.
    pub fn parse(raw: &str) -> Self {
        match raw {
            ON_REJECT_CONTINUE => Self::Continue,
            _ => Self::Cancel,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Cancel => ON_REJECT_CANCEL,
            Self::Continue => ON_REJECT_CONTINUE,
        }
    }

    pub const ALL: &'static [RejectPolicy] = &[Self::Cancel, Self::Continue];
}

/// One proposal, as the tray shows it.
#[derive(Debug, Clone, serde::Serialize)]
pub struct Approval {
    pub id: String,
    pub run_id: String,
    pub flow_id: String,
    pub step_id: String,
    /// [`KIND_COMMAND`] or [`KIND_DECISION`] — what «approve» will execute, if anything.
    pub kind: String,
    /// The command that will run, verbatim. **Empty for a `decision`**: that kind executes nothing.
    pub command: String,
    /// …with exactly these arguments. This is what «approve» means.
    pub payload: Json,
    /// What the model said it was doing. Free text from a model: shown, never trusted.
    pub reason: String,
    /// **The question, already templated** (hub#950). Rendered against the run when the row was
    /// written, not when the tray is read: editing the flow afterwards must not change what the
    /// person in front of the screen is agreeing to — the same property `payload` has.
    pub title: String,
    /// The second line of the same question. Optional.
    pub summary: String,
    /// The role that may answer, resolved server-side at the moment of deciding. Empty = whoever
    /// administers the hub, which is what the tray has always required.
    pub assignee_role: String,
    /// What the person typed when she decided. Part of the audit and part of the step's output.
    pub comment: String,
    pub status: String,
    pub decided_by: String,
    pub decided_at: Option<String>,
    pub expires_at: Option<String>,
    /// What the sweep will do to the RUN if `expires_at` passes with nobody answering. Shown in
    /// the tray for the same reason `expires_at` is: it is half of what «leave this for later»
    /// costs.
    pub on_expire: String,
    /// …and what saying no costs. The other half, and shown for the same reason.
    pub on_reject: String,
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

/// **The question the generic `approval` step asks** (hub#950).
///
/// Everything a person needs in order to decide is here, and it is here because it was rendered
/// when the question was asked: the title and the summary are already templated, so editing (or
/// deleting) the flow afterwards cannot change what she is agreeing to. That is the same property
/// the `payload` of a model's proposal has, and the reason the design did not need a snapshot of
/// the whole document in `vars`.
#[derive(Debug, Clone)]
pub struct NewDecision {
    pub run_id: String,
    pub flow_id: String,
    pub step_id: String,
    /// Already rendered against the run.
    pub title: String,
    /// Already rendered against the run. May be empty.
    pub summary: String,
    /// Empty = whoever administers the hub.
    pub assignee_role: String,
    /// How long it stays decidable, from now.
    pub expires_in_seconds: i64,
    pub on_expire: ExpiryPolicy,
    pub on_reject: RejectPolicy,
}

/// Every column of one row, so the two public constructors share ONE insert. Two `INSERT`s over
/// the same table is how the two kinds would quietly drift apart.
struct Row<'a> {
    run_id: &'a str,
    flow_id: &'a str,
    step_id: &'a str,
    kind: &'a str,
    command: &'a str,
    payload: String,
    reason: &'a str,
    title: &'a str,
    summary: &'a str,
    assignee_role: &'a str,
    expires_at: String,
    on_expire: ExpiryPolicy,
    on_reject: RejectPolicy,
}

async fn insert(db: &dyn DatabaseAdapter, hub_id: &str, r: Row<'_>) -> Result<Approval> {
    let id = new_id();
    let now = now_rfc3339();
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("run_id".into(), json!(r.run_id));
    p.insert("flow_id".into(), json!(r.flow_id));
    p.insert("step_id".into(), json!(r.step_id));
    p.insert("kind".into(), json!(r.kind));
    p.insert("command".into(), json!(r.command));
    p.insert("payload".into(), json!(r.payload));
    p.insert("reason".into(), json!(r.reason));
    p.insert("title".into(), json!(r.title));
    p.insert("summary".into(), json!(r.summary));
    p.insert("assignee_role".into(), json!(r.assignee_role));
    p.insert("status".into(), json!(STATUS_PENDING));
    p.insert("expires_at".into(), json!(r.expires_at));
    p.insert("on_expire".into(), json!(r.on_expire.as_str()));
    p.insert("on_reject".into(), json!(r.on_reject.as_str()));
    p.insert("now".into(), json!(now));
    db.execute(
        "INSERT INTO _flow_approvals \
           (id, hub_id, run_id, flow_id, step_id, kind, command, payload, reason, title, summary, \
            assignee_role, status, expires_at, on_expire, on_reject, created_at, updated_at) \
         VALUES (:id, :hub_id, :run_id, :flow_id, :step_id, :kind, :command, :payload, :reason, \
                 :title, :summary, :assignee_role, :status, :expires_at, :on_expire, :on_reject, \
                 :now, :now)",
        &p,
    )
    .await?;
    get(db, hub_id, &id).await
}

/// Writes the proposal. The caller (`Runtime::request_flow_approval`) parks the run in the same
/// gesture: a row here with a run still marching forward would be a question nobody is waiting for.
pub async fn create(db: &dyn DatabaseAdapter, hub_id: &str, new: &NewApproval) -> Result<Approval> {
    insert(
        db,
        hub_id,
        Row {
            run_id: &new.run_id,
            flow_id: &new.flow_id,
            step_id: &new.step_id,
            kind: KIND_COMMAND,
            command: &new.command,
            payload: new.payload.to_string(),
            reason: &new.reason,
            title: "",
            summary: "",
            assignee_role: "",
            expires_at: (chrono::Utc::now() + chrono::Duration::hours(DEFAULT_TTL_HOURS))
                .to_rfc3339(),
            on_expire: ExpiryPolicy::Reject,
            // An `ai` step has no way to say otherwise, so this is exactly what a rejection has
            // always done. Reading it from the row rather than branching on the kind is what keeps
            // `decide_flow_approval` one method with one rule.
            on_reject: RejectPolicy::Cancel,
        },
    )
    .await
}

/// Writes the question an `approval` step asks. Same table, same tray, same sweep — what differs
/// is that there is nothing to execute at the end of it.
pub async fn create_decision(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    new: &NewDecision,
) -> Result<Approval> {
    insert(
        db,
        hub_id,
        Row {
            run_id: &new.run_id,
            flow_id: &new.flow_id,
            step_id: &new.step_id,
            kind: KIND_DECISION,
            command: "",
            payload: "{}".to_string(),
            reason: "",
            title: &new.title,
            summary: &new.summary,
            assignee_role: &new.assignee_role,
            expires_at: (chrono::Utc::now()
                + chrono::Duration::seconds(new.expires_in_seconds.max(1)))
            .to_rfc3339(),
            on_expire: new.on_expire,
            on_reject: new.on_reject,
        },
    )
    .await
}

/// Every column the tray and the executor read, in one place: three `SELECT`s listing them by hand
/// is how one of them ends up missing a column that then silently reads as its default.
const COLUMNS: &str = "id, run_id, flow_id, step_id, kind, command, payload, reason, title, \
                       summary, assignee_role, comment, status, decided_by, decided_at, \
                       expires_at, on_expire, on_reject, error, created_at";

pub async fn get(db: &dyn DatabaseAdapter, hub_id: &str, id: &str) -> Result<Approval> {
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            &format!(
                "SELECT {COLUMNS} FROM _flow_approvals \
                 WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL"
            ),
            &p,
        )
        .await?;
    res.rows.first().map(row).ok_or_else(|| not_found(id))
}

/// **The question this run is already parked on**, if any — the idempotency key of the `approval`
/// step, derived from the run and the step exactly as the issue asks.
///
/// A tick that wrote the row and died before parking the run gets its lease reclaimed and
/// re-executes the step. Without this the person would find the same question twice, and answering
/// one would leave the other hanging until the sweep — the orphaned approval the Power Automate
/// forums are full of, grown in our own garden.
pub async fn pending_for_step(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    run_id: &str,
    step_id: &str,
) -> Result<Option<Approval>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("run_id".into(), json!(run_id));
    p.insert("step_id".into(), json!(step_id));
    p.insert("status".into(), json!(STATUS_PENDING));
    let res = db
        .query(
            &format!(
                "SELECT {COLUMNS} FROM _flow_approvals \
                 WHERE hub_id = :hub_id AND run_id = :run_id AND step_id = :step_id \
                   AND status = :status AND deleted_at IS NULL \
                 ORDER BY created_at DESC, id DESC LIMIT 1"
            ),
            &p,
        )
        .await?;
    Ok(res.rows.first().map(row))
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
        format!(
            "SELECT {COLUMNS} FROM _flow_approvals \
             WHERE hub_id = :hub_id AND status = :status AND deleted_at IS NULL \
             ORDER BY created_at DESC, id DESC LIMIT :limit"
        )
    } else {
        format!(
            "SELECT {COLUMNS} FROM _flow_approvals WHERE hub_id = :hub_id AND deleted_at IS NULL \
             ORDER BY created_at DESC, id DESC LIMIT :limit"
        )
    };
    let res = db.query(&sql, &p).await?;
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
    // A row the SWEEP closed (hub#972) is refused by the name it was closed under. Falling through
    // to `already_decided` would name a decider that does not exist and send the tray to the wrong
    // message: «somebody beat you to it» is a different fact from «this question is too old».
    if approval.status == STATUS_EXPIRED {
        return Err(expired(id, approval.expires_at.as_deref().unwrap_or("")));
    }
    if approval.status != STATUS_PENDING {
        return Err(RuntimeError::Domain {
            code: ERR_APPROVAL_ALREADY_DECIDED.to_string(),
            message: format!(
                "approval `{id}` was already {} by `{}`",
                approval.status, approval.decided_by
            ),
        });
    }
    // Still `pending`, but past its deadline: the hourly sweep has simply not come round yet. The
    // answer is the same one it will give afterwards — the person must not get a different verdict
    // depending on what minute she pressed the button.
    if let Some(expires_at) = &approval.expires_at {
        if expires_at.as_str() < now_rfc3339().as_str() {
            return Err(expired(id, expires_at));
        }
    }
    Ok(approval)
}

fn expired(id: &str, expires_at: &str) -> RuntimeError {
    RuntimeError::Domain {
        code: ERR_APPROVAL_EXPIRED.to_string(),
        message: format!(
            "approval `{id}` expired at {expires_at}; what it proposed was about a moment that \
             has passed"
        ),
    }
}

/// One proposal the sweep closed, and everything its caller needs to end (or resume) the run.
///
/// The sweep itself touches only `_flow_approvals`: this file has no executor and no event sink,
/// and giving it one would put «what happens to a run» in two places.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExpiredApproval {
    pub id: String,
    pub run_id: String,
    pub flow_id: String,
    pub step_id: String,
    /// [`KIND_COMMAND`] or [`KIND_DECISION`]. The two leave a different shape behind when the run
    /// carries on (`continue`): a model's turn plus how it ended, versus a decision — so the sweep
    /// has to know which it closed, and the row is what tells it.
    pub kind: String,
    pub command: String,
    /// The question, for a `decision`. Empty for a model's proposal, which names its `command`
    /// instead. It rides along in the `RETURNING` rather than being re-read afterwards: a second
    /// query per swept row, in a pass that already holds the runtime lock, to fetch a string the
    /// statement had in its hands.
    pub title: String,
    pub expires_at: String,
    /// Read from the ROW, not from the flow: see [`ExpiryPolicy`].
    pub on_expire: ExpiryPolicy,
}

/// Proposals closed per pass of the sweep. Smaller than the prune's [`crate::retention::BATCH`] on
/// purpose: closing one proposal is not one `DELETE` but a run being ended or resumed
/// (`complete_io`, several statements), and the whole pass happens under the runtime lock the tills
/// are queueing behind. The driver simply repeats the pass.
pub const SWEEP_BATCH: i64 = 100;

/// What one expiry sweep closed, so the caller can log it without a second query — same contract
/// as [`crate::retention::PruneReport`]: a silent sweep is indistinguishable from data loss the day
/// somebody looks for the proposal they were going to approve and does not find it.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct ExpirySweepReport {
    /// Proposals moved to `expired`.
    pub expired: u64,
    /// Runs ended by it (`reject`/`cancel`).
    pub runs_stopped: u64,
    /// Runs sent on to their next step (`continue`).
    pub runs_resumed: u64,
    /// Proposals closed whose run could no longer be reached (deleted, or already moved on). The
    /// tray is clean either way; this is the count that must never be silent.
    pub stranded: u64,
}

impl ExpirySweepReport {
    /// Nothing was overdue — the common case, and the one the caller must not log.
    pub fn is_empty(&self) -> bool {
        self.expired == 0
    }

    /// Fold one pass into the running total. Public for the same reason [`crate::retention::PruneReport::merge`]
    /// is: the driver owns the passes, because it re-takes the runtime lock between them.
    pub fn merge(&mut self, other: ExpirySweepReport) {
        self.expired += other.expired;
        self.runs_stopped += other.runs_stopped;
        self.runs_resumed += other.runs_resumed;
        self.stranded += other.stranded;
    }
}

/// **The barrier that was missing** (hub#972): closes every proposal whose deadline has passed and
/// says which runs are now waiting for nobody.
///
/// Before this, `expires_at` was consulted *only* on the way in ([`claim_pending`]). A row past its
/// TTL could therefore be neither approved nor rejected — both go through that door — so there was
/// no action left for a person to take, and its run stayed in `waiting_approval` for ever. That
/// status is exempt from the 90-day prune on purpose (a real approval waits for days), which meant
/// the `payload`, stored verbatim and quite capable of holding a customer's name and phone,
/// outlived every retention rule the hub has.
///
/// Three properties, and each one is load-bearing:
///
/// - **`UPDATE … WHERE status = 'pending'`**, inside a single data-modifying statement. Two sweeps
///   racing (or a sweep racing a person pressing *approve*) end with one winner, and the decision
///   a HUMAN took is never overwritten by a clock.
/// - **Bounded** by `limit`, like the prune: this runs against a live till.
/// - **`expires_at IS NOT NULL`** — no deadline means no TTL, not «expired at the epoch».
///
/// `now` is passed in rather than read here so the caller owns the clock, the same contract as
/// [`crate::retention::prune_once`]'s `cutoff`.
pub async fn sweep_expired(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    now: &str,
    limit: i64,
) -> Result<Vec<ExpiredApproval>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("now".into(), json!(now));
    p.insert("lim".into(), json!(limit.clamp(1, 1000)));
    p.insert("status".into(), json!(STATUS_EXPIRED));
    p.insert("by".into(), json!(DECIDED_BY_EXPIRY));
    let res = db
        .query(
            "WITH overdue AS (\
               SELECT id FROM _flow_approvals \
                WHERE hub_id = :hub_id AND status = 'pending' AND deleted_at IS NULL \
                  AND expires_at IS NOT NULL AND expires_at < :now \
                ORDER BY expires_at LIMIT :lim\
             ), swept AS (\
               UPDATE _flow_approvals \
                  SET status = :status, decided_by = :by, decided_at = :now, updated_at = :now \
                WHERE id IN (SELECT id FROM overdue) AND status = 'pending' \
                RETURNING id, run_id, flow_id, step_id, kind, command, title, expires_at, on_expire\
             ) SELECT id, run_id, flow_id, step_id, kind, command, title, expires_at, on_expire \
               FROM swept",
            &p,
        )
        .await?;
    Ok(res
        .rows
        .iter()
        .map(|r| {
            let text = |k: &str| r[k].as_str().unwrap_or_default().to_string();
            ExpiredApproval {
                id: text("id"),
                run_id: text("run_id"),
                flow_id: text("flow_id"),
                step_id: text("step_id"),
                kind: kind_of(&text("kind")),
                command: text("command"),
                title: text("title"),
                expires_at: text("expires_at"),
                on_expire: ExpiryPolicy::parse(&text("on_expire")),
            }
        })
        .collect())
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
    mark_decided_with_comment(db, hub_id, id, status, decided_by, error, "").await
}

/// …and what the person typed while deciding (hub#950). Stored on the row rather than logged: it
/// is half of the audit («approved, but only because the supplier called») and it is one of the
/// four fields the step leaves for the steps written after it.
#[allow(clippy::too_many_arguments)] // one decision's worth of context
pub async fn mark_decided_with_comment(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    id: &str,
    status: &str,
    decided_by: &str,
    error: &str,
    comment: &str,
) -> Result<Approval> {
    let now = now_rfc3339();
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("status".into(), json!(status));
    p.insert("by".into(), json!(decided_by));
    p.insert("error".into(), json!(error));
    p.insert("comment".into(), json!(comment));
    p.insert("now".into(), json!(now));
    db.execute(
        "UPDATE _flow_approvals \
         SET status = :status, decided_by = :by, decided_at = :now, error = :error, \
             comment = :comment, updated_at = :now \
         WHERE id = :id AND hub_id = :hub_id AND status = 'pending' AND deleted_at IS NULL",
        &p,
    )
    .await?;
    get(db, hub_id, id).await
}

/// A row written before the `kind` column existed is a model's proposal — that is what the table
/// held — and so is anything unrecognised. Guessing `decision` for an unknown value would turn a
/// stored `payload` into a question that executes nothing, silently dropping the write somebody
/// approved.
fn kind_of(raw: &str) -> String {
    match raw {
        KIND_DECISION => KIND_DECISION,
        _ => KIND_COMMAND,
    }
    .to_string()
}

fn row(r: &Json) -> Approval {
    let text = |k: &str| r[k].as_str().unwrap_or_default().to_string();
    let opt = |k: &str| r[k].as_str().map(|s| s.to_string());
    Approval {
        id: text("id"),
        run_id: text("run_id"),
        flow_id: text("flow_id"),
        step_id: text("step_id"),
        kind: kind_of(&text("kind")),
        command: text("command"),
        payload: serde_json::from_str(&text("payload")).unwrap_or(json!({})),
        reason: text("reason"),
        title: text("title"),
        summary: text("summary"),
        assignee_role: text("assignee_role"),
        comment: text("comment"),
        status: text("status"),
        decided_by: text("decided_by"),
        decided_at: opt("decided_at"),
        expires_at: opt("expires_at"),
        // Normalised through the two policies, so what the tray reads is what the hub will DO —
        // an unrecognised value shows as `reject`/`cancel` because that is how it will be obeyed.
        on_expire: ExpiryPolicy::parse(&text("on_expire")).as_str().to_string(),
        on_reject: RejectPolicy::parse(&text("on_reject")).as_str().to_string(),
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

    /// Ages a proposal's deadline, the way three days of silence would.
    async fn age(db: &impl DatabaseAdapter, id: &str, when: &str) {
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        p.insert("when".into(), json!(when));
        db.execute(
            "UPDATE _flow_approvals SET expires_at = :when WHERE id = :id",
            &p,
        )
        .await
        .unwrap();
    }

    const LONG_AGO: &str = "2020-01-01T00:00:00+00:00";

    /// The sweep decides the row, and what it hands back is what the caller needs to end the run:
    /// nothing about a run is decided in here, because this file has no executor.
    #[tokio::test]
    async fn the_sweep_expires_a_proposal_past_its_deadline_and_says_which_run_it_was() {
        let db = db().await;
        let created = create(&db, HUB, &proposal("agenda.booking.create"))
            .await
            .unwrap();
        age(&db, &created.id, LONG_AGO).await;

        let swept = sweep_expired(&db, HUB, &now_rfc3339(), 100).await.unwrap();

        assert_eq!(swept.len(), 1);
        assert_eq!(swept[0].id, created.id);
        assert_eq!(swept[0].run_id, "run-1");
        assert_eq!(swept[0].step_id, "agent");
        assert_eq!(
            swept[0].on_expire,
            ExpiryPolicy::Reject,
            "no document said otherwise, and the conservative answer is the default"
        );
        let after = get(&db, HUB, &created.id).await.unwrap();
        assert_eq!(after.status, STATUS_EXPIRED);
        assert_eq!(after.decided_by, DECIDED_BY_EXPIRY);
        assert!(after.decided_at.is_some());
    }

    /// Twice an hour for the life of the hub: the second pass has to find nothing.
    #[tokio::test]
    async fn the_sweep_is_idempotent_and_never_re_decides_a_decided_row() {
        let db = db().await;
        let expired = create(&db, HUB, &proposal("agenda.booking.create"))
            .await
            .unwrap();
        age(&db, &expired.id, LONG_AGO).await;
        // A row a PERSON already answered, aged past its deadline as well: a sweep that looked at
        // the clock alone would overwrite her decision with `expired`.
        let decided = create(&db, HUB, &proposal("agenda.booking.cancel"))
            .await
            .unwrap();
        mark_decided(&db, HUB, &decided.id, STATUS_APPROVED, "hub_user:1", "")
            .await
            .unwrap();
        age(&db, &decided.id, LONG_AGO).await;

        let first = sweep_expired(&db, HUB, &now_rfc3339(), 100).await.unwrap();
        let second = sweep_expired(&db, HUB, &now_rfc3339(), 100).await.unwrap();

        assert_eq!(first.len(), 1, "only the undecided one");
        assert!(second.is_empty(), "nothing left: {second:?}");
        let untouched = get(&db, HUB, &decided.id).await.unwrap();
        assert_eq!(untouched.status, STATUS_APPROVED);
        assert_eq!(untouched.decided_by, "hub_user:1");
    }

    /// One database can hold rows for more than one `hub_id` (the row contract, not the deploy).
    /// The neighbour here is ALIVE and equally overdue — a scoping test whose other tenant has
    /// nothing to lose proves nothing.
    #[tokio::test]
    async fn the_sweep_only_touches_the_hub_it_was_asked_for() {
        let db = db().await;
        test_support::ensure_schema(&db, "hub-next-door").await;
        let mine = create(&db, HUB, &proposal("agenda.booking.create"))
            .await
            .unwrap();
        let theirs = create(&db, "hub-next-door", &proposal("agenda.booking.create"))
            .await
            .unwrap();
        age(&db, &mine.id, LONG_AGO).await;
        age(&db, &theirs.id, LONG_AGO).await;

        let swept = sweep_expired(&db, HUB, &now_rfc3339(), 100).await.unwrap();

        assert_eq!(swept.len(), 1);
        assert_eq!(swept[0].id, mine.id);
        assert_eq!(
            get(&db, "hub-next-door", &theirs.id).await.unwrap().status,
            STATUS_PENDING,
            "the tenant is never negotiable, not even for a cleanup"
        );
    }

    /// A pass is BOUNDED, for the same reason the prune's is: this runs on a live till, and a hub
    /// that has been ignoring its tray for a year must not take the table with it in one statement.
    #[tokio::test]
    async fn a_pass_is_bounded_and_the_rest_waits_for_the_next_one() {
        let db = db().await;
        for _ in 0..5 {
            let a = create(&db, HUB, &proposal("agenda.booking.create"))
                .await
                .unwrap();
            age(&db, &a.id, LONG_AGO).await;
        }

        let first = sweep_expired(&db, HUB, &now_rfc3339(), 2).await.unwrap();
        let rest = sweep_expired(&db, HUB, &now_rfc3339(), 100).await.unwrap();

        assert_eq!(first.len(), 2, "one pass never exceeds the limit");
        assert_eq!(rest.len(), 3);
        assert_eq!(
            list(&db, HUB, Some(STATUS_PENDING), 50).await.unwrap().len(),
            0
        );
    }

    /// The policy travels in the ROW, so the generic `approval` step of hub#950 can set it per
    /// document without this sweep growing a second branch. Anything unrecognised falls back to
    /// the conservative answer rather than being obeyed literally.
    #[tokio::test]
    async fn the_expiry_policy_is_read_from_the_row_and_degrades_to_reject() {
        let db = db().await;
        for policy in [ON_EXPIRE_CONTINUE, ON_EXPIRE_CANCEL, "nonsense-from-v2"] {
            let a = create(&db, HUB, &proposal("agenda.booking.create"))
                .await
                .unwrap();
            let mut p = Params::new();
            p.insert("id".into(), json!(a.id));
            p.insert("policy".into(), json!(policy));
            p.insert("when".into(), json!(LONG_AGO));
            db.execute(
                "UPDATE _flow_approvals SET on_expire = :policy, expires_at = :when \
                 WHERE id = :id",
                &p,
            )
            .await
            .unwrap();

            let swept = sweep_expired(&db, HUB, &now_rfc3339(), 100).await.unwrap();

            assert_eq!(swept.len(), 1, "policy `{policy}`");
            assert_eq!(
                swept[0].on_expire,
                match policy {
                    ON_EXPIRE_CONTINUE => ExpiryPolicy::Continue,
                    ON_EXPIRE_CANCEL => ExpiryPolicy::Cancel,
                    _ => ExpiryPolicy::Reject,
                },
                "policy `{policy}`"
            );
        }
    }

    /// A row without a deadline is not overdue: `expires_at IS NULL` means «no TTL», and reading it
    /// as «expired at the epoch» would sweep away every proposal written before the column existed.
    #[tokio::test]
    async fn a_proposal_without_a_deadline_is_never_swept() {
        let db = db().await;
        let created = create(&db, HUB, &proposal("agenda.booking.create"))
            .await
            .unwrap();
        let mut p = Params::new();
        p.insert("id".into(), json!(created.id));
        db.execute(
            "UPDATE _flow_approvals SET expires_at = NULL WHERE id = :id",
            &p,
        )
        .await
        .unwrap();

        assert!(sweep_expired(&db, HUB, &now_rfc3339(), 100)
            .await
            .unwrap()
            .is_empty());
        assert_eq!(
            get(&db, HUB, &created.id).await.unwrap().status,
            STATUS_PENDING
        );
    }

    /// The refusal keeps its NAME after the sweep. `already_decided` would name a decider that
    /// does not exist, and the tray shows a different message for each code.
    #[tokio::test]
    async fn a_swept_proposal_is_refused_as_expired_not_as_already_decided() {
        let db = db().await;
        let created = create(&db, HUB, &proposal("agenda.booking.create"))
            .await
            .unwrap();
        age(&db, &created.id, LONG_AGO).await;
        sweep_expired(&db, HUB, &now_rfc3339(), 100).await.unwrap();

        let err = claim_pending(&db, HUB, &created.id)
            .await
            .expect_err("a swept proposal is not decidable either");
        assert_eq!(code_of(&err), ERR_APPROVAL_EXPIRED, "{err}");
    }

    // ── the generic decision (hub#950) ────────────────────────────────────────────────────────

    fn question() -> NewDecision {
        NewDecision {
            run_id: "run-1".into(),
            flow_id: "flow-1".into(),
            step_id: "approve".into(),
            title: "Aprobar compra a Frutas Paco".into(),
            summary: "Importe 812,40 €".into(),
            assignee_role: "owner".into(),
            expires_in_seconds: 3600,
            on_expire: ExpiryPolicy::Cancel,
            on_reject: RejectPolicy::Continue,
        }
    }

    /// **One table, two kinds** — the row is generalised, not forked. A decision carries the
    /// question a person reads instead of the write a model proposed, and it carries NO command:
    /// this kind executes nothing, and an empty `command` is what says so.
    #[tokio::test]
    async fn a_decision_is_the_same_row_with_a_question_instead_of_a_write() {
        let db = db().await;
        let created = create_decision(&db, HUB, &question()).await.unwrap();

        assert_eq!(created.kind, KIND_DECISION);
        assert_eq!(created.title, "Aprobar compra a Frutas Paco");
        assert_eq!(created.summary, "Importe 812,40 €");
        assert_eq!(created.assignee_role, "owner");
        assert_eq!(created.on_expire, ON_EXPIRE_CANCEL);
        assert_eq!(created.on_reject, ON_REJECT_CONTINUE);
        assert_eq!(created.status, STATUS_PENDING);
        assert_eq!(
            created.command, "",
            "a decision executes nothing; there is no command to run"
        );
        assert_eq!(created.payload, json!({}));
        assert!(created.expires_at.is_some());

        let read_back = get(&db, HUB, &created.id).await.unwrap();
        assert_eq!(read_back.title, created.title);
        assert_eq!(read_back.kind, KIND_DECISION);
    }

    /// The proposals an `ai` step writes keep saying what they always said. The column has a
    /// DEFAULT precisely so the rows already in a customer's tray do not become ambiguous.
    #[tokio::test]
    async fn a_proposal_from_a_model_is_still_of_kind_command() {
        let db = db().await;
        let created = create(&db, HUB, &proposal("agenda.booking.create"))
            .await
            .unwrap();
        assert_eq!(created.kind, KIND_COMMAND);
        assert_eq!(created.title, "", "a model's proposal has no question, it has a payload");
        assert_eq!(created.on_reject, ON_REJECT_CANCEL, "which is what it does today");
    }

    /// **The idempotency key is the run and the step** (the issue's criterion). A tick that died
    /// between writing the row and parking the run gets its lease reclaimed and re-executes the
    /// step; without this the person would find the same question twice and answering one would
    /// leave the other dangling for the sweep.
    #[tokio::test]
    async fn the_question_a_run_is_already_parked_on_is_found_instead_of_asked_twice() {
        let db = db().await;
        let first = create_decision(&db, HUB, &question()).await.unwrap();

        let found = pending_for_step(&db, HUB, "run-1", "approve").await.unwrap();
        assert_eq!(found.map(|a| a.id), Some(first.id.clone()));

        // Another step of the same run, and the same step of another run, are other questions.
        assert!(pending_for_step(&db, HUB, "run-1", "other").await.unwrap().is_none());
        assert!(pending_for_step(&db, HUB, "run-2", "approve").await.unwrap().is_none());
        // And once it is decided it is no longer pending, so a later run is free to ask again.
        mark_decided(&db, HUB, &first.id, STATUS_APPROVED, "hub_user:1", "").await.unwrap();
        assert!(pending_for_step(&db, HUB, "run-1", "approve").await.unwrap().is_none());
        // The tenant is never negotiable, not even for a lookup.
        test_support::ensure_schema(&db, "hub-next-door").await;
        assert!(pending_for_step(&db, "hub-next-door", "run-1", "approve")
            .await
            .unwrap()
            .is_none());
    }

    /// What a person typed when she decided. It is part of the audit and part of the step's
    /// output, so it is stored on the row rather than logged.
    #[tokio::test]
    async fn the_comment_of_whoever_decided_is_kept_on_the_row() {
        let db = db().await;
        let created = create_decision(&db, HUB, &question()).await.unwrap();
        let decided = mark_decided_with_comment(
            &db,
            HUB,
            &created.id,
            STATUS_REJECTED,
            "hub_user:1",
            "",
            "el proveedor no tiene el albarán",
        )
        .await
        .unwrap();

        assert_eq!(decided.comment, "el proveedor no tiene el albarán");
        assert_eq!(decided.status, STATUS_REJECTED);
        assert_eq!(decided.decided_by, "hub_user:1");
        assert_eq!(
            get(&db, HUB, &created.id).await.unwrap().comment,
            "el proveedor no tiene el albarán"
        );
    }

    /// The sweep has to say WHICH kind it closed: a decision resumes (or ends) its run with a
    /// decision-shaped output, and a model's proposal with the shape the `ai` step leaves. One
    /// sweep, two shapes, and the row is what tells them apart.
    #[tokio::test]
    async fn the_sweep_reports_the_kind_it_closed() {
        let db = db().await;
        let decision = create_decision(&db, HUB, &question()).await.unwrap();
        age(&db, &decision.id, LONG_AGO).await;

        let swept = sweep_expired(&db, HUB, &now_rfc3339(), 100).await.unwrap();

        assert_eq!(swept.len(), 1);
        assert_eq!(swept[0].kind, KIND_DECISION);
        assert_eq!(swept[0].on_expire, ExpiryPolicy::Cancel, "read from the row");
        assert_eq!(swept[0].step_id, "approve");
        assert_eq!(
            swept[0].title, "Aprobar compra a Frutas Paco",
            "the question comes back with the sweep: what the run is cancelled FOR has to be \
             sayable without a second query"
        );
    }

    /// Same rule as [`ExpiryPolicy`], same reason: a row written by a newer version — or by hand —
    /// must not be able to talk this hub into carrying a run past a refusal.
    #[test]
    fn an_unrecognised_reject_policy_degrades_to_ending_the_run() {
        assert_eq!(RejectPolicy::parse(ON_REJECT_CONTINUE), RejectPolicy::Continue);
        assert_eq!(RejectPolicy::parse(ON_REJECT_CANCEL), RejectPolicy::Cancel);
        for nonsense in ["", "reject", "nonsense-from-v2", "CONTINUE"] {
            assert_eq!(
                RejectPolicy::parse(nonsense),
                RejectPolicy::Cancel,
                "`{nonsense}`"
            );
        }
    }

    /// The deadline comes from the DOCUMENT, not from the constant: 72 h is what an `ai` proposal
    /// gets, and what an `approval` step gets when its author did not say otherwise.
    #[tokio::test]
    async fn the_deadline_of_a_decision_is_the_one_its_document_asked_for() {
        let db = db().await;
        let mut short = question();
        short.expires_in_seconds = 60;
        let created = create_decision(&db, HUB, &short).await.unwrap();

        let expires_at = created.expires_at.expect("a decision is never open-ended");
        let deadline = chrono::DateTime::parse_from_rfc3339(&expires_at).unwrap();
        let seconds = (deadline.timestamp() - chrono::Utc::now().timestamp()).abs();
        assert!(
            (0..=120).contains(&seconds),
            "60 s from now, not {DEFAULT_TTL_HOURS} h: {expires_at}"
        );
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
