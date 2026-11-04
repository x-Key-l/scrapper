"""Real integration evidence, never mocked. Failures are recorded individually."""
import json
import tempfile
import time
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scenetrace import media, network, sources


def run():
    report={'checked_at':time.time(),'mocked':False,'catalogs':[],'media':[]}
    for source in sources.GALLERY:
        if source['id']=='tmdb':
            report['catalogs'].append({'source':'TMDB','status':'not tested','reason':'Optional owner API token not supplied.'})
            continue
        try:
            query = {'anilist':'Naruto', 'pokemon-tv':'Pocket Monsters', 'open-animation':'Caminandes'}.get(source['id'], 'nature')
            rows, more = sources.search(source, query)
            assert rows, 'The provider returned no usable records for the sample query.'
            assert all(r['title'] and r['source_id']==source['id'] for r in rows)
            report['catalogs'].append({'source':source['name'],'status':'search verified','count':len(rows),'sample_title':rows[0]['title']})
        except Exception as exc:
            report['catalogs'].append({'source':source['name'],'status':'unavailable','reason':str(exc)[:200]})
    proxy=network.start_proxy()
    try:
        for name,value in [('Internet Archive','https://archive.org/details/BigBuckBunny_328'),
                           ('Generic yt-dlp','https://www.w3schools.com/html/mov_bbb.mp4')]:
            try:
                info=media.analyze(value,'http://127.0.0.1:'+str(proxy.server_port))
                assert info.get('formats'), 'No usable formats returned.'
                check={'source':name,'status':'verified metadata and formats','formats':len(info['formats']),'title':info.get('title')}
                direct=next((x for x in info['formats'] if x.get('url')),None)
                if direct:
                    conn,r,_=network.open_url(direct['url'],headers={'Range':'bytes=0-1023'})
                    try:
                        data=r.read(1024)
                        assert data
                        check['media_bytes_received']=len(data)
                        check['range_http_status']=r.status
                    finally:conn.close()
                report['media'].append(check)
            except Exception as exc:
                report['media'].append({'source':name,'status':'unavailable','reason':str(exc)[:200]})
    finally:
        proxy.shutdown();proxy.server_close()
    Path('live-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    return report


if __name__=='__main__':run()
