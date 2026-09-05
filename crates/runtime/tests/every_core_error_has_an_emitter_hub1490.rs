//! hub#1490 — **every error code the core publishes has somebody who can EMIT it.**
//!
//! `core_errors_carry_a_code.rs` (hub#1241) pins the other half of the contract: every
//! `RuntimeError` variant maps to a stable code the shell can translate. It says nothing about
//! whether a caller can ever *receive* that code, and that is the gap this file closes.
//!
//! The case that opened it: `CertificateTypeMismatch` / `certificate_type_mismatch` existed for
//! hub#470, when the control plane DECLARED a certificate type and the hub DERIVED another, and
//! `certificate::resolve_certificate_type` refused to install on a disagreement. hub#1435 retired
//! the whole delivery — the container is now the only source of the type, so there are no two
//! answers left to disagree — and the variant stayed behind: mapped in `error_registry`, given a
//! `409` in `dispatch_api`, sampled in the census, and **impossible to produce**.
//!
//! A code nobody can emit is worse than no code at all: it promises a failure the screen will
//! never see, so it earns a translation, a branch in the UI and a line in every exhaustive `match`
//! that is dead the day it is written. The retirement of one door leaving its error behind is a
//! SHAPE, not an accident — hub#1435 did exactly that — so the guard is mechanical instead of a
//! note in a review checklist.
//!
//! # What counts as an emitter
//!
//! A **construction** of the variant in production code (`crates/**/src`, `#[cfg(test)]` modules
//! excluded): `Err(RuntimeError::Foo { .. })`, `RuntimeError::Foo(msg)`, `return Err(E::Bar)`. A
//! `match` arm is NOT an emitter — reading an error is the opposite of producing one, and every
//! orphan has plenty of arms, which is precisely why counting mentions proves nothing.
//!
//! Variants carrying `#[from]` are exempt: `?` builds them without ever naming them.

use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};

/// The `RuntimeError` enum as written — the ground truth of which variants exist. Read from the
/// source, never from a list kept here, so a variant added tomorrow is judged too.
const ERRORS_SOURCE: &str = include_str!("../src/errors.rs");

/// How a variant is written, which is what tells a construction from a pattern.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Shape {
    /// `EventLoop,`
    Unit,
    /// `Print(String)`
    Tuple,
    /// `ReadUnavailable { query: String }`
    Struct,
}

#[derive(Debug)]
struct Variant {
    name: String,
    shape: Shape,
    /// Built by `?` through a `#[from]` conversion, so nothing ever names it.
    built_by_from: bool,
}

/// Variants declared by `pub enum RuntimeError`, with their shape, read from the source.
///
/// Same parse as `core_errors_carry_a_code.rs`: a variant sits at exactly one level of
/// indentation, so doc comments, attributes and field lines are excluded by shape alone.
fn declared_variants(source: &str) -> Vec<Variant> {
    let body = source
        .split_once("pub enum RuntimeError {")
        .expect("`pub enum RuntimeError {` is the enum this test is about")
        .1;
    let body = body.split("\n}\n").next().expect("the enum closes");
    let lines: Vec<&str> = body.lines().collect();

    // Where each variant is declared, so its own block (fields + attributes) can be read back.
    let mut declared: Vec<(usize, String, Shape)> = Vec::new();
    for (n, line) in lines.iter().enumerate() {
        let Some(rest) = line.strip_prefix("    ") else {
            continue;
        };
        if rest.starts_with(' ') || rest.starts_with("//") || rest.starts_with('#') {
            continue;
        }
        let name: String = rest
            .chars()
            .take_while(char::is_ascii_alphanumeric)
            .collect();
        if name.is_empty() || !name.starts_with(char::is_uppercase) {
            continue;
        }
        let tail = &rest[name.len()..];
        let shape = if tail.starts_with('(') {
            Shape::Tuple
        } else if tail.starts_with(" {") {
            Shape::Struct
        } else if tail.starts_with(',') {
            Shape::Unit
        } else {
            continue;
        };
        declared.push((n, name, shape));
    }

    (0..declared.len())
        .map(|i| {
            let (start, ref name, shape) = declared[i];
            let end = declared.get(i + 1).map_or(lines.len(), |next| next.0);
            Variant {
                name: name.clone(),
                shape,
                built_by_from: lines[start..end].iter().any(|l| l.contains("#[from]")),
            }
        })
        .collect()
}

// ── Reading production code ───────────────────────────────────────────────────────────────────

fn workspace_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

/// Every `.rs` under `crates/` that is PRODUCTION code: `src/`, minus the `tests/` directories.
/// An error only a test can build is exactly the orphan this guard is looking for.
fn production_sources(dir: &Path, out: &mut Vec<PathBuf>) {
    let Ok(entries) = fs::read_dir(dir) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        let name = entry.file_name();
        let name = name.to_string_lossy();
        if path.is_dir() {
            if name != "tests" && name != "target" && name != "node_modules" {
                production_sources(&path, out);
            }
        } else if name.ends_with(".rs") {
            out.push(path);
        }
    }
}

/// The file without its `#[cfg(test)]` module and without `//` lines, keeping the line count so a
/// reported line number still points where a reader can look.
fn production_half(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    let mut in_test = false;
    for line in text.lines() {
        let trimmed = line.trim_start();
        if trimmed == "#[cfg(test)]" {
            in_test = true;
            out.push('\n');
            continue;
        }
        if in_test {
            if line == "}" {
                in_test = false;
            }
            out.push('\n');
            continue;
        }
        if trimmed.starts_with("//") {
            out.push('\n');
            continue;
        }
        out.push_str(line);
        out.push('\n');
    }
    out
}

// ── Telling a construction from a pattern ─────────────────────────────────────────────────────

fn is_word_byte(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'_'
}

/// Byte offset of the delimiter closing the one at `open_at`.
fn closing(text: &str, open_at: usize, open: u8, close: u8) -> Option<usize> {
    let bytes = text.as_bytes();
    let mut depth = 0usize;
    for (i, &b) in bytes.iter().enumerate().skip(open_at) {
        if b == open {
            depth += 1;
        } else if b == close {
            depth -= 1;
            if depth == 0 {
                return Some(i);
            }
        }
    }
    None
}

fn next_non_space(text: &str, from: usize) -> usize {
    let bytes = text.as_bytes();
    let mut i = from;
    while i < bytes.len() && (bytes[i] == b' ' || bytes[i] == b'\n') {
        i += 1;
    }
    i
}

/// Does `text` CONSTRUCT `variant` anywhere?
///
/// The discriminator is the delimiter, not the mention:
///
/// * a struct variant's braces hold `..` in a pattern (`E::Foo { .. }`, `E::Foo { code, .. }`) and
///   never in a construction;
/// * a tuple variant's parens hold `_` or `..` in a pattern and a real argument in a construction;
/// * after the closing delimiter (past any `)` the pattern is nested in), a `=>` means a `match`
///   arm and a lone `=` means an `if let`. Both read the error; neither makes one.
fn constructs(text: &str, variant: &Variant) -> Option<usize> {
    let bytes = text.as_bytes();
    for path in ["RuntimeError::", "Self::", "E::"] {
        let needle = format!("{path}{}", variant.name);
        for (at, _) in text.match_indices(&needle) {
            // `SomeOtherE::Foo` is not `E::Foo`; `crate::errors::RuntimeError::Foo` IS the path.
            if at > 0 && is_word_byte(bytes[at - 1]) {
                continue;
            }
            let after_name = at + needle.len();
            // `Manifest` must not match inside `ManifestRejected`.
            if after_name < bytes.len() && is_word_byte(bytes[after_name]) {
                continue;
            }
            let open = next_non_space(text, after_name);
            let end = match variant.shape {
                Shape::Struct => {
                    if bytes.get(open) != Some(&b'{') {
                        continue;
                    }
                    let Some(end) = closing(text, open, b'{', b'}') else {
                        continue;
                    };
                    if text[open..end].contains("..") {
                        continue; // a rest pattern: `{ .. }`, `{ code, .. }`
                    }
                    end
                }
                Shape::Tuple => {
                    if bytes.get(open) != Some(&b'(') {
                        continue;
                    }
                    let Some(end) = closing(text, open, b'(', b')') else {
                        continue;
                    };
                    let inside = text[open + 1..end].trim();
                    if inside == "_" || inside == ".." {
                        continue; // `E::Foo(_)`
                    }
                    end
                }
                Shape::Unit => {
                    if matches!(bytes.get(open), Some(b'{') | Some(b'(')) {
                        continue; // shape mismatch: not the variant this parse declared
                    }
                    if text[..at].trim_end().ends_with('|') {
                        continue; // `| E::Bar` — an alternative in a pattern
                    }
                    after_name - 1
                }
            };
            // Past the `)` of an `Err(...)`/`Some(...)` the pattern may be wrapped in.
            let mut tail = next_non_space(text, end + 1);
            while bytes.get(tail) == Some(&b')') {
                tail = next_non_space(text, tail + 1);
            }
            let rest = &text[tail..];
            if rest.starts_with("=>") {
                continue; // a `match` arm
            }
            if rest.starts_with('=') && !rest.starts_with("==") {
                continue; // an `if let` / `while let` binding
            }
            return Some(text[..at].matches('\n').count() + 1);
        }
    }
    None
}

// ── The guard ─────────────────────────────────────────────────────────────────────────────────

/// A variant with each shape, so the positive control below exercises all three parses.
fn control_variants() -> Vec<Variant> {
    ["Foo", "Bar", "Baz"]
        .into_iter()
        .zip([Shape::Struct, Shape::Tuple, Shape::Unit])
        .map(|(name, shape)| Variant {
            name: name.to_string(),
            shape,
            built_by_from: false,
        })
        .collect()
}

/// 🔒 The detector SEES a construction and does NOT see a pattern.
///
/// A guard that cannot find what it forbids is a green light with no lamp behind it, and this one
/// fails open by construction: an orphan is proved by an ABSENCE. So the absence is only worth
/// something once the presence has been shown here.
#[test]
fn the_detector_tells_a_construction_from_a_match_arm() {
    let v = control_variants();
    let (struct_v, tuple_v, unit_v) = (&v[0], &v[1], &v[2]);

    // Constructions — every shape, in the forms production actually writes.
    for (code, variant) in [
        (
            "        return Err(RuntimeError::Foo { a: 1, b: 2 });",
            struct_v,
        ),
        ("        Err(RuntimeError::Foo { missing })", struct_v),
        (
            "    .map_err(|e| RuntimeError::Bar(e.to_string()))?;",
            tuple_v,
        ),
        ("        return Err(RuntimeError::Baz);", unit_v),
        (
            "        Some(crate::errors::RuntimeError::Foo { a: 1 })",
            struct_v,
        ),
    ] {
        assert!(
            constructs(code, variant).is_some(),
            "the detector missed a construction it has to see: {code}"
        );
    }

    // Patterns — reading an error is not producing one.
    for (code, variant) in [
        (
            "        E::Foo { .. } => (StatusCode::CONFLICT, \"foo\".into()),",
            struct_v,
        ),
        ("        E::Foo { code, .. } => code.as_str(),", struct_v),
        ("    if let E::Foo { a } = e {", struct_v),
        (
            "        Err(RuntimeError::Foo { a }) => other(a),",
            struct_v,
        ),
        ("        | E::Bar(_)", tuple_v),
        ("        E::Bar(_) => \"bar\",", tuple_v),
        ("        | E::Baz", unit_v),
        ("        E::Baz => \"baz\",", unit_v),
    ] {
        assert!(
            constructs(code, variant).is_none(),
            "the detector counted a `match` arm as an emitter: {code}"
        );
    }

    // A longer name is a different variant, not a hit on the shorter one.
    assert!(
        constructs(
            "        return Err(RuntimeError::FooBar { a: 1 });",
            struct_v
        )
        .is_none(),
        "`Foo` must not match inside `FooBar`"
    );
}

/// 🔒 No `RuntimeError` variant is left without somebody who can produce it.
#[test]
fn every_core_error_variant_has_a_production_emitter_hub1490() {
    let variants = declared_variants(ERRORS_SOURCE);
    assert!(
        variants.len() > 40,
        "the source parse found only {} variants — it stopped matching the enum's shape",
        variants.len()
    );

    let mut files = Vec::new();
    production_sources(&workspace_root().join("crates"), &mut files);
    assert!(
        files.len() > 50,
        "only {} production sources found — the walk is not reaching `crates/`",
        files.len()
    );

    let sources: Vec<String> = files
        .iter()
        .map(|p| production_half(&fs::read_to_string(p).expect("a source file reads")))
        .collect();

    let orphans: BTreeSet<&str> = variants
        .iter()
        .filter(|v| !v.built_by_from)
        .filter(|v| !sources.iter().any(|s| constructs(s, v).is_some()))
        .map(|v| v.name.as_str())
        .collect();

    assert!(
        orphans.is_empty(),
        "these `RuntimeError` variants have a stable code and a `match` arm everywhere, but no \
         production code can BUILD them, so no caller can ever receive that code: {orphans:?}. \
         Either retire the variant (its code, its arms and its census sample with it) or give it \
         the emitter that justifies it — a promise of a failure the screen never sees is worse \
         than no code at all (hub#1490)."
    );
}
