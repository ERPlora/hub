//! VerifactuEngine: NativeHandler entry point, errors and the contingency queue KPI — split out of `lib.rs` verbatim (hub#1405).

use crate::*;

/// Errores internos del motor (se aplanan a [`RuntimeError::Native`]).
#[derive(Debug, thiserror::Error)]
pub enum VerifactuError {
    #[error("payload inválido: {0}")]
    Payload(String),
    #[error("certificado: {0}")]
    Certificate(String),
    #[error("transmisión AEAT: {0}")]
    Transmission(String),
    /// El canal TLS con la AEAT falló: nuestro certificado de cliente fue rechazado, caducó, fue
    /// revocado, o el handshake no llegó a cerrarse (`aeat::is_tls_failure`).
    ///
    /// Variante propia porque **un fallo de red se reintenta y este se ARREGLA**: el registro se
    /// encola igual en contingencia, pero lo que hay que hacer con él no es esperar — es renovar el
    /// certificado. Distinguirlo es lo que deja que un operador lea «TLS» en el evento y sepa por
    /// dónde empezar, en vez de ver un `Transmission` más entre timeouts.
    ///
    /// 🪦 Hasta hub#1435 además **disparaba el refetch** del certificado delegado (ADR-0202 §2
    /// punto 4 — hub#318): ERPlora bajaba el suyo vigente del plano de control. Ese slot se retiró,
    /// y con la vía propia no hay nada que ERPlora pueda refrescar — el `.p12` es del negocio y lo
    /// renueva su dueño. La variante sigue por lo de arriba, NO para volver a disparar nada.
    #[error("transmisión AEAT (TLS): {0}")]
    Tls(String),
    /// La AEAT respondió a la **consulta** con un fallo (SOAP Fault). Es un error propio y no
    /// una lista vacía: «0 registros» se leería como «no hay nada que recuperar», que es la
    /// lectura que rompe la recuperación de la cadena (hub#287).
    #[error("consulta AEAT: {0}")]
    Consult(String),
    /// A field the AEAT requires is missing from what we were about to send; named by its XML
    /// tag, never by prose (hub#1070) — it is cut here because the 4102 the AEAT would answer
    /// arrives AFTER having talked to Hacienda.
    #[error("falta el campo obligatorio `{0}`")]
    MissingField(&'static str),
    /// The XML violates an `xs:sequence` of the schema: `tag` appears out of order; `sequence` is
    /// the order the schema expects (hub#1070: asserted by tag, not by the Spanish text).
    #[error("`{tag}` va fuera de orden: la secuencia del esquema es {sequence}")]
    OutOfOrder { tag: String, sequence: String },
}

impl From<VerifactuError> for RuntimeError {
    fn from(e: VerifactuError) -> Self {
        RuntimeError::Native(e.to_string())
    }
}

/// El plugin nativo del módulo `verifactu`. Se registra en el runtime con
/// `runtime.register_native("verifactu", Arc::new(VerifactuEngine))`.
#[derive(Debug, Default)]
pub struct VerifactuEngine;

#[async_trait::async_trait]
impl NativeHandler for VerifactuEngine {
    async fn call(&self, function: &str, input: &Json, host: &dyn NativeHost) -> Result<Output> {
        match function {
            "create_record" => create_record(input, host).await,
            "ingest_invoice" => ingest_invoice(input, host).await,
            "transmit_record" => transmit_record(input, host).await,
            "validate_chain" => validate_chain(input, host).await,
            "query_aeat_records" => query_aeat_records(input, host).await,
            "recover_from_aeat" => recover_from_aeat(input, host).await,
            "recover_manual" => recover_manual(input, host).await,
            "process_contingency_queue" => process_contingency_queue(input, host).await,
            "run_diagnostics" => run_diagnostics(input, host).await,
            other => Err(RuntimeError::Native(format!(
                "función desconocida del plugin verifactu: `{other}`"
            ))),
        }
    }

    /// **Retention gate (hub#314, ADR-0202 guard R2).** Records the AEAT does NOT have yet.
    /// While this is non-zero the runtime refuses to deactivate or uninstall the module: those
    /// records are the only proof pending for invoices already issued, and nothing outside this
    /// module can transmit them (VeriFactu FAQ §5).
    ///
    /// The counted states are exactly the module's own `compliance_summary` KPI —
    /// `pending`/`retry`/`error`/`rejected`, everything short of `accepted` — so the number in
    /// the refusal is the same one the operator already sees on the dashboard, and clearing the
    /// KPI is literally the way out. `rejected` counts too: the AEAT rejected the record, so the
    /// invoice is still unregistered and needs a corrected one before the module may go
    /// (`is_chainable_status`: a rejected link is not in the chain either).
    async fn pending_obligations(
        &self,
        hub_id: &str,
        host: &dyn NativeHost,
    ) -> Result<Option<PendingObligation>> {
        let queue = contingency_queue(hub_id, host).await?;
        let count = queue.depth;
        if count == 0 {
            return Ok(None);
        }
        Ok(Some(PendingObligation {
            count,
            // Since-when travels with the count (hub#326/hub#1406): same queue read,
            // so the heartbeat and this refusal can never disagree.
            oldest_pending_at: queue.oldest_pending_at,
            code: "verifactu.unsent_records".to_string(),
            // English source string; the UI translates against the stable code (ADR-0055).
            message: format!(
                "{count} VeriFactu record(s) have not reached the AEAT yet: send them before disabling or removing the module"
            ),
        }))
    }
}

/// How much work the AEAT is still waiting for, and since when (hub#326).
///
/// It is the **same** set of records the retention gate counts
/// (`NativeHandler::pending_obligations`) — everything short of `accepted` — read with the same
/// query, so the number the SaaS alerts on and the number that blocks an uninstall can never
/// disagree.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ContingencyQueue {
    /// Records this hub has not handed over yet. **`0` is a fact**, not an absence: it means the
    /// chain is fully remitted. «I could not count it» is the `Err` of [`contingency_queue`].
    pub depth: u64,
    /// `created_at` of the oldest entry still waiting, or `None` when the queue is empty.
    ///
    /// The hub reports the wait it can measure and **does not decide what «stuck» means**: a
    /// threshold belongs where the alert is raised (the SaaS), not baked into every hub in the
    /// fleet — a restaurant mid-service and a hub whose certificate expired last week both have a
    /// non-empty queue, and only the age tells them apart.
    pub oldest_pending_at: Option<String>,
}

/// Measure the contingency queue for `hub_id`: depth plus the wait of its oldest entry.
///
/// One query for both numbers, and the same one the retention gate uses. An `Err` means the read
/// itself failed (no `verifactu` module installed, so no table) — callers must report that as
/// «unknown», never as a zero: a fabricated `0` tells the fleet panel that a queue nobody could
/// read is under control, which is exactly the blindness hub#326 exists to remove.
pub async fn contingency_queue(hub_id: &str, host: &dyn NativeHost) -> Result<ContingencyQueue> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let rows = host
        .read(
            "SELECT COUNT(*) AS pending_count, MIN(created_at) AS oldest_pending_at \
             FROM verifactu_record \
             WHERE hub_id = :hub_id AND is_deleted = 0 \
               AND status IN ('pending', 'retry', 'error', 'rejected')",
            &p,
        )
        .await?;
    let row = rows.first();
    let depth = row
        .map(|r| int_field(r, "pending_count", 0))
        .unwrap_or(0)
        .max(0) as u64;
    let oldest_pending_at = row
        .and_then(|r| r.get("oldest_pending_at"))
        .and_then(|v| v.as_str())
        .map(str::to_owned);
    Ok(ContingencyQueue {
        depth,
        oldest_pending_at,
    })
}

// ── helpers de input ─────────────────────────────────────────────────────────

#[cfg(test)]
mod retention_gate_tests {
    //! ADR-0202 phase 1, guard R2 (hub#314): while records are still unsent, the module cannot
    //! be disabled or uninstalled. The runtime owns the refusal; the engine owns the COUNT and
    //! the stable code, because only it knows which record states mean "the AEAT does not have
    //! this invoice yet".

    use super::*;
    use erplora_runtime::native::NativeHandler;
    use std::sync::Mutex;

    const HUB: &str = "7b2f8a44-9c1d-4e2f-8a3b-944445555666";

    /// Answers the gate's COUNT with a fixed number and records the SQL it was asked, so the
    /// test can assert WHICH records the engine considers still owed to the AEAT.
    struct CountingHost {
        pending: i64,
        reads: Mutex<Vec<String>>,
    }

    impl CountingHost {
        fn with(pending: i64) -> Self {
            CountingHost {
                pending,
                reads: Mutex::new(Vec::new()),
            }
        }
    }

    #[async_trait::async_trait]
    impl NativeHost for CountingHost {
        async fn read(&self, sql: &str, _p: &Params) -> Result<Vec<Json>> {
            self.reads.lock().unwrap().push(sql.to_string());
            Ok(vec![json!({ "pending_count": self.pending })])
        }
    }

    #[tokio::test]
    async fn unsent_records_are_reported_as_a_pending_obligation() {
        let host = CountingHost::with(4);
        let owed = VerifactuEngine
            .pending_obligations(HUB, &host)
            .await
            .expect("counting what is owed must not fail")
            .expect("4 unsent records are an obligation");

        assert_eq!(owed.count, 4, "the operator must be told how many are left");
        assert_eq!(
            owed.code, "verifactu.unsent_records",
            "the stable code lives in the module's own namespace (hub#139 ABI)"
        );
        assert!(
            owed.message.contains('4'),
            "the human fallback must carry the count, got `{}`",
            owed.message
        );

        let reads = host.reads.lock().unwrap();
        let sql = reads.first().expect("the engine must ask the database");
        assert!(
            sql.contains("verifactu_record") && sql.contains("hub_id = :hub_id"),
            "the count is scoped to this hub's records: {sql}"
        );
        for state in ["pending", "retry", "error", "rejected"] {
            assert!(
                sql.contains(state),
                "`{state}` means the AEAT does not have the invoice yet — it must be counted: {sql}"
            );
        }
        assert!(
            sql.contains("is_deleted = 0"),
            "a soft-deleted record is not an obligation: {sql}"
        );
    }

    #[tokio::test]
    async fn a_fully_handed_over_chain_owes_nothing() {
        let host = CountingHost::with(0);
        let owed = VerifactuEngine
            .pending_obligations(HUB, &host)
            .await
            .expect("counting what is owed must not fail");
        assert!(
            owed.is_none(),
            "with every record accepted by the AEAT the module is free to be removed"
        );
    }
}

#[cfg(test)]
mod contingency_queue_tests {
    //! hub#326: the daily heartbeat carries how deep the contingency queue is and how long its
    //! oldest entry has been waiting, so a hub that stopped remitting is visible from the SaaS
    //! instead of only from its own dashboard.

    use super::*;
    use erplora_runtime::native::NativeHandler;
    use std::sync::Mutex;

    const HUB: &str = "7b2f8a44-9c1d-4e2f-8a3b-944445555666";

    /// Answers the queue read with a fixed count and oldest timestamp, recording the SQL so the
    /// test can assert WHICH records are being counted — and that there is only ONE query.
    struct QueueHost {
        pending: i64,
        oldest: Json,
        reads: Mutex<Vec<String>>,
    }

    impl QueueHost {
        fn with(pending: i64, oldest: Json) -> Self {
            QueueHost {
                pending,
                oldest,
                reads: Mutex::new(Vec::new()),
            }
        }
    }

    #[async_trait::async_trait]
    impl NativeHost for QueueHost {
        async fn read(&self, sql: &str, _p: &Params) -> Result<Vec<Json>> {
            self.reads.lock().unwrap().push(sql.to_string());
            let mut row = json!({ "pending_count": self.pending });
            // Like a real database, a column the query did not SELECT is simply not in the row.
            // Handing back the oldest timestamp unconditionally would make this test pass against
            // a query that never asks for it — the mock would be answering, not the engine.
            if sql.contains("MIN(created_at) AS oldest_pending_at") {
                row["oldest_pending_at"] = self.oldest.clone();
            }
            Ok(vec![row])
        }
    }

    /// A host whose reads fail, like a hub where the module was never installed and the table
    /// does not exist.
    struct BrokenHost;

    #[async_trait::async_trait]
    impl NativeHost for BrokenHost {
        async fn read(&self, _sql: &str, _p: &Params) -> Result<Vec<Json>> {
            Err(RuntimeError::Native("relation does not exist".into()))
        }
    }

    #[tokio::test]
    async fn the_queue_reports_its_depth_and_the_oldest_entry_still_waiting() {
        let host = QueueHost::with(4, json!("2026-08-01T09:00:00Z"));

        let queue = contingency_queue(HUB, &host)
            .await
            .expect("measuring the queue must not fail");

        assert_eq!(queue.depth, 4);
        assert_eq!(
            queue.oldest_pending_at.as_deref(),
            Some("2026-08-01T09:00:00Z"),
            "the age of the oldest entry is what separates a busy till from a stuck hub"
        );

        let reads = host.reads.lock().unwrap();
        assert_eq!(reads.len(), 1, "depth and age are one read, not two");
        let sql = &reads[0];
        assert!(
            sql.contains("verifactu_record") && sql.contains("hub_id = :hub_id"),
            "the queue is scoped to this hub's records: {sql}"
        );
        for state in ["pending", "retry", "error", "rejected"] {
            assert!(
                sql.contains(state),
                "`{state}` means the AEAT does not have the invoice yet: {sql}"
            );
        }
        assert!(
            sql.contains("is_deleted = 0"),
            "a soft-deleted record is not queued work: {sql}"
        );
    }

    /// **An empty queue is an explicit `0`, never silence.** The heartbeat's `Option` contract
    /// reserves «absent» for «I could not count it»; a hub that has handed everything over must
    /// say zero, or the fleet panel cannot tell it apart from one that went quiet.
    #[tokio::test]
    async fn a_drained_queue_reports_zero_and_no_oldest_entry() {
        let host = QueueHost::with(0, Json::Null);

        let queue = contingency_queue(HUB, &host)
            .await
            .expect("measuring the queue must not fail");

        assert_eq!(queue.depth, 0);
        assert_eq!(queue.oldest_pending_at, None);
    }

    /// **A read failure is an error, not a zero.** The caller turns it into an absent field; if
    /// this returned `0` the SaaS would read a hub whose table it cannot even open as healthy.
    #[tokio::test]
    async fn a_read_failure_is_not_an_empty_queue() {
        assert!(
            contingency_queue(HUB, &BrokenHost).await.is_err(),
            "not being able to count is not the same as having nothing to count"
        );
    }

    /// 🔒 **One query, one truth.** The retention gate (hub#314) and the heartbeat must count the
    /// same records: if they drifted, the SaaS would raise an alert about a queue the operator's
    /// own dashboard says is empty — or, worse, stay silent about one that blocks an uninstall.
    #[tokio::test]
    async fn the_retention_gate_reads_the_very_same_query() {
        let gate_host = QueueHost::with(4, json!("2026-08-01T09:00:00Z"));
        let owed = VerifactuEngine
            .pending_obligations(HUB, &gate_host)
            .await
            .expect("the gate must not fail")
            .expect("4 unsent records are an obligation");
        assert_eq!(owed.count, 4);

        let queue_host = QueueHost::with(4, json!("2026-08-01T09:00:00Z"));
        let queue = contingency_queue(HUB, &queue_host).await.unwrap();
        assert_eq!(u64::from(owed.count), queue.depth);

        assert_eq!(
            *gate_host.reads.lock().unwrap(),
            *queue_host.reads.lock().unwrap(),
            "both answers must come from the SAME SQL — a second copy is a second truth"
        );
    }
}
