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

EXTENSIONS = {'mp4','m4v','webm','ogv','mov','mkv','avi','mpeg','mpg','ts','m2ts','flv','3gp',
              'mp3','m4a','ogg','opus','wav','flac','aac','mka'}
TRANSFER_PROTOCOLS = {'http', 'https', 'm3u8_native', 'http_dash_segments'}


def format_issue(item):
    if item.get('has_drm'):
        return 'The source reports encrypted, DRM-protected media; no compatible decrypted format was provided.'
    if item.get('protocol') not in TRANSFER_PROTOCOLS:
        return 'The reported transport is not supported: ' + str(item.get('protocol') or 'unknown')
    if not re.fullmatch(r'[a-zA-Z0-9]{1,10}', str(item.get('ext', ''))):
        return 'The source did not report a usable file extension.'
    return ''


def failure_detail(error):
    """Classify observed failures without leaking signed URLs, cookies or headers."""
    message = str(error).lower()
    cases = [
        (('certificate verify failed', 'certificate_verify_failed'), 'certificate', 'Certificate validation failed. Check Windows certificates, the clock, and any HTTPS-inspecting antivirus or proxy.'),
        (('no space left', 'disk full'), 'disk_full', 'The destination disk is full. Free space and retry.'),
        (('permission denied',), 'permission', 'SceneTrace cannot write to the selected folder. Choose a writable folder.'),
        (('http error 401', 'http error 403', 'status 403', 'sign in', 'login required'), 'access', 'The source refused this request. Open the original page in the browser; an ordinary website download remains available independently.'),
        (('expired',), 'expired', 'The media URL expired. Refresh this video and try again.'),
        (('http error 404', 'not found'), 'unavailable', 'This media address is no longer available. Refresh the original page.'),
        (('drm',), 'protected', 'The source reports protected media without a compatible download format.'),
        (('unsupported url', 'no video formats', 'unsupported transport'), 'unsupported', 'No compatible media format was found. Use the original page or its ordinary download button.'),
        (('timed out', 'connection', 'network', 'name resolution'), 'network', 'The network request failed. Check connectivity and retry.'),
    ]
    for needles, code, detail in cases:
        if any(needle in message for needle in needles):
            return {'code': code, 'message': detail}
    return {'code': 'extraction', 'message': 'The extractor could not read this video. Refresh the page or use its ordinary browser download; this is not evidence of protected media.'}


def worker_args(*args):
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--worker', *args]
    return [sys.executable, '-m', 'scenetrace', '--worker', *args]


def ffmpeg_path():
    # Linux distributions supply a maintained build; imageio's older static Linux
    # binary crashes while probing MPEG-TS on some glibc hosts. Windows releases
    # continue to use the bundled binary and need no system installation.
    import shutil
    if sys.platform.startswith('linux') and not getattr(sys, 'frozen', False):
        installed = shutil.which('ffmpeg')
        if installed:
            return installed
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        return shutil.which('ffmpeg')


def worker(request):
    import yt_dlp
    opts = dict(proxy=request['proxy'], quiet=True, no_warnings=True, noplaylist=True,
                socket_timeout=12, retries=1, extractor_retries=0, geo_bypass=False,
                cachedir=False, plugin_dirs=[], js_runtimes={},
                remote_components=set(), compat_opts={'no-certifi'}, playlistend=1, allowed_extractors=['default'],
                ffmpeg_location=ffmpeg_path(), hls_prefer_native=True)
    if request.get('download'):
        def hook(data):
            # JSON lines consumed by parent; do not emit provider URLs or headers.
            out = {k:data.get(k) for k in ('status','downloaded_bytes','total_bytes','total_bytes_estimate','speed','eta')}
            print(json.dumps(out), flush=True)
        fmt = str(request['format_id'])
        format_ids = fmt.split('+')
        if len(format_ids) not in (1, 2) or any(not re.fullmatch(r'[\w.-]+', part) for part in format_ids):
            raise ValueError('Invalid format ID')
        if len(format_ids) == 2:
            opts['merge_output_format'] = 'mkv'
        opts.update(format=fmt, outtmpl=request['output'], continuedl=True, nopart=False,
                    progress_hooks=[hook], overwrites=False,
                    postprocessor_args={'ffmpeg_i':['-protocol_whitelist','file,pipe']})
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(request['url'], download=False)
        if not info or info.get('_type') in ('playlist','multi_video'):
            raise ValueError('Select a single public video.')
        if request.get('download'):
            by_id = {str(item.get('format_id')): item for item in info.get('formats', [])}
            tracks = [by_id.get(part) for part in format_ids]
            if any(not track or format_issue(track) for track in tracks):
                raise ValueError(next((format_issue(track) for track in tracks if track and format_issue(track)), 'The selected format is no longer available. Refresh this video.'))
            if len(tracks) == 2 and not (
                tracks[0].get('vcodec') not in (None, 'none') and tracks[0].get('acodec') == 'none'
                and tracks[1].get('vcodec') == 'none' and tracks[1].get('acodec') not in (None, 'none')
            ):
                raise ValueError('The selected video and audio tracks no longer match.')
            ydl.download([request['url']])
            return {'complete':True}
        formats, unsupported = [], []
        for x in info.get('formats') or []:
            issue = format_issue(x)
            if issue:
                unsupported.append({'id': str(x.get('format_id', '')), 'reason': issue})
                continue
            if not re.fullmatch(r'[\w.-]+', str(x.get('format_id',''))):
                continue
            formats.append(dict(id=str(x['format_id']), ext=x['ext'], height=x.get('height'),
                                size=x.get('filesize') or x.get('filesize_approx'),
                                label=x.get('format_note') or x.get('format') or x['ext'],
                                video=x.get('vcodec') != 'none', audio=x.get('acodec') != 'none',
                                protocol=x.get('protocol'), method='extractor'))
        audio = next((f for f in reversed(formats) if f['audio'] and not f['video']), None)
        if audio and ffmpeg_path():
            combinations = []
            for f in formats:
                if f['video'] and not f['audio']:
                    size = f['size'] + audio['size'] if f['size'] and audio['size'] else None
                    combinations.append(dict(f, id=f['id'] + '+' + audio['id'], ext='mkv', size=size,
                                             label=f['label'] + ' with audio', audio=True))
            formats = combinations + formats
        return dict(title=text(info.get('title')), description=text(info.get('description')),
                    thumbnail=url(info.get('thumbnail')), creators=[text(info.get('uploader'))],
                    duration=info.get('duration'), license=text(info.get('license')), formats=formats,
                    extractor=info.get('extractor_key'), unsupported_formats=unsupported)


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
        if raw.get('is_dark'):
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
                try:
                    failure = json.loads(proc.stdout.splitlines()[-1]).get('failure') or failure_detail(proc.stderr)
                except (ValueError, IndexError):
                    failure = failure_detail(proc.stderr)
                return {'title':'Video at '+p.hostname, 'url':value, 'formats':[], 'status':'Unsupported or inaccessible',
                        'failure':failure['code'], 'notice':failure['message']}
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
