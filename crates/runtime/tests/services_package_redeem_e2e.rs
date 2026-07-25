//! E2E real del CONSUMO de bonos/paquetes del módulo `services` (v1.2.0).
//! Instala los módulos reales (`taxes` + `services`) en SQLite en memoria y ejercita:
//!   - crear un paquete con `max_uses`/`validity_days`,
//!   - redimir N veces (decremento de usos restantes),
//!   - bloqueo al superar `max_uses`,
//!   - bloqueo tras caducar (`validity_days`),
//!   - la query de saldo (`services.packages.balance`).
//!
//! El consumo es declarativo (pure-SQL, sin WASM): un INSERT condicional en
//! `services_package_redemption` + un assert contra `services__gate` (CHECK ok=1) que
//! REVIERTE la transacción si el consumo no se materializó (mismo patrón que reservations).
use std::path::PathBuf;

use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}
fn services_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../modules-workspace/modules/services")
}
fn taxes_dir() -> PathBuf {
    services_dir().parent().unwrap().join("taxes")
}
fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}
fn wasm_present() -> bool {
    services_dir().join("dist/handler.wasm").exists()
}

async fn fresh() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&taxes_dir()).await.expect("instalar taxes");
    rt.install_from_dir(&services_dir()).await.expect("instalar services");
    rt
}

/// Crea un paquete vía el handler WASM `create_package` y devuelve su id (resuelto por
/// `services.packages.list`). Requiere `dist/handler.wasm`.
async fn create_package(
    rt: &Runtime,
    ctx: &RequestContext,
    name: &str,
    max_uses: Option<i64>,
    validity_days: Option<i64>,
) -> String {
    rt.execute_command(
        "services.packages.create",
        &params(json!({
            "name": name,
            "discount_type": "percentage",
            "discount_value": 10.0,
            "max_uses": max_uses,
            "validity_days": validity_days,
            "items": []
        })),
        ctx,
    )
    .await
    .expect("crear paquete");

    let pkgs = rt.execute_query("services.packages.list", &Params::new(), ctx).await.unwrap();
    pkgs.iter()
        .find(|p| p["name"] == json!(name))
        .unwrap_or_else(|| panic!("paquete {name} no encontrado"))["id"]
        .as_str()
        .unwrap()
        .to_string()
}

#[tokio::test]
async fn install_registers_redeem_capabilities() {
    let rt = fresh().await;
    let reg = rt.registry();
    assert!(reg.is_installed("services"));
    assert!(
        reg.get_command("services.packages.redeem").is_some(),
        "el command de consumo debe estar registrado"
    );
    assert!(
        reg.get_query("services.packages.balance").is_some(),
        "la query de saldo debe estar registrada"
    );
    // El consumo emite un evento para que otros módulos reaccionen.
    let redeem = reg.get_command("services.packages.redeem").unwrap();
    assert_eq!(redeem.def.emit, ["services.package.redeemed"]);
}

#[tokio::test]
async fn redeem_decrements_uses_and_blocks_over_max_uses() {
    if !wasm_present() {
        eprintln!("SKIP: dist/handler.wasm ausente (paquetes se crean por WASM)");
        return;
    }
    let rt = fresh().await;
    let ctx = admin();
    // Bono de 3 usos, sin caducidad.
    let pkg = create_package(&rt, &ctx, "Bono 3 cortes", Some(3), None).await;
    let cust = "cust-1";

    // 3 consumos válidos.
    for i in 0..3 {
        rt.execute_command(
            "services.packages.redeem",
            &params(json!({ "package_id": pkg, "customer_id": cust })),
            &ctx,
        )
        .await
        .unwrap_or_else(|e| panic!("consumo #{i} debería pasar: {e:?}"));
    }

    // Saldo: usados 3, restantes 0.
    let bal = rt
        .execute_query("services.packages.balance", &params(json!({ "customer_id": cust })), &ctx)
        .await
        .unwrap();
    assert_eq!(bal.len(), 1, "un único paquete con saldo");
    assert_eq!(bal[0]["used"], json!(3));
    assert_eq!(bal[0]["remaining"], json!(0));
    assert_eq!(bal[0]["is_expired"], json!(0));

    // 4º consumo: supera max_uses → RECHAZADO (la tx revierte por el gate).
    let err = rt
        .execute_command(
            "services.packages.redeem",
            &params(json!({ "package_id": pkg, "customer_id": cust })),
            &ctx,
        )
        .await
        .expect_err("el 4º consumo debe rechazarse (max_uses superado)");
    eprintln!("rechazo esperado (max_uses): {err}");

    // El saldo no cambió: sigue en 3 usos (la tx del 4º revirtió).
    let bal2 = rt
        .execute_query("services.packages.balance", &params(json!({ "customer_id": cust })), &ctx)
        .await
        .unwrap();
    assert_eq!(bal2[0]["used"], json!(3), "el consumo rechazado no debe registrarse");
}

#[tokio::test]
async fn redeem_blocks_after_expiry() {
    if !wasm_present() {
        eprintln!("SKIP: dist/handler.wasm ausente (paquetes se crean por WASM)");
        return;
    }
    let rt = fresh().await;
    let ctx = admin();
    // Bono con caducidad 1 día. El primer uso ancla la validez; un uso posterior fuera de la
    // ventana de 1 día debe rechazarse.
    let pkg = create_package(&rt, &ctx, "Bono caduco", Some(100), Some(1)).await;
    let cust = "cust-2";

    // Primer consumo: ancla la validez (no hay ancla previa) → pasa.
    rt.execute_command(
        "services.packages.redeem",
        &params(json!({ "package_id": pkg, "customer_id": cust })),
        &ctx,
    )
    .await
    .expect("primer consumo ancla la validez y pasa");

    // Envejecemos el ancla 10 días al pasado (DETERMINISTA: no dependemos del reloj ni de la
    // resolución sub-segundo de `:now`/julianday). Con validez 1 día, el bono queda caducado.
    let mut p = Params::new();
    p.insert("ts".into(), json!("2026-06-15T10:00:00.000Z"));
    p.insert("hub_id".into(), json!("h1"));
    p.insert("customer_id".into(), json!(cust));
    rt.db_for_test()
        .execute(
            "UPDATE services_package_redemption SET redeemed_at = :ts \
             WHERE hub_id = :hub_id AND customer_id = :customer_id",
            &p,
        )
        .await
        .expect("backdate del ancla");

    // Segundo consumo: ahora > ancla + 1 día → CADUCADO → rechazado (la tx revierte por el gate).
    let err = rt
        .execute_command(
            "services.packages.redeem",
            &params(json!({ "package_id": pkg, "customer_id": cust })),
            &ctx,
        )
        .await
        .expect_err("el consumo tras caducar debe rechazarse");
    eprintln!("rechazo esperado (caducado): {err}");

    // El saldo refleja un único uso y marca el bono como caducado.
    let bal = rt
        .execute_query("services.packages.balance", &params(json!({ "customer_id": cust })), &ctx)
        .await
        .unwrap();
    assert_eq!(bal[0]["used"], json!(1), "solo el consumo de anclaje quedó registrado");
    assert_eq!(bal[0]["is_expired"], json!(1), "el bono debe figurar como caducado");
}

#[tokio::test]
async fn redeem_rejects_unknown_package() {
    let rt = fresh().await;
    let ctx = admin();
    let err = rt
        .execute_command(
            "services.packages.redeem",
            &params(json!({ "package_id": "does-not-exist", "customer_id": "cust-x" })),
            &ctx,
        )
        .await
        .expect_err("consumir un paquete inexistente debe rechazarse");
    eprintln!("rechazo esperado (paquete inexistente): {err}");
}
