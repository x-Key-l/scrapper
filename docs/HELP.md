# SceneTrace owner guide

## Browse and search

Open **Browser**, enter a full website address and choose **Open**. In the Windows browser, Ctrl+L selects the address, Ctrl+T opens a tab, Ctrl+W closes it, Ctrl+F finds text and F5 reloads. Back/Forward preserve each tab's navigation. Use the star to bookmark a page. Bookmarks and browsing history appear in SceneTrace's Browser and History views.

The toolbar menu can **Add this website**, search it, inspect the current video page, save it, or open it in your normal browser. **Search current website** needs a connected searchable source. If automation is unsupported, ordinary browsing remains available. A failed website or renderer can be retried with Refresh. Use the external-browser option if a site's player cannot run inside WebView2.

Tabs are created lazily and inactive website views may be suspended. SceneTrace uses one shared WebView2 runtime environment, with separate application and website profiles. Close tabs you no longer need; heavy advertising sites can still consume substantial memory.

## Find and watch an episode

Open **Anime**, type **Pocket Monsters**, and select **Pokémon: Indigo League**. Choose one of the first three official episode pages. An official embed is offered when exposed; **Open exact video at source** remains available. Region or account requirements can affect the publisher player.

For a verified direct in-app video, search **Caminandes** in **Quick Search**, choose the series, then **Llamigos**. The native player has seeking, volume, speed and fullscreen controls. Provider embeds expose their own controls. Subtitle options appear only when the source supplies compatible tracks.

Metadata cards are identification leads. Select **Find viewing options** to search connected video sites. A poster alone never establishes playback or a download.

## Add a website

1. Choose **Video Sources → Add Video Website**, or add the current browser page from its toolbar menu.
2. Paste a public website, listing or feed URL and select **Inspect website**.
3. SceneTrace detects public methods and runs a sample search. Replace the sample title if necessary and **Test integration** again.
4. Review search results and each capability separately. Save the tested source, or keep a browse-only entry when integration is incomplete.
5. In Quick Search, select that website and enter a title.

Try **https://www.w3schools.com/html/html5_video.asp** with **HTML Video**. This listing exposes a real video. For **https://hianime.ms/**, the tested **Naruto** search retrieves title pages and 220 Naruto episode links. Playback and download from that website remain unverified; open an exact episode page to check its player. No access-control bypass is provided.

Advanced configuration supports search URL patterns, selectors, JSON mappings and feeds. Ordinary detected layouts do not require selector editing. You can edit, disable, retest or remove a source independently. A changed layout, restricted service, JavaScript requirement, network error and genuine empty search are reported separately.

**Find More Sources** suggests documented integrations. An optional Brave Search key adds web discovery. Candidates remain unverified until tested.

## Deep Search

Enter an imperfect title or remembered description. Add optional character, actor, period or category clues. Example: **Nartuo**. Another example: **A movie where people discover an underground cave and encounter dangerous creatures**.

Results arrive as sources respond. **Cancel** stops further retrieval while preserving received results. Evidence lists actual title, plot, character or cast matches. A remembered year is a soft clue, so a wrong decade does not remove otherwise useful matches. Exclude wrong candidates, add details and refine. Search additional pages to explore more of a provider's index.

SceneTrace checks connected video websites for likely titles and alternatives. Source availability is independent of relevance. Full-text articles and popular-catalog browsing have limited coverage; no result is a guarantee that every scene detail matches.

## Manage history

Use × beside a recent search to delete just that item. **History** supports text filtering, selection, bulk deletion and clearing all search history. Bulk deletion asks for confirmation. **Undo** is available for 60 seconds. Deleted entries stay deleted after restart.

History settings control future recording and automatic retention. Turning recording off does not erase previous entries. A retention value of 0 keeps history until you remove it. Search-history deletion does not remove bookmarks, saved videos, sources or downloads. Browsing history has its own recording control.

## Download an eligible video

Open an episode that offers files, expand **Download this video**, choose an available format and destination, and start the transfer. **Downloads** shows progress, speed, remaining time, pause, cancel and retry. Resume depends on the server supporting byte ranges and retaining the same file. Collisions produce a new filename; disk space is checked. Compatible separate HTTP audio/video tracks can be combined with bundled FFmpeg.

Some sources offer viewing only. SceneTrace keeps the exact original link when no eligible file is available. It does not bypass DRM, paywalls, login barriers or anti-bot challenges.

## Ordinary browser downloads and detected video

Use a website's own download button as usual. The native browser download dialog handles Save As and destination selection. These downloads do not require media analysis. They also appear in SceneTrace **Downloads**, where supported operations include pause, resume, cancel, open file, open folder and removal from transfer history. Removing history keeps the file and its library entry. Closing the download's tab keeps an active transfer alive; quitting the application stops native transfers. After restart, reopen the original website to start a fresh native download.

The **Videos** control near the address bar becomes active when media is observed. Select an item to inspect formats, choose a folder and download. Only formats actually reported by the source appear. Possible adverts are separated from other candidates. If detection cannot find a compatible transfer, keep using the site's player or its own download controls. Playback, file transfer and metadata identification are different capabilities.

MP4, WebM, MKV and common audio/container formats are supported when the transport is compatible. Standard unencrypted HLS/DASH can use yt-dlp's native fragment downloader; separate tracks can be merged by the included FFmpeg. No resolution or file-size ceiling is imposed. Available disk space and source access still matter.

## Protection controls

Click the shield beside the address bar to view blocked requests, disable protection globally, allow the current website, or update the domain list. The bundled HaGeZi Light list works offline; updates use the documented HTTPS provider. Old rules remain active if an update fails. This is domain filtering with limited cosmetic cleanup, not a full browser extension engine. If a website breaks, allow that site and refresh. Media requests and top-level document navigation are not blanket-blocked.

## Media Library

Completed video/audio transfers appear in **Media Library**. Import a folder to include older files without moving them. New downloads go into a source-domain folder by default; this can be disabled under **Automatic organization**. Category and recognized series subfolders are optional for analyzer downloads. Browser Save As can override its suggested folder.

Names such as `Example Anime Ep 5`, `Example Anime Episode 005` and `Example Anime S1E05` provide episode information. Unique exact aliases already present in the local metadata index can resolve a series; fuzzy matches remain suggestions. Unknown categories stay Unsorted. SceneTrace does not silently label every episodic video as anime.

Select videos and choose **Organize selected** to assign a category, series or collection. Use the same collection to merge groups; assign a new collection to split one. **Edit** changes metadata, **Rename file** changes the filename, and **Move selected files** changes the folder after confirmation. Collisions receive numbered names; existing files are not overwritten. Collection edits do not move files automatically.

## Startup and upgrades

Extract the entire ZIP and launch SceneTrace.exe. Keep its companion executable, DLLs and _internal folder together. The integrated browser uses Microsoft's WebView2 Evergreen Runtime. If unavailable, the app opens in your default browser. Install the runtime from Microsoft's official WebView2 page to enable integrated tabs. Runtime installation and first startup may take longer than subsequent launches.

Quit the old app before upgrading. Extract the new release into a separate folder. The profile stays at **%LOCALAPPDATA%\SceneTrace**. Save a copy of that profile before rolling back to an older version. Repeated launches focus the current application instead of creating another server.

## Troubleshooting

**Settings → Test Archive HTTPS** checks Internet Archive using Windows certificate trust and hostname validation. If Windows rejects the chain, check the PC clock and compare the same URL in Edge. On a managed network, ask its administrator to check a proxy or antivirus certificate issuer. SceneTrace never disables TLS validation to work around the error.

TMDB's **Optional key needed** status is a setup choice, not a failure of built-in playback. Configure your personal API Read Access Token only if you want that catalog. No paid AI key is needed.

Use **Settings → Export diagnostics** for a report that omits credentials, search text, media URLs and local paths. Retest one failing source; other sources can continue working. Long transfers, sleep/wake, SmartScreen and performance on your own hardware still require owner-side acceptance testing.
