package com.hdrmerge.lite

import android.content.Context
import com.chaquo.python.AndroidPlatform
import com.chaquo.python.Python
import com.chaquo.python.PyObject

/**
 * Bridge between the Android UI and the HDRMerge Python core.
 *
 * Chaquopy embeds a CPython interpreter in the app. Python is started once (the
 * manifest points at [com.chaquo.python.android.PyApplication]) and the
 * [hdrmerge_app] module — copied from ../python at build time — is loaded on
 * first use. [merge] is a blocking call and must run off the main thread.
 */
class HdrMergeEngine(context: Context) {

    private val appContext = context.applicationContext

    @Volatile
    private var python: Python? = null
    @Volatile
    private var module: PyObject? = null

    /** Receives status lines emitted by the Python core during a merge. */
    fun interface ProgressSink {
        fun onProgress(message: String)
    }

    val isReady: Boolean
        get() = module != null

    private fun ensureStarted(): Python {
        python?.let { return it }
        synchronized(this) {
            python?.let { return it }
            val p = if (Python.isStarted()) Python.getMainPython()
            else Python.start(AndroidPlatform(appContext))
            module = p.getModule("hdrmerge_app")
            return p
        }
    }

    /**
     * Merge three DNG exposures into a floating-point CFA DNG.
     *
     * @param inputs three real filesystem paths to input DNGs
     * @param outputPath destination file path for the merged DNG
     * @param align whether to run HDRMerge's automatic alignment/crop
     * @param radius mask feather radius (0 disables feathering)
     * @param bits output floating-point depth, 16 or 32
     * @param progress optional callback for status lines (may be null)
     * @return the output path
     * @throws com.chaquo.python.PyException if the Python core rejects the input
     */
    fun merge(
        inputs: List<String>,
        outputPath: String,
        align: Boolean,
        radius: Int,
        bits: Int,
        progress: ProgressSink?,
    ): String {
        val py = ensureStarted()
        val result = module!!.callAttr("run", inputs, outputPath, align, radius, bits, progress)
        return result.getAttr("output").getString()
    }
}
