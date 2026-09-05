//! E2E de hub#1391 — la puerta MANUAL y el motor tienen que estar de acuerdo, y viven en REPOS
//! DISTINTOS.
//!
//! `verifactu.records.create` es la puerta manual (recuperación de numeración, el alta que el
//! listener no cazó, integraciones y el asistente, que tiene el command con su bloque `ai`). Su
//! payload se valida contra `schemas/record_create.json` —del módulo `ERPlora/verifactu`— ANTES de
//! que el motor nativo —de ESTE repo— lo vea (`registry.rs`, `Validator::validate`), y el esquema
//! dice `additionalProperties: false`. Un campo que el esquema no declara no llega vacío: la
//! llamada entera se RECHAZA.
//!
//! **Por qué este fichero existe y no bastan los tests de cada mitad.** Justo esa costura es la
//! que se abrió: verifactu#58 dejó pasar `tax_breakdown` por esta puerta y el motor siguió fijando
//! `line_count: None`, así que juzgaba el desglose como si la factura tuviera UNA línea. El tique
//! canónico —4 líneas de 0,50 € al 21 %, `round_half_up(10,5) = 11` cuatro veces, agregado
//! `base 200 / cuota 44` donde el tipo justifica 42— moría con `quota_rate_mismatch` sobre una
//! desviación de 2 céntimos, mientras el `CHECK` de la migración `015` del propio módulo acepta esa
//! misma fila. El motor era MÁS ESTRICTO que la tabla en el caso que la tabla se molestó en dejar
//! pasar, y solo por esta puerta.
//!
//! Las dos mitades tienen ya su prueba, y ninguna caza el desacuerdo: los tests de
//! `crates/plugins/verifactu` seguirían verdes si el esquema perdiera el campo, y la batería
//! `tests/record_create_payload.contract.test.py` del módulo seguiría verde si el motor dejara de
//! leerlo. Lo que las ata es este recorrido: módulos REALES instalados desde disco, dispatcher
//! REAL (`Runtime::execute_command`, que valida el payload) y Postgres REAL, donde además el
//! registro tiene que sobrevivir a los `CHECK` de la tabla.

use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::{json, Value as Json};

const HUB: &str = "5b1e8c3d-7a24-4f96-8d0b-2c6e9a4f1b73";

/// El desglose AGREGADO de esas 4 líneas: una sola entrada por clave fiscal, con la cuota que sale
/// de redondear por línea y sumar. Es exactamente la forma que `invoice` selló hasta ADR-0405 y la
/// que una F3 verbatim copia hoy.
const AGGREGATED_BREAKDOWN: &str =
    r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":200,"quota":44}]"#;

fn modules_root() -> PathBuf {
    erplora_runtime::e2e_support::modules_root()
}

/// Misma cadena e instalación que `verifactu_chain_survives_certificate_rotation_e2e`: `verifactu`
/// depende de `invoice`, que necesita `sales` (y éste `inventory`) y `taxes`.
async fn runtime_with_verifactu() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables()
        .await
        .expect("ensure_system_tables");
    rt.register_native(
        "verifactu",
        std::sync::Arc::new(erplora_verifactu::VerifactuEngine),
    );
    for m in ["taxes", "inventory", "sales", "invoice", "verifactu"] {
        rt.install_from_dir(&modules_root().join(m))
            .await
            .unwrap_or_else(|e| panic!("install {m}: {e}"));
    }
    // El consentimiento del dueño para la capacidad `certificate` que declara `verifactu`: sin él
    // todo command del módulo se rechaza con `CapabilityDenied`, que es OTRA puerta (hub#1119).
    rt.set_module_capability("verifactu", "certificate", true, "hub_user:1")
        .await
        .expect("the owner grants the certificate capability");
    rt
}

fn admin() -> RequestContext {
    RequestContext::new(
        HUB,
        "u1",
        [
            "verifactu.manage_verifactu".to_string(),
            "verifactu.view_verifactu".to_string(),
        ],
    )
}

/// El alta del tique de 4 líneas, con el `line_count` que se le pase (o sin él).
fn alta(invoice_number: &str, line_count: Option<i64>) -> Params {
    let mut p = json!({
        "record_type": "alta",
        "issuer_nif": "B27593136",
        "issuer_name": "ERPLORA CLOUD SL",
        "invoice_number": invoice_number,
        "invoice_date": "2026-08-06",
        "invoice_type": "F2",
        "base_amount": 200,
        "tax_rate": 21.0,
        "tax_amount": 44,
        "total_amount": 244,
        "tax_breakdown": AGGREGATED_BREAKDOWN,
    })
    .as_object()
    .cloned()
    .expect("payload is a JSON object");
    if let Some(lines) = line_count {
        p.insert("line_count".into(), json!(lines));
    }
    p
}

/// Lo que quedó en la tabla, leído de la tabla y no de lo que `execute_command` devolvió.
async fn stored(rt: &Runtime, invoice_number: &str) -> Vec<Json> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    p.insert("invoice_number".into(), json!(invoice_number));
    rt.db()
        .query(
            "SELECT sequence_number, base_amount, tax_amount, tax_breakdown \
             FROM verifactu_record WHERE hub_id = :hub_id AND invoice_number = :invoice_number",
            &p,
        )
        .await
        .expect("query verifactu_record")
        .rows
}

/// 🟢 El esquema del módulo declara `line_count`, el motor de este repo lo lee, y el registro
/// aterriza en una tabla cuyos `CHECK` lo aceptan. Si cualquiera de las tres mitades se mueve, esto
/// se pone rojo.
#[tokio::test]
async fn the_manual_door_seals_a_four_line_ticket_when_it_declares_its_line_count_hub1391() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let rt = runtime_with_verifactu().await;
    rt.execute_command(
        "verifactu.records.create",
        &alta("TICKET-2026-000001", Some(4)),
        &admin(),
    )
    .await
    .expect("un tique de 4 líneas de 0,50 € al 21 % es legítimo también por la puerta manual");

    let rows = stored(&rt, "TICKET-2026-000001").await;
    assert_eq!(
        rows.len(),
        1,
        "el registro tiene que haber aterrizado: {rows:?}"
    );
    assert_eq!(
        rows[0]["tax_amount"],
        json!(44),
        "la cuota se sella tal cual: {rows:?}"
    );
    assert_eq!(
        rows[0]["tax_breakdown"].as_str(),
        Some(AGGREGATED_BREAKDOWN),
        "y el desglose viaja verbatim: {rows:?}"
    );
}

/// …y sin declararlo se sigue juzgando como una factura de UNA línea: quien no dice cuántas líneas
/// agrega no compra tolerancia. Es el lado seguro, y es lo que prueba que el `line_count` de arriba
/// es lo que cambia el veredicto — no otra cosa del recorrido.
#[tokio::test]
async fn without_the_line_count_the_same_ticket_is_still_refused_hub1391() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let rt = runtime_with_verifactu().await;
    let err = rt
        .execute_command(
            "verifactu.records.create",
            &alta("TICKET-2026-000002", None),
            &admin(),
        )
        .await
        .expect_err("sin conteo se juzga como una sola línea y la desviación de 2 céntimos sobra")
        .to_string();
    assert!(
        err.contains("quota_rate_mismatch"),
        "código esperado, llegó: {err}"
    );
    assert!(
        stored(&rt, "TICKET-2026-000002").await.is_empty(),
        "un rechazo no puede dejar registro: gastaría número de cadena"
    );
}

/// 🔒 Y el conteo NO es confiable —lo escribe el llamante—, así que no puede comprar el techo:
/// 99,99 € de cuota sobre una base de 5,45 € al 21 % (el caso del QA, verifactu#53) sigue muriendo
/// aquí aunque declare un millón de líneas. Es lo que mantiene esta puerta igual o más estricta que
/// el `CHECK` de la tabla.
#[tokio::test]
async fn a_declared_line_count_cannot_buy_its_way_past_the_ceiling_hub1391() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let rt = runtime_with_verifactu().await;
    let mut p = alta("TICKET-2026-000003", Some(1_000_000));
    p.insert("base_amount".into(), json!(545));
    p.insert("tax_amount".into(), json!(9999));
    p.insert("total_amount".into(), json!(10544));
    p.insert(
        "tax_breakdown".into(),
        json!(
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":545,"quota":9999}]"#
        ),
    );
    let err = rt
        .execute_command("verifactu.records.create", &p, &admin())
        .await
        .expect_err("ningún redondeo explica 99,99 € de cuota sobre 5,45 €")
        .to_string();
    assert!(
        err.contains("quota_rate_mismatch"),
        "código esperado, llegó: {err}"
    );
}

/// El esquema del módulo acota el campo: un conteo de cero o negativo lo rechaza la PUERTA, antes
/// del motor. Sin este `minimum`, `line_count: 0` sería un payload válido que el motor tendría que
/// desactivar por su cuenta.
#[tokio::test]
async fn the_schema_refuses_a_line_count_below_one_hub1391() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let rt = runtime_with_verifactu().await;
    let err = rt
        .execute_command(
            "verifactu.records.create",
            &alta("TICKET-2026-000004", Some(0)),
            &admin(),
        )
        .await
        .expect_err("`minimum: 1` en el esquema del módulo")
        .to_string();
    assert!(
        !err.contains("quota_rate_mismatch"),
        "esto lo tiene que parar el esquema, no el motor: {err}"
    );
}
