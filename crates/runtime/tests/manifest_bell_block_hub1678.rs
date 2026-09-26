//! hub#1678 — a module can put a counter on the shell's notification bell.
//!
//! The bell only knew two sources wired into the shell by hand (dead letters, stalled printing).
//! An appointment waiting for the owner to confirm it — the «I review them first» mode of
//! WhatsApp — never reached it. The fix is a manifest block, `bell`, that the SHELL reads (same
//! transport as `widgets`): the module names a query that returns `count` and the tab it leads to,
//! so the core never learns what an appointment is.
//!
//! The runtime does not act on the block, but it JUDGES it like every other block (hub#521): a
//! well-formed entry installs in silence, and a field it does not know is reported by its path.

use erplora_runtime::manifest::Manifest;

fn fixture(manifest: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-bell-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(dir.join("queries")).unwrap();
    std::fs::write(dir.join("module.json"), manifest).unwrap();
    std::fs::write(dir.join("queries/pending.sql"), "SELECT 1 AS count").unwrap();
    dir
}

fn manifest_with_bell(entry: &str) -> String {
    format!(
        r#"{{
          "id":"appointments",
          "name":"Appointments",
          "version":"1.0.0",
          "permissions":["appointments.view"],
          "queries":{{
            "appointments.pending_count":{{"permission":"appointments.view","sql":"queries/pending.sql"}}
          }},
          "bell":{{ "appointments.to_confirm": {entry} }}
        }}"#
    )
}

#[test]
fn a_well_formed_bell_entry_installs_without_a_warning() {
    let dir = fixture(&manifest_with_bell(
        r#"{"label":"Appointments to confirm","icon":"calendar-outline",
            "query":"appointments.pending_count","params":{},"nav":"agenda",
            "permission":"appointments.view"}"#,
    ));
    let manifest = Manifest::load(&dir).expect("a bell block must not refuse the module");
    assert!(
        !manifest.warnings.iter().any(|w| w.path.starts_with("bell")),
        "`bell` is a known block — it must install clean: {:?}",
        manifest.warnings
    );
    std::fs::remove_dir_all(dir).unwrap();
}

#[test]
fn an_unknown_field_inside_a_bell_entry_is_reported_by_its_path() {
    let dir = fixture(&manifest_with_bell(
        r#"{"label":"Appointments to confirm","query":"appointments.pending_count",
            "sound":"ding"}"#,
    ));
    let manifest = Manifest::load(&dir).expect("an unknown bell field warns, it does not refuse");
    assert!(
        manifest
            .warnings
            .iter()
            .any(|w| w.path == "bell.appointments.to_confirm.sound"),
        "the warning must point at the field inside the entry: {:?}",
        manifest.warnings
    );
    std::fs::remove_dir_all(dir).unwrap();
}
