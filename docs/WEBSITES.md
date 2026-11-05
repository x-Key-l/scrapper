# Website connectors

The wizard stores field mappings and URLs as data. It supports public HTTP GET, HTML listings, feeds, JSON and direct video sitemaps. Supply a page with identifiable results or a documented endpoint.

| Field | Example | Behavior |
| --- | --- | --- |
| Search URL pattern | /search?q={query}&page={page} | Encodes your query and page number on the configured origin |
| Search and page parameter | q and page | Adds or replaces query string values |
| Result selector | article.video | Selects each listing item |
| Title and detail link selectors | .title and a[href] | Reads the title and the page URL relative to the item |
| Episode list selector | .episodes a | Reads separate episode links on the series page |
| Episode title and link selectors | .name and a[href] | Reads an episode's title and exact destination |
| Media selector | video source[src] | Finds files that the selected page exposes |
| JSON result array | data.items | Chooses a nested result list |
| JSON field mappings | name, pageUrl, cover | Maps provider fields to title, URL and thumbnail |
| Result path prefix | /videos/ | Restricts a listing or sitemap to the relevant paths |

A result page can also expose a VideoObject, standard video tag or official YouTube/Vimeo embed. A download option requires source permission evidence and a usable file. The app checks the selected file again when it queues the transfer.

The optional **Render public pages** switch starts a fresh installed Edge or Chromium profile through the app's public-network proxy. This mode runs the website's JavaScript when selected. Login flows, challenges, protected media and arbitrary imported connector scripts are outside the supported integration methods. The normal player and static connectors work without the renderer.

## Developer extension

Register a built-in kind and capability description in **scenetrace/sources.py**. Implement search with **search(source, query, page)** returning normalized records and a pagination flag. Preserve the provider ID, title, alternatives, page URL, artwork and source ID. Supply stable page or episode URLs in **scenetrace/viewing.py**, and return verified direct formats, an official embed or the exact source page. Verify download permission independently of playback. Use **scenetrace.network** for public requests, certificate checks and address validation.

Add an actual provider integration test for the capabilities you claim. The app accepts configuration data through the wizard. Developer adapters are shipped as reviewed source code.

## 4.0 detection and diagnostics

The wizard detects common public result-card layouts and `/details/` pages, runs a real sample and stores capabilities individually. Numbered `data-ep` episode lists are sorted numerically. A functioning search may be saved even when a subsequent episode/player check fails; its failed capability remains explicit. Manual browse-only entries preserve navigation without pretending to support search.

`WebsiteSearchError` distinguishes service restrictions, JavaScript requirements, missing result structure and browse-only configuration. Detailed parser context is available to diagnostics; ordinary users see an explanation. An HTTP 200 homepage alone is not a successful connector test. Edits invalidate in-flight test/save tokens so old results cannot save a different configuration.
