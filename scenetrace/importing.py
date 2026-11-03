"""CSV/TSV, JSON, SQLite and RSS imports with preview and field mapping."""
import csv
import io
import itertools
import json
import sqlite3
import time
from pathlib import Path
from .model import flatten
from .sources import feed_rows, items_from, infer_mapping, mapped


def quote_ident(value):
    return '"' + str(value).replace('"', '""') + '"'


def rows(path, table='', items_path=''):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in ('.csv', '.tsv'):
        with path.open(encoding='utf-8-sig', newline='') as f:
            yield from csv.DictReader(f, delimiter='\t' if suffix == '.tsv' else ',')
    elif suffix in ('.sqlite', '.sqlite3', '.db'):
        with path.open('rb') as f:
            if f.read(16) != b'SQLite format 3\0':
                raise ValueError('This is not a SQLite database file.')
        conn = sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1', uri=True)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('PRAGMA trusted_schema=OFF')
            names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND sql NOT LIKE '%VIRTUAL TABLE%'")]
            if not names:
                raise ValueError('No ordinary data tables found in this SQLite file.')
            selected = table or names[0]
            if selected not in names:
                raise ValueError('Choose one of the available ordinary tables.')
            deadline = time.monotonic() + 60
            conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
            for r in conn.execute('SELECT * FROM '+quote_ident(selected)):
                yield dict(r)
        finally:
            conn.close()
    elif suffix in ('.jsonl', '.ndjson'):
        with path.open(encoding='utf-8-sig') as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    if not isinstance(item, dict):
                        raise ValueError('Each JSONL line must be an object.')
                    yield item
    elif suffix == '.json':
        # Large collections should use streaming CSV/JSONL or SQLite exports.
        if path.stat().st_size > 128*1024*1024:
            raise ValueError('For this large JSON export, use CSV, JSONL or SQLite to import without exhausting RAM.')
        with path.open(encoding='utf-8-sig') as f:
            yield from items_from(json.load(f), items_path)
    elif suffix in ('.rss', '.atom', '.xml'):
        yield from feed_rows(path.read_bytes())
    else:
        raise ValueError('Use CSV, TSV, JSON, JSONL, SQLite, RSS or Atom.')


def preview(path, table='', items_path=''):
    samples = list(itertools.islice(rows(path, table, items_path), 5))
    result = {'samples': samples, 'fields': list(dict.fromkeys(k for row in samples for k in flatten(row))),
              'mapping': infer_mapping(samples[0]) if samples else {}, 'tables': []}
    if Path(path).suffix.lower() in ('.sqlite', '.sqlite3', '.db'):
        with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro&immutable=1', uri=True) as c:
            result['tables'] = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND sql NOT LIKE '%VIRTUAL TABLE%'")]
    return result


def import_source(store, source, progress=None, cancel=None):
    """All-or-nothing transaction: a malformed later row never destroys the old index."""
    count = 0
    with store.db() as conn:
        conn.execute('DELETE FROM search_fts WHERE id IN (SELECT id FROM records WHERE source=?)', (source['id'],))
        conn.execute('DELETE FROM records WHERE source=?', (source['id'],))
        for item in rows(source['local_path'], source.get('table', ''), source.get('items_path', '')):
            if cancel and cancel.is_set():
                raise ValueError('Import cancelled; the previous index was preserved.')
            rec = mapped(source, item)
            if not rec:
                raise ValueError('A row has no mapped title. Check the Title field mapping.')
            conn.execute('INSERT OR REPLACE INTO records VALUES(?,?,?,?)', (rec['id'], source['id'], json.dumps(rec), time.time()))
            conn.execute('DELETE FROM search_fts WHERE id=?', (rec['id'],))
            conn.execute('INSERT INTO search_fts VALUES(?,?,?)', (rec['id'], rec['title']+' '+' '.join(rec['alternatives']), rec['description']+' '+' '.join(rec['genres'])))
            count += 1
            if progress and count % 500 == 0:
                progress(count)
        if not count:
            raise ValueError('No records found. Check the table or records path.')
    return count
