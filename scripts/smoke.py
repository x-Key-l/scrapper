"""Smoke an actual process, including PyInstaller builds; no source import needed."""
import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


def smoke(command):
    runtime=subprocess.run(command+['--check-runtime'],capture_output=True,text=True,timeout=30,check=True)
    evidence=json.loads(runtime.stdout)
    assert evidence['yt_dlp'] and evidence['ffmpeg'].startswith('ffmpeg version')
    with tempfile.TemporaryDirectory(prefix='scenetrace-smoke-') as folder:
        env=dict(os.environ,SCENETRACE_DATA=folder)
        proc=subprocess.Popen(command+['--no-browser'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def wait_ready():
            end=time.monotonic()+60
            while time.monotonic()<end:
                if proc.poll() is not None:
                    raise AssertionError('Application exited before becoming ready: '+str(proc.returncode))
                try:
                    info=json.loads((Path(folder)/'instance.json').read_text())
                    with opener.open(info['url']+'/health',timeout=1) as r:
                        health=json.load(r)
                    if health.get('instance')==info['instance']:
                        return info['url']
                except (OSError,ValueError):time.sleep(.15)
            raise AssertionError('Application startup timed out.')
        def post(address,path,body):
            req=urllib.request.Request(address+'/api/'+path,json.dumps(body).encode(),{'Content-Type':'application/json','X-SceneTrace':'local'})
            with opener.open(req,timeout=30) as r:return json.load(r)
        try:
            address=wait_ready()
            for asset in ('/','/app.js','/style.css','/icon.svg'):
                with opener.open(address+asset,timeout=5) as r:
                    assert r.status==200 and r.read()
            state=post(address,'state',{})
            assert len(state['sources'])>=6
            duplicate=subprocess.run(command+['--no-browser'],env=env,timeout=30)
            assert duplicate.returncode==0 and proc.poll() is None
            upload=post(address,'import/upload',{'name':'catalog.csv','data':base64.b64encode(b'id,title,description\n1,Forest Portal,A girl travels through a magic portal\n').decode()})
            task=post(address,'import/commit',{'upload_id':upload['upload_id'],'name':'Smoke catalog','role':'metadata','mapping':upload['mapping'],'categories':['movie']})
            for _ in range(100):
                task=post(address,'state',{})['tasks'][task['id']]
                if task['status']!='running':break
                time.sleep(.1)
            assert task['status']=='completed',task
            source_id=task['result']['source_id']
            found=post(address,'search',{'query':'magic portal girl','sources':[source_id],'mode':'memory'})
            assert found['results'][0]['title']=='Forest Portal'
            post(address,'save',{'record':found['results'][0]})
            post(address,'settings',{'destination':folder,'onboarded':True})
            diag=post(address,'diagnostics',{})
            assert 'magic portal' not in json.dumps(diag) and folder not in json.dumps(diag)
            post(address,'shutdown',{})
            proc.wait(timeout=25)
            assert proc.returncode==0
            proc=subprocess.Popen(command+['--no-browser'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            address=wait_ready()
            reopened=post(address,'state',{})
            assert reopened['settings']['onboarded'] and reopened['saved'][0]['title']=='Forest Portal'
            assert Path(reopened['settings']['destination']).samefile(folder)
            post(address,'shutdown',{})
            proc.wait(timeout=25)
            assert proc.returncode==0
            print('PASS: executable startup, assets, dynamic port, duplicate launch, HTTP import, FTS memory search, save, diagnostics, persistence and shutdown.')
        finally:
            if proc.poll() is None:
                proc.kill();proc.wait(timeout=10)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--exe')
    args=p.parse_args()
    smoke([str(Path(args.exe).resolve())] if args.exe else [sys.executable,'-m','scenetrace'])
