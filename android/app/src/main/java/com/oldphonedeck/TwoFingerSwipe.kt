package com.oldphonedeck

import android.view.MotionEvent
import kotlin.math.abs

/** Detects a two-finger horizontal swipe. Single-finger touches are ignored,
 *  so taps and button presses never accidentally change screens. */
class TwoFingerSwipe(
    private val density: Float,
    private val onRight: () -> Unit,
    private val onLeft: () -> Unit,
) {
    private var maxPointers = 0
    private var startX = 0f
    private var startY = 0f
    private var fired = false

    fun onTouch(ev: MotionEvent) {
        when (ev.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                maxPointers = 1; fired = false
                startX = ev.getX(0); startY = ev.getY(0)
            }
            MotionEvent.ACTION_POINTER_DOWN -> {
                maxPointers = maxOf(maxPointers, ev.pointerCount)
                if (ev.pointerCount >= 2) {
                    startX = ev.getX(0); startY = ev.getY(0); fired = false
                }
            }
            MotionEvent.ACTION_MOVE -> {
                if (!fired && maxPointers >= 2 && ev.pointerCount >= 2) {
                    val dx = ev.getX(0) - startX
                    val dy = ev.getY(0) - startY
                    val thresh = 85 * density
                    if (abs(dx) > thresh && abs(dx) > abs(dy) * 1.2f) {
                        fired = true
                        if (dx > 0) onRight() else onLeft()
                    }
                }
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> maxPointers = 0
        }
    }
}
