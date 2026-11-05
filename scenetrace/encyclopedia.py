"""Bounded public full-text retrieval with explicit Wikidata relationships.

Wikipedia text is attributed CC BY-SA; Wikidata statements are CC0. Neither is
a viewing source. Search hits alone never establish a cast or character credit.
"""
import re
from urllib.parse import urlencode, quote
from . import network
from .deep import words
from .model import record

WIKI = 'https://en.wikipedia.org/w/api.php'
DATA = 'https://www.wikidata.org/w/api.php'


def values(entity, prop):
    return [s.get('mainsnak', {}).get('datavalue', {}).get('value')
            for s in entity.get('claims', {}).get(prop, []) if s.get('rank') != 'deprecated']


def ids(entity, prop):
    return [v['id'] for v in values(entity, prop) if isinstance(v, dict) and re.fullmatch(r'Q\d+', v.get('id', ''))]


def label(entity):
    return entity.get('labels', {}).get('en', {}).get('value') or entity.get('id', '')


def search(source, query, analysis, page=1, request=None):
    transport = request or (lambda params, base=WIKI: network.json_request(base+'?'+urlencode(params)))
    def request(params, base=WIKI):
        raw = transport(params, base)
        if not isinstance(raw, dict) or raw.get('error'):
            raise network.SourceError('The encyclopedia API could not complete this query. Retest the source or try again later.')
        return raw
    actor = analysis.get('actor')
    actor_id = None
    if actor:
        people = request(dict(action='wbsearchentities', search=actor, language='en', type='item', limit=5, format='json'), DATA)
        actor_id = next((p['id'] for p in people.get('search', []) if re.search(r'actor|actress', p.get('description', ''), re.I)), None)
    # Keep distinctive nouns; do not AND an entire remembered paragraph.
    vocabulary = [w for w in words(query) if w not in {'covers','haired','joins','powerful','dangerous','strange','fights','city','group','use','trying','after','restore'}]
    if 'haired' in query.casefold():
        vocabulary = ['hair' if w == 'hair' else w for w in vocabulary]
        if 'hair' not in vocabulary: vocabulary.append('hair')
    if actor:
        searches = ['"'+actor.replace('"', '')+'" film']
        if set(analysis.get('expanded', [])) & {'crime', 'criminal', 'police'}:
            searches.insert(0, '"'+actor.replace('"', '')+'" crime film')
    elif analysis.get('title_like') or analysis.get('character'):
        searches = [analysis.get('character') or query]
    else:
        suffix = 'anime' if analysis.get('category') == 'anime' else 'film'
        searches = [' '.join(vocabulary[:5]+[suffix])]
    pages = []
    for phrase in searches:
        raw = request(dict(action='query', generator='search', gsrsearch=phrase, gsrlimit=10,
                           gsroffset=(page-1)*10, prop='extracts|pageprops', exintro=1,
                           explaintext=1, exlimit=10, format='json'))
        pages.extend((raw.get('query', {}).get('pages') or {}).values())
    mapped = {p.get('pageprops', {}).get('wikibase_item'):p for p in pages if p.get('pageprops', {}).get('wikibase_item')}
    if not mapped: return [], False
    entities = request(dict(action='wbgetentities', ids='|'.join(mapped), props='claims|labels|descriptions|aliases', languages='en', format='json'), DATA).get('entities', {})
    related = {}
    for ident, entity in entities.items():
        description = entity.get('descriptions', {}).get('en', {}).get('value', '')
        if 'character' in description.lower():
            for target in ids(entity, 'P1080')+ids(entity, 'P144')+ids(entity, 'P179'):
                related.setdefault(target, []).append(ident)
    relations = request(dict(action='wbgetentities', ids='|'.join(related), props='labels|descriptions|aliases|claims', languages='en', format='json'), DATA).get('entities', {}) if related else {}
    # A fictional universe and a television title are different entities. Follow
    # an explicit "based on" statement when present; never rename it by guessing.
    works = {}
    for ident, entity in relations.items():
        description = entity.get('descriptions', {}).get('en', {}).get('value', '').lower()
        if 'universe' in description:
            for target in ids(entity, 'P144'):
                works.setdefault(target, []).extend(related[ident])
    if works:
        relations.update(request(dict(action='wbgetentities', ids='|'.join(works), props='labels|descriptions|aliases|claims', languages='en', format='json'), DATA).get('entities', {}))
        related.update(works)
    output = []

    def make(ident, entity, article, characters=None):
        title = label(entity)
        description = article.get('extract') or entity.get('descriptions', {}).get('en', {}).get('value', '')
        source_url = 'https://en.wikipedia.org/wiki/'+quote(article['title'].replace(' ', '_'))
        year = next((v.get('time', '')[1:5] for v in values(entity, 'P577') if isinstance(v, dict)), '')
        cast = [{'name':actor, 'url':'https://www.wikidata.org/wiki/'+actor_id}] if actor_id and actor_id in ids(entity, 'P161') else []
        return record(source['id'], ident, title, alternatives=[v['value'] for v in entity.get('aliases', {}).get('en', [])],
                      description=description, year=year, category=analysis.get('category') or ('series' if 'series' in entity.get('descriptions', {}).get('en', {}).get('value', '') else 'movie'),
                      url=source_url, source_name=source['name'], external_ids={'wikidata':ident},
                      cast=cast, characters=characters or [], license='Wikipedia text: CC BY-SA 4.0; Wikidata: CC0',
                      retrieval_evidence=['Wikipedia article: '+article['title'], *(['Cast credit in Wikidata: '+actor] if cast else [])])

    for ident, entity in entities.items():
        description = entity.get('descriptions', {}).get('en', {}).get('value', '').lower()
        if 'character' in description:
            continue
        # Exclude people, filmography lists and unrelated encyclopedic articles.
        if not re.search(r'film|movie|anime|manga|television series|animated series', description) or re.search(r'filmography|list of|actor|actress', description):
            continue
        if actor_id and actor_id not in ids(entity, 'P161'):
            continue
        output.append(make(ident, entity, mapped[ident]))
    for ident, origins in related.items():
        entity = relations.get(ident)
        if not entity: continue
        for origin in origins:
            article = mapped[origin]
            person = {'name':label(entities[origin]), 'description':article.get('extract', ''),
                      'url':'https://en.wikipedia.org/wiki/'+quote(article['title'].replace(' ', '_'))}
            row = make(ident, entity, article, [person])
            row['retrieval_evidence'].append('Wikidata links this character to '+label(entity))
            output.append(row)
    return output, len(pages) >= 10
