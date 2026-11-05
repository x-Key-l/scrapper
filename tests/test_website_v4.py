import pytest
from scenetrace import websites


def test_real_hianime_structure_upgrades_old_saved_selectors(monkeypatch):
    # Minimal regression fixture of the observed public structure, without scripts/assets.
    html = '''<html><head><title>Naruto - Anime Search Results</title></head><body><main>
    <article class="hk-tile"><div class="hk-tile__art"><img src="/poster.webp"><a class="hk-tile__link" href="/details/naruto-e0a2e"></a></div>
    <h3 class="hk-tile__name"><a href="/details/naruto-e0a2e" title="Naruto (TV, 2002)"><span data-en="Naruto" data-jp="NARUTO">Naruto</span></a></h3>
    <p class="hk-tile__meta">TV 2002</p></article></main></body></html>'''
    source = dict(id='site', name='Example', endpoint='https://hianime.ms/', categories=['anime'],
                  web_config=websites.validate(dict(strategy='html', search_pattern='https://hianime.ms/search?q={query}', result_selector=websites.OLD_RESULT_LINKS)))
    monkeypatch.setattr(websites, 'fetch_page', lambda value, render=False:(websites.parse_page(html), value))
    rows, _ = websites.search(source, 'Naruto', 1)
    assert len(rows) == 1 and rows[0]['title'] == 'Naruto'
    assert rows[0]['url'] == 'https://hianime.ms/details/naruto-e0a2e'
    assert rows[0]['year'] == 2002 and 'NARUTO' in rows[0]['alternatives']
    assert websites.search_url(source, 'Naruto', 1) == 'https://hianime.ms/search?q=Naruto'


def test_structure_failure_is_distinct_from_genuine_no_results(monkeypatch):
    source = dict(id='site', name='Example', endpoint='https://example.com', categories=['video'],
                  web_config=websites.validate(dict(strategy='html', search_pattern='https://example.com/search?q={query}')))
    monkeypatch.setattr(websites, 'fetch_page', lambda value, render=False:(websites.parse_page('<h1>Search</h1><script src="app.js"></script>'), value))
    with pytest.raises(websites.WebsiteSearchError) as error:
        websites.search(source, 'missing')
    assert error.value.code in ('javascript_required', 'result_structure')
    monkeypatch.setattr(websites, 'fetch_page', lambda value, render=False:(websites.parse_page('<h1>No results</h1>'), value))
    assert websites.search(source, 'missing')[0] == []
    with pytest.raises(websites.WebsiteSearchError) as error:
        websites.check_restriction(websites.parse_page('<title>Just a moment...</title>'))
    assert error.value.code == 'service_restriction'


def test_numbered_episode_pages_use_observed_public_attributes(monkeypatch):
    source = dict(endpoint='https://hianime.ms/', web_config=websites.validate(dict(strategy='listing')))
    page = websites.parse_page('''<div class="hk-epgrid">
    <a class="hk-ep" data-ep="10" data-name="Later episode" href="/watch-naruto-episode-10-e0a2e">10</a>
    <a class="hk-ep" data-ep="2" data-name="Earlier episode" href="/watch-naruto-episode-2-e0a2e">2</a>
    </div>''')
    monkeypatch.setattr(websites, 'fetch_page', lambda value, render=False:(page, value))
    episodes = websites.episodes(source, 'https://hianime.ms/details/naruto-e0a2e')
    assert [e['number'] for e in episodes] == ['2', '10']
    assert episodes[0]['title'] == 'Earlier episode'
    assert episodes[0]['url'] == 'https://hianime.ms/watch-naruto-episode-2-e0a2e'
