package com.oldphonedeck

import android.annotation.SuppressLint
import android.os.Bundle
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity

/** Fullscreen in-app browser for the Dell Latitude status dashboard.
 *  Reached with a two-finger swipe right on the deck; two-finger swipe left or Back returns. */
class DashboardActivity : AppCompatActivity() {

    private lateinit var web: WebView
    private lateinit var swipe: TwoFingerSwipe

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_dashboard)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        hideSystemBars()

        web = findViewById(R.id.web)
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            loadWithOverviewMode = true
            useWideViewPort = true
            builtInZoomControls = true
            displayZoomControls = false
        }
        web.webViewClient = WebViewClient()
        web.setBackgroundColor(android.graphics.Color.BLACK)

        val url = intent.getStringExtra("url") ?: run { finish(); return }
        web.loadUrl(url)

        swipe = TwoFingerSwipe(resources.displayMetrics.density,
            onRight = { }, onLeft = { closeBack() })
    }

    override fun dispatchTouchEvent(ev: MotionEvent): Boolean {
        swipe.onTouch(ev)
        return super.dispatchTouchEvent(ev)
    }

    private fun closeBack() {
        finish()
        overridePendingTransition(R.anim.slide_in_left, R.anim.slide_out_right)
    }

    @Suppress("DEPRECATION")
    override fun onBackPressed() {
        if (this::web.isInitialized && web.canGoBack()) web.goBack() else closeBack()
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) hideSystemBars()
    }

    @Suppress("DEPRECATION")
    private fun hideSystemBars() {
        window.decorView.systemUiVisibility = (
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                or View.SYSTEM_UI_FLAG_FULLSCREEN
                or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            )
    }
}
