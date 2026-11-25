package com.hdrmerge.lite

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.OpenableColumns
import android.util.Size
import android.view.View
import android.widget.Button
import android.widget.ImageView
import android.widget.ProgressBar
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.SeekBar
import android.widget.Switch
import android.widget.TextView
import java.io.File
import java.util.concurrent.Executors

/** Pick three raw files, merge them off the UI thread, and save the result. */
class MainActivity : Activity() {
    private lateinit var engine: HdrMergeEngine
    private lateinit var statusText: TextView
    private lateinit var progressBar: ProgressBar
    private lateinit var mergeButton: Button
    private lateinit var resetButton: Button
    private lateinit var radiusSeek: SeekBar
    private lateinit var radiusValue: TextView
    private lateinit var alignSwitch: Switch
    private lateinit var bitsGroup: RadioGroup
    private lateinit var rows: List<View>
    private val executor = Executors.newSingleThreadExecutor()
    private val mainHandler = Handler(Looper.getMainLooper())
    private val prefs by lazy { getSharedPreferences("exposures", MODE_PRIVATE) }
    private val inputDir by lazy { File(filesDir, "inputs") }
    private val outputFile by lazy { File(filesDir, "output/merged.dng") }
    private val inputFiles by lazy { (1..3).map { File(inputDir, "exposure_$it.dng") } }
    private val thumbnailFiles by lazy { (1..3).map { File(inputDir, "thumbnail_$it.jpg") } }
    private var merging = false
    private val thumbnailGeneration = IntArray(3)
    private val progressSink = HdrMergeEngine.ProgressSink { message ->
        mainHandler.post { if (!isFinishing && !isDestroyed) appendStatus(message) }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        engine = HdrMergeEngine(this)
        setContentView(R.layout.activity_main)
        statusText = findViewById(R.id.statusText)
        progressBar = findViewById(R.id.progressBar)
        mergeButton = findViewById(R.id.mergeButton)
        resetButton = findViewById(R.id.resetButton)
        radiusSeek = findViewById(R.id.radiusSeek)
        radiusValue = findViewById(R.id.radiusValue)
        alignSwitch = findViewById(R.id.alignCheck)
        bitsGroup = findViewById(R.id.bitsGroup)
        rows = listOf(findViewById(R.id.rowShort), findViewById(R.id.rowMedium), findViewById(R.id.rowLong))

        radiusSeek.progress = prefs.getInt("radius", 0)
        radiusValue.text = "${radiusSeek.progress} px"
        alignSwitch.isChecked = prefs.getBoolean("align", true)
        bitsGroup.check(if (prefs.getInt("bits", 16) == 32) R.id.bits32 else R.id.bits16)
        val requests = listOf(DngFiles.RC_PICK_SHORT, DngFiles.RC_PICK_MEDIUM, DngFiles.RC_PICK_LONG)
        rows.forEachIndexed { index, row ->
            row.findViewById<TextView>(R.id.slotLabel).text = "Exposure ${index + 1}"
            row.setOnClickListener { DngFiles.pick(this, requests[index]) }
            updateRow(index)
        }
        updateCount()
        updateMergeButton()
        if (hasPendingOutput()) setStatus("A merged DNG is waiting to be saved. Tap Retry save.")

        radiusSeek.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar, progress: Int, fromUser: Boolean) {
                radiusValue.text = "$progress px"
                if (fromUser) {
                    prefs.edit().putInt("radius", progress).apply()
                }
            }
            override fun onStartTrackingTouch(seekBar: SeekBar) = Unit
            override fun onStopTrackingTouch(seekBar: SeekBar) = Unit
        })
        alignSwitch.setOnCheckedChangeListener { _, checked ->
            prefs.edit().putBoolean("align", checked).apply()
        }
        bitsGroup.setOnCheckedChangeListener { _, id ->
            prefs.edit().putInt("bits", if (id == R.id.bits32) 32 else 16).apply()
        }
        mergeButton.setOnClickListener { startMerge() }
        resetButton.setOnClickListener { resetExposures() }
    }

    override fun onDestroy() {
        super.onDestroy()
        executor.shutdownNow()
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (resultCode != RESULT_OK || data?.data == null) return
        val uri = data.data!!
        when (requestCode) {
            DngFiles.RC_PICK_SHORT, DngFiles.RC_PICK_MEDIUM, DngFiles.RC_PICK_LONG -> {
                val index = when (requestCode) {
                    DngFiles.RC_PICK_SHORT -> 0
                    DngFiles.RC_PICK_MEDIUM -> 1
                    else -> 2
                }
                val name = try {
                    contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use {
                        if (it.moveToFirst()) it.getString(0) else null
                    }
                } catch (_: Exception) { null } ?: uri.lastPathSegment ?: "Selected DNG"
                setMerging(true)
                setStatus("Loading $name…")
                executor.execute {
                    val copied = DngFiles.copyUriToFile(this, uri, inputFiles[index])
                    mainHandler.post {
                        if (!isFinishing && !isDestroyed) {
                            setMerging(false)
                            if (copied) {
                                thumbnailGeneration[index]++
                                val generation = thumbnailGeneration[index]
                                thumbnailFiles[index].delete()
                                prefs.edit().putString("name_$index", name).apply()
                                updateRow(index)
                                updateCount()
                                setStatus(if (hasPendingOutput()) "Loaded $name. An earlier merge still needs Retry save." else "Loaded $name")
                                // Providers may not expose a DNG thumbnail; keep the placeholder if not.
                                if (Build.VERSION.SDK_INT >= 29) executor.execute {
                                    try {
                                        val bitmap = contentResolver.loadThumbnail(uri, Size(320, 240), null)
                                        mainHandler.post {
                                            if (!isFinishing && !isDestroyed && thumbnailGeneration[index] == generation) {
                                                thumbnailFiles[index].outputStream().use { bitmap.compress(Bitmap.CompressFormat.JPEG, 85, it) }
                                                updateRow(index)
                                            }
                                        }
                                    } catch (_: Exception) { /* No embedded/provider thumbnail. */ }
                                }
                            } else setStatus("Could not read the selected file. Try again.")
                        }
                    }
                }
            }
        }
    }

    private fun updateRow(index: Int) {
        val row = rows[index]
        val selected = inputFiles[index].isFile
        row.findViewById<TextView>(R.id.fileLabel).text = if (selected) prefs.getString("name_$index", "Selected DNG") else "Select a DNG"
        row.findViewById<TextView>(R.id.selectedMark).text = if (selected) "✓" else "＋"
        row.contentDescription = if (selected) "Exposure ${index + 1}, ${prefs.getString("name_$index", "selected DNG")}. Tap to replace" else "Select exposure ${index + 1}"
        val image = row.findViewById<ImageView>(R.id.thumbnail)
        val bitmap = if (selected) BitmapFactory.decodeFile(thumbnailFiles[index].absolutePath) else null
        if (bitmap != null) {
            image.scaleType = ImageView.ScaleType.CENTER_CROP
            image.setImageBitmap(bitmap)
        } else {
            image.scaleType = ImageView.ScaleType.CENTER_INSIDE
            image.setImageResource(R.drawable.ic_photo)
        }
    }

    private fun updateCount() {
        findViewById<TextView>(R.id.selectionCount).text = "—  ${inputFiles.count { it.isFile }} of 3 selected"
    }

    private fun resetExposures() {
        if (merging) return
        var failed = false
        rows.indices.forEach { index ->
            // Invalidate outstanding thumbnail callbacks before clearing the UI.
            thumbnailGeneration[index]++
            if (inputFiles[index].exists() && !inputFiles[index].delete()) {
                failed = true
            } else {
                thumbnailFiles[index].delete()
                prefs.edit().remove("name_$index").apply()
            }
            updateRow(index)
        }
        updateCount()
        setStatus(when {
            failed -> "Could not clear all exposures. Try again."
            hasPendingOutput() -> "Exposures cleared. An earlier merge still needs Retry save."
            else -> "Exposures cleared. Select three DNG files to begin."
        })
    }

    private fun hasPendingOutput(): Boolean = outputFile.isFile && prefs.contains("pending_name")

    private fun startMerge() {
        if (merging) return
        if (!hasPendingOutput() && inputFiles.any { !it.isFile }) {
            setStatus("Please pick all three DNG exposures first.")
            return
        }
        // Scoped storage needs no permission on Android 10+. Older devices need
        // permission before starting the expensive merge, not after it finishes.
        if (Build.VERSION.SDK_INT < 29 && checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.WRITE_EXTERNAL_STORAGE), REQUEST_WRITE_STORAGE)
            return
        }
        val retry = hasPendingOutput()
        val radius = radiusSeek.progress
        val bits = if (retry) prefs.getInt("pending_bits", 16) else if (bitsGroup.checkedRadioButtonId == R.id.bits32) 32 else 16
        val align = alignSwitch.isChecked
        val name = if (retry) prefs.getString("pending_name", null)!! else DngFiles.outputName(prefs.getString("name_0", "exposure") ?: "exposure")
        setMerging(true)
        setStatus(if (retry) "Saving merged DNG…" else "Merging…")
        executor.execute {
            if (!retry) {
                val pendingOutput = File(outputFile.parentFile, "merged-pending.dng")
                try {
                    outputFile.parentFile?.mkdirs()
                    outputFile.delete()
                    pendingOutput.delete()
                    engine.merge(inputFiles.map { it.absolutePath }, pendingOutput.absolutePath, align, radius, bits, progressSink)
                    check(pendingOutput.isFile && pendingOutput.renameTo(outputFile)) { "Could not finalize merged DNG" }
                    check(prefs.edit().putString("pending_name", name).putInt("pending_bits", bits).commit()) { "Could not record merged DNG" }
                } catch (e: Throwable) {
                    pendingOutput.delete()
                    outputFile.delete()
                    mainHandler.post {
                        if (!isFinishing && !isDestroyed) {
                            setMerging(false)
                            setStatus("Merge failed: ${e.message ?: e}")
                        }
                    }
                    return@execute
                }
            }
            try {
                mainHandler.post { if (!isFinishing && !isDestroyed) setStatus("Saving merged DNG…") }
                val size = String.format(java.util.Locale.getDefault(), "%.1f MB", outputFile.length() / 1_000_000.0)
                val saved = DngFiles.saveMerged(applicationContext, outputFile, name)
                prefs.edit().remove("pending_name").remove("pending_bits").apply()
                outputFile.delete()
                mainHandler.post {
                    if (!isFinishing && !isDestroyed) {
                        setMerging(false)
                        setStatus("✓  Saved to ${DngFiles.OUTPUT_FOLDER}/${saved.name} • $bits-bit • $size")
                    }
                }
            } catch (e: Exception) {
                // Keep the private merge and its name so the user can retry without re-merging.
                mainHandler.post {
                    if (!isFinishing && !isDestroyed) {
                        setMerging(false)
                        setStatus("Could not save to ${DngFiles.OUTPUT_FOLDER}: ${e.message ?: e}. Tap Retry save.")
                    }
                }
            }
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_WRITE_STORAGE) {
            if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) startMerge()
            else setStatus("Storage permission is required to save to ${DngFiles.OUTPUT_FOLDER}.")
        }
    }

    private fun setMerging(value: Boolean) {
        merging = value
        updateMergeButton()
        resetButton.isEnabled = !value
        resetButton.alpha = if (value) 0.5f else 1f
        progressBar.visibility = if (value) View.VISIBLE else View.GONE
        rows.forEach { it.isEnabled = !value; it.alpha = if (value) 0.5f else 1f }
        radiusSeek.isEnabled = !value
        alignSwitch.isEnabled = !value
        findViewById<RadioButton>(R.id.bits16).isEnabled = !value
        findViewById<RadioButton>(R.id.bits32).isEnabled = !value
    }

    private fun updateMergeButton() {
        mergeButton.isEnabled = !merging
        mergeButton.alpha = if (merging) 0.5f else 1f
        mergeButton.text = if (hasPendingOutput()) "Retry save" else "Merge frames"
    }

    companion object { private const val REQUEST_WRITE_STORAGE = 1020 }
    private fun setStatus(message: String) { statusText.text = message }
    private fun appendStatus(message: String) { statusText.append("\n$message") }
}
