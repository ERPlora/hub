//! Manual invoice ingest — split out of `lib.rs` verbatim (hub#1405).

use crate::*;

/// Listener de `invoice.created` / `invoice.rectified`: crea automáticamente un **RegistroAlta**
/// VeriFactu desde una factura emitida (o rectificativa). Modelo español: una factura no se
/// anula — la devolución es una **factura rectificativa** (TipoFactura R1–R5, importes negativos)
/// que también se declara como alta. (El `RegistroAnulación` es solo para errores de envío, vía
/// `create_record`.) El `record_type` es **siempre `alta`**; el `invoice_type` real (F1–F3 / R1–R5)
/// se toma de la factura.
///
/// El payload del evento solo trae el id de la factura; el **número oficial** (`PREFIX-YYYY-NNNNNN`)
/// se calcula en SQL al insertar la factura y no viaja en el evento WASM `invoice.created`, así que
/// se resuelve con una lectura acotada por id de `invoice_invoice` (excepción documentada para el
/// plugin nativo first-party; `verifactu depends_on invoice`). Idempotente: si la factura no existe
/// devuelve vacío, y el índice único `uq_verifactu_record` evita duplicar el registro en reentregas.
pub(crate) async fn ingest_invoice(input: &Json, host: &dyn NativeHost) -> Result<Output> {
    let (payload, ctx) = split_input(input)?;

    // El id de factura llega como `invoice_id` (invoice.created) o `new_id` (invoice.rectified).
    let invoice_id = {
        let candidates = [
            str_field(&payload, "invoice_id"),
            str_field(&payload, "new_id"),
            str_field(&payload, "id"),
        ];
        candidates
            .into_iter()
            .find(|s| !s.is_empty())
            .unwrap_or_default()
    };
    if invoice_id.is_empty() {
        return Ok(Output::new()); // nada que ingerir
    }

    // Lectura acotada por id de la factura (snapshot fiscal: número oficial + importes). Los dos
    // LEFT JOIN a sí misma traen, EN LA MISMA lectura (respeta la "única lectura acotada" de
    // ADR-0058), la factura enlazada de cada caso:
    //
    // - `substitutes_invoice_id` → la F2 que una F3 sustituye (bloque XML `FacturasSustituidas`);
    // - `rectifies_invoice_id`   → la factura que una R1-R5 rectifica (`FacturasRectificadas`,
    //   hub#1023) — el camino normal de una devolución en TPV.
    //
    // NULL/'' cuando la factura no enlaza nada, que es el caso de toda venta corriente.
    //
    // And the line `COUNT` (hub#1180): a breakdown whose quota was rounded per line cannot be
    // judged without knowing how many lines were aggregated — a fixed tolerance rejected legitimate
    // multi-line tickets (see `line_rate_tolerance_cents`). `invoice` stopped producing that shape
    // in ADR-0405, but the rows already sealed — and every verbatim F3 — still carry it. It goes as
    // subconsulta de ESTA lectura, no como una segunda: un listener que abre dos lecturas por venta
    // es una lectura de más en cada tique, y ADR-0058 acota la excepción a UNA.
    let rows = host
        .read(
            "SELECT i.invoice_type, i.number, i.issue_date, i.issuer_nif, i.issuer_name, \
             i.customer_tax_id, i.customer_name, i.description, \
             i.base_amount, i.tax_amount, i.total_amount, i.tax_breakdown, \
             COALESCE(sub.number, '') AS substitutes_number, \
             COALESCE(sub.issue_date, '') AS substitutes_date, \
             COALESCE(sub.issuer_nif, '') AS substitutes_nif, \
             COALESCE(rec.number, '') AS rectifies_number, \
             COALESCE(rec.issue_date, '') AS rectifies_date, \
             COALESCE(rec.issuer_nif, '') AS rectifies_nif, \
             (SELECT COUNT(*) FROM invoice_invoiceitem it \
                WHERE it.invoice_id = i.id AND it.hub_id = i.hub_id) AS line_count \
             FROM invoice_invoice i \
             LEFT JOIN invoice_invoice sub \
               ON sub.id = i.substitutes_invoice_id AND sub.hub_id = i.hub_id AND sub.is_deleted = 0 \
             LEFT JOIN invoice_invoice rec \
               ON rec.id = i.rectifies_invoice_id AND rec.hub_id = i.hub_id AND rec.is_deleted = 0 \
             WHERE i.id = :invoice_id AND i.hub_id = :hub_id AND i.is_deleted = 0 LIMIT 1",
            &params(json!({ "invoice_id": invoice_id, "hub_id": ctx.hub_id })),
        )
        .await?;
    let inv = match rows.into_iter().next() {
        Some(r) => r,
        None => return Ok(Output::new()), // factura inexistente/borrada → no-op idempotente
    };

    // NIF del emisor (obligado tributario): viene de la factura, que a su vez lo toma de la
    // identidad fiscal GLOBAL del hub (hub_settings, vía _insert_invoice). La AEAT lo exige no
    // vacío (es el ancla de la cadena de hash) y el resto del módulo lo rechaza así (create_record).
    // Antes este punto devolvía OK/0-operaciones en silencio (verifactu#109): la factura→VeriFactu
    // aparentaba éxito y no generaba registro, hash ni cola fiscal — falsa sensación de cumplimiento.
    // Ahora rechaza con un error claro para que el operario vea que falta configurar la identidad
    // fiscal global del hub.
    let issuer_nif = str_field(&inv, "issuer_nif");
    if issuer_nif.is_empty() {
        return Err(VerifactuError::Payload(
            "missing_issuer_nif: falta el NIF del emisor (identidad fiscal global del hub sin configurar); \
             no se puede encadenar el registro VeriFactu".into(),
        )
        .into());
    }

    // Destinatario de la factura: decide el TIPO antes de encadenar nada.
    let recipient_nif = str_field(&inv, "customer_tax_id");
    let declared_type = {
        let t = str_field(&inv, "invoice_type");
        if INVOICE_TYPES.contains(&t.as_str()) {
            t
        } else {
            "F1".to_string()
        }
    };
    // Sin NIF de cliente, una F1 sale sin `Destinatarios` y la AEAT la rechaza con 1189 — ya con
    // el número de cadena gastado. El tipo entra en la huella, así que se resuelve AQUÍ, antes de
    // calcularla (`resolve_invoice_type`).
    let invoice_type = resolve_invoice_type(&declared_type, &recipient_nif);
    // hub#1104: y si degradó, se ANOTA. El documento que el cliente se llevó dice una cosa y el
    // registro que se declara dice otra; que las dos verdades existan es inevitable, que nadie se
    // entere no. `build_record_output` emite el hecho y comprueba el techo de la F2.
    let downgraded_from = if invoice_type == declared_type {
        String::new()
    } else {
        declared_type
    };

    // DescripcionOperacion: la AEAT la exige NO vacía (rechaza con código 1100). Usa la descripción
    // de la factura; si está vacía, un fallback genérico con el nº de factura.
    let invoice_number = str_field(&inv, "number");
    let description = {
        let d = str_field(&inv, "description");
        if d.trim().is_empty() {
            format!("Venta {invoice_number}")
        } else {
            d
        }
    };

    build_record_output(
        host,
        &ctx,
        RecordInput {
            record_type: "alta".to_string(),
            issuer_nif,
            issuer_name: str_field(&inv, "issuer_name"),
            invoice_number: invoice_number.clone(),
            invoice_date: str_field(&inv, "issue_date"),
            invoice_type,
            // Viene del `COUNT` de la MISMA lectura acotada: es lo que hace juzgable la cuota del
            // desglose sin abrir una segunda consulta por cada venta.
            line_count: Some(int_field(&inv, "line_count", 1)),
            downgraded_from,
            description,
            // El módulo invoice guarda importes en CÉNTIMOS (ADR-0007), igual que `create_record`;
            // `build_record_output` espera céntimos y divide /100 al formatear para la AEAT/QR.
            // NO convertir aquí (el `* 100.0` previo declaraba importes ×100 a la AEAT — QA 2026-06-25).
            base_amount: num_field(&inv, "base_amount", 0.0),
            // The row's COLUMN rate: the one the breakdown declares when it is unique, and the
            // effective one only when there is none (mixed, or no readable breakdown). The XML
            // uses it only as the no-breakdown fallback: `aeat::desglose` emits one line per rate.
            tax_rate: derive_tax_rate(
                &str_field(&inv, "tax_breakdown"),
                num_field(&inv, "base_amount", 0.0),
                num_field(&inv, "tax_amount", 0.0),
            ),
            // El desglose real viaja íntegro hasta el XML: es lo que la AEAT tiene que ver.
            tax_breakdown: str_field(&inv, "tax_breakdown"),
            tax_amount: num_field(&inv, "tax_amount", 0.0),
            total_amount: num_field(&inv, "total_amount", 0.0),
            invoice_id: Json::String(invoice_id),
            // Destinatario para el bloque XML Destinatarios (F1/F3/R1-R4). Tiquets (F2) sin cliente
            // → vacío → sin Destinatarios. Evita el error AEAT 1189 en facturas completas.
            recipient_nif,
            recipient_name: str_field(&inv, "customer_name"),
            // F3 → FacturasSustituidas: datos de la F2 sustituida (del LEFT JOIN). Vacíos si no es F3.
            substitutes_number: str_field(&inv, "substitutes_number"),
            substitutes_date: str_field(&inv, "substitutes_date"),
            substitutes_nif: str_field(&inv, "substitutes_nif"),
            // R1-R5 → FacturasRectificadas: datos de la factura rectificada (del LEFT JOIN).
            rectifies_number: str_field(&inv, "rectifies_number"),
            rectifies_date: str_field(&inv, "rectifies_date"),
            rectifies_nif: str_field(&inv, "rectifies_nif"),
            // `invoice.rectify` emite la rectificativa **negando** el original, así que los
            // importes de esta factura SON el delta: es una rectificativa por diferencias, y el
            // XML la deriva de que no haya importes rectificados (ver `aeat::rectification_type`).
            // La sustitutiva (`S`) llega por `create_record`, que sí acepta los `rectified_*`;
            // el módulo `invoice` todavía no tiene columna que distinga los dos (invoice#5).
            rectification_type: String::new(),
            rectified_base_amount: Json::Null,
            rectified_tax_amount: Json::Null,
            rectified_surcharge_amount: Json::Null,
        },
    )
    .await
}

#[cfg(test)]
mod ingest_tests {
    use super::*;

    /// Host que devuelve UNA factura con `issuer_nif` vacío (identidad fiscal global sin configurar).
    struct NoIssuerHost;
    #[async_trait::async_trait]
    impl NativeHost for NoIssuerHost {
        async fn read(&self, sql: &str, _p: &Params) -> Result<Vec<Json>> {
            if sql.contains("FROM invoice_invoice") {
                Ok(vec![json!({
                    "invoice_type": "F2", "number": "TICKET-2026-000001",
                    "issue_date": "2026-07-31", "issuer_nif": "", "issuer_name": "",
                    "customer_tax_id": "", "customer_name": "Cliente",
                    "description": "Venta", "base_amount": 100, "tax_amount": 21, "total_amount": 121,
                    "tax_breakdown": "", "substitutes_number": "", "substitutes_date": "",
                    "substitutes_nif": ""
                })])
            } else {
                Ok(vec![])
            }
        }
    }

    /// Host que devuelve una **rectificativa** (R5 de un tique) con los datos de la factura que
    /// rectifica, tal y como los trae el `LEFT JOIN` por `rectifies_invoice_id`. Guarda el SQL
    /// para poder comprobar que la lectura los pide.
    struct RectifyingInvoiceHost {
        reads: std::sync::Mutex<Vec<String>>,
    }
    impl RectifyingInvoiceHost {
        fn new() -> Self {
            Self { reads: std::sync::Mutex::new(Vec::new()) }
        }
    }
    #[async_trait::async_trait]
    impl NativeHost for RectifyingInvoiceHost {
        async fn read(&self, sql: &str, _p: &Params) -> Result<Vec<Json>> {
            self.reads.lock().unwrap().push(sql.to_string());
            if sql.contains("FROM invoice_invoice") {
                return Ok(vec![json!({
                    "invoice_type": "R5", "number": "RECT-2026-000001",
                    "issue_date": "2026-08-20", "issuer_nif": "B27593136",
                    "issuer_name": "ERPLORA CLOUD SL",
                    "customer_tax_id": "", "customer_name": "",
                    "description": "Devolución", "base_amount": -1000,
                    "tax_amount": -210, "total_amount": -1210,
                    "tax_breakdown": r#"{"21.00":{"base":-1000,"tax":-210}}"#,
                    "substitutes_number": "", "substitutes_date": "", "substitutes_nif": "",
                    "rectifies_number": "TICKET-2026-000001",
                    "rectifies_date": "2026-08-02",
                    "rectifies_nif": "B27593136"
                })]);
            }
            Ok(vec![])
        }
    }

    /// hub#1023: una rectificativa nacida de una devolución tiene que llegar al XML con el enlace
    /// a la factura que rectifica. El dato viaja en la MISMA lectura acotada (ADR-0058), por el
    /// `LEFT JOIN` a `rectifies_invoice_id` — igual que la F3 hace con `substitutes_invoice_id`.
    #[tokio::test]
    async fn ingest_invoice_carries_the_rectified_invoice() {
        let host = RectifyingInvoiceHost::new();
        let input = json!({
            "payload": { "new_id": "inv-r1" },
            "context": {
                "hub_id": "3f2a1b4c-5d6e-4f70-8192-a3b4c5d6e7f8",
                "now": "2026-08-20T10:00:00+02:00", "current_user_id": "u1",
                "new_ids": ["id-rec", "id-evt", "id-queue", "id-t1", "id-t2", "id-t3"]
            }
        });
        let out = ingest_invoice(&input, &host).await.expect("la R5 se ingesta");

        let sql = host.reads.lock().unwrap().join("\n");
        assert!(
            sql.contains("rectifies_invoice_id"),
            "la lectura de la factura tiene que traer la rectificada: {sql}"
        );

        let insert = out
            .operations
            .iter()
            .find(|o| o.command == "verifactu._insert_record")
            .expect("se inserta el registro");
        for (field, expected) in [
            ("invoice_type", json!("R5")),
            ("rectifies_number", json!("TICKET-2026-000001")),
            ("rectifies_date", json!("2026-08-02")),
            ("rectifies_nif", json!("B27593136")),
        ] {
            assert_eq!(
                insert.params.get(field),
                Some(&expected),
                "el registro tiene que llevar `{field}`"
            );
        }
    }

    /// verifactu#109: una factura SIN issuer_nif debe RECHAZAR (antes devolvía OK/0-operaciones en
    /// silencio y no generaba registro fiscal — falsa sensación de cumplimiento).
    #[tokio::test]
    async fn ingest_invoice_rejects_missing_issuer_nif() {
        let input = json!({
            "payload": { "invoice_id": "inv-1" },
            "context": { "hub_id": "h1", "now": "2026-07-31T10:00:00Z", "current_user_id": "u1" }
        });
        let res = ingest_invoice(&input, &NoIssuerHost).await;
        let err = res.unwrap_err().to_string();
        assert!(
            err.contains("missing_issuer_nif"),
            "esperaba rechazo por issuer_nif vacío, llegó: {err}"
        );
    }
}

#[cfg(test)]
mod ingest_integrity_tests {
    //! hub#1103 + hub#1104 — **la última puerta antes de Hacienda tiene que juzgar lo que sella**.
    //!
    //! Dos defectos distintos de la MISMA puerta (`build_record_output`, por donde pasan tanto el
    //! command público `verifactu.records.create` como el listener `ingest_invoice`):
    //!
    //!  * **hub#1103** — la aritmética no se comprobaba. Un registro con `rate 21.0` y una cuota de
    //!    99,99 € sobre una base de 5,45 € se selló, se encadenó y se remitió VERBATIM. El módulo
    //!    cerró su mitad en la TABLA (`013_arithmetic_integrity.sql`, verifactu#53), pero una
    //!    violación de `CHECK` llega como error crudo de Postgres: sin código de dominio, sin motivo
    //!    legible y DESPUÉS de haber leído el ancla. Aquí se rechaza antes, con su código.
    //!  * **hub#1104** — una F1 sin NIF de destinatario se degradaba a F2 **en silencio** (y una
    //!    R1–R4 a R5, que es un cambio de naturaleza fiscal). La degradación es correcta —sin ella
    //!    la AEAT responde 1189 con el número de cadena ya gastado—, pero muda no lo es.
    use super::*;

    const HUB: &str = "9c1d7b2f-4e2f-8a3b-9444-455566677788";
    const NIF: &str = "B27593136";

    /// Host mínimo: config de `testing`, cadena vacía y sin certificado (no se transmite nada, que
    /// es lo que estos tests quieren observar — la puerta, no la red).
    struct GateHost;
    #[async_trait::async_trait]
    impl NativeHost for GateHost {
        async fn read(&self, sql: &str, _p: &Params) -> Result<Vec<Json>> {
            if sql.contains("FROM verifactu_config") {
                return Ok(vec![json!({
                    "hub_id": HUB, "environment": "testing",
                    "issuer_nif": NIF, "issuer_name": "Test Business SL"
                })]);
            }
            Ok(vec![])
        }
    }

    /// Host que sirve UNA factura del módulo `invoice`, tal cual la lee `ingest_invoice`, con el
    /// número de líneas que trae el `COUNT` de la misma lectura. Guarda el SQL que se le pide.
    struct InvoiceHost {
        invoice: Json,
        line_count: i64,
        reads: std::sync::Mutex<Vec<String>>,
    }
    impl InvoiceHost {
        /// Una factura de UNA línea, que es el caso corriente del camino manual.
        fn new(invoice: Json) -> Self {
            Self::with_lines(invoice, 1)
        }
        fn with_lines(invoice: Json, line_count: i64) -> Self {
            Self { invoice, line_count, reads: std::sync::Mutex::new(Vec::new()) }
        }
    }
    #[async_trait::async_trait]
    impl NativeHost for InvoiceHost {
        async fn read(&self, sql: &str, _p: &Params) -> Result<Vec<Json>> {
            self.reads.lock().unwrap().push(sql.to_string());
            if sql.contains("FROM verifactu_config") {
                return Ok(vec![json!({
                    "hub_id": HUB, "environment": "testing",
                    "issuer_nif": NIF, "issuer_name": "Test Business SL"
                })]);
            }
            if sql.contains("FROM invoice_invoice") {
                let mut row = self.invoice.clone();
                if let Some(m) = row.as_object_mut() {
                    m.insert("line_count".into(), json!(self.line_count));
                }
                return Ok(vec![row]);
            }
            Ok(vec![])
        }
    }

    fn ids() -> Json {
        json!([
            "id-rec", "id-evt", "id-queue", "id-t1", "id-t2", "id-t3", "id-warn", "id-x"
        ])
    }

    fn context() -> Json {
        json!({
            "hub_id": HUB, "now": "2026-08-25T10:00:00+02:00", "current_user_id": "u1",
            "new_ids": ids()
        })
    }

    /// Payload de `verifactu.records.create` con los importes que se le pasen.
    fn create_payload(
        invoice_type: &str,
        base: i64,
        rate: f64,
        tax: i64,
        total: i64,
        breakdown: &str,
    ) -> Json {
        json!({
            "payload": {
                "record_type": "alta", "issuer_nif": NIF, "issuer_name": "Test Business SL",
                "invoice_number": "F-2026-000123", "invoice_date": "2026-08-25",
                "invoice_type": invoice_type, "base_amount": base, "tax_rate": rate,
                "tax_amount": tax, "total_amount": total, "tax_breakdown": breakdown
            },
            "context": context()
        })
    }

    /// Factura de `invoice` con los importes y el destinatario que se le pasen.
    fn invoice_row(invoice_type: &str, customer_tax_id: &str, base: i64, tax: i64, total: i64, breakdown: &str) -> Json {
        json!({
            "invoice_type": invoice_type, "number": "FACT-2026-000009",
            "issue_date": "2026-08-25", "issuer_nif": NIF, "issuer_name": "Test Business SL",
            "customer_tax_id": customer_tax_id, "customer_name": "Cliente",
            "description": "Venta", "base_amount": base, "tax_amount": tax,
            "total_amount": total, "tax_breakdown": breakdown,
            "substitutes_number": "", "substitutes_date": "", "substitutes_nif": "",
            "rectifies_number": "", "rectifies_date": "", "rectifies_nif": ""
        })
    }

    fn ingest_input() -> Json {
        json!({ "payload": { "invoice_id": "inv-1" }, "context": context() })
    }

    fn error_of(res: Result<Output>) -> String {
        match res {
            Ok(out) => panic!(
                "esperaba un RECHAZO y el registro se selló: {:?}",
                out.operations.iter().map(|o| o.command.clone()).collect::<Vec<_>>()
            ),
            Err(e) => e.to_string(),
        }
    }

    fn event_of<'a>(out: &'a Output, event_type: &str) -> Option<&'a Operation> {
        out.operations.iter().find(|o| {
            o.command == "verifactu._insert_event"
                && o.params.get("event_type") == Some(&json!(event_type))
        })
    }

    // ── hub#1103 · la aritmética ────────────────────────────────────────────────────────────

    /// El caso EXACTO del QA: 99,99 € de cuota sobre una base de 5,45 € declarando el 21 %.
    /// `base + cuota = total` cuadra (545 + 9999 = 10544), así que solo la contrastación contra el
    /// TIPO declarado lo caza.
    #[tokio::test]
    async fn a_quota_its_own_rate_cannot_justify_is_refused() {
        let input = create_payload(
            "F1",
            545,
            21.0,
            9999,
            10544,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":545,"quota":9999}]"#,
        );
        let err = error_of(create_record(&input, &GateHost).await);
        assert!(err.contains("quota_rate_mismatch"), "código esperado, llegó: {err}");
    }

    /// Sin desglose legible solo queda el `tax_rate` de la fila, y tiene que juzgarse igual.
    #[tokio::test]
    async fn without_a_breakdown_the_row_rate_still_has_to_explain_the_quota() {
        let input = create_payload("F1", 545, 21.0, 9999, 10544, "");
        let err = error_of(create_record(&input, &GateHost).await);
        assert!(err.contains("quota_rate_mismatch"), "código esperado, llegó: {err}");
    }

    /// `base + cuota ≠ total`: la cabecera se contradice a sí misma. Ninguna de las tres reglas de
    /// la tabla lo mira (`013` lo dejó fuera a propósito), así que esta es la única puerta.
    #[tokio::test]
    async fn a_header_that_contradicts_itself_is_refused() {
        let input = create_payload(
            "F1",
            545,
            21.0,
            114,
            660,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":545,"quota":114}]"#,
        );
        let err = error_of(create_record(&input, &GateHost).await);
        assert!(err.contains("totals_mismatch"), "código esperado, llegó: {err}");
    }

    /// El desglose tiene que sumar lo que dice la cabecera: es el cruce que hace la AEAT
    /// (`CuotaTotal` = Σ cuotas declaradas).
    #[tokio::test]
    async fn a_breakdown_that_does_not_add_up_to_the_header_is_refused() {
        let input = create_payload(
            "F1",
            10000,
            21.0,
            2100,
            12100,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":5000,"quota":1050}]"#,
        );
        let err = error_of(create_record(&input, &GateHost).await);
        assert!(err.contains("totals_mismatch"), "código esperado, llegó: {err}");
    }

    /// Una ordinaria no totaliza negativo: lo negativo es una RECTIFICATIVA.
    #[tokio::test]
    async fn an_ordinary_invoice_cannot_total_negative() {
        let input = create_payload(
            "F1",
            -500,
            21.0,
            -105,
            -605,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":-500,"quota":-105}]"#,
        );
        let err = error_of(create_record(&input, &GateHost).await);
        assert!(err.contains("negative_total"), "código esperado, llegó: {err}");
    }

    /// 🔴 **La trampa de esta issue.** El criterio escrito pedía rechazar `total ≤ 0`, y eso
    /// contradice lo decidido en `invoice#50`: un tique 100 % invitado suma 0,00 € honestamente y
    /// sigue siendo una venta que necesita su F2. Se sella.
    #[tokio::test]
    async fn a_fully_comped_ticket_still_gets_its_record() {
        let input = create_payload(
            "F2",
            0,
            21.0,
            0,
            0,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":0,"quota":0}]"#,
        );
        let out = create_record(&input, &GateHost)
            .await
            .expect("un tique invitado se sella: 0,00 € cuadra");
        assert!(
            out.operations.iter().any(|o| o.command == "verifactu._insert_record"),
            "el registro tiene que existir"
        );
    }

    /// Una rectificativa SÍ lleva importes negativos: es el camino legal de una devolución.
    #[tokio::test]
    async fn a_corrective_invoice_may_be_negative() {
        let input = create_payload(
            "R5",
            -1000,
            21.0,
            -210,
            -1210,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":-1000,"quota":-210}]"#,
        );
        create_record(&input, &GateHost)
            .await
            .expect("una R5 negativa es legítima");
    }

    /// El recargo de equivalencia va en su propio par y se contrasta contra SU tipo.
    #[tokio::test]
    async fn the_equivalence_surcharge_is_checked_against_its_own_rate() {
        let input = create_payload(
            "F1",
            10000,
            21.0,
            2620,
            12620,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":10000,"quota":2100,
                 "surcharge_rate":5.2,"surcharge_quota":999}]"#,
        );
        let err = error_of(create_record(&input, &GateHost).await);
        assert!(err.contains("quota_rate_mismatch"), "código esperado, llegó: {err}");
    }

    /// Un ticket de bar legítimo (21 % + 10 %, con el céntimo de redondeo por línea) pasa: la
    /// guarda no puede dejar sin facturar una venta real.
    #[tokio::test]
    async fn a_legitimate_mixed_rate_ticket_is_sealed() {
        let input = create_payload(
            "F2",
            1001,
            16.58,
            166,
            1167,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":601,"quota":126},
                {"tax":"vat","regime":"01","class":"subject","rate":10.0,"base":400,"quota":40}]"#,
        );
        create_record(&input, &GateHost)
            .await
            .expect("un ticket mixto con su redondeo se sella");
    }

    /// Y la MISMA guarda cubre el camino automático: el listener de `invoice.created`.
    #[tokio::test]
    async fn the_listener_refuses_the_same_amounts_the_public_command_refuses() {
        let host = InvoiceHost::new(invoice_row(
            "F1",
            "87654321X",
            545,
            9999,
            10544,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":545,"quota":9999}]"#,
        ));
        let err = error_of(ingest_invoice(&ingest_input(), &host).await);
        assert!(err.contains("quota_rate_mismatch"), "código esperado, llegó: {err}");
    }

    /// 🔴 **The counterexample that sent this PR back with CHANGES** — still a live requirement,
    /// but no longer for the reason it was written.
    ///
    /// Four lines of 0,50 € at 21 %: rounding per line, `round_half_up(10,5) = 11` each → the
    /// breakdown reads `base 200 / quota 44` where `200 × 21 % = 42`. With a fixed 1,5-cent
    /// tolerance this gate rejected it and the ticket was left with no fiscal record; at 12 lines
    /// and 10 % that reached ~1 in 3 legitimate tickets (hub#1180).
    ///
    /// ⚠️ **`invoice` stopped emitting this shape** in ADR-0405 §Decisión 4 (v1.2.27, `invoice#65`):
    /// the key now closes once and the same ticket declares 42. What keeps this test necessary is
    /// the other side of the gate — the rows it must keep ACCEPTING: invoices sealed before that
    /// version and already chained into the AEAT fingerprint, and the verbatim F3, which copies a
    /// ticket's per-line figures by design. See [`line_rate_tolerance_cents`].
    #[tokio::test]
    async fn a_ticket_of_several_lines_at_the_same_rate_is_sealed() {
        let host = InvoiceHost::with_lines(
            invoice_row(
                "F2",
                "",
                200,
                44,
                244,
                r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":200,"quota":44}]"#,
            ),
            4,
        );
        ingest_invoice(&ingest_input(), &host)
            .await
            .expect("4 líneas de 0,50 € al 21 % son un tique legítimo: se sella");
    }

    /// El segundo techo (el que también sabe medir la tabla, migración `015`): una cuota que DOBLA
    /// lo que su tipo justifica no la explica ningún redondeo, por muchas líneas que declare la
    /// factura. Sin él, este motor sería más permisivo que el `CHECK` y el registro moriría un
    /// `INSERT` después con un error crudo de Postgres — lo que hub#1103 vino a evitar.
    #[tokio::test]
    async fn the_engine_is_never_laxer_than_the_table() {
        let host = InvoiceHost::with_lines(
            invoice_row(
                "F2",
                "",
                20,
                10,
                30,
                r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":20,"quota":10}]"#,
            ),
            // 20 líneas de 1 céntimo al 21 % redondean a cuota CERO, no a 10.
            20,
        );
        let err = error_of(ingest_invoice(&ingest_input(), &host).await);
        assert!(err.contains("quota_rate_mismatch"), "código esperado, llegó: {err}");
    }

    /// The twelve-cover table of the counterexample: 12 lines of 0,55 € at 10 % rounded per line —
    /// `round_half_up(5,5) = 6` each → `base 660 / quota 72`, where the rate justifies 66. As with
    /// the four-line case above, `invoice` no longer BUILDS this (ADR-0405 closes the key once and
    /// declares 66); the gate must still ACCEPT it for rows already chained and for the verbatim
    /// F3. See [`line_rate_tolerance_cents`].
    #[tokio::test]
    async fn a_twelve_line_table_at_ten_percent_is_sealed() {
        let host = InvoiceHost::with_lines(
            invoice_row(
                "F2",
                "",
                660,
                72,
                732,
                r#"[{"tax":"vat","regime":"01","class":"subject","rate":10.0,"base":660,"quota":72}]"#,
            ),
            12,
        );
        ingest_invoice(&ingest_input(), &host)
            .await
            .expect("una mesa de 12 líneas al 10 % se sella");
    }

    /// …y la tolerancia NO puede tragárselo todo: el caso del QA sigue muriendo aunque la factura
    /// declare muchas líneas. 99,99 € de cuota sobre 5,45 € al 21 % no lo explica ningún redondeo.
    #[tokio::test]
    async fn the_line_count_does_not_excuse_an_impossible_quota() {
        let host = InvoiceHost::with_lines(
            invoice_row(
                "F1",
                "87654321X",
                545,
                9999,
                10544,
                r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":545,"quota":9999}]"#,
            ),
            40,
        );
        let err = error_of(ingest_invoice(&ingest_input(), &host).await);
        assert!(err.contains("quota_rate_mismatch"), "código esperado, llegó: {err}");
    }

    /// La lectura del número de líneas viaja en la MISMA lectura acotada de la factura (ADR-0058),
    /// no en una segunda consulta: un listener que abre dos lecturas por venta es una lectura de
    /// más en cada tique.
    #[tokio::test]
    async fn the_line_count_travels_in_the_same_scoped_read() {
        let host = InvoiceHost::with_lines(
            invoice_row(
                "F2",
                "",
                200,
                44,
                244,
                r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":200,"quota":44}]"#,
            ),
            4,
        );
        ingest_invoice(&ingest_input(), &host).await.expect("se ingesta");
        let reads = host.reads.lock().unwrap();
        let invoice_reads: Vec<&String> =
            reads.iter().filter(|s| s.contains("invoice_invoice")).collect();
        assert_eq!(
            invoice_reads.len(),
            1,
            "una sola lectura de la factura, no dos: {invoice_reads:?}"
        );
        assert!(
            invoice_reads[0].contains("invoice_invoiceitem"),
            "el conteo de líneas va DENTRO de esa lectura: {}",
            invoice_reads[0]
        );
    }

    // ── hub#1104 · la degradación no puede ser muda ─────────────────────────────────────────

    /// Una F1 sin NIF de destinatario se sigue degradando a F2 —sin eso la AEAT responde 1189 con
    /// el número de cadena ya gastado— pero **deja constancia**: un evento propio, con severidad
    /// `warning`, que nombra el tipo declarado, el efectivo y el motivo.
    #[tokio::test]
    async fn a_silent_downgrade_leaves_a_trace() {
        let host = InvoiceHost::new(invoice_row(
            "F1",
            "",
            10000,
            2100,
            12100,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":10000,"quota":2100}]"#,
        ));
        let out = ingest_invoice(&ingest_input(), &host)
            .await
            .expect("la factura se ingesta: degradar es correcto, callarlo no");

        let insert = out
            .operations
            .iter()
            .find(|o| o.command == "verifactu._insert_record")
            .expect("se inserta el registro");
        assert_eq!(insert.params.get("invoice_type"), Some(&json!("F2")));

        let warn = event_of(&out, EVENT_TYPE_INVOICE_TYPE_DOWNGRADED)
            .expect("la degradación tiene que dejar su evento");
        assert_eq!(warn.params.get("severity"), Some(&json!("warning")));
        let details: Json = serde_json::from_str(
            warn.params.get("details").and_then(Json::as_str).unwrap_or("{}"),
        )
        .expect("los detalles son JSON");
        assert_eq!(details.get("declared"), Some(&json!("F1")));
        assert_eq!(details.get("effective"), Some(&json!("F2")));
        assert_eq!(details.get("reason"), Some(&json!(REASON_MISSING_RECIPIENT)));
    }

    /// No es solo F1→F2: una rectificativa CON destinatario degradada a R5 cambia de naturaleza
    /// fiscal (por diferencias → de simplificada) y también tiene que verse.
    #[tokio::test]
    async fn a_corrective_downgraded_to_r5_leaves_the_same_trace() {
        let host = InvoiceHost::new(invoice_row(
            "R1",
            "",
            -1000,
            -210,
            -1210,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":-1000,"quota":-210}]"#,
        ));
        let out = ingest_invoice(&ingest_input(), &host)
            .await
            .expect("la rectificativa se ingesta");
        let insert = out
            .operations
            .iter()
            .find(|o| o.command == "verifactu._insert_record")
            .expect("se inserta el registro");
        assert_eq!(insert.params.get("invoice_type"), Some(&json!("R5")));
        let warn = event_of(&out, EVENT_TYPE_INVOICE_TYPE_DOWNGRADED)
            .expect("la degradación R1→R5 tiene que dejar su evento");
        let details: Json = serde_json::from_str(
            warn.params.get("details").and_then(Json::as_str).unwrap_or("{}"),
        )
        .unwrap();
        assert_eq!(details.get("declared"), Some(&json!("R1")));
        assert_eq!(details.get("effective"), Some(&json!("R5")));
    }

    /// Con NIF no hay degradación, así que no hay evento que emitir: un aviso que sale siempre
    /// deja de ser un aviso.
    #[tokio::test]
    async fn an_invoice_with_a_recipient_is_not_downgraded_and_warns_about_nothing() {
        let host = InvoiceHost::new(invoice_row(
            "F1",
            "87654321X",
            10000,
            2100,
            12100,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":10000,"quota":2100}]"#,
        ));
        let out = ingest_invoice(&ingest_input(), &host).await.expect("se ingesta");
        let insert = out
            .operations
            .iter()
            .find(|o| o.command == "verifactu._insert_record")
            .expect("se inserta el registro");
        assert_eq!(insert.params.get("invoice_type"), Some(&json!("F1")));
        assert!(
            event_of(&out, EVENT_TYPE_INVOICE_TYPE_DOWNGRADED).is_none(),
            "sin degradación no hay aviso"
        );
    }

    /// 🔴 §15.8: una F2 no puede pasar de 3.000,00 € (+10,00 € de tolerancia). Degradar una F1 de
    /// 4.000 € a F2 fabrica un registro que la AEAT rechaza — con el número de cadena gastado. Se
    /// para ANTES de sellar.
    #[tokio::test]
    async fn a_downgrade_that_would_break_the_f2_ceiling_is_refused() {
        let host = InvoiceHost::new(invoice_row(
            "F1",
            "",
            400_000,
            84_000,
            484_000,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":400000,"quota":84000}]"#,
        ));
        let err = error_of(ingest_invoice(&ingest_input(), &host).await);
        assert!(err.contains("f2_limit_exceeded"), "código esperado, llegó: {err}");
    }

    /// Y justo por debajo del techo (3.010,00 €) se sella: el margen de la AEAT es parte de la
    /// regla, no un detalle.
    #[tokio::test]
    async fn a_downgrade_right_at_the_ceiling_is_sealed() {
        let host = InvoiceHost::new(invoice_row(
            "F1",
            "",
            301_000,
            0,
            301_000,
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":0.0,"base":301000,"quota":0}]"#,
        ));
        ingest_invoice(&ingest_input(), &host)
            .await
            .expect("3.010,00 € entra: es el techo inclusive");
    }

    // ── hub#1103 · lo que `chain.validate` AFIRMA ───────────────────────────────────────────

    /// «Cadena íntegra» se leyó en el informe de QA como veredicto sobre los importes de 27
    /// registros imposibles. El contrato criptográfico se mantiene —recalcular huellas y verificar
    /// el encadenado es lo correcto sobre filas ya inmutables—, pero el texto tiene que decir QUÉ
    /// verificó, y los detalles tienen que llevarlo en un campo que la UI pueda traducir.
    #[tokio::test]
    async fn the_chain_verdict_names_the_fingerprints_it_actually_checked() {
        let input = json!({ "payload": { "issuer_nif": NIF }, "context": context() });
        let out = validate_chain(&input, &GateHost).await.expect("valida");
        let event = out
            .operations
            .iter()
            .find(|o| o.command == "verifactu._insert_event")
            .expect("el veredicto se persiste como evento");
        let message = event
            .params
            .get("message")
            .and_then(Json::as_str)
            .unwrap_or_default()
            .to_string();
        assert!(
            message.to_lowercase().contains("huella"),
            "el veredicto tiene que nombrar la HUELLA, no afirmar sobre los importes: {message}"
        );
        let details: Json = serde_json::from_str(
            event.params.get("details").and_then(Json::as_str).unwrap_or("{}"),
        )
        .expect("los detalles son JSON");
        assert_eq!(
            details.get("scope"),
            Some(&json!(CHAIN_VALIDATION_SCOPE)),
            "la UI necesita el alcance en un campo estable para traducirlo (ADR-0055)"
        );
    }
}
