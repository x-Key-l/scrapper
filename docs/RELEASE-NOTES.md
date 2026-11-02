# SceneTrace 2.0 Windows release candidate

Download SceneTrace-Windows-x64.zip, extract the entire archive and double-click SceneTrace.exe. Keep its _internal folder together with it. No Python or Node installation is needed.

Adds the Database Hub, source configuration, file/SQLite/feed importing with field mapping, federated search, FTS5 memory retrieval with evidence, separate media resolution, yt-dlp analysis, a persistent download queue with HTTP resume, FFmpeg conversion and a redesigned responsive interface.

Release gates: functional source tests on Windows/Linux, actual packaged executable HTTP smoke and real Chromium workflow. The ZIP contains docs/live-results.json with actual provider results; optional credentials are not supplied.

Limits: provider availability varies; arbitrary websites are not automatic APIs; memory matching needs relevant metadata; downloads support reported HTTP(S) files, without HLS/DASH, DRM or separate-stream pairing. Native Windows desktop interactions and modest-hardware performance still need owner acceptance. See README.md and docs/HELP.md.
