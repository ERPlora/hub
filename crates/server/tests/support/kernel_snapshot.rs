//! Compare a surface generated from the code with the file committed in `contracts/kernel/`.
//!
//! ERPlora/hub#1235 — the kernel contract as a committed artefact. The mechanism is the one
//! Kotlin (`apiCheck`), .NET (`PublicApiAnalyzers`) and `cargo-semver-checks` use: the public
//! surface lives in a file, a test regenerates it from the code, and the build breaks when the two
//! disagree. Regenerating is an explicit command, and the resulting diff is what a human reviews.
//!
//! Shared by every `kernel_contract_*` target of this crate; the same 60 lines live next to the
//! server's own target, because a dev-only crate to share them would be a heavier contract than
//! the one it serves.
#![allow(dead_code)]

use std::collections::BTreeSet;
use std::path::PathBuf;

/// `1` rewrites the committed snapshot instead of failing. Deliberately an environment variable
/// and not a test flag: `cargo test` refuses arguments libtest does not know.
pub const UPDATE_ENV: &str = "UPDATE_KERNEL_CONTRACT";

/// `<repo>/contracts/kernel/<name>`.
pub fn snapshot_path(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../contracts/kernel")
        .join(name)
}

/// Fails naming the added and the removed lines, and says how to update the file.
///
/// `generated` is what the code says today; the file is what the last `kind:contract` pull request
/// agreed to. Line order is the generator's, so both sides are compared as text AND as sets: the
/// set difference is what a reviewer needs to read, the text equality is what keeps the file
/// stable.
pub fn assert_snapshot(name: &str, generated: &str) {
    let path = snapshot_path(name);
    if std::env::var(UPDATE_ENV).as_deref() == Ok("1") {
        std::fs::create_dir_all(path.parent().expect("contracts/kernel"))
            .expect("crear el directorio del contrato");
        std::fs::write(&path, generated).expect("reescribir el snapshot");
        return;
    }
    let committed = match std::fs::read_to_string(&path) {
        Ok(text) => text,
        Err(e) => panic!(
            "`contracts/kernel/{name}` no se puede leer ({e}).\n\
             Es parte del contrato del kernel y va COMMITEADO. Genéralo con:\n  \
             {UPDATE_ENV}=1 cargo test -p {} --test {}",
            env!("CARGO_PKG_NAME"),
            current_target(),
        ),
    };
    if committed == generated {
        return;
    }
    let old: BTreeSet<&str> = committed.lines().collect();
    let new: BTreeSet<&str> = generated.lines().collect();
    let added: Vec<&&str> = new.difference(&old).collect();
    let removed: Vec<&&str> = old.difference(&new).collect();
    panic!(
        "`contracts/kernel/{name}` ya no describe el código.\n\
         \n  AÑADIDO por el código ({} línea/s):\n{}\
         \n  QUE FALTA en el código ({} línea/s):\n{}\
         \n\
         Cambiar esta superficie es una PR `kind:contract` con entrada en el decision-log \
         (ADR «El Hub se CIERRA como KERNEL»). Si el cambio es el que querías, regenera el \
         fichero y revisa el diff:\n  \
         {UPDATE_ENV}=1 cargo test -p {} --test {}\n",
        added.len(),
        render(&added, '+'),
        removed.len(),
        render(&removed, '-'),
        env!("CARGO_PKG_NAME"),
        current_target(),
    );
}

fn render(lines: &[&&str], marker: char) -> String {
    if lines.is_empty() {
        return "    (ninguna)\n".to_string();
    }
    lines
        .iter()
        .map(|l| format!("    {marker} {l}\n"))
        .collect()
}

/// Name of the integration-test binary that is running, so the failure can print the exact
/// command that regenerates this very file.
fn current_target() -> String {
    std::env::current_exe()
        .ok()
        .and_then(|p| p.file_name().map(|n| n.to_string_lossy().to_string()))
        .and_then(|n| n.rsplit_once('-').map(|(stem, _hash)| stem.to_string()))
        .unwrap_or_else(|| "kernel_contract_…".to_string())
}
