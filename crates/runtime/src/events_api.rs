//! Outbox processing, dead events and the event catalogue — split out of `lib.rs` verbatim (hub#1403).

use crate::*;

impl Runtime {
    /// Un ciclo del relay de eventos: entrega los eventos vencidos del outbox a sus listeners.
    /// Lo llama el bucle de background del server. Devuelve cuántas filas tomó (0 = nada vencido).
    pub async fn process_outbox(&self) -> Result<usize> {
        outbox::process_once(self.db.as_ref(), &self.registry).await
    }

    /// Drena el outbox hasta vaciarlo (cascada incluida). Útil al arrancar y en tests.
    pub async fn drain_outbox(&self) -> Result<usize> {
        outbox::drain(self.db.as_ref(), &self.registry).await
    }

    /// Dead-letters of this hub, newest first (hub#660). What the relay gave up on, with the
    /// payload it was carrying — the queue an admin operates from `/api/hub/events/dead`.
    pub async fn list_dead_events(&self, limit: i64) -> Result<Vec<outbox::DeadEvent>> {
        outbox::list_dead(self.db.as_ref(), &self.hub_id, limit).await
    }

    /// Dead-letters of this hub an operator CLOSED, newest closure first (hub#1117) — the read
    /// half of [`Self::discard_dead_event`]. Who closed each row, when and WHY, which had been
    /// written in full since hub#955 and projected by nothing: closing a row took it out of
    /// `list_dead`, the only listing there was. No payload travels: the decision is made, and what
    /// is asked of a closed row afterwards is the stamp, not the cargo.
    pub async fn list_discarded_events(&self, limit: i64) -> Result<Vec<outbox::DiscardedEvent>> {
        outbox::list_discarded(self.db.as_ref(), &self.hub_id, limit).await
    }

    /// Puts a dead-letter back in front of the relay (`pending`, attempts reset). Three answers,
    /// because a row that CANNOT be replayed is neither a success nor a missing id
    /// ([`outbox::RetryOutcome`], hub#827).
    pub async fn retry_dead_event(&self, id: &str) -> Result<outbox::RetryOutcome> {
        outbox::retry(self.db.as_ref(), &self.hub_id, id).await
    }

    /// Closes a dead-letter for good, keeping the row (auditable). `discarded_by` is the identity
    /// the HTTP layer resolved from the session; `reason` is why the person closed it (hub#955),
    /// optional and stored clamped. `false` if there is no such dead-letter here.
    pub async fn discard_dead_event(
        &self,
        id: &str,
        discarded_by: &str,
        reason: &str,
    ) -> Result<bool> {
        outbox::discard(self.db.as_ref(), &self.hub_id, id, discarded_by, reason).await
    }

    /// Puts EVERY dead-letter of this hub back in front of the relay at once (bulk retry, hub#660).
    /// Returns how many rows it moved. The hub never stays stuck behind a queue that only moves one
    /// click at a time: a transient outage that killed several events is cleared in one gesture.
    pub async fn retry_all_dead_events(&self) -> Result<u64> {
        outbox::retry_all(self.db.as_ref(), &self.hub_id).await
    }

    /// How many dead-letters this hub has right now (hub#660). Cheap count — powers the topbar bell
    /// without dragging the payloads the listing carries.
    pub async fn count_dead_events(&self) -> Result<i64> {
        outbox::count_dead(self.db.as_ref(), &self.hub_id).await
    }

    /// **What one event carries**, inferred from the last `limit` real events of this hub
    /// (hub#715) — the read the flow editor's data picker is built from, so an owner chooses
    /// «Total de la venta — 42,50 €» instead of `sale.total`.
    ///
    /// What comes back is the SHAPE, never the stored payloads: keys, types and one sample each,
    /// with the sample withheld wherever the value could be about a person
    /// ([`crate::event_shape`] explains where that line is drawn and why it is minimisation and
    /// not anonymisation).
    ///
    /// Three answers, and the middle one is the reason this returns an `Option` rather than an
    /// empty shape:
    ///
    /// - `Some(shape)` with samples — the event has happened here;
    /// - `Some(shape)` with `samples: 0` — an installed module declares it and no example
    ///   survives: it has never fired, or the last one aged out of the ninety-day retention window
    ///   (hub#699). An infrequent event lives here, and the editor must still offer it;
    /// - `None` — nobody declares it and it has never been seen. Only THAT is «no such event».
    pub async fn event_shape(
        &self,
        event_name: &str,
        limit: i64,
    ) -> Result<Option<event_shape::EventShape>> {
        let declared_by = self.registry.modules_emitting(event_name);
        let samples =
            outbox::sample_payloads(self.db.as_ref(), &self.hub_id, event_name, limit).await?;
        if declared_by.is_empty() && samples.is_empty() {
            return Ok(None);
        }
        let payloads: Vec<Json> = samples.iter().map(|s| s.payload.clone()).collect();
        Ok(Some(event_shape::EventShape {
            event_name: event_name.to_string(),
            declared_by,
            samples: samples.len(),
            last_seen_at: samples.first().map(|s| s.created_at.clone()),
            // The NAME travels into the inference: for a flat payload it is the only thing that
            // says whose data this is (hub#826).
            fields: event_shape::infer(event_name, &payloads),
        }))
    }

    /// **Every event this hub can speak of**, by name (hub#823) — the read the flow editor's
    /// «Cuando pase…» dropdown is built from, so it stops being seeded from a hand-written file
    /// that can never offer an event this hub emits and the file does not know.
    ///
    /// The union of two honest sources, sorted by name:
    ///
    /// - what installed modules DECLARE ([`Registry::declared_events`]: `events.emits` plus each
    ///   command's `emit`) — a declared event that never fired is still offered, with no
    ///   `last_seen_at`;
    /// - what was really SEEN in the outbox ([`outbox::seen_event_names`]) — an event that
    ///   happened and that nobody declares any more (a core event, an uninstalled module) is
    ///   still offered, with `declared_by` empty.
    ///
    /// Names only: what an event carries is [`Self::event_shape`]'s answer, with its redaction.
    pub async fn event_catalog(&self) -> Result<Vec<event_shape::EventCatalogEntry>> {
        let mut entries: std::collections::BTreeMap<String, event_shape::EventCatalogEntry> = self
            .registry
            .declared_events()
            .into_iter()
            .map(|(name, declared_by)| {
                (
                    name.clone(),
                    event_shape::EventCatalogEntry {
                        name,
                        declared_by,
                        last_seen_at: None,
                    },
                )
            })
            .collect();
        for seen in outbox::seen_event_names(self.db.as_ref(), &self.hub_id).await? {
            entries
                .entry(seen.name.clone())
                .or_insert_with(|| event_shape::EventCatalogEntry {
                    name: seen.name,
                    declared_by: Vec::new(),
                    last_seen_at: None,
                })
                .last_seen_at = Some(seen.last_seen_at);
        }
        Ok(entries.into_values().collect())
    }

    /// **What one event set off**: the runs it started and the events its delivery caused. This is
    /// the answer to «this sale fired these five steps», read from the event end of the chain.
    /// `None` when the event is not in this hub.
    pub async fn trace_event(&self, event_id: &str) -> Result<Option<EventTrace>> {
        let db = self.db.as_ref();
        let Some(event) = outbox::correlated_event(db, &self.hub_id, event_id).await? else {
            return Ok(None);
        };
        Ok(Some(EventTrace {
            runs: flows::store::runs_of_event(db, &self.hub_id, event_id).await?,
            caused: outbox::events_caused_by(db, &self.hub_id, event_id).await?,
            event,
        }))
    }

    // ── The agent step: what the server-side runner is allowed to ask for (hub#665) ──────────
    //
    // The runner lives in `crates/server` because it needs `cloud-client`, and the runtime has no
    // network by design. Everything it is NOT allowed to decide for itself goes through the
    // methods below (plus `complete_flow_io`, the seam hub#662 built) — and none of them lets it
    // build an automation context of its own:
    // `RequestContext.automation` is private with a `pub(crate)` setter precisely so that a caller
    // outside this crate cannot stamp a flow's identity on a request and inherit its grants
    // (flows.md §13.9).
}
