"""Evidence-based query understanding and hybrid ranking. No model downloads."""
import math
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher

STOP = set('i me my we our a an the and or is was were be been being this that those it its in on at to of for from by with without as then than but had have has watched saw remember years ago only about where who which he she they met main character show movie video series find looking like called some near into also very when can could would please dont know anime film old maybe think probably something'.split())
STOP.update('him her his hers their them one people someone person discovers discover encounters encounter'.split())
GROUPS = [
    ('boy', 'young', 'child', 'kid'), ('girl', 'young', 'child'), ('creature', 'beast', 'monster', 'demon'),
    ('fighter', 'ninja', 'warrior', 'martial'), ('transported', 'portal', 'isekai', 'reincarnated'),
    ('world', 'realm'), ('underground', 'cave', 'cavern', 'descent'), ('forest', 'woods'),
    ('teacher', 'mentor', 'sensei', 'instructor', 'leader'), ('eye', 'eyepatch', 'mask', 'covered', 'headband'),
    ('criminal', 'crime', 'police', 'gang'), ('fight', 'battle', 'combat'), ('spirit', 'ghost', 'supernatural'),
    ('notebook', 'book', 'diary'), ('death', 'kill', 'murder'), ('space', 'spaceship', 'alien'),
    ('robot', 'android', 'mecha'), ('animated', 'animation', 'anime'), ('school', 'academy', 'student'),
    ('inside', 'sealed', 'possessed', 'host'), ('white', 'silver', 'gray'), ('powerful', 'power', 'ability'),
]


def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value)).casefold() if not unicodedata.combining(c))


def words(value):
    return [w for w in re.findall(r'[^\W_]+', normalized(value)) if len(w) > 1 and w not in STOP]


def stem(word):
    # Modest normalization; title spellings remain intact for similarity.
    if len(word) > 5 and word.endswith('ies'):
        return word[:-3] + 'y'
    for suffix in ('ing', 'ers', 'ed', 's'):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[:-len(suffix)]
    return word


def terms(value):
    return [stem(w) for w in words(value)]


def understand(query, hints=None):
    hints = hints or {}
    original = list(dict.fromkeys(terms(query)))
    expansions = list(original)
    for group in GROUPS:
        group = [stem(w) for w in group]
        if set(group) & set(original):
            expansions.extend(group)
    decade = re.search(r'\b((?:18|19|20)\d)0s\b', query)
    date = re.search(r'\b(?:18|19|20)\d{2}\b', query)
    year = int(hints['decade']) if str(hints.get('decade', '')).isdigit() else int(decade[1])*10 if decade else int(date[0]) if date else None
    genre = hints.get('genre') or next((g for g in ('Fantasy', 'Sci-Fi', 'Action', 'Romance', 'Horror', 'Comedy', 'Adventure', 'Mystery', 'Drama') if g.casefold() in query.casefold()), None)
    if not genre:
        rules = {'Fantasy': ('portal', 'isekai', 'magic', 'reincarnated'), 'Action': ('ninja', 'fighter', 'fight', 'warrior'),
                 'Horror': ('dangerous creatures', 'underground', 'monsters', 'murder'), 'Mystery': ('notebook', 'detective')}
        genre = next((g for g, clues in rules.items() if any(c in query.casefold() for c in clues)), None)
    category = hints.get('category') or ('anime' if re.search(r'\b(anime|animated|animation|isekai)\b', query, re.I) else '')
    # Names are explicit hints or capitalized phrases in the user's text; never invented.
    names = re.findall(r'\b[A-ZÀ-Ý][a-zà-ÿ]+(?:[ -][A-ZÀ-Ý][a-zà-ÿ]+){1,3}\b', query)
    names = [n for n in names if not all(w.casefold() in STOP for w in n.split())]
    actor = str(hints.get('actor') or '')
    character = str(hints.get('character') or '')
    if not actor and not category and names:
        actor = names[0]
    if not actor and not category:
        explicit_actor = re.search(r'\b(?:starring|actor|with)\s+([a-z]+(?:\s+[a-z]+){1,2})(?=\s+(?:where|who|in|as)|[,.!?]|$)', query, re.I)
        if explicit_actor:
            actor = explicit_actor[1]
    if not character and category == 'anime' and names:
        character = names[0]
    quoted = re.findall(r'["“]([^"”]+)["”]', query)
    title_like = len(words(query)) <= 4 and not any(x in query.casefold() for x in (' where ', ' who ', ' with ', ' about '))
    queries = [query.strip()] if title_like else quoted + names + [' '.join(words(query)[:5])] + words(query)[:2]
    return dict(terms=original, expanded=list(dict.fromkeys(expansions)), queries=list(dict.fromkeys(x for x in queries if x))[:3],
                genre=genre, year_from=year, category=category, actor=actor, character=character,
                character_description=bool(re.search(r'\b(character|teacher|hair|haired|eye|sensei)\b', query, re.I)),
                title_like=title_like, hints=hints)


def similarity(a, b):
    a, b = ' '.join(words(a)), ' '.join(words(b))
    if not a or not b:
        return 0
    if a == b:
        return 1.0
    ratio = SequenceMatcher(None, a, b).ratio()
    # Token boundary containment, not arbitrary substrings such as "It" in "Titan".
    if ' ' + a + ' ' in ' ' + b + ' ':
        ratio = max(ratio, .84 + .1*len(a)/len(b))
    return ratio


def rank(query, records, analysis=None):
    analysis = analysis or understand(query)
    wanted = set(analysis['terms'])
    expanded = set(analysis.get('expanded') or wanted) - wanted
    documents = []
    for record in records:
        people = ' '.join(str(x.get('name', '')) + ' ' + str(x.get('description', '')) if isinstance(x, dict) else str(x)
                          for x in record.get('characters', []) + record.get('cast', []))
        documents.append(Counter(terms(record['title'] + ' ' + ' '.join(record.get('alternatives', [])) + ' ' +
                                       record.get('description', '') + ' ' + ' '.join(record.get('genres', [])) + ' ' + people)))
    df = Counter(t for document in documents for t in document)
    avg = sum(sum(d.values()) for d in documents) / max(1, len(documents)) or 1
    ranked = []
    for record, doc in zip(records, documents):
        matches = wanted & doc.keys()
        score, evidence = 0., []
        dl = sum(doc.values())
        for term in matches:
            idf = math.log(1 + (len(records)-df[term]+.5)/(df[term]+.5))
            score += idf * doc[term] * 2.2 / (doc[term]+1.2*(.25+.75*dl/avg))
        expanded_matches = expanded & doc.keys()
        score += min(3., .22*len(expanded_matches))
        titles = [record['title']] + record.get('alternatives', [])
        similarities = [(similarity(query, t), t) for t in titles]
        sim, closest = max(similarities, default=(0., ''))
        title_match = False
        if analysis.get('title_like') and sim >= .66:
            score += 18*sim**3
            title_match = True
            evidence.append(('Exact title: ' if sim == 1 else 'Similar title: ') + closest)
        if matches:
            evidence.append('Available metadata: ' + ', '.join(sorted(matches)[:10]))
        title_clues = wanted & set(terms(' '.join(titles)))
        if title_clues:
            evidence.append('Title clues: ' + ', '.join(sorted(title_clues)))
        if expanded_matches:
            evidence.append('Related terms: ' + ', '.join(sorted(expanded_matches)[:6]))
        for field, label, hint in (('characters', 'Character', analysis.get('character')), ('cast', 'Actor', analysis.get('actor'))):
            for person in record.get(field, []):
                name = person.get('name', '') if isinstance(person, dict) else person
                description = person.get('description', '') if isinstance(person, dict) else ''
                overlap = wanted & set(terms(name + ' ' + description))
                person_terms = set(terms(name + ' ' + description))
                if field == 'characters' and analysis.get('character_description'):
                    groups = [set(stem(w) for w in group) for group in GROUPS]
                    group_hits = [g for g in groups if g & wanted and g & person_terms]
                    score += min(8., 1.5*len(group_hits))
                    if any(g & {'teacher', 'mentor', 'sensei'} and g & wanted and g & person_terms for g in groups):
                        score += 3
                if hint and similarity(hint, name) >= .72:
                    score += 7
                    evidence.append(label + ': ' + name)
                elif len(overlap) >= 2:
                    score += min(5., len(overlap))
                    evidence.append(label + ' ' + name + ': ' + ', '.join(sorted(overlap)[:5]))
        evidence.extend(record.get('retrieval_evidence', []))
        if analysis.get('genre') in record.get('genres', []):
            score += 1.5
            evidence.append('Genre: ' + analysis['genre'])
        if analysis.get('category') == record.get('category'):
            score += .5
        if analysis.get('year_from') and record.get('year'):
            fits = abs(record['year'] - analysis['year_from'] - 4) < 7
            score += 1. if fits else -.35
            evidence.append('Released ' + str(record['year']) + ('; fits the approximate period' if fits else '; differs from the remembered period'))
        supported = title_match or len(matches) >= 3
        ranked.append(dict(record, relevance=round(score, 4),
                           relevance_label='Strong title match' if title_match and sim >= .85 else 'Several matching clues' if supported else 'Partial evidence',
                           evidence=list(dict.fromkeys(evidence)) or ['Provider candidate; available metadata has no direct clue overlap']))
    return sorted(ranked, key=lambda r: (-r['relevance'], r['title'].casefold()))
