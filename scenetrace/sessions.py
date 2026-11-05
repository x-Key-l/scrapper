"""Progressive, cancellable searches with bounded work and expiring snapshots."""
import concurrent.futures
import copy
import hashlib
import json
import threading
import time
import uuid
from . import sources
from .deep import understand, similarity
from .search import deduplicate


class SearchSessions:
    def __init__(self, app):
        self.app = app
        self.lock = threading.RLock()
        self.items = {}
        self.tasks = set()
        self.workers = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix='search-session')

    def start(self, body):
        query = body.get('query')
        if not isinstance(query, str) or not 2 <= len(query.strip()) <= 8000:
            raise ValueError('Enter a title or description between 2 and 8,000 characters.')
        hints = body.get('hints') or {}
        if not isinstance(hints, dict) or not all(isinstance(v, (str, int)) for v in hints.values()):
            raise ValueError('Search clues must be text.')
        selected = body.get('sources')
        if selected is not None and (not isinstance(selected, list) or not all(isinstance(x, str) for x in selected)):
            raise ValueError('Choose sources from the list.')
        with self.lock:
            now = time.monotonic()
            self.items = {k:v for k,v in self.items.items() if now-v['touched'] < 600 or v['status'] == 'running'}
            self.tasks = {task for task in self.tasks if not task.done()}
            if len(self.tasks) >= 2:
                raise ValueError('Two searches are already running. Cancel one or wait for its results.')
            ident = uuid.uuid4().hex
            self.items[ident] = dict(id=ident, status='running', results=[], sources=[], stage='Starting search', touched=now)
            self.tasks.add(self.workers.submit(self.run, ident, dict(body, query=query.strip(), hints=hints)))
        return {'id': ident}

    def update(self, ident, value):
        with self.lock:
            item = self.items.get(ident)
            if item and item['status'] != 'cancelled':
                item.update(copy.deepcopy(value), touched=time.monotonic())

    def poll(self, ident):
        with self.lock:
            item = self.items.get(ident)
            if not item:
                raise ValueError('This search expired. Run it again to refresh results.')
            item['touched'] = time.monotonic()
            return {k:copy.deepcopy(v) for k,v in item.items() if k != 'touched'}

    def cancel(self, ident):
        self.app.search.cancel(ident)
        with self.lock:
            if ident in self.items:
                self.items[ident].update(status='cancelled', stage='Search cancelled')
        return {'ok': True}

    def run(self, ident, body):
        query, selected = body['query'], body.get('sources')
        deep = body.get('mode', 'deep') == 'deep'
        analysis = understand(query, body['hints'])
        all_sources = [s for s in self.app.store.sources() if s.get('enabled')]
        current = body.get('current_source')
        if current:
            selected = [s['id'] for s in all_sources if s['id'] == current or s['role'] == 'metadata']
        if deep and analysis['category']:
            selected = [s['id'] for s in all_sources if (selected is None or s['id'] in selected)
                        and (s['role'] != 'metadata' or analysis['category'] in s.get('categories', []))]
        try:
            result = self.app.search.run(query, selected, body.get('page', 1), 'deep' if deep else 'search', body['hints'],
                                         request_id=ident, progress=lambda value:self.update(ident, value))
            if self.app.search.is_cancelled(ident):
                return
            excluded = set(body.get('excluded') or [])
            result['results'] = [r for r in result['results'] if r['id'] not in excluded]
            if deep:
                self.locate(ident, result, all_sources, selected, current, query)
            self.update(ident, dict(result, status='completed', stage='Search finished'))
        except Exception as error:
            self.update(ident, dict(status='failed', message=str(error) if isinstance(error, ValueError) else
                                   'The search could not finish. Your earlier results are still available.'))

    def locate(self, ident, result, active, selected, current, query):
        candidates = result['results'][:3]
        sites = [s for s in active if s['role'] != 'metadata' and s['kind'] != 'local'
                 and (s['id'] == current if current else selected is None or s['id'] in selected)
                 and not (s['kind'] == 'website' and s.get('web_config', {}).get('strategy') == 'browse')]
        titles = []
        for record in candidates:
            for title in [record['title'], *record.get('alternatives', [])]:
                if title and title.casefold() != query.casefold() and title not in titles:
                    titles.append(title)
        if not sites or not titles:
            return
        self.update(ident, dict(result, stage='Locating video pages for likely titles'))

        def lookup(site):
            rows = []
            for title in titles[:2]:
                if self.app.search.is_cancelled(ident):
                    break
                key = 'resolve:' + hashlib.sha256(json.dumps([site, title], sort_keys=True).encode()).hexdigest()
                found = self.app.store.cached(key)
                if found is None:
                    found, _ = sources.search(site, title)
                    self.app.store.cache(key, found)
                    self.app.store.put_records(found)
                rows.extend(found)
            return deduplicate(rows)

        pending = {self.app.search.pool.submit(lookup, site): site for site in sites}
        deadline = time.monotonic() + 30
        while pending and time.monotonic() < deadline and not self.app.search.is_cancelled(ident):
            done, _ = concurrent.futures.wait(pending, timeout=.15, return_when=concurrent.futures.FIRST_COMPLETED)
            for task in done:
                site = pending.pop(task)
                try:
                    pages = task.result()
                    for record in candidates:
                        names = [record['title']] + record.get('alternatives', [])
                        found = [p for p in pages if p.get('media_urls') and max(similarity(n, p['title']) for n in names) >= .76]
                        record.setdefault('viewing_matches', []).extend(found)
                    result.setdefault('resolution_sources', []).append({'name': site['name'], 'count': len(pages), 'status': 'ok'})
                except Exception as error:
                    result.setdefault('resolution_sources', []).append({'name': site['name'], 'status': 'unavailable',
                        'message': str(error) if isinstance(error, ValueError) else 'Video website could not be reached.'})
                self.update(ident, dict(result, stage='Locating video pages for likely titles'))
        for task, site in pending.items():
            task.cancel()
            result.setdefault('resolution_sources', []).append({'name':site['name'], 'status':'timeout', 'message':'Website search timed out.'})

    def close(self):
        with self.lock:
            for ident in self.items:
                self.app.search.cancel(ident)
        self.workers.shutdown(wait=False, cancel_futures=True)
