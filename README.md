# SceneTrace 4.1

Browse video websites in tabs, search connected sources, identify forgotten titles, and open real episode pages or supported players. Metadata catalogs provide identification evidence; viewing and download availability are checked separately.

## Install on Windows

1. Open [Releases](https://github.com/x-Key-l/scrapper/releases) and download **SceneTrace-Windows-x64.zip** from the latest **4.1 release candidate**.
2. Right-click the ZIP → **Extract All**.
3. Open the extracted **SceneTrace** folder and double-click **SceneTrace.exe**. Keep **all included files and folders together**.

Windows 10/11 x64. Python, Node, Git and Docker are not required. The package includes Python, yt-dlp and FFmpeg. The integrated browser uses Microsoft's installed **WebView2 Evergreen Runtime**. If it is missing, SceneTrace opens in your default browser; install Microsoft's [Evergreen Runtime](https://developer.microsoft.com/en-us/microsoft-edge/webview2/) to enable integrated tabs. No complete Chromium browser or AI model is bundled.

Quit the old app before upgrading. Settings, saved items, sources, downloads and history remain in **%LOCALAPPDATA%\SceneTrace**. Extract each release into a new folder. [SceneTrace 4.0 RC45](https://github.com/x-Key-l/scrapper/releases/tag/v4.0.0-rc.45) remains available for rollback; back up your profile before reverting after using new features.

## New in 4.1

Website download buttons use WebView2's native transfer engine. SceneTrace no longer cancels them or sends them to the analyzer first. The **Videos** toolbar control detects HTML5 and compatible network media, then offers actual reported formats. **Downloads** combines native browser and analyzer transfers. **Media Library** separately organizes completed videos and imported folders.

The shield blocks known ad/tracker domains using a locally cached HaGeZi Light list. Click it to allow a site or update rules. Downloads and media requests are kept separate from blocking. Tabs now sit above a compact address toolbar.

## Start here

- **Browser:** enter a public website. Use tabs, back/forward, refresh, bookmarks and find text. The toolbar menu can add or inspect the current site, or start Quick/Deep Search there. External websites have no native application bridge.
- **Anime:** search **Pocket Monsters**, choose **Pokémon: Indigo League**, and open one of the three starter official episode pages. These are exact publisher handoffs, not a claim of a complete anime streaming catalog.
- **Quick Search:** search **Caminandes**, select **Llamigos**, and play its actual Commons media file. Eligible files have format and destination controls.
- **Deep Search:** try **Nartuo**, a character name, an actor or a remembered description. Optional clues, source selection, exclusion and refinement remain available without retyping. Results explain matching metadata; the app also looks for viewing pages for likely titles.
- **Video Sources:** choose **Add Video Website**, paste a URL, inspect the suggested method, review the automatic sample search and save. Advanced settings are optional. A source can remain browse-only when automated searching is unavailable.
- **History:** delete one item with ×, select several, clear all with confirmation, undo a recent deletion, search history or change retention/recording settings. Bookmarks and saved videos are separate.

See [owner help](docs/HELP.md), [4.1 verification](docs/V4.1-AUDIT.md) and [4.0 baseline measurements](docs/V4-AUDIT.md), [website adapters](docs/WEBSITES.md) and [testing](docs/TESTING.md).

## Website compatibility

| Source | Search / discovery | Viewing | Download |
| --- | --- | --- | --- |
| Caminandes on Wikimedia Commons | Three animated episodes | Actual in-app playback tested on packaged Windows app | Completed licensed file transfer, decoded with FFmpeg |
| Official Pokémon TV | Starter title aliases; first three Indigo League episodes | Exact publisher episode handoff verified; embed frames not verified | No eligible path offered |
| W3Schools HTML Video page | Added through wizard; listing search verified | Actual direct playback in SceneTrace and native browser | Native MP4 button and detector-assisted file transfer are tested separately |
| HiAnime (`hianime.ms`) | Naruto search returns 27 results; Naruto detail page exposes 220 ordered episode links | Exact episode links; playback unverified | No verified eligible path |

HiAnime's failure was an omitted `/details/` link pattern in the parser. Its public GET search URL is `/search?q=Naruto`; the tested search and episode list did not require JavaScript. This repair does **not** verify third-party players or give download permission. Website content and restrictions can change; retest the source on your PC.

AniList, TVmaze, Wikipedia/Wikidata and optional TMDB are metadata sources. Archive, Commons and PeerTube expose independent media capabilities; consult their latest connection report. TMDB requires your optional personal API Read Access Token. Optional Brave Search credentials enable wider source discovery. Built-in viewing examples need neither key.

## Limits

No promise of universal site compatibility. Login barriers, anti-bot challenges, DRM, paywalls and protected playback are not bypassed. Unencrypted HLS and DASH supported by yt-dlp native fragment downloaders are available, including separate audio/video merging with FFmpeg. Unsupported transports and DRM remain explicitly reported. The queue supports eligible HTTP files, pause/resume when the host supports ranges, retry, disk checks and compatible FFmpeg processing.

Deep Search uses bounded live catalogs, full-text retrieval, fuzzy titles, aliases, character/cast relationships, local FTS5 and evidence ranking. It does not recognize scenes absent from the available sources, and does not download an embedding model. Live provider results and rights vary by region and date.

## Verification

The Windows pipeline builds the real executable, launches it, checks migration/restart, exercises WebView2 tabs and isolation, recovers a crashed renderer, plays real media and completes a licensed episode download. Browser tests cover the real Add Website and search-to-player workflow. The release ZIP contains build information and live reports; screenshots and SHA-256 checksum accompany the release. Performance figures are measured on shared Windows CI, not a low-end hardware guarantee.
