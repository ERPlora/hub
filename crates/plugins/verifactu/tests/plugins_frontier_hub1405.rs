//! hub#1405: the base↔piece frontier is READABLE in the workspace tree — the engine
//! lives under `crates/plugins/`, and its two external contracts survive the move:
//! the package name (`cargo test -p erplora-verifactu`, CI/gate scripts) and the
//! marketplace module id `"verifactu"` mounted by the server's composition root.

use std::path::PathBuf;

#[test]
fn hub1405_the_engine_lives_behind_the_plugins_frontier() {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    assert!(
        manifest_dir.ends_with("crates/plugins/verifactu"),
        "the engine moved out of crates/plugins/: {}",
        manifest_dir.display()
    );
    assert_eq!(env!("CARGO_PKG_NAME"), "erplora-verifactu");
}

#[test]
fn hub1405_the_marketplace_module_id_stays_verifactu() {
    let boot = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../server/src/boot.rs");
    let text = std::fs::read_to_string(&boot).expect("read server boot.rs");
    assert!(
        text.contains("\"verifactu\""),
        "the composition root no longer mounts the module id \"verifactu\" — that id is an \
         external contract (module manifest + marketplace) and must never be renamed"
    );
}
