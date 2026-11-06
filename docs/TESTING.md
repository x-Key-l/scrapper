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

## 4.0 browser, search and history gates

- `python scripts/v4_live_check.py`: actual HiAnime Naruto and W3Schools capability checks, plus live catalog evidence. Public failures remain visible in the report.
- `python scripts/windows_browser_check.py`: launch the real packaged native application twice, verify isolation, tabs/back/forward/find/reload, error and renderer-crash recovery, actual video frames, bookmarks and saved/history persistence.
- `python scripts/evaluate_deep.py --baseline baseline/scenetrace/search.py`: eleven fixed queries with live empty-index retrieval and identical-corpus old/new ranking; baseline must be the pinned 3.0 revision. Top-five/top-ten metrics are not general accuracy claims.
- `python scripts/v4_audit.py --root PATH --skip-website`: source backend readiness, RSS and local queries. `node scripts/browser_benchmark.cjs` measures a fresh installed Edge context for the v3 baseline. Native packaged measurements are recorded separately.
- `tests/test_history.py` covers stable-ID migration, individual/bulk deletion, undo, retention, recording disabled and persistence. `tests/test_deep.py` covers exact/alternative/fuzzy titles, cast/character evidence, soft date clues, FTS recall and progressive cancellation.

See V4-AUDIT.md for measured outcomes and precise limitations. A source's successful search does not establish its playback or download compatibility.

## 4.1 transfer, detector, shield and media-library gates

- Python tests include actual unencrypted HLS/DASH fragments, media processing, native host API authentication, completion-file validation, conservative episode matching, bulk-edit validation, source folders, collision-safe file moves and restart persistence.
- The packaged native check uses public MP4/PDF buttons and a throttled real HTTPS ZIP fixture. The fixture creates a short-lived certificate in the disposable CI user's trust store and removes it at exit. No production certificate or URL-validation bypass is used.
- Controlled native checks exercise progress, pause/resume, cancellation, a new retry, redirects, popup/opener behavior and closing a transferring tab. Final ZIP hashes must match the served bytes.
- Detector checks connect a real HTML5/network MP4 to extraction, file completion and Media Library indexing. Shield checks exercise ad requests, popup classification, allowlisting, media exemptions and a maintained-list update attempt. Update failure is reported without discarding prior rules.
- UI tests import a folder, edit metadata, select and move files, and check unchanged bytes. These catalog fixture files are not presented as playback evidence.
- `python scripts/library_benchmark.py` records initial and unchanged indexing for 1,000 small files; it does not measure video decoding.
