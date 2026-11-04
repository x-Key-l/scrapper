"""Media resolution is distinct from catalog identification."""
import json
import os
import re
import subprocess
import sys
import time
from urllib.parse import quote, unquote, urlencode, urlsplit
from . import network
from .model import text, url

EXTENSIONS = {'mp4','webm','ogv','mov','mkv','mp3','m4a','ogg','wav','flac'}


def worker_args(*args):
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--worker', *args]
    return [sys.executable, '-m', 'scenetrace', '--worker', *args]


def ffmpeg_path():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        import shutil
        return shutil.which('ffmpeg')


def worker(request):
    if sys.platform == 'win32':
        import truststore
        truststore.inject_into_ssl()
    import yt_dlp
    opts = dict(proxy=request['proxy'], quiet=True, no_warnings=True, noplaylist=True,
                socket_timeout=12, retries=1, extractor_retries=0, geo_bypass=False,
                cachedir=False, age_limit=0, plugin_dirs=[], js_runtimes={},
                remote_components=set(), compat_opts={'no-certifi'}, playlistend=1, allowed_extractors=['default'],
                ffmpeg_location=ffmpeg_path(), hls_prefer_native=True)
    if request.get('download'):
        def hook(data):
            # JSON lines consumed by parent; do not emit provider URLs or headers.
            out = {k:data.get(k) for k in ('status','downloaded_bytes','total_bytes','total_bytes_estimate','speed','eta')}
            print(json.dumps(out), flush=True)
        fmt = str(request['format_id'])
        if not re.fullmatch(r'[\w.-]+', fmt):
            raise ValueError('Invalid format ID')
        opts.update(format=fmt, outtmpl=request['output'], continuedl=True, nopart=False,
                    progress_hooks=[hook], overwrites=False,
                    postprocessor_args={'ffmpeg_i':['-protocol_whitelist','file,pipe']})
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(request['url'], download=False)
        if not info or info.get('_type') in ('playlist','multi_video'):
            raise ValueError('Select a single public video.')
        if (info.get('age_limit') or 0) > 0 or info.get('availability') in ('private','premium_only','subscriber_only','needs_auth'):
            raise ValueError('The source requires restricted access. Use its official viewing page.')
        if request.get('download'):
            selected = next((x for x in info.get('formats', []) if str(x.get('format_id')) == fmt), None)
            if not selected or selected.get('has_drm') or selected.get('protocol') not in ('http','https'):
                raise ValueError('This format is no longer a supported public direct media format.')
            ydl.download([request['url']])
            return {'complete':True}
        formats = []
        for x in info.get('formats') or []:
            if x.get('has_drm') or x.get('protocol') not in ('http','https') or x.get('ext') not in EXTENSIONS:
                continue
            if not re.fullmatch(r'[\w.-]+', str(x.get('format_id',''))):
                continue
            formats.append(dict(id=str(x['format_id']), ext=x['ext'], height=x.get('height'),
                                size=x.get('filesize') or x.get('filesize_approx'),
                                label=x.get('format_note') or x.get('format') or x['ext'],
                                video=x.get('vcodec') != 'none', audio=x.get('acodec') != 'none',
                                method='extractor'))
        return dict(title=text(info.get('title')), description=text(info.get('description')),
                    thumbnail=url(info.get('thumbnail')), creators=[text(info.get('uploader'))],
                    duration=info.get('duration'), license=text(info.get('license')), formats=formats,
                    extractor=info.get('extractor_key'))


def analyze(value, proxy):
    value = url(value)
    if not value:
        raise ValueError('Enter a public video or webpage URL.')
    network.target(value)
    p = urlsplit(value)
    if p.hostname in ('archive.org','www.archive.org') and p.path.startswith(('/details/','/download/')):
        ident = unquote(p.path.split('/')[2])
        if not re.fullmatch(r'[\w.-]+', ident):
            raise ValueError('Invalid Archive identifier.')
        raw = network.json_request('https://archive.org/metadata/'+quote(ident))
        meta = raw.get('metadata') or {}
        if raw.get('is_dark') or raw.get('is_restricted') or raw.get('is_lendable'):
            return {'title':text(meta.get('title')), 'url':value, 'formats':[], 'status':'Unsupported or inaccessible', 'notice':'Use the official Archive page for access to this item.'}
        formats = []
        for x in raw.get('files', []):
            name = str(x.get('name',''))
            ext = name.rsplit('.',1)[-1].lower()
            if ext in EXTENSIONS and not x.get('private'):
                formats.append(dict(id=str(len(formats)), ext=ext, size=int(x.get('size') or 0) or None, height=None,
                                    video=ext not in ('mp3','m4a','ogg','wav','flac'), audio=True,
                                    label=name, url='https://archive.org/download/'+quote(ident)+'/'+quote(name, safe=''), method='direct'))
        info = dict(title=text(meta.get('title')), description=text(meta.get('description')), creators=[text(meta.get('creator'))],
                    thumbnail='https://archive.org/services/img/'+quote(ident), license=text(meta.get('licenseurl')), formats=formats)
    elif p.hostname == 'commons.wikimedia.org' and unquote(p.path).startswith('/wiki/File:'):
        title = unquote(p.path.removeprefix('/wiki/'))
        raw = network.json_request('https://commons.wikimedia.org/w/api.php?'+urlencode({'action':'query','format':'json','titles':title,'prop':'videoinfo','viprop':'url|size|extmetadata|derivatives','viurlwidth':640}))
        page = next(iter(raw.get('query',{}).get('pages',{}).values()), {})
        v = (page.get('videoinfo') or [{}])[0]
        meta = v.get('extmetadata') or {}
        formats = []
        for x in [{'src':v.get('url'), 'size':v.get('size'), 'height':v.get('height')}, *(v.get('derivatives') or [])]:
            src = url(x.get('src'))
            ext = urlsplit(src).path.rsplit('.',1)[-1].lower()
            if ext in EXTENSIONS:
                formats.append(dict(id=str(len(formats)), ext=ext, size=x.get('size'), height=x.get('height'), video=True, audio=True, label=str(x.get('height') or 'Original'), url=src, method='direct'))
        info = dict(title=title.removeprefix('File:'), description=text(meta.get('ImageDescription',{}).get('value')),
                    license=text(meta.get('LicenseUrl',{}).get('value')), creators=[text(meta.get('Artist',{}).get('value'))],
                    thumbnail=url(v.get('thumburl')), formats=formats)
    else:
        request = dict(url=value, proxy=proxy)
        try:
            proc = subprocess.run(worker_args(), input=json.dumps(request), text=True, capture_output=True, timeout=50,
                                  creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if proc.returncode:
                return {'title':'Video at '+p.hostname, 'url':value, 'formats':[], 'status':'Unsupported or inaccessible',
                        'notice':'The source did not expose supported public video metadata. Open the original page; login, DRM and other access controls are not bypassed.'}
            info = json.loads(proc.stdout)
        except subprocess.TimeoutExpired:
            raise ValueError('Link analysis timed out. Try the official video page.')
    info.update(url=value, source=p.hostname, analyzed=time.time())
    info['status'] = 'Download available' if info.get('formats') else 'Metadata only'
    direct = next((f['url'] for f in info.get('formats', []) if f.get('method') == 'direct' and f.get('video') and f['ext'] in ('mp4','webm','ogv')), None)
    # Direct media was supplied by an official catalog; browser may still reject codecs.
    info['preview_url'] = direct
    info['notice'] = 'Formats were reported by the source. Confirm that your download is authorized. A listed format does not grant content rights.'
    return info


def classify(candidate, selected):
    title = candidate['title'].casefold()
    if any(x in title for x in ('trailer','teaser','preview')):
        return 'Trailer / preview'
    if any(x in title for x in ('clip','scene','excerpt','highlight')):
        return 'Clip'
    if 'full' in title and any(x in title for x in ('movie','film','episode','documentary')):
        return 'Full-length claimed by uploader; unconfirmed'
    duration, expected = candidate.get('duration'), selected.get('duration')
    if duration and expected and duration < expected*.65:
        return 'Shorter than catalog runtime'
    return 'Video; full-length status unconfirmed'
