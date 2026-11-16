# SceneTrace 4.1 · Windows release candidate

Download **SceneTrace-Windows-x64.zip**, choose **Extract All**, then open **SceneTrace.exe** inside the extracted SceneTrace folder. Keep the included files together. Python, Node, Git and Docker are not required. Integrated tabs reuse the installed Microsoft WebView2 Evergreen Runtime; a default-browser fallback remains available.

**Website downloads no longer get canceled and redirected into the analyzer.** WebView2 handles ordinary download buttons and Save As. Native transfers appear alongside analyzer downloads, and closing their tab keeps active transfers alive. Real popup windows preserve download workflows that depend on their opener.

The **Videos** toolbar control detects compatible media and offers actual reported formats. Compatible direct containers/audio, unencrypted native HLS/DASH and separate audio/video merging use yt-dlp and the included FFmpeg. The **Media Library** organizes completed videos and imported folders independently of transfer history, with source folders, conservative episode recognition, categories, collections and safe moves/renames.

A compact dark browser interface adds the **shield**: cached HaGeZi Light ad/tracker domains, per-site controls and manual updates. Existing search, source connectors, bookmarks, history and settings remain available.

The release gate exercises the actual packaged Windows application, native public MP4/PDF downloads, controlled ZIP transfers and range resume, detection, protection, playback, library organization and restart persistence. Detailed capability reports and measured timings are included in the ZIP. See **docs/V4.1-AUDIT.md** for the precise evidence and limits.

Animepahe's complete episode download workflow and HiAnime third-party playback/downloads remain unverified. Native download repair is not a claim that every source provides a compatible file. DRM and source access controls are not bypassed. Physical high-DPI and older-hardware acceptance, long downloads and sleep/wake still need owner testing.

Quit SceneTrace before upgrading, extract into a new folder, and keep the profile at **%LOCALAPPDATA%\SceneTrace**. The previous 4.0 release remains available for rollback.
