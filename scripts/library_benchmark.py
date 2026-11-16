"""Measure real SQLite metadata indexing; no media playback or speed claims."""
import json
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scenetrace.store import Store
from scenetrace.library import MediaLibrary
with tempfile.TemporaryDirectory() as folder:
    root=Path(folder);media=root/'videos';media.mkdir()
    # Small catalog fixtures measure filesystem traversal and metadata indexing only.
    for n in range(1000):(media/f'Series {n//25:02} S01E{n%25+1:02}.mp4').write_bytes(b'catalog indexing benchmark')
    library=MediaLibrary(Store(root/'profile'))
    start=time.perf_counter();result=library.import_folder(media);cold=time.perf_counter()-start
    start=time.perf_counter();library.import_folder(media);warm=time.perf_counter()-start
    report={'files':result['indexed'],'initial_index_seconds':round(cold,3),'unchanged_reindex_seconds':round(warm,3),'scope':'1000 small filesystem fixtures; SQLite catalog indexing, no video decoding'}
    output=Path('artifacts/library-benchmark.json');output.parent.mkdir(exist_ok=True);output.write_text(json.dumps(report,indent=2));print(json.dumps(report))
