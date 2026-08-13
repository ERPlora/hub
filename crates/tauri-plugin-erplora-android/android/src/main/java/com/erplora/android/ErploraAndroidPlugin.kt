package com.erplora.android

import android.app.Activity
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.ContextCompat
import app.tauri.annotation.Command
import app.tauri.annotation.Permission
import app.tauri.annotation.PermissionCallback
import app.tauri.annotation.TauriPlugin
import app.tauri.plugin.Invoke
import app.tauri.plugin.JSObject
import app.tauri.plugin.Plugin
import java.io.File

/**
 * Permisos de runtime del TPV en Android.
 *
 * Existe porque **declararlos en el manifest no basta**, y su ausencia no da ningún error:
 *
 *  - sin `ACCESS_LOCAL_NETWORK` (API 37+) el barrido del puerto 9100 son 254 **timeouts**, así que
 *    el descubrimiento devuelve una lista vacía y parece que el local no tiene impresoras;
 *  - sin `POST_NOTIFICATIONS` (API 33+) la notificación no aparece, y la comanda entra en cocina
 *    sin que nadie se entere.
 *
 * Los dos fallan **en silencio**, que es lo peor que puede pasarle a un TPV: el usuario no ve un
 * error, ve un producto que «no funciona». Verificado en el emulador API 37 antes de existir este
 * plugin — `discover_printers` devolvía `[]` sin la menor queja hasta conceder el permiso con `adb`.
 *
 * Es además el vehículo por el que el shell puede llevar código Kotlin a Android: aquí irá lo que
 * Rust no alcanza (`NsdManager`, quiosco, Bluetooth SPP si algún día vuelve).
 *
 * La clase es pegamento: toda decisión vive en las funciones puras del companion, probadas en la
 * JVM sin emulador.
 */
@TauriPlugin(
    // El ALIAS ES el string del permiso, a propósito: lo que devuelve `check_permissions` se lee
    // igual que lo que dice `dumpsys`, sin una segunda nomenclatura que mantener.
    //
    // Declararlos aquí NO es decorativo: `requestPermissionForAliases` resuelve el alias contra
    // esta anotación y, si no lo encuentra, **no hace nada** — ni diálogo ni excepción, y el
    // `invoke` queda colgado para siempre. Hay un test que lo verifica contra `PermissionPolicy`.
    permissions = [
        Permission(strings = [PermissionPolicy.POST_NOTIFICATIONS], alias = PermissionPolicy.POST_NOTIFICATIONS),
        Permission(strings = [PermissionPolicy.ACCESS_LOCAL_NETWORK], alias = PermissionPolicy.ACCESS_LOCAL_NETWORK),
    ]
)
class ErploraAndroidPlugin(private val activity: Activity) : Plugin(activity) {

    /**
     * `check_permissions` — qué hay concedido AHORA, sin molestar al usuario.
     *
     * `@PermissionCallback` no es opcional ni heredado: es también el callback que cierra el
     * `request_permissions` de abajo cuando el usuario responde.
     */
    @Command
    @PermissionCallback
    override fun checkPermissions(invoke: Invoke) {
        invoke.resolve(estadoActual())
    }

    /**
     * `request_permissions` — asks for what is missing, scoped to the OPERATION that asks
     * (hub#758).
     *
     * The caller names the permissions it is about to use in `args.permissions`; only those are
     * requested. Unscoped, the plugin asked for its whole batch, so tapping «Re-scan» popped the
     * local-network dialog and then — with no visible relation to anything — the notifications
     * one: an opportunistic-looking request the user rightly denies. A call WITHOUT the argument
     * (a web older than the scope) still gets the whole batch: the two halves ship separately and
     * an old web must not break.
     *
     * Idempotent: if everything in scope is already granted it resolves at once, with no dialog.
     * That matters because the PWA calls this before every discovery.
     *
     * The request goes through [requestPermissionForAliases] and **not**
     * `activity.requestPermissions`: the user's answer is collected by Tauri's Activity, which
     * only knows how to hand it back to the plugin if the request left through its own plumbing.
     * Asked by hand, the system grants the permissions all the same but the `invoke` never
     * resolves and the PWA waits forever.
     *
     * The callback is `checkPermissions`, so the answer carries the REAL state of every
     * permission: the user may grant one and deny another. And a «no» RESOLVES, it does not
     * reject — without a printer the till has to keep selling.
     */
    @Command
    override fun requestPermissions(invoke: Invoke) {
        val scope = requestScope(PermissionPolicy.required(), requestedPermissions(invoke))
        val missing = pendingOf(scope, concedidos())
        if (missing.isEmpty()) {
            invoke.resolve(estadoActual())
            return
        }
        requestPermissionForAliases(missing.toTypedArray(), invoke, "checkPermissions")
    }

    /** The scope the caller sent, or `null` when it sent none (a web older than hub#758). */
    private fun requestedPermissions(invoke: Invoke): List<String>? {
        val requested = invoke.getArgs().optJSONArray("permissions") ?: return null
        return (0 until requested.length()).mapNotNull { requested.optString(it, null) }
    }

    /**
     * `save_to_downloads` — puts a file the shell already wrote where the USER can find it
     * (hub#499).
     *
     * The only way a business gets its own data off the tablet it keeps it on: the backup, an
     * invoice PDF, a document out of `/files`. Until this existed the shell refused on Android,
     * because the folder Tauri calls Downloads is app-scoped storage that Android 11 closed to
     * every file manager — a file written there exists and cannot be reached (hub#480, ADR-0259).
     *
     * The bytes arrive as a PATH, not as a payload: the shell has already staged them in its own
     * cache, so a multi-megabyte export crosses the JNI boundary once instead of being copied onto
     * the tablet's heap a second time.
     *
     * Both failures are answered, and they are not the same sentence. An Android too old to have
     * the collection is rejected with [DownloadPublisher.DOWNLOADS_UNREACHABLE], which the page
     * turns into *«open your business in a browser»* — the refusal the user can act on. Everything
     * else keeps its own words, because "this device cannot save files" would be the wrong advice
     * for a full disk.
     */
    @Command
    fun saveToDownloads(invoke: Invoke) {
        val args = invoke.getArgs()
        val sourcePath = args.getString("sourcePath", null)
        val name = args.getString("name", null)
        if (sourcePath.isNullOrBlank() || name.isNullOrBlank()) {
            invoke.reject("save_to_downloads needs both sourcePath and name")
            return
        }

        if (!DownloadPublisher.canPublish()) {
            invoke.reject(
                "Android ${Build.VERSION.SDK_INT} has no public Downloads collection",
                DownloadPublisher.DOWNLOADS_UNREACHABLE,
            )
            return
        }

        try {
            val location = DownloadPublisher.publish(
                activity.contentResolver,
                File(sourcePath),
                name,
            )
            invoke.resolve(JSObject().put("location", location))
        } catch (e: Exception) {
            // Resolved-with-nothing would read as a save that happened. The page has to be able to
            // say the file did NOT arrive — that is the whole lesson of hub#475.
            invoke.reject(e.message ?: e.toString(), e)
        }
    }

    private fun concedidos(): Set<String> =
        PermissionPolicy.required()
            .filter { ContextCompat.checkSelfPermission(activity, it) == PackageManager.PERMISSION_GRANTED }
            .toSet()

    private fun estadoActual(): JSObject {
        val resultado = JSObject()
        for ((permiso, concedido) in statusOf(PermissionPolicy.required(), concedidos())) {
            resultado.put(permiso, concedido)
        }
        return resultado
    }

    companion object {
        /** Los que hay que pedir: los requeridos que aún no están concedidos. */
        @JvmStatic
        fun pendingOf(required: List<String>, granted: Set<String>): List<String> =
            required.filterNot { it in granted }

        /**
         * What a request may actually ask for: the caller's scope, clamped to what THIS Android
         * requires (hub#758).
         *
         * `null` (no scope sent — a web older than the scope) keeps the old behavior and asks for
         * everything. The intersection is not decoration: the policy stays the single authority
         * on what can be asked, so a scope cannot smuggle in a permission this API level does not
         * know — requesting one can hang the dialog on some vendors.
         */
        @JvmStatic
        fun requestScope(required: List<String>, requested: List<String>?): List<String> =
            if (requested == null) required else required.filter { it in requested }

        /**
         * Estado a devolver a la PWA. Solo incluye los permisos que la versión de Android conoce:
         * de los demás no se puede afirmar nada, así que informar de ellos sería mentir.
         */
        @JvmStatic
        fun statusOf(required: List<String>, granted: Set<String>): Map<String, Boolean> =
            required.associateWith { it in granted }
    }
}
