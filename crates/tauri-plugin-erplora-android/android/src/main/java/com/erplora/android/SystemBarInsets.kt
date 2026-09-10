package com.erplora.android

import android.view.View
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.updatePadding

/**
 * Keeps the app from painting over the system clock (hub#1719).
 *
 * The activity lays itself out edge-to-edge, and on `targetSdk = 36` that is not a choice: since
 * Android 15 the framework puts every window behind the system bars whether the app opts in or
 * not. Edge-to-edge is only half a contract, though — the other half is reserving the strip the
 * bars occupy — and until this file there was no second half at all. The WebView started at the
 * physical top of the screen, so every page loaded inside it painted over the status bar. QA hit
 * it twice on 2026-09-09 (emulator `Pixel_10_Pro` / Android 16, APK 1.1.21): the back arrow of the
 * sign-in page sat on top of the clock, and the search layer of the till blacked the whole bar out.
 *
 * It is reserved on the WINDOW, not in a page's stylesheet, and that is the point: the app hosts
 * pages served by the SaaS, by the hub and by any installed module, so a per-template fix would
 * have to be repeated in every one of them and would still miss the next. `env(safe-area-inset-*)`
 * is no substitute either — in an Android WebView it reports the display cutout, not the status
 * bar, so on a phone without a notch it is flat zero however carefully the page uses it.
 */
object SystemBarInsets {

    /**
     * How far down the top of the screen is unusable, given both insets that can occupy it.
     *
     * The status bar is the obvious one, but it can be hidden (immersive mode, some launchers) and
     * then reports zero, while a display cutout is carved out of the panel and never goes away.
     * Reserving only one of them leaves content painting under the other, so the window takes
     * whichever reaches further down.
     */
    fun topInset(systemBarsTop: Int, displayCutoutTop: Int): Int =
        maxOf(systemBarsTop, displayCutoutTop).coerceAtLeast(0)

    /**
     * Pads [view] so its content starts below the status bar and the cutout.
     *
     * The insets are returned untouched rather than consumed: the page inside still needs the
     * bottom and IME ones for its own `env(safe-area-inset-*)` rules, and swallowing them here
     * would trade the overlap at the top for a new one at the bottom.
     */
    fun applyTopSystemBarPadding(view: View) {
        ViewCompat.setOnApplyWindowInsetsListener(view) { target, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            val cutout = insets.getInsets(WindowInsetsCompat.Type.displayCutout())
            target.updatePadding(top = topInset(bars.top, cutout.top))
            insets
        }
        // The view may already be attached with its insets dispatched, in which case the listener
        // above would not run again until the next layout change — a first frame under the clock.
        ViewCompat.requestApplyInsets(view)
    }
}
