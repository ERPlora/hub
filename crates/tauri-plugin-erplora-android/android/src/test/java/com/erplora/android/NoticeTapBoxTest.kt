package com.erplora.android

import android.content.Intent
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * Where the taps the page was not there to hear wait for it (hub#2360), across the two ways a tap
 * reaches a dead app: the intent the activity is created with, and `onNewIntent` when the system
 * killed the process but kept the task — the activity comes back with its old launcher intent and
 * the tap arrives afterwards, before any plugin is loaded.
 */
class NoticeTapBoxTest {

    private class Memory(var last: String? = null) : KeptTapMemory {
        override fun last(): String? = last
        override fun remember(key: String) {
            last = key
        }
    }

    private fun tap(id: Int, path: String) =
        NoticeLaunch.Launch(Intent.ACTION_MAIN, 0x24000000, id, "tap", """{"id":$id,"extra":{"path":"$path"}}""")

    private val launcher = NoticeLaunch.Launch(Intent.ACTION_MAIN, 0x10000000, NoticeLaunch.NO_ID, null, null)

    @Test
    fun `a tap that starts the app is handed over once`() {
        val box = NoticeTapBox(Memory())
        box.pageLoading(tap(7, "/m/appointments"))
        assertEquals(7, box.take()?.id)
        assertNull(box.take())
    }

    @Test
    fun `a tap that reaches a dead process through onNewIntent is kept for the page`() {
        val box = NoticeTapBox(Memory())
        box.newIntent(tap(7, "/m/appointments"))
        // The plugin loads after it, with the launcher intent the activity was restored with.
        box.pageLoading(launcher)
        assertEquals(7, box.take()?.id)
    }

    @Test
    fun `once the page has claimed, a tap is the notification plugin's to deliver`() {
        val box = NoticeTapBox(Memory())
        box.pageLoading(launcher)
        assertNull(box.take())
        box.newIntent(tap(8, "/m/kitchen"))
        // Kept, it would open that screen a second time at the next boot of the page.
        assertNull(box.take())
    }

    @Test
    fun `a new page is not there to hear a tap until it claims`() {
        val box = NoticeTapBox(Memory())
        box.pageLoading(launcher)
        box.take()
        box.pageLoading(launcher)
        box.newIntent(tap(9, "/m/kitchen"))
        assertEquals(9, box.take()?.id)
    }

    @Test
    fun `the last tap wins`() {
        val box = NoticeTapBox(Memory())
        box.newIntent(tap(7, "/m/appointments"))
        box.newIntent(tap(8, "/m/kitchen"))
        assertEquals(8, box.take()?.id)
    }

    @Test
    fun `a new process does not keep the tap the last one already kept`() {
        val memory = Memory()
        NoticeTapBox(memory).pageLoading(tap(7, "/m/appointments"))
        // The system killed the process; back through the icon, the task's intent is the old tap.
        val next = NoticeTapBox(memory)
        next.pageLoading(tap(7, "/m/appointments"))
        assertNull(next.take())
    }

    @Test
    fun `a tap kept through onNewIntent is remembered too`() {
        val memory = Memory()
        NoticeTapBox(memory).newIntent(tap(7, "/m/appointments"))
        val next = NoticeTapBox(memory)
        next.newIntent(tap(7, "/m/appointments"))
        assertNull(next.take())
    }
}
