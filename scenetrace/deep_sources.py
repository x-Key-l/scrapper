"""Bounded provider-specific retrieval. Relationships come from provider responses."""
import hashlib
import json
from urllib.parse import urlencode
from . import network, sources
from .model import record
from .deep import terms

MEDIA = '''id title{romaji english native} synonyms description(asHtml:false) startDate{year}
genres coverImage{large} siteUrl duration format episodes season
streamingEpisodes{title thumbnail url site}'''
CHARACTER = '''id name{full native alternative} description(asHtml:false) siteUrl'''


def anime_record(source, value, characters=None):
    titles = value.get('title') or {}
    item = record(source['id'], value['id'], titles.get('english') or titles.get('romaji') or titles.get('native'),
                  alternatives=list(dict.fromkeys([x for x in titles.values() if x] + (value.get('synonyms') or []))),
                  description=value.get('description'), year=(value.get('startDate') or {}).get('year'),
                  category='anime', genres=value.get('genres'), thumbnail=(value.get('coverImage') or {}).get('large'),
                  url=value.get('siteUrl'), duration=(value.get('duration') or 0)*60 or None,
                  external_ids={'anilist': str(value['id'])}, source_name=source['name'],
                  characters=characters or [character_record(c) for c in (value.get('characters') or {}).get('nodes', [])])
    item.update(episode_count=value.get('episodes'), edition=value.get('format'), release_season=value.get('season'),
                episode_links=value.get('streamingEpisodes') or [])
    return item


def character_record(value):
    return dict(name=(value.get('name') or {}).get('full') or '', description=value.get('description') or '', url=value.get('siteUrl') or '')


def retrieve(source, query, analysis, store, page=1, cancelled=lambda: False):
    """Return provider candidates and per-operation evidence; at most three calls/provider."""
    kind = source['kind']
    endpoint = source.get('endpoint', '').rstrip('/')
    cache_config = {k:v for k,v in source.items() if k not in
                    ('health', 'last_sync', 'last_error', 'last_query', 'sync', 'video_checks')}
    def cached(label, operation, ttl=900):
        key = 'deep:' + hashlib.sha256(json.dumps([cache_config, label], sort_keys=True).encode()).hexdigest()
        result = store.cached(key, ttl=ttl)
        if result is None:
            if cancelled():
                return []
            result = sources.paced(source, operation)
            store.cache(key, result)
        return result

    def graphql(body):
        raw = network.json_request(endpoint, body)
        if raw.get('errors'):
            raise network.SourceError('AniList could not complete this catalog query. It may be rate limited; try again later.')
        return raw.get('data') or {}

    if kind == 'anilist' and (analysis.get('character') or analysis.get('character_description')):
        name = analysis.get('character')
        declaration = '($name:String,$page:Int)' if name else '($page:Int)'
        args = 'search:$name,sort:FAVOURITES_DESC' if name else 'sort:FAVOURITES_DESC'
        body = {'query': 'query'+declaration+'{Page(page:$page,perPage:50){characters('+args+'){'+CHARACTER+
                         ' media(type:ANIME,perPage:8,sort:POPULARITY_DESC){nodes{'+MEDIA+'}}}}}',
                'variables': dict(page=page, **({'name': name} if name else {}))}
        output = []
        for character_page in ([page] if name else [(page-1)*2+1, (page-1)*2+2]):
            if cancelled(): break
            body['variables']['page'] = character_page
            raw = cached(['characters', name, character_page], lambda: graphql(body), 86400)
            for character in (raw.get('Page') or {}).get('characters', []) if isinstance(raw, dict) else []:
                person = character_record(character)
                for anime in (character.get('media') or {}).get('nodes', []):
                    output.append(anime_record(source, anime, [person]))
        return output, len(output) >= 50

    if kind == 'anilist' and not analysis.get('title_like'):
        args, variables, declaration = 'type:ANIME,isAdult:false,sort:POPULARITY_DESC', {'page': page}, '$page:Int'
        if analysis.get('genre'):
            args += ',genre:$genre'
            declaration += ',$genre:String'
            variables['genre'] = analysis['genre']
        # Dates are soft ranking clues; a faulty memory cannot remove the answer.
        body = {'query': 'query('+declaration+'){Page(page:$page,perPage:50){pageInfo{hasNextPage} media('+args+'){'+MEDIA+
                         ' characters(perPage:8,sort:ROLE){nodes{'+CHARACTER+'}}}}}', 'variables': variables}
        raw = cached(['plot', analysis.get('genre'), page], lambda: graphql(body), 86400)
        data = raw.get('Page') or {} if isinstance(raw, dict) else {}
        return [anime_record(source, value) for value in data.get('media', [])], bool(data.get('pageInfo', {}).get('hasNextPage'))

    if kind == 'encyclopedia':
        from .encyclopedia import search as search_encyclopedia, WIKI
        def request(params, base=WIKI):
            return cached(['wiki', base, params], lambda: network.json_request(base+'?'+urlencode(params)), 86400)
        return search_encyclopedia(source, query, analysis, page, request)

    if kind == 'tmdb' and analysis.get('actor'):
        if not source.get('token'):
            raise ValueError('Connect the optional TMDB token for filmography search, or enable Wikipedia + Wikidata.')
        headers = {'Authorization': 'Bearer ' + source['token']}
        actor = analysis['actor']
        people = cached(['person', actor], lambda: network.json_request(endpoint+'/search/person?'+urlencode({'query': actor}), headers=headers))
        output = []
        for person in people.get('results', [])[:2]:
            credits = cached(['credits', person['id']], lambda p=person: network.json_request(endpoint+'/person/'+str(p['id'])+'/combined_credits', headers=headers))
            for movie in credits.get('cast', []):
                kind = movie.get('media_type', 'movie')
                output.append(record(source['id'], kind+'/'+str(movie['id']), movie.get('title') or movie.get('name'),
                                     category='movie' if kind == 'movie' else 'series', description=movie.get('overview'),
                                     year=movie.get('release_date') or movie.get('first_air_date'),
                                     url='https://www.themoviedb.org/'+kind+'/'+str(movie['id']),
                                     thumbnail='https://image.tmdb.org/t/p/w500'+movie['poster_path'] if movie.get('poster_path') else '',
                                     cast=[{'name': person['name'], 'description': movie.get('character') or ''}],
                                     external_ids={'tmdb': kind+'/'+str(movie['id'])}, source_name=source['name']))
        return output, False

    # Existing connectors keep their tested semantics. Title-only websites are resolved
    # with identified titles later; sending long paragraphs would misrepresent recall.
    queries = analysis['queries'][:2] or [query]
    output, more = [], False
    for part in queries:
        if cancelled():
            break
        key = 'deep-query:' + hashlib.sha256(json.dumps([cache_config, part, page], sort_keys=True).encode()).hexdigest()
        result = store.cached(key)
        if result is None:
            rows, next_page = sources.search(source, part, page)
            result = {'rows': rows, 'more': next_page}
            store.cache(key, result)
        output.extend(result['rows'])
        more |= result['more']
    return output, more
