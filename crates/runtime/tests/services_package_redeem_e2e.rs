//! E2E real del CONSUMO de bonos/paquetes del módulo `services`.
//! Instala los módulos reales (`taxes` + `services`) contra un Postgres de test y ejercita:
//!   - crear un paquete con `max_uses`/`validity_days`,
//!   - **CONCEDERLO** a un cliente (`services.packages.grant`),
//!   - redimir N veces (decremento de usos restantes),
//!   - bloqueo al superar `max_uses`,
//!   - bloqueo tras caducar (`validity_days`),
//!   - la query de saldo (`services.packages.balance`).
//!
//! 🔴 **La CONCESIÓN es obligatoria desde services 1.5.36** (services#73, ADR-0390). Antes, la
//! relación cliente↔bono se materializaba con el primer canje y `max_uses` se contaba por cliente
//! sobre el paquete del CATÁLOGO: cualquier cliente tenía sus N sesiones gratis de cualquier bono.
//! Ahora `services.packages.redeem` toma un **`grant_id`** —la compra— y el paquete y el cliente se
//! leen de ella, nunca del payload. Este fichero era el único sitio del hub que llamaba a la puerta
//! vieja.
//!
//! El consumo pasa por el handler WASM (que traduce el motivo a un código de dominio) y sus
//! sentencias con gate: un INSERT condicional en `services_package_redemption` + un assert contra
//! `services__gate` (CHECK ok=1) que REVIERTE la transacción si el consumo no se materializó.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}
fn services_dir() -> PathBuf {
    erplora_runtime::e2e_support::modules_root().join("services")
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
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.install_from_dir(&taxes_dir())
        .await
        .expect("instalar taxes");
    rt.install_from_dir(&services_dir())
        .await
        .expect("instalar services");
    rt
}

/// Un servicio REAL del catálogo de ESTE hub, para la línea del bono. `services.packages.create`
/// declara `reads` (ADR-0069, services v1.5.20): contrasta cada línea contra
/// `services.services.list` y RECHAZA el command si nombra algo que no está — un id inventado no
/// vale (hub#1036, services#42). Find-or-create para que el helper sea idempotente por runtime.
async fn bono_service(rt: &Runtime, ctx: &RequestContext) -> String {
    let list = rt
        .execute_query("services.services.list", &Params::new(), ctx)
        .await
        .unwrap();
    if let Some(found) = list.iter().find(|s| s["name"] == json!("Corte")) {
        return found["id"].as_str().unwrap().to_string();
    }
    rt.execute_command(
        "services.services.create",
        &params(json!({
            "name": "Corte",
            "tax_category_key": "service.generic",
            "price": 1000
        })),
        ctx,
    )
    .await
    .expect("crear el servicio de la línea del bono");
    let list = rt
        .execute_query("services.services.list", &Params::new(), ctx)
        .await
        .unwrap();
    list.iter()
        .find(|s| s["name"] == json!("Corte"))
        .unwrap_or_else(|| panic!("servicio Corte no encontrado tras crearlo"))["id"]
        .as_str()
        .unwrap()
        .to_string()
}

/// Crea un paquete vía el handler WASM `create_package` y devuelve su id (resuelto por
/// `services.packages.list`). Requiere `dist/handler.wasm`.
///
/// El bono lleva al menos UNA línea real (hub#1036): `services#42` va a exigir `minItems: 1`
/// en `schemas/package_create.json` — un bono sin líneas no es un producto vendible — y este
/// helper era el único llamante que creaba paquetes vacíos. La línea nombra un servicio del
/// catálogo (ver [`bono_service`]) porque el command lo contrasta antes de escribir.
async fn create_package(
    rt: &Runtime,
    ctx: &RequestContext,
    name: &str,
    max_uses: Option<i64>,
    validity_days: Option<i64>,
) -> String {
    let svc = bono_service(rt, ctx).await;
    rt.execute_command(
        "services.packages.create",
        &params(json!({
            "name": name,
            "discount_type": "percentage",
            "discount_value": 10.0,
            "max_uses": max_uses,
            "validity_days": validity_days,
            "items": [{ "service_id": svc, "quantity": 1_000_000 }]
        })),
        ctx,
    )
    .await
    .expect("crear paquete");

    let pkgs = rt
        .execute_query("services.packages.list", &Params::new(), ctx)
        .await
        .unwrap();
    let pkg_id = pkgs
        .iter()
        .find(|p| p["name"] == json!(name))
        .unwrap_or_else(|| panic!("paquete {name} no encontrado"))["id"]
        .as_str()
        .unwrap()
        .to_string();

    // El bono creado lleva su línea: la fixture no vuelve a fabricar el paquete vacío que
    // services#42 va a volver ilegal. Si el handler perdiera la línea en silencio, el redeem
    // seguiría pasando (cuenta usos, no líneas) — este assert es lo que lo haría visible.
    let lines = rt
        .execute_query(
            "services.package_items.list",
            &params(json!({ "package_id": pkg_id })),
            ctx,
        )
        .await
        .unwrap_or_else(|e| panic!("package_items.list del bono {name}: {e:?}"));
    assert!(
        lines.iter().any(|l| l["service_name"] == json!("Corte")),
        "el bono {name} debe llevar al menos la línea de «Corte»; líneas: {lines:?}"
    );

    pkg_id
}

/// Concede el bono a un cliente y devuelve el `grant_id` — la fila de COMPRA sin la cual no se
/// gasta ninguna sesión (services#73). El id se resuelve por `services.packages.balance`, que desde
/// esa versión responde **una fila por concesión**.
async fn grant_package(rt: &Runtime, ctx: &RequestContext, pkg: &str, customer: &str) -> String {
    rt.execute_command(
        "services.packages.grant",
        &params(json!({ "package_id": pkg, "customer_id": customer })),
        ctx,
    )
    .await
    .unwrap_or_else(|e| panic!("conceder el bono a {customer}: {e:?}"));

    let bal = rt
        .execute_query(
            "services.packages.balance",
            &params(json!({ "customer_id": customer })),
            ctx,
        )
        .await
        .expect("saldo tras conceder");
    bal.iter()
        .find(|b| b["package_id"] == json!(pkg))
        .unwrap_or_else(|| panic!("la concesión de {pkg} no aparece en el saldo de {customer}"))
        ["grant_id"]
        .as_str()
        .expect("grant_id de la concesión")
        .to_string()
}

#[tokio::test]
async fn install_registers_redeem_capabilities() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
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
    assert_eq!(
        redeem.def.emit.iter().map(|e| e.event()).collect::<Vec<_>>(),
        ["services.package.redeemed"]
    );
}

#[tokio::test]
async fn redeem_decrements_uses_and_blocks_over_max_uses() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    if !wasm_present() {
        eprintln!("SKIP: dist/handler.wasm ausente (paquetes se crean por WASM)");
        return;
    }
    let rt = fresh().await;
    let ctx = admin();
    // Bono de 3 usos, sin caducidad.
    let pkg = create_package(&rt, &ctx, "Bono 3 cortes", Some(3), None).await;
    let cust = "cust-1";

    // 🔴 Sin CONCESIÓN no hay nada que canjear, y esa es la razón de ser de services#73: antes de
    // conceder, este mismo canje pasaba y le regalaba tres sesiones a un cliente que no había
    // comprado nada. Se comprueba aquí, en el hub, porque es la puerta por la que entra el TPV.
    let sin_comprar = rt
        .execute_command(
            "services.packages.redeem",
            &params(json!({ "grant_id": "no-existe" })),
            &ctx,
        )
        .await
        .expect_err("canjear sin haber comprado el bono debe rechazarse");
    eprintln!("rechazo esperado (sin concesión): {sin_comprar}");

    let grant = grant_package(&rt, &ctx, &pkg, cust).await;

    // 3 consumos válidos.
    for i in 0..3 {
        rt.execute_command(
            "services.packages.redeem",
            &params(json!({ "grant_id": grant })),
            &ctx,
        )
        .await
        .unwrap_or_else(|e| panic!("consumo #{i} debería pasar: {e:?}"));
    }

    // Saldo: usados 3, restantes 0.
    let bal = rt
        .execute_query(
            "services.packages.balance",
            &params(json!({ "customer_id": cust })),
            &ctx,
        )
        .await
        .unwrap();
    assert_eq!(bal.len(), 1, "una única concesión con saldo");
    assert_eq!(bal[0]["used"], json!(3));
    assert_eq!(bal[0]["remaining"], json!(0));
    assert_eq!(bal[0]["is_expired"], json!(0));

    // 4º consumo: supera max_uses → RECHAZADO (la tx revierte por el gate).
    let err = rt
        .execute_command(
            "services.packages.redeem",
            &params(json!({ "grant_id": grant })),
            &ctx,
        )
        .await
        .expect_err("el 4º consumo debe rechazarse (max_uses superado)");
    eprintln!("rechazo esperado (max_uses): {err}");

    // El saldo no cambió: sigue en 3 usos (la tx del 4º revirtió).
    let bal2 = rt
        .execute_query(
            "services.packages.balance",
            &params(json!({ "customer_id": cust })),
            &ctx,
        )
        .await
        .unwrap();
    assert_eq!(
        bal2[0]["used"],
        json!(3),
        "el consumo rechazado no debe registrarse"
    );
}

#[tokio::test]
async fn redeem_blocks_after_expiry() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    if !wasm_present() {
        eprintln!("SKIP: dist/handler.wasm ausente (paquetes se crean por WASM)");
        return;
    }
    let rt = fresh().await;
    let ctx = admin();
    // Bono con caducidad 1 día. 🔴 Desde services#73 el reloj arranca en la COMPRA, no en el primer
    // uso: un bono comprado hace 10 días con 1 de validez está caducado AUNQUE NO SE HAYA ESTRENADO
    // — que es justo lo que el ancla anterior no podía expresar (sin primer uso no había reloj, así
    // que un bono de hace un año no había caducado y no iba a caducar nunca).
    let pkg = create_package(&rt, &ctx, "Bono caduco", Some(100), Some(1)).await;
    let cust = "cust-2";
    let grant = grant_package(&rt, &ctx, &pkg, cust).await;

    // Primer consumo, dentro de la ventana → pasa.
    rt.execute_command(
        "services.packages.redeem",
        &params(json!({ "grant_id": grant })),
        &ctx,
    )
    .await
    .expect("un consumo dentro de la ventana pasa");

    // Envejecemos la COMPRA 10 días al pasado (DETERMINISTA: no dependemos del reloj ni de la
    // resolución sub-segundo de `:now`). Con validez 1 día, el bono queda caducado.
    let mut p = Params::new();
    p.insert("ts".into(), json!("2026-06-15T10:00:00.000Z"));
    p.insert("hub_id".into(), json!("h1"));
    p.insert("grant_id".into(), json!(grant.clone()));
    rt.db_for_test()
        .execute(
            "UPDATE services_package_grant SET granted_at = :ts \
             WHERE hub_id = :hub_id AND id = :grant_id",
            &p,
        )
        .await
        .expect("backdate de la compra");

    // Segundo consumo: ahora > compra + 1 día → CADUCADO → rechazado (la tx revierte por el gate).
    let err = rt
        .execute_command(
            "services.packages.redeem",
            &params(json!({ "grant_id": grant })),
            &ctx,
        )
        .await
        .expect_err("el consumo tras caducar debe rechazarse");
    eprintln!("rechazo esperado (caducado): {err}");

    // El saldo refleja un único uso y marca el bono como caducado.
    let bal = rt
        .execute_query(
            "services.packages.balance",
            &params(json!({ "customer_id": cust })),
            &ctx,
        )
        .await
        .unwrap();
    assert_eq!(
        bal[0]["used"],
        json!(1),
        "solo el consumo válido quedó registrado"
    );
    assert_eq!(
        bal[0]["is_expired"],
        json!(1),
        "el bono debe figurar como caducado"
    );
}

/// Una concesión que no existe se rechaza — y se rechaza **por el motivo correcto**.
///
/// El assert es sobre el CÓDIGO de dominio y no sobre la prosa: el texto de un módulo cambia con su
/// traducción y no es contrato, mientras que `services.package_no_grant` sí lo es (ABI de errores de
/// dominio, hub#139). Sin este assert el test se conformaría con «falló algo», que es como un
/// rechazo por payload inválido se disfraza de rechazo de negocio.
#[tokio::test]
async fn redeem_rejects_a_grant_nobody_bought() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    if !wasm_present() {
        eprintln!("SKIP: dist/handler.wasm ausente (el canje pasa por el handler)");
        return;
    }
    let rt = fresh().await;
    let ctx = admin();
    let err = rt
        .execute_command(
            "services.packages.redeem",
            &params(json!({ "grant_id": "does-not-exist" })),
            &ctx,
        )
        .await
        .expect_err("consumir una concesión inexistente debe rechazarse");
    let shown = format!("{err:?}");
    assert!(
        shown.contains("services.package_no_grant"),
        "el rechazo debe nombrar la concesión que falta, no un error genérico; salió: {shown}"
    );
    eprintln!("rechazo esperado (sin concesión): {err}");
}
