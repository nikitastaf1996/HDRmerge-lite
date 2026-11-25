package com.hdrmerge.lite

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.Uri
import java.io.File

/**
 * Storage Access Framework helpers.
 *
 * DNGs selected by the user live behind a `content://` URI, but the Python
 * core (via tifffile) needs a real file path. Picked files are therefore copied
 * into the app's private directory before merging, and the merged result is
 * copied back to a user-chosen location afterwards.
 */
object DngFiles {

    const val RC_PICK_SHORT = 1001
    const val RC_PICK_MEDIUM = 1002
    const val RC_PICK_LONG = 1003
    const val RC_SAVE = 1010

    /** Open the system file picker for a single DNG. */
    fun pick(activity: Activity, requestCode: Int) {
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "image/*"
        }
        activity.startActivityForResult(intent, requestCode)
    }

    /** Ask the system to create a new DNG file at a user-chosen location. */
    fun createDocument(activity: Activity, fileName: String, requestCode: Int) {
        val intent = Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "image/dng"
            putExtra(Intent.EXTRA_TITLE, fileName)
        }
        activity.startActivityForResult(intent, requestCode)
    }

    /** Copy a content:// URI into [dest], a real file Python can open by path. */
    fun copyUriToFile(context: Context, uri: Uri, dest: File): Boolean {
        return try {
            dest.parentFile?.mkdirs()
            context.contentResolver.openInputStream(uri)?.use { input ->
                dest.outputStream().use { output -> input.copyTo(output) }
            } ?: return false
            true
        } catch (e: Exception) {
            false
        }
    }

    /** Copy a generated file into a user-chosen content:// destination. */
    fun copyFileToUri(context: Context, src: File, uri: Uri): Boolean {
        return try {
            context.contentResolver.openOutputStream(uri)?.use { output ->
                src.inputStream().use { input -> input.copyTo(output) }
            } ?: return false
            true
        } catch (e: Exception) {
            false
        }
    }
}
