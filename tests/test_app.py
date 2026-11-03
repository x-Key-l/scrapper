import base64
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
import pytest
from scenetrace.__main__ import make_server


@pytest.fixture
def server(tmp_path):
    s=make_server(tmp_path/'state')
    thread=threading.Thread(target=s.serve_forever,daemon=True)
    thread.start()
    try:yield s
    finally:
        s.shutdown();s.app.close();s.server_close();s.proxy.shutdown();s.proxy.server_close()
        thread.join(timeout=3)


def call(server,path,body=None,headers=None,host=None):
    url='http://127.0.0.1:'+str(server.server_port)+path
    h={'Content-Type':'application/json','X-SceneTrace':'local',**(headers or {})}
    if host:h['Host']=host
    request=urllib.request.Request(url,data=json.dumps(body).encode() if body is not None else None,headers=h)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request,timeout=5) as r:return r.status,r.headers,r.read()
    except urllib.error.HTTPError as e:return e.code,e.headers,e.read()


def test_startup_ui_static_assets_and_csp(server):
    status,headers,body=call(server,'/')
    assert status==200 and b'SceneTrace' in body
    assert "frame-ancestors 'none'" in headers['Content-Security-Policy']
    assert call(server,'/app.js')[0]==200
    assert json.loads(call(server,'/health')[2])['status']=='ok'
    assert call(server,'/../store.py')[0]==404
    assert call(server,'/%2e%2e/store.py')[0]==404


@pytest.mark.parametrize('headers',[
    {'Origin':'https://attacker.example'},
    {'Sec-Fetch-Site':'cross-site'},
    {'X-SceneTrace':'wrong'},
    {'Content-Type':'text/plain'},
])
def test_cross_site_calls_are_rejected(server,headers):
    assert call(server,'/api/state',{},headers)[0] in (400,403)


def test_host_header_rebinding_guard(server):
    assert call(server,'/health',host='attacker.example')[0]==403
    assert call(server,'/api/state',{},host='attacker.example')[0]==403


def test_real_http_import_search_save_persistence_and_diagnostics(server,tmp_path):
    csv='id,title,description\n1,Forest Girl,Magic portal adventure\n'
    d=json.loads(call(server,'/api/import/upload',{'name':'movies.csv','data':base64.b64encode(csv.encode()).decode()})[2])
    body={'upload_id':d['upload_id'],'name':'Test database','role':'metadata','mapping':d['mapping'],'categories':['movie']}
    task=json.loads(call(server,'/api/import/commit',body)[2])
    import time
    for _ in range(100):
        if server.app.tasks[task['id']]['status']!='running':break
        time.sleep(.02)
    assert server.app.tasks[task['id']]['status']=='completed'
    ident=server.app.tasks[task['id']]['result']['source_id']
    result=json.loads(call(server,'/api/search',{'query':'magic portal','sources':[ident],'mode':'memory'})[2])
    assert result['results'][0]['title']=='Forest Girl'
    r=result['results'][0]
    assert call(server,'/api/save',{'record':r})[0]==200
    assert server.app.store.saved()[0]['id']==r['id']
    assert call(server,'/api/settings',{'destination':str(tmp_path),'brave_key':'top-secret'})[0]==200
    diagnostics=call(server,'/api/diagnostics',{})[2].decode()
    assert 'top-secret' not in diagnostics and 'magic portal' not in diagnostics and str(tmp_path) not in diagnostics
    state=json.loads(call(server,'/api/state',{})[2])
    assert state['settings']['destination']==str(tmp_path)
    assert 'top-secret' not in json.dumps(state)


def test_format_ids_must_come_from_a_valid_analysis(server):
    status,_,_=call(server,'/api/download/add',{'analysis_id':'unknown','format_id':'1','authorized':True})
    assert status==400


def test_runtime_source_toggle_and_missing_credentials_are_honest(server):
    s=server.app.store.source('tmdb')
    s['enabled']=True
    assert server.app.source_update(s)['source']['enabled']
    result=server.app.test_source('tmdb')
    assert not result['ok'] and 'Token' in result['message']
    assert server.app.store.source('tmdb')['health']=='Unavailable'


def test_source_failure_not_global_server_failure(server):
    with patch('scenetrace.sources.search',side_effect=ValueError('Provider unavailable')):
        result=json.loads(call(server,'/api/search',{'query':'nature','sources':['tvmaze']})[2])
    assert result['sources'][0]['status']=='unavailable'
    assert call(server,'/health')[0]==200


def test_connection_test_does_not_overwrite_concurrent_configuration(server):
    def provider(*args):
        current=server.app.store.source('tvmaze')
        current.update(name='My television catalog',enabled=False)
        server.app.store.put_source(current)
        return [],False
    with patch('scenetrace.sources.search',side_effect=provider):
        assert server.app.test_source('tvmaze')['ok']
    actual=server.app.store.source('tvmaze')
    assert actual['name']=='My television catalog' and not actual['enabled']
    assert actual['health']=='Verified'
