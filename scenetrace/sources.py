"""Database adapters. Configurations are data: no eval, scripts, or plugins."""
import copy
import hashlib
import json
import re
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from urllib.parse import urlencode, quote, urlsplit, urljoin
from . import network
from .model import record, text, field, flatten, url

GALLERY = [
    dict(id='pokemon-tv', name='Pokémon TV', kind='pokemon-tv', role='media', categories=['anime'],
         description='Official English Indigo League episode pages. Starter selection of episodes 1–3.',
         website='https://www.youtube.com/@OfficialPokemonTV', endpoint='https://www.youtube.com', auth='None'),
    dict(id='open-animation', name='Caminandes on Commons', kind='open-animation', role='hybrid', categories=['animation'],
         description='Three open-license animated episodes with playable formats from Wikimedia Commons.',
         website='https://commons.wikimedia.org/wiki/Category:Caminandes', endpoint='https://commons.wikimedia.org', auth='None'),

    dict(id='tvmaze', name='TVmaze', kind='tvmaze', role='metadata', categories=['series', 'anime'], description='Television and animation titles, summaries, genres and external IDs.', website='https://www.tvmaze.com', docs='https://www.tvmaze.com/api', endpoint='https://api.tvmaze.com', auth='None'),
    dict(id='anilist', name='AniList', kind='anilist', role='metadata', categories=['anime'], description='Anime titles, alternative names, synopses and artwork.', website='https://anilist.co', docs='https://docs.anilist.co', endpoint='https://graphql.anilist.co', auth='None'),
    dict(id='archive', name='Internet Archive', kind='archive', role='hybrid', categories=['movie', 'documentary', 'archive', 'educational', 'music', 'video'], description='Public archival catalogs with item pages and available media files.', website='https://archive.org', docs='https://archive.org/developers', endpoint='https://archive.org', auth='None'),
    dict(id='commons', name='Wikimedia Commons', kind='commons', role='hybrid', categories=['documentary', 'archive', 'educational', 'video'], description='Open media with source attribution and license information.', website='https://commons.wikimedia.org', docs='https://www.mediawiki.org/wiki/Extension:TimedMediaHandler/API', endpoint='https://commons.wikimedia.org/w/api.php', auth='None'),
    dict(id='peertube', name='PeerTube / Sepia Search', kind='peertube', role='media', categories=['video', 'educational', 'music'], description='Search public federated videos. Individual instances decide availability.', website='https://sepiasearch.org', docs='https://docs.joinpeertube.org/api-rest-reference.html', endpoint='https://sepiasearch.org', auth='None'),
    dict(id='tmdb', name='TMDB', kind='tmdb', role='metadata', categories=['movie', 'series'], description='Movie and television metadata. Optional personal API read token required.', website='https://www.themoviedb.org', docs='https://developer.themoviedb.org/reference/search-multi', endpoint='https://api.themoviedb.org/3', auth='API Read Access Token'),
]
KINDS = {x['kind'] for x in GALLERY} | {'rest', 'graphql', 'feed', 'local'}
ALIASES = {
    'id': ['id', 'identifier', 'uuid', 'guid'], 'title': ['title', 'name', 'original_title'],
    'description': ['description', 'summary', 'synopsis', 'overview', 'plot'],
    'year': ['year', 'release_date', 'premiered', 'date'], 'url': ['url', 'link', 'website'],
    'thumbnail': ['thumbnail', 'poster', 'image', 'image.original', 'coverImage.large'],
    'media_url': ['media_url', 'video_url', 'download_url', 'enclosure'],
    'duration': ['duration', 'runtime'], 'category': ['category', 'type'],
    'genres': ['genres', 'genre'], 'creators': ['creators', 'creator', 'author'],
    'license': ['license', 'licenseurl'], 'imdb': ['imdb', 'imdb_id', 'external_ids.imdb'],
}


def defaults(store):
    existing = {s['id'] for s in store.sources()}
    initialized = store.setting('gallery_initialized', False)
    video_initialized = store.setting('video_gallery_initialized', False)
    for source in GALLERY:
        fresh = not initialized or (
            not video_initialized and source['kind'] in ('pokemon-tv', 'open-animation')
        )
        if fresh and source['id'] not in existing:
            health = 'Optional key needed' if source['id'] == 'tmdb' else 'Untested'
            store.put_source(dict(source, enabled=source['id'] != 'tmdb', health=health, last_sync=None, mapping={}))
    if not initialized:
        store.set_setting('gallery_initialized', True)
    if not video_initialized:
        store.set_setting('video_gallery_initialized', True)


def validate(config, previous=None):
    allowed = {'id', 'name', 'kind', 'role', 'categories', 'description', 'website', 'docs', 'endpoint', 'auth',
               'enabled', 'token', 'mapping', 'items_path', 'query_param', 'page_param', 'page_size_param',
               'page_size', 'graphql', 'variables', 'params', 'auth_header', 'auth_prefix', 'since_param',
               'local_path', 'table', 'health', 'last_sync', 'last_error', 'last_query', 'sync'}
    c = {k: copy.deepcopy(v) for k, v in config.items() if k in allowed}
    c['id'] = previous['id'] if previous else 'user-' + uuid.uuid4().hex
    c['name'] = text(c.get('name'))[:160]
    if not c['name']:
        raise ValueError('Give this source a name.')
    if c.get('kind') not in KINDS:
        raise ValueError('Choose a supported connector type.')
    if c.get('role') not in ('metadata', 'media', 'hybrid'):
        raise ValueError('Choose Metadata, Media or Hybrid.')
    if c['kind'] != 'local' and not url(c.get('endpoint')):
        raise ValueError('Enter the full public API or feed URL.')
    if not isinstance(c.get('mapping', {}), dict):
        raise ValueError('Field mapping must be an object.')
    for name in ('variables', 'params'):
        if name in c and not isinstance(c[name], dict):
            raise ValueError(name + ' must be a JSON object.')
    c['enabled'] = bool(c.get('enabled', True))
    c.setdefault('health', 'Untested')
    c.setdefault('categories', ['video'])
    c.setdefault('description', 'User-connected source')
    if not isinstance(c['categories'], list) or not all(isinstance(x, str) for x in c['categories']):
        raise ValueError('Categories must be a list of names.')
    if previous:
        if not c.get('token'):
            c['token'] = previous.get('token', '')
        for name in ('last_sync', 'last_query', 'local_path', 'sync'):
            if name not in c and name in previous:
                c[name] = previous[name]
    header = c.get('auth_header', 'Authorization')
    if not re.fullmatch(r'[A-Za-z0-9-]+', header) or header.lower() in ('host', 'cookie', 'content-length', 'connection', 'proxy-authorization', 'range', 'if-range', 'accept', 'content-type', 'user-agent'):
        raise ValueError('Use Authorization or a provider API key header.')
    if any('\r' in str(c.get(k, '')) or '\n' in str(c.get(k, '')) for k in ('token', 'auth_prefix')):
        raise ValueError('Invalid authentication header.')
    if c['kind'] == 'graphql' and not c.get('graphql', '').lstrip().startswith(('query', '{')):
        raise ValueError('Provide a read-only GraphQL query using $query and optional $page variables.')
    return c


def infer_mapping(row):
    keys = flatten(row)
    return {k: next((x for x in options if x in keys), '') for k, options in ALIASES.items()}


def mapped(source, item, mapping=None):
    m = mapping or source.get('mapping') or infer_mapping(item)
    values = {k: field(item, path) for k, path in m.items() if path}
    if not text(values.get('title')):
        return None
    def as_list(v):
        return [text(x) for x in v] if isinstance(v, list) else [text(v)] if v else []
    return record(source['id'], values.get('id') or hashlib.sha256(json.dumps(item, sort_keys=True, default=str).encode()).hexdigest(),
                  values['title'], description=values.get('description'), year=values.get('year'), url=values.get('url'),
                  thumbnail=values.get('thumbnail'), duration=values.get('duration'), category=values.get('category') or source['categories'][0],
                  media_urls=as_list(values.get('media_url')), genres=as_list(values.get('genres')),
                  creators=as_list(values.get('creators')), license=values.get('license'),
                  external_ids={'imdb': text(values['imdb'])} if values.get('imdb') else {}, source_name=source['name'])


def feed_rows(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('Feeds with custom entities are not accepted.')
    root = ET.fromstring(data)
    rows = []
    for node in root.iter():
        if node.tag.split('}')[-1] not in ('item', 'entry'):
            continue
        r = {}
        for child in node:
            tag = child.tag.split('}')[-1]
            if tag in ('title', 'description', 'summary', 'id', 'guid', 'published'):
                r['description' if tag == 'summary' else tag] = ''.join(child.itertext())
            elif tag == 'link':
                r['link'] = child.get('href') or child.text
            elif tag in ('enclosure', 'content') and child.get('url') and (child.get('type', '').startswith(('video/', 'audio/')) or tag == 'enclosure'):
                r['media_url'] = child.get('url')
            elif tag == 'thumbnail':
                r['thumbnail'] = child.get('url')
        rows.append(r)
    return rows


def items_from(raw, path=''):
    if path:
        raw = field(raw, path, [])
    elif isinstance(raw, dict):
        raw = next((raw[k] for k in ('results', 'items', 'data', 'records') if isinstance(raw.get(k), list)), raw)
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list) or not all(isinstance(x, dict) for x in raw):
        raise ValueError('Choose the path to the array of records, for example data.items.')
    return raw


def detect(endpoint):
    normalized = url(endpoint)
    if not normalized:
        raise ValueError('Enter a public HTTP(S) website, API or feed URL.')
    host = urlsplit(normalized).hostname
    known = next((s for s in GALLERY if host in (urlsplit(s['endpoint']).hostname, urlsplit(s['website']).hostname)), None)
    if known:
        return {'kind': known['kind'], 'gallery_id': known['id'], 'message': 'A built-in connector is available. Connect it from the gallery.'}
    data, content_type, _ = network.fetch(normalized)
    try:
        raw = json.loads(data)
        rows = items_from(raw)
        sample = rows[0] if rows else {}
        return {'kind': 'rest', 'sample': sample, 'mapping': infer_mapping(sample), 'fields': list(flatten(sample)), 'message': 'JSON detected. Confirm the records path, search parameter and field mapping.'}
    except (ValueError, UnicodeError):
        if 'xml' in content_type or data.lstrip().startswith(b'<?xml'):
            rows = feed_rows(data)
            if rows:
                return {'kind': 'feed', 'sample': rows[0], 'mapping': infer_mapping(rows[0]), 'fields': list(rows[0]), 'message': 'RSS or Atom feed detected.'}
    return {'kind': 'website', 'message': 'This is not a detected database API. Find its documented API/export/RSS URL, use Advanced API configuration, or analyze an individual video in Link Analyzer.'}


_locks = {}
_lock_guard = threading.Lock()
_last_request = {}


def search(source, query, page=1, memory=None):
    """One bounded page. Provider requests are paced independently, including across searches."""
    with _lock_guard:
        lock = _locks.setdefault(source['id'], threading.Lock())
    with lock:
        delay = (2.1 if source['kind'] == 'anilist' else .6) - (time.monotonic() - _last_request.get(source['id'], 0))
        if delay > 0:
            time.sleep(delay)
        _last_request[source['id']] = time.monotonic()
        return _search(source, query, page, memory)


def _search(s, q, page, memory=None):
    kind, base = s['kind'], s.get('endpoint', '').rstrip('/')
    sid, name = s['id'], s['name']
    headers = {}
    if s.get('token'):
        headers[s.get('auth_header', 'Authorization')] = s.get('auth_prefix', 'Bearer ') + s['token']
    def rec(ident, title, **kw):
        return record(sid, ident, title, source_name=name, **kw)
    more = False
    if kind in ('pokemon-tv', 'open-animation'):
        from .open_catalog import search as search_open_catalog
        return search_open_catalog(s, q, page)
    if kind == 'tvmaze':
        if page > 1:
            return [], False
        raw = network.json_request(base + '/search/shows?' + urlencode({'q': q}))
        hits = []
        for r in raw:
            x = r['show']
            ids = {k: str(v) for k, v in (x.get('externals') or {}).items() if v}
            hits.append(rec(x['id'], x['name'], description=x.get('summary'), year=x.get('premiered'), category='anime' if x.get('type') == 'Animation' else 'series', genres=x.get('genres'), thumbnail=(x.get('image') or {}).get('original'), url=x.get('url'), duration=(x.get('runtime') or 0)*60 or None, languages=[x['language']] if x.get('language') else [], external_ids=ids))
    elif kind == 'anilist':
        args = 'type:ANIME,isAdult:false,search:$query,sort:SEARCH_MATCH'
        variables = {'query': q, 'page': page}
        declaration = '$query:String,$page:Int'
        # Title APIs cannot answer a paragraph. Genre/year browsing retrieves real candidates.
        if memory and memory.get('genre'):
            args = 'type:ANIME,isAdult:false,genre:$genre'
            declaration += ',$genre:String'
            variables['genre'] = memory['genre']
            if memory.get('year_from'):
                args += ',startDate_greater:$after'
                declaration += ',$after:FuzzyDateInt'
                variables['after'] = memory['year_from']*10000
        raw = network.json_request(base, {'query': 'query('+declaration+'){Page(page:$page,perPage:25){pageInfo{hasNextPage} media('+args+'){id title{romaji english native} synonyms description(asHtml:false) startDate{year} genres coverImage{large} siteUrl duration format episodes season streamingEpisodes{title thumbnail url site}}}}', 'variables': variables})
        if raw.get('errors'):
            raise network.SourceError('AniList rejected the query or is rate limited.')
        data = raw.get('data', {}).get('Page') or {}
        more = bool(data.get('pageInfo', {}).get('hasNextPage'))
        hits = []
        for x in data.get('media') or []:
            titles = x.get('title') or {}
            hits.append(rec(x['id'], titles.get('english') or titles.get('romaji') or titles.get('native'), alternatives=list(dict.fromkeys([v for v in titles.values() if v] + (x.get('synonyms') or []))), description=x.get('description'), year=(x.get('startDate') or {}).get('year'), category='anime', genres=x.get('genres'), thumbnail=(x.get('coverImage') or {}).get('large'), url=x.get('siteUrl'), duration=(x.get('duration') or 0)*60 or None, external_ids={'anilist':str(x['id'])}))
            hits[-1].update(episode_count=x.get('episodes'), edition=x.get('format'), release_season=x.get('season'), episode_links=x.get('streamingEpisodes') or [])
    elif kind == 'archive':
        words = re.findall(r'[\w]+', q)
        phrase = ' OR '.join('"' + w + '"' for w in words)
        raw = network.json_request(base + '/advancedsearch.php?' + urlencode({'q': 'mediatype:movies AND (' + phrase + ')', 'output': 'json', 'rows': 25, 'page': page, 'fl[]': ['identifier','title','description','creator','year','language','licenseurl','subject']}, doseq=True))
        data = raw.get('response', {})
        more = data.get('numFound', 0) > page*25
        hits = [rec(x['identifier'], x.get('title'), description=x.get('description'), year=x.get('year'), creators=[text(x.get('creator'))], category='archive', genres=[text(x.get('subject'))], languages=[text(x.get('language'))], url=base+'/details/'+quote(x['identifier']), thumbnail=base+'/services/img/'+quote(x['identifier']), license=x.get('licenseurl'), media_urls=[base+'/details/'+quote(x['identifier'])]) for x in data.get('docs', [])]
    elif kind == 'commons':
        raw = network.json_request(base+'?'+urlencode({'action':'query','format':'json','generator':'search','gsrsearch':q+' filetype:video','gsrnamespace':6,'gsrlimit':25,'gsroffset':(page-1)*25,'prop':'videoinfo','viprop':'url|size|extmetadata','viurlwidth':400}))
        if raw.get('error'):
            raise network.SourceError('Commons rejected the request.')
        more = bool(raw.get('continue'))
        hits = []
        for x in raw.get('query', {}).get('pages', {}).values():
            info = (x.get('videoinfo') or [{}])[0]
            meta = info.get('extmetadata') or {}
            hits.append(rec(x['pageid'], x['title'].removeprefix('File:'), description=meta.get('ImageDescription', {}).get('value'), thumbnail=info.get('thumburl'), url=info.get('descriptionurl') or 'https://commons.wikimedia.org/wiki/'+quote(x['title']), license=meta.get('LicenseUrl', {}).get('value'), creators=[text(meta.get('Artist', {}).get('value'))], media_urls=[info['url']] if info.get('url') else []))
    elif kind == 'peertube':
        raw = network.json_request(base+'/api/v1/search/videos?'+urlencode({'search':q,'count':25,'start':(page-1)*25,'sort':'-match'}))
        more = raw.get('total', 0) > page*25
        hits = []
        for x in raw.get('data', []):
            video_url = x.get('url') or ''
            cover = x.get('thumbnailUrl') or urljoin(video_url, x.get('thumbnailPath') or '')
            hits.append(rec(x.get('uuid') or x.get('id'), x.get('name'), description=x.get('description'), url=video_url, thumbnail=cover, duration=x.get('duration'), media_urls=[video_url], category='video', license=(x.get('licence') or {}).get('label'), creators=[text((x.get('channel') or {}).get('displayName'))]))
    elif kind == 'tmdb':
        if not s.get('token'):
            raise ValueError('Add your optional TMDB API Read Access Token to connect this source.')
        raw = network.json_request(base+'/search/multi?'+urlencode({'query':q,'page':page}), headers=headers)
        more = raw.get('total_pages', 0) > page
        hits = []
        for x in raw.get('results', []):
            if x.get('media_type') not in ('movie', 'tv'):
                continue
            category = 'movie' if x['media_type'] == 'movie' else 'series'
            hits.append(rec(str(x['media_type'])+'/'+str(x['id']), x.get('title') or x.get('name'), alternatives=[x.get('original_title') or x.get('original_name') or ''], description=x.get('overview'), year=x.get('release_date') or x.get('first_air_date'), category=category, url='https://www.themoviedb.org/'+x['media_type']+'/'+str(x['id']), thumbnail='https://image.tmdb.org/t/p/w500'+x['poster_path'] if x.get('poster_path') else '', languages=[x['original_language']] if x.get('original_language') else [], external_ids={'tmdb':x['media_type']+'/'+str(x['id'])}))
    elif kind in ('rest', 'graphql', 'feed'):
        if kind == 'feed':
            rows = feed_rows(network.fetch(base, headers=headers)[0])
            hits = [r for x in rows if (r := mapped(s, x))]
            words = q.casefold().split()
            return [r for r in hits if any(w in (r['title']+' '+r['description']).casefold() for w in words)], False
        params = dict(s.get('params') or {})
        params[s.get('query_param') or 'q'] = q
        if s.get('page_param'):
            params[s['page_param']] = page
        if s.get('page_size_param'):
            params[s['page_size_param']] = int(s.get('page_size') or 25)
        if s.get('since_param') and s.get('last_sync'):
            params[s['since_param']] = s['last_sync']
        if kind == 'rest':
            raw = network.json_request(base+('&' if '?' in base else '?')+urlencode(params), headers=headers)
        else:
            variables = {**(s.get('variables') or {}), 'query':q, 'page':page}
            raw = network.json_request(base, {'query':s['graphql'], 'variables':variables}, headers)
            if raw.get('errors'):
                raise ValueError('The GraphQL provider rejected the query. Check its documented schema and variables.')
        rows = items_from(raw, s.get('items_path', ''))
        hits = [r for x in rows if (r := mapped(s, x))]
        if rows and not hits:
            raise ValueError('Records were received, but none has a mapped title. Check the records path and Title mapping.')
        more = len(rows) >= int(s.get('page_size') or 25) and bool(s.get('page_param') or kind == 'graphql')
    elif kind == 'local':
        return [], False
    else:
        raise ValueError('Unsupported source type.')
    return hits, more
