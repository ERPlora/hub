package com.erplora.app

import android.os.Bundle
import android.view.View
import androidx.activity.enableEdgeToEdge
import com.erplora.android.SystemBarInsets

class MainActivity : TauriActivity() {
  /**
   * Reserve the status bar and the cutout before anything is drawn (hub#1719).
   *
   * `enableEdgeToEdge()` only asks for the window to extend behind the system bars; nothing was
   * reserving the strip they sit on, so the window's content started at the physical top of the
   * screen and every page loaded inside it — the sign-in page the SaaS serves, the till, a module
   * — painted over the clock.
   *
   * The padding goes on the activity's content view, which is the WebView's container: it is
   * already there at this point (the WebView is not — the Rust side creates it later, during
   * `Rust.onActivityCreate`), it survives the container being handed a different child, and its
   * transparent background lets the reserved strip show the `DayNight` window background instead
   * of the WebView's opaque white.
   */
  override fun onCreate(savedInstanceState: Bundle?) {
    enableEdgeToEdge()
    super.onCreate(savedInstanceState)
    SystemBarInsets.applyTopSystemBarPadding(findViewById<View>(android.R.id.content))
  }
}
