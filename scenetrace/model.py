"""Plain source-preserving records. Provider strings never become HTML or code."""
import hashlib
import html
import re
from urllib.parse import urlsplit, urlunsplit


def text(value):
    if isinstance(value, (list, tuple)):
        return ', '.join(text(x) for x in value)
    if isinstance(value, dict):
        return ', '.join(text(x) for x in value.values())
    return html.unescape(re.sub(r'<[^>]*>', ' ', str(value or ''))).strip()


def url(value):
    try:
        p = urlsplit(str(value or '').strip())
        if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
            return ''
        return urlunsplit((p.scheme, p.netloc, p.path, p.query, ''))
    except ValueError:
        return ''


def number(value):
    try:
        return float(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def year(value):
    m = re.search(r'\b(18\d{2}|19\d{2}|20\d{2}|21\d{2})\b', text(value))
    return int(m[0]) if m else None


def record(source, ident, title, **f):
    title = text(title) or 'Untitled'
    ident = str(ident or hashlib.sha256((title + str(f.get('url', ''))).encode()).hexdigest())
    return dict(id=source + ':' + ident, source_id=source, source_record_id=ident,
                title=title, alternatives=f.get('alternatives') or [],
                description=text(f.get('description')), year=year(f.get('year')),
                category=text(f.get('category') or 'video'), genres=f.get('genres') or [],
                creators=f.get('creators') or [], thumbnail=url(f.get('thumbnail')), url=url(f.get('url')),
                duration=number(f.get('duration')), languages=f.get('languages') or [],
                external_ids=f.get('external_ids') or {},
                media_urls=[u for x in f.get('media_urls', []) if (u := url(x))],
                license=text(f.get('license')), download_info=f.get('download_info') or '',
                status='External video found' if f.get('media_urls') else 'Metadata only',
                source_name=f.get('source_name') or source)


def flatten(obj, prefix=''):
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = prefix + '.' + str(k) if prefix else str(k)
            if isinstance(v, dict):
                out.update(flatten(v, p))
            else:
                out[p] = v
    return out


def field(obj, path, default=''):
    if not path:
        return default
    cur = obj
    for name in str(path).split('.'):
        try:
            cur = cur[int(name)] if isinstance(cur, list) else cur[name]
        except (KeyError, IndexError, TypeError, ValueError):
            return default
    return cur
