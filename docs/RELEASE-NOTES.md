# SceneTrace 4.0 · Windows release candidate

Download **SceneTrace-Windows-x64.zip**, choose **Extract All**, and double-click **SceneTrace.exe** inside the extracted folder. Keep all companion files together. No Python, Node, Git or Docker is needed. Integrated tabs use the installed Microsoft WebView2 runtime; a default-browser fallback is available if it is missing.

This release adds a native tabbed video browser, progressive Quick and Deep Search, fuzzy and alternative title matching, character/cast evidence, public full-text retrieval, and complete search-history management. Existing saved items, sources and settings carry forward.

The HiAnime Naruto regression is fixed: public search returns real title links, and the series page exposes 220 ordered episode links. Its third-party playback and downloads remain unverified. Caminandes provides verified in-app playback and a completed licensed download. Pokémon TV provides exact official episode handoffs. A user-added W3Schools source was searched and played through the real Windows package.

Windows verification exercises actual WebView2 navigation, lazy tabs, bookmarks, isolation from local APIs, renderer-crash recovery, video frames and restart persistence. Source tests and browser workflows must pass before publication. Reports, measured performance and limitations are in **docs/V4-AUDIT.md** and the JSON reports inside the ZIP. Screenshots and a SHA-256 checksum are attached.

This is a release candidate. Live websites can change, regional restrictions apply, and owner-side testing on modest hardware is still needed. No DRM, authentication, paywall or anti-bot bypass is included. Download availability depends on an eligible source path. Deep Search identifies plausible candidates from available evidence; it does not guarantee scene recognition or universal site compatibility.
