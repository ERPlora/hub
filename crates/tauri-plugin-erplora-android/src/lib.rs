//! Permisos de RUNTIME de Android para el shell de ERPlora.
//!
//! Declarar un permiso en el manifest no basta, y los dos que necesita el TPV fallan **en
//! silencio**:
//!
//! - sin `ACCESS_LOCAL_NETWORK` (API 37+) el barrido del puerto 9100 son 254 **timeouts**, así que
//!   el descubrimiento devuelve `[]` y parece que el local no tiene impresoras;
//! - sin `POST_NOTIFICATIONS` (API 33+) la notificación no aparece, y la comanda entra en cocina
//!   sin que nadie se entere.
//!
//! Verificado en el emulador API 37 antes de existir este plugin: `erplora_discover_printers`
//! devolvía una lista vacía sin la menor queja hasta conceder el permiso a mano con `adb`.
//!
//! En escritorio no hay nada que pedir: los comandos existen igual y responden «concedido», para
//! que la PWA pueda llamarlos sin ramificar por plataforma.

use serde::{Deserialize, Serialize};
use tauri::{
    plugin::{Builder, TauriPlugin},
    Manager, Runtime,
};

/// Estado de un permiso tal y como lo ve la PWA: `{ "android.permission.X": true }`.
pub type PermissionStatus = std::collections::HashMap<String, bool>;

/// Local network access (API 37+). Without it the printer sweep is 254 silent timeouts.
///
/// Mirror of `PermissionPolicy.ACCESS_LOCAL_NETWORK` on the Kotlin side. The key of the map above
/// **is** the permission string, so Rust needs the same literal to read the answer — and a test
/// below checks the two never drift apart.
pub const ACCESS_LOCAL_NETWORK: &str = "android.permission.ACCESS_LOCAL_NETWORK";

/// System notifications (API 33+). Mirror of `PermissionPolicy.POST_NOTIFICATIONS`.
pub const POST_NOTIFICATIONS: &str = "android.permission.POST_NOTIFICATIONS";

/// The code an Android with no public Downloads collection is refused under (hub#499).
///
/// Mirror of `DownloadPublisher.DOWNLOADS_UNREACHABLE`, and the same word `apps/tauri` and
/// `save-download.ts` already read: it is the ONE refusal the user can act on, so it must survive
/// the trip from Kotlin to the page intact. A test below checks the two sides never drift apart.
pub const DOWNLOADS_UNREACHABLE: &str = "downloads_unreachable";

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("{0}")]
    PluginInvoke(String),
    /// This Android is older than the public Downloads collection (API 29), so there is nowhere to
    /// put a file that the user could then open. The shell turns this into its own sentence.
    #[error("downloads_unreachable")]
    DownloadsUnreachable,
}

impl Serialize for Error {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&self.to_string())
    }
}

#[derive(Debug, Default, Serialize, Deserialize)]
pub struct Empty {}

/// The scope of a `request_permissions` call (hub#758): the permissions the OPERATION that asks
/// is about to use, or `None` when the caller sent none (a web older than the scope), which keeps
/// the old ask-for-everything behavior so the two separately-shipped halves cannot break each
/// other.
#[derive(Debug, Serialize)]
struct RequestPermissionsArgs {
    permissions: Option<Vec<String>>,
}

/// What the shell asks the native side to publish, and where it staged the bytes (hub#499).
///
/// A **path** and not the bytes: the shell has already written the file into its own cache, so an
/// export crosses the JNI boundary once instead of being copied onto a tablet's heap a second time.
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct PublishArgs {
    source_path: String,
    name: String,
}

/// Where a published file ended up, in words to put in front of the user.
///
/// Not a path: `MediaStore` answers with `content://media/external/downloads/1234`, which says
/// nothing to anybody. What comes back is the folder and the name the file actually got — the only
/// sign it exists at all inside an app with no download shelf.
#[derive(Debug, Deserialize)]
pub struct PublishedDownload {
    pub location: String,
}

/// Reads the rejection Kotlin sent back and decides which of the two sentences it is.
///
/// Tauri renders a plugin rejection as `[code] - message` and hands Rust a plain string, so the
/// code has to be recognised out of the text. Getting this wrong is not cosmetic: an Android 9
/// till would be told "could not save" instead of "open your business in a browser", and a full
/// disk would be told to go and use a browser, which fixes nothing.
fn classify_publish_error(message: &str) -> Error {
    if message.contains(DOWNLOADS_UNREACHABLE) {
        Error::DownloadsUnreachable
    } else {
        Error::PluginInvoke(message.to_string())
    }
}

#[cfg(target_os = "android")]
const PLUGIN_IDENTIFIER: &str = "com.erplora.android";

/// Estado del plugin: en Android guarda el handle del módulo Kotlin; en escritorio, nada.
#[cfg(target_os = "android")]
pub struct ErploraAndroid<R: Runtime>(tauri::plugin::PluginHandle<R>);

#[cfg(not(target_os = "android"))]
pub struct ErploraAndroid<R: Runtime>(std::marker::PhantomData<fn() -> R>);

impl<R: Runtime> ErploraAndroid<R> {
    /// Permisos concedidos ahora mismo. En escritorio, siempre vacío: no hay nada que conceder.
    pub fn check_permissions(&self) -> Result<PermissionStatus, Error> {
        #[cfg(target_os = "android")]
        {
            return self
                .0
                .run_mobile_plugin("checkPermissions", Empty {})
                .map_err(|e| Error::PluginInvoke(e.to_string()));
        }
        #[cfg(not(target_os = "android"))]
        Ok(PermissionStatus::new())
    }

    /// Asks for what is missing, scoped to what the calling operation is about to use (hub#758).
    /// `None` = no scope sent (an older web): the whole batch, as before. Idempotent: if
    /// everything in scope is granted, no dialog.
    pub fn request_permissions(
        &self,
        permissions: Option<Vec<String>>,
    ) -> Result<PermissionStatus, Error> {
        #[cfg(target_os = "android")]
        {
            return self
                .0
                .run_mobile_plugin("requestPermissions", RequestPermissionsArgs { permissions })
                .map_err(|e| Error::PluginInvoke(e.to_string()));
        }
        #[cfg(not(target_os = "android"))]
        {
            let _ = permissions;
            Ok(PermissionStatus::new())
        }
    }

    /// Publishes the file at `source_path` into Android's **public** Downloads collection under
    /// `name`, and answers with the place to show the user (hub#499).
    ///
    /// This is how a business gets its own data off the tablet it keeps it on. Everywhere else the
    /// shell just writes to the Downloads folder; on Android there is no such folder to write to —
    /// what `download_dir()` resolves is app-scoped storage that Android 11 closed to every file
    /// manager, so the file would exist and be unreachable (hub#480, ADR-0259). `MediaStore` is the
    /// way in, and it needs Kotlin.
    ///
    /// ⚠️ **Blocks.** The call is dispatched onto Android's main looper and waits for the answer,
    /// so calling it FROM the main thread deadlocks. The shell's `save_download` is
    /// `#[tauri::command(async)]` for exactly this reason.
    pub fn save_to_downloads(
        &self,
        source_path: &std::path::Path,
        name: &str,
    ) -> Result<PublishedDownload, Error> {
        #[cfg(target_os = "android")]
        {
            return self
                .0
                .run_mobile_plugin(
                    "saveToDownloads",
                    PublishArgs {
                        source_path: source_path.display().to_string(),
                        name: name.to_string(),
                    },
                )
                .map_err(|e| classify_publish_error(&e.to_string()));
        }
        #[cfg(not(target_os = "android"))]
        {
            // Unreachable by construction: `save_target` only routes here on Android. Said out loud
            // anyway, because a desktop that somehow got here has NOT saved anything.
            let _ = (source_path, name);
            Err(Error::PluginInvoke(
                "save_to_downloads is Android only".into(),
            ))
        }
    }
}

pub trait ErploraAndroidExt<R: Runtime> {
    fn erplora_android(&self) -> &ErploraAndroid<R>;
}

impl<R: Runtime, T: Manager<R>> ErploraAndroidExt<R> for T {
    fn erplora_android(&self) -> &ErploraAndroid<R> {
        self.state::<ErploraAndroid<R>>().inner()
    }
}

#[tauri::command]
async fn check_permissions<R: Runtime>(app: tauri::AppHandle<R>) -> Result<PermissionStatus, Error> {
    app.erplora_android().check_permissions()
}

#[tauri::command]
async fn request_permissions<R: Runtime>(
    app: tauri::AppHandle<R>,
    permissions: Option<Vec<String>>,
) -> Result<PermissionStatus, Error> {
    app.erplora_android().request_permissions(permissions)
}

pub fn init<R: Runtime>() -> TauriPlugin<R> {
    Builder::new("erplora-android")
        .invoke_handler(tauri::generate_handler![check_permissions, request_permissions])
        .setup(|app, _api| {
            #[cfg(target_os = "android")]
            let handle = _api.register_android_plugin(PLUGIN_IDENTIFIER, "ErploraAndroidPlugin")?;
            #[cfg(target_os = "android")]
            app.manage(ErploraAndroid(handle));

            #[cfg(not(target_os = "android"))]
            app.manage(ErploraAndroid::<R>(std::marker::PhantomData));

            Ok(())
        })
        .build()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn el_estado_serializa_como_un_mapa_permiso_a_booleano() {
        // Es el contrato que consume la PWA: `{ "android.permission.X": true }`.
        let mut estado = PermissionStatus::new();
        estado.insert("android.permission.POST_NOTIFICATIONS".into(), true);
        let json = serde_json::to_string(&estado).unwrap();
        assert!(json.contains("\"android.permission.POST_NOTIFICATIONS\":true"));
    }

    /// The Kotlin policy is the only place that can actually ASK for these permissions, and the
    /// map it returns is keyed by the raw string. If the two sides ever spelled one differently,
    /// Rust would read `None` for a permission Android had denied and the till would go back to
    /// reporting zero printers with a straight face (hub#338).
    const PERMISSION_POLICY_KT: &str =
        include_str!("../android/src/main/java/com/erplora/android/PermissionPolicy.kt");

    #[test]
    fn rust_and_kotlin_spell_the_permissions_the_same_way() {
        for permission in [ACCESS_LOCAL_NETWORK, POST_NOTIFICATIONS] {
            assert!(
                PERMISSION_POLICY_KT.contains(permission),
                "{permission} is not in PermissionPolicy.kt — the status map would never mention it"
            );
        }
    }

    /// Every `android.permission.*` the Kotlin policy names, read out of its source.
    ///
    /// Read rather than listed so the guards below cannot drift from the one place that decides
    /// what the shell ASKS for: a permission added there and forgotten everywhere else is the bug
    /// this file is about.
    fn permissions_the_plugin_can_ask_for() -> Vec<&'static str> {
        PERMISSION_POLICY_KT
            .match_indices("\"android.permission.")
            .filter_map(|(at, _)| PERMISSION_POLICY_KT[at + 1..].split('"').next())
            .collect()
    }

    /// Everything outside XML comments. Commenting a tag out is the easiest way to "temporarily"
    /// drop a permission, and the edit nobody remembers to undo.
    fn without_comments(xml: &str) -> String {
        let mut out = String::new();
        let mut rest = xml;
        while let Some(start) = rest.find("<!--") {
            out.push_str(&rest[..start]);
            let Some(end) = rest[start..].find("-->") else { return out };
            rest = &rest[start + end + "-->".len()..];
        }
        out.push_str(rest);
        out
    }

    /// Permissions actually DECLARED by a manifest, read out of its live `<uses-permission>` tags.
    ///
    /// Not a text search: manifests here carry long comments naming the permissions and explaining
    /// why they are there, so `contains()` would keep passing on the prose after the tag itself was
    /// deleted — a guard that goes green on the wreckage is worse than no guard.
    fn declared_permissions(manifest: &str) -> Vec<String> {
        without_comments(manifest)
            .split("<uses-permission")
            .skip(1)
            .filter_map(|tag| {
                tag.split("android:name=\"")
                    .nth(1)
                    .and_then(|value| value.split('"').next())
                    .map(str::to_owned)
            })
            .collect()
    }

    #[test]
    fn a_commented_out_permission_does_not_count_as_declared() {
        // How a permission usually disappears: someone comments it out "for a minute". The prose
        // around it still names it, so a text search would call it declared and let the guard
        // below wave the regression through.
        let manifest = r#"<manifest>
            <uses-permission android:name="android.permission.INTERNET" />
            <!-- <uses-permission android:name="android.permission.ACCESS_LOCAL_NETWORK" /> -->
        </manifest>"#;

        assert_eq!(declared_permissions(manifest), ["android.permission.INTERNET"]);
    }

    /// Asking for a permission the merged manifest never declared is not a dialog the user can
    /// say yes to: Android answers DENIED at once, forever, and shows nothing. The till would
    /// then tell the user to grant local network access in the system settings (hub#338) and send
    /// them looking for a toggle that does not exist.
    ///
    /// The plugin declares them in its OWN Android library manifest, which the manifest merger
    /// folds into the app at build time. That is what makes the declaration survive
    /// `cargo tauri android init` — the generator rewrites `apps/tauri/src-tauri/gen/android`, it
    /// does not reach into `crates/` (hub#337).
    #[test]
    fn the_plugin_declares_every_permission_it_can_ask_for() {
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/android/src/main/AndroidManifest.xml");
        let manifest = std::fs::read_to_string(path).unwrap_or_else(|e| {
            panic!(
                "{path}: {e}\n\
                 The plugin ships no Android manifest, so these permissions exist only in the \
                 GENERATED gen/android project. Lose that file and `cargo tauri android init` \
                 writes Tauri's template back — INTERNET and nothing else — and the till stops \
                 finding printers with a perfectly green build."
            )
        });

        let declared = declared_permissions(&manifest);
        let asked_for = permissions_the_plugin_can_ask_for();
        assert!(!asked_for.is_empty(), "PermissionPolicy.kt names no permission at all");
        for permission in asked_for {
            assert!(
                declared.iter().any(|d| d == permission),
                "PermissionPolicy asks for {permission}, but no manifest of this plugin declares \
                 it: Android would answer that request DENIED without ever showing a dialog.\n\
                 Declared right now: {declared:?}"
            );
        }
    }

    /// The scope of a permission request has to reach Kotlin under the key Kotlin reads
    /// (hub#758). If either side renamed it, the argument would silently vanish and the plugin
    /// would fall back to requesting its whole batch — the exact out-of-context notifications
    /// dialog this contract exists to end, with no error anywhere.
    #[test]
    fn the_permission_scope_travels_under_the_key_kotlin_reads() {
        let args = RequestPermissionsArgs {
            permissions: Some(vec![ACCESS_LOCAL_NETWORK.to_string()]),
        };
        let json = serde_json::to_value(&args).expect("serializable");
        assert_eq!(json["permissions"][0], ACCESS_LOCAL_NETWORK);

        const PLUGIN_KT: &str =
            include_str!("../android/src/main/java/com/erplora/android/ErploraAndroidPlugin.kt");
        assert!(
            PLUGIN_KT.contains("optJSONArray(\"permissions\")"),
            "ErploraAndroidPlugin.kt no longer reads the \"permissions\" scope: every request \
             would go back to asking for the whole batch (hub#758)"
        );
    }

    /// An absent scope must serialize as an ABSENT key, not as `null`: Kotlin's `optJSONArray`
    /// treats both as "no scope", but the wire contract is "an old web sends nothing", and
    /// pinning it keeps the fallback path honest.
    #[test]
    fn no_scope_still_serializes_and_means_the_whole_batch() {
        let args = RequestPermissionsArgs { permissions: None };
        let json = serde_json::to_value(&args).expect("serializable");
        assert!(json["permissions"].is_null());
    }

    #[test]
    fn el_error_llega_al_frontend_como_texto_plano() {
        // Mismo patrón que el resto del shell: la promesa se rechaza con un mensaje legible.
        let e = Error::PluginInvoke("sin actividad".into());
        assert_eq!(serde_json::to_string(&e).unwrap(), "\"sin actividad\"");
    }

    // ── Publishing a file into the public Downloads collection (hub#499) ─────────────────────────

    const DOWNLOAD_PUBLISHER_KT: &str =
        include_str!("../android/src/main/java/com/erplora/android/DownloadPublisher.kt");

    /// The one refusal the user can act on has to survive the trip back from Kotlin.
    ///
    /// Kotlin rejects with a **code**, Tauri renders the rejection as `[code] - message`, and by
    /// the time it reaches Rust it is a plain string. If that string is not recognised the shell
    /// reports a generic failure and the page prints *«could not save»* instead of *«open your
    /// business in a browser»* — the sentence that tells the user what to do instead.
    #[test]
    fn an_android_too_old_to_publish_comes_back_as_downloads_unreachable() {
        let rejected = format!("[{DOWNLOADS_UNREACHABLE}] - Android 9 has no Downloads collection");
        assert!(matches!(
            classify_publish_error(&rejected),
            Error::DownloadsUnreachable
        ));
    }

    #[test]
    fn every_other_failure_keeps_its_own_words() {
        // A full disk, a revoked provider, a Kotlin exception: none of them is "this device cannot
        // save files", and dressing them up as that would send the user to a browser for a problem
        // a browser does not fix.
        for message in [
            "java.io.IOException: No space left on device",
            "insert into MediaStore returned no row",
            "",
        ] {
            assert!(
                matches!(classify_publish_error(message), Error::PluginInvoke(_)),
                "{message:?} is not the phone refusal"
            );
        }
    }

    #[test]
    fn the_refusal_reaches_the_page_under_the_name_the_shell_reads() {
        // `apps/tauri` maps this variant onto `ShellError::DownloadsUnreachable`, which serializes
        // to the same word the web checks for (`save-download.ts`). One spelling, end to end.
        assert_eq!(
            serde_json::to_string(&Error::DownloadsUnreachable).unwrap(),
            "\"downloads_unreachable\""
        );
    }

    #[test]
    fn rust_and_kotlin_spell_the_refusal_the_same_way() {
        // Same trap as the permission strings above: the code is a bare literal on both sides, so
        // a typo in either one is invisible until a real Android 9 till says the wrong sentence.
        assert!(
            DOWNLOAD_PUBLISHER_KT.contains(DOWNLOADS_UNREACHABLE),
            "DownloadPublisher.kt never rejects with {DOWNLOADS_UNREACHABLE}, so Rust would \
             classify an old Android as a generic failure"
        );
    }

    /// Kotlin source with its comments taken out.
    ///
    /// The guard below went red on its own prose the first time it ran: `DownloadPublisher` EXPLAINS
    /// why it does not use `WRITE_EXTERNAL_STORAGE`, and a plain `contains` cannot tell an
    /// explanation from a call. Same lesson as [`without_comments`] one screen up — a guard has to
    /// read the code, or it reads the documentation about the code.
    fn without_kotlin_comments(source: &str) -> String {
        let mut out = String::new();
        let mut rest = source;
        loop {
            let block = rest.find("/*");
            let line = rest.find("//");
            let (start, close, skip) = match (block, line) {
                (Some(b), Some(l)) if b < l => (b, "*/", 2),
                (Some(b), None) => (b, "*/", 2),
                (_, Some(l)) => (l, "\n", 0),
                (None, None) => break,
            };
            out.push_str(&rest[..start]);
            let Some(end) = rest[start..].find(close) else {
                break;
            };
            rest = &rest[start + end + skip..];
        }
        out.push_str(rest);
        out
    }

    #[test]
    fn publishing_needs_no_permission_the_plugin_would_have_to_ask_for() {
        // Why `MediaStore` and not `getExternalStoragePublicDirectory`: inserting into the public
        // Downloads collection needs NO permission from API 29 on. If this ever grows a
        // `WRITE_EXTERNAL_STORAGE`, it also grows a runtime dialog the save command has to wait
        // for — a different design, not a line to slip in.
        let code = without_kotlin_comments(DOWNLOAD_PUBLISHER_KT);
        assert!(
            !code.contains("WRITE_EXTERNAL_STORAGE"),
            "publishing now wants a runtime permission; the save path has to ask for it first"
        );
    }

    #[test]
    fn the_comment_stripper_keeps_the_code_and_drops_the_prose() {
        let source = "// asks for WRITE_EXTERNAL_STORAGE one day\nval a = 1\n/* WRITE_EXTERNAL_STORAGE */\nval b = 2";
        let code = without_kotlin_comments(source);
        assert!(!code.contains("WRITE_EXTERNAL_STORAGE"), "{code:?}");
        assert!(
            code.contains("val a = 1") && code.contains("val b = 2"),
            "{code:?}"
        );
    }
}
