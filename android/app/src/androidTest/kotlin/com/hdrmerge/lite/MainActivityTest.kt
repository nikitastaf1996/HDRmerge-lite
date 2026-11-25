package com.hdrmerge.lite

import android.content.Intent
import android.widget.RadioGroup
import android.widget.SeekBar
import android.widget.TextView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class MainActivityTest {
    @Test
    fun screenShowsExposureCardsAndSupportedSettings() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val intent = Intent(instrumentation.targetContext, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        val activity = instrumentation.startActivitySync(intent) as MainActivity
        try {
            instrumentation.runOnMainSync {
                for (id in listOf(R.id.rowShort, R.id.rowMedium, R.id.rowLong)) {
                    val row = activity.findViewById<android.view.View>(id)
                    assertNotNull(row.findViewById<TextView>(R.id.fileLabel))
                    assertNotNull(row.findViewById<TextView>(R.id.slotLabel))
                }
                assertEquals(64, activity.findViewById<SeekBar>(R.id.radiusSeek).max)
                assertEquals(2, activity.findViewById<RadioGroup>(R.id.bitsGroup).childCount)
                assertNotNull(activity.findViewById<android.view.View>(R.id.mergeButton))
                assertNotNull(activity.findViewById<android.view.View>(R.id.saveButton))
            }
        } finally {
            activity.finish()
        }
    }
}
