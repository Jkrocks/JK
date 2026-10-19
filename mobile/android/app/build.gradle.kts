plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "ai.tejas.app"
    compileSdk = 34

    defaultConfig {
        applicationId = "ai.tejas.app"
        minSdk = 29
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"
    }
    buildTypes {
        release {
            isMinifyEnabled = false
            // Signed with the debug key so families can install it straight away.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    // The pairing screen is shared with the iOS app.
    sourceSets["main"].assets.srcDirs("src/main/assets", "../../shared")
}
