package com.erplora.app

import android.os.Bundle
import android.webkit.WebView
import androidx.activity.enableEdgeToEdge
import com.erplora.android.SystemBarInsets

class MainActivity : TauriActivity() {
  override fun onCreate(savedInstanceState: Bundle?) {
    enableEdgeToEdge()
    super.onCreate(savedInstanceState)
  }

  /**
   * Reserve the status bar and the cutout before anything is drawn (hub#1719).
   *
   * `enableEdgeToEdge()` above only asks for the window to extend behind the system bars; nothing
   * was reserving the strip they sit on, so the WebView started at the physical top of the screen
   * and every page it loaded — the sign-in page the SaaS serves, the till, a module — painted over
   * the clock.
   *
   * This runs from `WryActivity.setWebView`, which is the only moment the WebView is guaranteed to
   * exist: the Rust side creates it during `Rust.onActivityCreate`, well after `onCreate` returns.
   */
  override fun onWebViewCreate(webView: WebView) {
    super.onWebViewCreate(webView)
    SystemBarInsets.applyTopSystemBarPadding(webView)
  }
}
