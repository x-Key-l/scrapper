# Connector configuration

Adapters return normalized records and a per-query pagination flag. Original provider ID, URL and external identifiers remain attached.

| Connector | API documentation | Credential | Role |
|---|---|---|---|
| Wikipedia + Wikidata | https://www.mediawiki.org/wiki/API:Search and https://www.wikidata.org/wiki/Wikidata:Data_access | None | Metadata / explicit relationships |
| TVmaze | https://www.tvmaze.com/api | None | Metadata |
| AniList | https://docs.anilist.co | None for public search | Metadata |
| Internet Archive | https://archive.org/developers | None for public items | Hybrid |
| Commons | https://www.mediawiki.org/wiki/Extension:TimedMediaHandler/API | None | Hybrid |
| PeerTube / Sepia Search | https://docs.joinpeertube.org/api-rest-reference.html | None for public search | Media |
| TMDB | https://developer.themoviedb.org/reference/search-multi | Personal read token | Metadata |

Health starts as Untested. Quotas and connectivity apply independently. AniList requests are paced at least 2.1 seconds apart, reflecting its currently documented reduced quota; other adapters are independently paced. HTTP 429 produces retry guidance.

## REST JSON

For a response containing a results array with id, name, plot and watch fields: map ID to id, Title to name, Description to plot, URL to watch. Configure the documented search parameter (q/search), optional numeric page parameter and result-array path (results or data.items). Static parameters must be a JSON object.

Use Authorization with a Bearer prefix or an API-key header with an empty prefix. Credentials belong in the credential field, not the URL.

Custom APIs can specify an incremental timestamp parameter. It receives the last successful synchronization epoch; use it only when the provider documents that behavior. Numeric page pagination is supported. Cursor/offset APIs need an appropriate adapter, compatible gateway or export.

## GraphQL

Provide a read-only query operation using $query and optional $page variables. Search text is passed as a variable, never interpolated into query syntax. Set the actual result-array path, for example data.search.items. Use the provider's schema; arbitrary websites do not supply one automatically.

## Imports

CSV/TSV use UTF-8 and headers. JSON supports an array or a configured nested records path. JSONL/NDJSON streams one object per line. SQLite opens ordinary tables read-only with quoted identifiers and trusted_schema=OFF; virtual tables/extensions are not executed. Checkpoint WAL data in the owning application before export.

RSS/Atom/Media RSS map titles, descriptions, item links, thumbnails and enclosures. Custom entities and DTDs are rejected. Missing titles or malformed records roll back the entire import.

Use the native file picker for large streaming CSV/JSONL/SQLite exports. Browser upload and JSON-array guards protect memory; they do not restrict source counts or download sizes.
