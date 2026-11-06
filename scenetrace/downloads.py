"""Persistent resource-aware queue. No fixed file-size, quality or queue limits."""
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from . import network, media

RESERVED = {'CON','PRN','AUX','NUL'} | {f'{x}{n}' for x in ('COM','LPT') for n in range(1,10)}


def safe_name(value):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value)).strip(' .')[:140] or 'video'
    if name.split('.')[0].upper() in RESERVED:
        name = '_'+name
    return name


class DownloadManager:
    def __init__(self, store, proxy, workers=2, completed=None):
        self.store, self.proxy = store, proxy
        self.completed = completed or (lambda job: None)
        self.browser_commands = []
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
                if j.get('engine') == 'browser':
                    j.update(status='failed', can_resume=False, error='The browser session ended. Open the source page to start this website download again.')
                self.store.job(j)
            if j.get('engine') == 'browser' and j['status'] not in ('completed','cancelled'):
                j.update(status='failed',can_resume=False,error='The browser session ended. Open the source page to start this website download again.')
                self.store.job(j)
            if j['status'] == 'completed': self.completed(j)
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
        from .library import destination_folder
        folder = destination_folder(self.store, folder, info['url'], info['title'], info.get('category','Unsorted'))
        required = int(fmt.get('size') or 0) + 32*1024*1024
        if shutil.disk_usage(folder).free < required:
            raise ValueError('There is not enough free space in the destination.')
        key = uuid.uuid4().hex
        ext = fmt['ext'] if output == 'original' else output
        name = safe_name(info['title'])
        suffix = '.' + fmt['ext']
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
        j = dict(id=key, title=info['title'], source=info['url'], extractor_url=info['url'], engine=fmt.get('method','extractor'),
                 extension=ext, height=fmt.get('height'), category=info.get('category','Unsorted'),
                 format=fmt, output=output, destination=str(folder), path=str(final), part=str(part),
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
            if action == 'remove':
                if j['status'] not in ('completed','failed','cancelled') or j.get('_running'):
                    raise ValueError('Finish or cancel this transfer before removing its history.')
                with self.store.db() as c: c.execute('DELETE FROM jobs WHERE id=?',(key,))
                self.items.pop(key)
                self.events.pop(key,None)
                return {'ok':True}
            if j.get('engine') == 'browser':
                if action not in ('pause','resume','retry','cancel'):
                    raise ValueError('Unknown download action.')
                if action in ('resume','retry') and not j.get('can_resume'):
                    raise ValueError('This browser transfer cannot resume. Open its source page to download again.')
                if j['status'] in ('completed','cancelled'):
                    raise ValueError('This download has finished.')
                self.browser_commands.append({'id':key,'action':action})
                return self.public(j)
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
            with self.lock:
                j = self.items.get(key)
                if not j or j['status'] != 'queued':
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
                self._cleanup(j, reserve=False)
                self.completed(j)
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
        req = dict(url=j['extractor_url'], proxy=self.proxy, download=True, format_id=j['format']['id'], output=j['part'])
        proc = subprocess.Popen(media.worker_args(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        proc.stdin.write(json.dumps(req))
        proc.stdin.close()
        def read():
            for line in proc.stdout:
                try:
                    d = json.loads(line)
                    if d.get('failure'):
                        j['failure'] = d['failure']['code']
                        j['error'] = d['failure']['message']
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
                raise ValueError(j.get('error') or 'The source could not deliver this format. Refresh the video or use its ordinary website download.')
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()

    def _convert(self, j):
        j['status'] = 'converting'
        self.persist(j)
        args = [media.ffmpeg_path(),'-nostdin','-hide_banner','-loglevel','error','-y',
                '-protocol_whitelist','file,pipe','-i',j['part'],'-threads','2']
        args += ['-vn','-c:a','libmp3lame','-q:a','2'] if j['output']=='mp3' else ['-c:v','libx264','-preset','veryfast','-crf','23','-c:a','aac','-movflags','+faststart']
        args += [j['temporary']]
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            while proc.poll() is None:
                self._check(j)
                self.events[j['id']].wait(.2)
            if proc.returncode:
                raise ValueError('Conversion failed. Retry with Original format.')
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()

    def close(self):
        self.stopping.set()
        for e in self.events.values():
            e.set()
        for t in self.threads:
            t.join(timeout=4)

    def browser_sync(self, updates):
        """Only the authenticated native host calls this; no browser cookies cross it."""
        with self.lock:
            for update in updates:
                key=str(update.get('id',''))
                if not re.fullmatch(r'[a-f0-9]{32}', key): raise ValueError('Invalid browser transfer identifier.')
                status=update.get('status')
                if status not in ('downloading','paused','completed','cancelled','failed'): raise ValueError('Invalid browser transfer state.')
                job=self.items.get(key)
                if job and job.get('engine')!='browser': raise ValueError('Transfer engine cannot change.')
                was_complete=job and job['status']=='completed'
                job=dict(job or {},id=key,engine='browser',created=(job or {}).get('created',time.time()))
                for field in ('title','source','path','status','bytes','total','speed','eta','can_resume','error','failure'):
                    if field in update: job[field]=update[field]
                job['destination']=str(Path(job['path']).parent)
                job['extension']=Path(job['path']).suffix.lstrip('.')
                job['progress']=100 if status=='completed' else (min(100,100*job['bytes']/job['total']) if job.get('total') else None)
                if status=='completed' and not was_complete:
                    file=Path(job['path'])
                    if not file.is_file() or file.stat().st_size!=job['bytes']:
                        raise ValueError('The browser completion file does not match the reported transfer.')
                    self.completed(job)
                self.items[key]=job
                self.persist(job)
            commands,self.browser_commands=self.browser_commands,[]
            return {'commands':commands}
