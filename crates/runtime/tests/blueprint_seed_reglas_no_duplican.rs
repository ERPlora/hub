//! Contract (hub#576): a blueprint is a COMPLETE hub, so the business's `tax_rules` TRAVEL in the
//! bundle next to its products — and importing over a hub that already has equivalent rules must
//! NOT duplicate them.
//!
//! History, because this file used to pin the OPPOSITE: `taxes_rule` had no unique index on its
//! natural key, so an equivalent rule arriving from another hub (its `id` embeds the ORIGIN hub:
//! `h1|taxrule|…` vs the destination's `h2|taxrule|…`) sailed past the id-based guard and the VAT
//! lookup silently became ambiguous — 12 rules where 10 belong. The only safe answer then was to
//! exclude seeded rules from the export ([`export::is_module_seeded`], `created_by='system'`).
//! That exclusion is now lifted for `taxes_rule` because BOTH halves of the fix exist:
//!   * the `taxes` module declares the natural key of a root rule as a real UNIQUE index
//!     (migration 004: partial over `parent_id IS NULL AND is_deleted = 0`, `NULLS NOT DISTINCT`);
//!   * the import guard asks the destination's catalog by NATURAL KEY (ADR-0304), so an
//!     equivalent row is SKIPPED instead of landing twice — or dying against the index.
//!
//! Reference data proper (`taxes_category` `is_system=1`, aliases `source='shipped'`) keeps NOT
//! traveling: the module re-seeds it on install (`import_test.rs` covers those).

use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::export::{export_hub, ExportSelection, ModuleDataSelection};
use erplora_runtime::import::{import_sections, ImportSelection, SectionStatus};
use erplora_runtime::Runtime;

/// Misma resolución que el guard `require_modules_workspace` — que honra `$ERPLORA_MODULES_DIR`.
/// Con la copia local sin esa variable, en un worktree fuera del monorepo el guard decía «sigue» y
/// el `install_from_dir` de después reventaba con `NotFound`: dos respuestas para la misma
/// pregunta. (El resto de suites e2e arrastra la misma copia — hub#541.)
fn modules_root() -> PathBuf {
    erplora_runtime::e2e_support::modules_root()
}

/// Un hub con `taxes` instalado (y por tanto su semilla aplicada) BAJO SU PROPIO `hub_id` —como en
/// producción. El test existente sembraba el destino bajo `h1` e importaba a `h2`, así que origen y
/// destino nunca compartían `(hub_id, …)` y el choque no salía.
async fn hub_con_taxes(hub_id: &str) -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.install_from_dir(&modules_root().join("taxes"))
        .await
        .expect("instalar taxes");
    rt
}

async fn count(rt: &Runtime, sql: &str) -> i64 {
    let res = rt.db().query(sql, &Params::new()).await.expect("count");
    res.rows
        .first()
        .and_then(|r| r.get("n"))
        .and_then(|v| v.as_i64())
        .unwrap_or(-1)
}

/// The bundle CARRIES the VAT rules (hub#576) — and restoring it over a hub that already has
/// equivalent rules does NOT duplicate them: the natural-key guard skips them one by one.
#[tokio::test]
async fn importar_blueprint_no_duplica_las_reglas_de_iva_sembradas() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    // ORIGEN h1 → bundle con taxes (los `id` embeben 'h1'; created_by='system').
    let a = hub_con_taxes("h1").await;
    let selection = ExportSelection {
        users: false,
        settings: false,
        settings_items: None,
        fiscal: false,
        media: false,
        modules: vec![ModuleDataSelection {
            module_id: "taxes".into(),
            with_data: true,
            tables: None,
        }],
        purpose: Default::default(),
    };
    let bundle = export_hub(
        &a,
        "h1",
        &selection,
        "barberia",
        "es",
        "2026-07-11T18:00:00Z",
    )
    .await
    .expect("export h1");
    // The rules are IN the bundle: a blueprint is a complete hub (hub#576). Before this, the
    // seeded rules were excluded and a per-country blueprint could never carry its VAT.
    let sql = String::from_utf8(bundle.files["data/taxes.sql"].clone()).unwrap();
    assert!(
        sql.contains("INSERT INTO taxes_rule"),
        "the blueprint must carry the hub's tax_rules next to its products:\n{sql}"
    );

    // DESTINO h2, sembrado bajo SU PROPIO hub_id: ya tiene sus reglas ES.
    //
    // El número se MIDE, no se clava: la semilla de `taxes` crece (las categorías exentas de
    // ADR-0185 la subieron de 6 a 10) y un literal convierte cada ampliación legítima del módulo en
    // un test rojo que no dice nada. Lo que este test afirma no es «cuántas hay» sino «importar no
    // añade ninguna», así que la referencia es el propio estado de antes.
    let mut b = hub_con_taxes("h2").await;
    let antes = count(
        &b,
        "SELECT count(*) AS n FROM taxes_rule WHERE hub_id = 'h2'",
    )
    .await;
    assert!(
        antes > 0,
        "precondición: el módulo siembra sus reglas al instalarse"
    );

    let import = ImportSelection {
        users: false,
        settings: false,
        fiscal: false,
        media: false,
        modules: vec!["taxes".into()],
    };
    let report = import_sections(&mut b, &bundle.manifest, &bundle.files, &import, "h2")
        .await
        .expect("best-effort");
    let taxes = report
        .sections
        .iter()
        .find(|s| s.section == "modules/taxes")
        .expect("taxes en informe");
    assert!(
        matches!(taxes.status, SectionStatus::Applied),
        "sección taxes: {:?}",
        taxes.status
    );

    // Las reglas de IVA sembradas NO se duplican: las mismas de antes, y ES/product.generic única.
    assert_eq!(
        count(
            &b,
            "SELECT count(*) AS n FROM taxes_rule WHERE hub_id = 'h2'"
        )
        .await,
        antes,
        "las reglas de IVA sembradas por el módulo se duplicaron al restaurar el blueprint",
    );
    assert_eq!(
        count(
            &b,
            "SELECT count(*) AS n FROM taxes_rule WHERE hub_id = 'h2' AND country_code = 'ES' \
             AND tax_category_key = 'product.generic' AND parent_id IS NULL AND is_deleted = 0",
        )
        .await,
        1,
        "IVA ambiguo: más de una regla activa para ES/product.generic tras importar el blueprint",
    );
}

/// [hub#532 → hub#576] Un hub VACÍO que importa una plantilla acaba **con los impuestos puestos**.
///
/// The contract FLIPPED with hub#576 (decision: a blueprint is a complete hub, its `tax_rules`
/// travel by default and per country, next to its products). Before, `data/taxes.sql` shipped
/// EMPTY on purpose and the taxes arrived only through the module seed on install — which is
/// exactly the coupling hub#576 dismantles: the module seed planting the ES baseline in every
/// hub regardless of country was the only thing holding the "ready to use" blueprint together.
///
/// Now the template carries its rules (they are the other half of its catalog: 280 products
/// pointing at `restaurant.food` price NOTHING without the rule that resolves it), and the
/// natural-key guard (ADR-0304 + taxes migration 004) is what keeps the double-seeded case
/// duplicate-free — proven above. What this test keeps asserting is the outcome that matters to
/// whoever imports a template: **after importing, can the hub charge VAT?**
#[tokio::test]
async fn importar_una_plantilla_deja_el_hub_con_los_impuestos_puestos() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    // ORIGEN: un hub con `taxes`, exportado como PLANTILLA.
    let origen = hub_con_taxes("h1").await;
    let selection = ExportSelection {
        users: false,
        settings: false,
        settings_items: None,
        fiscal: false,
        media: false,
        modules: vec![ModuleDataSelection {
            module_id: "taxes".into(),
            with_data: true,
            tables: None,
        }],
        purpose: erplora_runtime::export::BundlePurpose::Template,
    };
    let bundle = export_hub(
        &origen,
        "h1",
        &selection,
        "restaurante",
        "es",
        "2026-08-08T10:00:00Z",
    )
    .await
    .expect("export plantilla");
    let sql = String::from_utf8(bundle.files["data/taxes.sql"].clone()).unwrap();
    assert!(
        sql.contains("INSERT INTO taxes_rule"),
        "premise (hub#576): a template carries its tax_rules next to its products:\n{sql}"
    );
    // Reference data proper keeps NOT traveling: the module re-seeds it on install (ADR-0147).
    assert!(
        !sql.contains("INSERT INTO taxes_category "),
        "system categories are reference data and must keep out of the bundle:\n{sql}"
    );

    // DESTINO: hub NUEVO. Instalar el módulo del manifest es el paso 2 del import, y es el que
    // aplica el seed — igual que `install_from_cloud` en producción.
    let destino = hub_con_taxes("h2").await;

    // Cuántas son es cosa del módulo (y crece); lo que este test afirma es que NO son cero.
    assert!(
        count(&destino, "SELECT count(*) AS n FROM taxes_rule WHERE hub_id = 'h2'").await > 0,
        "el hub que importó la plantilla tiene que poder cobrar el IVA: sin reglas, `taxes.calculate` \
         devuelve `no_rate` y no hay venta que facturar"
    );
    assert!(
        count(&destino, "SELECT count(*) AS n FROM taxes_category WHERE hub_id = 'h2' AND is_system = 1").await > 0,
        "…y con sus categorías fiscales canónicas, que es a lo que apunta cada producto del catálogo"
    );
}
