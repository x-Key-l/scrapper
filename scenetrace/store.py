"""SQLite state, FTS5 and Windows user-bound credential encryption."""
import base64
import contextlib
import ctypes
import json
import os
import sqlite3
import time
from pathlib import Path


def protect(value, decrypt=False):
    if os.name != 'nt':
        return value
    class Blob(ctypes.Structure):
        _fields_ = [('size', ctypes.c_uint32), ('data', ctypes.POINTER(ctypes.c_char))]
    raw = base64.b64decode(value[6:]) if decrypt else value.encode()
    buf = ctypes.create_string_buffer(raw)
    inp, out = Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), Blob()
    fn = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not fn(ctypes.byref(inp), None, None, None, None, 1, ctypes.byref(out)):
        raise ValueError('Windows could not access the saved credential. Enter it again.')
    try:
        result = ctypes.string_at(out.data, out.size)
        return result.decode() if decrypt else 'dpapi:' + base64.b64encode(result).decode()
    finally:
        ctypes.windll.kernel32.LocalFree(out.data)


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        if os.name != 'nt':
            self.root.chmod(0o700)
        self.path = self.root / 'scenetrace.sqlite3'
        with self.db() as c:
            c.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,config TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,source TEXT NOT NULL,data TEXT NOT NULL,updated REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS record_source ON records(source);
            CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(id UNINDEXED,title,description,tokenize='porter unicode61');
            CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY,data TEXT NOT NULL,updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS saved(id TEXT PRIMARY KEY,data TEXT NOT NULL,updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY,query TEXT,mode TEXT,updated REAL);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,data TEXT NOT NULL);
            """)
        if os.name != 'nt':
            self.path.chmod(0o600)

    @contextlib.contextmanager
    def db(self):
        c = sqlite3.connect(self.path, timeout=20)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def setting(self, key, default=None):
        with self.db() as c:
            row = c.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.db() as c:
            c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (key, json.dumps(value)))

    def sources(self, public=False):
        with self.db() as c:
            rows = c.execute('SELECT config FROM sources ORDER BY id').fetchall()
        result = []
        for row in rows:
            s = json.loads(row[0])
            if public:
                s['has_token'] = bool(s.get('token'))
                s.pop('token', None)
            elif s.get('token', '').startswith('dpapi:'):
                s['token'] = protect(s['token'], True)
            result.append(s)
        return result

    def source(self, ident):
        return next((s for s in self.sources() if s['id'] == ident), None)

    def put_source(self, source):
        s = dict(source)
        if s.get('token') and not s['token'].startswith('dpapi:'):
            s['token'] = protect(s['token'])
        with self.db() as c:
            c.execute('INSERT OR REPLACE INTO sources VALUES(?,?)', (s['id'], json.dumps(s)))

    def delete_source(self, ident):
        with self.db() as c:
            c.execute('DELETE FROM search_fts WHERE id IN (SELECT id FROM records WHERE source=?)', (ident,))
            c.execute('DELETE FROM records WHERE source=?', (ident,))
            c.execute('DELETE FROM sources WHERE id=?', (ident,))
            c.execute('DELETE FROM cache')

    def put_records(self, records, replace_source=None):
        with self.db() as c:
            if replace_source:
                c.execute('DELETE FROM search_fts WHERE id IN (SELECT id FROM records WHERE source=?)', (replace_source,))
                c.execute('DELETE FROM records WHERE source=?', (replace_source,))
            for r in records:
                c.execute('INSERT OR REPLACE INTO records VALUES(?,?,?,?)', (r['id'], r['source_id'], json.dumps(r), time.time()))
                c.execute('DELETE FROM search_fts WHERE id=?', (r['id'],))
                c.execute('INSERT INTO search_fts VALUES(?,?,?)', (r['id'], r['title'] + ' ' + ' '.join(r.get('alternatives', [])), r['description'] + ' ' + ' '.join(r.get('genres', []))))

    def local_search(self, terms, sources, offset=0):
        if not sources or not terms:
            return []
        match = ' OR '.join('"' + x.replace('"', '""') + '"' for x in terms)
        marks = ','.join('?' for _ in sources)
        with self.db() as c:
            rows = c.execute(f"""SELECT r.data FROM search_fts f JOIN records r ON r.id=f.id
                WHERE search_fts MATCH ? AND r.source IN ({marks}) ORDER BY bm25(search_fts,0,4,1)
                LIMIT 100 OFFSET ?""", (match, *sources, offset)).fetchall()
        return [json.loads(x[0]) for x in rows]

    def cached(self, key, ttl=900):
        with self.db() as c:
            row = c.execute('SELECT data,updated FROM cache WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row and time.time() - row[1] < ttl else None

    def cache(self, key, data):
        with self.db() as c:
            c.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?)', (key, json.dumps(data), time.time()))
            c.execute('DELETE FROM cache WHERE updated<?', (time.time() - 7*86400,))

    def save(self, record, remove=False):
        with self.db() as c:
            if remove:
                c.execute('DELETE FROM saved WHERE id=?', (record['id'],))
            else:
                c.execute('INSERT OR REPLACE INTO saved VALUES(?,?,?)', (record['id'], json.dumps(record), time.time()))

    def saved(self):
        with self.db() as c:
            return [json.loads(r[0]) for r in c.execute('SELECT data FROM saved ORDER BY updated DESC')]

    def history(self, query=None, mode='search'):
        with self.db() as c:
            if query:
                c.execute('INSERT INTO history(query,mode,updated) VALUES(?,?,?)', (query, mode, time.time()))
            return [dict(r) for r in c.execute('SELECT * FROM history ORDER BY updated DESC LIMIT 30')]

    def job(self, data):
        with self.db() as c:
            c.execute('INSERT OR REPLACE INTO jobs VALUES(?,?)', (data['id'], json.dumps(data)))

    def jobs(self):
        with self.db() as c:
            return [json.loads(r[0]) for r in c.execute('SELECT data FROM jobs')]
