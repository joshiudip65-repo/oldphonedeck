package com.oldphonedeck

import android.content.Context
import android.content.Intent
import android.content.res.ColorStateList
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.net.wifi.WifiManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.HorizontalScrollView
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.oldphonedeck.databinding.ActivityMainBinding
import com.oldphonedeck.databinding.ItemBatteryBinding
import com.oldphonedeck.databinding.ItemButtonBinding
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.Executors
import kotlin.math.abs

class MainActivity : AppCompatActivity() {

    private lateinit var b: ActivityMainBinding
    private val io = Executors.newSingleThreadExecutor()
    private val ui = Handler(Looper.getMainLooper())
    private val base = "http://localhost:8790"

    private val buttons = ArrayList<JSONObject>()
    private val cells = HashMap<String, ItemButtonBinding>()
    private val iconCache = HashMap<String, Bitmap?>()
    private val iconLoading = HashSet<String>()
    private var gridBuilt = false
    private var touchbarSig = ""
    private var emojiMode = false
    private var lastTouchbar: JSONArray? = null
    private val emojis = listOf(
        "😀", "😁", "😂", "🤣", "😊", "😍", "😎", "😉", "🙂", "😇", "🥰", "😘",
        "😢", "😭", "😡", "🤔", "😴", "🤩", "🥳", "😅", "😜", "🙃", "😳", "🤯",
        "👍", "👎", "👏", "🙏", "🙌", "💪", "👀", "🤝", "👋", "🤙", "✌️",
        "🔥", "✨", "🎉", "❤️", "🧡", "💛", "💚", "💙", "💜", "💯", "✅", "❌",
        "⭐", "⚡", "☕", "🍕", "🎵", "🚀", "💩", "🤷", "🫶")
    private var dashboardUrl: String? = null
    private lateinit var swipe: TwoFingerSwipe

    private val timeFmt = SimpleDateFormat("h:mm", Locale.getDefault())
    private val dateFmt = SimpleDateFormat("EEEE, d MMMM", Locale.getDefault())
    private val sydFmt = SimpleDateFormat("h:mm a", Locale.getDefault()).apply {
        timeZone = java.util.TimeZone.getTimeZone("Australia/Sydney")
    }

    private var activeAppId: String? = null

    // Burn-in guard: this panel already has a dead line, so be gentle on the OLED.
    private var lastInteract = System.currentTimeMillis()
    private var dimmed = false
    private var shiftIdx = 0

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityMainBinding.inflate(layoutInflater)
        setContentView(b.root)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        hideSystemBars()

        b.btnPrev.setOnClickListener { media("prev", it) }
        b.btnPlay.setOnClickListener { media("play", it) }
        b.btnNext.setOnClickListener { media("next", it) }
        b.llPylon.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            action("pylon")
        }

        swipe = TwoFingerSwipe(resources.displayMetrics.density,
            onRight = { openDashboard() }, onLeft = { openApps() })

        startClock()
        poll()
        ui.postDelayed(burnGuard, 30_000L)
    }

    override fun dispatchTouchEvent(ev: MotionEvent): Boolean {
        lastInteract = System.currentTimeMillis()
        if (dimmed) setDim(false)
        swipe.onTouch(ev)
        return super.dispatchTouchEvent(ev)
    }

    // ---- Burn-in protection: dim after idle, gently shift pixels ----

    private val burnGuard = object : Runnable {
        override fun run() {
            val idle = System.currentTimeMillis() - lastInteract
            if (idle >= 120_000L && !dimmed) setDim(true)
            shiftIdx = (shiftIdx + 1) % 4
            val s = dp(3)
            val (sx, sy) = when (shiftIdx) {
                1 -> s to s; 3 -> -s to -s; else -> 0 to 0
            }
            b.root.translationX = sx.toFloat()
            b.root.translationY = sy.toFloat()
            ui.postDelayed(this, 30_000L)
        }
    }

    private fun setDim(on: Boolean) {
        dimmed = on
        val lp = window.attributes
        lp.screenBrightness =
            if (on) 0.1f else WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE
        window.attributes = lp
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

    private fun startClock() {
        val r = object : Runnable {
            override fun run() {
                val now = Date()
                b.tvTime.text = timeFmt.format(now)
                b.tvDate.text = dateFmt.format(now).uppercase(Locale.getDefault())
                b.tvSydney.text = "SYDNEY " + sydFmt.format(now).uppercase(Locale.getDefault())
                ui.postDelayed(this, 1000)
            }
        }
        ui.post(r)
    }

    private fun poll() {
        io.execute {
            val json = httpGet("$base/api/stats")
            ui.post {
                if (json != null) { b.offline.visibility = View.GONE; render(json) }
                else b.offline.visibility = View.VISIBLE
            }
        }
        ui.postDelayed({ poll() }, 2000)
    }

    private fun render(o: JSONObject) {
        o.optJSONArray("buttons")?.let { if (!gridBuilt) buildGrid(it) }
        b.tvHost.text = o.optString("mac_name", "Mac")
        dashboardUrl = o.optString("dashboard_url").ifEmpty { null }
        updateConn(o.optString("transport"))
        o.optJSONArray("touchbar")?.let { renderTouchbar(it) }
        renderBatteries(o)
        renderNetwork(o.optJSONObject("net"))
        renderPylon(o.optJSONObject("pylon"))
        renderRam(o.optJSONObject("ram"))
        renderPlayer(o.optJSONObject("now_playing"))
        highlightActiveApp(o.optString("frontmost"))
    }

    // ---- Connection status (USB / Wi-Fi with signal) ----

    private fun updateConn(transport: String) {
        when (transport) {
            "usb" -> {
                b.connIcon.setImageResource(R.drawable.ic_conn_usb)
                b.connIcon.imageTintList = ColorStateList.valueOf(Color.parseColor("#30D158"))
                b.connIcon.visibility = View.VISIBLE
                b.tvConn.text = "USB"
                b.tvConn.setTextColor(Color.parseColor("#8A8A8E"))
            }
            "wifi" -> {
                val lvl = wifiLevel()  // 0..4, or -1 unknown
                val color = when {
                    lvl < 0 -> "#30D158"
                    lvl >= 3 -> "#30D158"
                    lvl == 2 -> "#FFD60A"
                    else -> "#FF9F0A"
                }
                b.connIcon.setImageResource(R.drawable.ic_conn_wifi)
                b.connIcon.imageTintList = ColorStateList.valueOf(Color.parseColor(color))
                b.connIcon.visibility = View.VISIBLE
                b.tvConn.text = "Wi-Fi"
                b.tvConn.setTextColor(Color.parseColor("#8A8A8E"))
            }
            else -> {
                b.connIcon.visibility = View.GONE
                b.tvConn.text = ""
            }
        }
    }

    @Suppress("DEPRECATION")
    private fun wifiLevel(): Int = try {
        val wm = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        WifiManager.calculateSignalLevel(wm.connectionInfo.rssi, 5)
    } catch (e: Exception) {
        -1
    }

    // ---- Button grid (fixed, non-scrolling, weighted) ----

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun buildGrid(arr: JSONArray) {
        gridBuilt = true
        buttons.clear()
        for (i in 0 until arr.length()) buttons.add(arr.getJSONObject(i))
        // Keep the grid to 2 roomy rows: widen columns as tiles grow (min 4).
        val cols = maxOf(4, (buttons.size + 1) / 2)
        val rows = (buttons.size + cols - 1) / cols
        val m = dp(5)
        b.grid.removeAllViews()
        for (r in 0 until rows) {
            val row = LinearLayout(this)
            row.orientation = LinearLayout.HORIZONTAL
            row.layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f)
            for (c in 0 until cols) {
                val idx = r * cols + c
                if (idx < buttons.size) {
                    val btn = buttons[idx]
                    val id = btn.optString("id")
                    val cell = ItemButtonBinding.inflate(layoutInflater, row, false)
                    val lp = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f)
                    lp.setMargins(m, m, m, m)
                    cell.root.layoutParams = lp
                    cell.label.text = btn.optString("label")
                    cell.icon.text = btn.optString("icon", "▣")
                    cell.root.setOnClickListener {
                        it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                        action(id)
                    }
                    cells[id] = cell
                    row.addView(cell.root)
                    val cached = iconCache[id]
                    if (cached != null) setCellIcon(cell, cached) else loadIcon(id)
                } else {
                    val spacer = View(this)
                    spacer.layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f)
                    row.addView(spacer)
                }
            }
            b.grid.addView(row)
        }
    }

    private fun setCellIcon(cell: ItemButtonBinding, bmp: Bitmap) {
        cell.iconImg.setImageBitmap(bmp)
        cell.iconImg.visibility = View.VISIBLE
        cell.icon.visibility = View.GONE
    }

    private fun loadIcon(id: String) {
        if (!iconLoading.add(id)) return
        io.execute {
            var bmp: Bitmap? = null
            var c: HttpURLConnection? = null
            try {
                c = (URL("$base/api/icon?id=$id").openConnection() as HttpURLConnection).apply {
                    connectTimeout = 2000; readTimeout = 5000
                }
                if (c.responseCode == 200) bmp = BitmapFactory.decodeStream(c.inputStream)
            } catch (e: Exception) { /* emoji fallback */ } finally { c?.disconnect() }
            val result = bmp
            ui.post {
                iconCache[id] = result
                iconLoading.remove(id)
                if (result != null) cells[id]?.let { setCellIcon(it, result) }
            }
        }
    }

    // ---- Touch Bar (context-aware, re-renders when the set changes) ----

    private fun renderTouchbar(arr: JSONArray) {
        lastTouchbar = arr
        if (emojiMode) return  // emoji picker owns the strip until dismissed
        val sig = StringBuilder()
        for (i in 0 until arr.length()) {
            val it = arr.getJSONObject(i)
            sig.append(if (it.optBoolean("sep")) "|" else it.optString("id") + ":" + it.optString("glyph")).append(",")
        }
        if (sig.toString() == touchbarSig) return
        touchbarSig = sig.toString()
        b.touchbar.removeAllViews()
        for (i in 0 until arr.length()) {
            val it = arr.getJSONObject(i)
            if (it.optBoolean("sep")) {
                val div = View(this)
                div.layoutParams = LinearLayout.LayoutParams(dp(1), dp(22)).also { lp ->
                    lp.marginStart = dp(5); lp.marginEnd = dp(5)
                }
                div.setBackgroundColor(Color.parseColor("#2E2E30"))
                b.touchbar.addView(div)
                continue
            }
            val glyph = it.optString("glyph")
            val resId = if (glyph.isNotEmpty())
                resources.getIdentifier("ic_tb_$glyph", "drawable", packageName) else 0
            val view: View = if (resId != 0) {
                ImageView(this).apply {
                    setImageResource(resId)
                    scaleType = ImageView.ScaleType.FIT_CENTER
                    val p = dp(if (glyph == "siri") 2 else 8)
                    setPadding(p, p, p, p)
                }
            } else {
                TextView(this).apply {
                    text = it.optString("icon", "•")
                    textSize = 18f
                    gravity = Gravity.CENTER
                }
            }
            view.setBackgroundResource(R.drawable.touchbar_btn)
            view.isClickable = true
            view.layoutParams = LinearLayout.LayoutParams(0, dp(38), 1f).also { lp ->
                lp.marginStart = dp(2); lp.marginEnd = dp(2)
            }
            view.setOnClickListener { v ->
                v.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                when (it.optString("nav")) {
                    "apps" -> openApps()
                    "emoji" -> showEmojiPicker()
                    else -> action(it.optString("id"))
                }
            }
            b.touchbar.addView(view)
        }
    }

    private fun showEmojiPicker() {
        emojiMode = true
        touchbarSig = ""
        b.touchbar.removeAllViews()

        val back = ImageView(this).apply {
            setImageResource(R.drawable.ic_tb_chevron_left)
            scaleType = ImageView.ScaleType.FIT_CENTER
            val p = dp(8); setPadding(p, p, p, p)
            setBackgroundResource(R.drawable.touchbar_btn)
            layoutParams = LinearLayout.LayoutParams(dp(46), dp(38)).also { it.marginEnd = dp(4) }
            setOnClickListener {
                emojiMode = false
                touchbarSig = ""
                lastTouchbar?.let { arr -> renderTouchbar(arr) }
            }
        }
        b.touchbar.addView(back)

        val scroller = HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = false
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f)
        }
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        for (e in emojis) {
            val tv = TextView(this).apply {
                text = e
                textSize = 20f
                gravity = Gravity.CENTER
                setBackgroundResource(R.drawable.touchbar_btn)
                layoutParams = LinearLayout.LayoutParams(dp(46), dp(38)).also { it.marginEnd = dp(2) }
                setOnClickListener { v ->
                    v.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                    typeText(e)
                }
            }
            row.addView(tv)
        }
        scroller.addView(row)
        b.touchbar.addView(scroller)
    }

    private fun typeText(text: String) =
        io.execute { httpPost("$base/api/type", JSONObject().put("text", text)) }

    // ---- Widgets ----

    private fun renderBatteries(o: JSONObject) {
        val ll = b.llBatteries
        ll.removeAllViews()
        val bat = o.opt("battery")
        if (bat != null && bat !== JSONObject.NULL) {
            addBatteryRow(ll, if (o.optBoolean("charging")) "Mac ⚡" else "Mac", o.optInt("battery"))
        }
        o.optJSONArray("bt")?.let { arr ->
            for (i in 0 until arr.length()) {
                val d = arr.getJSONObject(i)
                val status = d.optString("status")
                if (status.isNotEmpty()) addStatusRow(ll, d.optString("name"), status)
                else addBatteryRow(ll, d.optString("name"), d.optInt("pct"))
            }
        }
        if (ll.childCount == 0) addBatteryRow(ll, "No devices", -1)
    }

    private fun addBatteryRow(parent: ViewGroup, name: String, pct: Int) {
        val row = ItemBatteryBinding.inflate(layoutInflater, parent, false)
        row.tvName.text = name
        if (pct < 0) {
            row.tvPct.text = ""
            row.meter.visibility = View.INVISIBLE
        } else {
            row.tvPct.text = "$pct%"
            val full = dp(44)
            row.meterFill.layoutParams = row.meterFill.layoutParams.apply {
                width = (full * pct / 100f).toInt().coerceAtLeast(dp(2))
            }
            val color = when {
                pct <= 10 -> "#FF453A"; pct <= 25 -> "#FFD60A"; else -> "#30D158"
            }
            row.meterFill.backgroundTintList = ColorStateList.valueOf(Color.parseColor(color))
        }
        parent.addView(row.root)
    }

    private fun addStatusRow(parent: ViewGroup, name: String, status: String) {
        val row = LinearLayout(this)
        row.orientation = LinearLayout.HORIZONTAL
        row.gravity = Gravity.CENTER_VERTICAL
        row.setPadding(0, dp(3), 0, dp(3))

        val nameTv = TextView(this).apply {
            text = name
            setTextColor(Color.parseColor("#F2F2F7"))
            textSize = 12f
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        }
        val ok = status.equals("Connected", true) || status.equals("Yes", true)
        val statusTv = TextView(this).apply {
            text = status
            setTextColor(Color.parseColor(if (ok) "#30D158" else "#8A8A8E"))
            textSize = 12f
            setTypeface(typeface, android.graphics.Typeface.BOLD)
        }
        row.addView(nameTv)
        row.addView(statusTv)
        parent.addView(row, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
    }

    private fun renderRam(ram: JSONObject?) {
        if (ram == null) {
            b.tvRamPct.text = "—"; b.tvRamUsed.text = "—"; return
        }
        val pct = ram.optInt("percent")
        b.tvRamPct.text = "$pct%"
        b.tvRamUsed.text = "${ram.optDouble("used_gb")} / ${ram.optDouble("total_gb")} GB"
        val color = when {
            pct >= 90 -> "#FF453A"; pct >= 75 -> "#FFD60A"; else -> "#30D158"
        }
        b.ramFill.backgroundTintList = ColorStateList.valueOf(Color.parseColor(color))
        b.ramTrack.post {
            b.ramFill.layoutParams = b.ramFill.layoutParams.apply {
                width = (b.ramTrack.width * pct / 100.0).toInt()
            }
        }
    }

    private fun renderNetwork(net: JSONObject?) {
        if (net == null) return
        val down = net.optDouble("down", 0.0)
        val up = net.optDouble("up", 0.0)
        b.tvNetRate.text = "↓ %.1f   ↑ %.1f Mbps".format(down, up)
        if (net.isNull("ping")) {
            b.tvNetPing.text = "— ms"
            b.tvNetPing.setTextColor(Color.parseColor("#8A8A8E"))
        } else {
            val ping = net.optInt("ping")
            b.tvNetPing.text = "$ping ms"
            val color = when { ping <= 40 -> "#30D158"; ping <= 100 -> "#FFD60A"; else -> "#FF453A" }
            b.tvNetPing.setTextColor(Color.parseColor(color))
        }
    }

    private fun renderPylon(p: JSONObject?) {
        if (p == null) { b.llPylon.visibility = View.GONE; return }
        b.llPylon.visibility = View.VISIBLE
        val new = p.optInt("new", 0)
        val onYou = p.optInt("on_you", 0)
        val open = p.optInt("open", 0)
        b.tvPylonNew.text = "$new New"
        b.tvPylonOnYou.text = "$onYou On you"
        b.tvPylonOnYou.setTextColor(Color.parseColor(if (onYou > 0) "#FFD60A" else "#F2F2F7"))
        b.tvPylonOpen.text = "$open Open"
    }

    // Highlight the tile of the Mac app that's currently frontmost.
    private fun highlightActiveApp(frontmost: String) {
        if (!gridBuilt) return
        var newId: String? = null
        if (frontmost.isNotEmpty()) {
            for (btn in buttons) {
                if (btn.optString("app").equals(frontmost, true)) { newId = btn.optString("id"); break }
            }
        }
        if (newId == activeAppId) return
        activeAppId?.let { cells[it]?.root?.setBackgroundResource(R.drawable.btn_bg) }
        activeAppId = newId
        newId?.let { cells[it]?.root?.setBackgroundResource(R.drawable.btn_bg_active) }
    }

    private fun renderPlayer(np: JSONObject?) {
        if (np == null) { b.player.visibility = View.GONE; return }
        b.player.visibility = View.VISIBLE
        b.tvTrack.text = np.optString("track")
        b.tvArtist.text = np.optString("artist")
        b.btnPlay.text = if (np.optBoolean("playing")) "⏸" else "▶"
        val dur = np.optDouble("dur", 0.0)
        val pos = np.optDouble("pos", 0.0)
        val frac = if (dur > 0) (pos / dur).coerceIn(0.0, 1.0) else 0.0
        b.progressTrack.post {
            b.progressFill.layoutParams = b.progressFill.layoutParams.apply {
                width = (b.progressTrack.width * frac).toInt()
            }
        }
    }

    // ---- Navigation + actions ----

    private fun openDashboard() {
        val url = dashboardUrl ?: return
        startActivity(Intent(this, DashboardActivity::class.java).putExtra("url", url))
        overridePendingTransition(R.anim.slide_in_right, R.anim.slide_out_left)
    }

    private fun openApps() {
        startActivity(Intent(this, RunningAppsActivity::class.java))
        overridePendingTransition(R.anim.slide_in_left, R.anim.slide_out_right)
    }

    private fun action(id: String) = io.execute { httpPost("$base/api/action", JSONObject().put("id", id)) }

    private fun media(cmd: String, v: View) {
        v.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
        io.execute {
            httpPost("$base/api/media", JSONObject().put("cmd", cmd))
            ui.postDelayed({ poll() }, 250)
        }
    }

    private fun httpGet(url: String): JSONObject? {
        var c: HttpURLConnection? = null
        return try {
            c = (URL(url).openConnection() as HttpURLConnection).apply {
                connectTimeout = 1500; readTimeout = 1500
            }
            JSONObject(c.inputStream.bufferedReader().use { it.readText() })
        } catch (e: Exception) { null } finally { c?.disconnect() }
    }

    private fun httpPost(url: String, body: JSONObject) {
        var c: HttpURLConnection? = null
        try {
            c = (URL(url).openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"; doOutput = true
                connectTimeout = 1500; readTimeout = 1500
                setRequestProperty("Content-Type", "application/json")
            }
            c.outputStream.use { it.write(body.toString().toByteArray()) }
            c.inputStream.use { it.readBytes() }
        } catch (e: Exception) { /* best effort */ } finally { c?.disconnect() }
    }
}
