# SceneTrace 4.0 audit and verification

## Foundation and reproduced defects

The original source, simplified PC archive and Anine reference were inspected in the earlier [archive audit](AUDIT.md). Their useful download/security lessons were retained in the existing Python/SQLite application. This work continues main commit `5383d468d3ce0fe2c21e2b86f80636399707869b` (3.0 RC29), on `build/intelligent-browser-v4`. That baseline and release are preserved. No Anine code or artwork is redistributed.

The original 3.0 source passed 78 automated tests before changes. Its actual HiAnime GET form generated the correct `/search?q=Naruto`, but result selectors omitted `/details/`. The response contained public static result cards; a search-form response alone had been treated as sufficient configuration. The detail page also exposed numbered episode links the generic parser missed.

The original history model had no complete individual/bulk deletion and undo flow. Memory ranking relied largely on literal tokens; exact titles could lose to numbered films after stopword removal. Actor/character relationships and progressive search were missing. State refreshes could replace a newly saved source with an older concurrent response. A wizard response could also apply to configuration edited while its test was running. These races and the parser/ranking problems now have targeted repairs.

Apple's movie search returned empty live responses for the attempted actor and description queries. It is not shipped as a verified integration. Wikipedia full-text plus explicit Wikidata relationships supplies an alternative, alongside optional TMDB filmography retrieval.

## Architecture and security

The existing loopback Python server, SQLite FTS5 store, static frontend, media resolver and download queue remain. Windows adds a small .NET Framework 4.8 WinForms host using WebView2 Evergreen. It reuses the installed runtime; no Electron or bundled Chromium. One WebView2 environment serves separate application and website profiles. Tabs initialize on selection, retain navigation and attempt suspension when hidden. Closing tabs disposes their controls.

Only the exact application origin has the restricted native message bridge. External websites cannot post native messages or use host objects. Native backend calls use a process-specific secret. Loopback APIs enforce host/origin/header rules, and external browser requests to local addresses are blocked. Imported connector configurations remain data. API extraction retains pinned public-network requests, redirect/address validation, TLS verification, request limits and timeouts. Browser automation does not bypass challenge pages.

Windows HTTPS uses the Windows trust store through truststore, preserving hostname validation. A certificate rejection produces actionable diagnostics, not a verification-disable switch. Optional TMDB credentials are clearly separate from failed video-source connections.

History uses stable IDs and transactional deletion; undo tokens expire after 60 seconds. Tests cover migration, persistence, selection, retention, recording disabled and separation from saved data. Bounded search sessions stream per-source results, preserve received results on cancellation, cache provider queries and report individual failures. Cache keys exclude changing health timestamps, so a source status update does not invalidate reusable results. No embedding model is downloaded automatically.

## Live viewing checks

The [passing Windows/package and browser run](https://github.com/x-Key-l/scrapper/actions/runs/41894427797) tested the following on 4 November 2026. Recheck the JSON reports bundled with a release for its latest requests.

| Source | Search | Pages / episodes | Playback | Download |
| --- | --- | --- | --- | --- |
| HiAnime | 27 Naruto results | 220 ordered Naruto episode URLs | Exact source-page handoff; actual player unverified | No eligible path found |
| W3Schools HTML Video | One listing result through Add Website | Exact public video page | Native WebView2 and SceneTrace direct video frames advanced | 4.0 withheld this file; current branch offers direct downloads (live retest pending) |
| Caminandes / Commons | Title and aliases | Three episodes | Actual Llamigos playback in packaged app | 6,564,631 bytes completed and FFmpeg decoded |
| Official Pokémon TV | Pocket Monsters alias | First three Indigo League episodes | Exact publisher handoff verified; embedded frames unverified | Publisher playback only |

The downloaded Caminandes test file SHA-256 was `dc430b910525915fa72081f11962d7758d028cd8c0b5742cce77a31f343ee88b`. This is one genuine licensed transfer, not a guarantee for every source or long interrupted network transfer.

HiAnime's exact tested first episode is `https://hianime.ms/watch-naruto-episode-1-e0a2e`. Public HTML yielded the title and episode lists without JavaScript. The source did not expose a verified eligible file or official embeddable player in this test. Normal browser navigation remains available; third-party player compatibility and content rights are independent. No protected player, authentication or anti-bot mechanism was bypassed.

## Deep Search evaluation

The fixed evaluation has eleven known-answer examples: exact title, typo, Japanese title, incomplete title, named character, appearance, actor/setting, partial plot, ambiguous scene, wrong period and combined clues. Each live case starts with an empty local index. A separate comparison runs old/new ranking over the same real candidates collected from those cases. It is a small curated regression set, not general-purpose accuracy.

The 5 November 2026 live run found the expected title in the top five and top ten for **10 of 11 cases**. On identical provider candidates, v3 ranked **7 of 11** in each cutoff and v4 ranked **10 of 11**. Live case latency was **0.714–5.857 seconds**, excluding subsequent video-website resolution. The white-haired teacher query identified **Naruto universe** first, but the exact Naruto catalog entry ranked 29th; this case remains a miss under the fixed scoring rule. No answer was renamed or silently counted as correct.

The latest retained evaluation and exact case ranks are in [deep-evaluation.json](deep-evaluation.json). Results and candidate coverage are reported separately. Optional TMDB actor lookup is implemented but live token-dependent filmography has not been verified without owner credentials. Metadata results do not count as available videos.

## Performance measurements

[Paired backend run](https://github.com/x-Key-l/scrapper/actions/runs/41981916036), shared Windows runner, same machine for v3 and v4 source processes:

| Measurement | v3 fresh / warm | v4 fresh / warm |
| --- | --- | --- |
| Backend ready | 1.648 / 0.595 s | 0.748 / 0.399 s |
| Backend RSS | 33.70 / 32.56 MiB | 34.07 / 32.88 MiB |
| Local Quick query | 0.364 / 0.298 s | 0.268 / 0.203 s |
| Local memory query | 1.192 / 0.280 s | 0.224 / 0.229 s |

These local queries are not live multi-provider Deep Search. Idle frontend state refresh is reduced to ten seconds outside downloads/source activity. No source-size or throughput improvement is inferred from this small sample.

Actual packaged WebView2 run `41894427797`:

| Native browser measurement | Fresh profile | Existing profile |
| --- | --- | --- |
| Browser app ready (separate native clock) | 13.491 s | 1.312 s |
| App host + WebView2 RSS | 335.30 MiB | 319.97 MiB |
| One small website tab | 436.43 MiB | 418.52 MiB |
| Five website tabs, four inactive | 507.21 MiB | 479.77 MiB |
| After real website playback | 636.46 MiB | 588.19 MiB |
| Separate packaged backend RSS | 40.55 MiB | 40.29 MiB |

Five website tabs plus the application allocated only three WebView controls (two visited website tabs, three not yet loaded). Cumulative browser/host CPU was 2.25 s at app-ready and 7.61 s after playback in the fresh run; these are process CPU totals, not CPU utilization percentages. Native tests also measured process counts and recovery. Raw reports accompany the package.

For context, v3 in a fresh system Edge instance measured 3.196 s browser-ready, 399.77 MiB app-only, 652.70 MiB with a playing W3Schools tab and 836.36 MiB with four extra blank tabs. That uses a different runner/run and page activity from the native fixture stages. It is **not a controlled percentage-speedup comparison**. An earlier benchmark accidentally used separate browser contexts for each blank tab; it was corrected before reporting these figures. Fresh runtime initialization remains a noticeable cost, and older PCs require owner testing.

## Release verification and limits

Automated tests include real local HTTP transfers and actual FFmpeg/yt-dlp execution. Windows CI additionally launches the packaged executable, verifies profile migration/restart, navigates WebView2, tests back/forward/reload/find, lazy tabs, bookmarks, failed navigation, an actual renderer crash/recovery, local API isolation and real video frames. Browser E2E covers adding and searching a website, exact episode handoff, direct playback and history deletion/undo. Screenshots are captured from running applications.

Local verification: 90 full-suite tests passed, followed by the partial-source and health-independent cache regressions passing in the affected subsets. Final CI reports contain the complete 92-test run.

The release ZIP includes `BUILD.json`, provider and viewing reports, native cold/warm results and this audit. Source-provider reports may record outages without failing unrelated sources; build, local functional, native and real viewing gates must pass before publication.

Owner acceptance still needed: older hardware, antivirus/SmartScreen, missing-runtime installation, native folder dialogs, sleep/wake and long transfers on the owner's network. The app is unsigned. The current branch expands enumeration to extractor-supported HLS/DASH and direct files. DRM formats are listed but not decrypted. Exhaustive anime availability and universal scene recognition remain unverified. Viewing pages remain accessible when analysis cannot return formats. The earlier Windows evidence above applies to 4.0, not this development branch.


## Pre-fix baseline — unrestricted-media

Base: `ce10f96105e88c421c205cdf8fc9485319951307`. Live attempts from the development environment; no browser-cookie profile was available. The YouTube URL is the age-gated Witcher trailer fixture documented in yt-dlp. Network failures below do not establish source incompatibility.

```text
$ python -m scenetrace --check-runtime
{"yt_dlp": "2026.10.26", "ffmpeg": "ffmpeg version 7.0.2-static https://johnvansickle.com/ffmpeg/  Copyright (c) 2000-2024 the FFmpeg developers"}

[
  {
    "url": "https://hlsjs.video-dev.org/demo/?src=https%3A%2F%2Ftest-streams.mux.dev%2Fx36xhzz%2Fx36xhzz.m3u8",
    "seconds": 0.0,
    "error": "The public hostname could not be safely resolved."
  },
  {
    "url": "https://www.w3schools.com/html/html5_video.asp",
    "seconds": 0.0,
    "error": "The public hostname could not be safely resolved."
  },
  {
    "url": "https://www.youtube.com/watch?v=HtVdAasjOgU",
    "seconds": 0.0,
    "error": "The public hostname could not be safely resolved."
  }
]
```

## Current media branch verification

Phases 4.1–4.11 expand media formats, website detection, official-page analysis, diagnostics, HLS player integration, batch queueing, subtitle selection and sidecars. Syntax checks pass. Initial functional run: 89 passed, 3 failed; two changed contracts and one real merge regression. Final regression results are recorded below when available. Public-network and cross-origin credential protections remain enabled. No source-side account, challenge or encryption mechanism is removed.

### Final source regression evidence

- `python -m pytest -q`: **110 passed in 29.49 seconds** on Linux.
- Real local HLS and DASH: HTML discovery → yt-dlp format selection → downloaded bytes → successful FFmpeg decode. NFO sidecars created. These fixtures use a test-only hostname mapping; production private-network validation remains intact.
- Real separate audio/video merge regression passes after limiting `allow_unplayable_formats` to analysis.
- Existing range resume, interruption, retry, collision and persistence tests pass.
- DRM enumeration and exact failure wording tested with controlled extractor/worker fixtures, not a live protected title.
- `--check-runtime`: yt-dlp 2026.10.26; system Linux FFmpeg 7.1.5. The bundled Linux FFmpeg 7.0.2 crashed with exit -11 during HLS postprocessing; Linux now prefers system FFmpeg when installed. Windows retains the bundled binary.
- Python compile checks and both edited JavaScript syntax checks pass. Required Python dependencies unchanged.
- Local browser test blocked: system Chromium exits at startup because the environment denies its process-singleton socket. HLS CDN loading, player interaction and batch UI remain browser-unverified here.
- Live external HLS/MP4/YouTube retests blocked by public DNS resolution. No user browser-cookie profile is available. Cloudflare challenge completion and a live DRM title are not verified.
- Exact-host/subdomain matching is supported. Full public-suffix-aware registrable-domain equivalence is not implemented because no maintained suffix database is bundled.
- Localhost/private targets and cross-origin credential forwarding remain blocked to preserve local API and credential isolation. Geo restriction evasion and third-party plugin/script execution are not enabled.

### Phase commits

| Phase | Commit | Files | Behavior / test delta |
|---|---|---|---|
| 4.0 | a5253bc | docs/V4-AUDIT.md | Runtime and three-URL pre-fix transcript; network failures recorded |
| 4.1 | 7fab623 | media.py | Stream extensions; syntax checked |
| 4.2 | abe4e1d | media.py | Protocol-neutral format enumeration; syntax checked |
| 4.3 | dc163f7 | media.py, downloads.py | Extractor retries, headers and explicit cookie source; syntax checked |
| 4.4 | 9f37f09 | media.py | Restriction metadata and first playlist entry; syntax checked |
| 4.5 | a15e635 | network.py | Browser UA and normalized Host; isolation retained |
| 4.6 | 5aed66b | websites.py | Structured/script media detection and manifest analysis; syntax checked |
| 4.7 | 95e4919 | viewing.py | Official pages reach analyzer; syntax checked |
| 4.8 | 2c5b440 | downloads.py, app.py | Checkbox gate removed; stderr and optional remux; syntax checked |
| 4.9 | 8ea508e | media.py, downloads.py | DRM listing and exact failure; initial suite started |
| 4.10 | 818a83c | web/app.js, web/watch.js, web/index.html, __main__.py | Optional HLS player and informational checkbox; JS checks pass |
| 4.11 | bbb61a9 | media.py, downloads.py, app.py, viewing.py, web/app.js, web/watch.js | Batch queue, sorting, subtitles, template, NFO; syntax checks pass |
| 4.12 | bd97f85 | README.md, docs/HELP.md, docs/V4-AUDIT.md | Capability and verification wording corrected |
| 4.13 | This commit | Media/app/download/viewing/website fixes; tests/test_core.py, tests/test_website_v4.py, tests/test_media_pipeline.py, tests/test_media_contracts.py; this audit | 110 tests pass; 18 added cases; consent/restriction expectations updated; actual merge and manifest transfers preserved |

### Windows follow-up, 12 November 2026

[Windows verification job](https://github.com/x-Key-l/scrapper/actions/runs/43033165535/job/130565122962) passed at `cdfeff2`: all 110 tests, source and packaged-executable smoke tests, native WebView2 tests, real public episode download and packaged browser playback. The downloaded episode SHA-256 remained `dc430b910525915fa72081f11962d7758d028cd8c0b5742cce77a31f343ee88b`. A Windows package artifact was produced; no release was published.

Linux setup failed on Ubuntu archive DNS, before completing application checks. The final phase now installs a checksum-pinned Linux FFmpeg test binary from GitHub and runs the separate UI job on Windows, removing the failing apt setup dependency. Pending UI assertions exercise paste-many input, subtitle options, DRM labels, the informational checkbox and filename-template persistence. Windows DASH fixture generation now uses the fixture directory as its working directory; actual download and decode assertions are unchanged. Phase 4.13 also touches `.github/workflows/verify-release.yml` and `scripts/ui-test.cjs`.

Creating the branch automatically triggered the existing pipeline on unchanged main before phase 4.9. Phase 4.0–4.12 commits suppressed further CI; the changed-code packaged pipeline was first enabled with phase 4.13.

Windows UI QA exposed an import-state race: source rows were read before task completion, allowing a completed import to be shown without its newly committed source. State now snapshots task completion before reading sources. The exact-result UI test also waits for the imported source selector. The optional HLS CDN script is asynchronous so its availability cannot block ordinary startup.
