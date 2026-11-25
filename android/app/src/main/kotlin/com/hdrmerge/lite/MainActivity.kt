package com.hdrmerge.lite

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.ProgressBar
import android.widget.Spinner
import android.widget.TextView
import java.io.File
import java.util.concurrent.Executors

/**
 * UI for the HDRMerge Lite app.
 *
 * Flow: pick three DNGs (copied into the app's private files dir), tap Merge
 * (runs the Python core on a background thread), then Save to choose a
 * destination for the merged DNG. All Python interaction is delegated to
 * [HdrMergeEngine].
 */
class MainActivity : Activity() {

    private lateinit var engine: HdrMergeEngine
    private lateinit var statusText: TextView
    private lateinit var progressBar: ProgressBar
    private lateinit var mergeButton: Button
    private lateinit var saveButton: Button
    private lateinit var radiusEdit: EditText
    private lateinit var bitsSpinner: Spinner

    private val executor = Executors.newSingleThreadExecutor()
    private val mainHandler = Handler(Looper.getMainLooper())

    private val inputDir = File(filesDir, "inputs")
    private val outputDir = File(filesDir, "output")
    private val outputFile = File(outputDir, "merged.dng")

    private val inputFiles = listOf(
        File(inputDir, "exposure_1.dng"),
        File(inputDir, "exposure_2.dng"),
        File(inputDir, "exposure_3.dng"),
    )
    private val inputLabels = listOf<TextView?>(null, null, null)

    private var merging = false

    private val progressSink = object : HdrMergeEngine.ProgressSink {
        override fun onProgress(message: String) {
            mainHandler.post { appendStatus(message) }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        engine = HdrMergeEngine(this)
        setContentView(R.layout.activity_main)

        statusText = findViewById(R.id.statusText)
        progressBar = findViewById(R.id.progressBar)
        mergeButton = findViewById(R.id.mergeButton)
        saveButton = findViewById(R.id.saveButton)
        radiusEdit = findViewById(R.id.radiusEdit)
        bitsSpinner = findViewById(R.id.bitsSpinner)

        inputLabels[0] = findViewById(R.id.shortLabel)
        inputLabels[1] = findViewById(R.id.mediumLabel)
        inputLabels[2] = findViewById(R.id.longLabel)

        bitsSpinner.adapter = ArrayAdapter(
            this, android.R.layout.simple_spinner_dropdown_item, listOf("16", "32"))

        findViewById<Button>(R.id.pickShort).setOnClickListener {
            DngFiles.pick(this, DngFiles.RC_PICK_SHORT)
        }
        findViewById<Button>(R.id.pickMedium).setOnClickListener {
            DngFiles.pick(this, DngFiles.RC_PICK_MEDIUM)
        }
        findViewById<Button>(R.id.pickLong).setOnClickListener {
            DngFiles.pick(this, DngFiles.RC_PICK_LONG)
        }

        mergeButton.setOnClickListener { startMerge() }
        saveButton.setOnClickListener {
            if (outputFile.exists()) {
                DngFiles.createDocument(this, "hdrmerge_merged.dng", DngFiles.RC_SAVE)
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        executor.shutdownNow()
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (resultCode != Activity.RESULT_OK || data?.data == null) return
        val uri = data.data!!

        when (requestCode) {
            DngFiles.RC_PICK_SHORT, DngFiles.RC_PICK_MEDIUM, DngFiles.RC_PICK_LONG -> {
                val index = when (requestCode) {
                    DngFiles.RC_PICK_SHORT -> 0
                    DngFiles.RC_PICK_MEDIUM -> 1
                    else -> 2
                }
                if (DngFiles.copyUriToFile(this, uri, inputFiles[index])) {
                    inputLabels[index]?.text = uri.lastPathSegment ?: inputFiles[index].name
                    setStatus("Loaded exposure ${index + 1}: ${inputFiles[index].name}")
                } else {
                    setStatus("Could not read the selected file. Try again.")
                }
            }
            DngFiles.RC_SAVE -> {
                if (DngFiles.copyFileToUri(this, outputFile, uri)) {
                    setStatus("Saved merged DNG to ${uri.lastPathSegment}")
                } else {
                    setStatus("Could not write the output file. Try again.")
                }
            }
        }
    }

    private fun startMerge() {
        if (merging) return
        val present = inputFiles.filter { it.exists() }
        if (present.size != 3) {
            setStatus("Please pick all three DNG exposures first.")
            return
        }
        val radius = radiusEdit.text.toString().toIntOrNull()
        if (radius == null || radius < 0 || radius > 64) {
            setStatus("Feather radius must be a number between 0 and 64.")
            return
        }
        val bits = if (bitsSpinner.selectedItemPosition == 0) 16 else 32
        val align = findViewById<CheckBox>(R.id.alignCheck).isChecked

        outputDir.mkdirs()
        if (outputFile.exists()) outputFile.delete()

        setMerging(true)
        setStatus("Merging…")
        executor.execute {
            try {
                val written = engine.merge(
                    inputs = inputFiles.map { it.absolutePath },
                    outputPath = outputFile.absolutePath,
                    align = align,
                    radius = radius,
                    bits = bits,
                    progress = progressSink,
                )
                mainHandler.post {
                    setMerging(false)
                    saveButton.isEnabled = true
                    setStatus("Merge complete. Output: ${written}")
                }
            } catch (e: Throwable) {
                mainHandler.post {
                    setMerging(false)
                    saveButton.isEnabled = false
                    setStatus("Merge failed: ${e.message ?: e.toString()}")
                }
            }
        }
    }

    private fun setMerging(value: Boolean) {
        merging = value
        mergeButton.isEnabled = !value
        saveButton.isEnabled = !value && outputFile.exists()
        progressBar.visibility = if (value) View.VISIBLE else View.GONE
        findViewById<Button>(R.id.pickShort).isEnabled = !value
        findViewById<Button>(R.id.pickMedium).isEnabled = !value
        findViewById<Button>(R.id.pickLong).isEnabled = !value
    }

    private fun setStatus(message: String) {
        statusText.text = message
    }

    private fun appendStatus(message: String) {
        statusText.append("\n$message")
    }
}
