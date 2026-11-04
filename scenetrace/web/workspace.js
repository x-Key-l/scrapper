'use strict';

const historyState = {entries: [], query: '', offset: 0, more: false, undo: null, selected: new Set(), loading: false};

function recentSearches() {
    return '<div class="history">' + state.data.history.slice(0, 8).map(h =>
        '<span class="history-item"><button data-action="history" data-id="' + h.id + '">' + esc(h.query) +
        '</button><button class="quiet" data-history="delete" data-id="' + h.id +
        '" aria-label="Delete search ' + esc(h.query) + '">×</button></span>').join('') + '</div>';
}

function historyPage() {
    const settings = state.data.settings;
    return title('YOUR ACTIVITY', 'History', 'Find a past search or remove the entries you no longer need.') +
        '<form data-workspace-form="history-search" class="searchbar"><input name="query" aria-label="Search history" value="' +
        esc(historyState.query) + '" placeholder="Search your history"><button>Find</button></form>' +
        '<div class="toolbar"><button data-history="selected">Delete selected</button><button data-history="all">Clear search history</button>' +
        (historyState.undo ? '<button data-history="undo">Undo deletion</button>' : '') + '</div>' +
        '<div id="history-rows">' + (historyState.loading ? '<p class="loading">Loading history…</p>' : '') +
        historyState.entries.map(h => '<div class="history-row"><input type="checkbox" data-history-select="' + h.id +
            '" aria-label="Select search ' + esc(h.query) + '"' + (historyState.selected.has(h.id) ? ' checked' : '') + '>' +
            '<button class="history-query" data-history="repeat" data-id="' + h.id + '">' + esc(h.query) +
            '<small>' + esc(h.mode) + ' · ' + esc(new Date(h.updated * 1000).toLocaleString()) + '</small></button>' +
            '<button class="quiet" data-history="delete" data-id="' + h.id + '" aria-label="Delete search ' + esc(h.query) + '">×</button></div>').join('') +
        (!historyState.entries.length && !historyState.loading ? empty('No matching history', 'Your recording preferences are below.') : '') + '</div>' +
        (historyState.more ? '<button data-history="more">More history</button>' : '') +
        '<details class="panel"><summary>History preferences</summary><form data-workspace-form="history-settings" class="form-grid">' +
        '<label><input type="checkbox" name="record_history"' + (settings.record_history ? ' checked' : '') + '> Record future searches</label>' +
        '<label><input type="checkbox" name="record_browsing"' + (settings.record_browsing ? ' checked' : '') + '> Record website visits</label>' +
        '<label>Keep searches for this many days<input type="number" name="retention" min="0" value="' + settings.history_retention_days +
        '"><small>Use 0 to keep searches until you delete them.</small></label><button class="primary">Save preferences</button></form></details>' +
        '<details class="panel"><summary>Browsing history</summary><button data-history="browsing">Show website visits</button><div id="browsing-history"></div></details>';
}

async function loadHistory(append = false) {
    historyState.loading = true;
    const result = await api('history/list', {query: historyState.query, offset: append ? historyState.offset + 100 : 0});
    historyState.offset = append ? historyState.offset + 100 : 0;
    historyState.entries = append ? [...historyState.entries, ...result.entries] : result.entries;
    historyState.more = result.has_more;
    historyState.loading = false;
    if (state.view === 'history') renderPage();
}

async function deleteSearchHistory(ids, clear = false) {
    if ((clear || ids.length > 1) && !confirm(clear ? 'Delete all search history?' : 'Delete these ' + ids.length + ' searches?')) return;
    historyState.undo = await api('history/delete', {ids, clear});
    historyState.selected.clear();
    await reload(true);
    await loadHistory();
    toast('Search history deleted. Undo is available in History for 60 seconds.');
}

function nativeCommand(action, values = {}) {
    if (window.chrome?.webview && state.data.settings.native_browser) {
        window.chrome.webview.postMessage({action, ...values});
        return true;
    }
    return false;
}

function openWebsite(value) {
    const safe = link(value);
    if (!safe) throw Error('Enter a full http:// or https:// website address.');
    if (!nativeCommand('open', {url: safe})) window.open(safe, '_blank', 'noopener,noreferrer');
}

function browserPage() {
    return title('YOUR WEBSITES', 'Browser', state.data.settings.native_browser
        ? 'Open a website in a tab. Use the top toolbar to search, inspect a page or add it as a source.'
        : 'Open a website in your browser. The Windows application includes tabs when WebView2 is available.') +
        '<form data-workspace-form="browse" class="searchbar"><input name="url" type="url" required aria-label="Website address" placeholder="https://example.org"><button class="primary">Open website</button></form>' +
        '<div class="section-title"><h2>Video websites</h2><button data-watch="add-website">Add Video Website</button></div><div class="source-grid">' +
        state.data.sources.filter(s => s.role !== 'metadata' && (s.website || s.endpoint)).map(s =>
            '<article class="source-card"><h3>' + esc(s.name) + '</h3><p>' + esc(s.description) +
            '</p><button data-browse="' + esc(s.website || s.endpoint) + '">Browse website</button></article>').join('') +
        '</div><h2>Bookmarks</h2>' + ((state.data.bookmarks || []).map(b => '<div class="history-row"><button class="history-query" data-browse="' +
            esc(b.url) + '">' + esc(b.title || b.url) + '</button><button data-bookmark-remove="' + esc(b.url) +
            '" aria-label="Remove bookmark ' + esc(b.title || b.url) + '">×</button></div>').join('') || '<p class="muted">Use the star in the browser toolbar to bookmark a page.</p>');
}

document.addEventListener('click', async event => {
    const button = event.target.closest('[data-history], [data-browse], [data-bookmark-remove]');
    if (!button) return;
    try {
        if (button.dataset.browse) return openWebsite(button.dataset.browse);
        if (button.dataset.bookmarkRemove) {
            await api('browser/bookmark', {url: button.dataset.bookmarkRemove, remove: true});
            return reload(true);
        }
        const action = button.dataset.history;
        if (action === 'delete') return await deleteSearchHistory([Number(button.dataset.id)]);
        if (action === 'selected') {
            if (!historyState.selected.size) return toast('Select one or more searches.');
            return await deleteSearchHistory([...historyState.selected]);
        }
        if (action === 'all') return await deleteSearchHistory([], true);
        if (action === 'undo') {
            await api('history/undo', {token: historyState.undo.undo_token});
            historyState.undo = null;
            await reload();
            return loadHistory();
        }
        if (action === 'more') return await loadHistory(true);
        if (action === 'repeat') {
            const entry = historyState.entries.find(h => h.id === Number(button.dataset.id));
            if (entry.mode === 'memory' || entry.mode === 'deep') {nav('memory'); return deepSearch(entry.query);}
            nav('search'); return searchVideos(entry.query, 'search');
        }
        if (action === 'browsing') {
            const result = await api('browser/history');
            $('browsing-history').innerHTML = result.entries.map(h => '<div class="history-row"><button data-browse="' +
                esc(h.url) + '">' + esc(h.title || h.url) + '</button><small>' + esc(new Date(h.updated * 1000).toLocaleString()) + '</small></div>').join('');
        }
    } catch (error) {toast(error.message, true);}
});

document.addEventListener('change', event => {
    if (!event.target.dataset.historySelect) return;
    const id = Number(event.target.dataset.historySelect);
    if (event.target.checked) historyState.selected.add(id); else historyState.selected.delete(id);
});

document.addEventListener('submit', async event => {
    const form = event.target;
    if (!form.dataset.workspaceForm) return;
    event.preventDefault();
    const data = new FormData(form);
    try {
        if (form.dataset.workspaceForm === 'browse') return openWebsite(data.get('url'));
        if (form.dataset.workspaceForm === 'history-search') {historyState.query = data.get('query'); return loadHistory();}
        if (form.dataset.workspaceForm === 'history-settings') {
            await api('settings', {record_history: data.has('record_history'), record_browsing: data.has('record_browsing'),
                                  history_retention_days: Number(data.get('retention'))});
            await reload();
            await loadHistory();
            toast('History preferences saved.');
        }
    } catch (error) {toast(error.message, true);}
});
