//! The hub's own architecture doc cannot bury a printer transport this crate still ships — hub#1562.
//!
//! `ARQUITECTURA.md` kept saying "USB se sigue descartando" (§2.7) and "Transporte: solo RED/LAN
//! (USB/Bluetooth descartados por drivers/mantenimiento)" (§14) long after hub#1083 landed the OS
//! print queue. That doc is what a person — or an agent — reads BEFORE touching printing, so a
//! stale sentence there does not merely age: it teaches the opposite of what the code does, and the
//! reader has no reason to doubt it.
//!
//! The guard is a cross-check between two independent artifacts, never a copy of the prose. The
//! transports come from [`parse_print_target`], the crate's real front door, and the doc has to
//! name every shape that door still accepts while declaring none of them dead. Delete the USB
//! transport for real and its sample id stops parsing, so the doc is free to bury it again.
//!
//! What it catches is the BLANKET verdict — "USB se sigue descartando", with nothing qualifying it.
//! Saying USB is out on Android, on Windows, or through `libusb`/WebUSB/OPOS is true today and has
//! to stay writable, so a sentence that names one of those is left alone. `escritorio`/`macOS`/
//! `Linux` are deliberately NOT on that list: that is where the queue prints, so burying USB there
//! is the regression itself. When hub#1269 lands USB on Windows, `Windows` comes off the list in
//! the same commit.

use erplora_peripherals::discovery::{parse_print_target, PrintTarget};

/// The doc, pulled in at compile time: moving or renaming it cannot leave this test green.
const ARQUITECTURA: &str = include_str!("../../../ARQUITECTURA.md");

/// One `printer_id` per transport the crate is meant to accept today.
const SAMPLE_IDS: [&str; 3] = [
    "network:192.168.1.50:9100",
    "bluetooth:00:11:22:33:44:55",
    "usb:Star_TSP100_Cutter",
];

/// Words this doc uses to declare a transport dead. `descart` covers descartado/descartados/
/// descartando; the other two are how §14 used to phrase the same verdict.
const BURIAL_WORDS: [&str; 3] = ["descart", "red-only", "solo red"];

/// What narrows a burial down to something that is TRUE, and so may keep being written.
///
/// Every one of these is a place USB really does not reach: Android (Kotlin, an intent-granted
/// permission and OTG cables), Windows (hub#1269, no machine to verify it on), iOS, and the three
/// library routes that would each bring back a driver per OS. Desktop is absent on purpose.
const LEGITIMATE_QUALIFIERS: [&str; 6] = ["android", "windows", "ios", "libusb", "webusb", "opos"];

/// How the doc has to name the transport behind a parsed target.
///
/// Exhaustive on purpose: a fourth `PrintTarget` variant stops this file compiling until someone
/// says how `ARQUITECTURA.md` names it. That is the point — the doc gets updated with the code, not
/// a month later.
fn documented_shape(target: &PrintTarget) -> &'static str {
    match target {
        PrintTarget::Network(_) => "network:{ip}:{port}",
        PrintTarget::Bluetooth(_) => "bluetooth:{mac}",
        PrintTarget::Usb(_) => "usb:{queue}",
    }
}

/// The doc as sentences, with the hard wrapping undone — a claim split across two lines, or sitting
/// inside a table row, is still one claim.
fn sentences(doc: &str) -> Vec<String> {
    doc.split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .split(". ")
        .map(str::to_owned)
        .collect()
}

/// Whether `text` talks about USB the transport, and not about `libusb` or `WebUSB` — both of which
/// §2.7 names precisely to say they stay out, and neither of which is what we ship.
fn mentions_usb(text: &str) -> bool {
    let bytes = text.as_bytes();
    text.match_indices("USB").any(|(start, _)| {
        let before_ok = start == 0 || !bytes[start - 1].is_ascii_alphanumeric();
        let end = start + "USB".len();
        let after_ok = end >= bytes.len() || !bytes[end].is_ascii_alphanumeric();
        before_ok && after_ok
    })
}

/// hub#1562: no sentence may declare USB dead while `parse_print_target` still takes a queue.
#[test]
fn hub1562_arquitectura_does_not_bury_the_usb_transport() {
    let usb_is_alive = parse_print_target("usb:Star_TSP100_Cutter").is_ok();
    assert!(
        usb_is_alive,
        "the crate no longer parses a `usb:{{queue}}` printer id. If the OS-queue transport was \
         removed on purpose, this test and ARQUITECTURA.md §2.7 have to be retired together — \
         which is the whole point of asking the code first"
    );

    let buried: Vec<String> = sentences(ARQUITECTURA)
        .into_iter()
        .filter(|sentence| {
            let lowered = sentence.to_lowercase();
            mentions_usb(sentence)
                && BURIAL_WORDS.iter().any(|word| lowered.contains(word))
                && !LEGITIMATE_QUALIFIERS
                    .iter()
                    .any(|qualifier| lowered.contains(qualifier))
        })
        .collect();

    assert!(
        buried.is_empty(),
        "ARQUITECTURA.md declares USB discarded while `crates/peripherals/src/usb.rs` prints \
         through the OS queue (hub#1083). Offending sentence(s):\n  - {}\n\nA blanket verdict is \
         what this catches. If USB is out somewhere in particular, name it — Android, Windows, \
         `libusb`/WebUSB/OPOS — and the sentence is left alone. Desktop is not on that list.",
        buried
            .iter()
            .map(|sentence| sentence.trim())
            .collect::<Vec<_>>()
            .join("\n  - ")
    );
}

/// hub#1562: every transport the front door still accepts has to be named in the doc.
#[test]
fn hub1562_arquitectura_names_every_transport_the_crate_accepts() {
    let missing: Vec<&str> = SAMPLE_IDS
        .iter()
        .filter_map(|id| parse_print_target(id).ok())
        .map(|target| documented_shape(&target))
        .filter(|shape| !ARQUITECTURA.contains(shape))
        .collect();

    assert!(
        missing.is_empty(),
        "`parse_print_target` accepts these transports and ARQUITECTURA.md never names them: {}. \
         The doc is what gets read before touching printing, so a transport it does not mention \
         does not exist for the reader.",
        missing.join(", ")
    );
}
