import threading
import time
from types import SimpleNamespace
from scenetrace.deep import rank, understand
from scenetrace.model import record
from scenetrace.search import SearchEngine, deduplicate
from scenetrace.sessions import SearchSessions
from scenetrace.store import Store


def test_exact_title_is_not_confused_with_numbered_films():
    rows = [record('a', 2, 'Naruto the Movie 2', alternatives=['Naruto Movie 2']), record('a', 1, 'Naruto')]
    assert rank('Naruto', rows)[0]['title'] == 'Naruto'


def test_encyclopedia_requires_actual_cast_credit():
    from scenetrace.encyclopedia import search
    def response(params, base=None):
        if params['action'] == 'wbsearchentities':
            return {'search':[{'id':'Q1','description':'Actor'}]}
        if params['action'] == 'query':
            return {'query':{'pages':{'2':{'title':'Example Film', 'extract':'An action story.', 'pageprops':{'wikibase_item':'Q2'}},
                                      '3':{'title':'Mention Only', 'pageprops':{'wikibase_item':'Q3'}}}}}
        return {'entities':{'Q2':{'labels':{'en':{'value':'Example Film'}}, 'descriptions':{'en':{'value':'1985 film'}},
                                  'claims':{'P161':[{'mainsnak':{'datavalue':{'value':{'id':'Q1'}}}}]}},
                            'Q3':{'labels':{'en':{'value':'Mention Only'}}, 'descriptions':{'en':{'value':'1985 film'}}}}}
    rows, _ = search({'id':'encyclopedia','name':'Wikipedia + Wikidata'}, 'An action movie with Jane Actor',
                     {'actor':'Jane Actor'}, request=response)
    assert len(rows) == 1 and rows[0]['cast'][0]['name'] == 'Jane Actor'
    assert rows[0]['media_urls'] == [] and rows[0]['status'] == 'Metadata only'


def test_fuzzy_alternative_and_character_evidence():
    naruto = record('catalog', 1, 'Naruto', category='anime', year=2002, alternatives=['NARUTO'],
                    characters=[{'name':'Kakashi Hatake', 'description':'A white-haired teacher who covers his left eye.'}],
                    description='A boy trains as a ninja. A powerful demon fox is sealed inside him.')
    other = record('catalog', 2, 'The Teacher', description='A schoolteacher in a city.', year=1990)
    titan = record('catalog', 3, 'Attack on Titan', alternatives=['Shingeki no Kyojin', '進撃の巨人'])
    records = [other, titan, naruto]
    for query in ('Nartuo', 'Narut', 'Anime with a white-haired teacher who covers one eye',
                  'An anime where a boy joins fighters with a powerful creature inside him'):
        result = rank(query, records)
        assert result[0]['id'] == naruto['id']
        assert result[0]['evidence'] and 'confidence' not in result[0]
    assert rank('進撃の巨人', records)[0]['id'] == titan['id']
    assert rank('shingeki kyojin', records)[0]['id'] == titan['id']
    assert rank('white-haired teacher', records, understand('white-haired teacher', {'decade':'1980'}))[0]['id'] == naruto['id']


def test_actor_and_combined_clues_are_evidence_not_hard_filters():
    action = record('movies', 1, 'Police Story', year=1985, description='Police fight criminals in the city.',
                    cast=[{'name':'Jackie Chan','description':'Police inspector'}])
    drama = record('movies', 2, 'City Roads', description='A drama about a family in the city.')
    query = 'An old action movie with Jackie Chan where he fights criminals in a city in the 1990s'
    analysis = understand(query)
    assert analysis['actor'] == 'Jackie Chan'
    result = rank(query, [drama, action], analysis)
    assert result[0]['id'] == action['id'] and any('Jackie Chan' in x for x in result[0]['evidence'])
    assert len(result) == 2


def test_fuzzy_index_recall_and_character_merge(tmp_path):
    store = Store(tmp_path)
    base = record('catalog', 1, 'Naruto', external_ids={'anilist':'20'}, characters=[{'name':'Kakashi', 'description':'Teacher'}])
    store.put_records([base])
    assert store.local_search(store.expanded_terms(['nartuo']), ['catalog'])[0]['title'] == 'Naruto'
    assert store.local_search(['kakashi'], ['catalog'])
    extra = dict(base, characters=[{'name':'Naruto Uzumaki','description':'Young ninja'}])
    merged = deduplicate([base, extra])
    assert len(merged) == 1 and len(merged[0]['characters']) == 2


def test_progressive_search_and_cancel_retains_received_results(tmp_path, monkeypatch):
    from scenetrace import sources
    store = Store(tmp_path)
    for ident in ('fast', 'slow'):
        store.put_source(dict(id=ident, name=ident, enabled=True, kind='rest', role='metadata', categories=['video']))
    gate = threading.Event()
    def fake(source, query, page=1, memory=None):
        if source['id'] == 'slow':
            gate.wait(4)
        return [record(source['id'], 1, 'Ocean story')], False
    monkeypatch.setattr(sources, 'search', fake)
    engine = SearchEngine(store)
    sessions = SearchSessions(SimpleNamespace(store=store, search=engine))
    try:
        ident = sessions.start({'query':'Ocean', 'mode':'quick'})['id']
        deadline = time.monotonic()+2
        while time.monotonic() < deadline:
            value = sessions.poll(ident)
            if value['results']:
                break
            time.sleep(.02)
        assert value['status'] == 'running' and value['results'][0]['source_id'] == 'fast'
        sessions.cancel(ident)
        assert sessions.poll(ident)['status'] == 'cancelled'
        assert sessions.poll(ident)['results']
    finally:
        gate.set()
        sessions.close()
        engine.close()
