//! hub#1407: **«the core does not name countries»** — the hub is the LEGO base
//! (país-agnóstico); everything country- or regime-specific lives in a module or in a
//! first-party plugin behind the `crates/plugins/` frontier (hub#1405), and the ONE
//! place allowed to name a concrete engine is the server's composition root
//! (`boot.rs`, hub#1404).
//!
//! Born with TRANSITIONAL exceptions (direction note on hub#1407, 2026-09-01) and
//! meant to HARDEN when the ADR «Motores de régimen fiscal en WASM del módulo con
//! primitivos de certificado del host» (ADR-0424) lands: the budgets below only ever
//! go DOWN, and at landing the composition-root and `crates/plugins/` exceptions
//! disappear too — zero country mentions in the whole hub.
//!
//! Scope: PRODUCTION code of core crates. Inline `#[cfg(test)]` modules, `tests/`
//! directories and comments are out — a fixture id or a history note is not a
//! coupling. (New fixtures should still prefer neutral regime ids: `testregime`.)

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

/// Country/regime markers, matched as lowercased substrings. When a new regime engine
/// arrives (`nf525`, `facturx`…), its name joins this list in the same PR.
const TERMS: [&str; 4] = ["verifactu", "ticketbai", "agenciatributaria", "aeat"];

/// Transitional budgets: production lines in core crates still carrying country
/// knowledge, frozen at their 2026-09-02 values. The rule is a RATCHET: shrink freely
/// (update the number down in the same PR), never grow — growth means country
/// knowledge is leaking back into the base. A file not listed here has budget 0.
const RATCHET: [(&str, usize, &str); 11] = [
    (
        "crates/server/src/boot.rs",
        2,
        "composition root — the ONE authorised engine-mounting point (hub#1404)",
    ),
    ("crates/runtime/src/errors.rs", 1, "container-kind error message"),
    ("crates/runtime/src/export.rs", 1, "verifactu_config gating in export"),
    (
        "crates/runtime/src/import.rs",
        1,
        "legacy installation-bound module list (hub#380)",
    ),
    (
        "crates/runtime/src/migration_guard.rs",
        2,
        "grandfathered destructive migrations",
    ),
    (
        "crates/runtime/src/money_backfill.rs",
        1,
        "legacy cents-backfill table list",
    ),
    (
        "crates/runtime/src/producer_facts.rs",
        5,
        "AEAT `SistemaInformatico` field names — external declaration contract (hub#323)",
    ),
    (
        "crates/runtime/src/reset.rs",
        5,
        "fiscal reset sections + RD 1007/2023 refusal",
    ),
    (
        "crates/runtime/src/settings.rs",
        3,
        "AEAT tax-id ceiling + XSD country list — external contract",
    ),
    (
        "crates/runtime/src/system_migrations.rs",
        2,
        "ES regime seed rows (data, pending migration to module-owned seeds)",
    ),
    (
        "crates/server/src/export_import.rs",
        1,
        "user-facing template message",
    ),
];

fn workspace_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

/// Production lines of one file that name a country/regime. Comment lines and inline
/// `#[cfg(test)] mod` bodies are skipped: this codebase closes those mods with a
/// column-zero `}` (everything inside is indented), which is what ends the skip.
fn country_lines(path: &Path) -> Vec<(usize, String)> {
    let text = fs::read_to_string(path).unwrap_or_default();
    let mut hits = Vec::new();
    let mut in_test = false;
    let mut pending_cfg = false;
    for (n, line) in text.lines().enumerate() {
        if in_test {
            if line == "}" {
                in_test = false;
            }
            continue;
        }
        let trimmed = line.trim_start();
        if trimmed == "#[cfg(test)]" {
            pending_cfg = true;
            continue;
        }
        if pending_cfg {
            pending_cfg = false;
            if trimmed.starts_with("mod ") {
                in_test = true;
                continue;
            }
        }
        if trimmed.starts_with("//") {
            continue;
        }
        let lower = line.to_lowercase();
        if TERMS.iter().any(|t| lower.contains(t)) {
            hits.push((n + 1, trimmed.to_string()));
        }
    }
    hits
}

/// Scan every production `.rs` under `<root>/crates`, skipping `crates/plugins/**`
/// (that is the frontier: naming a regime THERE is the point), `tests/` directories
/// and build output. Keys are workspace-relative paths.
fn scan(root: &Path) -> BTreeMap<String, Vec<(usize, String)>> {
    let mut out = BTreeMap::new();
    let mut stack = vec![root.join("crates")];
    while let Some(dir) = stack.pop() {
        let Ok(entries) = fs::read_dir(&dir) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            let name = entry.file_name().to_string_lossy().into_owned();
            if path.is_dir() {
                if name == "plugins" || name == "tests" || name == "target" {
                    continue;
                }
                stack.push(path);
            } else if name.ends_with(".rs") {
                let hits = country_lines(&path);
                if !hits.is_empty() {
                    let rel = path
                        .strip_prefix(root)
                        .unwrap_or(&path)
                        .to_string_lossy()
                        .replace('\\', "/");
                    out.insert(rel, hits);
                }
            }
        }
    }
    out
}

#[test]
fn hub1407_the_core_does_not_name_countries() {
    let budgets: BTreeMap<&str, usize> = RATCHET.iter().map(|(f, n, _)| (*f, *n)).collect();
    let mut violations = Vec::new();
    for (file, hits) in scan(&workspace_root()) {
        let budget = budgets.get(file.as_str()).copied().unwrap_or(0);
        if hits.len() > budget {
            let sample: Vec<String> = hits
                .iter()
                .take(4)
                .map(|(n, l)| format!("      {file}:{n}: {l}"))
                .collect();
            violations.push(format!(
                "  · {file}: {} country line(s), budget {budget}\n{}",
                hits.len(),
                sample.join("\n")
            ));
        }
    }
    assert!(
        violations.is_empty(),
        "\n«El core no nombra países»: el hub es la base de LEGO — lo específico de un país o \
         régimen fiscal vive en su módulo o tras la frontera `crates/plugins/` (hub#1405), y el \
         único punto autorizado a montar un motor concreto es el composition root (`boot.rs`, \
         hub#1404). Estas líneas meten conocimiento de país en la base:\n\n{}\n\n\
         Arreglo: mueve esa lógica al módulo/plugin del régimen. Si es un residuo transitorio \
         legítimo, súbele el presupuesto en la tabla RATCHET de este test EN LA MISMA PR, con su \
         porqué — el presupuesto solo debería bajar (se endurece al aterrizar ADR-0424).\n",
        violations.join("\n")
    );
}

/// The reverse ratchet: every budget matches its file EXACTLY. A file that shed lines
/// must lower its number (visible hardening); one that dropped to zero must leave the
/// table. This also proves the scanner still SEES what the budgets describe — a table
/// nobody has to touch again is a table that stopped measuring.
#[test]
fn hub1407_budgets_match_reality_exactly() {
    let found = scan(&workspace_root());
    let mut drift = Vec::new();
    for (file, budget, why) in RATCHET {
        let actual = found.get(file).map_or(0, Vec::len);
        if actual != budget {
            drift.push(format!(
                "  · {file}: budget {budget}, real {actual} ({why}) — ajusta la tabla"
            ));
        }
    }
    assert!(drift.is_empty(), "\n{}\n", drift.join("\n"));
}

/// Positive control (regla de cero regresiones): a guard that never saw red guards
/// nothing. A synthetic tree seeds one violation in `crates/runtime` — and the shapes
/// the scanner must IGNORE (a comment, a test-mod fixture, a plugins file) next to it.
#[test]
fn hub1407_the_check_catches_a_seeded_violation() {
    let root = std::env::temp_dir().join(format!("hub1407-seed-{}", std::process::id()));
    let src = root.join("crates/runtime/src");
    let plugin = root.join("crates/plugins/fake/src");
    fs::create_dir_all(&src).unwrap();
    fs::create_dir_all(&plugin).unwrap();
    fs::write(
        src.join("lib.rs"),
        "// aeat in a comment is history, not coupling\n\
         use erplora_verifactu::Engine;\n\
         #[cfg(test)]\n\
         mod tests {\n    const ID: &str = \"ticketbai\";\n}\n",
    )
    .unwrap();
    fs::write(plugin.join("lib.rs"), "pub const REGIME: &str = \"verifactu\";\n").unwrap();

    let found = scan(&root);
    let hits = found
        .get("crates/runtime/src/lib.rs")
        .expect("the seeded violation in crates/runtime MUST be caught");
    assert_eq!(
        hits,
        &vec![(2, "use erplora_verifactu::Engine;".to_string())],
        "exactly the production line — never the comment nor the test fixture"
    );
    assert!(
        !found.contains_key("crates/plugins/fake/src/lib.rs"),
        "naming a regime behind the plugins frontier is the POINT, not a violation"
    );
    fs::remove_dir_all(&root).ok();
}
