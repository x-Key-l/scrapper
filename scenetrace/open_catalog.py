"""Small, attributed publisher and open-film catalogs. Episodes are exact pages."""
import re
import unicodedata

from .model import record

COMMONS = 'https://commons.wikimedia.org/wiki/File:'

CATALOGS = {
    'pokemon-tv': {
        'title': 'Pokémon: Indigo League',
        'alternatives': ['Pokemon', 'Pokémon', 'Pocket Monsters', 'ポケットモンスター', 'Pokemon Season 1'],
        'description': 'Ash leaves Pallet Town with Pikachu and begins his journey as a Pokémon Trainer.',
        'year': 1997,
        'category': 'anime',
        'image': 'https://i.ytimg.com/vi/z3hMX65Khtg/hqdefault.jpg',
        'episodes': [
            (1, 'Pokémon, I Choose You!', 'https://www.youtube.com/watch?v=z3hMX65Khtg'),
            (2, 'Pokémon Emergency', 'https://www.youtube.com/watch?v=h6LFdBPjbf4'),
            (3, 'Ash Catches a Pokémon', 'https://www.youtube.com/watch?v=ObtS79k2NM4'),
        ],
    },
    'open-animation': {
        'title': 'Caminandes',
        'alternatives': ['Llama Drama', 'Gran Dillama', 'Llamigos'],
        'description': 'Three animated shorts follow Koro the llama through Patagonia.',
        'year': 2013,
        'category': 'animation',
        'image': '',
        'episodes': [
            (1, 'Llama Drama', COMMONS + 'Caminandes-_Llama_Drama_-_Short_Movie.ogv'),
            (2, 'Gran Dillama', COMMONS + 'Caminandes_-_Gran_Dillama_-_Blender_Foundation%27s_new_Open_Movie.webm'),
            (3, 'Llamigos', COMMONS + 'Caminandes_3_-_Llamigos_-_Blender_Animated_Short.webm'),
        ],
    },
}


def title_key(value):
    normalized = unicodedata.normalize('NFKD', str(value)).casefold()
    return ' '.join(re.findall(r'[^\W_]+', ''.join(c for c in normalized if not unicodedata.combining(c))))


def episodes(kind):
    return [
        {'number': n, 'season': 1, 'title': name, 'url': url}
        for n, name, url in CATALOGS[kind]['episodes']
    ]


def search(source, query, page):
    if page != 1:
        return [], False
    entry = CATALOGS[source['kind']]
    query_key = title_key(query)
    names = [entry['title'], *entry['alternatives'], *(e[1] for e in entry['episodes'])]
    description = title_key(entry['description'])
    if not query_key or not (
        any(query_key in title_key(name) or title_key(name) in query_key for name in names)
        or all(word in description.split() for word in query_key.split())
    ):
        return [], False
    result = record(
        source['id'], source['kind'], entry['title'], source_name=source['name'],
        alternatives=entry['alternatives'], description=entry['description'], year=entry['year'],
        category=entry['category'], thumbnail=entry['image'], url=entry['episodes'][0][2],
        media_urls=[entry['episodes'][0][2]],
    )
    result.update(episode_count=len(entry['episodes']), video_type='series', status='Episode pages found')
    return [result], False
