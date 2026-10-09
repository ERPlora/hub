//! Boot warm-up of the WASM handlers (hub#926), and the line that announces its end (hub#2693).
//!
//! The wasmtime disk cache lives INSIDE the container, so a deploy starts it empty: measured in
//! production, the first two sales after a deploy cost 8.2 s and 5.7 s, the next ones 75-91 ms.
//! Compiling has to happen anyway; what is chosen here is to do it while nobody is waiting, not
//! on the first charge of the day.
//!
//! In its own task and AFTER binding, like the rest of the boot: the hub already serves, and if the
//! warm-up is slow — or a module brings broken bytes — it delays and breaks nothing.

use crate::AppState;

/// Starts the warm-up in the background and prints its end on stderr (the hub log).
pub fn spawn(state: &AppState) {
    let state = state.clone();
    tokio::spawn(async move { eprintln!("{}", warm_up_handlers(&state).await) });
}

/// Compiles the handlers of the installed modules and returns the line that announces the end
/// (`erplora_runtime::wasm_cache::WARM_UP_DONE`).
///
/// Returned ALWAYS — with no handlers too: the CI module batteries wait for that line before
/// their first sale, and most modules are declarative and bring nothing to compile.
pub async fn warm_up_handlers(state: &AppState) -> String {
    // The cache (an `Arc` shared with the registry) is taken and the runtime lock RELEASED before
    // compiling: warming up must not block whoever is charging.
    let (cache, modules) = {
        let rt = state.runtime.read().await;
        (
            std::sync::Arc::clone(&rt.registry().wasm_cache),
            rt.registry().handlers_to_warm_up(),
        )
    };
    // `spawn_blocking`: compiling is CPU work and must not hold an async worker.
    match tokio::task::spawn_blocking(move || {
        erplora_runtime::wasm_cache::warm_up_report(
            &cache,
            &modules,
            erplora_runtime::wasm_cache::Limits::from_env(),
        )
    })
    .await
    {
        Ok(line) => line,
        Err(e) => format!("wasm: warm-up aborted: {e}"),
    }
}
