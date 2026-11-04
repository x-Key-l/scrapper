"""Fixed known-answer retrieval cases, live candidates, and paired v3/v4 ranking."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scenetrace.app import App
from scenetrace.deep import rank, understand
from scenetrace.search import deduplicate

CASES = [
    ('exact anime', 'Naruto', {}, ['Naruto'], ['anilist','tvmaze']),
    ('misspelled anime', 'Nartuo', {}, ['Naruto'], ['anilist','tvmaze']),
    ('Japanese title', '進撃の巨人', {}, ['Attack on Titan', 'Shingeki no Kyojin'], ['anilist','tvmaze']),
    ('incomplete title', 'Fullmetal Alchem', {}, ['Fullmetal Alchemist: Brotherhood','Fullmetal Alchemist'], ['anilist','tvmaze']),
    ('named character', 'Kakashi Hatake', {'category':'anime','character':'Kakashi Hatake'}, ['Naruto','Naruto: Shippuden'], ['anilist']),
    ('character appearance', 'Anime with a white-haired teacher who covers one eye', {}, ['Naruto','Naruto: Shippuden'], ['anilist']),
    ('actor and setting', 'An old action movie with Jackie Chan where he fights criminals in a city', {}, ['Police Story','Rush Hour','Rumble in the Bronx','Police Story 2'], ['itunes']),
    ('partial plot', 'Anime about a student with a notebook that kills people whose names he writes', {}, ['Death Note'], ['anilist']),
    ('ambiguous scene', 'A movie where people discover an underground cave and encounter dangerous creatures', {}, ['The Descent','The Cave'], ['itunes']),
    ('incorrect period', 'Anime where a boy trains as a ninja with a demon sealed inside him from the 1980s', {}, ['Naruto','Naruto: Shippuden'], ['anilist']),
    ('combined clues', 'Animated show about brothers who use alchemy after trying to restore their mother', {}, ['Fullmetal Alchemist: Brotherhood','Fullmetal Alchemist'], ['anilist']),
]


def position(rows, names):
    expected = {name.casefold() for name in names}
    return next((i+1 for i,row in enumerate(rows) if expected & {t.casefold() for t in [row['title']] + row.get('alternatives', [])}), None)


parser = argparse.ArgumentParser()
parser.add_argument('--baseline', default='baseline/scenetrace/search.py')
args = parser.parse_args()
out = Path('artifacts/deep-evaluation')
out.mkdir(parents=True, exist_ok=True)
report, corpus = [], []
for label, query, hints, expected, selected in CASES:
    with tempfile.TemporaryDirectory(prefix='scenetrace-evaluation-') as profile:
        app = App(profile, None)
        started = time.perf_counter()
        try:
            result = app.search.run(query, selected, mode='deep', hints=hints)
            corpus.extend(result['results'])
            report.append(dict(case=label, query=query, hints=hints, expected=expected,
                               cold_live_rank=position(result['results'], expected),
                               seconds=round(time.perf_counter()-started,3), sources=result['sources'],
                               top_ten=[{'id':r['id'],'title':r['title'],'evidence':r['evidence']} for r in result['results'][:10]]))
        finally:
            app.close()

corpus = deduplicate(corpus)
baseline_path = Path(args.baseline)
if not baseline_path.is_file():
    raise RuntimeError('Pinned v3 baseline search.py is required for the paired comparison.')
spec = importlib.util.spec_from_file_location('scenetrace.baseline_search', baseline_path)
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)
for case in report:
    query, hints = case['query'], case['hints']
    old = baseline.rank(query, copy.deepcopy(corpus), baseline.clues(query, hints))
    new = rank(query, copy.deepcopy(corpus), understand(query, hints))
    case['v3_same_corpus_rank'] = position(old, case['expected'])
    case['v4_same_corpus_rank'] = position(new, case['expected'])

summary = {}
for field in ('cold_live_rank','v3_same_corpus_rank','v4_same_corpus_rank'):
    summary[field] = {f'top_{k}':sum(r[field] is not None and r[field]<=k for r in report) for k in (5,10)}
    summary[field]['cases'] = len(report)
payload = dict(scope='Eleven fixed examples, not a general accuracy claim. Cold live tests use an empty local index per case. Paired ranking uses identical real provider candidates collected across these cases.',
               baseline_revision='5383d468d3ce0fe2c21e2b86f80636399707869b', corpus_records=len(corpus), summary=summary, cases=report)
(out/'results.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
(out/'corpus.json').write_text(json.dumps(corpus),encoding='utf-8')
print(json.dumps(payload,indent=2))
