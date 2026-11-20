# SceneTrace for Android

Phase 1 is a standalone Kotlin browser for Android 10 through Android 15 (minimum API 29, target API 35). It uses the device's Android System WebView. No desktop process, local HTTP application server, account or Python installation is needed.

## Install the debug build

1. Open [Android build and WebView checks](https://github.com/x-Key-l/scrapper/actions/workflows/android-build.yml) and select a successful run on `codex/scenetrace-android`. Open the artifact **SceneTrace-Android-debug**. GitHub requires sign-in to download workflow artifacts.
2. Extract `app-debug.apk` from the ZIP, copy it to your phone and open it from Files. If Android prompts for permission, allow that file manager to install unknown apps, install SceneTrace, then turn the permission off.
3. With USB debugging enabled, you can instead run `adb install -r app-debug.apk`. Open **SceneTrace** from the launcher. Debug signing keys can differ between CI runs and local builds. If Android reports a signature mismatch, replacing the existing installation requires uninstalling it first, which erases private browser data.

## Browse

Enter an HTTP(S) address or search in the address bar. The arrows move within the current tab. The tab count opens the tab switcher, including close and restore controls. Android Back dismisses panels or address editing, moves back through the page stack, then closes the tab or returns to the start page. The menu contains bookmarks, history, external browser handoff and settings. The shield toggles global filtering or allows the exact current hostname. Settings also selects the search provider.

Use a site's ordinary download link, long-press a link or image, or select **Download current URL** for an inline file. Confirm the suggested name and source. The download arrow opens transfer status, byte counts and cancellation. Tap a saved file to open it with an installed handler. Files are placed in **Downloads/SceneTrace**. The first release supports direct GET downloads, including ordinary HTTP redirects. Sites requiring a POST body, cookie-authenticated transfer, blob URL, client-generated data, DRM or media extraction may require another client. DownloadManager does not receive page cookies or Authorization headers. Sharing these with a downloader that follows redirects would require additional credential scoping.

## Build and test

Install JDK 17, Android SDK Platform 35, Build Tools 34.0.0 and Platform Tools. Point `ANDROID_HOME` at the SDK, or set `sdk.dir` in an untracked `android/local.properties`. From the repository root run:

```sh
cd android
./gradlew testDebugUnitTest assembleDebug assembleDebugAndroidTest
adb install -r app/build/outputs/apk/debug/app-debug.apk
./gradlew connectedDebugAndroidTest
```

On Windows use `gradlew.bat`. The last command needs an unlocked emulator or device with WebView installed. Instrumentation uses its own loopback HTTP fixture. Run these checks on a test device because they reset the installed debug app's browser data and download records. The JVM suite covers address resolution, domain matching, collision-safe names and the tab model. Device tests exercise the Activity, actual WebView navigation and system downloads. The dedicated Actions workflow builds a signed debug APK, uploads it, then boots an Android 15 emulator and runs instrumentation.

## Porting decisions

The baseline is unified v5 commit `77a5798`. Its integration notes, native tab controls, shield, download callbacks, Python store and transfer service, desktop web interface, fixture tests and Windows workflows informed the port. The S-arrow mark and mint accent follow the Windows identity. The Android APK bundles a decoded copy of the same HaGeZi Light snapshot and its license from `native/Filters/`. CI compares both against that source.

| Concern | Android implementation and boundary |
| --- | --- |
| Browser and chrome | An AndroidX ComponentActivity owns native Views, touch controls and a compact bottom toolbar. Remote pages run only inside WebView. Page code has no JavaScript bridge, filesystem access or app command channel. TLS errors use WebView's default rejection. Direct HTTP navigation is supported. |
| Tabs and lifecycle | Stable tab IDs separate session state from WebView ownership. Keep up to three live renderers' views, pause and detach background views, snapshot independent back/forward lists before eviction and destroy unused views. Memory pressure reduces the pool to the selected view. Keep at most 24 navigation snapshots of up to 512 KiB each. Tab URLs, titles, selection and the last 12 closes survive process death. Full navigation stacks and unsaved page forms are best effort across eviction and are lost after process death. Rotation retains the current Activity and WebViews. Renderer loss offers a manual reload. |
| History and settings | App-private SQLite stores bookmarks, the 500 most recently visited distinct URLs and transfer records. SharedPreferences persists the tab list, allowlist and browser settings. App backup is disabled. |
| Protection | Supported WebView callbacks filter known hostnames and subdomains, gesture-free popups and identifiable redirects. The initiating tab's settings govern popup decisions. Explicit popup links open as independent GET tabs. Script-only blank windows, popup POSTs and flows requiring a live opener are limited. Same-origin ads, service-worker traffic and all redirect hops are outside the guaranteed coverage of these hooks. The filter snapshot ships with the app. |
| Downloads | WebView's download listener prompts before a native DownloadManager request. Android owns network I/O, retry and scoped public storage. Closing tabs and restarting the Activity do not cancel transfers. DownloadManager status, readable file descriptor and saved byte length determine completion. The app preserves cancelled records and labels removed files unavailable. Choosing API 29 as the minimum permits saving to public Downloads without legacy storage permissions. |
| Next phase | BrowserViews owns web callbacks, BrowserStore owns local state and Transfers owns direct downloads. A future media observer, analyzer, queue and catalog can be integrated at these boundaries. The desktop MediaObserver, Python HTTP service, yt-dlp, FFmpeg and desktop HTML shell are outside this build. |

For physical-device acceptance, check Android 15 gesture and button navigation, rotation with an active form, a real site under network loss, a long background transfer, low-memory tab eviction and your chosen external file viewer. OEM power policies, WebView versions, available storage and installed handlers can affect these paths.
