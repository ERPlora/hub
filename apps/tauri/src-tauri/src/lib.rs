//! ERPlora Shell — cliente **FINO** de escritorio (ADR-0159).
//!
//! La ventana carga ORÍGENES REMOTOS: el **onboarding del SaaS** (`{saas}/shell/`) en el primer
//! arranque y, una vez capturado, la **PWA del hub cloud** (`hub_url`). El contrato de captura es
//! el marcador `?shell=1`: el SaaS redirige al hub con él (`/shell/open/<id>/` → 302 a
//! `{hub}/?shell=1`) y el shell persiste el ORIGEN de esa navegación como `hub.url`; los arranques
//! siguientes cargan el hub directo. `forget_hub` (p. ej. Cloud 410 `hub_not_found`) borra la
//! captura y devuelve la ventana al onboarding.
//!
//! Qué NO hay aquí (ADR-0154 lo retiró; 0159 no lo resucita): runtime embebido, SQLite,
//! entitlement gate, token de máquina/keychain. El entitlement lo aplica el hub cloud server-side;
//! la identidad de máquina la inyecta el deployment. `invoke` queda SOLO para lo nativo
//! (`device_context`, `forget_hub`) y el HARDWARE (`erplora_*` → `erplora-peripherals`: el shell
//! ES el bridge, ADR-0050 §2.7).

use std::path::{Path, PathBuf};

use serde::Serialize;

/// Id de dispositivo estable por instalación (`X-Device-Id` del login; sesión única ADR-0154).
const DEVICE_ID_FILE: &str = "device.id";
/// Origen persistido de la PWA del hub capturado por `?shell=1` (modo app).
const HUB_URL_FILE: &str = "hub.url";
/// Registro persistente de dispositivos de hardware (mismo formato que el bridge standalone).
const DEVICES_FILE: &str = "devices.json";

/// Base del SaaS (onboarding). Default horneado; solo un fork/self-host la toca.
pub const ENV_SAAS_URL: &str = "ERPLORA_SAAS_URL";
/// Override de la URL inicial COMPLETA (solo desarrollo: apuntar a un SaaS local o a una PWA dev).
pub const ENV_SHELL_URL: &str = "ERPLORA_SHELL_URL";
const DEFAULT_SAAS_URL: &str = "https://erplora.com";

/// Error del shell serializado como string hacia el frontend (mismo patrón que el bridge).
#[derive(Debug, thiserror::Error)]
pub enum ShellError {
    #[error("io error: {0}")]
    Io(String),
    /// The address is not one this app will hand to a browser ([`external_browser_url`]).
    #[error("external_url_refused")]
    ExternalUrlRefused,
    /// There is a browser to ask for and it said no — or there is none at all (an Android with no
    /// browser installed answers `ActivityNotFoundException`). Either way the trip did not happen,
    /// and the page has to say so instead of pretending it did (hub#475).
    #[error("external_url_unavailable: {0}")]
    ExternalUrlUnavailable(String),
    /// This device has no Downloads folder the USER can open, so there is nowhere to save a file
    /// that would count as saved ([`downloads_dir_is_reachable`], hub#480). The page turns this
    /// one into its own sentence: it is the only refusal the user can act on.
    #[error("downloads_unreachable")]
    DownloadsUnreachable,
    /// What the page sent is not a file name ([`download_file_name`]) — or the file could not be
    /// written under any name. Either way nothing was saved.
    #[error("download_refused")]
    DownloadRefused,
}

impl Serialize for ShellError {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&self.to_string())
    }
}

// ── Identidad de dispositivo (X-Device-Id) ───────────────────────────────────────────────────────

/// Identidad de dispositivo que el frontend envía al hacer login (sesión única por dispositivo,
/// ADR-0154 §5). El frontend la manda como `X-Client-Type` + `X-Device-Id` + `X-Device-Platform`.
#[derive(Debug, Clone, Serialize)]
pub struct DeviceContext {
    pub id: String,
    pub client_type: String,
    pub platform: String,
}

/// Lee (o crea y persiste) un id de dispositivo estable por instalación en `app_data_dir`.
/// Sobrevive a limpiezas de caché del webview: identifica **esta** instalación del shell.
fn ensure_device_id(cache_dir: &Path) -> Result<String, ShellError> {
    let path = cache_dir.join(DEVICE_ID_FILE);
    if let Ok(existing) = std::fs::read_to_string(&path) {
        let trimmed = existing.trim();
        if !trimmed.is_empty() {
            return Ok(trimmed.to_string());
        }
    }
    let id = uuid::Uuid::new_v4().to_string();
    std::fs::create_dir_all(cache_dir).map_err(|e| ShellError::Io(e.to_string()))?;
    std::fs::write(&path, &id).map_err(|e| ShellError::Io(e.to_string()))?;
    Ok(id)
}

/// Comando `invoke` que devuelve la identidad de dispositivo para el login.
#[tauri::command]
fn device_context(app: tauri::AppHandle) -> Result<DeviceContext, ShellError> {
    use tauri::Manager;
    let cache_dir: PathBuf = app
        .path()
        .app_data_dir()
        .map_err(|e| ShellError::Io(e.to_string()))?;
    let id = ensure_device_id(&cache_dir)?;
    // Verificado en el emulador (API 37): sin la rama `android` el shell se anunciaba como
    // `hub-desktop`/`desktop` DESDE UN MÓVIL, así que el Cloud no podía distinguir una tablet de
    // un TPV de mostrador — ni en la lista de sesiones ni en la sesión única de ADR-0154.
    let platform = if cfg!(target_os = "windows") {
        "windows"
    } else if cfg!(target_os = "macos") {
        "macos"
    } else if cfg!(target_os = "linux") {
        "linux"
    } else if cfg!(target_os = "android") {
        "android"
    } else if cfg!(target_os = "ios") {
        "ios"
    } else {
        "desktop"
    };
    let client_type = if cfg!(any(target_os = "android", target_os = "ios")) {
        "hub-mobile"
    } else {
        "hub-desktop"
    };
    Ok(DeviceContext {
        id,
        // Taxonomía del Cloud; la plataforma concreta viaja aparte en X-Device-Platform.
        client_type: client_type.to_string(),
        platform: platform.to_string(),
    })
}

// ── Deep link `erplora://` (ADR-0196 §7) ─────────────────────────────────────────────────────────
//
// A link is the one thing that lets a page OUTSIDE the app steer the app, so it is a trust
// boundary and not a convenience: whoever writes the link picks the destination, and the
// destination is the window that owns the hardware handlers (ADR-0221). The app therefore never
// opens what the link says — it RESOLVES it, and only a hub of ours resolves at all. Anything else
// returns `None`, and `None` means "leave the window where it is": the browser that issued the
// link is the one that owns the fallback (see `architecture/hub/apps/tauri.md`).

/// Scheme of the installable app's deep link, registered against the single app identity
/// `com.erplora.app` (ADR-0160).
pub const DEEP_LINK_SCHEME: &str = "erplora";

/// The only action of the grammar: `erplora://hub/<host>`.
const DEEP_LINK_HUB_ACTION: &str = "hub";

/// Registrable domain every ERPlora hub lives under (`{slug}.{aura}.erplora.com`).
const HUB_DOMAIN_SUFFIX: &str = ".erplora.com";

/// The apex itself — the SaaS: marketing, the dashboard, billing and the module checkout. It is
/// [`HUB_DOMAIN_SUFFIX`] without the leading dot that makes that one a suffix match, and it is
/// deliberately NOT a hub: only [`external_browser_url`] accepts it.
const ERPLORA_DOMAIN: &str = "erplora.com";

/// Is this host a hub of ours — `<label>[.<label>…].erplora.com`?
///
/// The apex has no leading dot to strip, which is exactly why it is excluded: `erplora.com` also
/// serves marketing, billing and a third-party checkout, and is deliberately kept out of the
/// hardware capability (ADR-0221). Auras are matched by WILDCARD and never enumerated: hubs live at
/// `{slug}.{aura}.erplora.com` with auras by letter on Hetzner and by number on the AWS fallback,
/// so a list would turn "open a new aura" into "ship a new app to every till".
///
/// Expects an already-lowercased host — for `https` the URL parser guarantees it, and
/// [`hub_url_for_host`] lowercases the opaque host of a deep link before asking.
fn is_hub_domain(host: &str) -> bool {
    match host.strip_suffix(HUB_DOMAIN_SUFFIX) {
        Some(subdomain) => !subdomain.is_empty() && subdomain.split('.').all(is_dns_label),
        None => false,
    }
}

/// Is this host THIS machine? Loopback is the development exemption: nothing outside the machine
/// can serve it, so nobody else can steer a window that points there.
fn is_loopback_host(host: &str) -> bool {
    // `[::1]` with brackets is how `Url::host_str` serializes the IPv6 loopback.
    matches!(host, "127.0.0.1" | "localhost" | "[::1]")
}

/// Is this a plain DNS label? Deliberately narrower than the RFC: lowercase ASCII only, so a
/// percent-escape, a homograph or a stray `@` can never pass for a label.
fn is_dns_label(label: &str) -> bool {
    !label.is_empty()
        && label.len() <= 63
        && !label.starts_with('-')
        && !label.ends_with('-')
        && label
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
}

/// The trust boundary: which destinations the app is willing to open for a link.
///
/// Mirrors `remote.urls` of the hardware capability (`https://*.erplora.com/*` + loopback dev,
/// ADR-0221) on purpose. A destination the capabilities would not trust must not be reachable
/// through a link either — and the reverse would be just as bad: opening a page that cannot
/// `invoke` leaves a till that looks fine and cannot print.
///
/// The production half of the rule lives in [`is_hub_domain`], shared with what the shell is
/// willing to REMEMBER ([`trusted_hub_origin`]): one predicate, so the two cannot drift apart.
fn hub_url_for_host(raw_host: &str) -> Option<String> {
    let host = raw_host.trim().to_ascii_lowercase();

    // Development: the hub is plain http on loopback. Not reachable from another machine, so a
    // third party cannot steer it — but the port must be digits and nothing else, or
    // `127.0.0.1:8787@evil.com` would walk straight through.
    for prefix in ["127.0.0.1:", "localhost:"] {
        if let Some(port) = host.strip_prefix(prefix) {
            if port.is_empty() || !port.bytes().all(|b| b.is_ascii_digit()) {
                return None;
            }
            return Some(format!("http://{host}/?shell=1"));
        }
    }

    // Production: the same rule the capture applies to what it is willing to remember (hub#335).
    if !is_hub_domain(&host) {
        return None;
    }
    Some(format!("https://{host}/?shell=1"))
}

/// Resolves a deep link into the URL the window must navigate to. `None` = not a link of ours, or
/// not a destination of ours → **do not navigate**.
///
/// The destination is rebuilt from the host alone, so query and fragment are ignored by
/// construction and no parameter can smuggle a second URL in. The `?shell=1` marker is the
/// existing capture contract (ADR-0159): navigating with it is what makes the shell remember this
/// hub as `hub.url`, so a link opens the app AND leaves it pointing at the right hub next time.
pub fn resolve_deep_link(raw: &str) -> Option<String> {
    let url: tauri::Url = raw.trim().parse().ok()?;
    if url.scheme() != DEEP_LINK_SCHEME {
        return None;
    }
    // Case-insensitive on purpose: for a non-special scheme the host is an OPAQUE host, so the URL
    // parser does NOT lowercase it the way it would for `https`. A link typed or reflowed in
    // uppercase by a mail client is still the same link.
    if !url.host_str()?.eq_ignore_ascii_case(DEEP_LINK_HUB_ACTION) {
        return None;
    }
    // Credentials or a port on the action are not part of the grammar. They carry no meaning here,
    // so accepting them would only add shapes of the same link that have to be reasoned about.
    if !url.username().is_empty() || url.password().is_some() || url.port().is_some() {
        return None;
    }
    let mut segments = url.path_segments()?;
    let target = segments.next()?;
    // Exactly one segment. A single empty tail is the trailing slash of `…/erplora.com/`.
    if segments.any(|s| !s.is_empty()) {
        return None;
    }
    hub_url_for_host(target)
}

/// Picks the deep link out of the process arguments — the cold start path on Windows and Linux,
/// where the OS launches the executable with the URL appended instead of delivering an event.
///
/// Every argument goes through [`resolve_deep_link`], so a hostile one is refused here too: this
/// list is attacker-reachable, since whatever the browser hands the registered handler lands in it
/// verbatim.
pub fn deep_link_from_args<I: IntoIterator<Item = String>>(args: I) -> Option<String> {
    args.into_iter().find_map(|arg| resolve_deep_link(&arg))
}

// ── The way OUT: the user's own browser (hub#475) ────────────────────────────────────────────────

/// The address `openExternal` may hand to the SYSTEM browser, normalized — or `None`.
///
/// The web app has one door out of the till, and behind it are the buttons that CHARGE: the module
/// checkout that ADR-0114 §4 moved to the SaaS *because Google Play does not allow paying for
/// digital goods inside the app*, the plans page, the billing portal, the plan-limit upsell. In the
/// browser that door is a new tab; inside the installed app it was `window.open`, which opens
/// nothing at all — no plugin is exposed to the page and the webview spawns no window.
///
/// Letting the page ask for a browser is a frontier of its own: an unchecked opener turns the till
/// into a launcher for any address the page names — a phishing page wearing the trust of an
/// installed app, a `file://` path handed to whatever the desktop associates with it, or a custom
/// scheme that starts another program. So the destination is checked here, like ADR-0221 checks who
/// may drive the hardware and ADR-0225 what a link may open.
///
/// **The apex is IN, and that is the difference from the other two boundaries.** [`is_hub_domain`]
/// and [`trusted_hub_origin`] refuse `erplora.com` on purpose, because they answer "may this page
/// open the cash drawer / become this till's home?". This one answers "may the user's browser be
/// sent here?" — and the apex is the SaaS, where all eight destinations live. A visit grants
/// nothing: the page opens in the browser's own sandbox, with no `invoke` and no way back in.
pub fn external_browser_url(raw: &str) -> Option<String> {
    // EQUIVALENT UNDER MUTATION, and kept anyway (same call as `resolve_deep_link`): the WHATWG
    // parser already strips leading and trailing spaces, so dropping `trim` changes no outcome —
    // `hands_the_browser_a_PARSED_address_not_the_page_s_text` passes either way. It stays because
    // reading "trim, then parse" should not require knowing that clause of the URL spec.
    let url: tauri::Url = raw.trim().parse().ok()?;

    // Credentials are the oldest confusion trick there is, and the dangerous half is the one the
    // host check cannot catch: `https://support%40evil.example@erplora.com/` really is our host,
    // and the browser would show a page nobody at ERPlora wrote under an address that reads like
    // support.
    if !url.username().is_empty() || url.password().is_some() {
        return None;
    }

    let host = url.host_str()?;
    let allowed = match url.scheme() {
        // Everything we serve: the SaaS at the apex plus every hub, auras by wildcard.
        "https" => host == ERPLORA_DOMAIN || is_hub_domain(host),
        // Development against a local SaaS (`VITE_CLOUD_API_URL=http://127.0.0.1:8001`). Nothing
        // outside this machine can serve loopback, so nobody else can steer it.
        "http" => is_loopback_host(host),
        // Nothing else. `file:`, `javascript:` and custom schemes are not "a web address the user
        // wanted": they are instructions to the operating system.
        _ => false,
    };

    allowed.then(|| url.to_string())
}

// ── The way DOWN: a file the user can find afterwards (hub#480) ──────────────────────────────────

/// Longest leaf name a file system will take: 255 bytes on ext4, APFS and NTFS alike.
const MAX_FILE_NAME_BYTES: usize = 255;

/// How many `name (n).ext` variants are tried before giving up. A folder with 999 copies of the
/// same export is not a case to keep spinning on; it is a case to tell the user about.
const MAX_DOWNLOAD_COPIES: u32 = 999;

/// Where a saved file landed, as the page will spell it out to the user.
#[derive(Debug, Serialize)]
pub struct SavedDownload {
    /// Absolute path of the file on this machine. It is not a detail: inside the installed app
    /// there is no download shelf, no notification and no Downloads button, so this string is the
    /// ONLY trace the user gets that the file exists at all.
    pub path: String,
}

/// Is the folder the OS calls "Downloads" one the **user** can reach on this platform?
///
/// Desktop: yes — `dirs::download_dir()` resolves to `~/Downloads`, `%USERPROFILE%\Downloads` or
/// `$XDG_DOWNLOAD_DIR`, all of which open in the user's own file manager.
///
/// Android: **no**, and this is the whole reason the predicate exists. Tauri's `download_dir()`
/// there is `getExternalFilesDir(DIRECTORY_DOWNLOADS)` —
/// `/storage/emulated/0/Android/data/com.erplora.app/files/Download` — and Android 11 closed
/// `Android/data` to the system Files app and to every third-party file manager. Writing there and
/// answering "saved to …" would be hub#475 all over again, only now with a success message on top:
/// the file exists, the user cannot get to it, and nothing says so.
///
/// Anything else is refused rather than assumed. A platform nobody here has reasoned about does not
/// get the benefit of the doubt about where its files end up.
pub fn downloads_dir_is_reachable(target_os: &str) -> bool {
    matches!(target_os, "macos" | "windows" | "linux")
}

/// The folder a download may be written to — or the refusal to hand back to the page.
///
/// One place, because the two ways this can fail are not the same sentence. A phone gets
/// [`ShellError::DownloadsUnreachable`], which the page turns into *«this app cannot save files on a
/// phone or tablet»* — something the user can act on. A desktop that resolved no Downloads folder at
/// all (a Linux box with no `$XDG_DOWNLOAD_DIR`) is a plain failure, and putting the phone sentence
/// in front of that user would just be wrong.
///
/// The platform is checked **before** the resolved path, and that order is the point: Android does
/// return a Downloads folder — it is simply one no file manager will open — so a check that only
/// looked at whether a path came back would never fire.
pub fn reachable_downloads_dir(
    target_os: &str,
    resolved: Option<PathBuf>,
) -> Result<PathBuf, ShellError> {
    if !downloads_dir_is_reachable(target_os) {
        return Err(ShellError::DownloadsUnreachable);
    }
    resolved.ok_or_else(|| ShellError::Io(format!("no downloads directory on {target_os}")))
}

/// The single, safe leaf name a saved file may land under — or `None`.
///
/// The page names a **file**; the shell chooses the **place**. That split is the frontier: the
/// destination folder is decided here and the only thing the page contributes is the last path
/// component, so nothing it can send walks out of Downloads and into `~/.ssh` or `System32`.
///
/// Refused: anything carrying a path separator or a drive/stream colon (`report.pdf:hidden.exe` is
/// an NTFS alternate data stream — a file that never shows up in a listing), anything with a
/// control character (a NUL truncates the name at the syscall boundary, so the file written is not
/// the file named, and the rest make the path we *report* unreadable), the pure-dot names that mean
/// "this directory" and "the one above", the empty name, and anything past what a file system will
/// take. Truncating a too-long name would save the file under a name the user was never shown.
pub fn download_file_name(raw: &str) -> Option<String> {
    // Trim BEFORE measuring, on purpose: the limit has to be about the name that is actually
    // written, and that is the trimmed one. Measuring first would refuse a perfectly good file for
    // the trailing newline a copy-paste brought along.
    let name = raw.trim();
    if name.is_empty() || name.len() > MAX_FILE_NAME_BYTES {
        return None;
    }
    // `.`, `..`, `...` — every one of them names a directory, not a file in it.
    if name.chars().all(|c| c == '.') {
        return None;
    }
    if name
        .chars()
        .any(|c| matches!(c, '/' | '\\' | ':') || c.is_control())
    {
        return None;
    }
    Some(name.to_string())
}

/// The path to write to inside `dir`, never on top of a file that is already there — or `None` when
/// every candidate is taken.
///
/// Saving twice must leave two files. A till exports its backup, exports it again after a change,
/// and silently overwriting the first one would destroy the copy the user was keeping. Same `name
/// (2).ext` convention every browser uses, so the file is where the user goes looking for it.
///
/// The number goes in before the **last** dot: `2026.08.08-backup.zip` becomes
/// `2026.08.08-backup (2).zip` and not `2026 (2).08.08-backup.zip`, which no longer reads as a date
/// and no longer sorts beside its sibling.
///
/// `taken` is asked, not assumed, so the rule is exercised without touching a disk.
pub fn free_download_path(
    dir: &Path,
    name: &str,
    taken: &dyn Fn(&Path) -> bool,
) -> Option<PathBuf> {
    let first = dir.join(name);
    if !taken(&first) {
        return Some(first);
    }
    // An empty stem means the dot is the FIRST character (`.env`): there is no name before it to
    // number, so the whole thing is the stem and ` (2)` goes on the end.
    let (stem, extension) = match name.rsplit_once('.') {
        Some((stem, ext)) if !stem.is_empty() => (stem, format!(".{ext}")),
        _ => (name, String::new()),
    };
    (2..=MAX_DOWNLOAD_COPIES).find_map(|n| {
        let candidate = dir.join(format!("{stem} ({n}){extension}"));
        (!taken(&candidate)).then_some(candidate)
    })
}

// ── Estado del shell: captura y persistencia del hub_url (ADR-0159) ──────────────────────────────

/// Normaliza la base del SaaS: sin espacios ni `/` final.
fn normalize_base(base: &str) -> String {
    base.trim().trim_end_matches('/').to_string()
}

/// URL del onboarding del SaaS que carga el primer arranque.
fn onboarding_url(base: &str) -> String {
    format!("{}/shell/", normalize_base(base))
}

/// Base del SaaS: env [`ENV_SAAS_URL`] o el default horneado.
fn saas_base_url() -> String {
    normalize_base(
        &std::env::var(ENV_SAAS_URL)
            .ok()
            .filter(|v| !v.trim().is_empty())
            .unwrap_or_else(|| DEFAULT_SAAS_URL.to_string()),
    )
}

/// The ORIGIN this installation may enter "app mode" on, or `None` if it may not.
///
/// The trust boundary of `hub.url`, and the reason it is a boundary at all: whatever ends up in
/// that file is what the window opens FULL-SCREEN, chrome-less and titled "ERPlora" on every cold
/// start from then on. So the destination is checked, not merely parsed — a hub of ours, or the
/// loopback of this machine, and nothing else.
///
/// It is deliberately the SAME rule as [`hub_url_for_host`] (what a deep link may open, ADR-0225)
/// and as `capabilities/*.json` (what may drive the hardware, ADR-0221); `tests/remote_acl.rs`
/// asserts the capture and the capabilities agree origin by origin. They have to: remembering an
/// origin the capabilities refuse produces a till that looks fine and cannot print, because every
/// `invoke` from it — down to `device_context` — is rejected by Tauri's ACL.
///
/// `https` everywhere, plus plain `http` on loopback for development. There is no opaque-origin
/// case left to reject: only `http`/`https` get here, and both are special schemes whose origin is
/// always a tuple.
fn trusted_hub_origin(url: &tauri::Url) -> Option<String> {
    // EQUIVALENT UNDER MUTATION, and kept anyway: replacing this `?` with any default changes no
    // outcome, because the scheme gate below only ever lets `http`/`https` through and neither
    // parses without a host — so the `None` branch is unreachable from here. It stays so the
    // function is total on its own terms instead of by depending on the order of the two checks.
    let host = url.host_str()?;
    let allowed = match url.scheme() {
        "https" => is_hub_domain(host) || is_loopback_host(host),
        // The cloud hub is always https; plain http is the development exemption.
        "http" => is_loopback_host(host),
        _ => false,
    };
    if !allowed {
        return None;
    }
    Some(url.origin().ascii_serialization())
}

/// Contrato de captura (ADR-0159): si la navegación lleva el marcador `?shell=1` **y** el destino
/// es uno de los nuestros ([`trusted_hub_origin`]), devuelve el ORIGEN a persistir como `hub_url`.
///
/// El marcador dice «recuérdame», no «soy de fiar»: lo lleva la URL a la que se navega, y el shell
/// nunca bloquea una navegación (`on_navigation` devuelve siempre `true`), así que sin el segundo
/// filtro basta un enlace para dejar el TPV arrancando en la página de otro — para siempre.
pub fn shell_capture_origin(url: &tauri::Url) -> Option<String> {
    let has_marker = url.query_pairs().any(|(k, v)| k == "shell" && v == "1");
    if !has_marker {
        return None;
    }
    let captured = trusted_hub_origin(url);
    if captured.is_none() {
        log::warn!(
            "shell: {} pide ser recordado y no es un hub nuestro; no se captura",
            url.origin().ascii_serialization()
        );
    }
    captured
}

/// Lee el `hub.url` persistido, reducido a su ORIGEN y pasado por [`trusted_hub_origin`].
///
/// Se revalida al LEER, no solo al escribir, porque proteger la captura solo protege a los TPV que
/// aún no han capturado nada: el que ya corrió una build sin el filtro lleva el origen ajeno en el
/// fichero, y una actualización que se lo crea otra vez no arregla justo el caso que importa. Es
/// además un fichero de texto en el directorio de datos del usuario: nada impide editarlo.
fn load_hub_url(cache_dir: &Path) -> Option<String> {
    let raw = std::fs::read_to_string(cache_dir.join(HUB_URL_FILE)).ok()?;
    // No `is_empty` guard: an empty (or blank) file does not parse as a URL, so the `?` below is
    // the same rejection written once instead of twice.
    //
    // The `trim` is EQUIVALENT UNDER MUTATION — the WHATWG parser strips leading and trailing C0
    // and space itself, so dropping it changes no outcome today. It stays because `hub.url` is OUR
    // file format: normalizing it here says so, instead of leaning on a parsing detail of a
    // dependency to make our own writes readable.
    let trimmed = raw.trim();
    let parsed: tauri::Url = trimmed.parse().ok()?;
    let trusted = trusted_hub_origin(&parsed);
    if trusted.is_none() {
        log::warn!(
            "shell: el hub recordado ({trimmed}) no es un hub nuestro; vuelvo al onboarding"
        );
    }
    trusted
}

/// Persiste el origen capturado como `hub.url` (crea `cache_dir` si no existe).
fn persist_hub_url(cache_dir: &Path, origin: &str) -> Result<(), ShellError> {
    std::fs::create_dir_all(cache_dir).map_err(|e| ShellError::Io(e.to_string()))?;
    std::fs::write(cache_dir.join(HUB_URL_FILE), origin).map_err(|e| ShellError::Io(e.to_string()))
}

/// Olvida el hub capturado (best-effort: no falla si no existía).
fn clear_hub_url(cache_dir: &Path) {
    let _ = std::fs::remove_file(cache_dir.join(HUB_URL_FILE));
}

/// Qué contesta el hub recordado cuando se le pregunta al arrancar.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum HubProbe {
    /// Contestó con este código HTTP.
    Status(u16),
    /// No se pudo contactar: sin red, DNS caído, timeout.
    Unreachable,
}

/// ¿Hay que olvidar el `hub.url` recordado?
///
/// **Solo** si el hub ya no existe. Es una decisión asimétrica a propósito: olvidarlo de más le
/// borra al usuario su hub y le manda a rehacer el onboarding, mientras que olvidarlo de menos
/// solo le deja una pantalla fea que se arregla sola en cuanto el hub vuelva. Ante la duda, se
/// conserva.
///
/// Existe porque [`forget_hub`] **no alcanza este caso**: a ese lo llama el frontend al recibir un
/// 410 del Cloud, y si el hub fue borrado la PWA no llega a cargarse nunca — el 404 lo sirve el
/// edge. Sin esto la app abre en «404 page not found» de forma permanente y sin salida por la UI.
/// Medido en un Mac el 2026-08-01 con un hub que la purga de prod se había llevado por delante.
fn should_forget_hub(probe: HubProbe) -> bool {
    match probe {
        // El hub no está. 410 es además el contrato explícito `hub_not_found` del Cloud.
        HubProbe::Status(404) | HubProbe::Status(410) => true,
        // Todo lo demás —vivo, redirigiendo al login, sin autenticar, caído o inalcanzable— es un
        // hub que SÍ existe.
        _ => false,
    }
}

/// URL inicial de la ventana, por precedencia: deep link del arranque (ADR-0196 §7) → override dev
/// ([`ENV_SHELL_URL`]) → `hub.url` persistido (modo app) → onboarding del SaaS. Pura para poder
/// testearla.
///
/// El deep link va **primero** porque es lo que el usuario está pidiendo AHORA: el override es
/// configuración estática y el hub persistido es lo de la última vez. Si ganase cualquiera de los
/// dos, pulsar «Open Terminal» del hub B desde un TPV que recuerda el A abriría el A —el negocio
/// equivocado— sin un solo error que lo delate.
fn initial_url_for(
    deep_link: Option<&str>,
    override_url: Option<&str>,
    persisted: Option<&str>,
    saas_base: &str,
) -> String {
    if let Some(target) = deep_link {
        return target.to_string();
    }
    if let Some(dev) = override_url {
        return dev.to_string();
    }
    if let Some(origin) = persisted {
        return format!("{}/", normalize_base(origin));
    }
    onboarding_url(saas_base)
}

/// Olvida el hub capturado y devuelve la ventana al onboarding del SaaS. Lo invoca el frontend
/// cuando el Cloud responde 410 `hub_not_found` (hub borrado/revocado). CONSERVA `device.id`
/// (ancla estable de la instalación). Best-effort en la navegación (sin ventana no falla).
#[tauri::command]
fn forget_hub(app: tauri::AppHandle) -> Result<(), ShellError> {
    use tauri::Manager;
    let cache_dir: PathBuf = app
        .path()
        .app_data_dir()
        .map_err(|e| ShellError::Io(e.to_string()))?;
    clear_hub_url(&cache_dir);
    if let Some(window) = app.get_webview_window("main") {
        if let Ok(url) = onboarding_url(&saas_base_url()).parse::<tauri::Url>() {
            let _ = window.navigate(url);
        }
    }
    Ok(())
}

/// `open_external_url` — hands `url` to the user's OWN browser, leaving the till where it is.
///
/// This is what the web app's `openExternal` calls inside the installed app (hub#475). It is a
/// separate program, not a tab of ours, and that is the point on two counts: the till stays exactly
/// as the user left it while they pay, and the payment happens **outside** the app — the shape
/// ADR-0114 §4 chose so the Android build can ship (Play does not allow digital goods to be paid
/// for inside the app).
///
/// A refusal is returned, never swallowed: the page turns it into something the user can read. A
/// button that does nothing when pressed is the defect this command exists to end.
#[tauri::command]
fn open_external_url(app: tauri::AppHandle, url: String) -> Result<(), ShellError> {
    use tauri_plugin_opener::OpenerExt;

    let Some(target) = external_browser_url(&url) else {
        log::warn!("shell: refused to open {url} externally — not an address of ours");
        return Err(ShellError::ExternalUrlRefused);
    };
    // `None` for `with`, deliberately: the plugin's `"inAppBrowser"` opens an Android Custom Tab,
    // which is chrome our app hosts. What is wanted here is the browser as its own app.
    app.opener()
        .open_url(target, None::<&str>)
        .map_err(|e| ShellError::ExternalUrlUnavailable(e.to_string()))
}

/// `save_download` — writes bytes the page already holds into the user's Downloads folder and
/// answers with the path (hub#480).
///
/// The sibling of `open_external_url`, for the other half of ADR-0255: three `window.open` calls
/// were left behind there, and all three were about **saving a file**, not about going somewhere.
/// Sending a browser is no answer for them — the bytes of a `/files` download, of a backup export
/// and of an invoice PDF are fetched with the hub session attached, and a separate program has no
/// session to fetch them again with.
///
/// So the page keeps the bytes and the shell keeps the disk. What comes back is the **path**,
/// because inside the installed app nothing else would say the file arrived: there is no download
/// shelf, no notification and no Downloads button, and wry's own default handler writes the file
/// without a word.
///
/// Refusals are returned, never swallowed — and one of them is a sentence in its own right:
/// `downloads_unreachable` means this device has no Downloads folder the user could open, which the
/// page must say out loud instead of reporting a path into storage nobody can browse.
#[tauri::command]
fn save_download(
    app: tauri::AppHandle,
    name: String,
    data_base64: String,
) -> Result<SavedDownload, ShellError> {
    use base64::Engine as _;
    use tauri::Manager;

    // `std::env::consts::OS` is the TARGET the binary was compiled for, so on the Android build it
    // reads `"android"` — the same string the tests reason about.
    let dir = reachable_downloads_dir(std::env::consts::OS, app.path().download_dir().ok())
        .inspect_err(|e| log::warn!("shell: nowhere to save {name:?}: {e}"))?;
    let Some(file_name) = download_file_name(&name) else {
        log::warn!("shell: refused to save {name:?} — that is not a file name");
        return Err(ShellError::DownloadRefused);
    };
    let bytes = base64::engine::general_purpose::STANDARD
        .decode(data_base64.as_bytes())
        .map_err(|_| ShellError::DownloadRefused)?;

    std::fs::create_dir_all(&dir).map_err(|e| ShellError::Io(e.to_string()))?;
    let path = free_download_path(&dir, &file_name, &|candidate| candidate.exists())
        .ok_or(ShellError::DownloadRefused)?;
    std::fs::write(&path, &bytes).map_err(|e| ShellError::Io(e.to_string()))?;

    Ok(SavedDownload {
        path: path.display().to_string(),
    })
}

/// Pregunta en segundo plano si el hub recordado sigue existiendo y, si no, lo olvida y devuelve
/// la ventana al onboarding.
///
/// En segundo plano a propósito: la ventana ya está abierta y mostrando el hub, así que en el
/// caso normal —el hub existe— esto no se nota. En el caso malo el usuario ve el 404 un instante
/// y acaba en el onboarding, que es de donde puede salir. Bloquear el arranque para evitar ese
/// parpadeo penalizaría **todos** los arranques por un caso raro.
///
/// Un `HEAD` basta y no descarga la PWA entera. El timeout es corto porque no hay prisa: si no
/// contesta a tiempo se conserva el hub, que es la decisión segura ([`should_forget_hub`]).
///
/// Va por el runtime **async** de Tauri y con el cliente async de reqwest, NO por
/// `std::thread` + `reqwest::blocking`. Medido en el emulador API 37: con el cliente blocking la
/// petición **no llegaba a salir** en Android —ni un solo `HEAD` en el servidor— así que el
/// rescate no existía justo en la plataforma donde el usuario no puede borrar datos de la app a
/// mano. En macOS sí funcionaba, que es lo que lo hacía fácil de dar por bueno.
fn spawn_hub_liveness_check(app: tauri::AppHandle, cache_dir: PathBuf, origin: String) {
    tauri::async_runtime::spawn(async move {
        use tauri::Manager;

        let url = format!("{}/", normalize_base(&origin));
        let probe = match reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(6))
            .build()
        {
            Ok(c) => match c.head(&url).send().await {
                Ok(r) => HubProbe::Status(r.status().as_u16()),
                Err(e) => {
                    log::warn!("shell: no se pudo consultar el hub recordado ({origin}): {e}");
                    HubProbe::Unreachable
                }
            },
            Err(e) => {
                log::warn!("shell: no se pudo crear el cliente HTTP: {e}");
                HubProbe::Unreachable
            }
        };
        if !should_forget_hub(probe) {
            return;
        }

        log::info!("shell: el hub recordado ({origin}) ya no existe ({probe:?}); vuelvo al onboarding");
        clear_hub_url(&cache_dir);
        if let Some(window) = app.get_webview_window("main") {
            if let Ok(url) = onboarding_url(&saas_base_url()).parse::<tauri::Url>() {
                let _ = window.navigate(url);
            }
        }
    });
}

/// Lleva la ventana principal a `url`. Best-effort a propósito: sin ventana (o con una URL que no
/// parsea) no hay nada que dirigir, y un enlace no puede tumbar la app.
fn navigate_main_window(app: &tauri::AppHandle, url: &str) {
    use tauri::Manager;
    let Some(window) = app.get_webview_window("main") else {
        log::warn!("shell: llega un enlace pero aún no hay ventana que dirigir ({url})");
        return;
    };
    match url.parse::<tauri::Url>() {
        Ok(parsed) => {
            if let Err(e) = window.navigate(parsed) {
                log::warn!("shell: no se pudo abrir el enlace ({url}): {e}");
            }
        }
        Err(e) => log::warn!("shell: destino de enlace ilegible ({url}): {e}"),
    }
}

/// Crea la ventana principal apuntando a [`initial_url_for`] y registra el `on_navigation` que
/// captura `?shell=1` → persiste el origen como `hub.url` (una sola escritura por cambio).
fn open_main_window(app: &tauri::App, cache_dir: Option<PathBuf>) -> tauri::Result<()> {
    use tauri::{WebviewUrl, WebviewWindowBuilder};

    let persisted = cache_dir.as_deref().and_then(load_hub_url);
    let override_url = std::env::var(ENV_SHELL_URL)
        .ok()
        .filter(|v| !v.trim().is_empty());
    // Arranque EN FRÍO por deep link: en Windows y Linux el sistema contesta a un enlace lanzando
    // el ejecutable otra vez con la URL como argumento, así que aquí es donde llega. En macOS/iOS/
    // Android llega como evento y lo recoge `on_open_url` (ver `run`).
    let deep_link = deep_link_from_args(std::env::args());
    let initial = initial_url_for(
        deep_link.as_deref(),
        override_url.as_deref(),
        persisted.as_deref(),
        &saas_base_url(),
    );
    let url = match initial.parse::<tauri::Url>() {
        Ok(u) => WebviewUrl::External(u),
        Err(e) => {
            // Degradado: página estática empaquetada (shell-dist). No debería pasar salvo un
            // ERPLORA_SHELL_URL/ERPLORA_SAAS_URL malformado.
            eprintln!("shell: URL inicial inválida ({initial}): {e}; cargo la página degradada");
            WebviewUrl::App("index.html".into())
        }
    };

    // Si se arranca contra un hub recordado, hay que comprobar que sigue existiendo — pero DESPUÉS
    // de abrir la ventana, no antes: bloquear el arranque de un TPV por una petición de red sería
    // peor que la pantalla que se intenta evitar.
    //
    // Con deep link NO se comprueba: la ventana está en el hub del ENLACE, no en el recordado, y
    // este chequeo termina navegando al onboarding — se llevaría por delante justo lo que el
    // usuario acaba de pedir. El `?shell=1` del enlace ya reemplaza el `hub.url` recordado.
    if override_url.is_none() && deep_link.is_none() {
        if let (Some(dir), Some(origin)) = (cache_dir.clone(), persisted.clone()) {
            spawn_hub_liveness_check(app.handle().clone(), dir, origin);
        }
    }

    let last = std::sync::Mutex::new(persisted);
    WebviewWindowBuilder::new(app, "main", url)
        .title("ERPlora")
        .inner_size(1280.0, 800.0)
        .min_inner_size(960.0, 600.0)
        .on_navigation(move |nav| {
            if let (Some(dir), Some(origin)) = (cache_dir.as_deref(), shell_capture_origin(nav)) {
                if let Ok(mut guard) = last.lock() {
                    if guard.as_deref() != Some(origin.as_str()) {
                        match persist_hub_url(dir, &origin) {
                            Ok(()) => *guard = Some(origin),
                            Err(e) => eprintln!("shell: no se pudo persistir hub.url: {e}"),
                        }
                    }
                }
            }
            true // el shell nunca bloquea la navegación; solo observa el marcador
        })
        .build()?;
    Ok(())
}

// ── Camino de hardware: handlers `invoke` → erplora-peripherals ──────────────────────────────────
//
// El shell ES el bridge (no hay proceso bridge aparte, §2.7): el hardware se expone por handlers
// `invoke` que delegan en `erplora-peripherals`. El contrato de datos lo heredó de las frames WS
// del bridge standalone (retirado en hub#340) y no cambió: `getDevices` devuelve el array de
// `protocol::Device` y `discoverPrinters` el outcome `PrinterDiscovery` (serde-serializado igual
// que `BridgeDevice`/`PrinterDiscovery` del SDK); `print`/`testPrint`/`openDrawer` no devuelven nada.
//
// El `Watchdog` del registry corre como tarea async del shell (auto-recuperación de IP por DHCP),
// y la `PrintQueue` con reintentos drena en segundo plano. Los outcomes y eventos del watchdog se
// loguean; el canal hacia la UI se cablearía con eventos Tauri en una fase posterior.

use erplora_peripherals::discovery::{self, parse_printer_id, LocalNetworkAccess, PrinterDiscovery};
use erplora_peripherals::drawer;
use erplora_peripherals::escpos::{self, DocumentType};
use erplora_peripherals::protocol::Device;
use erplora_peripherals::queue::{JobOutcome, PrintJob, PrintQueue, RetryPolicy};
use erplora_peripherals::registry::DeviceRegistry;

/// Estado de hardware compartido entre handlers `invoke`: registro persistente de dispositivos +
/// cola de impresión con reintentos. Vive en el estado gestionado de Tauri (`app.manage`). El
/// registro y la cola van tras `Arc` para que las tareas de fondo (watchdog + worker de la cola)
/// compartan las mismas instancias que los handlers `invoke`.
struct PeripheralsState {
    registry: std::sync::Arc<DeviceRegistry>,
    queue: std::sync::Arc<PrintQueue>,
}

/// Construye el estado de hardware y **lanza** las tareas de fondo en el runtime tokio actual:
///   - worker de la `PrintQueue` (envío con reintentos; cada `JobOutcome` se loguea),
///   - `Watchdog` del registry (health-check + recovery por MAC ante cambio de IP DHCP).
/// Heredado de `spawn_queue_worker`/`spawn_watchdog` del bridge standalone (retirado en hub#340).
fn build_peripherals_state(devices_path: PathBuf) -> PeripheralsState {
    let registry = std::sync::Arc::new(DeviceRegistry::load(devices_path));
    let queue = std::sync::Arc::new(PrintQueue::new(RetryPolicy::default()));

    // Worker de la cola de impresión: drena y reintenta; loguea cada outcome. `async_runtime::spawn`
    // usa el runtime tokio global de Tauri, así que funciona desde el `setup` hook.
    let worker_queue = queue.clone();
    tauri::async_runtime::spawn(async move {
        let (outcomes_tx, mut outcomes_rx) = tokio::sync::mpsc::unbounded_channel::<JobOutcome>();
        tauri::async_runtime::spawn(async move {
            while let Some(outcome) = outcomes_rx.recv().await {
                match outcome {
                    JobOutcome::Completed { job_id } => {
                        eprintln!("peripherals: trabajo de impresión completado ({job_id:?})")
                    }
                    JobOutcome::Failed { job_id, error } => {
                        eprintln!("peripherals: trabajo de impresión fallido ({job_id:?}): {error}")
                    }
                }
            }
        });
        worker_queue.run(outcomes_tx).await;
        eprintln!("peripherals: worker de la cola de impresión terminado (cola cerrada)");
    });

    // Watchdog del registry: auto-recuperación de dispositivos tras cambio de IP por DHCP.
    let watchdog_registry = registry.clone();
    tauri::async_runtime::spawn(async move {
        use erplora_peripherals::registry::{Watchdog, WatchdogConfig, WatchdogEvent};
        let (events_tx, mut events_rx) = tokio::sync::mpsc::unbounded_channel::<WatchdogEvent>();
        tauri::async_runtime::spawn(async move {
            while let Some(ev) = events_rx.recv().await {
                match ev {
                    // `key` y no `mac`: es la identidad estable del dispositivo y siempre existe
                    // (la MAC es `None` cuando ARP no resuelve — siempre en Android).
                    WatchdogEvent::Recovered(d) => {
                        eprintln!("peripherals: dispositivo recuperado {} ({})", d.name, d.key)
                    }
                    WatchdogEvent::Lost(d) => {
                        eprintln!("peripherals: dispositivo perdido {} ({})", d.name, d.key)
                    }
                }
            }
        });
        let watchdog = Watchdog::new(WatchdogConfig::default()).with_events(events_tx);
        watchdog.run(&watchdog_registry).await;
    });

    PeripheralsState { registry, queue }
}

/// Error de los handlers de hardware. Se serializa como string para el frontend (igual que el
/// `Event::Error` del bridge standalone se mapea a un rechazo de la promesa en el SDK).
#[derive(Debug, thiserror::Error)]
pub enum HardwareError {
    #[error("{0}")]
    Peripheral(#[from] erplora_peripherals::PeripheralError),
}

impl Serialize for HardwareError {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&self.to_string())
    }
}

/// `erplora_bridge_status` — el `IpcBridgeTransport.detect()` lo invoca para saber si el canal de
/// hardware existe (en el shell siempre existe: el shell ES el bridge). Devuelve la versión.
#[tauri::command]
fn erplora_bridge_status() -> serde_json::Value {
    serde_json::json!({ "version": env!("CARGO_PKG_VERSION") })
}

/// Reads the Android runtime-permission map and says whether the printer sweep may run.
///
/// Pure on purpose: an emulator is the only other way to reach this branch, and a state that
/// decides between two opposite messages to the user has to be provable on a laptop.
///
/// A permission the map does not mention is one this platform does not gate — desktop answers with
/// an empty map, and so does an Android older than the release that introduced it. Reading that
/// silence as "denied" would ground a till that can see its printer perfectly well.
fn local_network_access(status: &std::collections::HashMap<String, bool>) -> LocalNetworkAccess {
    match status.get(tauri_plugin_erplora_android::ACCESS_LOCAL_NETWORK) {
        Some(false) => LocalNetworkAccess::Denied {
            permission: tauri_plugin_erplora_android::ACCESS_LOCAL_NETWORK.to_string(),
        },
        _ => LocalNetworkAccess::Granted,
    }
}

/// What the OS allows right now — asked without prompting: the PWA already requested the
/// permission before invoking this, so here we only read the answer it gave.
fn shell_local_network_access<R: tauri::Runtime>(app: &tauri::AppHandle<R>) -> LocalNetworkAccess {
    use tauri_plugin_erplora_android::ErploraAndroidExt;

    match app.erplora_android().check_permissions() {
        Ok(status) => local_network_access(&status),
        // The CHECK failing is not a denial — on desktop there is no Android activity to ask. If
        // we treated it as one, the shell would start claiming "no permission" on the platform
        // that has no such permission, which is the same lie pointing the other way.
        Err(e) => {
            log::warn!("shell: could not read the local network permission ({e}); scanning anyway");
            LocalNetworkAccess::Granted
        }
    }
}

/// `erplora_discover_printers` — re-escanea la red (mDNS + subred), registra y devuelve las
/// impresoras. Espejo de `Command::DiscoverPrinters` del bridge.
///
/// Devuelve el OUTCOME (`{status, …}`), no el array pelado: sin permiso de red local no hay lista
/// vacía que devolver, hay una razón — y «conecta una impresora» y «da permiso a la app» son
/// instrucciones opuestas para el usuario (hub#338).
#[tauri::command]
async fn erplora_discover_printers(
    app: tauri::AppHandle,
    state: tauri::State<'_, PeripheralsState>,
) -> Result<PrinterDiscovery, HardwareError> {
    let access = shell_local_network_access(&app);
    Ok(discovery::discover_printers(&state.registry, access).await?)
}

/// `erplora_get_devices` — contenido del registro persistente de dispositivos (con sus roles).
#[tauri::command]
fn erplora_get_devices(state: tauri::State<'_, PeripheralsState>) -> Vec<Device> {
    state.registry.get_all()
}

/// `erplora_print` — renders the ESC/POS document and **queues** it for sending with retries (same
/// flow as the bridge's `Command::Print`). Errors before the enqueue (bad printer_id/payload) come
/// back to the caller; the outcome of the send arrives through the queue's worker (log).
///
/// **An unknown `document_type` is refused, not printed as `Generic`** (hub#501). This is the end of
/// the chain: the queue in the hub already checks the vocabulary, but a document that got past it —
/// a job written by hand, a producer talking straight to this command — would otherwise reach the
/// paper as a nameless key/value dump, and a kitchen order that comes out wrong is only discovered
/// when the plate is missing. Failing here turns that into a `failed` the print host reports.
#[tauri::command]
fn erplora_print(
    state: tauri::State<'_, PeripheralsState>,
    printer_id: String,
    document_type: String,
    data: serde_json::Value,
    job_id: Option<String>,
) -> Result<(), HardwareError> {
    let target = parse_printer_id(&printer_id)?;
    let doc = DocumentType::parse(&document_type).ok_or_else(|| {
        HardwareError::from(erplora_peripherals::PeripheralError::UnknownDocumentType(
            document_type.clone(),
        ))
    })?;
    let payload = escpos::render_document(doc, &data)?;
    state.queue.enqueue(PrintJob {
        job_id,
        target,
        payload,
        attempts: 0,
    })?;
    Ok(())
}

/// `erplora_test_print` — encola una página de prueba en la impresora dada.
#[tauri::command]
fn erplora_test_print(
    state: tauri::State<'_, PeripheralsState>,
    printer_id: String,
) -> Result<(), HardwareError> {
    let target = parse_printer_id(&printer_id)?;
    let payload = escpos::render_test_page(&printer_id);
    state.queue.enqueue(PrintJob {
        job_id: None,
        target,
        payload,
        attempts: 0,
    })?;
    Ok(())
}

/// `erplora_open_drawer` — abre el cajón vía kick ESC/POS por el socket de la impresora.
#[tauri::command]
async fn erplora_open_drawer(printer_id: String, pin: Option<u8>) -> Result<(), HardwareError> {
    let target = parse_printer_id(&printer_id)?;
    drawer::open_drawer(&target, pin.unwrap_or(2)).await?;
    Ok(())
}

/// `erplora_set_device_role` — asigna rol (receipt/kitchen/bar/label) y devuelve el registro
/// actualizado. Espejo de `Command::SetDeviceRole`.
#[tauri::command]
fn erplora_set_device_role(
    state: tauri::State<'_, PeripheralsState>,
    mac: String,
    role: String,
) -> Result<Vec<Device>, HardwareError> {
    state.registry.set_role(&mac, &role)?;
    Ok(state.registry.get_all())
}

/// `erplora_set_device_name` — renombra un dispositivo y devuelve el registro actualizado.
#[tauri::command]
fn erplora_set_device_name(
    state: tauri::State<'_, PeripheralsState>,
    mac: String,
    name: String,
) -> Result<Vec<Device>, HardwareError> {
    state.registry.set_name(&mac, &name)?;
    Ok(state.registry.get_all())
}

/// `erplora_remove_device` — elimina un dispositivo del registro y devuelve el registro actualizado.
#[tauri::command]
fn erplora_remove_device(
    state: tauri::State<'_, PeripheralsState>,
    mac: String,
) -> Result<Vec<Device>, HardwareError> {
    state.registry.remove(&mac)?;
    Ok(state.registry.get_all())
}

/// `erplora_notify` — notificación del SISTEMA (la del SO, no un toast dentro de la app).
///
/// Para eso existe: avisar cuando **nadie está mirando la pantalla**. El caso que la motiva es la
/// comanda — entra un pedido y cocina tiene que enterarse aunque la tablet esté en otra vista o
/// bloqueada. Un toast de la app no sirve ahí.
///
/// Lo expone el SHELL porque en Tauri el shell **es** el bridge (ADR-0050 §2.7); el binario suelto
/// (retirado en hub#340) lo hacía con `notify_rust` para el caso «PWA en Chrome». El protocolo lo
/// declaraba desde el principio (`Command::SendNotification`) y este era el lado que faltaba: sin
/// él, ningún módulo podía avisar de nada desde la app.
///
/// **Nunca falla hacia arriba.** Si el usuario denegó el permiso o la plataforma no puede
/// mostrarla, se registra y se sigue: una notificación que no sale no puede tumbar la comanda que
/// la provocó.
#[tauri::command]
fn erplora_notify(app: tauri::AppHandle, title: String, body: String) {
    use tauri_plugin_notification::NotificationExt;

    if let Err(e) = app.notification().builder().title(&title).body(&body).show() {
        eprintln!("notify: la plataforma no pudo mostrar «{title}» ({e}) — se sigue igualmente");
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder = tauri::Builder::default();

    // Escritorio: el sistema contesta a un `erplora://` LANZANDO el ejecutable otra vez. Sin esto,
    // pulsar un enlace con la app abierta arrancaría un SEGUNDO TPV encima del primero (dos
    // ventanas, dos colas de impresión, dos watchdogs). Con esto, la segunda instancia muere al
    // nacer y le pasa sus argumentos a la que ya está viva, que es la que navega.
    #[cfg(desktop)]
    let builder = builder.plugin(tauri_plugin_single_instance::init(|app, argv, _cwd| {
        if let Some(target) = deep_link_from_args(argv) {
            navigate_main_window(app, &target);
        }
    }));

    builder
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_erplora_android::init())
        // The user's own browser (hub#475). Registered for its RUST api only: no `opener:*`
        // permission is granted to any origin (`tests/remote_acl.rs`), so the page cannot reach the
        // plugin's own commands — which take any address, and two of which open FILES. What the
        // page gets is `open_external_url`, which checks the destination first.
        .plugin(tauri_plugin_opener::init())
        // Deep link `erplora://` (ADR-0196 §7): registro del esquema por plataforma + entrega de la
        // URL. Va DESPUÉS de single-instance a propósito: el orden que documenta el propio plugin.
        .plugin(tauri_plugin_deep_link::init())
        .setup(|app| {
            use tauri::Manager;
            use tauri_plugin_deep_link::DeepLinkExt;

            // Enlace con la app YA abierta (macOS, iOS y Android lo entregan como evento; en
            // escritorio lo reinyecta single-instance). El de arranque en frío no pasa por aquí:
            // ese llega por argumentos y lo resuelve `open_main_window`.
            //
            // Un enlace que NO resuelve no hace nada, a propósito: el fallback es del navegador que
            // lo lanzó, y navegar «a algo» sería peor que quedarse quieto.
            let handle = app.handle().clone();
            app.deep_link().on_open_url(move |event| {
                // Mismo filtro que el arranque en frío: un solo enlace por gesto y, si llegaran
                // varios, manda el primero que resuelva.
                let urls = event.urls().into_iter().map(String::from);
                match deep_link_from_args(urls) {
                    Some(target) => navigate_main_window(&handle, &target),
                    None => log::warn!("shell: enlace ignorado, no apunta a un hub nuestro"),
                }
            });

            // Windows y Linux aprenden el esquema al INSTALAR (registro / handler `.desktop`), así
            // que en una ejecución de desarrollo —sin instalador— no está registrado y el enlace no
            // se puede ni probar. Registrarlo aquí solo afecta a esa ejecución.
            #[cfg(any(windows, target_os = "linux"))]
            if let Err(e) = app.deep_link().register_all() {
                log::warn!("shell: no se pudo registrar el esquema {DEEP_LINK_SCHEME}://: {e}");
            }

            // Raíz de datos por-instalación: device.id + hub.url + devices.json. Si no se puede
            // resolver, el shell arranca igualmente (sin persistencia) — cliente fino, sin BD.
            let cache_dir = match app.path().app_data_dir() {
                Ok(dir) => {
                    if let Err(e) = std::fs::create_dir_all(&dir) {
                        eprintln!("shell: no se pudo crear app_data_dir ({}): {e}", dir.display());
                    }
                    Some(dir)
                }
                Err(e) => {
                    eprintln!("shell: app_data_dir no disponible: {e}");
                    None
                }
            };
            // Estado de hardware: registro de dispositivos + cola de impresión + watchdog.
            let devices_path = cache_dir
                .as_deref()
                .map(|d| d.join(DEVICES_FILE))
                .unwrap_or_else(|| PathBuf::from(DEVICES_FILE));
            app.manage(build_peripherals_state(devices_path));
            // Ventana única: onboarding del SaaS o el hub capturado (modo app).
            if let Err(e) = open_main_window(app, cache_dir) {
                eprintln!("no se pudo crear la ventana principal: {e}");
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            device_context,
            forget_hub,
            open_external_url,
            save_download,
            // Datos: NO van por `invoke` (ADR-0050) — la PWA habla HTTP+WS con su hub cloud.
            // Camino de hardware: impresoras de red ESC/POS + cajón → peripherals.
            erplora_bridge_status,
            erplora_discover_printers,
            erplora_get_devices,
            erplora_print,
            erplora_test_print,
            erplora_open_drawer,
            erplora_set_device_role,
            erplora_set_device_name,
            erplora_remove_device,
            erplora_notify
        ])
        .run(tauri::generate_context!())
        .expect("error while running ERPlora shell");
}

// ── Tests (TDD, ADR-0159) ────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn url(s: &str) -> tauri::Url {
        s.parse().expect("url de test válida")
    }

    fn tempdir() -> PathBuf {
        let dir = std::env::temp_dir().join(format!("erplora-shell-test-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&dir).expect("tempdir");
        dir
    }

    // ── shell_capture_origin: el contrato del marcador ?shell=1 ──────────────────────────────

    #[test]
    fn capture_requiere_el_marcador_shell_1() {
        assert_eq!(shell_capture_origin(&url("https://demo.erplora.com/")), None);
        assert_eq!(
            shell_capture_origin(&url("https://demo.erplora.com/?shell=2")),
            None
        );
        assert_eq!(
            shell_capture_origin(&url("https://demo.erplora.com/?other=1")),
            None
        );
    }

    #[test]
    fn capture_devuelve_el_origen_https() {
        assert_eq!(
            shell_capture_origin(&url("https://demo.erplora.com/pos?shell=1&x=2")),
            Some("https://demo.erplora.com".to_string())
        );
    }

    #[test]
    fn capture_http_solo_loopback() {
        // http remoto NO se captura (el hub cloud es siempre https).
        assert_eq!(shell_capture_origin(&url("http://evil.com/?shell=1")), None);
        // loopback sí (desarrollo local: runtime :8787 / Vite :5173).
        assert_eq!(
            shell_capture_origin(&url("http://127.0.0.1:8787/?shell=1")),
            Some("http://127.0.0.1:8787".to_string())
        );
        assert_eq!(
            shell_capture_origin(&url("http://localhost:5173/?shell=1")),
            Some("http://localhost:5173".to_string())
        );
    }

    #[test]
    fn capture_rechaza_esquemas_no_http() {
        assert_eq!(shell_capture_origin(&url("tauri://localhost/?shell=1")), None);
        assert_eq!(shell_capture_origin(&url("file:///tmp/x?shell=1")), None);
    }

    // ── hub#335: the marker says "remember me"; it does not say WHO may ask ───────────────────
    //
    // `?shell=1` was the whole capture contract, so ANY https origin that carried it became the
    // origin this installation boots at, for good. The shell never blocks a navigation
    // (`on_navigation` always returns `true`), so one link is enough: an open redirect on the SaaS,
    // an injection into the third-party checkout the same window loads, or simply a link a user
    // taps. From then on the till opens full-screen, chrome-less and titled "ERPlora" on somebody
    // else's page, and the operator types the hub password into it.
    //
    // The destination rule is therefore the SAME one the deep link already applies (ADR-0225) and
    // the same one `capabilities/*.json` declares (ADR-0221): only a hub of ours, or the loopback
    // of this machine. The three must agree — an origin the capabilities refuse is a till that
    // looks fine and cannot print, which is the failure `remote_acl.rs` exists to prevent.

    #[test]
    fn capture_refuses_an_origin_that_is_not_a_hub_of_ours() {
        // The one the old suite ENSHRINED: `capture_conserva_el_puerto_no_default` asserted that
        // `https://hub.example.com:8443/?shell=1` was captured. Preserving a non-default port is
        // right; treating a stranger's domain as this till's hub never was.
        assert_eq!(
            shell_capture_origin(&url("https://hub.example.com:8443/?shell=1")),
            None
        );
        assert_eq!(shell_capture_origin(&url("https://evil.com/?shell=1")), None);
    }

    #[test]
    fn capture_refuses_the_saas_apex() {
        // `erplora.com` is where the app BOOTS, not a hub — and it is deliberately kept out of the
        // hardware capability (ADR-0221). Remembering it would pin the till to the marketing site
        // on every cold start, with the onboarding one redirect further away than before.
        assert_eq!(shell_capture_origin(&url("https://erplora.com/?shell=1")), None);
        assert_eq!(
            shell_capture_origin(&url("https://erplora.com/shell/?shell=1")),
            None
        );
    }

    #[test]
    fn capture_refuses_the_domains_that_only_look_like_ours() {
        // Same three shapes `remote_acl.rs` rejects at the ACL, checked here at the capture: a
        // boundary that only holds in one of the two places holds nowhere.
        assert_eq!(
            shell_capture_origin(&url("https://demo.a.erplora.com.attacker.com/?shell=1")),
            None
        );
        assert_eq!(shell_capture_origin(&url("https://myerplora.com/?shell=1")), None);
        // Reads as ours to a human; the host is `evil.com`.
        assert_eq!(
            shell_capture_origin(&url("https://demo.a.erplora.com@evil.com/?shell=1")),
            None
        );
    }

    #[test]
    fn capture_accepts_every_shape_a_real_cloud_hub_takes() {
        // Lettered aura (Hetzner) and numbered aura (AWS fallback) — TWO labels under the
        // registrable domain. A rule that only allowed one would kill the app in production.
        assert_eq!(
            shell_capture_origin(&url("https://panaderia.a.erplora.com/pos?shell=1&x=2")),
            Some("https://panaderia.a.erplora.com".to_string())
        );
        assert_eq!(
            shell_capture_origin(&url("https://panaderia.3.erplora.com/?shell=1")),
            Some("https://panaderia.3.erplora.com".to_string())
        );
    }

    #[test]
    fn capture_accepts_loopback_over_tls_too() {
        // A dev PWA served over TLS (`vite --https`) is the same machine as the plain-http one, so
        // the loopback exemption belongs to the HOST, not to the scheme.
        assert_eq!(
            shell_capture_origin(&url("https://127.0.0.1:5173/?shell=1")),
            Some("https://127.0.0.1:5173".to_string())
        );
    }

    // ── hub#335: an install poisoned by an older build must not stay poisoned ─────────────────

    #[test]
    fn a_persisted_origin_that_is_not_a_hub_of_ours_is_refused_on_load() {
        // Refusing at the capture only protects installs that have not been captured yet. Every
        // till that already ran a build without the check carries the foreign origin in
        // `hub.url`, and an upgrade that keeps reading it blindly fixes nothing where it matters.
        // `None` sends the window back to the onboarding, which is the one screen it can leave.
        let dir = tempdir();
        std::fs::write(dir.join(HUB_URL_FILE), "https://evil.com").expect("write");
        assert_eq!(load_hub_url(&dir), None);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_persisted_value_that_is_not_even_a_url_is_refused_on_load() {
        // `hub.url` is a plain file in the user's data dir: nothing stops it being edited, or
        // truncated by a crash. `initial_url_for` used to hand whatever it said to the webview.
        let dir = tempdir();
        std::fs::write(dir.join(HUB_URL_FILE), "not a url").expect("write");
        assert_eq!(load_hub_url(&dir), None);
        std::fs::write(dir.join(HUB_URL_FILE), "javascript:alert(1)").expect("write");
        assert_eq!(load_hub_url(&dir), None);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_persisted_hub_loads_reduced_to_its_ORIGIN() {
        // Whatever ends up in the file, what boots is the origin: a stored path or query would
        // otherwise be replayed on every cold start.
        let dir = tempdir();
        std::fs::write(dir.join(HUB_URL_FILE), "https://demo.a.erplora.com/pos?x=1\n").expect("write");
        assert_eq!(load_hub_url(&dir), Some("https://demo.a.erplora.com".to_string()));
        let _ = std::fs::remove_dir_all(&dir);
    }

    // ── hub#335: a user with SEVERAL hubs ─────────────────────────────────────────────────────

    #[test]
    fn capturing_a_second_hub_replaces_the_first() {
        // How switching hubs works, and the reason it needs no extra machinery: `/shell/?choose=1`
        // lists the user's hubs and 302s into the chosen one carrying the marker, so the capture
        // that persists hub B is the same one that persisted hub A. Were the first capture sticky,
        // a till moved to another business would keep opening the old one.
        let dir = tempdir();
        persist_hub_url(&dir, "https://a.a.erplora.com").expect("first");
        persist_hub_url(&dir, "https://b.a.erplora.com").expect("second");
        assert_eq!(load_hub_url(&dir), Some("https://b.a.erplora.com".to_string()));
        let _ = std::fs::remove_dir_all(&dir);
    }

    // ── persistencia de hub.url ──────────────────────────────────────────────────────────────

    #[test]
    fn hub_url_roundtrip_persist_load_clear() {
        let dir = tempdir();
        assert_eq!(load_hub_url(&dir), None);
        persist_hub_url(&dir, "https://demo.erplora.com").expect("persist");
        assert_eq!(load_hub_url(&dir), Some("https://demo.erplora.com".to_string()));
        clear_hub_url(&dir);
        assert_eq!(load_hub_url(&dir), None);
        clear_hub_url(&dir); // best-effort: repetir no falla
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn load_hub_url_ignora_vacios_y_recorta() {
        let dir = tempdir();
        std::fs::write(dir.join(HUB_URL_FILE), "  \n").expect("write");
        assert_eq!(load_hub_url(&dir), None);
        std::fs::write(dir.join(HUB_URL_FILE), "https://a.erplora.com\n").expect("write");
        assert_eq!(load_hub_url(&dir), Some("https://a.erplora.com".to_string()));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn persist_hub_url_crea_el_directorio() {
        let dir = tempdir().join("anidado");
        persist_hub_url(&dir, "https://b.erplora.com").expect("persist");
        assert_eq!(load_hub_url(&dir), Some("https://b.erplora.com".to_string()));
        let _ = std::fs::remove_dir_all(dir.parent().unwrap());
    }

    // ── URL inicial: precedencia override dev → hub persistido → onboarding ──────────────────

    #[test]
    fn initial_url_precedencia() {
        // Override de desarrollo gana siempre.
        assert_eq!(
            initial_url_for(
                None,
                Some("http://127.0.0.1:8001/shell/"),
                Some("https://demo.erplora.com"),
                "https://erplora.com"
            ),
            "http://127.0.0.1:8001/shell/"
        );
        // Hub persistido → modo app (origen + "/").
        assert_eq!(
            initial_url_for(None, None, Some("https://demo.erplora.com"), "https://erplora.com"),
            "https://demo.erplora.com/"
        );
        // Nada persistido → onboarding del SaaS.
        assert_eq!(
            initial_url_for(None, None, None, "https://erplora.com"),
            "https://erplora.com/shell/"
        );
    }

    #[test]
    fn a_cold_start_through_a_link_opens_the_hub_the_link_named() {
        // Windows and Linux answer a link by launching the executable with the URL appended, so at
        // a COLD start the link is all there is. If the persisted hub won, clicking "Open Terminal"
        // for hub B from a till that remembers hub A would quietly open A — the wrong business,
        // and with no error to notice it by.
        assert_eq!(
            initial_url_for(
                Some("https://demo.b.erplora.com/?shell=1"),
                None,
                Some("https://demo.a.erplora.com"),
                "https://erplora.com"
            ),
            "https://demo.b.erplora.com/?shell=1"
        );
        // It also beats the dev override: the override is static configuration, the link is what
        // the user is asking for right now.
        assert_eq!(
            initial_url_for(
                Some("https://demo.b.erplora.com/?shell=1"),
                Some("http://127.0.0.1:8001/shell/"),
                None,
                "https://erplora.com"
            ),
            "https://demo.b.erplora.com/?shell=1"
        );
    }

    // ── El hub recordado ya no existe: la app NO puede quedarse tapiada ──────────────────────

    #[test]
    fn un_hub_borrado_se_olvida_al_arrancar() {
        // Medido en un Mac el 2026-08-01: `hub.url` apuntaba a un hub que la purga de prod había
        // borrado, y la app abría en «404 page not found» — para siempre y SIN salida. El
        // `forget_hub` que ya existe no sirve aquí: lo invoca el frontend al recibir un 410, y en
        // este caso la PWA no llega a cargarse nunca porque el 404 lo sirve el edge.
        assert!(should_forget_hub(HubProbe::Status(404)));
        // 410 es el contrato explícito de `hub_not_found` del Cloud.
        assert!(should_forget_hub(HubProbe::Status(410)));
    }

    #[test]
    fn un_hub_vivo_no_se_olvida() {
        assert!(!should_forget_hub(HubProbe::Status(200)));
        // El hub redirige al login: existe.
        assert!(!should_forget_hub(HubProbe::Status(302)));
    }

    #[test]
    fn no_estar_autenticado_no_es_que_el_hub_no_exista() {
        // Confundirlo echaría al usuario al onboarding cada vez que le caduca la sesión.
        assert!(!should_forget_hub(HubProbe::Status(401)));
        assert!(!should_forget_hub(HubProbe::Status(403)));
    }

    #[test]
    fn un_hub_caido_no_se_olvida() {
        // Caído ≠ inexistente. Olvidarlo por una caída de 30 s le borraría al usuario su hub y le
        // obligaría a rehacer el onboarding, que es MUCHO peor que esperar.
        for s in [500, 502, 503, 504] {
            assert!(!should_forget_hub(HubProbe::Status(s)), "{s} no debe olvidar el hub");
        }
    }

    #[test]
    fn sin_red_no_se_olvida_nada() {
        // Un TPV arranca en locales con wifi malo, con el router reiniciándose o con el portátil
        // aún sin asociar. Borrar el hub por no poder contactarlo sería catastrófico: el hub está
        // perfectamente vivo y el usuario acabaría en el onboarding sin entender por qué.
        assert!(!should_forget_hub(HubProbe::Unreachable));
    }

    #[test]
    fn onboarding_url_normaliza_la_base() {
        assert_eq!(onboarding_url("https://erplora.com"), "https://erplora.com/shell/");
        assert_eq!(
            initial_url_for(None, None, None, "https://erplora.com/"),
            "https://erplora.com/shell/"
        );
        assert_eq!(normalize_base("  https://erplora.com/  "), "https://erplora.com");
    }

    // ── identidad de dispositivo ─────────────────────────────────────────────────────────────

    #[test]
    fn ensure_device_id_estable_entre_llamadas() {
        let dir = tempdir();
        let a = ensure_device_id(&dir).expect("primera");
        let b = ensure_device_id(&dir).expect("segunda");
        assert_eq!(a, b);
        assert!(!a.is_empty());
        let _ = std::fs::remove_dir_all(&dir);
    }

    // ── hub#338: "the OS won't let me look" is not "there are no printers" ───────────────────
    //
    // The shell is where the two states are told apart, because it is the only layer that can ask
    // Android what it granted. Get this wrong in either direction and the till hands the user the
    // opposite instruction to the one that would fix it.

    use erplora_peripherals::discovery::LocalNetworkAccess;
    use std::collections::HashMap;
    use tauri_plugin_erplora_android::{ACCESS_LOCAL_NETWORK, POST_NOTIFICATIONS};

    fn permission_status(pairs: &[(&str, bool)]) -> HashMap<String, bool> {
        pairs.iter().map(|(k, v)| ((*k).to_string(), *v)).collect()
    }

    #[test]
    fn a_platform_that_never_answers_is_not_a_platform_that_said_no() {
        // Desktop returns an empty map — there is no such permission on Windows/macOS/Linux, and
        // Android below API 37 does not know it either. Reading that silence as a denial would
        // ground a till whose printer is right there.
        assert_eq!(
            local_network_access(&HashMap::new()),
            LocalNetworkAccess::Granted
        );
    }

    #[test]
    fn a_granted_permission_lets_the_scan_run() {
        assert_eq!(
            local_network_access(&permission_status(&[(ACCESS_LOCAL_NETWORK, true)])),
            LocalNetworkAccess::Granted
        );
    }

    #[test]
    fn a_denied_permission_names_itself_instead_of_faking_an_empty_venue() {
        // The name is what turns a dead end into an instruction: the screen can say which toggle
        // to flip rather than inviting the user to go hunting for a printer that is already on.
        assert_eq!(
            local_network_access(&permission_status(&[(ACCESS_LOCAL_NETWORK, false)])),
            LocalNetworkAccess::Denied {
                permission: ACCESS_LOCAL_NETWORK.to_string(),
            }
        );
    }

    #[test]
    fn saying_no_to_notifications_does_not_ground_printer_discovery() {
        // Two independent permissions asked in the same dialog run. Refusing the notifications one
        // must not make the till claim it cannot reach a network it can reach.
        assert_eq!(
            local_network_access(&permission_status(&[
                (POST_NOTIFICATIONS, false),
                (ACCESS_LOCAL_NETWORK, true),
            ])),
            LocalNetworkAccess::Granted
        );
        assert_eq!(
            local_network_access(&permission_status(&[(POST_NOTIFICATIONS, false)])),
            LocalNetworkAccess::Granted
        );
    }

    #[test]
    fn denying_both_still_blames_the_permission_that_actually_blocks_the_printers() {
        assert_eq!(
            local_network_access(&permission_status(&[
                (POST_NOTIFICATIONS, false),
                (ACCESS_LOCAL_NETWORK, false),
            ])),
            LocalNetworkAccess::Denied {
                permission: ACCESS_LOCAL_NETWORK.to_string(),
            }
        );
    }
}
