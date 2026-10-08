//! Contract (hub#842): **a bundle's data section may not duplicate what the module's own install
//! seed already guarantees.**
//!
//! The sequence that produces the defect is the one a TEMPLATE import runs, and only that one:
//! the bundle names the module, so the import INSTALLS it first — which runs
//! `seed/install.postgres.sql` and plants `Cash`/`Card` — and only THEN applies `data/sales.sql`,
//! which brings the template's `Efectivo`/`Tarjeta`. Two idempotency guards that cannot see each
//! other: the seed's asks by natural key `(hub_id, type)`, the bundle's asks by `id` — and the id
//! it asks about is one `import::derive_id` just rewrote (uuid v5 over the DESTINATION hub), so it
//! can never match a seeded row whose id is `<hub_id>|paymethod|<type>`. Both insert. Four payment
//! methods where the owner should see two, half of them in a language that is not hers.
//!
//! An `export` → `import` between two hubs does NOT reproduce it (that is what kept the issue open
//! for four days): with no module installation in between, nothing plants the seeded row the
//! bundle collides with.
//!
//! Why not fix it in the exporter: `export::natural_keys` reads the destination's UNIQUE indexes,
//! and `sales_payment_method` has none on `(hub_id, type)` — it cannot have one, either, because
//! `type` is a behaviour class (cash opens the drawer, card does not), not an identity: a hub may
//! legitimately run `Visa` and `Amex`, both `card`. The key exists in exactly one place, and it is
//! the module's own seed guard. That is what the import now reads.

use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::export::{export_hub, BundlePurpose, ExportSelection, ModuleDataSelection};
use erplora_runtime::import::{import_sections, ImportSelection, SectionStatus};
use erplora_runtime::Runtime;

fn mdir(id: &str) -> PathBuf {
    erplora_runtime::e2e_support::modules_root().join(id)
}

/// A hub with `sales` installed — and therefore with its seed applied — under its OWN `hub_id`,
/// exactly as production does it.
async fn hub_con_sales(hub_id: &str) -> Runtime {
    ensure_master_key();
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.install_from_dir(&mdir("taxes")).await.expect("taxes");
    rt.install_from_dir(&mdir("inventory"))
        .await
        .expect("inventory");
    rt.install_from_dir(&mdir("sales")).await.expect("sales");
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

async fn payment_methods(rt: &Runtime, hub_id: &str) -> Vec<(String, String)> {
    let sql = format!(
        "SELECT name, type FROM sales_payment_method \
         WHERE hub_id = '{hub_id}' AND is_deleted = 0 ORDER BY type, name"
    );
    let res = rt
        .db()
        .query(&sql, &Params::new())
        .await
        .expect("payment methods");
    res.rows
        .iter()
        .map(|r| {
            (
                r.get("name")
                    .and_then(|v| v.as_str())
                    .unwrap_or_default()
                    .to_string(),
                r.get("type")
                    .and_then(|v| v.as_str())
                    .unwrap_or_default()
                    .to_string(),
            )
        })
        .collect()
}

/// Adds a payment method the way the OWNER does (`created_by` = a user, not `system`), which is
/// what makes it travel: `export::is_module_seeded` keeps the module's own reference rows out of
/// the bundle, so the `Efectivo`/`Tarjeta` of the published `peluqueria` v1.0.4 are rows a person
/// created in the hub the blueprint was built from.
async fn owner_adds_method(rt: &Runtime, hub_id: &str, id: &str, name: &str, kind: &str) {
    let sql = format!(
        "INSERT INTO sales_payment_method \
         (id, hub_id, name, type, icon, is_active, sort_order, opens_cash_drawer, \
          requires_change, is_deleted, created_by, updated_by, created_at, updated_at) \
         VALUES ('{id}', '{hub_id}', '{name}', '{kind}', '', 1, 10, 0, 0, 0, \
                 'u-owner', 'u-owner', '2026-08-15T10:00:00Z', '2026-08-15T10:00:00Z')"
    );
    rt.db()
        .execute(&sql, &Params::new())
        .await
        .expect("owner adds a payment method");
}

/// The published `peluqueria` template, rebuilt: a hub whose owner created `Efectivo` and
/// `Tarjeta`, exported with `purpose: template`.
async fn plantilla_con_formas_de_pago() -> (erplora_runtime::export::ExportBundle, Runtime) {
    let origen = hub_con_sales("h1").await;
    owner_adds_method(
        &origen,
        "h1",
        "bad260fd-0642-4a70-9d65-6cac4503b7f6",
        "Efectivo",
        "cash",
    )
    .await;
    owner_adds_method(
        &origen,
        "h1",
        "34fa35c7-2b20-419a-ab9c-023642439abf",
        "Tarjeta",
        "card",
    )
    .await;
    let selection = ExportSelection {
        users: false,
        settings: false,
        settings_items: None,
        fiscal: false,
        media: false,
        modules: vec![ModuleDataSelection {
            module_id: "sales".into(),
            with_data: true,
            tables: None,
        }],
        purpose: BundlePurpose::Template,
    };
    let bundle = export_hub(
        &origen,
        "h1",
        &selection,
        "peluqueria",
        "es",
        "2026-08-15T10:00:00Z",
    )
    .await
    .expect("export plantilla");
    (bundle, origen)
}

fn import_selection() -> ImportSelection {
    ImportSelection {
        users: false,
        settings: false,
        fiscal: false,
        media: false,
        modules: vec!["sales".into()],
    }
}

async fn aplica(
    destino: &mut Runtime,
    bundle: &erplora_runtime::export::ExportBundle,
    hub_id: &str,
) {
    let report = import_sections(
        destino,
        &bundle.manifest,
        &bundle.files,
        &import_selection(),
        hub_id,
    )
    .await
    .expect("best-effort");
    let sales = report
        .sections
        .iter()
        .find(|s| s.section == "modules/sales")
        .expect("sales en el informe");
    assert!(
        matches!(sales.status, SectionStatus::Applied),
        "sección sales: {:?}",
        sales.status
    );
}

/// 🔴 The golden one: importing the template over a hub that just installed `sales` leaves **two**
/// payment methods, not four — and the ones that stay are the DESTINATION's, in canonical English
/// (ADR-0055: the UI translates them; if the bundle's name won, a `fr` hub importing an `es`
/// template would inherit «Efectivo»).
#[tokio::test]
async fn importar_una_plantilla_no_duplica_las_formas_de_pago_del_seed() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let (bundle, _origen) = plantilla_con_formas_de_pago().await;
    let sql = String::from_utf8(bundle.files["data/sales.sql"].clone()).unwrap();
    assert!(
        sql.contains("'Efectivo'") && sql.contains("'Tarjeta'"),
        "premise: the template carries the payment methods its owner created:\n{sql}"
    );
    assert!(
        !sql.contains("'Cash'"),
        "premise: the module's OWN seeded rows never travel (export::is_module_seeded):\n{sql}"
    );

    // DESTINO: a hub where installing the module planted Cash/Card — step 2 of every template
    // import, and the step an `export`→`import` between two hubs never performs.
    let mut destino = hub_con_sales("h2").await;
    assert_eq!(
        payment_methods(&destino, "h2").await,
        vec![
            ("Card".into(), "card".into()),
            ("Cash".into(), "cash".into())
        ],
        "precondición: instalar `sales` siembra Cash/Card"
    );

    aplica(&mut destino, &bundle, "h2").await;

    assert_eq!(
        payment_methods(&destino, "h2").await,
        vec![
            ("Card".into(), "card".into()),
            ("Cash".into(), "cash".into())
        ],
        "el TPV ofrece «Efectivo, Tarjeta, Cash, Card»: cuatro botones donde debe haber dos"
    );
}

/// Re-importing the same bundle keeps being a no-op (the idempotency the id guard already gave).
#[tokio::test]
async fn reimportar_la_misma_plantilla_sigue_siendo_idempotente() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let (bundle, _origen) = plantilla_con_formas_de_pago().await;
    let mut destino = hub_con_sales("h2").await;
    aplica(&mut destino, &bundle, "h2").await;
    let tras_el_primero = payment_methods(&destino, "h2").await;
    aplica(&mut destino, &bundle, "h2").await;
    assert_eq!(
        payment_methods(&destino, "h2").await,
        tras_el_primero,
        "re-importar el mismo bundle no puede añadir filas"
    );
}

/// The dedupe is about the SEEDED slot, not about the table: a method the module never plants
/// (`bizum`) is the vertical's own contribution and lands untouched. This is the half the issue's
/// option «que las plantillas no lleven formas de pago» would have thrown away.
#[tokio::test]
async fn una_forma_de_pago_propia_del_vertical_si_aterriza() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let origen = hub_con_sales("h1").await;
    owner_adds_method(
        &origen,
        "h1",
        "bad260fd-0642-4a70-9d65-6cac4503b7f6",
        "Efectivo",
        "cash",
    )
    .await;
    owner_adds_method(
        &origen,
        "h1",
        "9a1d0f4e-2c33-4a41-9f0b-6b2c5d7e8f01",
        "Bizum",
        "bizum",
    )
    .await;
    let selection = ExportSelection {
        users: false,
        settings: false,
        settings_items: None,
        fiscal: false,
        media: false,
        modules: vec![ModuleDataSelection {
            module_id: "sales".into(),
            with_data: true,
            tables: None,
        }],
        purpose: BundlePurpose::Template,
    };
    let bundle = export_hub(
        &origen,
        "h1",
        &selection,
        "peluqueria",
        "es",
        "2026-08-15T10:00:00Z",
    )
    .await
    .expect("export");

    let mut destino = hub_con_sales("h2").await;
    aplica(&mut destino, &bundle, "h2").await;

    assert_eq!(
        payment_methods(&destino, "h2").await,
        vec![
            ("Bizum".into(), "bizum".into()),
            ("Card".into(), "card".into()),
            ("Cash".into(), "cash".into())
        ],
        "el «Bizum» del vertical no es lo que el seed garantiza: tiene que aterrizar"
    );
}

/// The rule is about what the SEED guarantees, never about what the OWNER made. A destination
/// where the owner created a `bizum` method does not shadow the template's own `bizum`: the module
/// plants none, so it guarantees nothing there and has no claim on that slot.
#[tokio::test]
async fn lo_que_creo_el_dueno_del_destino_no_tapa_la_aportacion_de_la_plantilla() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let origen = hub_con_sales("h1").await;
    owner_adds_method(
        &origen,
        "h1",
        "9a1d0f4e-2c33-4a41-9f0b-6b2c5d7e8f01",
        "Bizum salon",
        "bizum",
    )
    .await;
    let selection = ExportSelection {
        users: false,
        settings: false,
        settings_items: None,
        fiscal: false,
        media: false,
        modules: vec![ModuleDataSelection {
            module_id: "sales".into(),
            with_data: true,
            tables: None,
        }],
        purpose: BundlePurpose::Template,
    };
    let bundle = export_hub(
        &origen,
        "h1",
        &selection,
        "peluqueria",
        "es",
        "2026-08-15T10:00:00Z",
    )
    .await
    .expect("export");

    let mut destino = hub_con_sales("h2").await;
    owner_adds_method(
        &destino,
        "h2",
        "c0ffee00-0000-4000-8000-000000000001",
        "Bizum",
        "bizum",
    )
    .await;
    aplica(&mut destino, &bundle, "h2").await;

    assert_eq!(
        payment_methods(&destino, "h2").await,
        vec![
            ("Bizum".into(), "bizum".into()),
            ("Bizum salon".into(), "bizum".into()),
            ("Card".into(), "card".into()),
            ("Cash".into(), "cash".into())
        ],
        "el seed no siembra `bizum`: no tiene nada que reclamar en esa ranura"
    );
}

/// A hub restoring its OWN backup loses nothing. Its seeded rows never travelled, so everything in
/// the bundle is something a person made — including a second method of a type the module seeds
/// (`Amex`, `card`), which a foreign template could not have brought without shadowing the seed.
#[tokio::test]
async fn restaurar_el_backup_propio_no_pierde_una_forma_de_pago_del_dueno() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let origen = hub_con_sales("h1").await;
    owner_adds_method(
        &origen,
        "h1",
        "1f0a2b3c-4d5e-6f70-8192-a3b4c5d6e7f8",
        "Amex",
        "card",
    )
    .await;
    let selection = ExportSelection {
        users: false,
        settings: false,
        settings_items: None,
        fiscal: false,
        media: false,
        modules: vec![ModuleDataSelection {
            module_id: "sales".into(),
            with_data: true,
            tables: None,
        }],
        purpose: BundlePurpose::Backup,
    };
    let bundle = export_hub(
        &origen,
        "h1",
        &selection,
        "backup",
        "es",
        "2026-08-15T10:00:00Z",
    )
    .await
    .expect("export backup");

    // Restoring over a REDEPLOY of the same hub: the modules are installed again (the seed runs
    // again) and then the data lands. `manifest.hub.hub_id` says h1, so this is `same_hub`.
    let mut destino = hub_con_sales("h1").await;
    aplica(&mut destino, &bundle, "h1").await;

    assert_eq!(
        payment_methods(&destino, "h1").await,
        vec![
            ("Amex".into(), "card".into()),
            ("Card".into(), "card".into()),
            ("Cash".into(), "cash".into())
        ],
        "restaurar tu propia copia no puede tirar un método que creaste tú"
    );
    assert_eq!(
        count(
            &destino,
            "SELECT count(*) AS n FROM sales_payment_method WHERE hub_id = 'h1'"
        )
        .await,
        3,
    );
}

/// `HUB_SECRETS_KEY` once for this binary, as every production hub has it: a hub's own copy is
/// only proven by the origin seal derived from it (hub#2497), so a restore of the hub's own backup
/// needs it at both ends.
fn ensure_master_key() {
    use base64::Engine as _;
    use std::sync::Once;
    static ONCE: Once = Once::new();
    ONCE.call_once(|| {
        let key = base64::engine::general_purpose::STANDARD.encode([0x24u8; 32]);
        // SAFETY: `Once` runs this before any test reads the variable, and nothing writes it again.
        unsafe { std::env::set_var("HUB_SECRETS_KEY", key) };
    });
}
