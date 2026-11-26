package com.hdrmerge.lite

import android.graphics.drawable.AdaptiveIconDrawable
import android.os.Build
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class LauncherIconTest {
    @Test
    fun applicationUsesApertureLauncherIcon() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        assertEquals(R.drawable.ic_launcher, context.applicationInfo.icon)
        val icon = context.packageManager.getApplicationIcon(context.packageName)
        assertNotNull(icon)
        if (Build.VERSION.SDK_INT >= 26) {
            assertTrue(icon is AdaptiveIconDrawable)
        }
    }
}
