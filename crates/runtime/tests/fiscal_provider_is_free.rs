//! **A module that fulfils the hub's own fiscal regime may not be SOLD** — ADR-0273 D7, hub#559.
//!
//! This is a **defensive** rule and it fixes nothing that is broken today: VeriFactu is free
//! (decisión de Ioan, 2026-08-08), so the path *«the entitlement expired → VeriFactu off → the
//! till keeps selling»* does not exist — there is nothing to expire. Not paying costs the customer
//! **access to the hub**, which is a platform matter, not a fiscal one.
//!
//! What is missing is anything **structural** stopping it from coming back. A future price change,
//! or a third-party module implementing the same regime and charging for it, reopens it — and the
//! mechanism that would break it already exists: module-system §2bis, *«blocking = the dispatcher
//! refuses the module's queries/commands»*. Applied to the fiscal provider, an unpaid invoice would
//! leave the hub unable to transmit or even see its own queue: a billing incident turned into a
//! fiscal fire.
//!
//! So the door is at the install: a module that fulfils **this hub's** regime and declares paid
//! commercial terms is refused, with a stable code.

use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;

/// A module directory carrying `manifest` as its `module.json`.
fn fixture(manifest: &str) -> std::path::PathBuf {
    let dir =
        std::env::temp_dir().join(format!("erplora-fiscal-provider-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("module.json"), manifest).unwrap();
    dir
}

/// A booted hub. The default country is `ES` (ADR-0085), so its profile is born owing VeriFactu.
async fn spanish_hub(hub_id: &str) -> Runtime {
    let runtime = Runtime::with_hub_id(Box::new(fresh_db().await), hub_id);
    runtime.ensure_system_tables().await.unwrap();
    runtime
}

/// 🔴 **The rule.** The hub owes VeriFactu; this module says it implements VeriFactu for Spain and
/// that it is sold by subscription. Installing it would make complying with the law depend on a
/// subscription staying paid — which is the one thing ADR-0273 exists to forbid.
#[tokio::test]
async fn a_paid_module_cannot_be_the_provider_of_the_hubs_own_regime() {
    let mut runtime = spanish_hub("hub-es").await;
    let dir = fixture(
        r#"{
          "id":"verifactu",
          "name":"VeriFactu",
          "version":"1.5.7",
          "fiscal_regime":{"country":"ES","regime":"verifactu"},
          "billing":{"tier":"premium","type":"subscription","price":9.99,"interval":"month"}
        }"#,
    );

    let error = runtime
        .install_from_dir(&dir)
        .await
        .expect_err("a sold provider of the hub's own regime must not install");

    assert!(
        matches!(&error, erplora_runtime::errors::RuntimeError::Domain { code, .. }
            if code == erplora_runtime::installer::PROVIDER_NOT_FREE),
        "the rejection carries a stable code the UI programs against, got {error:?}"
    );
    assert_eq!(
        erplora_runtime::installer::PROVIDER_NOT_FREE,
        "fiscal.provider_not_free",
        "the code is public ABI: the marketplace and the UI translate against this literal"
    );
    std::fs::remove_dir_all(dir).unwrap();
}

/// The provider as it actually ships: it declares the regime and nothing commercial. This is the
/// shape of `verifactu` v1.5.7 today, and the rule must not touch it.
#[tokio::test]
async fn a_free_provider_of_the_hubs_regime_installs() {
    let mut runtime = spanish_hub("hub-es").await;
    let dir = fixture(
        r#"{
          "id":"verifactu",
          "name":"VeriFactu",
          "version":"1.5.7",
          "fiscal_regime":{"country":"ES","regime":"verifactu"}
        }"#,
    );

    assert_eq!(
        runtime.install_from_dir(&dir).await.unwrap(),
        "verifactu",
        "the free provider is the whole point: it must keep installing"
    );
    std::fs::remove_dir_all(dir).unwrap();
}

/// **Selling a module is not the hub's business.** The rule is about the module the hub's
/// COMPLIANCE would hang from, not about commerce: a paid module that fulfils no regime installs
/// exactly as before (this is the shape of `whatsapp_inbox`, the one published module with a
/// `billing` block).
#[tokio::test]
async fn a_paid_module_that_is_not_a_fiscal_provider_installs() {
    let mut runtime = spanish_hub("hub-es").await;
    let dir = fixture(
        r#"{
          "id":"whatsapp_inbox",
          "name":"WhatsApp Inbox",
          "version":"1.0.0",
          "billing":{"tier":"premium","type":"subscription","trial_days":15,
            "tiers":[{"slug":"free","name":"Free","price":0,"interval":"month"},
                     {"slug":"starter","name":"Starter","price":14.99,"interval":"month"}]}
        }"#,
    );

    assert_eq!(
        runtime.install_from_dir(&dir).await.unwrap(),
        "whatsapp_inbox"
    );
    std::fs::remove_dir_all(dir).unwrap();
}

/// A paid provider of ANOTHER country's regime is not this hub's provider, so refusing it would be
/// the runtime having an opinion about somebody else's commerce. It installs.
#[tokio::test]
async fn a_paid_provider_of_another_regime_installs() {
    let mut runtime = spanish_hub("hub-es").await;
    let dir = fixture(
        r#"{
          "id":"facturx",
          "name":"Factur-X",
          "version":"1.0.0",
          "fiscal_regime":{"country":"FR","regime":"facturx"},
          "billing":{"type":"subscription","price":9.99}
        }"#,
    );

    assert_eq!(runtime.install_from_dir(&dir).await.unwrap(), "facturx");
    std::fs::remove_dir_all(dir).unwrap();
}

/// 🔴 **The guard refuses to CREATE the dependency; it never breaks one the hub already has.**
///
/// Every restart re-registers the installed modules through the install path
/// (`Runtime::rehydrate_installed`), and a stateless Hub Cloud re-downloads them after a redeploy.
/// So a rule that only asked "is this sold?" would turn a price change into a hub that stops
/// mounting its provider at the next boot — `BLOCKED`, till stopped. That is the very fiscal fire
/// this rule exists to prevent, caused by the rule itself. Refusing what is already installed is
/// the SaaS's job at publish time, where no till is open.
#[tokio::test]
async fn a_provider_the_hub_already_installed_still_boots_after_a_price_change() {
    let mut runtime = spanish_hub("hub-es").await;
    let free = fixture(
        r#"{
          "id":"verifactu",
          "name":"VeriFactu",
          "version":"1.5.7",
          "fiscal_regime":{"country":"ES","regime":"verifactu"}
        }"#,
    );
    runtime.install_from_dir(&free).await.unwrap();

    // Somebody starts charging for it, and the hub restarts.
    let paid = fixture(
        r#"{
          "id":"verifactu",
          "name":"VeriFactu",
          "version":"1.6.0",
          "fiscal_regime":{"country":"ES","regime":"verifactu"},
          "billing":{"tier":"premium","type":"subscription","price":9.99}
        }"#,
    );

    assert_eq!(
        runtime.install_from_dir(&paid).await.unwrap(),
        "verifactu",
        "a hub that already complies through this module keeps complying through it"
    );
    std::fs::remove_dir_all(free).unwrap();
    std::fs::remove_dir_all(paid).unwrap();
}
