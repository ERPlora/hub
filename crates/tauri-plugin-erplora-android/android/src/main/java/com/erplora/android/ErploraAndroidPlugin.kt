package com.erplora.android

import android.app.Activity
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import app.tauri.annotation.Command
import app.tauri.annotation.Permission
import app.tauri.annotation.PermissionCallback
import app.tauri.annotation.TauriPlugin
import app.tauri.plugin.Invoke
import app.tauri.plugin.JSObject
import app.tauri.plugin.Plugin

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
     * `request_permissions` — pide lo que falte.
     *
     * Idempotente: si ya está todo concedido resuelve al momento y sin diálogo. Importa porque la
     * PWA lo llama antes de cada descubrimiento, y un diálogo por escaneo sería insufrible.
     *
     * La petición va por [requestPermissionForAliases] y **no** por `activity.requestPermissions`:
     * la respuesta del usuario la recoge la Activity de Tauri, que solo sabe devolvérsela al plugin
     * si la petición salió de su propia fontanería. Pidiéndolo a mano el sistema concede los
     * permisos igual, pero el `invoke` no se resuelve nunca y la PWA se queda esperando.
     *
     * El callback es `checkPermissions`, así que se responde con el estado REAL de cada permiso:
     * el usuario puede conceder uno y denegar otro. Y un «no» se RESUELVE, no se rechaza — sin
     * impresora el TPV tiene que seguir cobrando.
     */
    @Command
    override fun requestPermissions(invoke: Invoke) {
        val faltan = pendingOf(PermissionPolicy.required(), concedidos())
        if (faltan.isEmpty()) {
            invoke.resolve(estadoActual())
            return
        }
        requestPermissionForAliases(faltan.toTypedArray(), invoke, "checkPermissions")
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
         * Estado a devolver a la PWA. Solo incluye los permisos que la versión de Android conoce:
         * de los demás no se puede afirmar nada, así que informar de ellos sería mentir.
         */
        @JvmStatic
        fun statusOf(required: List<String>, granted: Set<String>): Map<String, Boolean> =
            required.associateWith { it in granted }
    }
}
