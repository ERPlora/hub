//! Cierra el hueco que dejó escondido el bug del DesgloseIVA: cada enlace de la cadena fiscal
//! estaba probado, pero la cadena no.
//!
//! El registro VeriFactu construye su `<Desglose>` a partir del `tax_breakdown` de la factura. Los
//! tests unitarios de `aeat::desglose` prueban que un `tax_breakdown` con dos tipos → dos líneas
//! `DetalleDesglose`. Lo que faltaba por probar es el otro extremo: que el módulo `invoice`
//! **produce** ese `tax_breakdown` con la forma exacta que aquel consume —una entrada por tipo, con
//! base y cuota en céntimos— cuando la factura mezcla tipos.
//!
//! Un ticket de bar (caña 21% + tapa 10%) es ese caso. Antes se declaraba a la AEAT un único tipo
//! efectivo (17,33%) que no existe en el sistema fiscal español. Con las dos mitades probadas
//! —invoice genera el desglose, aeat lo emite línea a línea— la cadena entera queda cubierta.

use std::path::PathBuf;

use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::{json, Value};

fn params(v: Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}
fn mdir(n: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules")
        .join(n)
}
fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}
/// El desglose lo calcula el handler WASM de invoice; sin él no hay nada que probar.
fn wasm() -> bool {
    mdir("invoice").join("dist/handler.wasm").exists()
}

/// `(tipo %, base en céntimos, cuota en céntimos)` de cada línea del `tax_breakdown`, **sea cual
/// sea la generación del contrato** (hub#292):
///
/// - **array** — una entrada por clave fiscal completa (`tax`/`regime`/`class`/`rate`/`base`/
///   `quota`), que es lo que emite `invoice` desde que la calificación dejó de ser literal;
/// - **objeto** — clave = tipo, `{base, tax}`, el formato de las facturas ya encadenadas.
///
/// La tolerancia es DELIBERADA y no afloja el test: este fichero vive en el repo `hub` y lee el
/// módulo `invoice` **del disco**, que es otro repo con su propio PR. Atarlo a una sola forma
/// haría que el CI del hub dependiera del orden en que se mergean los dos. Lo que el test asegura
/// —que invoice produce una entrada por tipo REAL, con base y cuota en céntimos, y no un tipo
/// efectivo inventado— es idéntico en ambas.
fn lineas_de_desglose(tb: &Value) -> Vec<(f64, i64, i64)> {
    let cents = |v: &Value| v.as_i64().expect("céntimos i64");
    match tb {
        Value::Array(entradas) => entradas
            .iter()
            .map(|e| {
                (
                    e["rate"].as_f64().unwrap_or(0.0),
                    cents(&e["base"]),
                    cents(&e["quota"]),
                )
            })
            .collect(),
        Value::Object(map) => map
            .iter()
            .filter_map(|(k, v)| {
                k.trim()
                    .parse::<f64>()
                    .ok()
                    .map(|r| (r, cents(&v["base"]), cents(&v["tax"])))
            })
            .collect(),
        _ => panic!("tax_breakdown no es ni array ni objeto: {tb}"),
    }
}

async fn rt_invoice() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&mdir("invoice")).await.expect("instalar invoice");
    rt
}

#[tokio::test]
async fn factura_mixta_produce_un_desglose_por_tipo_para_verifactu() {
    if !erplora_runtime::require_modules_workspace() { return; }
    if !wasm() {
        eprintln!("SKIP: invoice handler.wasm ausente");
        return;
    }
    let rt = rt_invoice().await;
    let ctx = admin();

    // Caña al 21% + tapa al 10% en el mismo ticket — el caso normal de un bar.
    rt.execute_command(
        "invoice.create",
        &params(json!({
            "series_code": "FACT", "issuer_nif": "B12345678", "issuer_name": "Bar Paco SL",
            "customer_name": "Cliente", "customer_tax_id": "B99",
            "items": [
                { "description": "Caña", "quantity": 1_000_000, "unit_price": 1000, "tax_rate": 21.0 },
                { "description": "Tapa", "quantity": 1_000_000, "unit_price": 500, "tax_rate": 10.0 }
            ]
        })),
        &ctx,
    )
    .await
    .expect("create_invoice");

    let invs = rt.execute_query("invoice.list", &Params::new(), &ctx).await.unwrap();
    let inv = rt
        .execute_query("invoice.get", &params(json!({ "invoice_id": invs[0]["id"] })), &ctx)
        .await
        .unwrap();
    let inv = &inv[0];

    // El desglose es la fuente del `<Desglose>` del XML AEAT (verifactu lo lee de aquí, verbatim).
    let tb: Value =
        serde_json::from_str(inv["tax_breakdown"].as_str().expect("tax_breakdown string"))
            .expect("tax_breakdown es JSON");
    let lineas = lineas_de_desglose(&tb);

    // Dos tipos reales, NO uno solo con el efectivo. Este es el corazón del arreglo.
    assert_eq!(lineas.len(), 2, "una entrada por tipo real, no una agregada: {tb}");
    let de = |rate: f64| {
        lineas
            .iter()
            .find(|(r, _, _)| (r - rate).abs() < 0.01)
            .unwrap_or_else(|| panic!("falta el {rate}%: {tb}"))
    };
    assert!(
        !lineas.iter().any(|(r, _, _)| (r - 17.33).abs() < 0.01),
        "el tipo efectivo no debe aparecer: {tb}"
    );

    // Base y cuota por tipo, en céntimos (el contrato que espera `aeat::desglose`).
    assert_eq!((de(21.0).1, de(21.0).2), (1000, 210));
    assert_eq!((de(10.0).1, de(10.0).2), (500, 50));

    // Coherencia con los totales de cabecera (lo que alimenta CuotaTotal/ImporteTotal del XML).
    assert_eq!(inv["tax_amount"].as_i64().unwrap(), 260);
    assert_eq!(inv["base_amount"].as_i64().unwrap(), 1500);
}
