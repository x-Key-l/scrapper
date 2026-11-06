"""Local media catalog. Indexing never renames, deletes or moves a user's files."""
import json
import os
import re
import shutil
import threading
import time
import unicodedata
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from .media import EXTENSIONS

CATEGORIES = ['Anime','Movies','Television','Music videos','Documentaries','Educational videos','Other videos','Unsorted']


def component(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value)).strip(' .')[:140] or 'Unsorted'
    if value.split('.')[0].upper() in {'CON','PRN','AUX','NUL', *('COM'+str(n) for n in range(1,10)), *('LPT'+str(n) for n in range(1,10))}:
        value = '_'+value
    return value


def source_domain(value):
    try:
        return (urlsplit(value).hostname or 'Imported').lower().removeprefix('www.')
    except ValueError:
        return 'Imported'


def identity(value):
    return re.sub(r'[^\w]+', ' ', unicodedata.normalize('NFKC', str(value)).casefold()).strip()


def episode_metadata(filename):
    name = Path(filename).stem
    name = re.sub(r'^\[[^\]]+\]\s*', '', name)
    patterns = [r'(?i)\bS(\d{1,3})[ ._-]*E(\d{1,4})(?:\b|_)',
                r'(?i)\b(?:episode|ep|e)[ ._-]*(\d{1,4})(?:\b|_)',
                r'\s-\s(\d{1,3})(?=\s|\[|$)']
    for index, pattern in enumerate(patterns):
        match = re.search(pattern, name)
        if match:
            series = re.sub(r'[._]+', ' ', name[:match.start()]).strip(' -')
            if series:
                return {'series': series, 'season': int(match[1]) if index == 0 else None,
                        'episode': int(match[2] if index == 0 else match[1]), 'identity': identity(series)}
    return {'series':'', 'season':None, 'episode':None, 'identity':''}


def destination_folder(store, root, source, title='', category='Unsorted'):
    folder = Path(root)
    if store.setting('organize_by_source', True):
        folder /= component(source_domain(source))
    if store.setting('organize_by_series', False):
        parsed = episode_metadata(title)
        folder /= component(category)
        if parsed['series']:
            folder /= component(parsed['series'])
            if parsed['season'] is not None:
                folder /= 'Season '+str(parsed['season']).zfill(2)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


class MediaLibrary:
    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        with store.db() as c:
            c.execute('CREATE TABLE IF NOT EXISTS media_library(id TEXT PRIMARY KEY,path TEXT UNIQUE NOT NULL,data TEXT NOT NULL,updated REAL NOT NULL)')
            c.execute('CREATE INDEX IF NOT EXISTS library_updated ON media_library(updated DESC)')

    def get(self, key):
        with self.store.db() as c:
            row=c.execute('SELECT data FROM media_library WHERE id=?',(key,)).fetchone()
        if not row: raise ValueError('This library item was not found.')
        return json.loads(row[0])

    def put(self, item):
        with self.store.db() as c:
            c.execute('INSERT INTO media_library VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET path=excluded.path,data=excluded.data,updated=excluded.updated',
                      (item['id'],item['path'],json.dumps(item),time.time()))

    def add(self, path, source='', title='', job_id='', category='Unsorted'):
        file=Path(path).expanduser().resolve()
        if not file.is_file() or file.suffix.lower().lstrip('.') not in EXTENSIONS: return None
        with self.lock:
            with self.store.db() as c:
                old=c.execute('SELECT data FROM media_library WHERE path=?',(str(file),)).fetchone()
            if old: return json.loads(old[0])
            parsed=episode_metadata(file.name)
            item=dict(parsed,id=uuid.uuid4().hex,path=str(file),filename=file.name,title=title or file.stem,
                      source=source,website=source_domain(source),category=category,collection=parsed['series'],
                      bytes=file.stat().st_size,created=time.time(),job_id=job_id,suggestions=[])
            # Only unique exact catalog aliases can establish an identity automatically.
            # Similar names remain suggestions, never silent collection merges.
            if parsed['series']:
                from difflib import SequenceMatcher
                candidates=[]
                with self.store.db() as c:
                    tokens = parsed['identity'].split()
                    match = ' OR '.join('\"'+t.replace('\"','\"\"')+'\"' for t in tokens)
                    rows=c.execute('SELECT r.data FROM search_fts f JOIN records r ON r.id=f.id WHERE search_fts MATCH ? ORDER BY bm25(search_fts) LIMIT 100',(match,)).fetchall() if match else []
                for row in rows:
                    record=json.loads(row[0])
                    aliases=[record.get('title',''),*(record.get('alternatives') or [])]
                    exact=any(identity(a)==parsed['identity'] for a in aliases)
                    score=max((SequenceMatcher(None,identity(a),parsed['identity']).ratio() for a in aliases),default=0)
                    if exact or score>=.84: candidates.append((exact,record))
                exact={r['id']:r for match,r in candidates if match}
                if len(exact)==1:
                    record=next(iter(exact.values()))
                    item.update(series=record['title'],collection=record['title'],identity=identity(record['title']),catalog_id=record['id'])
                    if record.get('category') in ('anime','animation'): item['category']='Anime'
                else:
                    item['suggestions']=[{'title':r['title'],'id':r['id']} for _,r in candidates][:8]
            self.put(item)
            return item

    def completed(self, job):
        try:
            self.add(job['path'],job.get('source',''),job.get('title',''),job['id'],job.get('category','Unsorted'))
        except Exception:
            # A catalog problem must never turn a completed transfer into a failed download.
            job['library_notice']='The completed file could not be indexed. Import its folder in Media Library.'

    def listing(self, query='', offset=0):
        offset=max(0,int(offset))
        with self.store.db() as c:
            rows=c.execute('SELECT data FROM media_library WHERE data LIKE ? ORDER BY updated DESC LIMIT 101 OFFSET ?',('%'+str(query)+'%',offset)).fetchall()
            categories=c.execute("SELECT DISTINCT json_extract(data,'$.category') FROM media_library").fetchall()
        items=[json.loads(row[0]) for row in rows[:100]]
        for item in items: item['available']=Path(item['path']).is_file()
        return {'items':items,'has_more':len(rows)>100,'categories':sorted(set(CATEGORIES+[r[0] for r in categories if r[0]]))}

    def edit(self, ids, values):
        if not isinstance(ids,list) or not ids: raise ValueError('Select one or more videos.')
        allowed={'title','series','category','source','collection','season','episode'}
        changes={}
        for name,value in values.items():
            if name not in allowed: continue
            if name in ('season','episode'):
                if value in ('',None): value=None
                elif not str(value).isdigit(): raise ValueError('Season and episode must be whole numbers.')
                else: value=int(value)
            else: value=str(value).strip()[:500]
            changes[name]=value
        with self.lock:
            items=[self.get(key) for key in dict.fromkeys(ids)]
            with self.store.db() as c:
                for item in items:
                    item.update(changes)
                    item['identity']=identity(item['series'])
                    item['website']=source_domain(item['source'])
                    c.execute('UPDATE media_library SET data=?,updated=? WHERE id=?',
                              (json.dumps(item),time.time(),item['id']))
        return {'ok':True}

    def move(self, ids, destination, rename=''):
        folder=Path(destination).expanduser().resolve()
        if not folder.is_dir(): raise ValueError('Choose an existing destination folder.')
        if rename and len(ids)!=1: raise ValueError('Select one video when renaming a file.')
        moved=[]
        with self.lock:
            for key in ids:
                item=self.get(key); old=Path(item['path'])
                name=component(rename) if rename else old.name
                if rename and not Path(name).suffix: name+=old.suffix
                if (folder/name)==old: continue
                if not old.is_file(): raise ValueError('A selected file is missing. Reconnect its drive and retry.')
                if shutil.disk_usage(folder).free<old.stat().st_size+32*1024*1024: raise ValueError('Not enough free disk space to move this file safely.')
                n=0
                while True:
                    new=folder/(name if not n else Path(name).stem+f' ({n})'+Path(name).suffix)
                    try:
                        target=new.open('xb'); break
                    except FileExistsError: n+=1
                try:
                    with target,old.open('rb') as source:
                        shutil.copyfileobj(source,target,1024*1024);target.flush();os.fsync(target.fileno())
                    item.update(path=str(new),filename=new.name)
                    self.put(item)
                except BaseException:
                    new.unlink(missing_ok=True);raise
                try: old.unlink()
                except OSError: item['notice']='Moved copy is indexed; the original could not be removed.';self.put(item)
                # Keep the Download Center pointing at the organized file.
                with self.store.db() as c:
                    if item.get('job_id'):
                        row=c.execute('SELECT data FROM jobs WHERE id=?',(item['job_id'],)).fetchone()
                        if row:
                            job=json.loads(row[0]);job.update(path=str(new),destination=str(folder))
                            c.execute('UPDATE jobs SET data=? WHERE id=?',(json.dumps(job),job['id']))
                moved.append(item)
        return {'items':moved}

    def import_folder(self, value, progress=lambda message:None):
        folder=Path(value).expanduser().resolve()
        if not folder.is_dir(): raise ValueError('Choose an existing media folder.')
        count=0
        for root,dirs,files in os.walk(folder,followlinks=False):
            dirs[:]=[d for d in dirs if not (Path(root)/d).is_symlink()]
            for name in files:
                path=Path(root)/name
                if path.is_symlink(): continue
                if self.add(path): count+=1
                if count and count%100==0: progress(f'Indexed {count} videos')
        return {'indexed':count}
