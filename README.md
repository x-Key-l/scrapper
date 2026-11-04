# SceneTrace 3.0

Search video websites, select a title or episode, and watch through a direct file or the source's player. SceneTrace runs locally and opens in your default browser.

## Install on Windows

1. Open [GitHub Releases](https://github.com/x-Key-l/scrapper/releases) and download **SceneTrace-Windows-x64.zip** from the 3.0 release candidate.
2. Right-click the ZIP and choose **Extract All**.
3. Open the extracted SceneTrace folder and double-click **SceneTrace.exe**. Keep the included **_internal** folder beside it.

The portable Windows 10/11 x64 package includes its Python and FFmpeg runtime. The existing local profile at **%LOCALAPPDATA%\SceneTrace** continues to hold saved items, history, downloads and settings. Quit the old app before launching the upgrade. The [2.0 release candidate](https://github.com/x-Key-l/scrapper/releases/tag/v2.0.0-rc.13) remains available for comparison.

## Find and watch a video

- **Anime** accepts English, Japanese, Romaji and alternative title searches. Try **Pocket Monsters**, open **Pokémon: Indigo League**, and select one of the first three official Pokémon TV episodes. The exact episode link remains available alongside the official embed when the publisher exposes one.
- **Universal Video Search** queries video websites. Try **Caminandes**, open its series result, and select **Episode 3 · Llamigos**. The app uses the actual Commons media file and provides playback controls and eligible formats.
- **Memory Search** uses plot, character, setting and date clues. Open a match and choose **Find Video** to look up viewing options from connected websites.
- **Video Sources** separates searches, discovered pages, checked media bytes, embeds and eligible downloads. Select **Test viewing** to check a sample on your PC. **Metadata & imports** contains AniList, TVmaze, optional TMDB and file imports.

See [owner help](docs/HELP.md), [website adapter configuration](docs/WEBSITES.md), and [verification and limits](docs/V3-AUDIT.md).

## Add a website

Open **Video Sources → Add Video Website**, enter a public website, inspect it, check the suggested configuration, test a sample title, then save. Supported methods include public GET search forms, HTML listings, structured VideoObject metadata, JSON, RSS/Atom and video sitemaps. Configure selectors, query parameters and episode links in the wizard.

For an example, enter **https://www.w3schools.com/html/html5_video.asp**, use the detected HTML video listing, and test **HTML Video**. Save it, choose the new source in Universal Video Search, and search again. The live browser workflow exercises this exact path.

Optional JavaScript rendering uses an installed Edge or Chromium in an isolated profile. Brave Search is optional for wider source discovery. TMDB needs a personal API Read Access Token. Built-in viewing examples require neither key.

## Playback and download scope

Direct browser playback supports compatible MP4/WebM/OGG files. Play, pause, seek, volume, fullscreen, speed and source-provided WebVTT subtitles are available according to the selected player. Official embeds can handle a provider's own adaptive playback. The direct file path covers progressive media. Protected subscriptions, DRM, login-only or challenge-gated pages, and arbitrary HLS/DASH extraction are unsupported. HiAnime and AnimeKai have no verified connectors in this release.

Downloads use eligible source files and the existing queue, including pause and resume when the host supports ranges. The link analyzer can combine compatible yt-dlp video-only and audio-only HTTP tracks with bundled FFmpeg. Regional and account requirements can affect official player handoffs.

## Verification

Run **python -m pytest -q** and **python scripts/smoke.py** for local checks. CI runs live provider checks, genuine browser playback, setup of a real user-added HTML source, and a completed licensed episode download. The Windows job repeats playback with the actual packaged executable. The ZIP includes **docs/live-results.json**, **docs/watch-results.json** and **docs/BUILD.json**. The release includes screenshots and a ZIP checksum.
