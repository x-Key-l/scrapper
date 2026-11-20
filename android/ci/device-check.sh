#!/usr/bin/env bash
# Install the same signed APK that was uploaded, then check AndroidJUnitRunner's result.
set -euo pipefail
reports=app/build/device-check
mkdir -p "$reports"
trap 'adb logcat -d -t 2500 > "$reports/logcat.txt" || true' EXIT
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb install -r app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb shell am instrument -w dev.scenetrace.browser.test/androidx.test.runner.AndroidJUnitRunner | tee "$reports/instrumentation.txt"
# Activity Manager may exit zero even if a test fails or its process dies.
grep -Eq '^OK \([1-9][0-9]* tests?\)' "$reports/instrumentation.txt"
