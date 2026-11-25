plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

// The HDRMerge Python sources live in ../python at the repository root. Copy
// them into a build directory and expose that directory as a Chaquopy source
// set, so a single source of truth feeds both the Python tests and the APK.
val pythonSourceDir: Provider<Directory> = layout.buildDirectory.dir("generated/python")
val copyPythonSource = tasks.register<Copy>("copyPythonSource") {
    from(rootProject.file("../python")) { include("*.py") }
    into(pythonSourceDir)
}
tasks.named("preBuild") { dependsOn(copyPythonSource) }

// CI signing: when the GitHub Actions workflow provides a keystore through
// environment variables, sign the release with it. Local builds without these
// variables keep the default (unsigned) release configuration.
val ciKeystore = System.getenv("ANDROID_KEYSTORE_FILE")

android {
    namespace = "com.hdrmerge.lite"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.hdrmerge.lite"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"

        ndk {
            // arm64-v8a covers current devices; x86_64 covers emulators.
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    signingConfigs {
        if (!ciKeystore.isNullOrEmpty()) {
            create("ciRelease") {
                storeFile = file(ciKeystore)
                storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("ANDROID_KEY_ALIAS")
                keyPassword = System.getenv("ANDROID_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            if (!ciKeystore.isNullOrEmpty()) {
                signingConfig = signingConfigs.getByName("ciRelease")
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

chaquopy {
    defaultConfig {
        // 3.11 supports both 32-bit and 64-bit ABIs, maximizing device coverage.
        version = "3.11"

        pip {
            // NumPy and SciPy are required by the processing core; tifffile reads
            // and writes the DNG files. These have Android builds on Chaquopy's
            // package index; if a native package is missing for the chosen Python
            // version, Chaquopy builds it from source (needs Python + NDK on the
            // build machine).
            install("numpy")
            install("scipy")
            install("tifffile")
            // xalglib is deliberately NOT installed: it has no Android ARM build.
            // hdrmerge_core falls back to the pure-NumPy port in alglib_compat.
            // imagecodecs is optional (tifffile only needs it for compressed
            // TIFFs; the merge output here is uncompressed), so it is omitted to
            // avoid an Android-only native build.
        }
    }

    sourceSets {
        getByName("main") {
            // Resolve to a path; the preBuild dependency above guarantees the
            // copy task has run before the Python sources are packaged.
            srcDir(copyPythonSource.map { it.destinationDir }.get())
        }
    }
}
