package com.erplora.android

import android.content.Intent
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * The tap on a notice that STARTED the app (hub#2360).
 *
 * The notification plugin reports it as `actionPerformed` while it is still loading, before the page
 * has a listener, and Tauri drops an event nobody listens to — so the tap opened the app on its first
 * screen instead of the booking it announced. This plugin keeps it for the page to claim; what is
 * decided here is WHICH launches are such a tap, from the extras the notification plugin puts on it.
 */
class NoticeLaunchTest {

    private val json = """{"id":7,"title":"New booking","extra":{"path":"/m/appointments"}}"""

    @Test
    fun `a tap on a notice that starts the app is kept with its notice`() {
        assertEquals(
            NoticeLaunch.Tap(7, json),
            NoticeLaunch.tapOf(Intent.ACTION_MAIN, 0, 7, "tap", json, claimed = false),
        )
    }

    @Test
    fun `a tap whose notice was not stored still opens the app`() {
        assertEquals(NoticeLaunch.Tap(7, null), NoticeLaunch.tapOf(Intent.ACTION_MAIN, 0, 7, "tap", null, claimed = false))
    }

    @Test
    fun `an ordinary launch is no tap`() {
        assertNull(NoticeLaunch.tapOf(Intent.ACTION_MAIN, 0, NoticeLaunch.NO_ID, null, null, claimed = false))
        // No notice id, no notice to open — whatever else the intent carries.
        assertNull(NoticeLaunch.tapOf(Intent.ACTION_MAIN, 0, NoticeLaunch.NO_ID, "tap", json, claimed = false))
        assertNull(NoticeLaunch.tapOf(Intent.ACTION_VIEW, 0, 7, "tap", json, claimed = false))
    }

    @Test
    fun `a button or a swipe is not a tap on the notice`() {
        assertNull(NoticeLaunch.tapOf(Intent.ACTION_MAIN, 0, 7, "dismiss", json, claimed = false))
        assertNull(NoticeLaunch.tapOf(Intent.ACTION_MAIN, 0, 7, "reply", json, claimed = false))
        assertNull(NoticeLaunch.tapOf(Intent.ACTION_MAIN, 0, 7, null, json, claimed = false))
    }

    @Test
    fun `reopening the app from recents does not replay an old tap`() {
        // Android hands the ORIGINAL intent back when the app is relaunched from the recents list,
        // extras and all: without this the booking of this morning would open again every time.
        assertNull(
            NoticeLaunch.tapOf(Intent.ACTION_MAIN, Intent.FLAG_ACTIVITY_LAUNCHED_FROM_HISTORY, 7, "tap", json, claimed = false),
        )
    }

    @Test
    fun `a tap already kept is not kept again when the activity is recreated`() {
        assertNull(NoticeLaunch.tapOf(Intent.ACTION_MAIN, 0, 7, "tap", json, claimed = true))
    }
}
