# SceneTrace 3.0 audit and verification

Version 2.0 began with a common catalog search and required a separate media lookup. AniList records supplied descriptions and title aliases. The old Find Video action led to another list of candidates. Anine's watch implementation creates title-specific search URLs and hands them off to the browser. Its focused watch entry point informed this redesign.

The supplied Windows screenshots showed an Internet Archive self-signed chain rejection and a TMDB error from a missing optional key. Version 3.0 uses the native Windows certificate chain validator through truststore, retains hostname checks and exposes an Archive HTTPS diagnostic. Tests exercise an actual rejected self-signed certificate. The originating PC's certificate chain still needs an owner-side retest.

## Verification scope

| Source | Search | Episode or video discovery | Playback evidence | Download evidence |
| --- | --- | --- | --- | --- |
| Pokémon TV | English and alternate title | Three official Indigo League episode pages | Exact publisher handoff and oEmbed response. Embedded frames depend on the owner browser and region. | Publisher viewing only |
| Caminandes on Wikimedia Commons | Series title and remembered plot clues | Three exact episode pages | Chromium advances decoded video and tests speed. The packaged Windows executable repeats the flow. | Complete licensed episode file downloaded and decoded in the Windows gate |
| W3Schools HTML video listing | User-added website and title query | Video discovered from the actual HTML | Browser playback after inspect, test, save and search | Source viewing sample |
| Internet Archive | Live search | Live sample video formats and byte-range access | Owner playback check for this source | Licensed formats can be queued. The release gate's full transfer uses Commons. |
| Wikimedia Commons general search | Live search | Direct media URLs and exact file pages | The Caminandes workflow exercises Commons playback | The Caminandes workflow exercises Commons download |
| PeerTube / Sepia Search | Live federated search | Video URLs from the index | Instance-specific direct files or official embed. Live frames still need verification. | Instance permission and file formats determine eligibility |

Read the generated **live-results.json** and **watch-results.json** for the specific release run. Media transfer tests exercise actual HTTP, yt-dlp and FFmpeg. The separate-track test supplies a controlled extractor manifest and transfers and merges both real fixture files.

Regional availability and provider changes affect official links and embeds. Some websites require a custom selector or a source-specific adapter. Native Windows file dialogs, optional Edge rendering on the owner's PC and modest hardware performance remain owner checks. HLS/DASH extraction, protected playback and account bypass are unsupported.
