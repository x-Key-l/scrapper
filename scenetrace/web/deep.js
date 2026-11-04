'use strict';

const deepState = {query: '', hints: {}, rows: [], sources: [], resolution: [], excluded: new Set(),
    currentSource: '', sourceIds: null, page: 1, more: false, id: null, busy: false, stage: '', error: '', sequence: 0};

function deepSearchPage() {
    const enabled = state.data.sources.filter(s => s.enabled);
    const categories = [...new Set(enabled.flatMap(s => s.categories))].sort();
    return title('IDENTIFY, THEN FIND A VIDEO', 'Deep Search',
        'Use a title, character, actor, scene or uncertain memory. Results explain the evidence and look for matching video pages.') +
        '<form data-deep-form="search"><textarea name="query" aria-label="Describe the video you remember" required minlength="2" ' +
        'placeholder="An anime with a white-haired teacher who covers one eye…">' + esc(deepState.query) + '</textarea>' +
        '<div class="toolbar"><button class="primary">' + (deepState.rows.length ? 'Refine search' : 'Search deeply') + '</button>' +
        '<button type="button" data-deep="cancel"' + (!deepState.busy ? ' disabled' : '') + '>Cancel</button>' +
        '<label for="deep-website">Find viewing pages on</label><select id="deep-website" name="current_source"><option value="">All selected video websites</option>' +
        enabled.filter(s => s.role !== 'metadata').map(s => '<option value="' + esc(s.id) + '"' +
            (deepState.currentSource === s.id ? ' selected' : '') + '>' + esc(s.name) + '</option>').join('') + '</select></div>' +
        '<details class="panel"><summary>Optional clues and source selection</summary><div class="form-grid">' +
        '<label>Category<select name="category"><option value="">Any category</option>' + categories.map(c => '<option' +
            (deepState.hints.category === c ? ' selected' : '') + '>' + esc(c) + '</option>').join('') + '</select></label>' +
        '<label>Approximate decade<input name="decade" inputmode="numeric" placeholder="1990" value="' + esc(deepState.hints.decade || '') + '"></label>' +
        '<label>Character name<input name="character" value="' + esc(deepState.hints.character || '') + '"></label>' +
        '<label>Actor name<input name="actor" value="' + esc(deepState.hints.actor || '') + '"></label></div><div class="source-select">' +
        enabled.map(s => '<label class="source-chip"><input type="checkbox" data-deep-source value="' + esc(s.id) + '"' +
            (deepState.sourceIds === null || deepState.sourceIds.includes(s.id) ? ' checked' : '') + '>' + esc(s.name) + '</label>').join('') +
        '</div><p class="meta">Dates and clues affect ranking without excluding a title solely because one detail differs.</p></details></form>' +
        '<div id="deep-progress" aria-live="polite">' + deepProgress() + '</div><div id="deep-results">' + deepResults() + '</div>';
}

function deepProgress() {
    return (deepState.busy ? '<p class="loading">' + esc(deepState.stage || 'Searching…') + '</p>' : '') +
        (deepState.error ? '<p class="notice error" role="alert">' + esc(deepState.error) + '</p>' : '') +
        (deepState.excluded.size ? '<p class="meta">' + deepState.excluded.size + ' candidates excluded. <button class="quiet" data-deep="reset-excluded">Restore candidates</button></p>' : '');
}

function deepResults() {
    const rows = deepState.rows.map((r, i) => ({r, i})).filter(({r}) => !deepState.excluded.has(r.id));
    return '<div class="grid deep-grid">' + rows.map(({r, i}) => {
        const matches = r.viewing_matches || [];
        const video = r.media_urls?.length;
        return '<article class="card"><div class="poster">' + (link(r.thumbnail) ? '<img src="' + esc(link(r.thumbnail)) +
            '" loading="lazy" alt="" referrerpolicy="no-referrer">' : '<span aria-hidden="true">▷</span>') +
            '<span class="badge">' + esc(r.source_name) + '</span></div><div class="card-body"><h3>' + esc(r.title) + '</h3>' +
            '<div class="meta">' + esc([r.year, r.category, r.episode_count && r.episode_count + ' catalog episodes'].filter(Boolean).join(' · ')) +
            '</div><b class="match-label">' + esc(r.relevance_label || 'Candidate match') + '</b><p class="card-description">' +
            esc(r.description || 'The source has no description for this record.') + '</p><details class="evidence"><summary>Why this match</summary><ul>' +
            (r.evidence || []).map(e => '<li>' + esc(e) + '</li>').join('') + '</ul></details><p class="meta">' +
            (matches.length ? matches.length + ' matching video pages found' : video ? 'Source page found · playback checked on selection' : 'Title identification · viewing availability separate') + '</p>' +
            matches.map((m, j) => '<button class="source-result" data-deep="view-page" data-index="' + i + '" data-page="' + j + '">' +
                esc(m.source_name + ' · ' + m.title) + '</button>').join('') +
            '<div class="card-actions"><button class="primary" data-deep="view" data-index="' + i + '">' + (video ? 'View video options' : 'Find viewing options') +
            '</button><button data-deep="exclude" data-index="' + i + '">Not this one</button></div>' +
            (r.source_id === 'itunes' ? '<p class="meta">' + external(r.url, 'View movie on Apple TV') + '</p>' : '') + '</div></article>';
    }).join('') + '</div>' + (!rows.length && deepState.query && !deepState.busy ? empty('No candidates found',
        'Add another clue or connect a catalog with descriptions. Source errors are listed below.') : '') +
        (deepState.more && !deepState.busy ? '<button data-deep="more">Search next catalog page</button>' : '') +
        (deepState.sources.length || deepState.resolution.length ? '<details class="panel"><summary>Source responses</summary><ul>' +
            [...deepState.sources, ...deepState.resolution].map(s => '<li>' + esc(s.name + ' · ' + (s.message || (s.count ?? 0) + ' records · ' + s.status)) +
                '</li>').join('') + '</ul></details>' : '');
}

function updateDeepResults() {
    if (state.view !== 'memory') return;
    if ($('deep-results')) $('deep-results').innerHTML = deepResults();
    if ($('deep-progress')) $('deep-progress').innerHTML = deepProgress();
    const cancel = document.querySelector('[data-deep="cancel"]');
    if (cancel) cancel.disabled = !deepState.busy;
}

async function deepSearch(query, page = 1) {
    if (deepState.id && deepState.busy) await api('deep/cancel', {id: deepState.id});
    const sequence = ++deepState.sequence;
    Object.assign(deepState, {query, page, busy: true, error: '', stage: 'Searching connected sources…', more: false});
    if (page === 1) Object.assign(deepState, {rows: [], sources: [], resolution: []});
    renderPage();
    try {
        const job = await api('deep/start', {query, page, hints: deepState.hints, sources: deepState.sourceIds,
            current_source: deepState.currentSource, excluded: [...deepState.excluded], mode: 'deep'});
        deepState.id = job.id;
        while (sequence === deepState.sequence) {
            const result = await api('deep/poll', {id: job.id});
            if (sequence !== deepState.sequence) return;
            deepState.rows = page === 1 ? result.results : [...new Map([...deepState.rows, ...result.results].map(r => [r.id, r])).values()];
            Object.assign(deepState, {sources: result.sources, resolution: result.resolution_sources || [], stage: result.stage,
                more: result.has_more, error: result.message || '', busy: result.status === 'running'});
            updateDeepResults();
            if (!deepState.busy) {await reload(); break;}
            await new Promise(resolve => setTimeout(resolve, 350));
        }
    } catch (error) {
        if (sequence === deepState.sequence) {deepState.error = error.message; deepState.busy = false; updateDeepResults();}
    }
}

document.addEventListener('submit', event => {
    if (!event.target.dataset.deepForm) return;
    event.preventDefault();
    const data = new FormData(event.target);
    deepState.hints = Object.fromEntries(['category', 'decade', 'character', 'actor'].map(k => [k, data.get(k) || '']));
    deepState.currentSource = data.get('current_source') || '';
    deepState.sourceIds = [...document.querySelectorAll('[data-deep-source]:checked')].map(x => x.value);
    deepSearch(data.get('query')).catch(error => toast(error.message, true));
});

document.addEventListener('click', async event => {
    const button = event.target.closest('[data-deep]');
    if (!button) return;
    const record = deepState.rows[Number(button.dataset.index)];
    try {
        if (button.dataset.deep === 'view') return showViewing(record);
        if (button.dataset.deep === 'view-page') return showViewing(record.viewing_matches[Number(button.dataset.page)]);
        if (button.dataset.deep === 'exclude') {deepState.excluded.add(record.id); return updateDeepResults();}
        if (button.dataset.deep === 'reset-excluded') {deepState.excluded.clear(); return deepSearch(deepState.query);}
        if (button.dataset.deep === 'more') return deepSearch(deepState.query, deepState.page + 1);
        if (button.dataset.deep === 'cancel') {
            await api('deep/cancel', {id: deepState.id});
            deepState.sequence++;
            deepState.busy = false;
            deepState.stage = 'Search cancelled';
            updateDeepResults();
        }
    } catch (error) {toast(error.message, true);}
});

if (window.chrome?.webview) window.chrome.webview.addEventListener('message', async event => {
    const value = event.data;
    if (!value || !['deep-all', 'deep-site', 'quick-site', 'add-source', 'inspect', 'save-page'].includes(value.action)) return;
    try {
        await reload();
        const safe = link(value.url);
        const source = safe && state.data.sources.find(s => s.kind === 'website' && link(s.endpoint) && new URL(s.endpoint).origin === new URL(safe).origin);
        if (value.action === 'deep-all' || value.action === 'deep-site') {
            deepState.currentSource = value.action === 'deep-site' && source ? source.id : '';
            nav('memory');
            if (value.action === 'deep-site' && !source) toast('This website is not connected for search. Use Add website as source to test it.');
        } else if (value.action === 'quick-site') {
            if (source) {watchState.sourceId = source.id; watchState.mode = 'search'; nav('search');}
            else {nav('websites'); toast('Add and test this website before searching it automatically.');}
        } else if (value.action === 'add-source' && safe) {
            websiteWizard(null, safe);
        } else if (value.action === 'inspect' && safe) {
            nav('link');
            const input = document.querySelector('form[data-form="analyze"] input');
            if (input) {input.value = safe; input.form.requestSubmit();}
        } else if (value.action === 'save-page' && safe) {
            await api('browser/bookmark', {url: safe, title: value.title || safe});
            toast('Page saved to bookmarks.');
        }
    } catch (error) {toast(error.message, true);}
});
