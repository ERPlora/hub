//! hub#1404: the composition root is the ONLY server module allowed to mount
//! concrete native plugins («el core no nombra países» — the mounting point is
//! the single authorised exception). The split made that frontier a file
//! (`src/boot.rs`); this pins it so a later refactor cannot quietly spread
//! plugin mounting back across the server.

use std::fs;
use std::path::Path;

#[test]
fn hub1404_register_native_lives_only_in_the_composition_root() {
    let src = Path::new(env!("CARGO_MANIFEST_DIR")).join("src");
    let mut offenders = Vec::new();
    for entry in fs::read_dir(&src).expect("read crates/server/src") {
        let path = entry.expect("dir entry").path();
        if path.extension().and_then(|e| e.to_str()) != Some("rs") {
            continue;
        }
        let name = path.file_name().unwrap().to_string_lossy().into_owned();
        let text = fs::read_to_string(&path).expect("read source file");
        if text.contains("register_native(") && name != "boot.rs" {
            offenders.push(name);
        }
    }
    assert!(
        offenders.is_empty(),
        "register_native( mounted outside the composition root (boot.rs): {offenders:?}"
    );
    // Positive control: the check must be able to SEE the mounting it guards —
    // an empty boot.rs would mean the scan is looking at the wrong place.
    let boot = fs::read_to_string(src.join("boot.rs")).expect("read boot.rs");
    assert!(
        boot.contains("register_native("),
        "the composition root no longer mounts any native plugin — did the mounting move?"
    );
}
