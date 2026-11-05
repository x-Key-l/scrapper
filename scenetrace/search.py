"""Federated retrieval and explainable local memory ranking. No invented matches."""
import concurrent.futures
import hashlib
import json
import math
import re
import threading
import time
from collections import Counter
from . import sources

STOP = set('i me my we our a an the and or is was were be been being this that those it its in on at to of for from by with without as then than but had have has watched saw remember years ago only about where who which he she they met main character show movie video series find looking like called some near into also very when can could would please dont know'.split())
EXPANSIONS = {'transported':['portal','isekai','reincarnation'], 'another':['other'], 'world':['fantasy'], 'spaceship':['space','science fiction'], 'robot':['android','mecha'], 'animated':['animation','anime'], 'school':['academy'], 'forest':['woods'], 'girl':['woman']}


def tokens(q):
    return [t for t in re.findall(r'[^\W_]+', q.casefold(), flags=re.UNICODE) if len(t) > 1 and t not in STOP]


def clues(q, hints=None):
    hints = hints or {}
    terms = list(dict.fromkeys(tokens(q)))
    expanded = list(dict.fromkeys(terms+[t for term in terms for x in EXPANSIONS.get(term, []) for t in tokens(x)]))
    decade = re.search(r'\b((?:18|19|20)\d)0s\b', q)
    start = int(hints['decade']) if str(hints.get('decade', '')).isdigit() else int(decade[1])*10 if decade else None
    genre = next((g for g in ('Fantasy','Sci-Fi','Action','Romance','Horror','Comedy','Adventure','Mystery') if g.casefold() in q.casefold()), None)
    if not genre and any(t in terms for t in ('transported', 'isekai', 'reincarnation', 'magic')):
        genre = 'Fantasy'
    category = hints.get('category') or ('anime' if any(w in q.casefold() for w in ('anime','animated','animation','isekai')) else '')
    # Phrases and individual distinctive terms diversify title-only provider recall.
    quoted = re.findall(r'["“]([^"”]+)["”]', q)
    queries = list(dict.fromkeys(quoted + [' '.join(terms[:6])] + terms[:3]))
    return {'terms':terms, 'expanded':expanded, 'queries':[x for x in queries if x], 'genre':genre, 'year_from':start, 'category':category, 'hints':hints}


def rank(q, records, memory=None):
    from .deep import rank as hybrid_rank, understand
    analysis = understand(q, (memory or {}).get('hints'))
    if memory:
        analysis.update({k: memory[k] for k in ('genre', 'category', 'year_from') if memory.get(k)})
    return hybrid_rank(q, records, analysis)


def deduplicate(records):
    """Only shared strong identifiers or the same source ID merge automatically."""
    output, identities = [], {}
    for r in records:
        keys = [('source', r['id'])]
        keys += [(k, str(v)) for k, v in r.get('external_ids', {}).items() if v and k in ('imdb','tmdb','tvdb','thetvdb','anilist')]
        index = next((identities[k] for k in keys if k in identities), None)
        origin = {'id':r['id'], 'source_id':r['source_id'], 'name':r.get('source_name'), 'url':r['url'], 'identifiers':r.get('external_ids', {})}
        if index is not None:
            old = output[index]
            # Conflicting strong IDs or distinct release years need human judgment.
            conflict = any(k in old['external_ids'] and str(old['external_ids'][k]) != str(v) for k,v in r.get('external_ids', {}).items())
            if conflict or (old.get('year') and r.get('year') and abs(old['year']-r['year']) > 1):
                index = None
        if index is None:
            index = len(output)
            output.append(dict(r, origins=[origin]))
        else:
            old = output[index]
            if not any(o['id'] == r['id'] for o in old['origins']):
                old['origins'].append(origin)
            old['external_ids'] = {**old['external_ids'], **r.get('external_ids', {})}
            old['media_urls'] = list(dict.fromkeys(old['media_urls'] + r.get('media_urls', [])))
            for field in ('alternatives', 'characters', 'cast', 'retrieval_evidence'):
                merged = {json.dumps(x, sort_keys=True): x for x in old.get(field, []) + r.get(field, [])}
                old[field] = list(merged.values())
            if len(r['description']) > len(old['description']):
                old['description'] = r['description']
        for k in keys:
            identities.setdefault(k, index)
    return output


class SearchEngine:
    def __init__(self, store):
        self.store = store
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=6, thread_name_prefix='sources')
        self.cancelled = {}
        self.lock = threading.Lock()

    def cancel(self, ident):
        with self.lock:
            self.cancelled = {k:v for k,v in self.cancelled.items() if time.monotonic()-v < 120}
            self.cancelled[ident] = time.monotonic()

    def is_cancelled(self, ident):
        with self.lock:
            return ident in self.cancelled

    def run(self, query, selected=None, page=1, mode='search', hints=None, refresh=False, request_id='', progress=None):
        if not isinstance(query, str) or len(query.strip()) < 2 or len(query) > 8000:
            raise ValueError('Enter at least two characters, up to a full description of 8,000 characters.')
        if not isinstance(page, int) or page < 1:
            raise ValueError('Invalid result page.')
        query = query.strip()
        from .deep import understand
        memory = understand(query, hints) if mode in ('deep', 'memory') else None
        active = [s for s in self.store.sources() if s.get('enabled') and (selected is None or s['id'] in selected)]
        if mode == 'media':
            active = [s for s in active if s['role'] in ('media','hybrid')]
        if not active:
            return {'results':[], 'sources':[], 'has_more':False, 'notice':'Enable or connect a suitable source in Database Hub.', 'clues':memory}
        sid = [s['id'] for s in active]
        terms = (memory or {}).get('expanded') or tokens(query)
        found = self.store.local_search(self.store.expanded_terms(terms), sid, (page-1)*100)
        statuses, futures, has_more = [], {}, False
        def snapshot(stage='Searching sources'):
            output = {'results':rank(query, deduplicate(found), memory), 'sources':list(statuses), 'has_more':has_more,
                      'clues':memory, 'stage':stage, 'pending':len(active)-len(statuses)}
            if progress:
                progress(output)
            return output
        snapshot('Searching connected sources')
        def load(s):
            if mode in ('deep', 'memory'):
                from .deep_sources import retrieve
                rows, more = retrieve(s, query, memory, self.store, page, lambda: self.is_cancelled(request_id))
                self.store.put_records(rows)
                return rows, more
            queries = (memory['queries'][:2] if memory else [query])
            if not queries:
                queries = [query]
            hits, more = [], False
            for q in queries:
                if request_id and self.is_cancelled(request_id):
                    break
                config = {k:v for k,v in s.items() if k not in ('health','last_sync','last_error','last_query','sync')}
                key = hashlib.sha256(json.dumps([config, q, page, memory], sort_keys=True).encode()).hexdigest()
                cached = None if refresh else self.store.cached(key)
                if cached is not None:
                    rows, next_page = cached['results'], cached['more']
                else:
                    rows, next_page = sources.search(s, q, page, memory)
                    self.store.put_records(rows)
                    self.store.cache(key, {'results':rows, 'more':next_page})
                hits.extend(rows)
                more |= next_page
                # AniList genre browse ignores title queries, so do not repeat it.
                if memory and s['kind'] == 'anilist' and memory.get('genre'):
                    break
            return hits, more
        for s in active:
            if s['kind'] == 'local':
                statuses.append({'id':s['id'], 'name':s['name'], 'status':'local index', 'count':sum(r['source_id']==s['id'] for r in found)})
            else:
                futures[self.pool.submit(load, s)] = s
        pending = set(futures)
        deadline = time.monotonic()+35
        while pending and time.monotonic() < deadline:
            if request_id and self.is_cancelled(request_id):
                for f in pending:
                    f.cancel()
                return {'results':[], 'sources':statuses, 'cancelled':True, 'has_more':False, 'clues':memory}
            done, pending = concurrent.futures.wait(pending, timeout=.15, return_when=concurrent.futures.FIRST_COMPLETED)
            for f in done:
                s = futures[f]
                try:
                    rows, more = f.result()
                    found.extend(rows)
                    has_more |= more
                    s.update(health='Search responded', last_sync=time.time(), last_query=query, last_error='')
                    statuses.append({'id':s['id'],'name':s['name'],'status':'ok','count':len(rows)})
                except Exception as exc:
                    message = str(exc) if isinstance(exc, ValueError) else 'Source could not be reached. Check internet access or try later.'
                    s.update(health='Unavailable', last_error=message)
                    statuses.append({'id':s['id'],'name':s['name'],'status':'unavailable','message':message})
                # Merge health only so a concurrent enable/edit is not overwritten.
                current = self.store.source(s['id'])
                if current:
                    current.update({k:s[k] for k in ('health','last_sync','last_error','last_query') if k in s})
                    self.store.put_source(current)
                snapshot()
        for f in pending:
            f.cancel()
            s = futures[f]
            statuses.append({'id':s['id'],'name':s['name'],'status':'timeout','message':'Provider exceeded the search deadline. Other sources are available.'})
        self.store.history(query, mode)
        result = snapshot('Search finished')['results']
        # Guided hints boost ranking, rather than excluding possibly incorrect memories.
        return {'results':result, 'sources':statuses, 'has_more':has_more or len(found)>=100, 'clues':memory,
                'notice':'Results come from connected catalogs. Memory ranking compares available metadata; scene-level identification requires a catalog containing those clues.' if memory else 'Metadata and media availability are checked separately.'}

    def close(self):
        self.pool.shutdown(wait=False, cancel_futures=True)
