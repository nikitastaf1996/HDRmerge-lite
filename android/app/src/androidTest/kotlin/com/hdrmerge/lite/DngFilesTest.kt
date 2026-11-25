package com.hdrmerge.lite

import android.os.Build
import android.provider.MediaStore
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class DngFilesTest {
    @Test
    fun namesAreSafeDescriptiveAndUnique() {
        val first = DngFiles.outputName("IMG 123.DNG")
        val second = DngFiles.outputName("IMG 123.DNG")
        assertTrue(first.startsWith("IMG_123_HDR_"))
        assertTrue(first.endsWith(".dng"))
        assertNotEquals(first, second)
        assertTrue(!DngFiles.outputName("../../test.dng").contains('/'))
    }

    @Test
    fun savesToPicturesAndPublishesCompleteBytes() {
        assumeTrue(Build.VERSION.SDK_INT >= 29)
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val bytes = byteArrayOf(1, 2, 3, 4)
        val source = File(context.cacheDir, "save-test.dng").apply { writeBytes(bytes) }
        val name = DngFiles.outputName("bracket.dng")
        val saved = DngFiles.saveMerged(context, source, name)
        try {
            context.contentResolver.openInputStream(saved.uri)!!.use { assertArrayEquals(bytes, it.readBytes()) }
            context.contentResolver.query(saved.uri, arrayOf(MediaStore.Images.Media.DISPLAY_NAME, MediaStore.Images.Media.RELATIVE_PATH, MediaStore.Images.Media.IS_PENDING), null, null, null)!!.use {
                assertTrue(it.moveToFirst())
                assertEquals(name, it.getString(0))
                assertEquals("Pictures/HDRmerge/", it.getString(1))
                assertEquals(0, it.getInt(2))
            }
        } finally {
            context.contentResolver.delete(saved.uri, null, null)
            source.delete()
        }
    }
}
