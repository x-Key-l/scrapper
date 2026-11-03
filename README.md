# SceneTrace

A local Windows-first workspace for searching connected video catalogs, identifying possible titles from memories, locating source media and downloading authorized files.

## Windows: start here

1. Open [Releases](https://github.com/x-Key-l/scrapper/releases).
2. Download **SceneTrace-Windows-x64.zip**.
3. Right-click the ZIP and choose **Extract All**.
4. Open the extracted **SceneTrace** folder.
5. Double-click **SceneTrace.exe**. The interface opens in your default browser.

Keep the complete folder, including **_internal**, together. Python, Node.js, FFmpeg, Git and Docker do not need to be installed. Windows 10/11 x64 is the target.

The first package is a **release candidate**, pending owner acceptance. The release workflow must launch the actual packaged executable and exercise its local HTTP endpoint; compiling source alone is insufficient.

Double-clicking again reopens the existing instance. Use **Quit SceneTrace** to stop it. Closing only the browser tab keeps the local service and downloads running.

## Features

- **Database Hub:** source types, authentication, enable/disable, real connection tests, independent refresh and health. Built-in adapters: TVmaze, AniList, Internet Archive, Wikimedia Commons, PeerTube/Sepia Search and optional TMDB.
- **Your sources:** configurable REST JSON and GraphQL APIs, RSS/Atom/Media RSS, CSV/TSV, JSON/JSONL and ordinary SQLite tables. Preview data and visually map fields.
- **Universal Search:** parallel queries, isolated provider failures, selection, pagination, caching, category filters, source provenance and strong-ID deduplication.
- **Memory Search:** SQLite FTS5, clue extraction/expansion, optional refinement, genre browsing where supported and local ranking with actual matching evidence. No paid AI dependency or fabricated confidence probabilities.
- **Find Video:** separate media/hybrid-source search using titles and alternative names. Trailers/clips are labeled; full-length claims remain unconfirmed.
- **Link Analyzer:** official Archive/Commons metadata plus yt-dlp for supported public pages; formats come from source responses.
- **Download Center:** source quality/format, destination, persistent queue, bytes/progress/speed/ETA, pause/cancel/retry, validated HTTP resume, collision handling, disk checks and bundled FFmpeg MP4/MP3 conversion.
- **Saved Library:** persistent local metadata, offline access and JSON export.
- **Settings:** optional discovery key, destination, cache/history controls and sanitized diagnostics.

## First use

Open Universal Search, enter a title/topic and select sources. **Verified** means a successful request from this installation; **Untested** is not a compatibility claim. Source availability can change.

Open Details, then **Find Video** to search connected media sources. Analyze the actual source link for current formats. A metadata record does not prove the full video is online.

Optional: TMDB needs your API Read Access Token. Wider Find More Sources web discovery needs an optional Brave Search key; curated documented suggestions and a manual web search work without one.

Credentials use Windows DPAPI, tied to the current Windows user. On other operating systems the settings folder is user-restricted but credentials are not encrypted by SceneTrace. Keep credentials in the credential box, not endpoint URLs. Queries go to selected providers; saved data stays on this PC.

Read [Help](docs/HELP.md), [Connector configuration](docs/CONNECTORS.md), [Audit](docs/AUDIT.md) and [Testing](docs/TESTING.md).

## Practical limits

- Modularity does not mean every website is supported or every title is indexed. An arbitrary website is not assumed to be an API.
- Memory retrieval needs relevant catalog descriptions. Title-only APIs cannot answer every plot paragraph. No semantic model or AI reranker is bundled.
- Generic downloads support provider-reported HTTP(S) files. HLS/DASH, live streams, DRM, paywalls, restricted accounts, age-gated access and automatic separate audio/video pairing are unsupported. Video-only and audio-only files are labeled. There is no fixed quality, file-size or source-count cap.
- Preview depends on source availability and browser codecs. Use the official viewing link when it fails.
- Refresh updates a recent query cache or reindexes a local export; compatible custom APIs can use an incremental timestamp parameter. There is no unrestricted crawler.
- Large CSV, JSONL and SQLite imports stream through the native picker. JSON arrays use a memory guard; convert huge arrays to CSV/JSONL/SQLite. Malformed imports roll back atomically.
- This is a local PC app, not a hosted multi-device service. The executable is unsigned. Native dialogs, owner-browser launch, antivirus behavior and low-spec performance still need owner-machine acceptance.

## Development only

Python 3.12:

~~~sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
python scripts/smoke.py
python -m scenetrace
~~~

Browser QA uses Node only during development:

~~~sh
npm ci
npx playwright install chromium --only-shell
npm run test:ui
~~~

Build on Windows:

~~~sh
python scripts/build.py
python scripts/smoke.py --exe dist/SceneTrace/SceneTrace.exe
python scripts/live_check.py
python scripts/package_release.py
~~~

CI stores actual provider evidence in live-results.json, separately from controlled fixtures. Both OS test jobs and browser verification gate the main-branch prerelease.

Data: %LOCALAPPDATA%\SceneTrace. Default downloads: Downloads/SceneTrace. SCENETRACE_DATA overrides the state directory for tests. Back up the state directory while the app is closed; program-folder updates preserve this data.
