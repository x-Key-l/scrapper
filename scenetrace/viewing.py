"""Search, resolve episodes, and open a verified viewing option."""
import concurrent.futures
import re
import secrets
import time
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit

from . import media, network, open_catalog, sources
from .model import url

BROWSER_VIDEO = {'.mp4': 'video/mp4', '.webm': 'video/webm', '.ogv': 'video/ogg'}
STREAM_MIME = {'application/vnd.apple.mpegurl', 'application/x-mpegurl', 'application/dash+xml', 'audio/mpegurl'}
EXTERNAL_EPISODES = {
    'www.crunchyroll.com': r'/(?:[a-z-]+/)?watch/[^/]+',
    'www.hulu.com': r'/watch/[^/]+',
    'www.hidive.com': r'/video/[^/]+',
    'www.netflix.com': r'/watch/[^/]+',
    'tubitv.com': r'/tv-shows/[^/]+',
}


def youtube_id(value):
    parsed = urlsplit(value)
    if parsed.scheme not in ('http', 'https'):
        return ''
    if parsed.hostname == 'youtu.be':
        ident = parsed.path.strip('/')
    elif parsed.hostname in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com'):
        if parsed.path == '/watch':
            ident = parse_qs(parsed.query).get('v', [''])[0]
        elif re.fullmatch(r'/(shorts|embed|live|v)/[^/]+/?', parsed.path):
            ident = parsed.path.strip('/').split('/')[1]
        else:
            return ''
    else:
        return ''
    return ident if re.fullmatch(r'[A-Za-z0-9_-]{11}', ident) else ''


def official_episode(value):
    parsed = urlsplit(value)
    if parsed.scheme != 'https':
        return False
    pattern = EXTERNAL_EPISODES.get(parsed.hostname)
    return bool(youtube_id(value) or (pattern and re.match(pattern, parsed.path)))


def open_license(value):
    parsed = urlsplit(str(value or ''))
    return parsed.hostname in ('creativecommons.org', 'www.creativecommons.org') and bool(
        re.match(r'^/(?:licenses/by(?:-sa|-nc|-nc-sa|-nd|-nc-nd)?/[0-9.]+|publicdomain/(?:zero|mark)/[0-9.]+)(?:/[a-z-]+)?/?$', parsed.path)
    )


def probe_file(value, *, browser=True):
    conn, response, final = network.open_url(value, headers={'Range': 'bytes=0-1023'})
    try:
        content_type = response.getheader('Content-Type', '').split(';')[0].lower()
        header = response.read(1024)
        if not header or content_type in ('text/html', 'application/json'):
            raise network.SourceError('The host returned a page instead of a media file.')
        ext = '.' + urlsplit(final).path.rsplit('.', 1)[-1].lower()
        if content_type in STREAM_MIME or (ext == '.m3u8' and header.lstrip().startswith(b'#EXTM3U')):
            return {'url': final, 'mime': content_type, 'stream': True, 'size': None}
        expected = BROWSER_VIDEO.get(ext)
        valid_signature = header.startswith((b'\x1aE\xdf\xa3', b'OggS', b'ID3')) or b'ftyp' in header[:32]
        if browser and not (content_type in BROWSER_VIDEO.values() or (expected and valid_signature)):
            raise network.SourceError('The source file uses a format the browser cannot play.')
        if not browser and not (content_type.startswith(('video/', 'audio/')) or valid_signature):
            raise network.SourceError('The host did not provide a downloadable media file.')
        total = response.getheader('Content-Range', '').rsplit('/', 1)[-1]
        if not total.isdigit() and response.status == 200:
            total = response.getheader('Content-Length', '')
        return {'url': final, 'mime': expected or content_type, 'size': int(total) if total.isdigit() else None}
    finally:
        conn.close()


def episode_number(title):
    match = re.search(r'\b(?:episode|ep\.?|e)\s*(\d+(?:\.\d+)?)\b', title, re.I)
    return match[1] if match else None


def episode_row(value, title, source, **extra):
    return {'url': value, 'title': title, 'source': source, 'number': episode_number(title), **extra}


class Viewing:
    def __init__(self, app):
        self.app = app
        self.tickets = {}

    def ticket(self, kind, value):
        now = time.monotonic()
        for key, entry in list(self.tickets.items()):
            if entry[0] < now:
                self.tickets.pop(key, None)
        key = secrets.token_urlsafe(24)
        self.tickets[key] = (now + 7200, kind, value)
        return key

    def get_ticket(self, key, kind):
        entry = self.tickets.get(key)
        if not entry or entry[0] < time.monotonic() or entry[1] != kind:
            raise ValueError('This viewing option expired. Open the video again.')
        return entry[2]

    def search_scope(self, body):
        anime = body.get('mode') == 'anime'
        selected = body.get('sources')
        category = body.get('category') or ''
        active = self.app.store.sources(public=True)
        ids = [
            s['id'] for s in active if s.get('enabled')
            and (selected is None or s['id'] in selected)
            and (not anime or set(s.get('categories', [])) & {'anime', 'animation'})
            and (not category or category in s.get('categories', []))
            and (anime or s['role'] in ('media', 'hybrid'))
        ]
        return ids

    def search(self, body):
        output = self.app.search.run(body.get('query', ''), self.search_scope(body), body.get('page', 1))
        return self.decorate(output, body.get('mode') == 'anime')

    def decorate(self, output, anime=False):
        active = self.app.store.sources(public=True)
        by_id = {s['id']: s for s in active}
        rows = []
        for item in output['results']:
            source = by_id.get(item['source_id'], {})
            if source.get('role') == 'metadata':
                item['status'] = 'Title identification'
                item['is_video'] = False
            elif item.get('media_urls'):
                item['is_video'] = True
                item['status'] = 'Episode pages found' if item.get('video_type') == 'series' else 'Video page found'
            else:
                continue
            if anime and item['category'] not in ('anime', 'animation') and source.get('role') == 'metadata':
                continue
            rows.append(item)
        unique = {}
        for item in rows:
            key = item['url'] if item['is_video'] and item['url'] else item['id']
            unique.setdefault(key, item)
        output['results'] = sorted(unique.values(), key=lambda item: not item['is_video'])
        output['notice'] = 'Select a result to see episodes and viewing options.'
        return output

    def episodes(self, item, follow=True):
        source = self.app.store.source(item.get('source_id'))
        if not source or not source.get('enabled'):
            return []
        kind = source['kind']
        if kind in open_catalog.CATALOGS and item.get('source_record_id') == kind:
            return [dict(e, source=source['name'], kind=kind) for e in open_catalog.episodes(kind)]
        if kind == 'anilist':
            rows = []
            for episode in item.get('episode_links', []):
                value = url(episode.get('url'))
                if value and official_episode(value):
                    rows.append(episode_row(value, episode.get('title') or 'Episode', episode.get('site') or 'Official provider', kind='official'))
            return rows
        if source['role'] not in ('media', 'hybrid') or not item.get('media_urls'):
            return []
        if kind == 'website' and follow:
            from . import websites
            found = websites.episodes(source, item['url'])
            if found:
                return [dict(e, source=source['name'], kind='website', website=source['id']) for e in found]
        value = url(item.get('url')) or url(item['media_urls'][0])
        if not value:
            return []
        return [episode_row(value, item['title'], source['name'], kind=kind, website=source['id'])]

    def details(self, item):
        rows = self.episodes(item)
        errors = []
        source = self.app.store.source(item.get('source_id'))
        if not rows or (source and source['role'] == 'metadata'):
            names = list(dict.fromkeys([item['title'], *(item.get('alternatives') or [])]))[:3]
            keys = {open_catalog.title_key(t) for t in names}
            active = [s for s in self.app.store.sources() if s['enabled'] and s['role'] in ('media', 'hybrid')]
            # Reuse the source executor. Each provider gets a small title query budget.
            def lookup(site):
                matches = []
                for title in names:
                    found, _ = sources.search(site, title, 1)
                    for result in found:
                        candidates = {open_catalog.title_key(result['title']), *(open_catalog.title_key(x) for x in result['alternatives'])}
                        if not keys & candidates:
                            continue
                        if item.get('year') and result.get('year') and abs(item['year'] - result['year']) > 2:
                            continue
                        matches.extend(self.episodes(result))
                    if matches:
                        break
                return matches
            pending = {self.app.search.pool.submit(lookup, site):site for site in active if site['kind'] != 'local'}
            done, unfinished = concurrent.futures.wait(pending, timeout=21)
            for task in done:
                try:
                    rows.extend(task.result())
                except Exception as exc:
                    errors.append({'source': pending[task]['name'], 'message': str(exc) if isinstance(exc, ValueError) else 'Source could not be reached.'})
            for task in unfinished:
                task.cancel()
                errors.append({'source': pending[task]['name'], 'message': 'Lookup timed out.'})
        unique = {}
        for episode in rows:
            value = url(episode['url'])
            if value and value not in unique:
                unique[value] = dict(episode, url=value, ticket=self.ticket('episode', episode))
        return {'episodes': list(unique.values()), 'errors': errors}

    def play(self, key):
        episode = self.get_ticket(key, 'episode')
        value = episode['url']
        base = {'episode': episode['title'], 'source': episode['source'], 'original': value, 'playback': 'external', 'formats': []}
        ident = youtube_id(value)
        if ident:
            base.update(playback='embed', embed='https://www.youtube.com/embed/' + ident,
                        message='Official YouTube player. Open the original page if playback is unavailable.')
        try:
            return self.play_media(episode, base)
        except (OSError, ValueError) as exc:
            return dict(base, message=str(exc) if isinstance(exc, ValueError) else 'The video host is unavailable. Try its original page.')

    def play_media(self, episode, base, source=None):
        value = episode['url']
        if source is None and episode.get('website'):
            source = self.app.store.source(episode['website'])
        if episode['kind'] == 'peertube':
            info = self.peertube(value)
        elif episode['kind'] == 'website' and source:
            from . import websites
            info = websites.resolve(source, value, self.app.proxy)
        elif urlsplit(value).hostname in ('archive.org', 'www.archive.org', 'commons.wikimedia.org'):
            info = media.analyze(value, self.app.proxy)
            info['download_allowed'] = open_license(info.get('license'))
        else:
            try:
                info = media.analyze(value, self.app.proxy)
            except (OSError, ValueError) as exc:
                info = {'formats': [], 'notice': str(exc)}
        formats = [f for f in info.get('formats', []) if f.get('method') in ('direct', 'extractor') and f.get('url')]
        playable = sorted(
            [f for f in formats if f.get('video') and not f.get('drm') and ('.' + f.get('ext', '') in BROWSER_VIDEO or f.get('ext') == 'm3u8')],
            key=lambda f: (f.get('ext') == 'ogv', abs((f.get('height') or 480) - 360)),
        )
        output = dict(base, license=info.get('license', ''), attribution=', '.join(info.get('creators') or []))
        last_error = ''
        for selected in playable[:4]:
            try:
                checked = probe_file(selected['url'])
                output.update(playback='direct', stream=checked['url'] if checked.get('stream') else '/media/' + self.ticket('stream', checked), stream_ext='m3u8' if checked.get('stream') and checked['mime'] != 'application/dash+xml' else selected.get('ext'), message='Direct media checked. Use the player controls to watch.', quality=selected.get('height'), mime=checked['mime'], direct_url=checked['url'], playing_format_id=selected['id'])
                break
            except (OSError, ValueError) as exc:
                last_error = str(exc)
        if output['playback'] == 'external' and info.get('embed'):
            output.update(playback='embed', embed=info['embed'], message='The source provides an official player. Open the source page if it cannot play here.')
        if output['playback'] == 'external':
            output['message'] = last_error or 'Open the exact source page to check playback.'
        if output['playback'] == 'direct':
            subtitles = []
            for track in info.get('subtitles', []):
                if not track.get('url'):
                    continue
                try:
                    content, _, final = network.fetch(track['url'], limit=512 * 1024)
                    if content.lstrip(b'\xef\xbb\xbf \n\r').startswith(b'WEBVTT'):
                        token = self.ticket('stream', {'url': final, 'mime': 'text/vtt'})
                        subtitles.append(dict(track, url='/media/' + token))
                except (OSError, ValueError):
                    continue
            output['subtitles'] = subtitles
        eligible = [f for f in formats if f.get('permitted', True)]
        if eligible:
            analysis = dict(info, title=info.get('title') or episode['title'], url=value, formats=eligible, analyzed=time.time())
            safe = self.app.register_analysis(analysis)
            output.update(analysis_id=safe['analysis_id'], formats=safe['formats'], subtitles=output.get('subtitles') or safe.get('subtitles', []))
        if info.get('notice'):
            output['message'] = (output.get('message', '') + ' ' + info['notice']).strip()
        if info.get('restricted'):
            output['message'] = (output.get('message', '') + ' The source reports account or availability requirements.').strip()
        return output

    def check(self, source, query, sample_url=''):
        from . import websites
        checks = {'search': 'Unchecked', 'discovery': 'Unchecked', 'playback': 'Unchecked', 'download': 'Unchecked'}
        rows = []
        try:
            rows, _ = sources.search(source, query, 1)
            checks['search'] = f'{len(rows)} results returned' if rows else 'No matches for sample'
            selected = next((row for row in rows if row.get('media_urls')), None)
            if not selected:
                return {'ok': False, 'checks': checks, 'results': rows[:6], 'message': 'No video pages matched. Adjust the search method or selectors.'}
            if source['kind'] == 'website':
                value = url(sample_url) if sample_url else selected['url']
                if sample_url and not websites.same_origin(value, source['endpoint']):
                    raise ValueError('The sample page must be on this website.')
                episodes = websites.episodes(source, value)
                checks['discovery'] = f'{len(episodes)} episode pages' if episodes else 'Exact video or detail page found'
                episode = episodes[0] if episodes else episode_row(value, selected['title'], source['name'])
                episode = dict(episode, source=source['name'], kind='website')
                base = {'episode': episode['title'], 'source': source['name'], 'original': episode['url'],
                        'playback': 'external', 'formats': []}
                if youtube_id(episode['url']):
                    player = self.play(self.ticket('episode', episode))
                else:
                    player = self.play_media(episode, base, source)
            else:
                episodes = self.episodes(selected)
                checks['discovery'] = f'{len(episodes)} episode or video pages'
                player = self.play(self.ticket('episode', episodes[0])) if episodes else {}
            playback = player.get('playback')
            checks['playback'] = {
                'direct': 'Direct media bytes checked', 'embed': 'Official embed offered',
                'external': 'Source page only · playback unverified',
            }.get(playback, 'No viewing option checked')
            checks['download'] = 'Eligible formats exposed' if player.get('formats') else 'No eligible format found'
            if playback == 'external' and player.get('message'):
                checks['detail'] = player['message']
            return {'ok': True, 'checks': checks, 'results': rows[:6], 'message': 'Review the sample video and playback options.',
                    'sample': player}
        except (OSError, ValueError) as error:
            message = str(error) if isinstance(error, ValueError) else 'The website did not complete the request.'
            checks['error'] = message
            # A later episode/player outage must not erase a verified search method.
            searchable = any(row.get('media_urls') for row in rows)
            return {'ok': searchable, 'checks': checks, 'results': rows[:6], 'message': message,
                    'error_code': getattr(error, 'code', 'connection_error'),
                    'diagnostics': getattr(error, 'diagnostics', {})}

    def test_website(self, body):
        previous = self.app.store.source(body.get('id'))
        if previous and previous['kind'] != 'website':
            raise ValueError('Choose a custom website to edit.')
        query = body.get('query', '')
        if not isinstance(query, str) or not 2 <= len(query.strip()) <= 200:
            raise ValueError('Enter a sample title or keywords to test this website.')
        config = sources.validate(dict(
            kind='website', role='media', name=body.get('name'), endpoint=body.get('endpoint'),
            website=body.get('endpoint'), web_config=body.get('web_config'), mapping=body.get('mapping') or {},
            categories=body.get('categories') or ['video'], enabled=previous.get('enabled', True) if previous else True,
            sample_query=query,
        ), previous)
        result = self.check(config, query, body.get('sample_url', ''))
        if result['ok']:
            config['video_checks'] = result['checks']
            result['save_ticket'] = self.ticket('website-config', config)
        else:
            browsing = dict(config, web_config=dict(config['web_config'], strategy='browse'),
                            video_checks={'search': 'Integration incomplete', 'playback': 'Manual browsing available'})
            result['browse_ticket'] = self.ticket('website-config', browsing)
        return result

    def save_website(self, ticket):
        config = self.get_ticket(ticket, 'website-config')
        self.app.store.put_source(config)
        with self.app.store.db() as conn:
            conn.execute('DELETE FROM cache')
            conn.execute('DELETE FROM search_fts WHERE id IN (SELECT id FROM records WHERE source=?)', (config['id'],))
            conn.execute('DELETE FROM records WHERE source=?', (config['id'],))
        self.tickets.pop(ticket, None)
        return {'id': config['id'], 'name': config['name']}

    def test_source(self, ident, query=''):
        source = self.app.source(ident)
        sample = query.strip() or source.get('sample_query') or {
            'pokemon-tv': 'Pokémon', 'open-animation': 'Caminandes', 'archive': 'Big Buck Bunny',
            'commons': 'Caminandes', 'peertube': 'Blender',
        }.get(source['kind'], 'nature')
        result = self.check(source, sample)
        current = self.app.store.source(ident)
        if current:
            current['video_checks'] = result['checks']
            self.app.store.put_source(current)
        return result

    def peertube(self, value):
        p = urlsplit(value)
        ident = unquote(p.path.rstrip('/').split('/')[-1])
        if p.scheme != 'https' or not re.fullmatch(r'[\w-]{8,64}', ident):
            raise ValueError('This PeerTube result does not contain an exact video ID.')
        base = 'https://' + p.netloc
        item = network.json_request(base + '/api/v1/videos/' + quote(ident))
        if not item.get('uuid') or item.get('privacy', {}).get('id') not in (1, 2) or item.get('isLive'):
            raise ValueError('The instance did not expose a public recorded video.')
        files = []
        for f in item.get('files', []):
            value = url(f.get('fileUrl'))
            ext = urlsplit(value).path.rsplit('.', 1)[-1].lower()
            if ext in media.EXTENSIONS:
                files.append(dict(id=str(len(files)), url=value, ext=ext, height=f.get('resolution', {}).get('id'),
                                  size=f.get('size'), video=bool(f.get('resolution', {}).get('id')),
                                  audio=True, method='direct', label='PeerTube file'))
        embed = item.get('embedPath') or ''
        return dict(title=item.get('name'), formats=files, download_allowed=item.get('downloadEnabled') is True,
                    license=(item.get('licence') or {}).get('label', ''), embed=base+embed if re.fullmatch(r'/videos/embed/[\w-]+', embed) else '')
