# Third-party notices

Portable packages contain separate upstream runtime components. Their license texts are copied into licenses at packaging time. Catalog images, descriptions and media retain original owners and licenses; metadata does not grant media rights.

- Python: Python Software Foundation license. SQLite: public domain.
- yt-dlp 2026.10.26: Python distribution under the Unlicense; https://github.com/yt-dlp/yt-dlp.
- imageio-ffmpeg 0.6.0: BSD-2-Clause wrapper, with separately licensed FFmpeg; https://github.com/imageio/imageio-ffmpeg and https://github.com/imageio/imageio-binaries provide source/build provenance.
- FFmpeg runs as a separate executable. Its exact version, configuration and license output are included in licenses/FFmpeg-build-and-license.txt. GPL-enabled builds use GPLv3 or later. Upstream source releases: https://ffmpeg.org/releases/; binary build information: imageio-binaries repository. Retain upstream license/source notices on redistribution.
- PyInstaller bootloader: GPL with its special distribution exception; license copied from the build environment.
- Tcl/Tk: upstream Tcl/Tk licenses; collected with native dialog runtime files.
- TVmaze metadata: CC BY-SA 4.0, https://www.tvmaze.com/api. Plain-text adaptations retain source links.
- Other providers: their data/media licenses and service terms apply. SceneTrace is not endorsed or certified by any provider.

The UI uses system fonts, original CSS/SVG and provider-supplied artwork. No Anine executable, artwork or application code is redistributed.

- Microsoft.Web.WebView2 SDK 1.0.3537.50: Microsoft WebView2 license, https://www.nuget.org/packages/Microsoft.Web.WebView2/1.0.3537.50. SDK license/notices are copied from the restored NuGet package into licenses. The separately installed Evergreen Runtime retains Microsoft's runtime terms; SceneTrace does not redistribute a Chromium installation.
- .NET Framework 4.8 is a Windows system runtime. The build-only Microsoft.NETFramework.ReferenceAssemblies package is not an end-user dependency.
- Wikipedia article extracts: CC BY-SA 4.0, https://en.wikipedia.org/wiki/Wikipedia:Copyrights. Plain-text extracts preserve the article URL and attribution. Wikidata structured statements: CC0, https://www.wikidata.org/wiki/Wikidata:Licensing. These sources provide identification evidence, not media rights.

- HaGeZi Light domain filter list: GPL-3.0, https://github.com/hagezi/dns-blocklists. The bundled list is retained verbatim in gzip/base64 form; its complete license and source data are included under licenses. SceneTrace parses domain rules without executing list content. Manual updates retrieve the upstream HTTPS list.
