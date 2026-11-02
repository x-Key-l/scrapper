# Verification

Run **python -m pytest -q** for functional tests covering imports, rollback, FTS5, memory evidence, identifiers, deduplication, failure isolation, cache reuse, credentials/Windows DPAPI, actual local HTTP operations, URL attacks, download recovery, collision/disk handling and normalization.

The media-pipeline tests create a real 0.5-second video, serve it over a controlled HTTP fixture, download it, convert with actual FFmpeg and decode the outputs. They launch the actual yt-dlp worker through the validating proxy. Only that test's fixture hostname receives a scoped DNS override; production URL validation has no override.

**python scripts/smoke.py** tests a separate application process: assets, dynamic port, repeated launches, HTTP import, memory retrieval, saving, diagnostics, persistence, shutdown and restart.

**python scripts/smoke.py --exe dist/SceneTrace/SceneTrace.exe** repeats that test against the actual packaged executable and bundled runtime/assets.

**npm run test:ui** uses real Chromium for onboarding, navigation, CSV import, field mapping, local memory search, detail/saved views, filtering, JavaScript errors and desktop/mobile layout.

**python scripts/live_check.py** performs unmocked public-source checks. The resulting live-results.json distinguishes verified responses, failures and optional missing credentials. Archive media checks sample actual bytes; they do not claim an entire large movie was downloaded. Controlled fixtures never count as public-provider verification.

## Release gate

GitHub Actions must pass source tests on Ubuntu and Windows, source-process smoke, Windows build, packaged executable smoke and Chromium tests. Provider checks are recorded independently so outages are reported honestly. The ZIP includes that report and a build manifest.

## Owner acceptance still needed

- Double-click opening the owner's configured default browser.
- Native folder/file dialogs on a normal Windows desktop.
- Long transfers, sleep/wake and network changes on the owner's network.
- Antivirus/SmartScreen behavior and performance on modest hardware.

The first Windows package is a release candidate, not a claim of completed manual acceptance.
