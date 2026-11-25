package com.hdrmerge.lite

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.chaquo.python.Python
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class HdrMergeEngineTest {
    @Test
    fun mergesRealDngsThroughTheJavaPythonBridge() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val dir = File(context.cacheDir, "bridge-test").apply {
            deleteRecursively()
            mkdirs()
        }
        try {
            // Load the test-only fixture helpers into Python, not the app APK.
            val script = instrumentation.context.assets.open("bridge_fixtures.py")
                .bufferedReader().use { it.readText() }
            val builtins = Python.getInstance().getModule("builtins")
            builtins.callAttr("exec", script, builtins.get("__dict__"))
            builtins.callAttr("make_bridge_fixtures", dir.absolutePath)

            // map produces a Java ArrayList, just like MainActivity does.
            val inputs = (0..2).map { File(dir, "$it.dng").absolutePath }
            val output = File(dir, "merged.dng")
            val progress = mutableListOf<String>()
            val path = HdrMergeEngine(context).merge(
                inputs, output.absolutePath, false, 3, 16,
                HdrMergeEngine.ProgressSink { progress.add(it) },
            )

            assertEquals(output.absolutePath, path)
            assertTrue(output.isFile)
            assertTrue(progress.isNotEmpty())
            assertEquals("True", builtins.callAttr("verify_bridge_output", path).toString())
        } finally {
            dir.deleteRecursively()
        }
    }
}
