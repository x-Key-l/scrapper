# SceneTrace unified v5 integration

This is an integration candidate, not a verified Windows release.

## Provenance and reconciliation

Base: PR #4 tip `4396d04`; PR #5 tip `f939e4f`.

Base: PR #4 (`build/browser-downloads-v4.1`). PR #5 (`build/unrestricted-media`) was compared against the common 4.0 ancestor and against PR #4. The earlier branch tips remain untouched.

| Files / concern | Decision |
| --- | --- |
| `native/*`, library backend/UI, native downloads | Retain PR #4, including HaGeZi rules and license, WebView2 download operations, library callbacks, collision-safe names and persisted download state. |
| `media.py` | Retain PR #4 HTTP/HLS/DASH compatibility and sanitized diagnostics; import subtitle enumeration, bitrate ranking, and bounded fragment retries/concurrency. Keep DRM and unsupported transports excluded. |
| `downloads.py` | Import configurable safe filenames, subtitles, NFO sidecars, per-format extractor URLs and compatible remux optimization. Preserve native synchronization, source folders, pause/restart behavior and library registration. Do not overwrite existing sidecars. |
| `app.py` | Import validated subtitle selection and filename settings; sort actual formats. Existing organization preferences and routes remain. |
| `websites.py` | Import dynamic attribute/script discovery and limited iframe extraction; route manifests through analysis and retain their extractor URL/ID. Exclude segments. Preserve configured-origin checks, challenge diagnostics, custom selectors and bounded rendering. |
| `viewing.py`, `watch.js` | Include analyzer formats independently of in-app direct playback; subtitle selection. Keep official-player handoff and direct playback validation. Do not import PR #5's unbundled `window.Hls` player dependency. |
| `web/app.js` | Import sequential batch analysis/queueing, filename control and subtitle selector; retain PR #4 Download Center, Media Library and organization settings. Authorization confirmation accompanies media queueing. |
| `network.py` | Construct Host from validated hostname/port. Preserve private-network checks, TLS verification, cross-origin credential stripping and identifiable application user agent. |
| launcher, HTML, docs, workflow, tests | Keep PR #4's native integration and checks; add integration-specific tests and evidence. Do not carry forward historical PR #5 success claims as current evidence. |

Deliberately excluded: automatic cookie-profile loading, pretending every URL-bearing or DRM format is downloadable, silently selecting the first playlist item, challenge text becoming a success, and classifying raw `.ts`/`.m4s` fragments as complete videos. No authentication/DRM bypass is introduced.

## Browser changes

- Known advertising popups are blocked even when WebView2 reports a user gesture; player clicks no longer automatically exempt advertising destinations. Known advertising HTTP redirects are blocked. Per-site/global protection controls remain.
- Preserve legitimate popup opener relationships, native download dialogs and independent WebView2 transfers. Unknown ad domains and same-document script redirects remain imperfect; no Brave-equivalence claim.
- Install bounded, debounced observation in a DevTools isolated world in each frame. Media lifecycle events and DOM mutations capture delayed players. External WebView messaging and host objects remain disabled. Telemetry cannot invoke application commands.
- Player presence, observed playback, media response and analyzed format remain separate. Blob URLs and media segments are never invented as complete download URLs.
- Tab activation rechecks selection across awaits and snapshots tab enumeration. Popup deferrals are handled before asynchronous creation. Closed tabs can be restored with Ctrl+Shift+T or the browser menu; active native transfers retain their hidden tab.

## Verification in Codex Cloud

- PR #4 baseline: 106 tests passed.
- Integrated portable suite: 110 tests passed. Actual generated, authorized direct MP4, HLS, DASH and separate audio/video downloads complete through HTTP/yt-dlp and decode with FFmpeg. Conversion and range/rate-limit recovery also run.
- Chromium application UI: passed onboarding, import/search/save, navigation, library controls, desktop/mobile layout, and JavaScript-error checks.
- Portable observer: actual cross-origin delayed HTML5 playback; blob player-only state; fragment exclusion; idle deduplication passed.
- Source process smoke: startup, assets, duplicate launch, import/search/save, persistence, shutdown/restart.
- Native .NET 4.8 executable cross-compiled on Linux using SDK 8.0.428: zero warnings/errors. This is not a Windows execution or package verification.
- New Windows gates exercise dynamic cross-origin playback with the external bridge disabled, click-triggered ad popups, close/restore and repeated tab switching. Existing native file-button/redirect/pause-resume/cancel, library, public playback and packaged restart gates remain.

Reproduce portable checks from the checkout with `.venv/bin/python -m pytest -q`, `.venv/bin/python scripts/smoke.py`, and `PLAYWRIGHT_BROWSERS_PATH=/workspace/.cache/ms-playwright SCENETRACE_PYTHON=/workspace/scrapper/.venv/bin/python npm run test:ui`. Run `node scripts/detector-test.cjs` with the same environment for observer checks. Windows CI uses its installed Python and Playwright.

Library benchmark on this Cloud instance: 1,000 small metadata fixtures indexed in 2.182 s; unchanged reindex 0.165 s. This measures catalog work only, not video throughput or Windows performance.

## Remaining release gates

The environment proxy rejects `api.github.com`, `animepahe.ch`, and `hianime.ms` with CONNECT HTTP 403. Their additions were saved to the environment draft, not applied or published by the agent. Git fetch/push and public package downloads are separate capabilities from GitHub API access.

Neither target site's search, episode pages, playback, download controls nor authorized transfer has been verified in this run. A network denial establishes none of those site capabilities. Independently authorized public-provider tests and Windows ZIP verification remain pending Actions execution and inspection. Controlled generated media tests do not substitute for those public tests.

Do not mark this candidate release-ready until Windows build/package/native checks and the other required gates pass on this exact commit. No Windows ZIP is presented as verified yet. Older-laptop CPU/RSS, five live tabs, native detection/filter overhead, high DPI, long transfers and sleep/wake need actual Windows measurements/owner checks. Existing measurement harnesses produce evidence; no throughput claims are inferred from short local fixtures.
