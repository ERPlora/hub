package com.erplora.android

import android.content.Intent

/**
 * The tap on a notice that STARTED the app (hub#2360).
 *
 * The notification plugin reports it as `actionPerformed` while it is still loading, before the page
 * has a listener, and Tauri drops an event nobody listens to. This plugin keeps the tap and the page
 * claims it once it is up (`takeNoticeTap`). Pure, so it is decided without a device: which launch
 * is such a tap, read from the extras the notification plugin puts on the intent.
 */
object NoticeLaunch {
    /** What the notification plugin writes on the intent (`TauriNotificationManager.buildIntent`). */
    const val ID_KEY = "NotificationId"
    const val USER_ACTION_KEY = "NotificationUserAction"
    const val NOTIFICATION_KEY = "LocalNotficationObject" // sic — the plugin's own spelling

    /** Our mark on an intent whose tap was already kept, so a recreated activity keeps it once. */
    const val CLAIMED_KEY = "com.erplora.noticeTapClaimed"

    /** The plugin's «no id on this intent». */
    const val NO_ID = Int.MIN_VALUE

    /** The plugin's action for a tap on the notice itself (not a button, not a swipe). */
    private const val TAP = "tap"

    /** The notice's id and the JSON the plugin stored it as, whose `extra.path` is the screen. */
    data class Tap(val id: Int, val notification: String?)

    fun tapOf(action: String?, flags: Int, id: Int, userAction: String?, notification: String?, claimed: Boolean): Tap? {
        if (action != Intent.ACTION_MAIN || id == NO_ID || userAction != TAP || claimed) return null
        // Relaunched from recents: Android hands back the ORIGINAL intent, extras and all.
        if (flags and Intent.FLAG_ACTIVITY_LAUNCHED_FROM_HISTORY != 0) return null
        return Tap(id, notification)
    }
}
