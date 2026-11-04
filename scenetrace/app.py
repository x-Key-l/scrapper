"""Local application services. UI, adapters and downloads share one SQLite store."""
import base64
import hashlib
import json
import logging
import os
import platform
import shutil
import threading
import time
import uuid
from pathlib import Path
from . import __version__, discovery, importing, media, network, sources
from .downloads import DownloadManager
from .viewing import Viewing, probe_file
from .search import SearchEngine
from .store import Store, protect

log = logging.getLogger('scenetrace')


class App:
    def __init__(self, root, proxy):
        self.store = Store(root)
        sources.defaults(self.store)
        self.proxy = proxy
        self.search = SearchEngine(self.store)
        self.downloads = DownloadManager(self.store, proxy)
        self.analyses = {}
        self.viewing = Viewing(self)
        self.uploads = {}
        self.tasks = {}
        self.task_lock = threading.Lock()
        self.folder = Path.home()/'Downloads'/'SceneTrace'
        self.folder.mkdir(parents=True, exist_ok=True)
        self.imports = self.store.root/'imports'
        self.imports.mkdir(exist_ok=True)

    def state(self):
        return dict(version=__version__, sources=self.store.sources(public=True), saved=self.store.saved(),
                    history=self.store.history(), downloads=self.downloads.all(), tasks={k:dict(v) for k,v in list(self.tasks.items())},
                    settings={'destination':self.store.setting('destination',str(self.folder)), 'onboarded':self.store.setting('onboarded',False),
                              'brave_configured':bool(self.store.setting('brave_key','')), 'ffmpeg':bool(media.ffmpeg_path())})

    def task(self, label, fn):
        ident = uuid.uuid4().hex
        task = dict(id=ident, label=label, status='running', progress='Starting…', created=time.time())
        self.tasks[ident] = task
        def work():
            try:
                result = fn(lambda msg:task.update(progress=msg))
                task.update(status='completed', progress='Finished', result=result)
            except Exception as exc:
                task.update(status='failed', error=str(exc) if isinstance(exc, ValueError) else 'The operation could not finish. Check the source or file and try again.')
                log.warning('task_failed kind=%s',type(exc).__name__)
        threading.Thread(target=work,daemon=True).start()
        return task

    def source(self, ident):
        s = self.store.source(ident)
        if not s:
            raise ValueError('Source not found.')
        return s

    def source_update(self, body):
        previous = self.store.source(body.get('id'))
        cfg = dict(previous or {}, **body)
        # local_path is always set by an import or native picker, never a configuration.
        cfg.pop('local_path',None)
        if previous and previous.get('local_path'):
            cfg['local_path'] = previous['local_path']
        cfg = sources.validate(cfg,previous)
        if body.get('clear_token'):
            cfg.pop('token',None)
        if cfg['kind']=='local' and not previous:
            raise ValueError('Choose Import Database to add a local source.')
        self.store.put_source(cfg)
        with self.store.db() as c:
            c.execute('DELETE FROM cache')
        return {'source':next(s for s in self.store.sources(public=True) if s['id']==cfg['id'])}

    def test_source(self, ident):
        s = self.source(ident)
        def save_health():
            current = self.store.source(ident)
            if current:
                current.update({k:s[k] for k in ('health','last_sync','last_error') if k in s})
                self.store.put_source(current)
        try:
            if s['kind']=='local':
                p = importing.preview(s['local_path'],s.get('table',''),s.get('items_path',''))
                count = len(p['samples'])
            else:
                rows, _ = sources.search(s,'Naruto' if s['kind']=='anilist' else 'nature')
                count = len(rows)
                self.store.put_records(rows)
            s.update(health='Verified',last_sync=time.time(),last_error='')
        except Exception as exc:
            s.update(health='Unavailable',last_error=str(exc) if isinstance(exc,ValueError) else 'Connection failed. Check internet access and provider availability.')
            save_health()
            return {'ok':False,'message':s['last_error']}
        save_health()
        return {'ok':True,'message':f'Connection verified; {count} sample records received.','count':count}

    def refresh(self, ident):
        s = self.source(ident)
        def work(progress):
            if s['kind']=='local':
                progress('Reading and indexing the local database…')
                count = importing.import_source(self.store,s,lambda n:progress(f'Indexed {n:,} records'))
                s.update(health='Verified',last_sync=time.time(),sync={'records':count})
                self.store.put_source(s)
                return {'records':count}
            progress('Refreshing cached query and source health…')
            result = self.search.run(s.get('last_query') or 'nature',[s['id']],refresh=True)
            if any(x['status'] not in ('ok','local index') for x in result['sources']):
                raise ValueError(result['sources'][0].get('message','Source could not be refreshed.'))
            return {'records':len(result['results']), 'notice':'Incremental query cache refresh; the entire external database is not copied.'}
        return self.task('Refresh '+s['name'],work)

    def upload(self, body):
        name = Path(str(body.get('name','database.json'))).name
        suffix = Path(name).suffix.lower()
        if suffix not in ('.csv','.tsv','.json','.jsonl','.ndjson','.db','.sqlite','.sqlite3','.rss','.atom','.xml'):
            raise ValueError('Choose a supported database export or feed.')
        try:
            raw = base64.b64decode(body.get('data',''),validate=True)
        except ValueError:
            raise ValueError('The selected file could not be read.')
        key = uuid.uuid4().hex
        path = self.imports/(key+suffix)
        path.write_bytes(raw)
        self.uploads[key] = {'path':str(path),'name':name,'created':time.time()}
        try:
            preview = importing.preview(path)
        except Exception:
            path.unlink(missing_ok=True)
            self.uploads.pop(key,None)
            raise
        return dict(preview,upload_id=key,name=name)

    def import_preview(self, body):
        u = self.uploads.get(body.get('upload_id'))
        if not u:
            raise ValueError('Choose the file again to preview it.')
        return importing.preview(u['path'],body.get('table',''),body.get('items_path',''))

    def import_commit(self, body):
        u = self.uploads.get(body.get('upload_id'))
        if not u:
            raise ValueError('Choose the file again before importing.')
        c = sources.validate(dict(name=body.get('name') or u['name'],kind='local',role=body.get('role','metadata'),
                                  categories=body.get('categories') or ['video'],mapping=body.get('mapping') or {},
                                  table=body.get('table',''),items_path=body.get('items_path',''),enabled=True))
        c['local_path']=u['path']
        def work(progress):
            progress('Indexing imported records…')
            count=importing.import_source(self.store,c,lambda n:progress(f'Indexed {n:,} records'))
            c.update(health='Verified',last_sync=time.time(),sync={'records':count})
            self.store.put_source(c)
            self.uploads.pop(body['upload_id'],None)
            return {'records':count,'source_id':c['id']}
        return self.task('Import '+c['name'],work)

    def analyze(self, value):
        return self.register_analysis(media.analyze(value,self.proxy))

    def register_analysis(self, result):
        key=uuid.uuid4().hex
        self.analyses[key]=result
        for old,v in list(self.analyses.items()):
            if time.time()-v.get('analyzed',time.time())>3600:
                self.analyses.pop(old,None)
        return {**result,'analysis_id':key,'formats':[{k:v for k,v in f.items() if k!='url'} for f in result.get('formats',[])]}

    def resolve(self, selected):
        if not isinstance(selected,dict) or not selected.get('title'):
            raise ValueError('Choose a catalog result first.')
        queries=list(dict.fromkeys([selected['title'],*(selected.get('alternatives') or [])]))[:3]
        found, statuses=[],[]
        for q in queries[:2]:
            r=self.search.run(q,mode='media')
            found.extend(r['results'])
            statuses.extend(r['sources'])
        from .search import deduplicate, rank
        hits=rank(selected['title'],deduplicate(found))
        for r in hits:
            r['media_kind']=media.classify(r,selected)
        return {'results':hits,'sources':statuses,'has_more':False,
                'known_links':selected.get('media_urls',[]),
                'notice':'Candidate videos require a separate Analyze check. Title overlap does not establish that this is the full work or that downloads are authorized.'}

    def download(self, body):
        a=self.analyses.get(body.get('analysis_id'))
        if not a or time.time()-a.get('analyzed',0)>3600:
            raise ValueError('Analyze the link again; available formats have expired.')
        fmt=next((f for f in a.get('formats',[]) if f['id']==body.get('format_id')),None)
        if not fmt:
            raise ValueError('Select an available quality and format.')
        if a.get('download_allowed') and fmt.get('method') == 'direct':
            probe_file(fmt['url'], browser=False)
        dest=body.get('destination') or self.store.setting('destination',str(self.folder))
        return self.downloads.add(a,fmt,dest,body.get('authorized') is True,body.get('output','original'))

    def settings(self, body):
        if 'destination' in body:
            path=Path(body['destination']).expanduser().resolve()
            if not path.is_dir():
                raise ValueError('Select an existing destination folder.')
            self.store.set_setting('destination',str(path))
        if 'brave_key' in body and body['brave_key']:
            self.store.set_setting('brave_key',protect(str(body['brave_key'])))
        if body.get('clear_brave'):
            self.store.set_setting('brave_key','')
        if 'onboarded' in body:
            self.store.set_setting('onboarded',bool(body['onboarded']))
        if body.get('clear_history'):
            with self.store.db() as c:
                c.execute('DELETE FROM history')
        if body.get('clear_cache'):
            with self.store.db() as c:
                c.execute('DELETE FROM cache')
                ids=[s['id'] for s in self.store.sources() if s['kind']!='local']
                for ident in ids:
                    c.execute('DELETE FROM search_fts WHERE id IN (SELECT id FROM records WHERE source=?)',(ident,))
                    c.execute('DELETE FROM records WHERE source=?',(ident,))
        return {'ok':True}

    def diagnostics(self):
        import yt_dlp.version
        return {'version':__version__,'os':platform.system()+' '+platform.release(),'python':platform.python_version(),
                'yt_dlp':yt_dlp.version.__version__,'ffmpeg':bool(media.ffmpeg_path()),'sqlite_fts5':True,
                'sources':[{'name':s['name'],'kind':s['kind'],'health':s.get('health'),'last_sync':s.get('last_sync')} for s in self.store.sources(public=True)],
                'downloads':{status:sum(j['status']==status for j in self.downloads.all()) for status in ('queued','downloading','paused','completed','failed','cancelled')},
                'note':'Credentials, search history, source URLs, filenames and local paths are omitted.'}

    def native_pick(self, kind):
        import tkinter as tk
        from tkinter import filedialog
        root=tk.Tk()
        root.withdraw()
        root.attributes('-topmost',True)
        try:
            path=filedialog.askdirectory(parent=root,title='Choose download folder') if kind=='folder' else filedialog.askopenfilename(parent=root,title='Choose database export',filetypes=[('Database exports','*.csv *.tsv *.json *.jsonl *.ndjson *.db *.sqlite *.sqlite3 *.rss *.atom *.xml')])
        finally:
            root.destroy()
        if not path:
            return {'cancelled':True}
        if kind=='folder':
            return {'path':path}
        source_path=Path(path)
        key=uuid.uuid4().hex
        dest=self.imports/(key+source_path.suffix.lower())
        shutil.copyfile(source_path,dest)
        self.uploads[key]={'path':str(dest),'name':source_path.name,'created':time.time()}
        try:
            return dict(importing.preview(dest),upload_id=key,name=source_path.name)
        except Exception:
            dest.unlink(missing_ok=True)
            self.uploads.pop(key,None)
            raise

    def open_download(self, key, folder=False):
        j=self.downloads.items.get(key)
        if not j or j['status']!='completed' or not Path(j['path']).is_file():
            raise ValueError('This download is not available on disk.')
        target=Path(j['path']).parent if folder else Path(j['path'])
        if os.name=='nt':
            os.startfile(str(target))
        else:
            import subprocess
            subprocess.Popen(['open' if platform.system()=='Darwin' else 'xdg-open',str(target)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return {'ok':True}

    def call(self, path, body):
        if path=='/api/state': return self.state()
        if path=='/api/watch/search': return self.viewing.search(body)
        if path=='/api/watch/details':
            item = body.get('record')
            if not isinstance(item, dict) or not item.get('title'):
                raise ValueError('Select a title first.')
            return self.viewing.details(item)
        if path=='/api/watch/play': return self.viewing.play(body.get('ticket', ''))
        if path=='/api/network/tls': return network.tls_diagnostics('https://archive.org/metadata/BigBuckBunny_328')

        if path=='/api/search':
            hints=body.get('hints') or {}
            query=body.get('query','')
            extra=' '.join(str(v) for k,v in hints.items() if k not in ('category','decade') and v)
            return self.search.run(query+' '+extra if extra else query,body.get('sources'),body.get('page',1),body.get('mode','search'),hints,body.get('refresh',False),body.get('request_id',''))
        if path=='/api/search/cancel':
            self.search.cancel(str(body.get('request_id','')))
            return {'ok':True}
        if path=='/api/source/save': return self.source_update(body)
        if path=='/api/source/delete':
            self.store.delete_source(str(body.get('id','')))
            return {'ok':True}
        if path=='/api/source/test': return self.test_source(str(body.get('id','')))
        if path=='/api/source/refresh': return self.refresh(str(body.get('id','')))
        if path=='/api/source/detect': return sources.detect(body.get('url',''))
        if path=='/api/import/upload': return self.upload(body)
        if path=='/api/import/preview': return self.import_preview(body)
        if path=='/api/import/commit': return self.import_commit(body)
        if path=='/api/native/pick': return self.native_pick(body.get('kind','folder'))
        if path=='/api/discover':
            key=self.store.setting('brave_key','')
            if key.startswith('dpapi:'): key=protect(key,True)
            return discovery.find(str(body.get('query','')),key)
        if path=='/api/analyze': return self.analyze(body.get('url',''))
        if path=='/api/resolve': return self.resolve(body.get('record'))
        if path=='/api/download/add': return self.download(body)
        if path=='/api/download/control': return self.downloads.control(body.get('id'),body.get('action'))
        if path=='/api/download/open': return self.open_download(body.get('id'),bool(body.get('folder')))
        if path=='/api/save':
            record=body.get('record')
            if not isinstance(record,dict) or not isinstance(record.get('id'),str): raise ValueError('Choose a result to save.')
            self.store.save(record,body.get('remove',False))
            return {'ok':True}
        if path=='/api/settings': return self.settings(body)
        if path=='/api/diagnostics': return self.diagnostics()
        raise ValueError('Unknown application action.')

    def close(self):
        self.downloads.close()
        self.search.close()
        for u in self.uploads.values():
            Path(u['path']).unlink(missing_ok=True)
