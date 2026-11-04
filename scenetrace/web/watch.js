'use strict';

const watchState = {
    query: '', category: '', page: 1, mode: '', busy: false, more: false,
    rows: [], sources: [], episodes: [], selected: null, request: 0, playRequest: 0,
};

function watchCard(record, index) {
    const art = link(record.thumbnail);
    const image = art ? '<img loading="lazy" alt="" src="' + esc(art) + '">' : '<span aria-hidden="true">▷</span>';
    const type = [record.year, record.edition, record.episode_count && record.episode_count + ' episodes'].filter(Boolean).join(' · ');
    return '<article class="card"><div class="poster">' + image + '<span class="badge">' +
        esc(record.source_name) + '</span></div><div class="card-body"><h3>' + esc(record.title) +
        '</h3><div class="meta">' + esc(type || record.category) + '</div><span class="badge ' +
        (record.is_video ? 'ok' : '') + '">' + esc(record.status) + '</span><p class="card-description">' +
        esc(record.description) + '</p><button class="primary" data-watch="title" data-index="' + index + '">' +
        (record.is_video ? 'View video options' : 'Find episodes') + '</button></div></article>';
}

function watchSearchPage(mode) {
    const anime = mode === 'anime';
    const visible = watchState.mode === mode;
    const active = state.data.sources.filter(source => source.enabled && (anime
        ? source.categories.some(category => ['anime', 'animation'].includes(category))
        : source.role !== 'metadata'));
    const categories = [...new Set(active.flatMap(source => source.categories))].sort();
    const options = active.map(source => '<option value="' + esc(source.id) + '"' +
        (visible && watchState.sourceId === source.id ? ' selected' : '') + '>' + esc(source.name) + '</option>').join('');
    return title(anime ? 'ANIME' : 'VIDEO DISCOVERY', anime ? 'Find anime to watch' : 'Find videos on your websites',
        anime ? 'Search by English, Japanese or Romaji title. Choose a result to see available episode pages.' :
            'Search connected video websites. Open a result to see the source player or available files.') +
        '<form data-watch-form="search" class="searchbar"><input name="query" aria-label="Video search" required minlength="2" value="' +
        esc(visible ? watchState.query : '') + '" placeholder="' + (anime ? 'Try Pokémon or Pocket Monsters' : 'Try Caminandes or a topic') +
        '"><button class="primary">Search</button></form><div class="toolbar"><label for="watch-source">Website</label>' +
        '<select id="watch-source"><option value="">All enabled sources</option>' + options + '</select>' +
        '<label for="watch-category">Category</label><select id="watch-category"><option value="">Any category</option>' +
        categories.map(category => '<option' + (visible && watchState.category === category ? ' selected' : '') + '>' + esc(category) + '</option>').join('') +
        '</select></div><details class="panel"><summary>Select several sources</summary><div class="source-select">' +
        active.map(source => '<label class="source-chip"><input type="checkbox" data-watch-filter value="' + esc(source.id) + '"' +
            (!visible || !watchState.selectedIds || watchState.selectedIds.includes(source.id) ? ' checked' : '') + '>' +
            esc(source.name) + '</label>').join('') + '</div></details>' + '<section id="watch-results">' + watchResults(mode) + '</section>';
}

function watchResults(mode) {
    const visible = watchState.mode === mode;
    const status = visible ? watchState.sources.map(source =>
        '<li>' + esc(source.name) + ' · ' + esc(source.message || (source.count ?? 0) + ' matches') + '</li>').join('') : '';
    const rows = visible ? watchState.rows : [];
    const videos = rows.map((record, index) => ({record, index})).filter(row => row.record.is_video);
    const titles = rows.map((record, index) => ({record, index})).filter(row => !row.record.is_video);
    const section = (heading, list) => list.length ? '<h2>' + heading + '</h2><div class="grid">' +
        list.map(row => watchCard(row.record, row.index)).join('') + '</div>' : '';
    return (visible && watchState.busy ? '<div class="loading">Searching connected sources… <button data-watch="cancel">Cancel search</button></div>' : '') +
        (visible && watchState.error ? '<div class="notice error" role="alert">' + esc(watchState.error) + '</div>' : '') +
        section('Video results', videos) + section('Title matches', titles) +
        (visible && watchState.query && !watchState.busy && !rows.length && !watchState.error
            ? empty('No matching videos or titles', 'Try an alternative title, change the website filter or use Deep Search.') : '') +
        (status ? '<details class="panel"><summary>Source responses</summary><ul>' + status + '</ul></details>' : '') +
        (visible && watchState.more ? '<button data-watch="more">More results</button>' : '');
}

async function searchVideos(query, mode, page = 1) {
    const sourceId = $('watch-source')?.value || '';
    const category = $('watch-category')?.value || '';
    const filters = [...document.querySelectorAll('[data-watch-filter]')];
    const selectedIds = filters.length ? filters.filter(input => input.checked).map(input => input.value) : null;
    const request = ++watchState.request;
    Object.assign(watchState, {query, mode, page, category, sourceId, selectedIds, busy: true, error: '', more: false});
    if (page === 1) Object.assign(watchState, {rows: [], sources: []});
    renderPage();
    try {
        if (watchState.job) await api('deep/cancel', {id: watchState.job});
        const job = await api('watch/start', {query, mode, page, category, sources: sourceId ? [sourceId] : selectedIds});
        watchState.job = job.id;
        while (request === watchState.request) {
            const result = await api('watch/poll', {id: job.id, mode});
            if (request !== watchState.request) return;
            const rows = new Map([...watchState.rows, ...result.results].map(record => [record.id, record]));
            Object.assign(watchState, {rows: [...rows.values()], sources: result.sources, more: result.has_more,
                                      busy: result.status === 'running', error: result.message || ''});
            if (state.view === mode && $('watch-results')) $('watch-results').innerHTML = watchResults(mode);
            if (!watchState.busy) {await reload(); break;}
            await new Promise(resolve => setTimeout(resolve, 300));
        }
    } catch (error) {
        if (request === watchState.request) watchState.error = error.message;
    } finally {
        if (request === watchState.request) {
            watchState.busy = false;
            if (state.view === mode && $('watch-results')) $('watch-results').innerHTML = watchResults(mode);
        }
    }
}

async function showViewing(record) {
    watchState.selected = record;
    watchState.playRequest++;
    const details = [record.year, record.edition, record.release_season, record.episode_count && record.episode_count + ' catalog episodes'].filter(Boolean);
    dialog(record.title, '<div class="watch-title">' + (link(record.thumbnail)
        ? '<img class="watch-cover" src="' + esc(link(record.thumbnail)) + '" alt="">' : '') +
        '<div><div class="meta">' + esc(details.join(' · ')) + '</div><p>' + esc(record.description) + '</p>' +
        ((record.alternatives || []).length ? '<p class="meta">Also known as ' + esc(record.alternatives.join(' · ')) + '</p>' : '') +
        '<button data-watch="save-title">' + (saved(record) ? 'Remove saved title' : 'Save title') + '</button></div></div>' +
        '<section id="watch-episodes"><div class="loading">Finding viewing options…</div></section><section id="watch-player"></section>');
    try {
        const result = await api('watch/details', {record});
        if (record !== watchState.selected || !$('watch-episodes')) return;
        watchState.episodes = result.episodes;
        $('watch-episodes').innerHTML = '<h3>Episodes and videos</h3>' + (result.episodes.length
            ? '<div class="episode-list">' + result.episodes.map((episode, index) =>
                '<button class="episode" data-watch="play" data-index="' + index + '">' +
                '<span>' + esc(episode.number ? 'Episode ' + episode.number + ' · ' + episode.title : episode.title) +
                '</span><small>' + esc(episode.source) + '</small></button>').join('') + '</div>'
            : empty('No viewing options found', 'Try another title edition or add a video website that lists these episodes.')) +
            result.errors.map(error => '<p class="meta">' + esc(error.source + ' · ' + error.message) + '</p>').join('');
    } catch (error) {
        if (record === watchState.selected && $('watch-episodes')) $('watch-episodes').innerHTML = '<div class="notice error">' + esc(error.message) + '</div>';
    }
}

function watchDownload(result) {
    if (!result.formats.length) return '<p class="meta">The source offers viewing through the options above.</p>';
    const formats = result.formats.map(format => '<option value="' + esc(format.id) + '"' + (format.id === result.playing_format_id ? ' selected' : '') + '>' +
        esc([format.height && format.height + 'p', format.label, format.ext.toUpperCase(),
            format.video && !format.audio ? 'video only' : null, bytes(format.size)].filter(Boolean).join(' · ')) + '</option>').join('');
    return '<details class="panel"><summary>Download this video</summary><form data-watch-form="download" data-analysis="' + esc(result.analysis_id) + '">' +
        '<div class="form-grid"><div><label for="watch-format">Format and resolution</label><select id="watch-format" name="format_id">' +
        formats + '</select></div><div><label for="watch-output">Output</label><select id="watch-output" name="output">' +
        '<option value="original">Original</option><option value="mp4">Convert to MP4</option><option value="mp3">Audio MP3</option>' +
        '</select></div></div><label for="watch-destination">Destination folder</label><input name="destination" id="watch-destination" value="' +
        esc(state.data.settings.destination) + '"><button type="button" data-action="pick-folder" data-target="watch-destination">Browse</button>' +
        '<label class="check"><input type="checkbox" name="authorized" required> I am authorized to download this video.</label>' +
        '<button class="primary">Queue download</button></form></details>';
}

async function selectEpisode(index) {
    const episode = watchState.episodes[index];
    const player = $('watch-player');
    if (!episode || !player) return;
    const request = ++watchState.playRequest;
    player.innerHTML = '<div class="loading">Checking the episode source…</div>';
    try {
        const result = await api('watch/play', {ticket: episode.ticket});
        if (request !== watchState.playRequest || player !== $('watch-player')) return;
        let playback = '';
        if (result.playback === 'direct' && /^\/media\/[A-Za-z0-9_-]+$/.test(result.stream)) {
            playback = '<video id="episode-video" controls playsinline preload="metadata" src="' + esc(link(result.direct_url) || result.stream) + '">' +
                (result.subtitles || []).map(track => '<track kind="subtitles" src="' + esc(track.url) + '" srclang="' +
                    esc(track.language) + '" label="' + esc(track.label) + '">').join('') + '</video>' +
                '<label for="play-speed">Speed</label><select id="play-speed"><option>0.5</option><option selected>1</option>' +
                '<option>1.25</option><option>1.5</option><option>2</option></select><p id="play-error" class="inline-error" role="alert"></p>';
        } else if (result.playback === 'embed' && link(result.embed)?.startsWith('https://')) {
            playback = '<iframe title="Official episode player" class="episode-frame" src="' + esc(result.embed) +
                '" referrerpolicy="strict-origin-when-cross-origin" sandbox="allow-scripts allow-same-origin allow-presentation" allow="fullscreen; encrypted-media" allowfullscreen></iframe>';
        }
        const neighbors = '<div class="toolbar">' + (index > 0 ? '<button data-watch="play" data-index="' + (index - 1) +
            '">Previous episode</button>' : '') + (index + 1 < watchState.episodes.length
                ? '<button data-watch="play" data-index="' + (index + 1) + '">Next episode</button>' : '') + '</div>';
        player.innerHTML = '<h3>' + esc(result.episode) + '</h3><div class="meta">' + esc(result.source) + '</div>' +
            '<p>' + esc(result.message) + '</p>' + playback +
            '<p>' + external(result.original, 'Open exact video at source') + '</p>' +
            (result.license ? '<p class="meta">License · ' + esc(result.license) + ' · ' + esc(result.attribution) + '</p>' : '') +
            neighbors + watchDownload(result);
        const video = $('episode-video');
        video?.addEventListener('error', () => {
            if (video.getAttribute('src') !== result.stream) {
                const shouldPlay = !video.paused;
                video.src = result.stream;
                if (shouldPlay) video.play().catch(() => {});
                return;
            }
            if ($('play-error')) $('play-error').textContent = 'This file could not play in your browser. Open the exact video at its source.';
        });
        player.scrollIntoView({block: 'nearest'});
    } catch (error) {
        if (request !== watchState.playRequest || player !== $('watch-player')) return;
        player.innerHTML = '<div class="notice error">' + esc(error.message) + '</div><p>' +
            external(episode.url, 'Open exact video at source') + '</p>';
    }
}

function videoSourcesPage() {
    const cards = state.data.sources.filter(source => source.role !== 'metadata').map(source => {
        const capability = source.video_checks || {};
        const checks = [
            ['Browsing', capability.browsing], ['Search', capability.search], ['Video pages', capability.discovery],
            ['Playback', capability.playback], ['Download', capability.download],
        ].map(([label, value]) => '<li>' + esc(label) + ' · ' + esc(value || 'Unchecked on this PC') + '</li>').join('');
        return '<article class="source-card"><h3>' + esc(source.name) + '</h3><p>' + esc(source.description) +
            '</p><ul class="capabilities">' + checks + '</ul>' + ((capability.error || capability.detail) ? '<p class="inline-error">' + esc(capability.error || capability.detail) + '</p>' : '') +
            '<div class="actions"><label class="toggle"><input type="checkbox" data-enable="' + esc(source.id) + '"' +
            (source.enabled ? ' checked' : '') + '>Enabled</label><button data-watch="test-source" data-id="' + esc(source.id) +
            '">Test viewing</button><button data-browse="' + esc(source.website || source.endpoint) + '">Browse website</button>' + (source.kind === 'website' ? '<button data-watch="edit-website" data-id="' +
            esc(source.id) + '">Edit website</button>' : '') + '</div></article>';
    });
    return title('VIDEO SOURCES', 'Choose where SceneTrace looks', 'Enable video websites and test the options they expose.') +
        '<div class="toolbar"><button class="primary" data-watch="add-website">Add Video Website</button>' +
        '<button data-watch="discover">Find More Sources</button><button data-nav="hub">Metadata & imports</button></div>' +
        '<div class="source-grid">' + cards.join('') + '</div>';
}

document.addEventListener('click', async event => {
    const button = event.target.closest('button[data-watch]');
    if (!button) return;
    const index = Number(button.dataset.index);
    button.disabled = true;
    try {
        if (button.dataset.watch === 'cancel') {
            await api('deep/cancel', {id: watchState.job}); watchState.request++; watchState.busy=false;
            if ($('watch-results')) $('watch-results').innerHTML=watchResults(watchState.mode);
        }
        if (button.dataset.watch === 'title') await showViewing(watchState.rows[index]);
        if (button.dataset.watch === 'play') await selectEpisode(index);
        if (button.dataset.watch === 'more') await searchVideos(watchState.query, watchState.mode, watchState.page + 1);
        if (button.dataset.watch === 'save-title') {
            const record = watchState.selected;
            await api('save', {record, remove: saved(record)});
            await reload();
            button.textContent = saved(record) ? 'Remove saved title' : 'Save title';
        }
        if (button.dataset.watch === 'test-source') {
            button.textContent = 'Testing…';
            const result = await api('watch/test-source', {id: button.dataset.id});
            await reload(true);
            toast(result.message, !result.ok);
        }
        if (button.dataset.watch === 'add-website') websiteWizard();
        if (button.dataset.watch === 'edit-website') websiteWizard(state.data.sources.find(source => source.id === button.dataset.id));
        if (button.dataset.watch === 'discover') websiteDiscovery();
        if (button.dataset.watch === 'tls') {
            const report = await api('network/tls');
            dialog('Internet Archive connection', '<p>' + esc(report.status) + '</p><p>' + esc(report.message || 'The HTTPS request passed verification.') +
                '</p>' + (report.verify_code ? '<p>Certificate code ' + esc(report.verify_code) + '</p>' : ''));
        }
    } catch (error) {
        toast(error.message, true);
    } finally {
        button.disabled = false;
    }
});

document.addEventListener('submit', async event => {
    const form = event.target;
    const action = form.dataset.watchForm;
    if (!action) return;
    event.preventDefault();
    const values = Object.fromEntries(new FormData(form));
    try {
        if (action === 'search' || action === 'home') {
            if (action === 'home') nav('search');
            await searchVideos(values.query, state.view);
        }
        if (action === 'download') {
            await api('download/add', {...values, analysis_id: form.dataset.analysis, authorized: values.authorized === 'on'});
            toast('Download queued. Track it under Downloads.');
        }
    } catch (error) {
        toast(error.message, true);
    }
});
document.addEventListener('change', event => {
    if (event.target.id === 'play-speed' && $('episode-video')) $('episode-video').playbackRate = Number(event.target.value);
});
$('dialog').addEventListener('close', () => {
    const player = $('watch-player');
    if (player) player.replaceChildren();
});

start();

const websiteFields = [
    ['search_pattern', 'Search URL pattern', '/search?q={query}&page={page}'],
    ['query_param', 'Search parameter', 'q'],
    ['page_param', 'Page parameter', 'page'],
    ['result_selector', 'Result selector', 'article.video'],
    ['title_selector', 'Title selector', '.title'],
    ['link_selector', 'Detail link selector', 'a[href]'],
    ['thumbnail_selector', 'Thumbnail selector', 'img'],
    ['description_selector', 'Description selector', '.description'],
    ['episode_selector', 'Episode list selector', '.episode-list li'],
    ['episode_title_selector', 'Episode title selector', '.episode-name'],
    ['episode_link_selector', 'Episode link selector', 'a[href]'],
    ['playback_selector', 'Media selector', 'video source[src]'],
    ['items_path', 'JSON result array path', 'results.items'],
    ['path_prefix', 'Result path prefix', '/videos/'],
];

function websiteWizard(existing = null, website = '') {
    if (existing) {
        showWebsiteConfig({...existing, ...existing.web_config, query: existing.sample_query || ''});
        return;
    }
    dialog('Add Video Website',
        '<p class="meta">1 Website → 2 Inspect → 3 Test → 4 Save</p>' +
        '<p>Enter a public website, a video listing or a feed. SceneTrace will look for an available search method.</p>' +
        '<form data-site-form="inspect"><label for="website-url">Website URL</label><input id="website-url" name="url" type="url" required value="' +
        esc(website) + '" placeholder="https://example.org/videos"><div class="actions"><button class="primary">Inspect website</button>' +
        '<button type="button" data-site="manual">Configure manually</button></div><div id="website-inspection"></div></form>');
}

function showWebsiteConfig(config) {
    const strategies = [
        ['html', 'Public search form or HTML results'], ['listing', 'HTML video listing'],
        ['browse', 'Browsing only'], ['json', 'Public JSON search or listing'], ['feed', 'RSS, Atom or Media RSS'], ['sitemap', 'Video sitemap'],
    ];
    const options = strategies.map(([key, label]) =>
        '<option value="' + key + '"' + (key === config.strategy ? ' selected' : '') + '>' + label + '</option>').join('');
    const fields = websiteFields.map(([key, label, placeholder]) =>
        '<div><label for="website-' + key + '">' + label + '</label><input id="website-' + key + '" name="' + key +
        '" placeholder="' + esc(placeholder) + '" value="' + esc(config[key] || '') + '"></div>').join('');
    const mapping = ['title', 'url', 'description', 'thumbnail', 'alternatives', 'year', 'id'].map(key =>
        '<div><label for="website-map-' + key + '">JSON ' + key + ' field</label><input id="website-map-' + key +
        '" name="map_' + key + '" placeholder="' + key + '" value="' + esc(config.mapping?.[key] || '') + '"></div>').join('');
    dialog(config.id ? 'Edit Video Website' : 'Configure Video Website',
        '<p class="meta">Review the detected settings and test a title. Advanced settings are optional.</p>' +
        (config.findings || []).map(finding => '<div class="notice">' + esc(finding) + '</div>').join('') +
        '<form data-site-form="test" data-id="' + esc(config.id || '') + '"><div class="form-grid">' +
        '<div><label for="website-name">Name</label><input id="website-name" name="name" required value="' + esc(config.name || '') + '"></div>' +
        '<div><label for="website-endpoint">Website or endpoint</label><input id="website-endpoint" name="endpoint" type="url" required value="' +
        esc(config.endpoint || '') + '"></div><div><label for="website-strategy">Connection method</label><select id="website-strategy" name="strategy">' +
        options + '</select></div><div><label for="website-categories">Categories</label><input id="website-categories" name="categories" value="' +
        esc((config.categories || ['video']).join(', ')) + '" placeholder="anime, animation, video"></div></div>' +
        '<details class="panel"><summary>Advanced website configuration</summary><p class="meta">Use {query} and {page} in URL patterns. ' +
        'Set CSS selectors relative to each result or episode. JSON mappings use dotted field paths.</p><div class="form-grid">' +
        fields + mapping + '</div><label class="check"><input type="checkbox" name="render_browser"' +
        (config.render_browser ? ' checked' : '') + '> Render public pages in an isolated Edge or Chromium profile. ' +
        'The website runs its JavaScript only when you enable this option.</label></details>' +
        '<label for="website-query">Sample title or keywords</label><input id="website-query" name="query" required minlength="2" value="' +
        esc(config.query || '') + '"><label for="website-sample">Optional exact video or series page on this website</label>' +
        '<input id="website-sample" name="sample_url" type="url"><div class="actions"><button class="primary">Test integration</button>' +
        (config.id ? '<button type="button" data-site="remove" data-id="' + esc(config.id) + '">Remove website</button>' : '') +
        '</div><div id="website-test"></div></form>');
}

function websiteDiscovery() {
    dialog('Find More Sources', '<p>Search the connector gallery and, if configured, Brave Search for additional video websites.</p>' +
        '<form data-site-form="discover" class="searchbar"><input name="query" aria-label="Describe the video source" required minlength="2" ' +
        'placeholder="Anime websites with searchable episode catalogs"><button class="primary">Find sources</button></form>' +
        '<div id="website-discovery"></div>');
}

function showWebsiteTest(result) {
    const sample = result.sample;
    const direct = sample?.playback === 'direct' ? link(sample.direct_url) : '';
    return '<h3>Integration preview</h3><p>' + esc(result.message) + '</p><ul class="capabilities">' +
        Object.entries(result.checks).map(([key, value]) => '<li>' + esc(key + ' · ' + value) + '</li>').join('') +
        '</ul><ul>' + result.results.map(row => '<li>' + external(row.url, row.title) + '</li>').join('') + '</ul>' +
        (direct ? '<video controls preload="none" class="episode-frame" src="' + esc(direct) + '"></video>' : '') +
        (sample ? '<p>' + external(sample.original, 'Open sample source page') + '</p>' : '') +
        (result.browse_ticket ? '<button type="button" data-site="save" data-ticket="' + esc(result.browse_ticket) + '">Save for browsing</button>' : '') + (result.save_ticket ? '<button type="button" class="primary" data-site="save" data-ticket="' +
            esc(result.save_ticket) + '">Save website</button>' : '');
}

let discoveredWebsites = [];
document.addEventListener('submit', async event => {
    const form = event.target;
    const action = form.dataset.siteForm;
    if (!action) return;
    event.preventDefault();
    const values = Object.fromEntries(new FormData(form));
    const button = form.querySelector('button[type="submit"], button.primary');
    if (button) button.disabled = true;
    try {
        if (action === 'inspect') {
            $('website-inspection').innerHTML = '<p class="loading">Inspecting public website…</p>';
            let detected;
            try {detected = await api('watch/inspect', values);}
            catch (error) {detected = {name: new URL(values.url).hostname, endpoint: values.url, strategy: 'browse', findings: [error.message]};}
            detected.query ||= 'video';
            showWebsiteConfig(detected);
            document.querySelector('[data-site-form="test"]').requestSubmit();
        } else if (action === 'test') {
            $('website-test').innerHTML = '<p class="loading">Searching and checking a sample page…</p>';
            const webConfig = Object.fromEntries(websiteFields.map(([key]) => [key, values[key] || '']));
            Object.assign(webConfig, {strategy: values.strategy, render_browser: values.render_browser === 'on'});
            const mapping = Object.fromEntries(Object.entries(values)
                .filter(([key, value]) => key.startsWith('map_') && value)
                .map(([key, value]) => [key.slice(4), value]));
            const result = await api('watch/test-website', {
                id: form.dataset.id || undefined, name: values.name, endpoint: values.endpoint,
                categories: values.categories.split(',').map(s => s.trim()).filter(Boolean),
                query: values.query, sample_url: values.sample_url, web_config: webConfig, mapping,
            });
            if (!document.contains(form)) return;
            if (JSON.stringify(Object.fromEntries(new FormData(form))) !== JSON.stringify(values)) {
                delete result.save_ticket; delete result.browse_ticket;
                result.message = 'Settings changed during the test. Test again before saving.';
            }
            $('website-test').innerHTML = showWebsiteTest(result);
        } else if (action === 'discover') {
            $('website-discovery').innerHTML = '<p class="loading">Looking for sources…</p>';
            const result = await api('discover', {...values, video_only: true});
            discoveredWebsites = [...result.providers, ...result.candidates];
            $('website-discovery').innerHTML = '<p>' + esc(result.notice) + '</p><p>' +
                external(result.fallback_url, 'Search the web') + '</p><div class="source-grid">' +
                discoveredWebsites.map((source, index) => '<article class="source-card"><h3>' +
                    esc(source.name) + '</h3><p>' + esc(source.description) + '</p><p class="meta">' +
                    esc(source.kind ? 'Built-in connector · Test playback in Video Sources' : 'Discovered website · Integration unverified') +
                    '</p><button type="button" data-site="' + (source.kind ? 'enable' : 'candidate') +
                    '" data-index="' + index + '">' + (source.kind ? 'Enable and test' : 'Inspect website') + '</button></article>').join('') + '</div>';
        }
    } catch (error) {
        const output = $('website-test') || $('website-inspection') || $('website-discovery');
        if (output) output.innerHTML = '<p class="notice error" role="alert">' + esc(error.message) + '</p>';
    } finally {
        if (button) button.disabled = false;
    }
});

document.addEventListener('input', event => {
    if (event.target.closest('form[data-site-form="test"]') && !event.target.closest('#website-test')) {
        $('website-test')?.querySelector('[data-site="save"]')?.remove();
    }
});

document.addEventListener('click', async event => {
    const button = event.target.closest('button[data-site]');
    if (!button) return;
    button.disabled = true;
    try {
        const action = button.dataset.site;
        if (action === 'manual') {
            const value = $('website-url').value;
            const parsed = link(value);
            if (!parsed) throw Error('Enter a public website URL first.');
            showWebsiteConfig({endpoint: parsed, name: new URL(parsed).hostname, strategy: 'html'});
        } else if (action === 'save') {
            const source = await api('watch/save-website', {ticket: button.dataset.ticket});
            $('dialog').close();
            await reload();
            nav('websites');
            toast(source.name + ' is ready for search.');
        } else if (action === 'remove' && confirm('Remove this website from SceneTrace?')) {
            await api('source/delete', {id: button.dataset.id});
            $('dialog').close();
            await reload(true);
        } else if (action === 'candidate') {
            websiteWizard(null, discoveredWebsites[Number(button.dataset.index)].website);
        } else if (action === 'enable') {
            const candidate = discoveredWebsites[Number(button.dataset.index)];
            const savedSource = await api('source/save', {...candidate, enabled: true});
            $('dialog').close();
            await reload(true);
            const test = await api('watch/test-source', {id: savedSource.source.id});
            await reload(true);
            toast(test.message, !test.ok);
        }
    } catch (error) {
        toast(error.message, true);
    } finally {
        button.disabled = false;
    }
});
