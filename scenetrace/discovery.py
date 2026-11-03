"""Documented provider suggestions and optional Brave Search discovery."""
from urllib.parse import urlencode, urlsplit
from . import network
from .sources import GALLERY
from .search import tokens


def find(query, brave_key=''):
    terms = set(tokens(query))
    curated = []
    for s in GALLERY:
        matches = terms & set(tokens(s['name']+' '+s['description']+' '+' '.join(s['categories'])))
        curated.append(dict(s, compatibility='Documented built-in connector; test connection before relying on it',
                            reason=', '.join(sorted(matches)) or 'General video or metadata catalog', tested=False,
                            score=len(matches), api_available=True))
    curated.sort(key=lambda x:-x['score'])
    out = {'providers':curated, 'candidates':[], 'fallback_url':'https://www.google.com/search?'+urlencode({'q':query+' database documented API'}),
           'notice':'Suggestions are drawn from documented integrations. For wider automatic web discovery, add an optional Brave Search API key in Settings, or use Search the web.'}
    if brave_key:
        try:
            raw = network.json_request('https://api.search.brave.com/res/v1/web/search?'+urlencode({'q':query+' database API documentation','count':10}), headers={'X-Subscription-Token':brave_key})
            for x in raw.get('web',{}).get('results',[]):
                out['candidates'].append(dict(name=x.get('title'), website=x.get('url'), description=x.get('description'),
                                              compatibility='Discovered website; API and compatibility unverified', api_available=None,
                                              auth='Consult provider documentation', tested=False))
            out['notice'] = 'Web candidates are unverified. Open their documentation before configuring a connector.'
        except Exception:
            out['notice'] = 'Web discovery is unavailable. Documented connectors and the manual web search remain available.'
    return out
