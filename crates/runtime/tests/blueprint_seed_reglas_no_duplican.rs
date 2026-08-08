//! Contrato: los datos de REFERENCIA que un módulo re-siembra en cada hub NO deben viajar en el
//! blueprint y duplicarse al restaurar. Complementa `import_test.rs`, que solo cubre
//! `taxes_category`/`taxes_category_alias` (marcadas `is_system`/`source='shipped'`), ya excluidas
//! por [`export::is_module_seeded`] (PR #191).
//!
//! Hueco que fija ESTE test: `taxes_rule` no lleva `is_system` NI `source` — el heurístico no la
//! reconocía y sus 6 reglas de IVA sembradas SÍ viajaban. Al importar sobre un hub que ya re-sembró
//! las suyas, el guard-por-`id` no las ve (el `id` embebe el hub ORIGEN: `h1|taxrule|…` vs el
//! destino `h2|taxrule|…`) → el destino acaba con 12 reglas y el lookup de IVA es AMBIGUO. No
//! revienta (`taxes_rule` no tiene índice único por clave natural), así que es un fallo SILENCIOSO
//! en un módulo fiscal — peor que un crash.
//!
//! Marcador uniforme de lo sembrado por el módulo: `created_by = 'system'` (lo pone
//! `apply_module_seed`). `hub_settings`/`hub_user` no tienen esa columna, así que excluir por ella
//! no les afecta.

use std::path::PathBuf;

use erplora_db::{Params, testutil::fresh_db};
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

/// Restaurar un blueprint sobre un hub que ya tiene su semilla NO duplica las reglas de IVA.
#[tokio::test]
async fn importar_blueprint_no_duplica_las_reglas_de_iva_sembradas() {
    if !erplora_runtime::require_modules_workspace() { return; }
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

    // DESTINO h2, sembrado bajo SU PROPIO hub_id: ya tiene sus reglas ES.
    //
    // El número se MIDE, no se clava: la semilla de `taxes` crece (las categorías exentas de
    // ADR-0185 la subieron de 6 a 10) y un literal convierte cada ampliación legítima del módulo en
    // un test rojo que no dice nada. Lo que este test afirma no es «cuántas hay» sino «importar no
    // añade ninguna», así que la referencia es el propio estado de antes.
    let mut b = hub_con_taxes("h2").await;
    let antes = count(&b, "SELECT count(*) AS n FROM taxes_rule WHERE hub_id = 'h2'").await;
    assert!(antes > 0, "precondición: el módulo siembra sus reglas al instalarse");

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

/// 🔴 [hub#532] Un hub VACÍO que importa una plantilla acaba **con los impuestos puestos**.
///
/// Es la afirmación que faltaba, y su ausencia costó un diagnóstico equivocado: al auditar las
/// cuatro plantillas del catálogo (2026-08-08) las cuatro traían `data/taxes.sql` **vacío** —el
/// restaurante, 280 productos y cero tipos de IVA— y eso se leyó como un agujero: *«las plantillas
/// no traen los impuestos»*. No lo es. El fichero está vacío **a propósito**, por dos reglas que ya
/// existían y que nadie había juntado en una sola frase:
///
/// 1. el export **omite** las filas que un módulo re-siembra ([`export::is_module_seeded`],
///    `created_by = 'system'`) — el resto de este fichero prueba por qué: si viajaran, el destino
///    acabaría con las reglas por duplicado y el lookup de IVA ambiguo;
/// 2. el import **instala** los módulos del manifest, y el instalador aplica su bloque `seed`
///    (ADR-0147) — más el suplemento de IVA ES si el hub es de España.
///
/// O sea: los impuestos llegan, pero **por el seed del módulo, no por el bundle**. Y así es como
/// tiene que ser, porque el seed siembra **según el país del hub**: unas filas dentro del bundle
/// plantarían el IVA español en un hub francés.
///
/// Los otros tests de esta familia prueban las dos mitades por separado —que no se duplican
/// (arriba) y que un hub ES recibe 21/10/4 al instalar (`es_iva_seed_e2e`)—. Ninguno afirmaba el
/// resultado que le importa a quien mira una plantilla: **después de importar, ¿puede facturar?**
#[tokio::test]
async fn importar_una_plantilla_deja_el_hub_con_los_impuestos_puestos() {
    if !erplora_runtime::require_modules_workspace() { return; }
    // ORIGEN: un hub con `taxes`, exportado como PLANTILLA. Su `data/taxes.sql` sale vacío.
    let origen = hub_con_taxes("h1").await;
    let selection = ExportSelection {
        users: false,
        settings: false,
        settings_items: None,
        fiscal: false,
        media: false,
        modules: vec![ModuleDataSelection { module_id: "taxes".into(), with_data: true }],
        purpose: erplora_runtime::export::BundlePurpose::Template,
    };
    let bundle = export_hub(&origen, "h1", &selection, "restaurante", "es", "2026-08-08T10:00:00Z")
        .await
        .expect("export plantilla");
    let sql = String::from_utf8(bundle.files["data/taxes.sql"].clone()).unwrap();
    assert!(
        !sql.contains("INSERT INTO taxes_rule"),
        "premisa: las reglas sembradas NO viajan en el bundle (las re-siembra el módulo):\n{sql}"
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
