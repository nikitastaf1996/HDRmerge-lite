package com.hdrmerge.lite

import android.app.Activity
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.media.MediaScannerConnection
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID

/** File picker, private input copies, and shared output storage. */
object DngFiles {
    const val RC_PICK_SHORT = 1001
    const val RC_PICK_MEDIUM = 1002
    const val RC_PICK_LONG = 1003
    const val OUTPUT_FOLDER = "Pictures/HDRmerge"
    private const val DNG_MIME = "image/x-adobe-dng"

    data class SavedOutput(val name: String, val uri: Uri)

    fun pick(activity: Activity, requestCode: Int) {
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "*/*"
            putExtra(Intent.EXTRA_MIME_TYPES, arrayOf("image/*", "application/octet-stream"))
        }
        activity.startActivityForResult(intent, requestCode)
    }

    fun copyUriToFile(context: Context, uri: Uri, dest: File): Boolean {
        val temp = File(dest.parentFile, "${dest.name}.tmp")
        return try {
            dest.parentFile?.mkdirs()
            context.contentResolver.openInputStream(uri)?.use { input ->
                temp.outputStream().use { output -> input.copyTo(output) }
            } ?: return false
            temp.renameTo(dest)
        } catch (e: Exception) {
            false
        } finally {
            temp.delete()
        }
    }

    /** A recognizable, filesystem-safe name which won't overwrite another merge. */
    fun outputName(inputName: String): String {
        val base = inputName.substringAfterLast('/').substringAfterLast('\\')
            .replace(Regex("(?i)\\.dng$"), "")
            .replace(Regex("[^\\p{L}\\p{N}_-]+"), "_")
            .trim('_', '-')
            .take(48).ifEmpty { "exposure" }
        val timestamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
        return "${base}_HDR_${timestamp}_${UUID.randomUUID().toString().take(8)}.dng"
    }

    /** Copy a completed merge to shared Pictures/HDRmerge, deleting partial writes on failure. */
    fun saveMerged(context: Context, source: File, name: String): SavedOutput {
        require(source.isFile) { "Merged DNG is missing" }
        if (Build.VERSION.SDK_INT >= 29) {
            val resolver = context.contentResolver
            val values = ContentValues().apply {
                put(MediaStore.Images.Media.DISPLAY_NAME, name)
                put(MediaStore.Images.Media.MIME_TYPE, DNG_MIME)
                put(MediaStore.Images.Media.RELATIVE_PATH, "${Environment.DIRECTORY_PICTURES}/HDRmerge/")
                put(MediaStore.Images.Media.IS_PENDING, 1)
            }
            val uri = resolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values)
                ?: throw java.io.IOException("Could not create output in $OUTPUT_FOLDER")
            try {
                val stream = resolver.openOutputStream(uri) ?: throw java.io.IOException("Could not open output")
                stream.use { output -> source.inputStream().use { it.copyTo(output) } }
                val published = ContentValues().apply { put(MediaStore.Images.Media.IS_PENDING, 0) }
                if (resolver.update(uri, published, null, null) != 1) throw java.io.IOException("Could not publish output")
                return SavedOutput(name, uri)
            } catch (e: Exception) {
                try { resolver.delete(uri, null, null) } catch (_: Exception) { }
                throw e
            }
        } else {
            @Suppress("DEPRECATION")
            val directory = File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES), "HDRmerge")
            if (!directory.isDirectory && !directory.mkdirs()) throw java.io.IOException("Could not create $OUTPUT_FOLDER")
            val target = File(directory, name)
            if (!target.createNewFile()) throw java.io.IOException("Output file already exists")
            try {
                source.inputStream().use { input -> target.outputStream().use { input.copyTo(it) } }
                MediaScannerConnection.scanFile(context, arrayOf(target.absolutePath), arrayOf(DNG_MIME), null)
                return SavedOutput(name, Uri.fromFile(target))
            } catch (e: Exception) {
                target.delete()
                throw e
            }
        }
    }
}
