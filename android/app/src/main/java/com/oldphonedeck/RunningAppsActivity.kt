package com.oldphonedeck

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.HapticFeedbackConstants
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.GridLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.oldphonedeck.databinding.ActivityRunningappsBinding
import com.oldphonedeck.databinding.ItemAppBinding
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.concurrent.Executors

class RunningAppsActivity : AppCompatActivity() {

    private lateinit var b: ActivityRunningappsBinding
    private val io = Executors.newSingleThreadExecutor()
    private val ui = Handler(Looper.getMainLooper())
    private val base = "http://localhost:8790"

    private val apps = ArrayList<String>()
    private val iconCache = HashMap<String, Bitmap?>()
    private val iconLoading = HashSet<String>()
    private lateinit var adapter: AppAdapter
    private lateinit var swipe: TwoFingerSwipe

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityRunningappsBinding.inflate(layoutInflater)
        setContentView(b.root)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        hideSystemBars()

        adapter = AppAdapter()
        b.rvApps.layoutManager = GridLayoutManager(this, 5)
        b.rvApps.adapter = adapter
        b.closeBtn.setOnClickListener { closeBack() }

        swipe = TwoFingerSwipe(resources.displayMetrics.density,
            onRight = { closeBack() }, onLeft = { })
        loadApps()
    }

    override fun dispatchTouchEvent(ev: MotionEvent): Boolean {
        swipe.onTouch(ev)
        return super.dispatchTouchEvent(ev)
    }

    private fun closeBack() {
        finish()
        overridePendingTransition(R.anim.slide_in_right, R.anim.slide_out_left)
    }

    @Suppress("DEPRECATION")
    override fun onBackPressed() = closeBack()

    private fun loadApps() {
        io.execute {
            val list = ArrayList<String>()
            try {
                val c = (URL("$base/api/apps").openConnection() as HttpURLConnection).apply {
                    connectTimeout = 2000; readTimeout = 4000
                }
                val arr = JSONObject(c.inputStream.bufferedReader().use { it.readText() })
                    .optJSONArray("apps")
                if (arr != null) for (i in 0 until arr.length()) list.add(arr.getJSONObject(i).optString("name"))
            } catch (e: Exception) { /* ignore */ }
            ui.post {
                apps.clear(); apps.addAll(list); adapter.notifyDataSetChanged()
            }
        }
    }

    private fun quit(name: String) {
        io.execute {
            try {
                val c = (URL("$base/api/quit").openConnection() as HttpURLConnection).apply {
                    requestMethod = "POST"; doOutput = true
                    connectTimeout = 2000; readTimeout = 3000
                    setRequestProperty("Content-Type", "application/json")
                }
                c.outputStream.use { it.write(JSONObject().put("name", name).toString().toByteArray()) }
                c.inputStream.use { it.readBytes() }
            } catch (e: Exception) { /* ignore */ }
            ui.post {
                val i = apps.indexOf(name)
                if (i >= 0) { apps.removeAt(i); adapter.notifyItemRemoved(i) }
                Toast.makeText(this, "Quit $name", Toast.LENGTH_SHORT).show()
                ui.postDelayed({ loadApps() }, 1200)  // reconcile with the Mac
            }
        }
    }

    private fun loadIcon(name: String, pos: Int) {
        if (!iconLoading.add(name)) return
        io.execute {
            var bmp: Bitmap? = null
            var c: HttpURLConnection? = null
            try {
                val url = "$base/api/appicon?name=" + URLEncoder.encode(name, "UTF-8")
                c = (URL(url).openConnection() as HttpURLConnection).apply {
                    connectTimeout = 2000; readTimeout = 5000
                }
                if (c.responseCode == 200) bmp = BitmapFactory.decodeStream(c.inputStream)
            } catch (e: Exception) { /* ignore */ } finally { c?.disconnect() }
            val result = bmp
            ui.post {
                iconCache[name] = result
                iconLoading.remove(name)
                val i = apps.indexOf(name)
                if (result != null && i >= 0) adapter.notifyItemChanged(i)
            }
        }
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

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) hideSystemBars()
    }

    inner class AppAdapter : RecyclerView.Adapter<AppAdapter.VH>() {
        inner class VH(val v: ItemAppBinding) : RecyclerView.ViewHolder(v.root)

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH =
            VH(ItemAppBinding.inflate(layoutInflater, parent, false))

        override fun getItemCount() = apps.size

        override fun onBindViewHolder(h: VH, i: Int) {
            val name = apps[i]
            h.v.appName.text = name
            h.v.appEmoji.text = name.take(1).uppercase()

            val bmp = iconCache[name]
            if (bmp != null) {
                h.v.appImg.setImageBitmap(bmp)
                h.v.appImg.visibility = View.VISIBLE
                h.v.appEmoji.visibility = View.GONE
            } else {
                h.v.appImg.visibility = View.GONE
                h.v.appEmoji.visibility = View.VISIBLE
                if (!iconCache.containsKey(name)) loadIcon(name, i)
            }

            h.v.root.setOnClickListener {
                it.performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
                quit(name)
            }
        }
    }
}
