//! **Draining** the print queue — who is allowed to take a ticket out, and what happens when they
//! do not come back (ADR-0196 §6, hub#343).
//!
//! [`crate::print_queue`] (hub#341) put the queue in the hub and [`crate::print_hosts`] (hub#342)
//! recorded which device drains which role. Neither of them decides **who may pull**: `claim_next`
//! takes a `claimed_by` string and believes it. This module is that decision, and it is not
//! bookkeeping — the queue carries the **document**: names, lines, totals, the fiscal QR. A logged-in
//! phone in the dining room must not be able to siphon every ticket the business prints by asking
//! nicely.
//!
//! ## The two refusals, and why they are two
//!
//! | Code | Who gets it |
//! |------|-------------|
//! | [`ERR_HOST_NOT_REGISTERED`] | a device that hosts **nothing** here — including one registered in another hub, and one that did not say who it is |
//! | [`ERR_ROLE_NOT_HOSTED`] | a real print host reaching for **somebody else's** role |
//!
//! They are deliberately distinguishable. Collapsing them into one refusal would make either guard
//! deletable without a single test noticing, and they protect different things: the first stops a
//! stranger reading tickets, the second stops the counter till closing the kitchen's job — which
//! does not leak a ticket, it **loses** one.
//!
//! The order matters too: an unregistered caller is refused **before** the job is looked up, so the
//! confirmation door cannot be used to find out which `jobId`s exist.
//!
//! ## The three decisions this layer makes
//!
//! **The host printed the paper and died before confirming → it prints again.** See
//! [`claim`]: losing a ticket is worse than duplicating one, and the duplicate is bounded by
//! `MAX_ATTEMPTS` and visible in `attempts`.
//!
//! **A claimed ticket is held for 90 seconds, no longer and no shorter.** Pinned from both ends
//! against `print_hosts::HOST_TTL_SECONDS`, because a queue that took a job back from a host the hub
//! still calls live would duplicate for nothing, and a hung till must not sit on a customer's ticket
//! for minutes with the spare till beside it forbidden to help.
//!
//! **The expired lease is reclaimed when somebody asks for work, not by a background sweeper.**
//! Same reasoning `print_hosts` uses to derive liveness rather than store it: a sweeper is one more
//! thing that can be down, and while it is down a ticket sits stranded in `printing` with nobody
//! the wiser. A lazy reclaim is right even when nothing has run.
use erplora_db::DatabaseAdapter;

use crate::errors::{Result, RuntimeError};
use crate::print_hosts;
use crate::print_queue::{self, PrintJob};

/// The caller is not a print host of this hub at all.
pub const ERR_HOST_NOT_REGISTERED: &str = "print.host_not_registered";

/// The caller is a print host, but not of the role it is reaching for.
pub const ERR_ROLE_NOT_HOSTED: &str = "print.role_not_hosted";

fn denied(code: &str, message: impl Into<String>) -> RuntimeError {
    RuntimeError::Domain {
        code: code.to_string(),
        message: message.into(),
    }
}

/// Resolves the roles `device_id` hosts here and refuses a device that hosts none.
///
/// Returned rather than checked in place because both doors need the list: [`claim`] to check the
/// role it was asked for, [`confirm`] to check the role of the job it was given.
async fn require_registered_host(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    device_id: &str,
) -> Result<Vec<String>> {
    let roles = hosted_roles(db, hub_id, device_id).await?;
    if roles.is_empty() {
        return Err(denied(
            ERR_HOST_NOT_REGISTERED,
            "this device is not a print host of this hub: register it before draining",
        ));
    }
    Ok(roles)
}

/// Refuses a real print host that is reaching for a role it does not hold.
fn require_role(roles: &[String], role: &str) -> Result<()> {
    if roles.iter().any(|r| r == role) {
        return Ok(());
    }
    Err(denied(
        ERR_ROLE_NOT_HOSTED,
        format!("this device does not print `{role}` for this hub"),
    ))
}

/// Hands the next job of `role` to `device_id`, leasing it for
/// [`print_queue::DEFAULT_LEASE_SECONDS`].
///
/// Three things happen before the hand-out, in this order:
///
/// 1. **The caller is checked against the registry.** `claim_next` believes whatever `claimed_by`
///    it is given; here is where "who are you" stops being a label and becomes a permission.
/// 2. **Expired leases are reclaimed.** Lazily, at the moment somebody asks for work — nothing
///    sweeps in the background, on purpose.
/// 3. **The device's liveness is refreshed.** A device that is taking tickets out is demonstrably
///    there; without this a till that drains flat out could still be reported as "nothing is
///    printing" because its beat timer starved.
///
/// **A job whose host died after printing comes back and is printed again.** That is the choice,
/// not an oversight: the alternative is dropping a job the moment its holder goes quiet, which
/// trades a second piece of paper for a customer with no receipt and a kitchen with no order. The
/// duplicate is bounded — every hand-out burns an attempt and `MAX_ATTEMPTS` of them dead-letter
/// the job — and observable, because `attempts` is in the listing.
pub async fn claim(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    device_id: &str,
    role: &str,
) -> Result<Option<PrintJob>> {
    let device_id = device_id.trim();
    let roles = require_registered_host(db, hub_id, device_id).await?;
    // The station is resolved BEFORE the registry check so the two refusals stay distinct: a role
    // that names no station of this hub is a bad payload (422, naming the real ones), while a real
    // station this device does not host is [`ERR_ROLE_NOT_HOSTED`] (hub#457).
    let station = crate::print_stations::resolve(db, hub_id, role).await?;
    require_role(&roles, &station.key)?;
    print_queue::reclaim_expired(db, hub_id).await?;
    print_hosts::heartbeat(db, hub_id, device_id).await?;
    print_queue::claim_next(
        db,
        hub_id,
        &station.id,
        device_id,
        print_queue::DEFAULT_LEASE_SECONDS,
    )
    .await
}

/// The host confirms the paper came out of the printer. `false` = this hub has no such job, or it
/// was already terminal.
///
/// Scoped to the roles the device hosts: a `receipt` host that could confirm the kitchen's job
/// would mark it done with nothing ever coming out of the kitchen printer. Within a role it stays
/// lenient — a host whose lease expired may still confirm, because the paper did come out and what
/// we are avoiding is a second one (hub#341).
pub async fn confirm(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    device_id: &str,
    job_id: &str,
) -> Result<bool> {
    let job_id = job_id.trim();
    let roles = require_registered_host(db, hub_id, device_id.trim()).await?;
    let Some(role) = print_queue::role_of(db, hub_id, job_id).await? else {
        // Not a refusal: an unknown id here is a host confirming a ticket this hub no longer has
        // (dead-lettered, wiped, or another hub's). A plain "no" is the honest answer.
        return Ok(false);
    };
    require_role(&roles, &role)?;
    print_queue::mark_done(db, hub_id, job_id).await
}

/// The host could not print it (no paper, printer off, socket refused). `true` = back in the queue
/// for another host, `false` = out of hand-outs and dead-lettered.
///
/// Same role scope as [`confirm`], and for a sharper reason: failing somebody else's job burns one
/// of its hand-outs, and `MAX_ATTEMPTS` of those dead-letter a ticket nobody ever tried to print.
pub async fn report_failure(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    device_id: &str,
    job_id: &str,
    error: &str,
) -> Result<bool> {
    let job_id = job_id.trim();
    let roles = require_registered_host(db, hub_id, device_id.trim()).await?;
    let Some(role) = print_queue::role_of(db, hub_id, job_id).await? else {
        return Ok(false);
    };
    require_role(&roles, &role)?;
    print_queue::mark_failed(db, hub_id, job_id, error).await
}

/// Roles `device_id` hosts in this hub — what the hub answers when a host asks "what am I for?",
/// so the client never has to guess (same shape as publishing `heartbeatSeconds` in hub#342).
///
/// A caller that names no device hosts nothing. It must never match a row by matching an empty id,
/// which is the same hole [`print_hosts`] closes on its own doors.
pub async fn hosted_roles(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    device_id: &str,
) -> Result<Vec<String>> {
    let device_id = device_id.trim();
    if device_id.is_empty() {
        return Ok(Vec::new());
    }
    Ok(print_hosts::list(db, hub_id)
        .await?
        .into_iter()
        .filter(|h| h.device_id == device_id)
        .map(|h| h.role)
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::testutil::TestDb;
    use erplora_db::{Params, PgAdapter};
    use serde_json::json;

    /// A hub whose system schema is in place (queue = v18, host registry = v22).
    async fn drain_db() -> PgAdapter {
        let db = TestDb::new().await.adapter().await;
        crate::installer::ensure_hub_module_table(&db)
            .await
            .unwrap();
        crate::identity::ensure_tables(&db).await.unwrap();
        crate::system_migrations::apply(&db, "h1").await.unwrap();
        db
    }

    async fn queue(db: &PgAdapter, hub_id: &str, job_id: &str, role: &str) {
        print_queue::enqueue(
            db,
            hub_id,
            &print_queue::NewPrintJob {
                job_id: job_id.into(),
                role: role.into(),
                document_type: "receipt".into(),
                document: serde_json::json!({ "receipt_id": job_id }),
                format: print_queue::FORMAT_RECEIPT.into(),
            },
        )
        .await
        .unwrap();
    }

    async fn host(db: &PgAdapter, hub_id: &str, device_id: &str, role: &str) {
        print_hosts::register(db, hub_id, device_id, role, "Till", "u1")
            .await
            .unwrap();
    }

    /// Back-dates a job's lease into the past: the only way to say "the host took it and never
    /// came back" without waiting 90 seconds in a test.
    async fn expire_lease(db: &PgAdapter, job_id: &str) {
        let past = (chrono::Utc::now() - chrono::Duration::seconds(1)).to_rfc3339();
        let mut p = Params::new();
        p.insert("at".into(), json!(past));
        p.insert("job_id".into(), json!(job_id));
        db.execute(
            "UPDATE _print_queue SET lease_expires_at = :at WHERE job_id = :job_id",
            &p,
        )
        .await
        .unwrap();
    }

    async fn status_of(db: &PgAdapter, hub_id: &str, job_id: &str) -> String {
        print_queue::list(db, hub_id, None, None, 500)
            .await
            .unwrap()
            .into_iter()
            .find(|j| j.job_id == job_id)
            .map(|j| j.status)
            .unwrap_or_default()
    }

    fn code_of(e: &RuntimeError) -> String {
        match e {
            RuntimeError::Domain { code, .. } => code.clone(),
            other => panic!("expected a domain refusal, got {other:?}"),
        }
    }

    // ── The evasion guards ────────────────────────────────────────────────────────────────────

    /// **A device that is not a print host drains nothing.** The queue carries the document, so
    /// this is not bookkeeping: without it, any session on any phone could pull every ticket the
    /// business prints — names, lines, totals — one `claim` at a time.
    #[tokio::test]
    async fn a_device_that_is_not_a_registered_host_cannot_claim() {
        let db = drain_db().await;
        queue(&db, "h1", "j1", "receipt").await;

        let e = claim(&db, "h1", "phone-9", "receipt")
            .await
            .expect_err("an unregistered device must not be handed a ticket");
        assert_eq!(code_of(&e), ERR_HOST_NOT_REGISTERED);
        assert_eq!(
            status_of(&db, "h1", "j1").await,
            print_queue::STATUS_PENDING,
            "the refused claim did not even burn an attempt"
        );
    }

    /// **A host of one role does not reach into another's.** `claim_next` already filters by role,
    /// but only because the caller asked nicely for its own: nothing stopped the bar's till from
    /// asking for `kitchen` and reading the kitchen's tickets.
    #[tokio::test]
    async fn a_host_cannot_claim_a_role_it_does_not_host() {
        let db = drain_db().await;
        host(&db, "h1", "till-bar", "bar").await;
        queue(&db, "h1", "j1", "kitchen").await;

        let e = claim(&db, "h1", "till-bar", "kitchen")
            .await
            .expect_err("the bar's till must not drain the kitchen");
        assert_eq!(
            code_of(&e),
            ERR_ROLE_NOT_HOSTED,
            "a registered device reaching for someone else's role is a DIFFERENT refusal from an \
             unregistered one — if both said the same thing, one of the two guards could be \
             deleted and nobody would notice"
        );
        assert_eq!(
            status_of(&db, "h1", "j1").await,
            print_queue::STATUS_PENDING
        );
    }

    /// The mirror on the confirmation door, and this one **loses paper**: a `receipt` host that
    /// could confirm the kitchen's job would mark it done without anything ever coming out of the
    /// kitchen printer. That is the "lost ticket" the whole design refuses.
    #[tokio::test]
    async fn a_host_cannot_confirm_a_job_of_a_role_it_does_not_host() {
        let db = drain_db().await;
        host(&db, "h1", "till-1", "receipt").await;
        host(&db, "h1", "till-k", "kitchen").await;
        queue(&db, "h1", "j1", "kitchen").await;
        claim(&db, "h1", "till-k", "kitchen")
            .await
            .unwrap()
            .unwrap();

        let e = confirm(&db, "h1", "till-1", "j1")
            .await
            .expect_err("the counter must not close the kitchen's job");
        assert_eq!(code_of(&e), ERR_ROLE_NOT_HOSTED);
        assert_eq!(
            status_of(&db, "h1", "j1").await,
            print_queue::STATUS_PRINTING,
            "the kitchen's ticket is still on its way out"
        );
    }

    /// Same door, same reasoning, for the failure report: marking somebody else's job failed burns
    /// one of its hand-outs and, five times over, dead-letters a ticket that was never even tried.
    #[tokio::test]
    async fn a_host_cannot_fail_a_job_of_a_role_it_does_not_host() {
        let db = drain_db().await;
        host(&db, "h1", "till-1", "receipt").await;
        host(&db, "h1", "till-k", "kitchen").await;
        queue(&db, "h1", "j1", "kitchen").await;
        claim(&db, "h1", "till-k", "kitchen")
            .await
            .unwrap()
            .unwrap();

        let e = report_failure(&db, "h1", "till-1", "j1", "no paper")
            .await
            .expect_err("the counter must not fail the kitchen's job");
        assert_eq!(code_of(&e), ERR_ROLE_NOT_HOSTED);
        assert_eq!(
            status_of(&db, "h1", "j1").await,
            print_queue::STATUS_PRINTING
        );
    }

    /// An unregistered device cannot confirm either — and it is refused **before** the job is even
    /// looked up, so it cannot use the confirmation door to find out which job ids exist.
    #[tokio::test]
    async fn a_device_that_is_not_a_registered_host_cannot_confirm_or_fail() {
        let db = drain_db().await;
        host(&db, "h1", "till-1", "receipt").await;
        queue(&db, "h1", "j1", "receipt").await;
        claim(&db, "h1", "till-1", "receipt")
            .await
            .unwrap()
            .unwrap();

        for job_id in ["j1", "a-job-that-does-not-exist"] {
            let e = confirm(&db, "h1", "phone-9", job_id).await.expect_err(
                "an unregistered device is refused on the id it invents as well as on the real one",
            );
            assert_eq!(code_of(&e), ERR_HOST_NOT_REGISTERED);
        }
        assert_eq!(
            status_of(&db, "h1", "j1").await,
            print_queue::STATUS_PRINTING
        );

        let e = report_failure(&db, "h1", "phone-9", "j1", "x")
            .await
            .unwrap_err();
        assert_eq!(code_of(&e), ERR_HOST_NOT_REGISTERED);
    }

    /// A caller that does not say which device it is hosts nothing, so it is an unregistered one.
    /// It must never match a row by matching an empty id — the same hole `print_hosts` closed on
    /// its own doors.
    #[tokio::test]
    async fn a_nameless_caller_drains_nothing() {
        let db = drain_db().await;
        host(&db, "h1", "till-1", "receipt").await;
        queue(&db, "h1", "j1", "receipt").await;

        for nameless in ["", "   "] {
            assert_eq!(
                code_of(&claim(&db, "h1", nameless, "receipt").await.unwrap_err()),
                ERR_HOST_NOT_REGISTERED
            );
            assert_eq!(
                code_of(&confirm(&db, "h1", nameless, "j1").await.unwrap_err()),
                ERR_HOST_NOT_REGISTERED
            );
        }
        assert_eq!(
            status_of(&db, "h1", "j1").await,
            print_queue::STATUS_PENDING
        );
    }

    /// **The neighbouring hub is alive, with a host and a ticket of its own, throughout.**
    ///
    /// A device registered in `h2` is not a print host of `h1`, so `h1` refuses it — and refuses it
    /// as an *unregistered* device, because from `h1`'s side that is exactly what it is. What the
    /// test has to prove is the other half: that the refusal did not reach across. `h2`'s job is
    /// still waiting, its host is still registered, and `h2` can still drain it afterwards.
    ///
    /// The neighbour's job is deliberately a **`kitchen`** one while `h1`'s host only prints
    /// `receipt`: that is what makes the hub scope of the job lookup load-bearing. Reaching across
    /// hubs would find a role, and finding a role changes the answer from "no such ticket here"
    /// into "not your role" — two different sentences, only one of them true.
    #[tokio::test]
    async fn a_host_of_another_hub_can_neither_drain_nor_confirm_this_ones_queue() {
        let db = drain_db().await;
        crate::system_migrations::apply(&db, "h2").await.unwrap();

        host(&db, "h1", "till-1", "receipt").await;
        queue(&db, "h1", "j-h1", "receipt").await;
        // The neighbour, alive and with work of its own for the whole of this test.
        host(&db, "h2", "till-2", "kitchen").await;
        queue(&db, "h2", "j-h2", "kitchen").await;

        // h2's device reaching into h1.
        assert_eq!(
            code_of(&claim(&db, "h1", "till-2", "kitchen").await.unwrap_err()),
            ERR_HOST_NOT_REGISTERED
        );
        // h1's device reaching for h2's job by id — on both closing doors.
        assert!(
            !confirm(&db, "h1", "till-1", "j-h2").await.unwrap(),
            "another hub's job is not a job this hub can confirm"
        );
        assert!(
            !report_failure(&db, "h1", "till-1", "j-h2", "x")
                .await
                .unwrap(),
            "nor one it can fail"
        );

        assert_eq!(
            status_of(&db, "h2", "j-h2").await,
            print_queue::STATUS_PENDING,
            "the neighbour's ticket was not touched"
        );
        assert_eq!(
            print_hosts::list(&db, "h2").await.unwrap().len(),
            1,
            "the neighbour's host is still registered"
        );
        let neighbour = claim(&db, "h2", "till-2", "kitchen")
            .await
            .unwrap()
            .expect("the neighbour can still drain its own queue");
        assert_eq!(neighbour.job_id, "j-h2");
        assert_eq!(neighbour.attempts, 1, "and it is its FIRST hand-out");

        // And h1's own queue is exactly where it was: nothing crossed in either direction.
        assert_eq!(
            status_of(&db, "h1", "j-h1").await,
            print_queue::STATUS_PENDING
        );
    }

    // ── What the drain actually does ──────────────────────────────────────────────────────────

    /// The happy path end to end at this layer: a registered host takes its role's ticket, with the
    /// document, and confirms it. Confirmed is terminal — nobody is handed it again.
    #[tokio::test]
    async fn a_registered_host_drains_and_confirms_its_own_role() {
        let db = drain_db().await;
        host(&db, "h1", "till-1", "receipt").await;
        queue(&db, "h1", "j1", "receipt").await;

        let job = claim(&db, "h1", "till-1", "receipt")
            .await
            .unwrap()
            .expect("the registered host is handed the ticket");
        assert_eq!(job.job_id, "j1");
        assert_eq!(
            job.document,
            serde_json::json!({ "receipt_id": "j1" }),
            "the structured document travels to the host"
        );

        assert!(confirm(&db, "h1", "till-1", "j1").await.unwrap());
        assert_eq!(status_of(&db, "h1", "j1").await, print_queue::STATUS_DONE);
        assert!(
            claim(&db, "h1", "till-1", "receipt")
                .await
                .unwrap()
                .is_none(),
            "a confirmed ticket is never handed out again"
        );
    }

    /// An empty queue is not an error: it is the answer "nothing for you right now".
    #[tokio::test]
    async fn a_registered_host_with_an_empty_queue_is_told_so_rather_than_refused() {
        let db = drain_db().await;
        host(&db, "h1", "till-1", "receipt").await;

        assert!(claim(&db, "h1", "till-1", "receipt")
            .await
            .unwrap()
            .is_none());
    }

    /// **The question this piece exists to answer: the host printed the paper and died before
    /// confirming.**
    ///
    /// The lease expires, the job goes back to the queue and the next host prints it **again**. We
    /// choose the duplicate on purpose. The alternative — treating a hand-out as delivery and
    /// dropping the job when the host goes quiet — trades a second piece of paper for a customer
    /// who leaves with no receipt at all, and a kitchen that never got the order. A duplicate is
    /// visible, cheap and fixable by a human; a ticket that never existed is neither.
    ///
    /// What keeps the choice honest is that it is **bounded and observable**: every reprint burns a
    /// hand-out (`attempts`), five of them dead-letter the job, and the count is in the listing, so
    /// a till that keeps dying mid-print shows up as a ticket on its fifth attempt rather than as a
    /// printer quietly spooling forever.
    #[tokio::test]
    async fn a_host_that_printed_and_died_before_confirming_reprints_rather_than_losing_the_ticket()
    {
        let db = drain_db().await;
        host(&db, "h1", "till-1", "receipt").await;
        host(&db, "h1", "till-2", "receipt").await;
        queue(&db, "h1", "j1", "receipt").await;

        // till-1 takes it, prints the paper, and dies with the confirmation still in its hand.
        let first = claim(&db, "h1", "till-1", "receipt")
            .await
            .unwrap()
            .unwrap();
        assert_eq!(first.attempts, 1);
        expire_lease(&db, "j1").await;

        // The spare till drains next. It gets the SAME ticket, and prints it a second time.
        let second = claim(&db, "h1", "till-2", "receipt")
            .await
            .unwrap()
            .expect("late and duplicated beats lost");
        assert_eq!(second.job_id, "j1");
        assert_eq!(second.document, first.document);
        assert_eq!(
            second.attempts, 2,
            "the reprint is counted, so it cannot go round for ever"
        );
    }

    /// The bound on that choice: a job that keeps coming back is dead-lettered instead of being
    /// reprinted for ever. Five hand-outs is the cap the queue already carries.
    #[tokio::test]
    async fn reprinting_is_bounded_by_the_hand_out_cap() {
        let db = drain_db().await;
        host(&db, "h1", "till-1", "receipt").await;
        queue(&db, "h1", "j1", "receipt").await;

        for _ in 0..print_queue::MAX_ATTEMPTS {
            claim(&db, "h1", "till-1", "receipt")
                .await
                .unwrap()
                .expect("still being handed out");
            expire_lease(&db, "j1").await;
        }

        assert!(
            claim(&db, "h1", "till-1", "receipt")
                .await
                .unwrap()
                .is_none(),
            "a ticket nobody ever confirms stops being reprinted"
        );
        assert_eq!(status_of(&db, "h1", "j1").await, print_queue::STATUS_DEAD);
    }

    /// **Nothing sweeps leases in the background, and that is deliberate.** The reclaim happens
    /// when somebody asks for work, so the answer is right even when no scheduled task has run —
    /// the same reasoning `print_hosts` uses to derive liveness instead of storing it. A background
    /// sweeper is one more thing that can be down, and while it is down a ticket stays stranded in
    /// `printing` with nobody the wiser.
    #[tokio::test]
    async fn the_next_claim_reclaims_the_expired_lease_with_no_background_sweeper() {
        let db = drain_db().await;
        host(&db, "h1", "till-1", "receipt").await;
        queue(&db, "h1", "j1", "receipt").await;
        claim(&db, "h1", "till-1", "receipt")
            .await
            .unwrap()
            .unwrap();
        expire_lease(&db, "j1").await;

        // No call to `reclaim_expired`, no scheduled task: just the next host asking for work.
        let back = claim(&db, "h1", "till-1", "receipt")
            .await
            .unwrap()
            .expect("the stranded ticket comes back on the next ask");
        assert_eq!(back.job_id, "j1");
    }

    /// **A hung host holds ONE ticket, never the queue.** It keeps the job it was handed until the
    /// lease runs out — that is the price of not printing it twice while it is still trying — but
    /// everything behind it keeps moving through the spare till.
    #[tokio::test]
    async fn a_hung_host_holds_the_job_it_took_but_never_the_queue_behind_it() {
        let db = drain_db().await;
        host(&db, "h1", "till-1", "receipt").await;
        host(&db, "h1", "till-2", "receipt").await;
        queue(&db, "h1", "j1", "receipt").await;
        queue(&db, "h1", "j2", "receipt").await;

        // till-1 takes the first one and hangs, holding it.
        assert_eq!(
            claim(&db, "h1", "till-1", "receipt")
                .await
                .unwrap()
                .unwrap()
                .job_id,
            "j1"
        );

        // The spare till is not blocked: it takes the next ticket straight away.
        assert_eq!(
            claim(&db, "h1", "till-2", "receipt")
                .await
                .unwrap()
                .unwrap()
                .job_id,
            "j2",
            "one hung device must not sequester the whole queue"
        );

        // And j1 is not handed out twice while its lease still holds.
        assert!(claim(&db, "h1", "till-2", "receipt")
            .await
            .unwrap()
            .is_none());
        expire_lease(&db, "j1").await;
        assert_eq!(
            claim(&db, "h1", "till-2", "receipt")
                .await
                .unwrap()
                .unwrap()
                .job_id,
            "j1"
        );
    }

    /// **How long a host may hold a claimed ticket, pinned from both ends** — both numbers are
    /// product decisions and neither follows from the other:
    ///
    ///  - **not shorter than the liveness window**, or the queue would take a job back from a host
    ///    the hub still believes is there and print it twice for no reason at all. Requeueing has
    ///    to mean "we have stopped believing in this device", and that belief is
    ///    `print_hosts::HOST_TTL_SECONDS`;
    ///  - **not longer than three minutes**, or a till that hung with the ticket in its hand keeps
    ///    the customer waiting at the counter with nothing to hand them, and the spare till right
    ///    next to it is not allowed to help.
    #[test]
    fn a_claimed_ticket_is_held_for_at_least_the_liveness_window_and_at_most_three_minutes() {
        assert!(
            print_queue::DEFAULT_LEASE_SECONDS >= print_hosts::HOST_TTL_SECONDS,
            "taking a ticket back from a host we still call live would duplicate it for nothing"
        );
        assert!(
            print_queue::DEFAULT_LEASE_SECONDS <= 180,
            "a hung till must not sit on a customer's ticket for longer than three minutes"
        );
    }

    /// **Draining is news.** A host that is busy taking tickets out is demonstrably there, so the
    /// traffic itself refreshes its liveness. Without this, a till that drains flat out but whose
    /// beat timer starved would be reported as "nothing is printing" while the paper is coming out.
    #[tokio::test]
    async fn draining_counts_as_news_from_the_device() {
        let db = drain_db().await;
        host(&db, "h1", "till-1", "receipt").await;
        queue(&db, "h1", "j1", "receipt").await;

        // The device went quiet as far as the beat is concerned.
        let long_ago = (chrono::Utc::now()
            - chrono::Duration::seconds(print_hosts::HOST_TTL_SECONDS + 5))
        .to_rfc3339();
        let mut p = Params::new();
        p.insert("at".into(), json!(long_ago));
        db.execute("UPDATE _print_host SET last_seen_at = :at", &p)
            .await
            .unwrap();
        assert!(!print_hosts::list(&db, "h1").await.unwrap()[0].live);

        claim(&db, "h1", "till-1", "receipt")
            .await
            .unwrap()
            .unwrap();
        assert!(
            print_hosts::list(&db, "h1").await.unwrap()[0].live,
            "a device that just took a ticket out is not a device we have lost"
        );
    }

    /// One device, two roles: it drains both, and each role only sees its own work.
    #[tokio::test]
    async fn one_device_drains_every_role_it_hosts_and_no_others() {
        let db = drain_db().await;
        host(&db, "h1", "till-1", "receipt").await;
        host(&db, "h1", "till-1", "kitchen").await;
        queue(&db, "h1", "j-r", "receipt").await;
        queue(&db, "h1", "j-k", "kitchen").await;

        assert_eq!(
            claim(&db, "h1", "till-1", "receipt")
                .await
                .unwrap()
                .unwrap()
                .job_id,
            "j-r"
        );
        assert_eq!(
            claim(&db, "h1", "till-1", "kitchen")
                .await
                .unwrap()
                .unwrap()
                .job_id,
            "j-k"
        );
        assert_eq!(
            code_of(&claim(&db, "h1", "till-1", "bar").await.unwrap_err()),
            ERR_ROLE_NOT_HOSTED
        );
    }

    /// Confirming a job this hub does not have is not a refusal — it is `false`. A host that
    /// reconnects and confirms a ticket that was already dead-lettered gets a plain "no", not an
    /// error it would have to reason about.
    #[tokio::test]
    async fn confirming_a_job_this_hub_does_not_have_is_a_plain_no() {
        let db = drain_db().await;
        host(&db, "h1", "till-1", "receipt").await;

        assert!(!confirm(&db, "h1", "till-1", "never-existed").await.unwrap());
    }

    /// A failure sends the ticket back to the queue for the next host, which is the whole point of
    /// reporting it instead of going quiet: "out of paper" on this till is not "this ticket is
    /// gone".
    #[tokio::test]
    async fn a_reported_failure_puts_the_ticket_back_for_the_next_host() {
        let db = drain_db().await;
        host(&db, "h1", "till-1", "receipt").await;
        host(&db, "h1", "till-2", "receipt").await;
        queue(&db, "h1", "j1", "receipt").await;
        claim(&db, "h1", "till-1", "receipt")
            .await
            .unwrap()
            .unwrap();

        assert!(
            report_failure(&db, "h1", "till-1", "j1", "out of paper")
                .await
                .unwrap(),
            "requeued for another attempt"
        );
        assert_eq!(
            claim(&db, "h1", "till-2", "receipt")
                .await
                .unwrap()
                .unwrap()
                .job_id,
            "j1"
        );
    }

    /// The roles a device hosts are what the hub tells it at connection time, so the client never
    /// has to guess (same shape as publishing `heartbeatSeconds` in hub#342).
    #[tokio::test]
    async fn the_hub_reports_which_roles_a_device_hosts() {
        let db = drain_db().await;
        host(&db, "h1", "till-1", "receipt").await;
        host(&db, "h1", "till-1", "kitchen").await;
        host(&db, "h1", "till-2", "bar").await;

        let mut roles = hosted_roles(&db, "h1", "till-1").await.unwrap();
        roles.sort();
        assert_eq!(roles, ["kitchen", "receipt"]);
        assert!(hosted_roles(&db, "h1", "phone-9").await.unwrap().is_empty());
        assert!(hosted_roles(&db, "h1", "").await.unwrap().is_empty());
    }
}
