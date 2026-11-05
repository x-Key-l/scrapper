"""Live v4 regressions. Report each capability independently and retain evidence."""
import json
from pathlib import Path
import sys
import tempfile
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scenetrace import websites, sources, network
from scenetrace.app import App
from scenetrace.deep_sources import retrieve
from scenetrace.deep import understand, rank
from scenetrace.search import deduplicate

out = Path('artifacts/v4-live')
out.mkdir(parents=True, exist_ok=True)
report = {'website_tests': [], 'deep_catalog_tests': []}
corpus = []
with tempfile.TemporaryDirectory() as folder:
    app = App(folder, None)
    try:
        for name, endpoint, query in [('HiAnime', 'https://hianime.ms/', 'Naruto'),
                                     ('W3Schools', 'https://www.w3schools.com/html/html5_video.asp', 'video')]:
            test = {'name':name, 'url':endpoint, 'query':query}
            try:
                config = websites.inspect(endpoint)
                source = dict(id='live-'+name, name=name, kind='website', role='media', enabled=True, categories=['anime' if name=='HiAnime' else 'educational'],
                              endpoint=config['endpoint'], web_config=websites.validate(config))
                test['search_url'] = websites.search_url(source, query, 1)
                result = app.viewing.test_website(dict(source, query=query))
                test.update({k:v for k,v in result.items() if k not in ('save_ticket', 'browse_ticket')})
                if result.get('results'):
                    page, _ = websites.fetch_page(result['results'][0]['url'])
                    (out/(name.lower()+'-detail.html')).write_text(str(page), encoding='utf-8')
                if name == 'HiAnime':
                    assert any('naruto' in r['title'].lower() for r in result['results']), 'Naruto results not retrieved'
                    assert '/search?q=Naruto' in test['search_url']
                    test['regression'] = 'Original /details/ selector omission fixed; exact title links retrieved'
            except Exception as error:
                test['error'] = str(error)
            report['website_tests'].append(test)
        for kind, query, hints in [
            ('anilist','Anime with a white-haired teacher who covers one eye',{}),
            ('anilist','An anime where a boy has a powerful creature sealed inside him',{'category':'anime','genre':'Action'}),
            ('encyclopedia','An old action movie with Jackie Chan where he fights criminals in a city',{}),
            ('tvmaze','Nartuo',{}),
        ]:
            check = {'source':kind, 'query':query}
            start = time.perf_counter()
            try:
                rows, more = retrieve(app.source(kind), query, understand(query,hints), app.store)
                rows = deduplicate(rows)
                corpus.extend(rows)
                ranked = rank(query, rows, understand(query,hints))
                check.update(count=len(rows), seconds=round(time.perf_counter()-start,3),
                             top_ten=[{'title':r['title'],'id':r['id'],'evidence':r['evidence']} for r in ranked[:10]])
                app.store.put_records(rows)
            except Exception as error:
                check['error'] = str(error)
            report['deep_catalog_tests'].append(check)
    finally:
        app.close()
(out/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
(out/'corpus.json').write_text(json.dumps(deduplicate(corpus)), encoding='utf-8')
