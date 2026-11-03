import base64
import io
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit
import pytest
from scenetrace import importing, media, network, sources
from scenetrace.model import record, text, url, year
from scenetrace.search import SearchEngine, clues, deduplicate, rank
from scenetrace.store import Store, protect
from scenetrace.downloads import DownloadManager, safe_name


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path/'data')


def local_source(store, path, mapping=None):
    s=sources.validate(dict(name='My catalog',kind='local',role='metadata',categories=['anime'],mapping=mapping or {'id':'id','title':'name','description':'plot'}))
    s['local_path']=str(path)
    store.put_source(s)
    return s


def test_normalization_keeps_unicode_ids_and_plain_text():
    r=record('catalog','42','<b>魔女 &amp; The Forest</b>',year='1987-04-12',description='<script>alert(1)</script>',external_ids={'imdb':'tt1'},url='javascript:alert(1)',media_urls=['file:///private','https://example.org/a.mp4'])
    assert r['title']=='魔女 & The Forest' and r['year']==1987
    assert r['url']=='' and r['media_urls']==['https://example.org/a.mp4']
    assert '<' not in r['description']


@pytest.mark.parametrize('value',[None,'Unknown',''])
def test_unknown_year_remains_unknown(value):
    assert year(value) is None


@pytest.mark.parametrize('extension,data',[
    ('.csv','id,name,plot\n1,Forest Girl,Portal in the woods\n2,Other,School comedy\n'),
    ('.tsv','id\tname\tplot\n1\tForest Girl\tPortal in the woods\n2\tOther\tSchool comedy\n'),
    ('.json',json.dumps([{'id':1,'name':'Forest Girl','plot':'Portal in the woods'},{'id':2,'name':'Other','plot':'School comedy'}])),
    ('.jsonl','{"id":1,"name":"Forest Girl","plot":"Portal in the woods"}\n{"id":2,"name":"Other","plot":"School comedy"}\n'),
])
def test_imports_are_fts_searchable_and_persist(store,tmp_path,extension,data):
    path=tmp_path/('export'+extension)
    path.write_text(data)
    s=local_source(store,path)
    assert importing.import_source(store,s)==2
    reopened=Store(store.root)
    hits=reopened.local_search(['portal'],[s['id']])
    assert len(hits)==1 and hits[0]['title']=='Forest Girl'
    assert importing.preview(path)['samples']


def test_sqlite_import_quoted_table_readonly(store,tmp_path):
    path=tmp_path/'db.sqlite'
    with sqlite3.connect(path) as c:
        c.execute('CREATE TABLE "my "" videos"(id TEXT,name TEXT,plot TEXT)')
        c.execute('INSERT INTO "my "" videos" VALUES(?,?,?)',('a','Forest Girl','Magic portal'))
    before=path.read_bytes()
    s=local_source(store,path);s['table']='my " videos'
    assert importing.import_source(store,s)==1
    assert path.read_bytes()==before
    s['table']='records; DROP TABLE data'
    with pytest.raises(ValueError):importing.import_source(store,s)


def test_malformed_late_row_rolls_back_entire_import(store,tmp_path):
    p=tmp_path/'file.jsonl'
    p.write_text('{"id":1,"name":"Original","plot":"Forest"}\n')
    s=local_source(store,p)
    importing.import_source(store,s)
    p.write_text('{"id":2,"name":"New","plot":"Forest"}\n{"broken":')
    with pytest.raises(ValueError):importing.import_source(store,s)
    assert store.local_search(['forest'],[s['id']])[0]['title']=='Original'


def test_json_nested_export_and_mapping(store,tmp_path):
    p=tmp_path/'file.json'
    p.write_text(json.dumps({'data':{'items':[{'key':77,'title':{'english':'Sky Road'},'details':{'plot':'Space journey'}}]}}))
    s=local_source(store,p,{'id':'key','title':'title.english','description':'details.plot'})
    s['items_path']='data.items'
    assert importing.import_source(store,s)==1
    assert store.local_search(['space'],[s['id']])[0]['source_record_id']=='77'


def test_feed_import_handles_atom_media_rss_and_rejects_entities():
    data=b'<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/"><entry><id>1</id><title>Sky Road</title><summary>Space story</summary><link href="https://example.org/watch"/><media:content url="https://example.org/video.mp4" type="video/mp4"/></entry></feed>'
    rows=sources.feed_rows(data)
    assert rows[0]['media_url'].endswith('.mp4')
    assert rows[0]['description']=='Space story'
    with pytest.raises(ValueError):sources.feed_rows(b'<!DOCTYPE x [<!ENTITY a "secret">]><rss/>')


def test_no_title_row_is_not_silently_accepted(store,tmp_path):
    p=tmp_path/'file.json';p.write_text('[{"id":1,"wrong":"No title"}]')
    s=local_source(store,p)
    with pytest.raises(ValueError):importing.import_source(store,s)


def test_memory_expands_clues_without_confidence_fabrication():
    memory=clues('Animated show from the 1990s transported into another world near a forest')
    assert memory['year_from']==1990 and memory['genre']=='Fantasy'
    assert 'isekai' in memory['expanded']
    rs=[record('a','1','Forest Portal',description='A girl in the woods discovers a magic portal.',year=1995,genres=['Fantasy'],category='anime'),
        record('b','2','Motor Road',description='Racing cars.',year=2020)]
    ranked=rank('girl forest portal',rs,memory)
    assert ranked[0]['id']=='a:1'
    assert any('Title' in x for x in ranked[0]['evidence'])
    assert 'confidence' not in ranked[0]


def test_uncertain_dates_do_not_remove_good_memory_matches():
    memory=clues('portal girl',{'decade':'1980'})
    r=record('a','1','Portal Girl',description='Girl through a portal',year=2019)
    assert rank('portal girl',[r],memory)[0]['id']==r['id']


def test_strong_id_cross_reference_retains_both_origins():
    a=record('one','1','Sky Road',year=2001,external_ids={'imdb':'tt123'})
    b=record('two','999','Alternative title',year=2001,external_ids={'imdb':'tt123'},media_urls=['https://example.org/a.mp4'])
    found=deduplicate([a,b])
    assert len(found)==1 and len(found[0]['origins'])==2
    assert found[0]['media_urls']


def test_similar_titles_and_conflicting_ids_never_merge():
    a=record('a','1','The Forest',year=2010,external_ids={'imdb':'tt1'})
    b=record('b','2','The Forest',year=2010,external_ids={'imdb':'tt2'})
    c=record('c','3','The Forest',year=1950,external_ids={'imdb':'tt1'})
    assert len(deduplicate([a,b,c]))==3


def test_federation_isolates_failure_and_uses_cache(store):
    for ident in ('good','broken'):
        store.put_source(dict(id=ident,name=ident,kind='rest',role='metadata',enabled=True,categories=['movie'],endpoint='https://example.org/api',mapping={}))
    count=[]
    def search(s,q,page,memory):
        count.append(s['id'])
        if s['id']=='broken':raise ValueError('Provider offline')
        return [record('good','1','Forest',description='Forest girl')],False
    engine=SearchEngine(store)
    try:
        with patch('scenetrace.sources.search',side_effect=search):
            first=engine.run('forest')
            second=engine.run('forest')
        assert any(r['title']=='Forest' for r in first['results'])
        assert any(s['status']=='unavailable' for s in first['sources'])
        assert count.count('good')==1
        assert second['results'] and store.history()
    finally:engine.close()


def test_federation_source_selection_and_cancel(store):
    s=dict(id='one',name='one',kind='rest',role='metadata',enabled=True,categories=['movie'],endpoint='https://example.org')
    store.put_source(s)
    engine=SearchEngine(store)
    try:
        assert engine.run('forest',[])['results']==[]
        engine.cancel('req')
        assert engine.run('forest',request_id='req')['cancelled']
    finally:engine.close()


def test_rest_mapping_pagination_and_auth():
    s=sources.validate(dict(name='Demo',kind='rest',role='hybrid',endpoint='https://example.org/api',categories=['movie'],items_path='data.items',query_param='search',page_param='page',page_size=1,mapping={'id':'key','title':'name','media_url':'file'},token='secret',auth_header='X-API-Key',auth_prefix=''))
    with patch('scenetrace.network.json_request',return_value={'data':{'items':[{'key':'a','name':'Example','file':'https://example.org/media.mp4'}]}}) as req:
        rows,more=sources._search(s,'forest',3)
        assert rows[0]['media_urls'] and more
        assert 'page=3' in req.call_args[0][0]
        assert req.call_args.kwargs['headers']['X-API-Key']=='secret'


def test_graphql_uses_variables_and_no_string_interpolation():
    s=sources.validate(dict(name='Graph',kind='graphql',role='metadata',endpoint='https://example.org/graphql',graphql='query($query:String,$page:Int){items(query:$query){id title}}',items_path='data.items',categories=['video']))
    q='"} mutation { deleteEverything }'
    with patch('scenetrace.network.json_request',return_value={'data':{'items':[{'id':1,'title':'Safe'}]}}) as req:
        rows,_=sources._search(s,q,1)
        payload=req.call_args[0][1]
        assert payload['variables']['query']==q and q not in payload['query']
        assert rows[0]['title']=='Safe'
    with pytest.raises(ValueError):sources.validate({**s,'graphql':'mutation { delete }'})


@pytest.mark.parametrize('header',['Host','Cookie','Content-Length','X-API-Key\r\nBad'])
def test_unsafe_auth_headers_rejected(header):
    with pytest.raises(ValueError):sources.validate(dict(name='Bad',kind='rest',role='metadata',endpoint='https://example.org',auth_header=header))


def test_plain_website_not_reported_as_api():
    with patch('scenetrace.network.fetch',return_value=(b'<html><video></video></html>','text/html','https://example.org')):
        assert sources.detect('https://example.org')['kind']=='website'


def test_tokens_are_hidden_in_public_config(store):
    s=sources.validate(dict(name='Credential',kind='rest',role='metadata',endpoint='https://example.org',token='secret'))
    store.put_source(s)
    assert 'secret' not in json.dumps(store.sources(public=True))
    assert store.source(s['id'])['token']=='secret'
    if os.name=='nt':
        with store.db() as c:assert 'secret' not in c.execute('SELECT config FROM sources').fetchone()[0]


@pytest.mark.parametrize('value',['file:///etc/passwd','http://localhost/x','http://user:pass@example.org/','https://example.org/\r\nx','http://127.0.0.1/'])
def test_unsafe_destinations_rejected(value):
    with pytest.raises(network.UnsafeURL):network.target(value)


def test_mixed_dns_and_rebinding_protected():
    answers=[(2,1,6,'',('93.184.216.34',443)),(2,1,6,'',('127.0.0.1',443))]
    with patch('socket.getaddrinfo',return_value=answers):
        with pytest.raises(network.UnsafeURL):network.target('https://example.org')
    with patch('socket.getaddrinfo',return_value=answers[:1]):
        assert network.target('https://example.org')[3]=='93.184.216.34'


def test_network_connection_pins_ip_and_retains_tls_hostname():
    with patch('socket.create_connection') as connect, patch('ssl.create_default_context') as context:
        conn=network.PinnedHTTPS('example.org',443,'93.184.216.34',5)
        conn.connect()
        assert connect.call_args[0][0]==('93.184.216.34',443)
        assert context.return_value.wrap_socket.call_args.kwargs['server_hostname']=='example.org'


def test_archive_analysis_separates_catalog_from_files():
    raw={'metadata':{'title':'Example','licenseurl':'https://creativecommons.org/licenses/by-nc/4.0/'},'files':[{'name':'original.mp4','size':'4'},{'name':'private.mp4','private':True},{'name':'metadata.xml'}]}
    with patch('scenetrace.network.target'),patch('scenetrace.network.json_request',return_value=raw):
        r=media.analyze('https://archive.org/details/example','proxy')
    assert r['status']=='Download available' and len(r['formats'])==1
    assert 'by-nc' in r['license']


def test_trailer_is_never_labeled_full_movie():
    selected=record('a','1','Example',duration=7000)
    assert media.classify(record('b','1','Example Official Trailer',duration=130),selected)=='Trailer / preview'
    assert 'unconfirmed' in media.classify(record('b','2','Example full movie',duration=7000),selected)


@pytest.mark.parametrize('value',['../x','CON','NUL.txt','a:b/c\\d','', 'COM1'])
def test_windows_names_cannot_traverse_or_use_reserved_files(value):
    result=safe_name(value)
    assert '/' not in result and '\\' not in result and ':' not in result
    assert result.split('.')[0].upper() not in ('CON','NUL','COM1')


class Response:
    def __init__(self,data,status=200,headers=None):
        self.stream=io.BytesIO(data);self.status=status
        self.headers=headers or {'Content-Length':str(len(data))}
    def read(self,n):return self.stream.read(n)
    def getheader(self,k,default=None):return self.headers.get(k,default)


class Connection:
    def close(self):pass


def wait_job(manager,key,statuses=('completed','failed','cancelled'),seconds=5):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        j=manager.items[key]
        if j['status'] in statuses and not j.get('_running'):return j
        time.sleep(.02)
    raise AssertionError('Job did not finish: '+str(manager.public(manager.items[key])))


def add_job(manager,tmp_path,title='Example'):
    return manager.add({'title':title,'url':'https://example.org/watch'},{'id':'0','ext':'mp4','size':4,'method':'direct','url':'https://example.org/file.mp4'},str(tmp_path),True)


def test_download_consent_collision_bytes_and_persistence(store,tmp_path):
    m=DownloadManager(store,'proxy',workers=1)
    try:
        with pytest.raises(ValueError):m.add({'title':'X','url':'https://example.org'},{'ext':'mp4'},str(tmp_path),False)
        (tmp_path/'Example.mp4').write_bytes(b'KEEP')
        with patch('scenetrace.network.open_url',return_value=(Connection(),Response(b'DATA'),'url')):
            j=add_job(m,tmp_path);done=wait_job(m,j['id'])
        assert Path(done['path']).read_bytes()==b'DATA'
        assert (tmp_path/'Example.mp4').read_bytes()==b'KEEP'
        assert done['status']=='completed' and store.jobs()
    finally:m.close()


def test_download_interruption_and_validated_range_resume(store,tmp_path):
    m=DownloadManager(store,'proxy',workers=0)
    try:
        j=add_job(m,tmp_path);internal=m.items[j['id']]
        Path(internal['part']).write_bytes(b'DA')
        with patch('scenetrace.network.open_url',return_value=(Connection(),Response(b'TA',206,{'Content-Length':'2','Content-Range':'bytes 2-3/4'}),'url')) as opened:
            m._direct(internal)
        assert opened.call_args.kwargs['headers']['Range']=='bytes=2-'
        assert Path(internal['part']).read_bytes()==b'DATA'
        Path(internal['part']).write_bytes(b'OLD')
        with patch('scenetrace.network.open_url',return_value=(Connection(),Response(b'NEW!'),'url')):
            m._direct(internal)
        assert Path(internal['part']).read_bytes()==b'NEW!'
    finally:m.close()


def test_invalid_range_or_short_response_fails(store,tmp_path):
    m=DownloadManager(store,'proxy',workers=0)
    try:
        j=add_job(m,tmp_path);internal=m.items[j['id']]
        Path(internal['part']).write_bytes(b'A')
        with patch('scenetrace.network.open_url',return_value=(Connection(),Response(b'DATA',206,{'Content-Range':'bytes 0-3/4'}),'url')):
            with pytest.raises(ValueError):m._direct(internal)
        with patch('scenetrace.network.open_url',return_value=(Connection(),Response(b'DA',200,{'Content-Length':'4'}),'url')):
            with pytest.raises(ValueError):m._direct(internal)
    finally:m.close()


def test_cancel_cleans_partial_and_restart_preserves_paused(store,tmp_path):
    m=DownloadManager(store,'proxy',workers=0)
    j=add_job(m,tmp_path);internal=m.items[j['id']]
    Path(internal['part']).write_bytes(b'DA')
    m.control(j['id'],'cancel')
    assert not Path(internal['part']).exists()
    other=add_job(m,tmp_path,'Second')
    m.close()
    reopened=DownloadManager(store,'proxy',workers=0)
    try:
        assert reopened.items[other['id']]['status']=='paused'
    finally:reopened.close()


def test_disk_space_checked_before_queueing(store,tmp_path):
    m=DownloadManager(store,'proxy',workers=0)
    try:
        with patch('shutil.disk_usage',return_value=type('Disk',(),{'free':1})()):
            with pytest.raises(ValueError):add_job(m,tmp_path)
    finally:m.close()


def test_custom_credentials_removed_on_cross_host_redirect():
    class Redirect:
        status=302
        def getheader(self,key,default=None):return 'https://other.example/data' if key=='Location' else default
    class Success:
        status=200
    first=type('Conn',(),{})()
    second=type('Conn',(),{})()
    from unittest.mock import Mock
    for c,r in ((first,Redirect()),(second,Success())):
        c.request=Mock();c.getresponse=Mock(return_value=r);c.close=Mock()
    def resolved(value):
        p=urlsplit(value)
        return p,p.hostname,443,'93.184.216.34'
    with patch('scenetrace.network.target',side_effect=resolved),patch('scenetrace.network.PinnedHTTPS',side_effect=[first,second]):
        network.open_url('https://source.example/data',headers={'X-Custom-Secret':'private','Authorization':'Bearer private','Range':'bytes=2-'})
    sent=second.request.call_args[0][3]
    assert 'X-Custom-Secret' not in sent and 'Authorization' not in sent
    assert sent['Range']=='bytes=2-'
