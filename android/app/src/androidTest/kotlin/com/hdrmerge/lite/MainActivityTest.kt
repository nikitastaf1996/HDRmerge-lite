package com.hdrmerge.lite

import android.content.Intent
import android.os.Build
import android.provider.MediaStore
import android.view.View
import android.widget.RadioGroup
import android.widget.SeekBar
import android.widget.TextView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class MainActivityTest {
    @Test
    fun screenDefaultsToZeroAndResetClearsAllExposures() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val prefs = context.getSharedPreferences("exposures", 0)
        prefs.edit().clear().commit()
        val dir = File(context.filesDir, "inputs").apply { mkdirs() }
        val inputs = (1..3).map { File(dir, "exposure_$it.dng").apply { writeText("fixture") } }
        (0..2).forEach { prefs.edit().putString("name_$it", "test$it.dng").commit() }
        val intent = Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        val activity = instrumentation.startActivitySync(intent) as MainActivity
        try {
            instrumentation.runOnMainSync {
                for (id in listOf(R.id.rowShort, R.id.rowMedium, R.id.rowLong)) {
                    val row = activity.findViewById<View>(id)
                    assertNotNull(row.findViewById<TextView>(R.id.fileLabel))
                    assertNotNull(row.findViewById<TextView>(R.id.slotLabel))
                }
                assertEquals(0, activity.findViewById<SeekBar>(R.id.radiusSeek).progress)
                assertEquals(64, activity.findViewById<SeekBar>(R.id.radiusSeek).max)
                assertEquals(2, activity.findViewById<RadioGroup>(R.id.bitsGroup).childCount)
                assertEquals("—  3 of 3 selected", activity.findViewById<TextView>(R.id.selectionCount).text.toString())
                activity.findViewById<View>(R.id.resetButton).performClick()
                assertEquals("—  0 of 3 selected", activity.findViewById<TextView>(R.id.selectionCount).text.toString())
                for (id in listOf(R.id.rowShort, R.id.rowMedium, R.id.rowLong)) {
                    assertEquals("Select a DNG", activity.findViewById<View>(id).findViewById<TextView>(R.id.fileLabel).text.toString())
                }
                assertFalse(inputs.any { it.exists() })
            }
        } finally {
            activity.finish()
            inputs.forEach { it.delete() }
            prefs.edit().clear().commit()
        }
    }
    @Test
    fun pendingSaveCanBeRetriedAfterReset() {
        assumeTrue(Build.VERSION.SDK_INT >= 29)
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val prefs = context.getSharedPreferences("exposures", 0)
        prefs.edit().clear().commit()
        val pending = File(context.filesDir, "output/merged.dng")
        pending.parentFile!!.mkdirs()
        pending.writeBytes(byteArrayOf(1, 2, 3))
        val name = DngFiles.outputName("retry.dng")
        prefs.edit().putString("pending_name", name).putInt("pending_bits", 16).commit()
        val intent = Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        val activity = instrumentation.startActivitySync(intent) as MainActivity
        try {
            instrumentation.runOnMainSync {
                activity.findViewById<View>(R.id.resetButton).performClick()
                assertTrue(pending.isFile)
                assertEquals("Retry save", activity.findViewById<TextView>(R.id.mergeButton).text.toString())
                activity.findViewById<View>(R.id.mergeButton).performClick()
            }
            val deadline = System.currentTimeMillis() + 15000
            var saved = false
            while (!saved && System.currentTimeMillis() < deadline) {
                instrumentation.runOnMainSync {
                    saved = activity.findViewById<TextView>(R.id.statusText).text.toString().contains("Pictures/HDRmerge/$name")
                }
                if (!saved) Thread.sleep(50)
            }
            assertTrue("Pending output was not saved", saved)
            assertFalse(prefs.contains("pending_name"))
            assertFalse(pending.exists())
        } finally {
            activity.finish()
            val collection = MediaStore.Images.Media.EXTERNAL_CONTENT_URI
            context.contentResolver.query(collection, arrayOf(MediaStore.Images.Media._ID), "${MediaStore.Images.Media.DISPLAY_NAME} = ?", arrayOf(name), null)?.use {
                while (it.moveToNext()) {
                    context.contentResolver.delete(android.content.ContentUris.withAppendedId(collection, it.getLong(0)), null, null)
                }
            }
            pending.delete()
            prefs.edit().clear().commit()
        }
    }

}
