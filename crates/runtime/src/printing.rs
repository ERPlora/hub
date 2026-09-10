//! Print queue, stations, hosts, routes and job claiming — split out of `lib.rs` verbatim (hub#1403).

use crate::*;

/// A queued job, **and whether anything is going to come out of a printer** (hub#1731).
///
/// "The job waits — late, not lost" is true of the queue and was, on its own, the whole answer the
/// producer got. On a hub with no printer set up "late" never arrives, and a cashier who was told
/// `queued` had no way to tell that from a ticket already on paper: they charged, said "here you
/// go", and nothing came out. The queue was never wrong; it just was not the whole answer.
///
/// So the enqueue reports the other half. Facts, not a sentence — the words belong to the surface
/// that can translate them (ADR-0055).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EnqueueReport {
    /// Written, or already there under that `jobId`. Both are success.
    pub outcome: print_queue::EnqueueOutcome,
    /// The station the job landed on, resolved — never the word the producer sent.
    pub role: String,
    /// Devices live for that station at this instant. **`0` means nobody is going to take it.**
    pub live_hosts: i64,
}

impl EnqueueReport {
    /// The state worth telling the person at the till about: it is in the queue and there is
    /// nobody to drain it.
    pub fn awaiting_host(&self) -> bool {
        self.live_hosts == 0
    }
}

impl Runtime {
    /// Enqueues a document for a printer role, **idempotently by `jobId`**: repeating the same id
    /// never produces a second ticket (see [`print_queue`]). Scoped to the deployment's `hub_id`.
    /// With no print host connected the job **waits** — late, not lost — and the report says so
    /// ([`EnqueueReport::awaiting_host`]), because on a hub with no printer "late" is "never".
    ///
    /// The host count is read **after** the write and for the **resolved** station, in that order
    /// on purpose: before the write there is no station to ask about, and asking about the
    /// producer's raw word would answer for a station this hub may not have.
    pub async fn enqueue_print_job(&self, job: &print_queue::NewPrintJob) -> Result<EnqueueReport> {
        let queued = print_queue::enqueue(self.db.as_ref(), &self.hub_id, job).await?;
        let live_hosts =
            print_hosts::live_hosts_for(self.db.as_ref(), &self.hub_id, &queued.role).await?;
        Ok(EnqueueReport {
            outcome: queued.outcome,
            role: queued.role,
            live_hosts,
        })
    }

    /// The hub's print queue in hand-out order (optional role/status filters). This is the
    /// observable view: what is waiting, what is printing and what died (and why).
    pub async fn print_queue(
        &self,
        role: Option<&str>,
        status: Option<&str>,
        limit: i64,
    ) -> Result<Vec<print_queue::PrintJob>> {
        print_queue::list(self.db.as_ref(), &self.hub_id, role, status, limit).await
    }

    /// The names behind the stamps in `jobs`, for the door that is allowed to read them.
    ///
    /// Kept next to [`Runtime::print_queue`] because the HTTP listing has no database handle of its
    /// own: the shape it serves and the shape the dispatcher serves must resolve the same way, or
    /// the module's screen and the shell's would disagree about who binned a ticket.
    pub async fn print_queue_actor_names(
        &self,
        jobs: &[print_queue::PrintJob],
    ) -> Result<print_queue::ActorNames> {
        print_queue::ActorNames::of(self.db.as_ref(), &self.hub_id, jobs).await
    }

    /// **Puts a dead print job back in front of the hosts** (hub#1108), with its hand-outs reset,
    /// stamping who asked for it and — since hub#1532 — through which module.
    /// Scoped to the deployment's `hub_id`, like every other read and write here: another tenant's
    /// `jobId` is simply not a job as far as this hub is concerned.
    ///
    /// `retried_by` and `retried_by_module` are resolved by the caller at the door (the session and
    /// `X-Erplora-Module`), never taken from a request body. `retried_by_module` is `""` when the
    /// caller named no module.
    pub async fn retry_print_job(
        &self,
        job_id: &str,
        retried_by: &str,
        retried_by_module: &str,
    ) -> Result<print_queue::RequeueOutcome> {
        print_queue::requeue(
            self.db.as_ref(),
            &self.hub_id,
            job_id,
            retried_by,
            retried_by_module,
        )
        .await
    }

    /// **Retires a print job nobody is ever going to print** (hub#1108), stamping who, through which
    /// module (hub#1532), when and why.
    /// Never a delete — see [`print_queue::discard`]. `discarded_by` and `discarded_by_module` are
    /// resolved by the caller from the session and `X-Erplora-Module`, never taken from a request
    /// body; `discarded_by_module` is `""` when the caller named no module.
    pub async fn discard_print_job(
        &self,
        job_id: &str,
        discarded_by: &str,
        discarded_by_module: &str,
        reason: &str,
    ) -> Result<print_queue::DiscardOutcome> {
        print_queue::discard(
            self.db.as_ref(),
            &self.hub_id,
            job_id,
            discarded_by,
            discarded_by_module,
            reason,
        )
        .await
    }

    // ── Print stations: the destinations themselves, as rows (hub#457) ─────────────────────────

    /// Every printing destination of this hub, by key. This is what a selector shows and what the
    /// refusal of an unknown role names.
    pub async fn print_stations(&self) -> Result<Vec<print_stations::PrintStation>> {
        print_stations::list(self.db.as_ref(), &self.hub_id).await
    }

    /// Adds a station ("Barra de la terraza"). An empty `key` is derived from the label.
    pub async fn create_print_station(
        &self,
        key: &str,
        label: &str,
    ) -> Result<print_stations::PrintStation> {
        print_stations::create(self.db.as_ref(), &self.hub_id, key, label).await
    }

    /// Renames a station — the label only; the key is what every queued job already carries.
    /// `None` = no such station in this hub.
    pub async fn rename_print_station(
        &self,
        id: &str,
        label: &str,
    ) -> Result<Option<print_stations::PrintStation>> {
        print_stations::rename(self.db.as_ref(), &self.hub_id, id, label).await
    }

    /// Removes a station and the host registrations that pointed at it. Refuses while it still
    /// has unfinished work, and always for `receipt` — see [`print_stations::delete`].
    pub async fn delete_print_station(&self, id: &str) -> Result<print_stations::DeleteOutcome> {
        print_stations::delete(self.db.as_ref(), &self.hub_id, id).await
    }

    // ── Print hosts: who drains each printer role (ADR-0196 §6, hub#342) ───────────────────────

    /// Registers `device_id` as a print host of `role` (or refreshes a registration it had).
    /// Several devices may host one role and one device may host several — see [`print_hosts`].
    pub async fn register_print_host(
        &self,
        device_id: &str,
        role: &str,
        label: &str,
        actor: &str,
    ) -> Result<print_hosts::PrintHost> {
        print_hosts::register(
            self.db.as_ref(),
            &self.hub_id,
            device_id,
            role,
            label,
            actor,
        )
        .await
    }

    /// News from a print host: it is still there, for every role it drains. Returns how many
    /// registrations were refreshed (`0` = this device hosts nothing here and must register).
    pub async fn print_host_heartbeat(&self, device_id: &str) -> Result<usize> {
        print_hosts::heartbeat(self.db.as_ref(), &self.hub_id, device_id).await
    }

    /// Retires a device from `role`, or from all its roles when `role` is `None`. Returns how many
    /// registrations were removed.
    pub async fn unregister_print_host(
        &self,
        device_id: &str,
        role: Option<&str>,
    ) -> Result<usize> {
        print_hosts::unregister(self.db.as_ref(), &self.hub_id, device_id, role).await
    }

    /// The print host registry, with `live` resolved from each device's last news.
    pub async fn print_hosts(&self) -> Result<Vec<print_hosts::PrintHost>> {
        print_hosts::list(self.db.as_ref(), &self.hub_id).await
    }

    /// Per printer role: how much work is waiting and how many hosts are live. This is what lets
    /// the hub say "nothing is printing the kitchen's tickets" instead of leaving the queue to
    /// grow in silence.
    pub async fn print_coverage(&self) -> Result<Vec<print_hosts::RoleCoverage>> {
        print_hosts::coverage(self.db.as_ref(), &self.hub_id).await
    }

    /// The stations that are stuck: work waiting, nobody draining, past the threshold (hub#987).
    /// The cheap question a badge on every screen is allowed to ask — see [`print_hosts::undrained`].
    pub async fn print_undrained(&self) -> Result<Vec<print_hosts::RoleCoverage>> {
        print_hosts::undrained(self.db.as_ref(), &self.hub_id).await
    }

    /// This hub's `documentType → station` map (hub#987): where each kind of document comes out.
    pub async fn print_routes(&self) -> Result<Vec<print_routes::PrintRoute>> {
        print_routes::list(self.db.as_ref(), &self.hub_id).await
    }

    /// Points a document type at a station. The merchant's decision, not a module's.
    pub async fn set_print_route(
        &self,
        document_type: &str,
        station_key: &str,
        actor: &str,
    ) -> Result<print_routes::PrintRoute> {
        print_routes::set(
            self.db.as_ref(),
            &self.hub_id,
            document_type,
            station_key,
            actor,
        )
        .await
    }

    // ── Draining the queue: who may pull, and who may close (ADR-0196 §6, hub#343) ─────────────

    /// Hands the next job of `role` to `device_id` — **only** if that device is a registered print
    /// host of that role here. Reclaims expired leases on the way in, so a ticket stranded by a
    /// dead host comes back without any background sweeper having to be alive. See [`print_drain`].
    pub async fn claim_print_job(
        &self,
        device_id: &str,
        role: &str,
    ) -> Result<Option<print_queue::PrintJob>> {
        print_drain::claim(self.db.as_ref(), &self.hub_id, device_id, role).await
    }

    /// The print host confirms the paper came out. `false` = this hub has no such job (or it was
    /// already terminal). Refused if the device does not host that job's role.
    pub async fn confirm_print_job(&self, device_id: &str, job_id: &str) -> Result<bool> {
        print_drain::confirm(self.db.as_ref(), &self.hub_id, device_id, job_id).await
    }

    /// The print host could not print it. `true` = back in the queue, `false` = dead-lettered.
    pub async fn fail_print_job(&self, device_id: &str, job_id: &str, error: &str) -> Result<bool> {
        print_drain::report_failure(self.db.as_ref(), &self.hub_id, device_id, job_id, error).await
    }

    /// Which printer roles `device_id` hosts here — the hub's answer to "what am I for?", so the
    /// draining client never has to guess.
    pub async fn print_roles_of_device(&self, device_id: &str) -> Result<Vec<String>> {
        print_drain::hosted_roles(self.db.as_ref(), &self.hub_id, device_id).await
    }

    // ── Identidad local (usuarios/PIN/sesiones; §2.9). La autoridad de permisos es local. ──
}
