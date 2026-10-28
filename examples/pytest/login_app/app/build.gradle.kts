plugins {
  alias(libs.plugins.android.application)
}

android {
    namespace = "com.example.geppettologindemo"
    compileSdk = 36
    defaultConfig {
        applicationId = "com.example.geppettologindemo"
        minSdk = 24
        targetSdk = 28
        versionCode = 1
        versionName = "1.0"
    }

}
