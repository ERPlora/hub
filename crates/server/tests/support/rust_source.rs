//! A very small reader of this crate's own Rust source: enough to answer "which routes does
//! `app()` register, and which authentication primitive gates each one".
//!
//! ERPlora/hub#1235. Reading the source is deliberate. `axum::Router` does not expose its table,
//! so the alternatives were a second, hand-written route list next to `app()` — the very drift the
//! contract exists to stop — or this. It is the same trade every public-API snapshot tool makes.
//!
//! It is NOT a Rust parser and does not pretend to be one. It blanks comments and literals first
//! (keeping byte offsets, so the original text can still be read at the same positions), then
//! matches braces and parentheses. Anything it cannot resolve stays out of the answer instead of
//! being guessed.
#![allow(dead_code)]

use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

/// Every `.rs` under `src/`, keyed by module name (the file stem).
pub fn crate_sources() -> BTreeMap<String, String> {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("src");
    read_dir_rs(&dir)
}

pub fn read_dir_rs(dir: &Path) -> BTreeMap<String, String> {
    let mut out = BTreeMap::new();
    let entries = std::fs::read_dir(dir).unwrap_or_else(|e| panic!("leer {}: {e}", dir.display()));
    for entry in entries {
        let path = entry.expect("entrada de directorio").path();
        if path.extension().and_then(|e| e.to_str()) != Some("rs") {
            continue;
        }
        let stem = path
            .file_stem()
            .expect("nombre de fichero")
            .to_string_lossy()
            .to_string();
        out.insert(
            stem,
            std::fs::read_to_string(&path)
                .unwrap_or_else(|e| panic!("leer {}: {e}", path.display())),
        );
    }
    out
}

/// A copy of `src` with the same byte length where every comment and every literal body is
/// spaces. Same length is the point: a match found here can be read back from the original at the
/// identical offset, so `/// calls require_admin_session` in a doc comment stops looking like a
/// call while `"/api/settings"` can still be recovered as a path.
pub fn blank_noise(src: &str) -> String {
    let b = src.as_bytes();
    let mut out = b.to_vec();
    let mut i = 0usize;
    let blank = |out: &mut Vec<u8>, at: usize| {
        if out[at] != b'\n' {
            out[at] = b' ';
        }
    };
    while i < b.len() {
        // Raw string: r"…", r#"…"#, r##"…"##
        if b[i] == b'r' && i + 1 < b.len() && (b[i + 1] == b'"' || b[i + 1] == b'#') {
            let mut hashes = 0usize;
            let mut j = i + 1;
            while j < b.len() && b[j] == b'#' {
                hashes += 1;
                j += 1;
            }
            if j < b.len() && b[j] == b'"' {
                j += 1;
                while j < b.len() {
                    if b[j] == b'"'
                        && b[j + 1..].iter().take(hashes).all(|c| *c == b'#')
                        && j + hashes < b.len()
                    {
                        j += 1 + hashes;
                        break;
                    }
                    blank(&mut out, j);
                    j += 1;
                }
                i = j;
                continue;
            }
        }
        match b[i] {
            b'/' if b.get(i + 1) == Some(&b'/') => {
                while i < b.len() && b[i] != b'\n' {
                    blank(&mut out, i);
                    i += 1;
                }
            }
            b'/' if b.get(i + 1) == Some(&b'*') => {
                let mut depth = 1usize;
                blank(&mut out, i);
                blank(&mut out, i + 1);
                i += 2;
                while i < b.len() && depth > 0 {
                    if b[i] == b'/' && b.get(i + 1) == Some(&b'*') {
                        depth += 1;
                    } else if b[i] == b'*' && b.get(i + 1) == Some(&b'/') {
                        depth -= 1;
                        blank(&mut out, i);
                        blank(&mut out, i + 1);
                        i += 2;
                        continue;
                    }
                    blank(&mut out, i);
                    i += 1;
                }
            }
            b'"' => {
                i += 1;
                while i < b.len() && b[i] != b'"' {
                    if b[i] == b'\\' {
                        blank(&mut out, i);
                        i += 1;
                    }
                    if i < b.len() {
                        blank(&mut out, i);
                        i += 1;
                    }
                }
                i += 1;
            }
            // A char literal, never a lifetime: `'x'`, `'\n'`. `'a` / `'static` have no closer.
            b'\'' if b.get(i + 1) == Some(&b'\\') || b.get(i + 2) == Some(&b'\'') => {
                i += 1;
                while i < b.len() && b[i] != b'\'' {
                    blank(&mut out, i);
                    i += 1;
                }
                i += 1;
            }
            _ => i += 1,
        }
    }
    String::from_utf8(out).expect("blanquear solo sustituye bytes completos por espacios")
}

/// End offset (exclusive) of the block that opens with `{` at `open`, in already-blanked text.
pub fn block_end(blanked: &str, open: usize) -> usize {
    let b = blanked.as_bytes();
    let mut depth = 0usize;
    let mut i = open;
    while i < b.len() {
        match b[i] {
            b'{' => depth += 1,
            b'}' => {
                depth -= 1;
                if depth == 0 {
                    return i + 1;
                }
            }
            _ => {}
        }
        i += 1;
    }
    b.len()
}

/// End offset (exclusive) of the argument list that opens with `(` at `open`.
pub fn paren_end(blanked: &str, open: usize) -> usize {
    let b = blanked.as_bytes();
    let mut depth = 0usize;
    let mut i = open;
    while i < b.len() {
        match b[i] {
            b'(' => depth += 1,
            b')' => {
                depth -= 1;
                if depth == 0 {
                    return i + 1;
                }
            }
            _ => {}
        }
        i += 1;
    }
    b.len()
}

/// Bodies of every `fn` and `macro_rules!` of the crate, keyed by `(module, name)`.
///
/// The bodies are the BLANKED text: what is looked up in them are calls, and a call named inside a
/// comment or a string is not a call.
pub fn item_bodies(sources: &BTreeMap<String, String>) -> BTreeMap<(String, String), String> {
    let mut out = BTreeMap::new();
    for (module, raw) in sources {
        let text = blank_noise(raw);
        for (keyword, skip) in [("fn ", 3usize), ("macro_rules!", 12usize)] {
            let mut from = 0usize;
            while let Some(rel) = text[from..].find(keyword) {
                let at = from + rel;
                from = at + skip;
                if at > 0 && is_ident_byte(text.as_bytes()[at - 1]) {
                    continue; // `…_fn ` and friends
                }
                let name_start = from + text[from..].len() - text[from..].trim_start().len();
                let name_end = name_start
                    + text[name_start..]
                        .find(|c: char| !(c.is_ascii_alphanumeric() || c == '_'))
                        .unwrap_or(0);
                if name_end == name_start {
                    continue;
                }
                let name = text[name_start..name_end].to_string();
                let Some(rel_open) = text[name_end..].find('{') else {
                    continue;
                };
                let open = name_end + rel_open;
                out.entry((module.clone(), name))
                    .or_insert_with(|| text[open..block_end(&text, open)].to_string());
            }
        }
    }
    out
}

fn is_ident_byte(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'_'
}

/// Names this body calls: `foo(`, `mod::foo(` and `foo!`, normalised to at most `mod::name`.
pub fn called_names(body: &str) -> BTreeSet<String> {
    let b = body.as_bytes();
    let mut out = BTreeSet::new();
    let mut i = 0usize;
    while i < b.len() {
        if !(b[i].is_ascii_alphabetic() || b[i] == b'_') || (i > 0 && is_ident_byte(b[i - 1])) {
            i += 1;
            continue;
        }
        let start = i;
        while i < b.len()
            && (is_ident_byte(b[i])
                || (b[i] == b':'
                    && b.get(i + 1) == Some(&b':')
                    && b.get(i + 2).is_some_and(|c| is_ident_byte(*c))))
        {
            if b[i] == b':' {
                i += 2;
            } else {
                i += 1;
            }
        }
        let path = &body[start..i];
        let mut j = i;
        while j < b.len() && (b[j] == b' ' || b[j] == b'\n' || b[j] == b'\t') {
            j += 1;
        }
        if j < b.len() && (b[j] == b'(' || b[j] == b'!') {
            let segments: Vec<&str> = path.split("::").collect();
            let tail: String = segments[segments.len().saturating_sub(2)..].join("::");
            out.insert(tail);
        }
    }
    out
}
