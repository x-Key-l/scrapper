# SceneTrace help

## Add a database

Open Database Hub. Enable the built-in sources you want; **Test connection** makes a real request. TMDB needs your own API Read Access Token.

For a file, choose **Import database**. Select an export, inspect the sample and map Title, Description, Year, URL and Media URL as available. Title is required. Choose a SQLite table or JSON records path when needed. **Import and index** displays progress. Failed imports preserve the previous index.

For an API/feed, choose **Add a source**. Paste the documented endpoint and choose **Detect & preview**. Ordinary websites require API/export documentation rather than automatic integration. Advanced configuration supports parameters, authentication, GraphQL variables and dotted field paths.

**Find More Sources** suggests documented connectors. Optional Brave Search finds candidate websites whose APIs remain unverified; a manual web search is available without a key.

## Search and identify

Universal Search queries checked sources and the local index. Individual source messages explain failures; other sources continue. Load another page for more provider results.

In Memory Search, describe whatever you remember. Optional setting, characters, scene, language and decade clues help ranking without excluding every uncertain memory. Evidence labels describe real metadata overlap. Refine and submit again. Difficult scene searches need richer imported descriptions or more suitable catalogs.

## Locate media

Open Details and choose **Find Video**. Connected media/hybrid sources are searched by title and alternative names. Trailers/clips are labeled; uploader full-length claims are unconfirmed.

Analyze the actual source link for current formats. Preview uses real source media, subject to browser codecs and source availability. Open the original page when extraction or playback fails. A catalog record does not establish full-video availability.

## Download

Analyze first. Select a reported quality/source format, destination and optional MP4/MP3 conversion. Video-only files are explicitly labeled. Confirm authorization, then add to the queue.

Download Center shows progress, speed and ETA when known. Pause preserves partial data. Resume validates byte ranges when supported; otherwise it restarts safely. Cancel removes SceneTrace temporary data. Retry after errors. Expired links may need fresh analysis and a new transfer.

Existing files are preserved using numbered filenames. Disk checks prevent exhaustion; no fixed download-size limit is imposed. Completed files remain in your chosen folder.

## Troubleshoot

- Failed source: test connection, check endpoint/credentials, internet and provider status.
- No matches: use shorter/different clues, another provider or richer descriptions.
- Wrong mapped fields: configure the source and refresh its local index.
- Configuration error: static parameters and GraphQL variables must be JSON objects.
- Inaccessible media: open the official page; restrictions and DRM are not bypassed.
- Missing runtime: extract the full ZIP, including _internal.
- Browser closed: double-click the executable to reopen the running interface.
- App closed: launch again and resume paused work.

Export sanitized diagnostics from Settings. For a complete backup, quit and copy %LOCALAPPDATA%\SceneTrace. Re-enter DPAPI credentials when moving to another Windows account.
