//! E2E of the fiscal breakdown (hub#296): what `invoice` WRITES is what the AEAT READS.
//!
//! Every link of the fiscal chain was unit-tested; the chain was not. The VeriFactu record builds
//! its `<Desglose>` from the invoice's `tax_breakdown`, and the unit tests of `aeat::desglose`
//! only prove that a HAND-WRITTEN breakdown with two rates becomes two `DetalleDesglose`. The half
//! nobody exercised is the other end: that the `invoice` module, running its real WASM handler
//! against a real Postgres, PRODUCES the breakdown that `aeat` consumes — and that the XML built
//! from it survives the pre-network validator.
//!
//! So this file runs the whole way through, once per case:
//!
//! ```text
//! taxes rules (real seed + real `taxes.rules.create`)
//!   → invoice.create / sales.complete_sale + outbox relay   (real WASM, real Postgres)
//!     → invoice_invoice.tax_breakdown                        (the inter-module contract)
//!       → VerifactuEngine::ingest_invoice                    (real read of the invoice row)
//!         → aeat::build_soap                                 (the `<Desglose>`)
//!           → xsd::validate_registro                         (what runs before the wire)
//! ```
//!
//! **The breakdown must be the ARRAY** (ADR-0186). Until invoice v1.2.1 shipped, this file also
//! accepted the legacy object (`{"21.00": {...}}`) because the hub's CI would otherwise have
//! depended on the order in which hub#293 and invoice#20 were merged. That order no longer exists,
//! and the tolerance was hiding the very thing the array was introduced for: with the object, an
//! EXEMPT service and a subject sale at 0 % shared the key `"0.00"` and melted into one line that
//! declared both wrong. Tolerance for the object stays only where there really is historical data:
//! the compat unit tests of `aeat::desglose`, whose invoices are already chained into the hash.
//!
//! **The `verifactu` MODULE is deliberately not installed.** It declares the `certificate`
//! capability, and that arms the second arm of the fiscal precondition gate (ADR-0203):
//! `invoice.create` would then demand a loaded business certificate, i.e. the test would stop
//! measuring the breakdown and start measuring certificate storage. The native engine is called
//! directly instead, over a host that reads the invoice row from the SAME Postgres — which is
//! exactly what the module does when the `invoice.created` event reaches it.

use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::native::{NativeHandler, NativeHost};
use erplora_runtime::{RequestContext, Runtime};
use erplora_verifactu::{aeat, xsd, VerifactuEngine};
use serde_json::{json, Value};

/// Timestamp handed to the record builder: fixed, with an explicit offset, because it enters the
/// AEAT fingerprint and must not depend on when the suite runs.
const GEN_TS: &str = "2026-08-07T10:00:00+02:00";

fn params(v: Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

/// Same resolution as the guard (`ERPLORA_MODULES_DIR`, else the monorepo-relative path). Building
/// the path by hand here would diverge from [`erplora_runtime::require_modules_workspace`] and
/// bring back the exact failure mode of hub#253: the guard says "run" while every `mdir(..)` points
/// at a directory that does not exist, so the test skips itself and still reports `ok`.
fn mdir(n: &str) -> PathBuf {
    erplora_runtime::modules_root().join(n)
}

/// The context shares the runtime's `hub_id` (`DEV_HUB_ID`, a UUID as ADR-0202 requires for
/// `NumeroInstalacion`) so that `set_settings` and the dispatcher's enricher read the SAME
/// `hub_settings` row — needed since the fiscal precondition gate (hub#328, ADR-0203).
fn admin() -> RequestContext {
    RequestContext::new(erplora_runtime::DEV_HUB_ID, "u1", ["*".to_string()])
}

/// The breakdown is computed by invoice's WASM handler; without it there is nothing to measure.
fn handlers_built() -> bool {
    mdir("invoice").join("dist/handler.wasm").exists()
        && mdir("sales").join("dist/handler.wasm").exists()
}

/// Runtime with the real fiscal chain: `invoice` needs `sales` (the `sales.get` read of
/// `create_from_sale`, hub#108) and `taxes` (the rule catalog), and `sales` needs
/// `inventory`+`customers`. Installing `taxes` on an ES hub also plants the Spain VAT baseline —
/// including the VAT-EXEMPT categories — which is what these cases resolve against.
async fn fiscal_chain() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.ensure_system_tables().await.expect("ensure_system_tables");
    for m in ["taxes", "inventory", "customers", "sales", "invoice"] {
        rt.install_from_dir(&mdir(m))
            .await
            .unwrap_or_else(|e| panic!("install {m}: {e}"));
    }
    // Business identity (ADR-0061) — without it `invoice.*` is rejected by the fiscal gate; it is
    // also the `IDEmisorFactura`/`ObligadoEmision` of the record. Country ES is what makes the
    // seeded rules resolve at all (ADR-0085: no country → no rule → the browser picks the VAT).
    let mut up = serde_json::Map::new();
    up.insert("business_tax_id".into(), json!("B12345674"));
    up.insert("business_legal_name".into(), json!("Bar Paco SL"));
    up.insert("country_code".into(), json!("ES"));
    rt.set_settings(&up, "u1").await.expect("set business identity");
    rt
}

// ── The bridge invoice → VeriFactu record → XML ────────────────────────────────────────────────

/// `NativeHost` that answers the engine's ONE bounded read (`invoice_invoice`) from the real
/// Postgres, and nothing else: the `verifactu` module is not installed, so its config singleton
/// and its chain anchor have no tables. Empty config = no certificate → no inline transmission;
/// empty anchor = first link of the chain. Neither touches the breakdown, which is the subsystem
/// under test.
struct InvoiceHost<'a> {
    rt: &'a Runtime,
}

#[async_trait::async_trait]
impl NativeHost for InvoiceHost<'_> {
    async fn read(&self, sql: &str, p: &Params) -> erplora_runtime::Result<Vec<Value>> {
        if sql.contains("invoice_invoice") {
            let res = self.rt.db().query(sql, p).await.expect("read invoice row");
            return Ok(res.rows);
        }
        Ok(Vec::new())
    }
}

/// Runs the invoice through the real ingest and returns the SOAP that would go on the wire, after
/// the same pre-network validation the transmission does (`xsd::validate_registro`) — an XML that
/// does not validate has already burnt its chain number when the AEAT answers 4102.
async fn aeat_xml(rt: &Runtime, invoice_id: &str) -> String {
    let host = InvoiceHost { rt };
    let input = json!({
        "payload": { "invoice_id": invoice_id },
        "context": {
            "hub_id": erplora_runtime::DEV_HUB_ID,
            "current_user_id": "u1",
            "now": GEN_TS,
            "new_ids": ["rec-0", "rec-1", "rec-2", "rec-3", "rec-4", "rec-5"],
        }
    });
    let out = VerifactuEngine
        .call("ingest_invoice", &input, &host)
        .await
        .expect("ingest_invoice");
    let insert = out
        .operations
        .iter()
        .find(|o| o.command == "verifactu._insert_record")
        .expect("an issued invoice must produce a VeriFactu record");
    // The record row IS the params of that insert — the same shape the transmission reads back.
    let record = Value::Object(insert.params.clone());
    // Producer facts as the control plane serves them (hub#323): without them there is no
    // `SistemaInformatico`, so there is no envelope to validate.
    let config = json!({
        "producer_facts": {
            "NombreRazon": "ERPLORA CLOUD SL",
            "NIF": "B27593136",
            "NombreSistemaInformatico": "ERPlora Hub",
            "IdSistemaInformatico": "EC",
            "TipoUsoPosibleSoloVerifactu": "S",
            "TipoUsoPosibleMultiOT": "S",
            "IndicadorMultiplesOT": "N",
        }
    });
    let xml = aeat::build_soap(&record, &config, None, erplora_runtime::DEV_HUB_ID)
        .expect("el registro se puede declarar");
    if let Err(e) = xsd::validate_registro(&xml) {
        panic!("the pre-network validator rejected the record: {e}\n{xml}");
    }
    xml
}

// ── Reading the breakdown and the XML ──────────────────────────────────────────────────────────

/// One entry of the `tax_breakdown`, already required to be the ARRAY generation.
#[derive(Debug, Clone)]
struct Entry {
    tax: String,
    regime: String,
    class: String,
    exempt_reason: String,
    rate: f64,
    base: i64,
    quota: i64,
}

fn field(v: &Value, k: &str) -> String {
    v.get(k).and_then(Value::as_str).unwrap_or_default().to_string()
}

/// Parses `invoice_invoice.tax_breakdown`. **Array only**: the object generation is history that
/// only `aeat::desglose` still has to read (already-chained invoices), never something the module
/// may produce today.
fn breakdown_of(inv: &Value) -> Vec<Entry> {
    let raw = inv["tax_breakdown"].as_str().expect("tax_breakdown is a string column");
    let parsed: Value = serde_json::from_str(raw).expect("tax_breakdown is JSON");
    let entries = match &parsed {
        Value::Array(a) => a.clone(),
        other => panic!(
            "`tax_breakdown` must be the ARRAY of full fiscal keys (ADR-0186); got {other}"
        ),
    };
    entries
        .iter()
        .map(|e| Entry {
            tax: field(e, "tax"),
            regime: field(e, "regime"),
            class: field(e, "class"),
            exempt_reason: field(e, "exempt_reason"),
            rate: e["rate"].as_f64().unwrap_or_else(|| panic!("entry without rate: {e}")),
            base: e["base"].as_i64().unwrap_or_else(|| panic!("base must be integer cents: {e}")),
            quota: e["quota"].as_i64().unwrap_or_else(|| panic!("quota must be integer cents: {e}")),
        })
        .collect()
}

/// The entry declared at `rate`, or a failure naming the whole breakdown.
fn at_rate(entries: &[Entry], rate: f64) -> &Entry {
    entries
        .iter()
        .find(|e| (e.rate - rate).abs() < 0.01)
        .unwrap_or_else(|| panic!("no entry at {rate}%: {entries:#?}"))
}

/// The inner XML of every `<sum1:DetalleDesglose>`, in document order.
fn detalles(xml: &str) -> Vec<String> {
    xml.split("<sum1:DetalleDesglose>")
        .skip(1)
        .map(|chunk| {
            chunk
                .split("</sum1:DetalleDesglose>")
                .next()
                .expect("closing DetalleDesglose")
                .to_string()
        })
        .collect()
}

/// Value of `<sum1:{tag}>` inside a chunk, or `None` when the element is absent.
fn tag(chunk: &str, name: &str) -> Option<String> {
    let open = format!("<sum1:{name}>");
    let close = format!("</sum1:{name}>");
    let rest = chunk.split(&open).nth(1)?;
    Some(rest.split(&close).next()?.to_string())
}

/// AEAT amounts travel as euros with 2 decimals; the whole system reasons in cents (ADR-0123).
fn cents(euros: &str) -> i64 {
    (euros.parse::<f64>().unwrap_or_else(|_| panic!("not an AEAT amount: {euros}")) * 100.0).round()
        as i64
}

/// The cross-check the AEAT itself runs over a `RegistroAlta`: `CuotaTotal` is the sum of the
/// `CuotaRepercutida` of the breakdown, and `ImporteTotal` is that plus every declared base. It is
/// the one invariant that catches a breakdown which is internally plausible but does not add up to
/// the invoice — a cent lost in the split, an aggregated line, a base counted twice.
fn assert_xml_reconciles(xml: &str) {
    let blocks = detalles(xml);
    let base_sum: i64 = blocks
        .iter()
        .map(|b| cents(&tag(b, "BaseImponibleOimporteNoSujeto").expect("every detail has a base")))
        .sum();
    let quota_sum: i64 = blocks
        .iter()
        .map(|b| tag(b, "CuotaRepercutida").map(|q| cents(&q)).unwrap_or(0))
        .sum();
    let cuota_total = cents(&tag(xml, "CuotaTotal").expect("CuotaTotal"));
    let importe_total = cents(&tag(xml, "ImporteTotal").expect("ImporteTotal"));
    assert_eq!(
        quota_sum, cuota_total,
        "CuotaTotal must be the sum of the breakdown's CuotaRepercutida\n{xml}"
    );
    assert_eq!(
        base_sum + quota_sum,
        importe_total,
        "ImporteTotal must be the declared bases plus their quotas\n{xml}"
    );
}

// ── Driving the modules ────────────────────────────────────────────────────────────────────────

/// Issues a simplified ticket (F2, series TICKET) with the given lines and returns its row.
/// `items` are `(description, quantity_units, unit_price_cents, tax_rate_pct, tax_category_key)`.
async fn issue_ticket(rt: &Runtime, items: &[(&str, i64, i64, f64, &str)]) -> Value {
    let ctx = admin();
    let lines: Vec<Value> = items
        .iter()
        .map(|(desc, qty, price, rate, cat)| {
            json!({
                "description": desc,
                // Fixed point, scale 10^6 (ADR-0147).
                "quantity": qty * 1_000_000,
                "unit_price": price,
                "tax_rate": rate,
                "tax_category_key": cat,
            })
        })
        .collect();
    rt.execute_command(
        "invoice.create",
        &params(json!({ "series_code": "TICKET", "customer_name": "Cliente", "items": lines })),
        &ctx,
    )
    .await
    .expect("invoice.create");

    let list = rt.execute_query("invoice.list", &Params::new(), &ctx).await.unwrap();
    let id = list.last().expect("one invoice")["id"].clone();
    let got = rt
        .execute_query("invoice.get", &params(json!({ "invoice_id": id })), &ctx)
        .await
        .expect("invoice.get");
    got.into_iter().next().expect("invoice row")
}

// ── Cases ──────────────────────────────────────────────────────────────────────────────────────

/// THE business case: a beer at 21 % and a tapa at 10 % on the same ticket. Before ADR-0186 the
/// AEAT was told a single EFFECTIVE rate (17,33 %) that does not exist in the Spanish tax system.
#[tokio::test]
async fn a_mixed_ticket_declares_one_breakdown_line_per_real_rate() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    if !handlers_built() {
        eprintln!("SKIP: module handler.wasm missing");
        return;
    }
    let rt = fiscal_chain().await;
    let inv = issue_ticket(
        &rt,
        &[
            ("Caña", 1, 1000, 21.0, "restaurant.alcohol"),
            ("Tapa", 1, 500, 10.0, "restaurant.food"),
        ],
    )
    .await;

    let entries = breakdown_of(&inv);
    assert_eq!(entries.len(), 2, "one entry per REAL rate, not one aggregate: {entries:#?}");
    assert!(
        !entries.iter().any(|e| (e.rate - 17.33).abs() < 0.01),
        "the effective rate is not a Spanish rate and must never be declared: {entries:#?}"
    );
    // The full fiscal key, not just the rate: this is what the array generation buys (ADR-0186).
    for e in &entries {
        assert_eq!(e.tax, "vat", "domestic sale, VAT: {e:?}");
        assert_eq!(e.regime, "01", "general regime: {e:?}");
        assert_eq!(e.class, "subject", "subject and not exempt: {e:?}");
    }
    assert_eq!((at_rate(&entries, 21.0).base, at_rate(&entries, 21.0).quota), (1000, 210));
    assert_eq!((at_rate(&entries, 10.0).base, at_rate(&entries, 10.0).quota), (500, 50));
    assert_eq!(inv["base_amount"].as_i64().unwrap(), 1500);
    assert_eq!(inv["tax_amount"].as_i64().unwrap(), 260);

    let xml = aeat_xml(&rt, inv["id"].as_str().unwrap()).await;
    let blocks = detalles(&xml);
    assert_eq!(blocks.len(), 2, "two DetalleDesglose: {xml}");
    assert!(!xml.contains("17.33"), "the effective rate must not reach the AEAT: {xml}");
    // Stable order: rate descending inside the same fiscal key. The XML cannot depend on the order
    // in which the producer built the array (the object generation had no order at all).
    assert_eq!(tag(&blocks[0], "TipoImpositivo").as_deref(), Some("21.00"), "{xml}");
    assert_eq!(tag(&blocks[1], "TipoImpositivo").as_deref(), Some("10.00"), "{xml}");
    // Rate, base and quota belong to the SAME detail — a breakdown that pairs them wrong balances
    // just as well in total, and declares two rates that were never charged.
    assert_eq!(tag(&blocks[0], "BaseImponibleOimporteNoSujeto").as_deref(), Some("10.00"), "{xml}");
    assert_eq!(tag(&blocks[0], "CuotaRepercutida").as_deref(), Some("2.10"), "{xml}");
    assert_eq!(tag(&blocks[1], "BaseImponibleOimporteNoSujeto").as_deref(), Some("5.00"), "{xml}");
    assert_eq!(tag(&blocks[1], "CuotaRepercutida").as_deref(), Some("0.50"), "{xml}");
    for b in &blocks {
        // Domestic VAT under the general regime — the OTHER axis of the breakdown (ADR-0186).
        // `Impuesto 03`/`02` would declare IGIC/IPSI, and `ClaveRegimen 08` means the exact
        // opposite of what it looks like: "this operation does NOT carry my tax".
        assert_eq!(tag(b, "Impuesto").as_deref(), Some("01"), "{xml}");
        assert_eq!(tag(b, "ClaveRegimen").as_deref(), Some("01"), "{xml}");
        assert_eq!(tag(b, "CalificacionOperacion").as_deref(), Some("S1"), "{xml}");
        // A bar under the ordinary regime charges NO equivalence surcharge, and the two surcharge
        // elements are optional — an empty pair is not harmless: §15.3 accepts a 0 % surcharge, so
        // the pre-network validator lets it through and the AEAT is told this business is on the
        // surcharge regime. Absent means absent.
        assert_eq!(tag(b, "TipoRecargoEquivalencia"), None, "{xml}");
        assert_eq!(tag(b, "CuotaRecargoEquivalencia"), None, "{xml}");
    }
    assert_eq!(tag(&xml, "CuotaTotal").as_deref(), Some("2.60"), "{xml}");
    assert_eq!(tag(&xml, "ImporteTotal").as_deref(), Some("17.60"), "{xml}");
    assert_xml_reconciles(&xml);
}

/// Two lines under the SAME fiscal key are ONE `DetalleDesglose`. `restaurant.alcohol` and
/// `product.generic` are different categories, but in Spain both resolve to VAT / general regime /
/// subject / 21 %: the AEAT wants the operation grouped by the key it declares, not by the
/// catalogue the shop happens to use. The rest of the file would still pass if the aggregation
/// broke and every line got its own detail — this is the case that will not.
#[tokio::test]
async fn two_lines_under_the_same_fiscal_key_collapse_into_one_breakdown_line() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    if !handlers_built() {
        eprintln!("SKIP: module handler.wasm missing");
        return;
    }
    let rt = fiscal_chain().await;
    let inv = issue_ticket(
        &rt,
        &[
            ("Copa de vino", 1, 400, 21.0, "restaurant.alcohol"),
            ("Mechero", 1, 100, 21.0, "product.generic"),
            ("Bocadillo", 1, 500, 10.0, "restaurant.food"),
        ],
    )
    .await;

    let entries = breakdown_of(&inv);
    assert_eq!(
        entries.len(),
        2,
        "two rates → two entries, however many lines feed them: {entries:#?}"
    );
    let general = at_rate(&entries, 21.0);
    assert_eq!((general.base, general.quota), (500, 105), "the 21 % lines add up: {entries:#?}");
    assert_eq!((at_rate(&entries, 10.0).base, at_rate(&entries, 10.0).quota), (500, 50));

    let xml = aeat_xml(&rt, inv["id"].as_str().unwrap()).await;
    assert_eq!(detalles(&xml).len(), 2, "one detail per fiscal key, not per line: {xml}");
    assert_xml_reconciles(&xml);
}

/// A VAT-EXEMPT service (healthcare, art. 20.Uno.3 — seeded as `service.health` with cause `E1`)
/// must reach the XML as `OperacionExenta`, which in the XSD is an ALTERNATIVE to
/// `CalificacionOperacion` (`<choice>`), not a rate of 0 %. §15.5 also forbids informing
/// `TipoImpositivo`/`CuotaRepercutida` on that line. Declaring it as "subject at 0 %" is a
/// different fact about the same money and is what the hub did before ADR-0186.
#[tokio::test]
async fn an_exempt_service_reaches_the_xml_as_operacion_exenta_not_as_subject_at_zero() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    if !handlers_built() {
        eprintln!("SKIP: module handler.wasm missing");
        return;
    }
    let rt = fiscal_chain().await;
    let inv = issue_ticket(
        &rt,
        &[
            ("Tratamiento capilar médico", 1, 4000, 0.0, "service.health"),
            ("Corte de pelo", 1, 2000, 21.0, "service.generic"),
        ],
    )
    .await;

    let entries = breakdown_of(&inv);
    assert_eq!(entries.len(), 2, "exempt and subject never share an entry: {entries:#?}");
    let exempt = entries
        .iter()
        .find(|e| e.class == "exempt")
        .unwrap_or_else(|| panic!("the healthcare line must be EXEMPT, not subject: {entries:#?}"));
    assert_eq!(exempt.exempt_reason, "E1", "cause in the AEAT vocabulary: {exempt:?}");
    assert_eq!((exempt.base, exempt.quota), (4000, 0), "an exempt line charges nothing");
    let subject = at_rate(&entries, 21.0);
    assert_eq!(subject.class, "subject");
    assert_eq!((subject.base, subject.quota), (2000, 420));
    // The exempt base is base, not quota: it must be in the invoice total and out of the VAT.
    assert_eq!(inv["base_amount"].as_i64().unwrap(), 6000);
    assert_eq!(inv["tax_amount"].as_i64().unwrap(), 420);

    let xml = aeat_xml(&rt, inv["id"].as_str().unwrap()).await;
    let blocks = detalles(&xml);
    assert_eq!(blocks.len(), 2, "{xml}");
    let exempt_block = blocks
        .iter()
        .find(|b| b.contains("<sum1:OperacionExenta>"))
        .unwrap_or_else(|| panic!("no OperacionExenta in the breakdown: {xml}"));
    assert_eq!(tag(exempt_block, "OperacionExenta").as_deref(), Some("E1"), "{xml}");
    assert_eq!(
        tag(exempt_block, "CalificacionOperacion"),
        None,
        "the XSD is a <choice>: an exempt line carries no CalificacionOperacion — {xml}"
    );
    assert_eq!(
        tag(exempt_block, "TipoImpositivo"),
        None,
        "§15.5: an exempt line informs no rate — 'subject at 0 %' is a different declaration — {xml}"
    );
    assert_eq!(tag(exempt_block, "CuotaRepercutida"), None, "§15.5: nor a quota — {xml}");
    assert_eq!(
        tag(exempt_block, "BaseImponibleOimporteNoSujeto").as_deref(),
        Some("40.00"),
        "the amount of the operation is the only mandatory element — {xml}"
    );
    let subject_block = blocks
        .iter()
        .find(|b| b.contains("<sum1:CalificacionOperacion>"))
        .unwrap_or_else(|| panic!("no subject line: {xml}"));
    assert_eq!(tag(subject_block, "CalificacionOperacion").as_deref(), Some("S1"), "{xml}");
    assert_eq!(tag(subject_block, "TipoImpositivo").as_deref(), Some("21.00"), "{xml}");
    assert_xml_reconciles(&xml);
}

/// The collision the array generation was introduced for (ADR-0186 §1): an EXEMPT service and a
/// sale SUBJECT at 0 % are two different declarations that the object format could not tell apart
/// — both hashed to the key `"0.00"` and melted into one line that declared both wrong. It is
/// literally a salon ticket with a healthcare treatment on it.
#[tokio::test]
async fn an_exempt_service_and_a_zero_rated_sale_never_share_a_breakdown_line() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    if !handlers_built() {
        eprintln!("SKIP: module handler.wasm missing");
        return;
    }
    let rt = fiscal_chain().await;
    let ctx = admin();
    // A zero-rated but SUBJECT category, created the way a hub creates it (Settings → Taxes).
    rt.execute_command(
        "taxes.categories.create",
        &params(json!({ "key": "product.zero_rated", "name": "Product — zero rated" })),
        &ctx,
    )
    .await
    .expect("taxes.categories.create");
    rt.execute_command(
        "taxes.rules.create",
        &params(json!({
            "country_code": "ES",
            "tax_category_key": "product.zero_rated",
            "rate_pct": 0,
            "tax_type": "vat",
            "operation_class": "subject",
        })),
        &ctx,
    )
    .await
    .expect("taxes.rules.create");

    let inv = issue_ticket(
        &rt,
        &[
            ("Consulta médica", 1, 3000, 0.0, "service.health"),
            ("Mascarilla sanitaria", 1, 1000, 0.0, "product.zero_rated"),
        ],
    )
    .await;

    let entries = breakdown_of(&inv);
    assert_eq!(
        entries.len(),
        2,
        "exempt and subject-at-0 % are two declarations, not one line: {entries:#?}"
    );
    let exempt = entries.iter().find(|e| e.class == "exempt").expect("the exempt entry");
    let zero = entries.iter().find(|e| e.class == "subject").expect("the subject-at-0 entry");
    assert_eq!((exempt.base, exempt.quota), (3000, 0));
    assert_eq!((zero.base, zero.quota, zero.rate), (1000, 0, 0.0));

    let xml = aeat_xml(&rt, inv["id"].as_str().unwrap()).await;
    let blocks = detalles(&xml);
    assert_eq!(blocks.len(), 2, "the two must not collapse into one detail: {xml}");
    let exempt_block = blocks.iter().find(|b| b.contains("<sum1:OperacionExenta>")).expect("exempt");
    let zero_block =
        blocks.iter().find(|b| b.contains("<sum1:CalificacionOperacion>")).expect("subject");
    assert_eq!(tag(exempt_block, "OperacionExenta").as_deref(), Some("E1"), "{xml}");
    assert_eq!(tag(exempt_block, "BaseImponibleOimporteNoSujeto").as_deref(), Some("30.00"));
    // §15.4: S1 at 0 % DOES inform rate and quota, explicitly zero. That is precisely the
    // difference with the exempt line above, and the reason they cannot share a detail.
    assert_eq!(tag(zero_block, "CalificacionOperacion").as_deref(), Some("S1"), "{xml}");
    assert_eq!(tag(zero_block, "TipoImpositivo").as_deref(), Some("0.00"), "{xml}");
    assert_eq!(tag(zero_block, "CuotaRepercutida").as_deref(), Some("0.00"), "{xml}");
    assert_eq!(tag(zero_block, "BaseImponibleOimporteNoSujeto").as_deref(), Some("10.00"));
    assert_xml_reconciles(&xml);
}

/// VAT is computed and rounded PER LINE (ADR-0187), HALF_UP (ADR-0123), and only then aggregated
/// into the breakdown entry. Two coffees at 2,50 € make it visible: 52,5 cents each → 53 + 53 =
/// **1,06 €**, while rounding the aggregated base (5,00 € × 21 % = 105,0) would give 1,05 €. One
/// cent, and it is the cent that has to match the till and `CuotaTotal`.
#[tokio::test]
async fn the_quota_is_rounded_per_line_before_it_is_aggregated() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    if !handlers_built() {
        eprintln!("SKIP: module handler.wasm missing");
        return;
    }
    let rt = fiscal_chain().await;
    let inv = issue_ticket(
        &rt,
        &[
            ("Café solo", 1, 250, 21.0, "product.generic"),
            ("Café con leche", 1, 250, 21.0, "product.generic"),
        ],
    )
    .await;

    let entries = breakdown_of(&inv);
    assert_eq!(entries.len(), 1, "same fiscal key → one entry: {entries:#?}");
    assert_eq!(
        (entries[0].base, entries[0].quota),
        (500, 106),
        "53 + 53, not round(500 × 21 %) = 105: the quota is rounded per LINE (ADR-0187)"
    );
    assert_eq!(inv["tax_amount"].as_i64().unwrap(), 106);

    let xml = aeat_xml(&rt, inv["id"].as_str().unwrap()).await;
    let block = &detalles(&xml)[0];
    assert_eq!(tag(block, "CuotaRepercutida").as_deref(), Some("1.06"), "{xml}");
    assert_eq!(tag(&xml, "CuotaTotal").as_deref(), Some("1.06"), "{xml}");
    assert_eq!(tag(&xml, "ImporteTotal").as_deref(), Some("6.06"), "{xml}");
    assert_xml_reconciles(&xml);
}

/// A whole-sale discount over lines at DIFFERENT rates. The POS prices are VAT-INCLUDED, `sales`
/// prorates the discount to each line and extracts its base there, and the auto-F2 that
/// `invoice.create_from_sale` issues off the outbox must respect that split — never re-apply VAT
/// on the gross. What the AEAT is told has to be what the customer actually paid, to the cent:
/// 11,00 € + 5,00 € with 10 % off is 14,40 € in the till, so `ImporteTotal` is 14,40 € and the two
/// bases and quotas add up to it.
#[tokio::test]
async fn a_sale_wide_discount_is_spread_across_rates_and_the_breakdown_still_reconciles() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    if !handlers_built() {
        eprintln!("SKIP: module handler.wasm missing");
        return;
    }
    let rt = fiscal_chain().await;
    let ctx = admin();
    // The hub's payment-method catalogue is the only authority on the method (sales): read the
    // seeded cash method instead of naming an id the browser could have invented.
    let methods = rt
        .execute_query("sales.payment_methods", &Params::new(), &ctx)
        .await
        .expect("sales.payment_methods");
    let cash = methods
        .iter()
        .find(|m| m["type"] == json!("cash"))
        .expect("the hub seeds a cash payment method")["id"]
        .clone();
    rt.execute_command(
        "sales.complete_sale",
        &params(json!({
            "customer_name": "Cliente",
            // Key of the payment ATTEMPT (sales#20), mandatory since sales v2.13.
            "idempotency_key": "desglose-e2e-discount",
            "payment_method_id": cash,
            "tax_included": true,
            "discount_percent": 10.0,
            "items": [
                { "product_name": "Menú del día", "price": 1100, "quantity": 1_000_000,
                  "tax_rate": 10.0, "tax_category_key": "restaurant.food" },
                { "product_name": "Copa de vino", "price": 500, "quantity": 1_000_000,
                  "tax_rate": 21.0, "tax_category_key": "restaurant.alcohol" }
            ]
        })),
        &ctx,
    )
    .await
    .expect("sales.complete_sale");
    // Asynchronous delivery: the relay turns sale.completed into invoice.create_from_sale.
    rt.drain_outbox().await.expect("drain_outbox");

    let list = rt.execute_query("invoice.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(list.len(), 1, "the sale must auto-issue exactly one F2");
    let inv = rt
        .execute_query("invoice.get", &params(json!({ "invoice_id": list[0]["id"] })), &ctx)
        .await
        .expect("invoice.get")
        .remove(0);

    let entries = breakdown_of(&inv);
    assert_eq!(entries.len(), 2, "the discount must not invent or merge rates: {entries:#?}");
    // 11,00 € − 10 % = 9,90 € VAT-included at 10 % → base 9,00 € + quota 0,90 €.
    assert_eq!((at_rate(&entries, 10.0).base, at_rate(&entries, 10.0).quota), (900, 90));
    // 5,00 € − 10 % = 4,50 € VAT-included at 21 % → base 3,72 € + quota 0,78 €.
    assert_eq!((at_rate(&entries, 21.0).base, at_rate(&entries, 21.0).quota), (372, 78));
    assert_eq!(inv["base_amount"].as_i64().unwrap(), 1272);
    assert_eq!(inv["tax_amount"].as_i64().unwrap(), 168);
    assert_eq!(
        inv["total_amount"].as_i64().unwrap(),
        1440,
        "what the AEAT is told is what the till took"
    );

    let xml = aeat_xml(&rt, inv["id"].as_str().unwrap()).await;
    assert_eq!(detalles(&xml).len(), 2, "{xml}");
    assert_eq!(tag(&xml, "CuotaTotal").as_deref(), Some("1.68"), "{xml}");
    assert_eq!(tag(&xml, "ImporteTotal").as_deref(), Some("14.40"), "{xml}");
    assert_xml_reconciles(&xml);
}
