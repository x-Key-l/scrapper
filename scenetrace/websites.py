"""Data-only adapters for public search forms, listings, feeds, JSON and sitemaps."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import xml.etree.ElementTree as ET
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from soupsieve import SelectorSyntaxError

from . import network
from .model import field, record, text, url
from .open_catalog import title_key

RESULT_LINKS = (
    'a[href*="/watch/"], a[href*="/video/"], a[href*="/episode/"], '
    'a[href*="/series/"], a[href*="/anime/"], a[href*="/videos/watch/"]'
)
FIELD_NAMES = (
    'strategy', 'search_pattern', 'query_param', 'page_param', 'items_path',
    'result_selector', 'title_selector', 'link_selector', 'thumbnail_selector',
    'description_selector', 'episode_selector', 'episode_title_selector',
    'episode_link_selector', 'playback_selector', 'path_prefix', 'render_browser',
)
_RENDER_SLOT = threading.BoundedSemaphore(1)


def parse_page(data):
    return BeautifulSoup(data, 'html.parser')


def same_origin(a, b):
    p, q = urlsplit(a), urlsplit(b)
    return (p.scheme, p.hostname, p.port or (443 if p.scheme == 'https' else 80)) == (
        q.scheme, q.hostname, q.port or (443 if q.scheme == 'https' else 80),
    )


def relative(base, value):
    return url(urljoin(base, str(value or ''))) if value else ''


def select(node, selector):
    if not selector:
        return []
    try:
        return node.select(selector)
    except SelectorSyntaxError as error:
        raise ValueError('A CSS selector is invalid. Check the selector fields.') from error


def first(node, selector):
    return next(iter(select(node, selector)), None) if selector else node


def node_value(node, selector, attrs=()):
    target = first(node, selector)
    if target is None:
        return ''
    if not attrs:
        return target.get_text(' ', strip=True) or target.get('title') or target.get('aria-label', '')
    return next((target.get(attr) for attr in attrs if isinstance(target.get(attr), str) and target.get(attr)), '')


def validate(config):
    if not isinstance(config, dict):
        raise ValueError('Website configuration must be an object.')
    output = {}
    for key in FIELD_NAMES:
        if key == 'render_browser':
            output[key] = config.get(key) is True
        else:
            value = config.get(key, '')
            if not isinstance(value, str):
                raise ValueError('Website configuration fields must be text.')
            if len(value) > 4096:
                raise ValueError('A website configuration field is too long.')
            output[key] = value.strip()
    if output['strategy'] not in ('html', 'listing', 'json', 'feed', 'sitemap'):
        raise ValueError('Choose a supported website strategy.')
    if output['strategy'] == 'html' and not (output['query_param'] or '{query}' in output['search_pattern']):
        raise ValueError('Enter the public search parameter or a URL pattern with {query}.')
    for name in FIELD_NAMES:
        if name.endswith('_selector') and output[name]:
            select(parse_page('<div></div>'), output[name])
    pattern = output['search_pattern']
    if re.search(r'\{(?!query\}|page\})', pattern):
        raise ValueError('Use only {query} and {page} in a search URL pattern.')
    return output


def browser_html(value):
    """Use a fresh installed Chromium profile only after the user opts in."""
    network.target(value)
    candidates = [shutil.which('msedge'), shutil.which('chromium'), shutil.which('chrome')]
    if os.name == 'nt':
        for variable in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA'):
            if os.environ.get(variable):
                candidates.append(str(Path(os.environ[variable]) / 'Microsoft/Edge/Application/msedge.exe'))
    browser = next((path for path in candidates if path and Path(path).is_file()), '')
    if not browser:
        raise ValueError('Browser rendering requires installed Microsoft Edge or Chromium. Use an HTML, feed or JSON source instead.')
    if not _RENDER_SLOT.acquire(False):
        raise ValueError('A website is already rendering. Retry when it finishes.')
    proxy = network.start_proxy()
    try:
        with tempfile.TemporaryDirectory(prefix='scenetrace-browser-', ignore_cleanup_errors=True) as profile:
            args = [
                browser, '--headless=new', '--dump-dom', '--no-first-run', '--disable-extensions',
                '--disable-quic', '--disable-background-networking', '--disable-component-update',
                '--force-webrtc-ip-handling-policy=disable_non_proxied_udp',
                '--proxy-server=http://127.0.0.1:' + str(proxy.server_port),
                '--proxy-bypass-list=<-loopback>', '--virtual-time-budget=4000',
                '--user-data-dir=' + profile, value,
            ]
            try:
                result = subprocess.run(args, capture_output=True, timeout=18, check=True,
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
                raise ValueError('The isolated browser could not render the public page.') from error
            if len(result.stdout) > 4 * 1024 * 1024:
                raise ValueError('The rendered page exceeds the inspection size budget.')
            return result.stdout
    finally:
        proxy.shutdown()
        proxy.server_close()
        _RENDER_SLOT.release()


def fetch_page(value, render=False):
    if render:
        return parse_page(browser_html(value)), value
    data, mime, final = network.fetch(value, limit=4 * 1024 * 1024)
    if not ('html' in mime or data.lstrip().startswith(b'<')):
        raise ValueError('This endpoint did not return a public HTML page.')
    return parse_page(data), final


def inspect(value):
    value = url(value)
    if not value:
        raise ValueError('Enter a public website URL.')
    data, mime, final = network.fetch(value, limit=4 * 1024 * 1024)
    name = urlsplit(final).hostname
    result = dict(name=name, endpoint=final, categories=['video'], strategy='listing', findings=[])
    if 'json' in mime or data.lstrip().startswith((b'[', b'{')):
        json.loads(data)
        return dict(result, strategy='json', findings=['Public JSON response. Map its result fields and test a title.'])
    if re.search(br'<(?:rss|feed)\b', data[:800], re.I):
        return dict(result, strategy='feed', findings=['Public RSS or Atom feed found. Test whether its items contain video pages.'])
    if re.search(br'<urlset\b', data[:800], re.I):
        return dict(result, strategy='sitemap', findings=['Public sitemap found. Use a video path prefix when it lists other pages.'])
    page = parse_page(data)
    if page.title:
        result['name'] = text(page.title.get_text())[:100] or name
    if page.select_one('video[src], video source[src]'):
        return dict(result, result_selector='video', findings=['HTML video found. Test this listing to verify playback.'])
    for form in page.select('form'):
        if str(form.get('method', 'get')).lower() != 'get':
            continue
        query = form.select_one('input[type=search][name], input[name=q], input[name=search], input[name=keyword], input[name=s]')
        action = relative(final, form.get('action') or final)
        if query and action and same_origin(final, action):
            result.update(strategy='html', search_pattern=action, query_param=query['name'],
                          result_selector=RESULT_LINKS, findings=['Public GET search form found. Confirm the result selectors with a sample search.'])
            return result
    for feed in page.select('link[rel=alternate][href]'):
        value = relative(final, feed.get('href'))
        if feed.get('type') in ('application/rss+xml', 'application/atom+xml') and same_origin(final, value):
            return dict(result, strategy='feed', endpoint=value, findings=['Public feed advertised by this page. Test a title in its entries.'])
    if page.select_one(RESULT_LINKS):
        return dict(result, result_selector=RESULT_LINKS, findings=['Possible video or series links found. Test their titles and exact pages.'])
    return dict(result, findings=['No public search form, video listing or feed was recognized. Enter a documented endpoint or selectors. JavaScript-only pages may need optional browser rendering.'])


def search_url(source, query, page):
    cfg = source['web_config']
    pattern = cfg['search_pattern'] or source['endpoint']
    value = relative(source['endpoint'], pattern.replace('{query}', quote(query, safe='')).replace('{page}', str(page)))
    if not value or not same_origin(value, source['endpoint']):
        raise ValueError('The search URL must stay on the configured website origin.')
    parsed = urlsplit(value)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    updates = {}
    if cfg['query_param'] and '{query}' not in pattern:
        updates[cfg['query_param']] = query
    if cfg['page_param'] and '{page}' not in pattern:
        updates[cfg['page_param']] = str(page)
    pairs = [(k, v) for k, v in pairs if k not in updates] + list(updates.items())
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(pairs), ''))


def structured_videos(page):
    def walk(value):
        if isinstance(value, dict):
            kinds = value.get('@type', [])
            if 'VideoObject' in ([kinds] if isinstance(kinds, str) else kinds or []):
                yield value
            for key in ('@graph', 'itemListElement', 'video', 'item', 'mainEntity'):
                yield from walk(value.get(key))
        elif isinstance(value, list):
            for item in value:
                yield from walk(item)
    for script in page.select('script[type="application/ld+json"]'):
        try:
            yield from walk(json.loads(script.get_text()))
        except (ValueError, RecursionError, TypeError):
            continue


def matches(query, title, description=''):
    words = title_key(query).split()
    haystack = title_key(title + ' ' + description)
    return bool(words and all(word in haystack for word in words))


def sitemap_rows(raw, base, prefix):
    if re.search(br'<!\s*(?:DOCTYPE|ENTITY)', raw, re.I):
        raise ValueError('Sitemaps with document types or entities are unsupported.')
    tree = ET.fromstring(raw)
    if tree.tag.rsplit('}', 1)[-1] != 'urlset':
        raise ValueError('Use a direct video sitemap rather than a sitemap index.')
    for node in tree.findall('{*}url'):
        value = relative(base, node.findtext('{*}loc'))
        video = node.find('{*}video')
        if not value or (video is None and not prefix):
            continue
        if prefix and not urlsplit(value).path.startswith(prefix):
            continue
        slug = urlsplit(value).path.rstrip('/').rsplit('/', 1)[-1].replace('-', ' ')
        yield {'title': video.findtext('{*}title') if video is not None else slug,
               'description': video.findtext('{*}description') if video is not None else '',
               'url': value, 'thumbnail': video.findtext('{*}thumbnail_loc') if video is not None else ''}


def search(source, query, page=1):
    from .sources import feed_rows, items_from
    cfg = source['web_config']
    strategy = cfg['strategy']
    if page > 1 and not (cfg['page_param'] or '{page}' in cfg['search_pattern']):
        return [], False
    target = search_url(source, query, page)
    if strategy in ('html', 'listing'):
        doc, final = fetch_page(target, cfg['render_browser'])
        raw_rows = []
        for node in select(doc, cfg['result_selector'] or RESULT_LINKS):
            href = node_value(node, cfg['link_selector'], ('href', 'src', 'data-href'))
            title = node_value(node, cfg['title_selector'])
            if node.name == 'video':
                href = final
                title = node.get('title') or node.get('aria-label') or (title if cfg['title_selector'] else '') or (doc.title.get_text(strip=True) if doc.title else '')
            image = node_value(node, cfg['thumbnail_selector'] or 'img', ('src', 'data-src', 'poster')) or node.get('poster')
            raw_rows.append(dict(title=title, url=href, thumbnail=image,
                                 description=node_value(node, cfg['description_selector']) if cfg['description_selector'] else ''))
        raw_rows.extend(dict(title=v.get('name'), description=v.get('description'), url=v.get('url') or final,
                             thumbnail=v.get('thumbnailUrl')) for v in structured_videos(doc))
    else:
        raw, _, final = network.fetch(target, limit=4 * 1024 * 1024)
        if strategy == 'feed':
            raw_rows = [dict(row, url=row.get('url') or row.get('link') or row.get('media_url')) for row in feed_rows(raw)]
        elif strategy == 'sitemap':
            try:
                raw_rows = list(sitemap_rows(raw, final, cfg['path_prefix']))
            except ET.ParseError as error:
                raise ValueError('This endpoint did not return a valid sitemap.') from error
        else:
            mapping = {'title': 'title', 'url': 'url', 'description': 'description', 'thumbnail': 'thumbnail',
                       'id': 'id', 'year': 'year', 'alternatives': 'alternatives', **source.get('mapping', {})}
            raw_rows = [{key: field(row, value) for key, value in mapping.items()} for row in items_from(json.loads(raw), cfg['items_path'])]
    rows = {}
    for row in raw_rows:
        name = text(row.get('title'))
        description = text(row.get('description'))
        value = relative(final, row.get('url'))
        alternatives = row.get('alternatives') or []
        if isinstance(alternatives, str):
            alternatives = [alternatives]
        if not name or not value or (strategy in ('listing', 'feed', 'sitemap') and not matches(query, name, description)):
            continue
        if cfg['path_prefix'] and not urlsplit(value).path.startswith(cfg['path_prefix']):
            continue
        image = row.get('thumbnail')
        if isinstance(image, list):
            image = next(iter(image), '')
        item = record(source['id'], row.get('id') or value, name, source_name=source['name'],
                      description=description, thumbnail=relative(final, image), url=value, media_urls=[value],
                      category=next(iter(source.get('categories', [])), 'video'),
                      alternatives=[text(alias) for alias in alternatives], year=row.get('year'))
        rows.setdefault(value, item)
    pagination = bool(cfg['page_param'] or '{page}' in cfg['search_pattern'])
    return list(rows.values())[:100], bool(rows and pagination)


def episodes(source, value):
    from .viewing import episode_number, official_episode
    cfg = source['web_config']
    if not cfg['episode_selector'] or not same_origin(value, source['endpoint']):
        return []
    doc, final = fetch_page(value, cfg['render_browser'])
    rows = {}
    for node in select(doc, cfg['episode_selector']):
        href = relative(final, node_value(node, cfg['episode_link_selector'], ('href', 'src', 'data-href')))
        name = node_value(node, cfg['episode_title_selector'])
        if href and name and (same_origin(final, href) or official_episode(href)):
            rows.setdefault(href, dict(url=href, title=name, number=episode_number(name)))
    return list(rows.values())


def resolve(source, value):
    from .media import EXTENSIONS
    from .viewing import open_license, youtube_id
    p = urlsplit(value)
    ext = p.path.rsplit('.', 1)[-1].lower()
    if ext in EXTENSIONS:
        return dict(formats=[dict(id='original', url=value, ext=ext, video=ext not in ('m4a', 'mp3', 'ogg', 'wav', 'flac'),
                                  audio=True, method='direct', label='Source file')], download_allowed=False)
    if not same_origin(value, source['endpoint']):
        return dict(formats=[], download_allowed=False)
    cfg = source['web_config']
    doc, final = fetch_page(value, cfg['render_browser'])
    media_links = [relative(final, node_value(node, '', ('src', 'href', 'content'))) for node in
                   select(doc, cfg['playback_selector'] or 'video[src], video source[src], meta[property="og:video:secure_url"]')]
    structured = list(structured_videos(doc))
    media_links.extend(relative(final, video.get('contentUrl')) for video in structured)
    download_links = {relative(final, anchor.get('href')) for anchor in doc.select('a[download][href]')}
    license_node = doc.select_one('a[rel=license][href], link[rel=license][href]')
    license_url = relative(final, license_node.get('href')) if license_node else next(
        (relative(final, video.get('license')) for video in structured if video.get('license')), '',
    )
    files = []
    for href in dict.fromkeys(media_links + list(download_links)):
        ext = urlsplit(href).path.rsplit('.', 1)[-1].lower()
        if ext in EXTENSIONS:
            files.append(dict(id=str(len(files)), url=href, ext=ext, video=ext not in ('m4a', 'mp3', 'ogg', 'wav', 'flac'),
                              audio=True, method='direct', label='Website file',
                              permitted=open_license(license_url) or href in download_links))
    tracks = [dict(url=relative(final, node.get('src')), language=node.get('srclang') or 'und',
                   label=node.get('label') or 'Subtitles') for node in doc.select('video track[src]')]
    embeds = [relative(final, video.get('embedUrl')) for video in structured]
    embeds += [relative(final, frame.get('src')) for frame in doc.select('iframe[src]')]
    embed = ''
    for candidate in embeds:
        host = urlsplit(candidate).hostname
        path = urlsplit(candidate).path
        if host in ('www.youtube.com', 'www.youtube-nocookie.com') and re.fullmatch(r'/embed/[\w-]{11}', path):
            embed = 'https://www.youtube.com' + path
            break
        if host == 'player.vimeo.com' and re.fullmatch(r'/video/\d+', path):
            embed = 'https://player.vimeo.com' + path
            break
    return dict(title=doc.title.get_text(strip=True) if doc.title else '', formats=files,
                subtitles=tracks, license=license_url, embed=embed,
                download_allowed=any(f['permitted'] for f in files))
