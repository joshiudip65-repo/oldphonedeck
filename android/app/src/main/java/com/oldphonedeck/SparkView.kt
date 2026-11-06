package com.oldphonedeck

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.util.AttributeSet
import android.view.View

/** Minimal sparkline: feed it a list of values, it draws a smooth-ish polyline. */
class SparkView @JvmOverloads constructor(ctx: Context, attrs: AttributeSet? = null) :
    View(ctx, attrs) {

    private val data = ArrayList<Float>()
    private val linePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 3f
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
        color = Color.parseColor("#0A84FF")
    }
    private val fillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = Color.parseColor("#1F0A84FF")
    }

    fun setData(values: List<Float>) {
        data.clear()
        data.addAll(values)
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        if (data.size < 2) return
        val max = (data.maxOrNull() ?: 1f).coerceAtLeast(1f)
        val w = width.toFloat()
        val h = height.toFloat()
        val pad = h * 0.08f
        val line = Path()
        data.forEachIndexed { i, v ->
            val x = i.toFloat() / (data.size - 1) * w
            val y = h - pad - (v / max) * (h - pad * 2)
            if (i == 0) line.moveTo(x, y) else line.lineTo(x, y)
        }
        val fill = Path(line)
        fill.lineTo(w, h)
        fill.lineTo(0f, h)
        fill.close()
        canvas.drawPath(fill, fillPaint)
        canvas.drawPath(line, linePaint)
    }
}
