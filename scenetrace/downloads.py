"""Persistent resource-aware queue. No fixed file-size, quality or queue limits."""
import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from . import network, media

RESERVED = {'CON','PRN','AUX','NUL'} | {f'{x}{n}' for x in ('COM','LPT') for n in range(1,10)}


def safe_name(value):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value)).strip(' .')[:140] or 'video'
    if name.split('.')[0].upper() in RESERVED:
        name = '_'+name
    return name


class DownloadManager:
    def __init__(self, store, proxy, workers=2):
        self.store, self.proxy = store, proxy
        self.lock = threading.RLock()
        self.items = {j['id']:j for j in store.jobs()}
        self.events = {}
        self.stopping = threading.Event()
        self.queue = queue.Queue()
        self.threads = []
        for j in self.items.values():
            j.pop('_running', None)
            if j['status'] in ('queued','downloading','converting'):
                j.update(status='paused', error='SceneTrace closed before this transfer finished. Choose Resume.')
                self.store.job(j)
        for n in range(workers):
            t = threading.Thread(target=self._loop, name=f'download-{n}', daemon=True)
            t.start()
            self.threads.append(t)

    def public(self, j):
        return {k:v for k,v in j.items() if k not in ('format','part','temporary','extractor_url','etag','_running')}

    def all(self):
        with self.lock:
            return [self.public(j) for j in sorted(self.items.values(), key=lambda j:-j['created'])]

    def persist(self, j):
        self.store.job(j)

    def add(self, info, fmt, destination, authorized=False, output='original'):
        if output not in ('original','mp4','mp3'):
            raise ValueError('Choose Original, MP4 or MP3.')
        if output != 'original' and not media.ffmpeg_path():
            raise ValueError('FFmpeg is unavailable. Choose Original format.')
        folder = Path(destination).expanduser().resolve()
        if not folder.is_dir():
            raise ValueError('Choose an existing destination folder.')
        required = int(fmt.get('size') or 0) + 32*1024*1024
        if shutil.disk_usage(folder).free < required:
            raise ValueError('There is not enough free space in the destination.')
        key = uuid.uuid4().hex
        ext = fmt['ext'] if output == 'original' else output
        template = self.store.setting('filename_template', '%(title)s [%(height)sp].%(ext)s')
        fields = dict(title=info['title'], height=fmt.get('height') or 'original', ext=ext, uploader=', '.join(info.get('creators') or []))
        name = safe_name(re.sub(r'%\((title|height|ext|uploader)\)s', lambda match: str(fields[match[1]]), template))
        suffix = '.' + ext
        if name.lower().endswith(suffix.lower()):
            name = name[:-len(suffix)]
        final = folder / (name + '.' + ext)
        # Reserve a final path atomically so concurrent jobs cannot overwrite each other.
        for n in range(1000000):
            candidate = final if n == 0 else folder/(name+f' ({n}).'+ext)
            try:
                with candidate.open('xb'):
                    pass
                final = candidate
                break
            except FileExistsError:
                continue
        else:
            raise ValueError('Could not allocate a free destination filename.')
        part = folder/('.scenetrace-'+key+'.'+fmt['ext'])
        j = dict(id=key, title=info['title'], source=info['url'], extractor_url=fmt.get('extractor_url') or info['url'],
                 format=fmt, output=output, subtitles=info.get('selected_subtitles', []),
                 metadata={k:info.get(k) for k in ('title','url','creators','duration','license')}, destination=str(folder), path=str(final), part=str(part),
                 temporary=str(part)+'.converted.'+ext, status='queued', bytes=0, total=fmt.get('size'),
                 speed=None, eta=None, progress=None, error='', created=time.time(), etag='')
        with self.lock:
            self.items[key] = j
            self.events[key] = threading.Event()
            self.persist(j)
        self.queue.put(key)
        return self.public(j)

    def control(self, key, action):
        with self.lock:
            j = self.items.get(key)
            if not j:
                raise ValueError('Download not found.')
            if action in ('pause','cancel') and j['status'] not in ('completed','cancelled'):
                j['status'] = 'paused' if action == 'pause' else 'cancelled'
                self.events.setdefault(key, threading.Event()).set()
                if action == 'cancel' and not j.get('_running'):
                    self._cleanup(j)
            elif action in ('retry','resume') and j['status'] in ('paused','failed'):
                if j.get('_running'):
                    raise ValueError('The transfer is stopping. Try Resume in a moment.')
                j.update(status='queued', error='')
                self.events[key] = threading.Event()
                self.queue.put(key)
            else:
                raise ValueError('This action is not available in the current download state.')
            self.persist(j)
            return self.public(j)

    def _cleanup(self, j, reserve=True):
        for path in (j['part'], j['part']+'.part', j['temporary']):
            Path(path).unlink(missing_ok=True)
        if reserve and Path(j['path']).exists() and Path(j['path']).stat().st_size == 0:
            Path(j['path']).unlink(missing_ok=True)

    def _check(self, j, extra=0):
        if self.events[j['id']].is_set() or self.stopping.is_set():
            raise InterruptedError()
        if shutil.disk_usage(j['destination']).free < max(extra, 32*1024*1024):
            raise ValueError('Disk space is running low. Free space and choose Retry.')

    def _loop(self):
        while not self.stopping.is_set():
            try:
                key = self.queue.get(timeout=.25)
            except queue.Empty:
                continue
            j = self.items[key]
            with self.lock:
                if j['status'] != 'queued':
                    self.queue.task_done()
                    continue
                j['_running'] = True
                j['status'] = 'downloading'
                self.persist(j)
            try:
                if j['format'].get('method') == 'direct':
                    self._direct(j)
                else:
                    self._extractor(j)
                self._check(j)
                original = Path(j['part'])
                if not original.is_file() or original.stat().st_size == 0:
                    raise ValueError('Source returned no usable media.')
                if j['output'] != 'original':
                    self._convert(j)
                    original = Path(j['temporary'])
                os.replace(original, j['path'])
                j.update(status='completed', bytes=Path(j['path']).stat().st_size, progress=100, eta=0)
                try:
                    metadata = j.get('metadata') or {}
                    root = ET.Element('movie')
                    for key, tag in (('title','title'),('url','source'),('creators','uploader'),('duration','duration'),('license','license')):
                        value = metadata.get(key)
                        if value:
                            ET.SubElement(root, tag).text = ', '.join(value) if isinstance(value, list) else str(value)
                    if len(root):
                        sidecar = Path(j['path']).with_suffix('.nfo')
                        if sidecar.exists():
                            sidecar = Path(j['path'] + '.nfo')
                        with sidecar.open('xb') as out:
                            out.write(ET.tostring(root, encoding='utf-8', xml_declaration=True))
                    for lang in j.get('subtitles', []):
                        for subtitle in Path(j['part']).parent.glob(Path(j['part']).stem + '.' + lang + '.*'):
                            destination = Path(j['path'] + '.' + lang + subtitle.suffix)
                            with destination.open('xb') as out:
                                out.write(subtitle.read_bytes())
                            subtitle.unlink()
                except OSError as exc:
                    j['notice'] = 'Media completed; sidecar could not be saved: ' + str(exc)
                self._cleanup(j, reserve=False)
            except InterruptedError:
                if j['status'] not in ('cancelled','paused'):
                    j['status'] = 'paused'
                if j['status'] == 'cancelled':
                    self._cleanup(j)
            except Exception as exc:
                j.update(status='failed', error=str(exc) if isinstance(exc, ValueError) else 'Transfer interrupted or source unavailable. Choose Retry; partial data will resume if supported.')
                # Keep transfer partials for recovery, remove incomplete conversions.
                Path(j['temporary']).unlink(missing_ok=True)
            finally:
                with self.lock:
                    j.pop('_running', None)
                    self.persist(j)
                self.queue.task_done()

    def _direct(self, j):
        part = Path(j['part'])
        offset = part.stat().st_size if part.exists() else 0
        if offset and j.get('total') and offset == j['total']:
            j['bytes'] = offset
            return
        h = {'Range':f'bytes={offset}-'}
        if offset and j.get('etag'):
            h['If-Range'] = j['etag']
        for attempt in range(3):
            try:
                conn, response, _ = network.open_url(j['format']['url'], headers=h, timeout=20)
                break
            except network.RateLimitError as error:
                if attempt == 2 or error.delay > 15:
                    raise
                self.events[j['id']].wait(error.delay + .25)
                self._check(j)
        try:
            content_type = response.getheader('Content-Type', '').split(';')[0].lower()
            if content_type in ('text/html', 'application/xhtml+xml', 'application/json'):
                raise ValueError('The source returned a webpage instead of a media file.')
            if response.status == 206:
                match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+|\*)', response.getheader('Content-Range',''))
                if not match or int(match[1]) != offset:
                    raise ValueError('Source returned an invalid resume range. Analyze the link again.')
                total = int(match[3]) if match[3] != '*' else None
            else:
                offset = 0  # Range was ignored or resource changed: restart safely.
                total = int(response.getheader('Content-Length')) if response.getheader('Content-Length') else None
            j['etag'] = response.getheader('ETag') or response.getheader('Last-Modified') or ''
            j.update(bytes=offset, total=total)
            self._check(j, max(0, (total or 0)-offset)+32*1024*1024)
            start, last = time.monotonic(), time.monotonic()
            transferred = 0
            with part.open('ab' if offset else 'wb') as out:
                while True:
                    self._check(j)
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    out.write(chunk)
                    transferred += len(chunk)
                    j['bytes'] = offset+transferred
                    elapsed = max(.01,time.monotonic()-start)
                    j['speed'] = transferred/elapsed
                    j['eta'] = max(0,(total-j['bytes'])/j['speed']) if total and j['speed'] else None
                    j['progress'] = min(99,100*j['bytes']/total) if total else None
                    if time.monotonic()-last > .5:
                        self.persist(j)
                        last = time.monotonic()
            if total is not None and j['bytes'] != total:
                raise ValueError('Source ended early. Retry to resume the incomplete download.')
        finally:
            conn.close()

    def _extractor(self, j):
        req = dict(url=j['extractor_url'], proxy=self.proxy, cookies=media.COOKIE_BROWSER, download=True, subtitles=j.get('subtitles', []), format_id=j['format'].get('extractor_id', j['format']['id']), output=j['part'])
        errors = tempfile.TemporaryFile(mode='w+t', encoding='utf-8')
        proc = subprocess.Popen(media.worker_args(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=errors, text=True, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        proc.stdin.write(json.dumps(req))
        proc.stdin.close()
        def read():
            for line in proc.stdout:
                try:
                    d = json.loads(line)
                    if 'downloaded_bytes' in d:
                        j.update(bytes=d.get('downloaded_bytes') or 0, total=d.get('total_bytes') or d.get('total_bytes_estimate'), speed=d.get('speed'), eta=d.get('eta'))
                        j['progress'] = 100*j['bytes']/j['total'] if j.get('total') else None
                        self.persist(j)
                except (ValueError, TypeError):
                    pass
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        try:
            while proc.poll() is None:
                self._check(j)
                self.events[j['id']].wait(.2)
            reader.join(timeout=2)
            if proc.returncode:
                if j['format'].get('drm'):
                    raise ValueError('Protected stream. yt-dlp could not decrypt it.')
                errors.seek(0)
                detail = next((line.strip() for line in reversed(errors.read().splitlines()) if line.strip()), 'No extractor diagnostic was returned.')
                raise ValueError('The source could not deliver this format. ' + detail)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            errors.close()

    def _convert(self, j):
        j['status'] = 'converting'
        self.persist(j)
        args = [media.ffmpeg_path(),'-nostdin','-hide_banner','-loglevel','error','-y',
                '-protocol_whitelist','file,pipe','-i',j['part'],'-threads','2']
        copy = False
        probe = shutil.which('ffprobe')
        sibling = Path(media.ffmpeg_path()).with_name('ffprobe.exe' if os.name == 'nt' else 'ffprobe')
        if sibling.is_file():
            probe = str(sibling)
        if j['output'] == 'mp4' and probe:
            try:
                result = subprocess.run([probe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', j['part']],
                                        capture_output=True, text=True, timeout=15,
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    streams = data.get('streams', [])
                    copy = bool(streams) and any(x in data.get('format', {}).get('format_name', '').split(',') for x in ('mp4', 'mpegts')) and all(
                        stream.get('codec_name') in ('h264', 'aac') for stream in streams)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass  # Optional optimization; encoding remains available.
        args += (['-vn','-c:a','libmp3lame','-q:a','2'] if j['output']=='mp3' else
                 ['-c','copy','-movflags','+faststart'] if copy else
                 ['-c:v','libx264','-preset','veryfast','-crf','23','-c:a','aac','-movflags','+faststart'])
        args += [j['temporary']]
        errors = tempfile.TemporaryFile(mode='w+t', encoding='utf-8')
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=errors,
                                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            while proc.poll() is None:
                self._check(j)
                self.events[j['id']].wait(.2)
            if proc.returncode:
                errors.seek(0)
                detail = next((line.strip() for line in reversed(errors.read().splitlines()) if line.strip()), 'No FFmpeg diagnostic was returned.')
                raise ValueError('Conversion failed. ' + detail)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            errors.close()

    def close(self):
        self.stopping.set()
        for e in self.events.values():
            e.set()
        for t in self.threads:
            t.join(timeout=4)
