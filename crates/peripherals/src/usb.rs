//! USB printing through the operating system's own print queue — desktop only (hub#1083).
//!
//! The transport is CUPS on macOS and Linux: `lp -d <queue> -o raw` hands our already-rendered
//! ESC/POS straight to the spooler, filters bypassed. That indirection is the whole point of the
//! design. The standing "red-only" decision (ADR-0196 §4; `ARQUITECTURA.md` §2.7 in the hub's own
//! doc) refused USB because *a driver per
//! operating system does not scale* — and that is still true. What changed is that we no longer
//! need one: the vendor (Star, Epson) already ships the CUPS driver, the OS already owns the
//! cable, and ESC/POS is already the universal language we generate. So the generic transport is
//! the queue, not a USB library.
//!
//! Deliberately NOT here:
//!   - **Windows** (`OpenPrinter`/`StartDocPrinter`/`WritePrinter`) — the same idea against the
//!     other spooler, but it cannot be verified without a real Windows machine, and a print path
//!     that is green in tests and broken at the counter is how the queue's bugs got in. hub#1269.
//!   - **Android** — deliberate (hub#1083): the SPP transport of ADR-0204 already covers the cheap
//!     printer there, and USB Host means Kotlin, an intent-granted permission and OTG cables.
//!   - **`libusb` / WebUSB / OPOS** — each one re-introduces the per-OS driver problem.
//!   - **A role (kitchen/bar/receipt) on a USB queue** — the device registry keys on the MAC or
//!     on `ip:port`, and a queue has neither, so every USB printer would collapse onto one key and
//!     overwrite the previous. Discovering and printing do not need the registry; giving it a
//!     proper identity is hub#1536.

use std::collections::HashSet;
use std::io::{Read, Write};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

use crate::discovery::{is_cups_queue_name, UsbTarget};
use crate::protocol::{default_printer_category, PrinterInfo};
use crate::{PeripheralError, Result};

/// The CUPS client that submits a job.
pub const CUPS_LP: &str = "lp";
/// The CUPS client that lists destinations and their device URIs.
pub const CUPS_LPSTAT: &str = "lpstat";

/// How long a CUPS client gets before we give up on it.
///
/// Not a formality: when `cupsd` wedges, `lp` blocks on its socket and never returns. Without a
/// deadline that is a till frozen on the press that prints the ticket — the cashier's only way out
/// being to kill the app. Twenty seconds is far beyond a healthy submit (milliseconds) and still
/// short enough that the error reaches the screen while the customer is still standing there.
pub const CUPS_TIMEOUT: Duration = Duration::from_secs(20);

/// How often the wait wakes up to check on the child.
const POLL_INTERVAL: Duration = Duration::from_millis(20);

/// Job title, so a stuck ticket is identifiable in the OS queue window instead of being an
/// anonymous "Untitled" the user cannot connect to the till.
const JOB_TITLE: &str = "ERPlora";

/// The device-URI scheme the CUPS USB backend uses. Queues on any other scheme are network
/// printers the sweep already finds, and listing them twice would turn one printer into two.
const USB_DEVICE_URI_SCHEME: &str = "usb://";

/// Thermal receipt width, in millimetres — the same assumption the network sweep makes.
const DEFAULT_PAPER_WIDTH: u32 = 80;

/// What a CUPS client command answered.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CupsOutput {
    /// Whether the process exited 0.
    pub success: bool,
    pub stdout: String,
    pub stderr: String,
}

/// Runs a CUPS client binary — the seam between this module and the machine.
///
/// It exists so the transport can be tested at all: a unit test that really spawned `lp` would
/// either print on the developer's desk or fail on every machine without a printer, so neither
/// outcome would mean anything. [`SystemCups`] is the real one.
pub trait CupsClient {
    /// Runs `program` with `args`, feeding `stdin`, and waits for it (bounded by [`CUPS_TIMEOUT`]).
    fn run(&self, program: &str, args: &[&str], stdin: &[u8]) -> Result<CupsOutput>;
}

/// The argv for submitting raw bytes to `queue`.
///
/// `-o raw` is the load-bearing flag: it marks the job `application/vnd.cups-raw`, which tells
/// CUPS to skip its filter chain and hand the bytes to the backend untouched. Without it the
/// spooler would try to *render* our ESC/POS as if it were a document, and what comes out of the
/// printer is a page of garbage instead of a receipt.
pub fn lp_args(queue: &str) -> Vec<&str> {
    vec!["-d", queue, "-t", JOB_TITLE, "-o", "raw"]
}

/// Sends already-rendered ESC/POS to the printer behind an OS print queue.
///
/// Direct, not queued — the same phase-1 shape Bluetooth has (ADR-0204). [`crate::queue`] is the
/// NETWORK path: its jobs carry a socket target and its retry policy is written around a TCP
/// connect. Widening it to cover a spooler is a real change to the one piece of the print chain
/// that already works, so it is not smuggled in here. The failure stays visible either way: the
/// error comes straight back to the caller and the print host reports the job `failed`.
///
/// `Ok` means the SPOOLER took the job, which is as far as `lp` can see. A printer that is out of
/// paper, unplugged or paused keeps the job held in the OS queue — under the title `ERPlora`, so it
/// can be told apart there — and `lp` still exits 0. What does come back as an error is the spooler
/// refusing: a queue that does not exist, is disabled or is rejecting jobs, with `lp`'s own sentence
/// in it.
pub fn send_raw(client: &dyn CupsClient, target: &UsbTarget, payload: &[u8]) -> Result<()> {
    let out = client.run(CUPS_LP, &lp_args(&target.queue), payload)?;
    if out.success {
        return Ok(());
    }
    // `lp` says WHY on stderr ("paper out", "printer disabled", "does not exist"). Dropping it
    // would leave the cashier with a ticket that never printed and no way to know it.
    let reason = first_meaningful_line(&out.stderr)
        .or_else(|| first_meaningful_line(&out.stdout))
        .unwrap_or("no reason given");
    Err(PeripheralError::Unreachable(format!(
        "the OS print queue `{}` refused the job: {reason}",
        target.queue
    )))
}

/// The first line with something in it — `lp` puts the useful sentence first and can pad the rest.
fn first_meaningful_line(text: &str) -> Option<&str> {
    text.lines().map(str::trim).find(|l| !l.is_empty())
}

/// The USB print queues the OS knows about, out of two `lpstat` listings: `-e`, the bare
/// destination names, and `-v`, each destination's device URI.
///
/// Two listings because `lpstat -v` is LOCALISED: `device for <queue>: <uri>` in the C locale,
/// `dispositivo para …` on a Spanish Mac, `<queue> のデバイス: …` in Japanese — and macOS picks that
/// language from the system preference (`AppleLanguages`), not from `LANG`/`LC_ALL`, so forcing a
/// locale on the child does not help. What no translation moves is that the line carries the queue
/// name as a word of its own and ends with the URI; and `lpstat -e` prints the names untranslated.
/// So each line is matched against those names instead of against a template we would have to
/// guess per language.
///
/// The URI is the only thing that says which cable a queue is on, and it is what keeps the network
/// printers out: the sweep already finds them, and offering them twice would turn one printer into
/// two devices. A queue name our own contract would refuse is skipped rather than listed — a
/// printer on screen that fails the moment it is picked is worse than one that is not there.
pub fn parse_usb_queues(destinations: &str, devices: &str) -> Vec<PrinterInfo> {
    let names: HashSet<&str> = destinations
        .lines()
        .map(str::trim)
        .filter(|name| !name.is_empty())
        .collect();
    devices
        .lines()
        .filter_map(|line| {
            let (before_uri, uri) = split_at_device_uri(line)?;
            if !uri.to_ascii_lowercase().starts_with(USB_DEVICE_URI_SCHEME) {
                return None;
            }
            let Some(queue) = queue_named_in(before_uri, &names) else {
                // A USB cable we cannot put a name to is the one case where the till HAS a USB
                // printer and the screen will not show it — worth a line in the log, never a guess:
                // an invented name is a printer that fails the moment it is picked.
                tracing::warn!(
                    "usb: `lpstat -v` lists a USB queue that `lpstat -e` does not name; not offered: {line}"
                );
                return None;
            };
            if !is_cups_queue_name(queue) {
                return None;
            }
            Some(PrinterInfo {
                id: format!("usb:{queue}"),
                name: device_name(uri).unwrap_or_else(|| queue.to_string()),
                kind: "usb".into(),
                // A USB port says "bytes go through", not "this speaks ESC/POS": an A4 inkjet
                // plugs into the very same cable. Same honesty rule as the 9100 sweep and SPP.
                category: default_printer_category(),
                status: "ready".into(),
                paper_width: DEFAULT_PAPER_WIDTH,
                mac: None,
            })
        })
        .collect()
}

/// Splits an `lpstat -v` line into what comes before the device URI and the URI itself. The URI
/// is where `://` is, extended left over its scheme: the one landmark no translation moves.
fn split_at_device_uri(line: &str) -> Option<(&str, &str)> {
    let line = line.trim();
    let separator = line.find("://")?;
    let scheme_start = line[..separator]
        .char_indices()
        .rev()
        .find(|&(_, c)| !(c.is_ascii_alphanumeric() || matches!(c, '+' | '-' | '.')))
        .map_or(0, |(i, c)| i + c.len_utf8());
    Some((&line[..scheme_start], &line[scheme_start..]))
}

/// The destination name that `before_uri` carries as a word of its own — the one nearest the URI,
/// should a template word happen to be a queue name too. Words are cut on whitespace and on the
/// `:` (or full-width `：`) CUPS puts between the name and the URI, with or without space around it.
fn queue_named_in<'a>(before_uri: &'a str, names: &HashSet<&str>) -> Option<&'a str> {
    before_uri
        .rsplit(|c: char| c.is_whitespace() || c == ':' || c == '：')
        .find(|word| !word.is_empty() && names.contains(word))
}

/// Every USB print queue this machine has, ready to be offered next to the network ones.
///
/// Asks twice — `lpstat -e` for the names (CUPS 2.2+, 2016; macOS and any current Linux have it),
/// `lpstat -v` for the cables — because the second listing is localised and the first is not; see
/// [`parse_usb_queues`]. A till with no printer at all answers an empty list from both, exit 0.
///
/// The failure is returned, not swallowed into an empty list: "this till has no USB printer" and
/// "we could not ask the OS" need opposite things from the user, and a silent empty list reads as
/// the first while being the second. The caller decides whether that is fatal — for the shell's
/// discovery it is not: a venue whose LAN printers work must not lose them because CUPS is absent.
pub fn discover_usb_printers(client: &dyn CupsClient) -> Result<Vec<PrinterInfo>> {
    let destinations = lpstat(client, "-e")?;
    let devices = lpstat(client, "-v")?;
    Ok(parse_usb_queues(&destinations, &devices))
}

/// One `lpstat` listing, or why it could not be had.
fn lpstat(client: &dyn CupsClient, flag: &str) -> Result<String> {
    let out = client.run(CUPS_LPSTAT, &[flag], &[])?;
    if out.success {
        return Ok(out.stdout);
    }
    let reason = first_meaningful_line(&out.stderr)
        .or_else(|| first_meaningful_line(&out.stdout))
        .unwrap_or("no reason given");
    Err(PeripheralError::Unreachable(format!(
        "could not list the OS print queues (`lpstat {flag}`): {reason}"
    )))
}

/// A human name out of a `usb://Make/Model?serial=…` device URI.
///
/// `usb://Star/TSP143%20(STR_T-001)?serial=X5` → `Star TSP143 (STR_T-001)`. `None` when the URI
/// carries nothing but the scheme, so the caller can fall back to the queue name.
fn device_name(uri: &str) -> Option<String> {
    let rest = uri.get(USB_DEVICE_URI_SCHEME.len()..)?;
    let rest = rest.split('?').next().unwrap_or(rest);
    let name = percent_decode(&rest.replace('/', " "));
    let name = name.trim();
    (!name.is_empty()).then(|| name.to_string())
}

/// Decodes the `%XX` escapes CUPS puts in a device URI. Anything that is not a well-formed escape
/// is left exactly as it was: this is a label for a screen, never a round-trip.
fn percent_decode(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        let decoded = (bytes[i] == b'%' && i + 2 < bytes.len())
            .then(|| std::str::from_utf8(&bytes[i + 1..i + 3]).ok())
            .flatten()
            .and_then(|hex| u8::from_str_radix(hex, 16).ok());
        match decoded {
            Some(byte) => {
                out.push(byte);
                i += 3;
            }
            None => {
                out.push(bytes[i]);
                i += 1;
            }
        }
    }
    String::from_utf8_lossy(&out).into_owned()
}

/// The real [`CupsClient`]: spawns the client binary and waits for it, bounded by
/// [`CUPS_TIMEOUT`].
pub struct SystemCups;

impl CupsClient for SystemCups {
    fn run(&self, program: &str, args: &[&str], stdin: &[u8]) -> Result<CupsOutput> {
        run_bounded(program, args, stdin, CUPS_TIMEOUT)
    }
}

/// [`SystemCups::run`] with the deadline spelled out, so the give-up path can be exercised in
/// milliseconds instead of making the suite wait out a real [`CUPS_TIMEOUT`].
fn run_bounded(program: &str, args: &[&str], stdin: &[u8], timeout: Duration) -> Result<CupsOutput> {
    {
        let mut child = Command::new(program)
            .args(args)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| {
                PeripheralError::Unreachable(format!(
                    "could not run `{program}`: {e} — the CUPS client tools have to be installed \
                     for USB printing (macOS ships them; on Linux they are the `cups-client` package)"
                ))
            })?;

        // The payload goes in on its own thread. `lp` reads stdin to EOF, and a receipt with a
        // logo can outgrow the pipe buffer (~64 KB): writing it inline would deadlock us against a
        // child that is waiting for us to finish before it starts reading. Dropping the handle at
        // the end of the closure is the EOF `lp` waits for.
        let mut sink = child.stdin.take().ok_or_else(|| {
            PeripheralError::Unreachable(format!("`{program}` gave no stdin to write to"))
        })?;
        let payload = stdin.to_vec();
        let writer = std::thread::spawn(move || sink.write_all(&payload).and_then(|()| sink.flush()));

        // Both output pipes are drained on their own threads for the same reason the payload is
        // written on one: a child that fills a pipe buffer nobody is reading blocks there forever.
        // Draining only after the exit looks safe as long as the client answers in a line or two —
        // and then the deadline below reports "cupsd is wedged" when what actually wedged is us.
        // Measured: 512 KB through `cat` timed out at 20 s until these two threads existed.
        let out_pipe = child.stdout.take();
        let err_pipe = child.stderr.take();
        let out_reader = std::thread::spawn(move || drain(out_pipe));
        let err_reader = std::thread::spawn(move || drain(err_pipe));

        let deadline = Instant::now() + timeout;
        let status = loop {
            match child.try_wait() {
                Ok(Some(status)) => break status,
                Ok(None) if Instant::now() >= deadline => {
                    // Killing it closes the pipe, which releases the writer thread too.
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err(PeripheralError::Unreachable(format!(
                        "`{program}` did not answer in {:?} (is cupsd running?); the job was NOT sent",
                        timeout
                    )));
                }
                Ok(None) => std::thread::sleep(POLL_INTERVAL),
                Err(e) => {
                    return Err(PeripheralError::Unreachable(format!(
                        "could not wait for `{program}`: {e}"
                    )))
                }
            }
        };

        // The child is gone, so both pipes are at EOF and these joins return at once. A reader
        // that somehow panicked costs a diagnostic sentence, never the outcome — that is decided
        // by the exit status.
        let stdout = out_reader.join().unwrap_or_default();
        let stderr = err_reader.join().unwrap_or_default();

        // Precedence matters. When the child rejected the job it closed the pipe, so the writer
        // reports a broken pipe — reporting THAT would bury `lp`'s actual sentence ("paper out").
        // The write error is only the real story when the child itself was happy.
        if status.success() {
            match writer.join() {
                Ok(Ok(())) => {}
                Ok(Err(e)) => {
                    return Err(PeripheralError::Unreachable(format!(
                        "`{program}` accepted the job but the document could not be handed over: {e}"
                    )))
                }
                Err(_) => {
                    return Err(PeripheralError::Unreachable(format!(
                        "the thread feeding `{program}` panicked; the job may be incomplete"
                    )))
                }
            }
        }

        Ok(CupsOutput {
            success: status.success(),
            stdout,
            stderr,
        })
    }
}

/// Reads a child pipe to the end. A pipe we cannot read is reported as empty: it costs us a
/// diagnostic sentence, never the outcome, which is decided by the exit status.
fn drain(pipe: Option<impl Read>) -> String {
    let mut text = String::new();
    if let Some(mut pipe) = pipe {
        if let Err(e) = pipe.read_to_string(&mut text) {
            tracing::warn!("usb: could not read a CUPS client pipe ({e}); its output is lost");
        }
    }
    text
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::RefCell;

    /// Records what would have been run, and answers whatever the test wants it to — per argv,
    /// so a discovery that asks two questions (`-e`, then `-v`) can be given two answers.
    struct FakeCups {
        /// `(args, answer)`; an empty `args` answers any call.
        answers: Vec<(Vec<&'static str>, CupsOutput)>,
        calls: RefCell<Vec<(String, Vec<String>, Vec<u8>)>>,
    }

    impl FakeCups {
        fn answering(answer: CupsOutput) -> Self {
            Self { answers: vec![(Vec::new(), answer)], calls: RefCell::new(Vec::new()) }
        }
        fn ok() -> Self {
            Self::answering(CupsOutput {
                success: true,
                stdout: "request id is Star_TSP143-7 (1 file(s))".into(),
                stderr: String::new(),
            })
        }
        /// A healthy CUPS whose `lpstat -e` prints `destinations` and whose `lpstat -v` prints
        /// `devices`.
        fn listing(destinations: &str, devices: &str) -> Self {
            let ok = |stdout: &str| CupsOutput {
                success: true,
                stdout: stdout.into(),
                stderr: String::new(),
            };
            Self {
                answers: vec![(vec!["-e"], ok(destinations)), (vec!["-v"], ok(devices))],
                calls: RefCell::new(Vec::new()),
            }
        }
    }

    impl CupsClient for FakeCups {
        fn run(&self, program: &str, args: &[&str], stdin: &[u8]) -> Result<CupsOutput> {
            self.calls.borrow_mut().push((
                program.to_string(),
                args.iter().map(|a| a.to_string()).collect(),
                stdin.to_vec(),
            ));
            let scripted = self
                .answers
                .iter()
                .find(|(for_args, _)| for_args.is_empty() || for_args.as_slice() == args)
                .map(|(_, answer)| answer.clone());
            Ok(scripted.unwrap_or_else(|| CupsOutput {
                success: false,
                stdout: String::new(),
                stderr: format!("fake cups: nothing scripted for `{program} {args:?}`"),
            }))
        }
    }

    fn a_queue() -> UsbTarget {
        UsbTarget { queue: "Star_TSP143".into() }
    }

    #[test]
    fn hub1083_a_raw_cups_queue_receives_the_escpos_bytes() {
        let cups = FakeCups::ok();
        // A cut command: the bytes must arrive byte-for-byte, not re-encoded as text.
        let payload = b"\x1b@Hello\n\x1dV\x00".to_vec();

        send_raw(&cups, &a_queue(), &payload).expect("a healthy queue accepts the job");

        let calls = cups.calls.borrow();
        assert_eq!(calls.len(), 1, "exactly one submit per document");
        let (program, args, stdin) = &calls[0];
        assert_eq!(program, CUPS_LP);
        assert_eq!(stdin, &payload, "the ESC/POS must reach the spooler untouched");
        assert!(
            args.windows(2).any(|w| w == ["-d", "Star_TSP143"]),
            "the job must be addressed to the queue, got {args:?}"
        );
        assert!(
            args.windows(2).any(|w| w == ["-o", "raw"]),
            "without `-o raw` CUPS renders the ESC/POS as a document and prints garbage, got {args:?}"
        );
    }

    #[test]
    fn hub1083_a_refused_job_comes_back_as_an_error_naming_the_queue_and_the_reason() {
        // A queue that does not exist, is disabled or is rejecting jobs: `lp` exits non-zero and
        // says why, and that sentence is the only thing standing between the cashier and a ticket
        // that silently never printed, so it has to survive into the error. (Paper out or a pulled
        // cable are NOT this case: the spooler accepts the job and holds it — see `send_raw`.)
        let cups = FakeCups::answering(CupsOutput {
            success: false,
            stdout: String::new(),
            stderr: "lp: Error - The printer or class does not exist.".into(),
        });

        let err = send_raw(&cups, &a_queue(), b"ticket").expect_err("a refusal must not read as sent");

        let shown = err.to_string();
        assert!(shown.contains("Star_TSP143"), "must name the queue, got: {shown}");
        assert!(shown.contains("does not exist"), "must carry lp's reason, got: {shown}");
    }

    #[test]
    fn hub1083_only_usb_queues_are_offered_and_they_are_named_after_the_device() {
        // `lpstat -v` is the only place the OS says which queue is on which cable. The office
        // laser on IPP and the shared network printer are already found by the sweep; offering
        // them again here would turn one printer into two devices in the registry.
        let listing = "device for Star_TSP143: usb://Star/TSP143%20(STR_T-001)?serial=X5\n\
                       device for Office_Laser: ipp://10.0.0.9:631/ipp/print\n\
                       device for Kitchen: socket://10.0.0.5:9100\n\
                       device for EPSON_TM: usb://EPSON/TM-T20III\n";

        let found = parse_usb_queues("Star_TSP143\nOffice_Laser\nKitchen\nEPSON_TM\n", listing);

        let ids: Vec<&str> = found.iter().map(|p| p.id.as_str()).collect();
        assert_eq!(ids, vec!["usb:Star_TSP143", "usb:EPSON_TM"], "only the USB cables");

        let star = &found[0];
        assert_eq!(star.kind, "usb");
        assert_eq!(
            star.name, "Star TSP143 (STR_T-001)",
            "the device URI carries make and model; percent escapes are not for human eyes"
        );
        // Same honesty rule as the port-9100 sweep and SPP: a USB cable says "bytes go through",
        // not "this speaks ESC/POS" — an A4 inkjet plugs into the same port.
        assert_eq!(star.category, default_printer_category());
        assert_eq!(star.status, "ready");
        assert_eq!(star.mac, None, "a queue has no MAC; its name is its identity");
    }

    #[test]
    fn hub1083_a_listing_in_the_systems_language_still_finds_the_usb_queue() {
        // CUPS localises the `lpstat -v` line, and macOS picks that language from the system
        // preference (`AppleLanguages`), NOT from `LANG`/`LC_ALL` — forcing the C locale on the
        // child does not help there (measured 2026-09-05: `dispositivo para …` with `LC_ALL=C`).
        // A till in Spain runs in Spanish, so an English-only parser would list zero USB printers
        // for exactly the customer this transport exists for. Templates are the real ones from
        // CUPS' `locale/cups_<lang>.po`; the Spanish line is verbatim from a Mac.
        let listing = "dispositivo para Star_TSP143: usb://Star/TSP143?serial=X5\n\
                       dispositivo para Brother_HL_3150CDW_series: dnssd://Brother%20HL-3150CDW%20series._ipp._tcp.local./?uuid=e3248000-80ce-11db-8000-3c2af45a10ef\n\
                       matériel pour EPSON_TM : usb://EPSON/TM-T20III\n\
                       Gerät für Bar_Star: usb://Star/TSP654\n\
                       dispositiu per Cuina: usb://EPSON/TM-T88\n\
                       Kitchen_Star のデバイス: usb://Star/TSP143\n\
                       用于 Caja_Epson 的设备：usb://EPSON/TM-m30\n";
        // `lpstat -e` is the same in every language: bare names, one per line.
        let names = "Star_TSP143\nBrother_HL_3150CDW_series\nEPSON_TM\nBar_Star\nCuina\nKitchen_Star\nCaja_Epson\n";

        let ids: Vec<String> = parse_usb_queues(names, listing).into_iter().map(|p| p.id).collect();

        assert_eq!(
            ids,
            vec![
                "usb:Star_TSP143",
                "usb:EPSON_TM",
                "usb:Bar_Star",
                "usb:Cuina",
                "usb:Kitchen_Star",
                "usb:Caja_Epson"
            ],
            "every USB queue must be found whatever language CUPS speaks, and the Bonjour one never"
        );
    }

    #[test]
    fn hub1083_a_queue_we_could_never_address_is_not_offered() {
        // If the OS reports a destination whose name our own contract refuses (`-oraw` would be
        // read by `lp -d` as a flag), listing it would put a printer on screen that fails the
        // moment it is picked. Better absent than a trap.
        let listing = "device for -oraw: usb://Star/TSP143\n\
                       device for good_one: usb://Star/TSP143\n";

        let ids: Vec<String> =
            parse_usb_queues("-oraw\ngood_one\n", listing).into_iter().map(|p| p.id).collect();

        assert_eq!(ids, vec!["usb:good_one"]);
    }

    #[test]
    fn hub1083_a_usb_cable_the_destination_list_does_not_name_is_not_guessed() {
        // Matching against `lpstat -e` is what makes the parser language-proof; the flip side is
        // that a line whose name is not in that list must NOT be offered under whatever word sits
        // before the colon (`のデバイス` in Japanese) — that is a printer that fails when picked.
        let listing = "Kitchen_Star のデバイス: usb://Star/TSP143\n";

        assert!(parse_usb_queues("", listing).is_empty(), "no name, no guess");
        assert!(parse_usb_queues("Other_Queue\n", listing).is_empty(), "a different name is no name");
    }

    // ── The REAL runner ──────────────────────────────────────────────────────────────────────
    //
    // `SystemCups` is the half no fake can vouch for: spawning, feeding stdin, the deadline, a
    // binary that is not there. Exercised against `cat`/`sh`/`sleep` rather than `lp`, because a
    // test that really submitted a job would either print on the developer's desk or fail on every
    // machine without a printer — and neither outcome would mean anything.

    #[test]
    fn hub1083_the_real_runner_feeds_stdin_and_brings_the_answer_back() {
        let out = run_bounded("cat", &[], b"\x1b@ticket", CUPS_TIMEOUT).expect("`cat` is everywhere");

        assert!(out.success);
        assert_eq!(out.stdout.as_bytes(), b"\x1b@ticket", "the bytes must pass through untouched");
    }

    #[test]
    fn hub1083_a_payload_bigger_than_the_pipe_buffer_does_not_deadlock() {
        // THE reason the payload is written on its own thread. A receipt carrying a logo outgrows
        // the ~64 KB pipe buffer; writing it inline would block us against a child that is itself
        // blocked waiting for us to stop writing, and the till would hang on the press that
        // prints. 512 KB is comfortably past any platform's buffer.
        let payload = vec![b'A'; 512 * 1024];

        let out = run_bounded("cat", &[], &payload, CUPS_TIMEOUT).expect("must not hang");

        assert!(out.success);
        assert_eq!(out.stdout.len(), payload.len(), "the whole document has to get through");
    }

    #[test]
    fn hub1083_a_nonzero_exit_is_reported_instead_of_passing_for_sent() {
        let out = run_bounded("sh", &["-c", "echo nope >&2; exit 3"], b"", CUPS_TIMEOUT)
            .expect("the process ran, it just refused");

        assert!(!out.success, "exit 3 is not a sent job");
        assert!(out.stderr.contains("nope"), "the reason has to survive, got: {:?}", out.stderr);
    }

    #[test]
    fn hub1083_a_wedged_client_is_given_up_on_rather_than_hanging_the_till() {
        // When `cupsd` wedges, `lp` blocks on its socket and never returns. Without the deadline
        // that is a till frozen on the press that prints, with no way out but killing the app.
        let started = Instant::now();

        let err = run_bounded("sleep", &["30"], b"", Duration::from_millis(150))
            .expect_err("a client that never answers must not read as success");

        assert!(started.elapsed() < Duration::from_secs(5), "it waited out the whole sleep");
        assert!(err.to_string().contains("NOT sent"), "must be explicit, got: {err}");
    }

    #[test]
    fn hub1083_a_missing_cups_client_says_so_instead_of_blaming_the_printer() {
        // Linux without `cups-client` installed. "Install the CUPS tools" and "check the printer"
        // are opposite instructions, so the error has to point at the right one.
        let err = run_bounded("erplora-no-such-binary", &[], b"", CUPS_TIMEOUT)
            .expect_err("a binary that is not there cannot have printed");

        assert!(err.to_string().contains("cups-client"), "must name the fix, got: {err}");
    }

    #[test]
    fn hub1083_the_real_lpstat_listing_of_this_machine_parses() {
        // Captured verbatim from `lpstat -v` on macOS (2026-09-04). A network printer shared over
        // Bonjour: it is already found by the LAN sweep, so offering it here too would turn one
        // printer into two devices. Pinning REAL output keeps the parser honest about the shape
        // CUPS actually emits, which no hand-written fixture can promise.
        let real = "device for Brother_HL_3150CDW_series: dnssd://Brother%20HL-3150CDW%20series._ipp._tcp.local./?uuid=e3248000-80ce-11db-8000-3c2af45a10ef\n";

        assert!(
            parse_usb_queues("Brother_HL_3150CDW_series\n", real).is_empty(),
            "a Bonjour printer is not on a USB cable"
        );
    }

    #[test]
    fn hub1083_discovery_asks_the_os_for_its_queues_and_their_cables() {
        let cups = FakeCups::listing(
            "Star_TSP143\nOffice\n",
            "device for Star_TSP143: usb://Star/TSP143\ndevice for Office: ipp://10.0.0.9:631/ipp/print\n",
        );

        let found = discover_usb_printers(&cups).expect("a healthy CUPS answers");

        let calls = cups.calls.borrow();
        let asked: Vec<(&str, &[String])> =
            calls.iter().map(|(program, args, _)| (program.as_str(), args.as_slice())).collect();
        assert_eq!(
            asked,
            vec![(CUPS_LPSTAT, &["-e".to_string()][..]), (CUPS_LPSTAT, &["-v".to_string()][..])],
            "`-e` is the names (never translated); `-v` is what prints the device URI, without \
             which there is no way to tell a cable from a LAN"
        );
        assert_eq!(found.len(), 1);
        assert_eq!(found[0].id, "usb:Star_TSP143");
    }

    #[test]
    fn hub1083_not_being_able_to_ask_the_os_is_an_error_not_an_empty_list() {
        // "no USB printer here" and "we could not ask" need opposite things from the user: plug
        // one in, versus install the CUPS tools. An empty list would say the first while meaning
        // the second, and the till would look like it simply has no printer.
        let cups = FakeCups::answering(CupsOutput {
            success: false,
            stdout: String::new(),
            stderr: "lpstat: Bad file descriptor".into(),
        });

        let err = discover_usb_printers(&cups).expect_err("a failed listing must not read as empty");

        assert!(err.to_string().contains("Bad file descriptor"), "got: {err}");
    }

    #[test]
    fn hub1083_a_listing_without_any_usb_queue_is_an_empty_answer_not_a_failure() {
        // A till with only LAN printers is normal, not broken — and so is one with no printer at
        // all, where both listings come back empty with exit 0 (checked in CUPS' `lpstat.c`:
        // `show_devices` prints nothing and returns 0 when there is nothing to show).
        assert!(parse_usb_queues("Office\n", "device for Office: ipp://10.0.0.9:631/ipp/print\n").is_empty());
        assert!(parse_usb_queues("", "").is_empty());
        assert!(parse_usb_queues("", "lpstat: No destinations added.\n").is_empty());
        assert!(discover_usb_printers(&FakeCups::listing("", "")).expect("empty is fine").is_empty());
    }
}
