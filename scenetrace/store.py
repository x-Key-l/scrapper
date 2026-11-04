"""SQLite state, FTS5 and Windows user-bound credential encryption."""
import base64
import contextlib
import ctypes
import json
import os
import sqlite3
import time
import uuid
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
            CREATE VIRTUAL TABLE IF NOT EXISTS search_vocabulary USING fts5vocab(search_fts, 'row');
            CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY,data TEXT NOT NULL,updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS saved(id TEXT PRIMARY KEY,data TEXT NOT NULL,updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY,query TEXT,mode TEXT,updated REAL);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS history_trash(token TEXT,id INTEGER,query TEXT,mode TEXT,updated REAL,deleted REAL,PRIMARY KEY(token,id));
            CREATE TABLE IF NOT EXISTS navigation(id INTEGER PRIMARY KEY AUTOINCREMENT,url TEXT NOT NULL,title TEXT,updated REAL);
            CREATE TABLE IF NOT EXISTS bookmarks(url TEXT PRIMARY KEY,title TEXT,updated REAL);
            """)
            definition = c.execute("SELECT sql FROM sqlite_master WHERE name='history'").fetchone()[0]
            if 'AUTOINCREMENT' not in definition.upper():
                c.executescript("""
                    BEGIN IMMEDIATE;
                    ALTER TABLE history RENAME TO history_legacy;
                    CREATE TABLE history(id INTEGER PRIMARY KEY AUTOINCREMENT,query TEXT,mode TEXT,updated REAL);
                    INSERT INTO history SELECT * FROM history_legacy;
                    DROP TABLE history_legacy;
                    COMMIT;
                """)
            c.execute('CREATE INDEX IF NOT EXISTS history_updated ON history(updated DESC)')
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
                people = ' '.join(x.get('name', '') + ' ' + x.get('description', '') if isinstance(x, dict) else str(x)
                                  for x in r.get('characters', []) + r.get('cast', []))
                c.execute('INSERT INTO search_fts VALUES(?,?,?)', (r['id'], r['title'] + ' ' + ' '.join(r.get('alternatives', [])), r['description'] + ' ' + ' '.join(r.get('genres', [])) + ' ' + people))

    def expanded_terms(self, terms):
        """Fuzzy recall from indexed vocabulary, with bounded prefix lookups."""
        from difflib import get_close_matches
        output = list(dict.fromkeys(terms))
        with self.db() as c:
            for word in terms[:8]:
                if len(word) < 4:
                    continue
                rows = c.execute('SELECT term FROM search_vocabulary WHERE term>=? AND term<? LIMIT 400',
                                 (word[:1], chr(ord(word[0])+1))).fetchall()
                output.extend(get_close_matches(word, [r[0] for r in rows if abs(len(r[0])-len(word)) <= 2], n=3, cutoff=.72))
        return list(dict.fromkeys(output))

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
        recording = self.setting('record_history', True)
        days = self.setting('history_retention_days', 0)
        with self.db() as c:
            if days:
                c.execute('DELETE FROM history WHERE updated<?', (time.time() - days * 86400,))
            c.execute('DELETE FROM history_trash WHERE deleted<?', (time.time() - 60,))
            if query and recording:
                c.execute('INSERT INTO history(query,mode,updated) VALUES(?,?,?)', (query, mode, time.time()))
            return [dict(r) for r in c.execute('SELECT * FROM history ORDER BY updated DESC LIMIT 30')]

    def history_page(self, query='', offset=0):
        self.history()
        query = str(query).strip()
        if not isinstance(offset, int) or offset < 0:
            raise ValueError('Choose a valid history page.')
        with self.db() as c:
            rows = c.execute("""SELECT * FROM history WHERE instr(lower(query), lower(?))>0
                                ORDER BY updated DESC, id DESC LIMIT 101 OFFSET ?""", (query, offset)).fetchall()
        return {'entries': [dict(row) for row in rows[:100]], 'has_more': len(rows) > 100}

    def delete_history(self, ids=None, clear=False):
        if not clear and (not isinstance(ids, list) or not ids or
                          any(type(ident) is not int or ident < 1 for ident in ids)):
            raise ValueError('Select the searches to delete.')
        token = uuid.uuid4().hex
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            if clear:
                rows = c.execute('SELECT * FROM history').fetchall()
            else:
                rows = []
                for offset in range(0, len(ids), 500):
                    batch = ids[offset:offset + 500]
                    rows.extend(c.execute('SELECT * FROM history WHERE id IN (' +
                                          ','.join('?' for _ in batch) + ')', batch).fetchall())
            c.executemany('INSERT OR IGNORE INTO history_trash VALUES(?,?,?,?,?,?)',
                          [(token, row['id'], row['query'], row['mode'], row['updated'], time.time()) for row in rows])
            c.executemany('DELETE FROM history WHERE id=?', [(row['id'],) for row in rows])
        return {'deleted': len(rows), 'undo_token': token, 'undo_seconds': 60}

    def restore_history(self, token):
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            rows = c.execute('SELECT * FROM history_trash WHERE token=? AND deleted>=?',
                             (str(token), time.time() - 60)).fetchall()
            if not rows:
                raise ValueError('The undo period has ended.')
            c.executemany('INSERT OR IGNORE INTO history(id,query,mode,updated) VALUES(?,?,?,?)',
                          [(row['id'], row['query'], row['mode'], row['updated']) for row in rows])
            c.execute('DELETE FROM history_trash WHERE token=?', (str(token),))
        return {'restored': len(rows)}

    def navigation(self, value=None, title=''):
        from .model import url, text
        with self.db() as c:
            if value and self.setting('record_browsing', True):
                value = url(value)
                if not value:
                    raise ValueError('Use a public website address.')
                c.execute('INSERT INTO navigation(url,title,updated) VALUES(?,?,?)',
                          (value, text(title)[:300], time.time()))
            return [dict(row) for row in c.execute('SELECT * FROM navigation ORDER BY updated DESC LIMIT 100')]

    def bookmarks(self, value=None, title='', remove=False):
        from .model import url, text
        with self.db() as c:
            if value:
                value = url(value)
                if not value:
                    raise ValueError('Use a valid website address.')
                if remove:
                    c.execute('DELETE FROM bookmarks WHERE url=?', (value,))
                else:
                    c.execute('INSERT OR REPLACE INTO bookmarks VALUES(?,?,?)', (value, text(title)[:300], time.time()))
            return [dict(row) for row in c.execute('SELECT * FROM bookmarks ORDER BY updated DESC')]

    def job(self, data):
        with self.db() as c:
            c.execute('INSERT OR REPLACE INTO jobs VALUES(?,?)', (data['id'], json.dumps(data)))

    def jobs(self):
        with self.db() as c:
            return [json.loads(r[0]) for r in c.execute('SELECT data FROM jobs')]
