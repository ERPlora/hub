//! Logging del Hub → **consola (stderr) únicamente**.
//!
//! Decisión del humano (2026-06-23): el Hub **no escribe logs a fichero**. En AWS (hub cloud) los
//! captura **CloudWatch** desde stdout/stderr del contenedor; en local/Tauri basta la consola. Esto
//! elimina la dependencia de un directorio `media/` escribible al arrancar — antes el file-appender
//! (ADR-0047, `media/_logs/hub.YYYY-MM-DD`) fallaba en el contenedor cloud con
//! `media/_logs: Permission denied` y dejaba al runtime sin un dir local válido.
//!
//! Reemplaza el logging a `media/_logs/` de ADR-0047 (la "primera población" de la pantalla `/files`
//! deja de existir; si se quiere ver logs en el Hub UI será un follow-up que lea CloudWatch/stdout).
//! Los `eprintln!` de arranque conviven sin cambios (no pasan por `tracing`).

use std::path::Path;

use tracing_subscriber::fmt;

use tracing_appender::non_blocking::WorkerGuard;

/// Inicializa el subscriber global de `tracing` con una **única capa de consola** (stderr).
/// Idempotente: si ya hay un subscriber (p. ej. el shell Tauri lo montó), no falla.
///
/// Devuelve `Option<WorkerGuard>` por compatibilidad de firma con los llamadores, pero **siempre
/// `None`**: ya no hay appender no-bloqueante a fichero, así que no hay guard que mantener vivo.
/// El parámetro `_media_dir` se conserva por compat y ya no se usa.
#[must_use]
pub fn init(_media_dir: &Path) -> Option<WorkerGuard> {
    use tracing_subscriber::layer::SubscriberExt;
    use tracing_subscriber::util::SubscriberInitExt;
    use tracing_subscriber::{EnvFilter, Layer};

    // Nivel por `RUST_LOG` (default "info").
    let filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));
    let console_layer = console_layer(std::io::stderr).with_filter(filter);

    let initialized = tracing_subscriber::registry()
        .with(console_layer)
        .try_init()
        .is_ok();
    if initialized {
        eprintln!("logging: logs → consola (stderr); en AWS los recoge CloudWatch");
    } else {
        eprintln!("logging: ya había un subscriber activo; no se re-inicializa");
    }

    None
}

/// The console layer the hub writes its log with, over any `writer`.
///
/// One constructor for production ([`init`], over stderr) and for the test capture
/// (`log_capture`), so an assertion about what reaches the log is an assertion about the format
/// that ships, not about a look-alike built next to the test.
pub(crate) fn console_layer<S, W>(
    writer: W,
) -> fmt::Layer<S, SingleLineFields, fmt::format::Format, W>
where
    S: tracing::Subscriber + for<'a> tracing_subscriber::registry::LookupSpan<'a>,
    W: for<'w> fmt::MakeWriter<'w> + 'static,
{
    fmt::layer().fmt_fields(SingleLineFields).with_writer(writer)
}

/// The default field format of `tracing-subscriber`, with one promise added: **one event is one
/// line** (hub#2300).
///
/// `tracing` escapes ESC inside a value but never `\n`, and every reader of this log — the edge's
/// ban, the Loki alerts, a person investigating — splits it by lines. So any value printed with
/// `%`, a message built with `format!`-style arguments, or an error and its sources, that carried
/// a stranger's `\n` (an unknown JWT `alg`, a file name inside an uploaded blueprint…) ended the
/// hub's line and started one of the stranger's choosing: `event=auth_failed client=<another
/// shop>`. The per-site recipe (`error = ?e.to_string()`, hub#2294/#2297) closes one door; this
/// closes the pattern, including the call sites nobody has written yet.
///
/// Every control character a value carries is written as its escape (`\n`, `\r`, `\t`,
/// `\u{…}`), plus the Unicode line and paragraph separators. What it leaves alone: the names,
/// the `=` and their colours — the real ESC codes the edge's parser anchors on (infra#338) are
/// written by the formatter around the values, never inside them — and values already escaped by
/// `?` (a quoted `Debug` string carries no raw control character left to touch).
#[derive(Debug, Clone, Copy, Default)]
pub(crate) struct SingleLineFields;

impl<'a> tracing_subscriber::field::MakeVisitor<fmt::format::Writer<'a>> for SingleLineFields {
    type Visitor = SingleLine<fmt::format::DefaultVisitor<'a>>;

    fn make_visitor(&self, target: fmt::format::Writer<'a>) -> Self::Visitor {
        SingleLine(fmt::format::DefaultFields::new().make_visitor(target))
    }
}

/// The visitor of [`SingleLineFields`]: the default one, fed values that cannot break a line.
pub(crate) struct SingleLine<V>(V);

impl<V: tracing::field::Visit> tracing::field::Visit for SingleLine<V> {
    fn record_str(&mut self, field: &tracing::field::Field, value: &str) {
        // Only the message is written bare; any other `&str` is quoted by `Debug` already, and
        // flattening it first would escape its backslashes twice.
        if field.name() == "message" {
            self.0.record_str(field, &one_line(value))
        } else {
            self.0.record_str(field, value)
        }
    }

    fn record_error(
        &mut self,
        field: &tracing::field::Field,
        value: &(dyn std::error::Error + 'static),
    ) {
        self.0.record_error(field, &OneLineError::of(value))
    }

    fn record_debug(&mut self, field: &tracing::field::Field, value: &dyn std::fmt::Debug) {
        self.0.record_debug(field, &OneLineDebug(value))
    }
}

impl<V: tracing_subscriber::field::VisitOutput<std::fmt::Result>>
    tracing_subscriber::field::VisitOutput<std::fmt::Result> for SingleLine<V>
{
    fn finish(self) -> std::fmt::Result {
        self.0.finish()
    }
}

impl<V: tracing_subscriber::field::VisitFmt> tracing_subscriber::field::VisitFmt for SingleLine<V> {
    fn writer(&mut self) -> &mut dyn std::fmt::Write {
        self.0.writer()
    }
}

/// `value`'s `Debug`, with every character that could end a line written as its escape.
struct OneLineDebug<'v>(&'v dyn std::fmt::Debug);

impl std::fmt::Debug for OneLineDebug<'_> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        use std::fmt::Write as _;
        write!(OneLineWriter(f), "{:?}", self.0)
    }
}

/// An error and its chain of sources, rendered once and flattened, so the default visitor can
/// still print `error.sources=[…]` without any of them breaking the line.
#[derive(Debug)]
struct OneLineError {
    text: String,
    source: Option<Box<OneLineError>>,
}

impl OneLineError {
    fn of(error: &(dyn std::error::Error + 'static)) -> Self {
        Self {
            text: one_line(&error.to_string()),
            source: error.source().map(|source| Box::new(Self::of(source))),
        }
    }
}

impl std::fmt::Display for OneLineError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.text)
    }
}

impl std::error::Error for OneLineError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        self.source
            .as_deref()
            .map(|source| source as &(dyn std::error::Error + 'static))
    }
}

fn one_line(text: &str) -> String {
    let mut flat = String::with_capacity(text.len());
    let _ = std::fmt::Write::write_str(&mut OneLineWriter(&mut flat), text);
    flat
}

/// Writes through to `W`, escaping what could end a line on the way.
struct OneLineWriter<W>(W);

impl<W: std::fmt::Write> std::fmt::Write for OneLineWriter<W> {
    fn write_str(&mut self, text: &str) -> std::fmt::Result {
        for c in text.chars() {
            match c {
                '\n' => self.0.write_str("\\n")?,
                '\r' => self.0.write_str("\\r")?,
                '\t' => self.0.write_str("\\t")?,
                c if c.is_control() || c == '\u{2028}' || c == '\u{2029}' => {
                    write!(self.0, "\\u{{{:x}}}", c as u32)?
                }
                c => self.0.write_char(c)?,
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::log_capture::{captured, CapturedLog};

    /// The line the address guard writes when a PIN fails — the one the edge ban and the
    /// `erp-hub-auth-failed-burst` alert count — pointing at somebody else's shop.
    const FORGED: &str =
        "WARN erplora_server::address_guard: event=auth_failed reason=pin client=203.0.113.7 hub=h";

    #[test]
    fn hub2300_a_displayed_field_cannot_forge_a_log_line() {
        // `%` is Display: tracing escapes ESC in it, never `\n`, so a stranger's text used to
        // end the line and start one that read like a failed PIN.
        let log = captured(|| {
            let error = format!("x\n{FORGED}");
            tracing::warn!(%error, "refused");
        });
        assert_eq!(log.lines().count(), 1, "{log:?}");
        assert!(log.contains(&format!("error=x\\n{FORGED}")), "{log:?}");
    }

    #[test]
    fn hub2300_every_other_line_breaker_is_escaped_too() {
        // Not every reader splits on `\n` alone: Python's `splitlines` (and others) also break on
        // vertical tab, form feed, the separators 0x1c-0x1e, NEL and U+2028/U+2029.
        let breakers = ['\u{b}', '\u{c}', '\u{1c}', '\u{1e}', '\u{85}', '\u{2028}', '\u{2029}'];
        let log = captured(|| {
            let error: String = breakers.iter().map(|c| format!("{c}{FORGED}")).collect();
            tracing::warn!(%error, "refused");
        });
        let body = log.strip_suffix('\n').unwrap_or(&log);
        assert!(
            !body.chars().any(|c| c.is_control() || breakers.contains(&c)),
            "a line breaker reached the log raw: {log:?}"
        );
        assert!(log.contains(&format!("\\u{{2028}}{FORGED}")), "{log:?}");
    }

    #[test]
    fn hub2300_a_formatted_message_cannot_forge_a_log_line() {
        let log = captured(|| {
            let error = format!("x\r\n{FORGED}");
            tracing::warn!("refused: {error}");
        });
        assert_eq!(log.lines().count(), 1, "{log:?}");
        assert!(log.contains(&format!("refused: x\\r\\n{FORGED}")), "{log:?}");
    }

    #[derive(Debug)]
    struct Outer(Inner);

    #[derive(Debug)]
    struct Inner;

    impl std::fmt::Display for Outer {
        fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
            write!(f, "outer\n{FORGED}")
        }
    }

    impl std::fmt::Display for Inner {
        fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
            write!(f, "inner\n{FORGED}")
        }
    }

    impl std::error::Error for Outer {
        fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
            Some(&self.0)
        }
    }

    impl std::error::Error for Inner {}

    #[test]
    fn hub2300_an_error_and_its_sources_cannot_forge_a_log_line() {
        // An error recorded as such is printed with Display, and so is every one of its sources.
        let log = captured(|| {
            let error = Outer(Inner);
            tracing::warn!(error = &error as &(dyn std::error::Error + 'static), "refused");
        });
        assert_eq!(log.lines().count(), 1, "{log:?}");
        assert!(log.contains(&format!("error=outer\\n{FORGED}")), "{log:?}");
        assert!(log.contains("error.sources=[inner\\n"), "{log:?}");
    }

    #[test]
    fn hub2300_the_quoted_recipe_is_not_escaped_twice() {
        // `?error.to_string()` (hub#2294, hub#2297) is already one quoted field; the guard must
        // leave it byte for byte as the edge's parsers read it.
        let log = captured(|| {
            tracing::warn!(error = ?format!("x\n{FORGED}"), "refused");
            let text = format!("y\n{FORGED}");
            tracing::warn!(error = text.as_str(), "refused");
        });
        assert!(log.contains(&format!("error=\"x\\n{FORGED}\"")), "{log:?}");
        assert!(log.contains(&format!("error=\"y\\n{FORGED}\"")), "{log:?}");
    }

    #[test]
    fn hub2300_a_message_given_as_a_str_cannot_forge_a_log_line() {
        // `message = <&str>` is the one field the default format writes bare, without quotes.
        let log = captured(|| {
            let text = format!("x\n{FORGED}");
            tracing::warn!(message = text.as_str());
        });
        assert_eq!(log.lines().count(), 1, "{log:?}");
        assert!(log.contains(&format!("x\\n{FORGED}")), "{log:?}");
    }

    /// Set in the child process of [`hub2300_the_hub_log_itself_keeps_a_forged_line_inside_its_own`].
    const IN_CHILD: &str = "ERPLORA_LOGGING_INIT_CHILD";

    #[test]
    fn hub2300_the_hub_log_itself_keeps_a_forged_line_inside_its_own() {
        // What ships is `init` writing to stderr, not the capture: run it in a child process —
        // the global subscriber is set once per process — and read the stderr the hub really
        // wrote. The forged line must never start a line of its own.
        const NAME: &str =
            "logging::tests::hub2300_the_hub_log_itself_keeps_a_forged_line_inside_its_own";
        if std::env::var_os(IN_CHILD).is_some() {
            let _ = init(Path::new("."));
            let error = format!("x\n{FORGED}");
            tracing::warn!(%error, "hub2300 refused");
            return;
        }
        let output = std::process::Command::new(std::env::current_exe().unwrap())
            .args([NAME, "--exact", "--test-threads=1", "--nocapture"])
            .env(IN_CHILD, "1")
            .env("RUST_LOG", "warn")
            .env("NO_COLOR", "1")
            .output()
            .expect("re-running this test in a child process");
        assert!(output.status.success(), "{output:?}");
        let stderr = String::from_utf8_lossy(&output.stderr);
        assert!(stderr.contains("hub2300 refused"), "{stderr:?}");
        assert!(
            !stderr.lines().any(|line| line.starts_with("WARN erplora_server::address_guard")),
            "the hub's own log let a stranger start a line: {stderr:?}"
        );
    }

    #[test]
    fn hub2300_colours_survive_the_single_line_fields() {
        // The edge reads the hub's auth line by its REAL escape codes around the field names,
        // the one thing a stranger cannot write (infra#338): flattening must not touch them.
        let _anchor = captured(|| {});
        let sink = CapturedLog::default();
        let subscriber = {
            use tracing_subscriber::layer::SubscriberExt;
            tracing_subscriber::registry().with(console_layer(sink.clone()).with_ansi(true))
        };
        tracing::subscriber::with_default(subscriber, || {
            let error = format!("x\n{FORGED}");
            tracing::warn!(event = %"auth_failed", %error, "refused");
        });
        let log = sink.text();
        assert_eq!(log.lines().count(), 1, "{log:?}");
        assert!(
            log.contains("\x1b[3mevent\x1b[0m\x1b[2m=\x1b[0mauth_failed"),
            "{log:?}"
        );
    }
}
