import sqlite3
import time

import pytest

from scenetrace.store import Store


def test_history_deletion_upgrade_and_restart_preserve_other_data(tmp_path):
    root = tmp_path / 'profile'
    root.mkdir()
    with sqlite3.connect(root / 'scenetrace.sqlite3') as db:
        db.execute('CREATE TABLE history(id INTEGER PRIMARY KEY,query TEXT,mode TEXT,updated REAL)')
        db.execute('INSERT INTO history VALUES(1,?,?,?)', ('Naruto', 'search', time.time()))
    store = Store(root)
    store.history('Caminandes')
    store.history('Pocket Monsters')
    store.put_source({'id': 'keep', 'name': 'Source'})
    store.save({'id': 'keep', 'title': 'Saved video'})
    store.job({'id': 'keep', 'status': 'completed'})
    original = store.history()
    removed = store.delete_history([original[0]['id']])
    store = Store(root)
    assert original[0]['id'] not in {row['id'] for row in store.history()}
    store.history('Later')
    assert store.history()[0]['id'] > original[0]['id']
    store.restore_history(removed['undo_token'])
    assert len(store.history()) == 4
    store.delete_history([row['id'] for row in original[:2]])
    assert [row['query'] for row in Store(root).history()] == ['Later', 'Naruto']
    store.delete_history(clear=True)
    assert Store(root).history() == []
    assert store.sources()[0]['id'] == store.saved()[0]['id'] == store.jobs()[0]['id'] == 'keep'


def test_history_retention_recording_search_and_expired_undo(tmp_path):
    store = Store(tmp_path)
    store.history('Naruto')
    store.set_setting('record_history', False)
    store.history('Private search')
    assert len(store.history()) == 1
    store.set_setting('record_history', True)
    store.history('Caminandes')
    assert store.history_page('nar')['entries'][0]['query'] == 'Naruto'
    with store.db() as db:
        db.execute('UPDATE history SET updated=? WHERE query=?', (time.time() - 40 * 86400, 'Naruto'))
    store.set_setting('history_retention_days', 30)
    assert [row['query'] for row in Store(tmp_path).history()] == ['Caminandes']
    deleted = store.delete_history(clear=True)
    with store.db() as db:
        db.execute('UPDATE history_trash SET deleted=?', (time.time() - 90,))
    with pytest.raises(ValueError, match='undo'):
        store.restore_history(deleted['undo_token'])
    with pytest.raises(ValueError):
        store.delete_history(['1 OR 1=1'])


def test_bookmarks_and_navigation_are_separate_from_search(tmp_path):
    store = Store(tmp_path)
    store.bookmarks('https://example.org/video', 'Video')
    store.navigation('https://example.org/video', 'Video')
    store.history('Example')
    store.delete_history(clear=True)
    assert store.bookmarks() and store.navigation()
    store.set_setting('record_browsing', False)
    store.navigation('https://example.org/private', 'Private')
    assert len(store.navigation()) == 1
