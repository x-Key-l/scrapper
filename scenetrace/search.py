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
    wanted = set(tokens(q))
    expanded = set((memory or {}).get('expanded') or wanted)
    docs = [set(tokens(r['title']+' '+' '.join(r.get('alternatives', []))+' '+r['description']+' '+' '.join(r.get('genres', [])))) for r in records]
    freq = Counter(t for d in docs for t in d)
    ranked = []
    for r, doc in zip(records, docs):
        title = set(tokens(r['title']+' '+' '.join(r.get('alternatives', []))))
        matches = wanted & doc
        evidence = []
        score = sum((1+math.log(1+len(docs)/(1+freq[t])))*(4 if t in title else 1) for t in matches)
        score += .35*len((expanded-wanted) & doc)
        if q.casefold().strip() in [r['title'].casefold(), *(x.casefold() for x in r.get('alternatives', []))]:
            score += 15
            evidence.append('Exact title or alternative title')
        if matches & title:
            evidence.append('Title: '+', '.join(sorted(matches & title)))
        if matches-title:
            evidence.append('Metadata: '+', '.join(sorted(matches-title)))
        if memory:
            if memory.get('genre') in r.get('genres', []):
                score += 2
                evidence.append('Genre: '+memory['genre'])
            if memory.get('category') and memory['category'] == r['category']:
                score += 1
            if memory.get('year_from') and r.get('year'):
                delta = abs(r['year']-(memory['year_from']+4))
                score += 2 if delta < 6 else -.5
                evidence.append('Release '+str(r['year'])+(' fits the remembered decade' if delta < 6 else ' differs from the remembered decade'))
        ranked.append(dict(r, relevance=round(score, 4), evidence=evidence or ['Returned by the provider; no direct clue overlap in available metadata']))
    return sorted(ranked, key=lambda x:(-x['relevance'], x['title'].casefold()))


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
            if len(r['description']) > len(old['description']):
                old['description'] = r['description']
        for k in keys:
            identities.setdefault(k, index)
    return output


class SearchEngine:
    def __init__(self, store):
        self.store = store
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=6, thread_name_prefix='sources')
        self.cancelled = set()
        self.lock = threading.Lock()

    def cancel(self, ident):
        with self.lock:
            self.cancelled.add(ident)

    def is_cancelled(self, ident):
        with self.lock:
            return ident in self.cancelled

    def run(self, query, selected=None, page=1, mode='search', hints=None, refresh=False, request_id=''):
        if not isinstance(query, str) or len(query.strip()) < 2 or len(query) > 8000:
            raise ValueError('Enter at least two characters, up to a full description of 8,000 characters.')
        if not isinstance(page, int) or page < 1:
            raise ValueError('Invalid result page.')
        query = query.strip()
        memory = clues(query, hints) if mode == 'memory' else None
        active = [s for s in self.store.sources() if s.get('enabled') and (selected is None or s['id'] in selected)]
        if mode == 'media':
            active = [s for s in active if s['role'] in ('media','hybrid')]
        if not active:
            return {'results':[], 'sources':[], 'has_more':False, 'notice':'Enable or connect a suitable source in Database Hub.', 'clues':memory}
        sid = [s['id'] for s in active]
        terms = (memory or {}).get('expanded') or tokens(query)
        found = self.store.local_search(terms, sid, (page-1)*100)
        statuses, futures, has_more = [], {}, False
        def load(s):
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
                    s.update(health='Verified', last_sync=time.time(), last_query=query, last_error='')
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
        for f in pending:
            f.cancel()
            s = futures[f]
            statuses.append({'id':s['id'],'name':s['name'],'status':'timeout','message':'Provider exceeded the search deadline. Other sources are available.'})
        self.store.history(query, mode)
        result = rank(query, deduplicate(found), memory)
        # Guided hints boost ranking, rather than excluding possibly incorrect memories.
        return {'results':result, 'sources':statuses, 'has_more':has_more or len(found)>=100, 'clues':memory,
                'notice':'Results come from connected catalogs. Memory ranking compares available metadata; scene-level identification requires a catalog containing those clues.' if memory else 'Metadata and media availability are checked separately.'}

    def close(self):
        self.pool.shutdown(wait=False, cancel_futures=True)
