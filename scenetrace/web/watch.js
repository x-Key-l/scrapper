'use strict';

const watchState = {
    query: '', category: '', page: 1, mode: '', busy: false, more: false,
    rows: [], sources: [], episodes: [], selected: null, request: 0, result: null,
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
        (watchState.sourceId === source.id ? ' selected' : '') + '>' + esc(source.name) + '</option>').join('');
    const status = visible ? watchState.sources.map(source =>
        '<li>' + esc(source.name) + ' · ' + esc(source.message || (source.count ?? 0) + ' matches') + '</li>').join('') : '';
    const rows = visible ? watchState.rows : [];
    const videos = rows.map((record, index) => ({record, index})).filter(row => row.record.is_video);
    const titles = rows.map((record, index) => ({record, index})).filter(row => !row.record.is_video);
    const section = (heading, list) => list.length ? '<h2>' + heading + '</h2><div class="grid">' +
        list.map(row => watchCard(row.record, row.index)).join('') + '</div>' : '';
    return title(anime ? 'ANIME' : 'VIDEO DISCOVERY', anime ? 'Find anime to watch' : 'Find videos on your websites',
        anime ? 'Search by English, Japanese or Romaji title. Choose a result to see available episode pages.' :
            'Search connected video websites. Open a result to see the source player or available files.') +
        '<form data-watch-form="search" class="searchbar"><input name="query" aria-label="Video search" required minlength="2" value="' +
        esc(visible ? watchState.query : '') + '" placeholder="' + (anime ? 'Try Pokémon or Pocket Monsters' : 'Try Caminandes or a topic') +
        '"><button class="primary">Search</button></form><div class="toolbar"><label for="watch-source">Website</label>' +
        '<select id="watch-source"><option value="">All enabled sources</option>' + options + '</select>' +
        '<label for="watch-category">Category</label><select id="watch-category"><option value="">Any category</option>' +
        categories.map(category => '<option' + (watchState.category === category ? ' selected' : '') + '>' + esc(category) + '</option>').join('') +
        '</select></div>' + (visible && watchState.busy ? '<div class="loading">Searching connected sources…</div>' : '') +
        (visible && watchState.error ? '<div class="notice error" role="alert">' + esc(watchState.error) + '</div>' : '') +
        section('Video results', videos) + section('Title matches', titles) +
        (visible && watchState.query && !watchState.busy && !rows.length && !watchState.error
            ? empty('No matching videos or titles', 'Try an alternative title, change the website filter or use Memory Search.') : '') +
        (status ? '<details class="panel"><summary>Source responses</summary><ul>' + status + '</ul></details>' : '') +
        (visible && watchState.more ? '<button data-watch="more">More results</button>' : '');
}

async function searchVideos(query, mode, page = 1) {
    const sourceId = $('watch-source')?.value || '';
    const category = $('watch-category')?.value || '';
    const request = ++watchState.request;
    Object.assign(watchState, {query, mode, page, category, sourceId, busy: true, error: '', more: false});
    if (page === 1) Object.assign(watchState, {rows: [], sources: []});
    renderPage();
    try {
        const result = await api('watch/search', {query, mode, page, category, sources: sourceId ? [sourceId] : null});
        if (request !== watchState.request) return;
        const rows = new Map([...watchState.rows, ...result.results].map(record => [record.id, record]));
        Object.assign(watchState, {rows: [...rows.values()], sources: result.sources, more: result.has_more});
    } catch (error) {
        if (request === watchState.request) watchState.error = error.message;
    } finally {
        if (request === watchState.request) {
            watchState.busy = false;
            if (state.view === mode) renderPage();
        }
    }
}

async function showViewing(record) {
    watchState.selected = record;
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
        if ($('watch-episodes')) $('watch-episodes').innerHTML = '<div class="notice error">' + esc(error.message) + '</div>';
    }
}

function watchDownload(result) {
    if (!result.formats.length) return '<p class="meta">The source offers viewing through the options above.</p>';
    const formats = result.formats.map(format => '<option value="' + esc(format.id) + '">' +
        esc([format.height && format.height + 'p', format.label, format.ext.toUpperCase(),
            format.video && !format.audio ? 'video only' : null, bytes(format.size)].filter(Boolean).join(' · ')) + '</option>').join('');
    return '<details class="panel"><summary>Download this video</summary><form data-watch-form="download">' +
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
    player.innerHTML = '<div class="loading">Checking the episode source…</div>';
    try {
        const result = await api('watch/play', {ticket: episode.ticket});
        if (player !== $('watch-player')) return;
        watchState.result = result;
        let playback = '';
        if (result.playback === 'direct' && /^\/media\/[A-Za-z0-9_-]+$/.test(result.stream)) {
            playback = '<video id="episode-video" controls playsinline preload="metadata" src="' + esc(result.stream) + '">' +
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
        $('episode-video')?.addEventListener('error', () => {
            if ($('play-error')) $('play-error').textContent = 'This file could not play in your browser. Open the exact video at its source.';
        });
        player.scrollIntoView({block: 'nearest'});
    } catch (error) {
        player.innerHTML = '<div class="notice error">' + esc(error.message) + '</div><p>' +
            external(episode.url, 'Open exact video at source') + '</p>';
    }
}

function videoSourcesPage() {
    const cards = state.data.sources.filter(source => source.role !== 'metadata').map(source => {
        const capability = source.video_checks || {};
        const checks = [
            ['Search', capability.search], ['Video pages', capability.discovery],
            ['Playback', capability.playback], ['Download', capability.download],
        ].map(([label, value]) => '<li>' + esc(label) + ' · ' + esc(value || 'Unchecked on this PC') + '</li>').join('');
        return '<article class="source-card"><h3>' + esc(source.name) + '</h3><p>' + esc(source.description) +
            '</p><ul class="capabilities">' + checks + '</ul>' + (capability.error ? '<p class="inline-error">' + esc(capability.error) + '</p>' : '') +
            '<div class="actions"><label class="toggle"><input type="checkbox" data-enable="' + esc(source.id) + '"' +
            (source.enabled ? ' checked' : '') + '>Enabled</label><button data-watch="test-source" data-id="' + esc(source.id) +
            '">Test viewing</button>' + (source.kind === 'website' ? '<button data-watch="edit-website" data-id="' +
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
            await api('download/add', {...values, analysis_id: watchState.result.analysis_id, authorized: values.authorized === 'on'});
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
