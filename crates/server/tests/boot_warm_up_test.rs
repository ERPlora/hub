//! The boot warm-up of the WASM handlers announces its end — ALWAYS (hub#2693).
//!
//! `/readyz` says UP before the handlers are compiled (hub#926: in production nobody waits for
//! it). The CI module batteries (`scripts/ci/run-module-hub-batteries.sh`) boot a real hub per
//! module and wait for `WARM_UP_DONE` in its log before charging the first sale: on a fresh runner
//! that sale raced Cranelift and `cash_register`'s battery timed out in 2 of 3 runs. Most modules
//! are declarative (Tier 0) and bring nothing to compile, so the boot used to return early and
//! print nothing — a waiter would sit until its timeout on every one of them.

use erplora_db::testutil::fresh_db;
use erplora_runtime::wasm_cache::WARM_UP_DONE;
use erplora_runtime::Runtime;
use erplora_server::{AppState, AuthMode, HubConfig, DEV_HUB_ID};

async fn booted_hub() -> AppState {
    let db = fresh_db().await;
    erplora_runtime::migrations::ensure_table(&db)
        .await
        .unwrap();
    erplora_runtime::installer::ensure_hub_module_table(&db)
        .await
        .unwrap();
    erplora_runtime::identity::ensure_tables(&db).await.unwrap();
    erplora_runtime::system_migrations::apply(&db, DEV_HUB_ID)
        .await
        .unwrap();
    AppState::with_config(
        Runtime::new(Box::new(db)),
        HubConfig::from_env_with_auth(AuthMode::Dev),
    )
}

#[tokio::test]
async fn a_hub_without_handlers_still_announces_the_end_of_its_warm_up() {
    let state = booted_hub().await;

    let line = erplora_server::boot_warm_up::warm_up_handlers(&state).await;

    assert!(
        line.starts_with(WARM_UP_DONE),
        "the boot prints the line the batteries wait for: {line}"
    );
    assert!(
        line.contains("0/0"),
        "nothing to compile, and it says so: {line}"
    );
}
