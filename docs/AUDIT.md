# Technical audit

All three supplied archives were inspected before implementation. The authenticated GitHub repository was empty (Git tree request: HTTP 409).

| Input | SHA-256 |
|---|---|
| Anine.zip | 9a4c9c48dbcdeabc2b978e9ce122fb270d13eda6edc479d3266e289284be7692 |
| SceneTrace-PC-source.zip | 6660e3a5f5b696fcb6a7a12243e40b0479e578fecb9f6dfe21ff12d1fd6cd297 |
| SceneTrace-source.zip | 553cac628b2203595ea9f93abab227f0ce5fefd1710af028f0859773e1ee6c39 |

## Baseline

- SceneTrace PC: unittest discovery, 5 passed.
- Original: PYTHONPATH=backend python -m pytest backend/tests -q, 36 passed after installing its dependencies; one Starlette deprecation warning.
- Anine: node --test, 66 passed.

## Confirmed findings

| Area | Supplied evidence | Decision |
|---|---|---|
| Launch | PC fixed port, exits on conflict, no instance lock. | Dynamic port, file lock, identity-checked reopen. |
| Setup | Original requires API_TOKEN, separate Vite frontend and backend deployment. | Local stdlib HTTP and static UI in one portable folder. |
| Windows | Original media_worker.py unconditionally imports Unix-only resource. | Platform-neutral subprocess processing; Windows build smoke. |
| Downloads | PC generic worker strips formats and provides no queue. Original jobs.py defaults to 200 MB/240 sec/20 jobs, deletes delivered files. | Reported formats, persistent resource-aware queue, destinations, recovery and FFmpeg. |
| Search | Hardcoded sources; entire memories treated as title queries; no import/index/configuration. | Adapter system, Hub, FTS5, clue retrieval and configurable sources. |
| Federation | PC awaits futures in insertion order; executor context waits for all. Its source-result test patches functions after SEARCHERS captured originals. | Shared executor, deadline isolation and tests that patch actual call sites. |
| UI | Saved records only in browser localStorage; inline image error code conflicts with CSP. | SQLite persistence, escaped rendering, delegated handlers. |
| Rights | PC whitelist excludes CC BY-NC and other permissions without assessing authorization. | Preserve license information and require explicit download authorization. |
| Network | Useful public-IP validation and pinned proxy; no range or POST relay. | Extend design for Range, POST and credential-safe redirects. |
| Packaging | PC builds EXE without launch tests or Releases. | Functional tests, packaged HTTP smoke, notices, checksums and gated release workflow. |
| Anine | Good cards/navigation and native launcher; still locates an installed Node runtime and fixed port. | Adopt usability ideas, bundle runtime; no Anine assets/code copied. |

## Foundation

SceneTrace PC provided the conceptual foundation for a small Python/static-UI desktop app. Retained public-network pinning/proxy and isolated extractor-worker designs; rebuilt storage, adapters, search, imports, queue, UI and launcher. Original source informed behavior without retaining its deployment stack.

## Verification boundary

Workspace HTTP requests through the environment proxy can reach some endpoints, but production pinned transport uses direct DNS, which this workspace cannot resolve. This is an environment limitation, not successful production-adapter verification. GitHub Actions records real adapter results separately in live-results.json.
